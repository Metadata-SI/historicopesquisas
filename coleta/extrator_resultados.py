"""
Extração dos percentuais por candidato a partir do texto das matérias.

Só aceita blocos estruturados em lista ("- Lula (PT): 39% (eram 38%)"), formato usado por
g1 e Estadão. Números em prosa ou em imagens não são lidos: se a matéria não traz o cenário
completo, nada é gravado.

Cada cenário só entra no banco se passar por TODAS as verificações:
  * o rótulo de cada linha é um candidato (com partido ou nome conhecido) ou Branco/Indeciso;
  * a soma dos percentuais fica na faixa aceita pelo validador;
  * o registro tem um único código BR ligado ao bloco e existe na base oficial do TSE;
  * a amostra citada na matéria é a mesma do TSE (pega códigos trocados nas matérias);
  * a abrangência (nacional ou UF) é inequívoca;
  * não contradiz o que outra matéria já gravou para o mesmo cenário.
O que falhar vai para a quarentena com o motivo.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from coleta.descoberta import extrair_amostras, extrair_codigos
from modelo.database import (
    registrar_quarentena,
    salvar_cenario,
    salvar_fonte,
    salvar_instituto,
    salvar_pesquisa,
    salvar_resultado,
)
from modelo.validador import validar_soma_percentuais

logger = logging.getLogger("coleta.extrator_resultados")

REGEX_ITEM = re.compile(r"^\s*[-•*]\s*(?P<rotulo>[^:]+?)\s*:\s*(?P<resto>.*)$")
REGEX_PCT = re.compile(r"^(?P<pct>\d{1,3}(?:[.,]\d+)?)\s*%")
REGEX_PARTIDO = re.compile(r"\(([A-Za-zÀ-ú]{2,15}(?:[ /-][A-Za-z]{2,10})?)\)\s*$")
PREFIXOS_TITULO = re.compile(
    r"^(escritor|veterin[aá]rio|senador|senadora|deputado|deputada|governador|governadora|"
    r"ex-presidente|presidente|ex-governador|prefeito|empres[aá]rio|m[eé]dico|apresentador|"
    r"pastor|coronel|delegado|professor|professora|advogado)\s+",
    re.IGNORECASE,
)
REGEX_BRANCO = re.compile(r"branco|nulo|nenhum", re.IGNORECASE)
REGEX_INDECISO = re.compile(r"indecis|n[aã]o sabe|n[aã]o respond|n[aã]o soube|n[aã]o souberam", re.IGNORECASE)

ESTADOS = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas", "BA": "Bahia", "CE": "Ceará",
    "DF": "Distrito Federal", "ES": "Espírito Santo", "GO": "Goiás", "MA": "Maranhão",
    "MT": "Mato Grosso", "MS": "Mato Grosso do Sul", "MG": "Minas Gerais", "PA": "Pará",
    "PB": "Paraíba", "PR": "Paraná", "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte", "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    ).lower()


@dataclass
class Bloco:
    linhas: List[Dict[str, Any]]  # {"rotulo", "percentual" (None se a linha está sem número)}
    antes: List[str]              # linhas de texto (não-lista) imediatamente antes
    depois: str                   # texto entre este bloco e o próximo
    inicio: int = 0
    fim: int = 0

    @property
    def linhas_ilegiveis(self) -> List[str]:
        return [l["rotulo"] for l in self.linhas if l["percentual"] is None]


@dataclass
class Cenario:
    turno: int
    nome: str
    resultados: Dict[str, float]
    bloco: Bloco = field(repr=False, default=None)  # type: ignore[assignment]
    erro: Optional[str] = None  # preenchido quando o bloco é de voto mas está corrompido


def _numero(txt: str) -> float:
    return float(txt.replace(",", "."))


def segmentar_blocos(texto: str) -> List[Bloco]:
    """
    Agrupa itens de lista consecutivos ('- rótulo: ...') em blocos, com o contexto ao redor.
    Um item sem percentual legível (ex.: '- Fulano (PX): % (era 0%)') não quebra o bloco:
    fica marcado como ilegível, para o bloco inteiro ser rejeitado em vez de virar dois.
    """
    linhas = texto.splitlines()
    blocos: List[Bloco] = []
    i = 0
    while i < len(linhas):
        if not REGEX_ITEM.match(linhas[i]):
            i += 1
            continue
        inicio = i
        itens: List[Dict[str, Any]] = []
        while i < len(linhas) and (m := REGEX_ITEM.match(linhas[i])):
            p = REGEX_PCT.match(m.group("resto").strip())
            itens.append({
                "rotulo": m.group("rotulo").strip(),
                "percentual": _numero(p.group("pct")) if p else None,
            })
            i += 1
        antes = [l.strip() for l in linhas[max(0, inicio - 4):inicio] if l.strip() and not REGEX_ITEM.match(l)]
        blocos.append(Bloco(linhas=itens, antes=antes[-2:], depois="", inicio=inicio, fim=i))

    for idx, b in enumerate(blocos):
        proximo = blocos[idx + 1] if idx + 1 < len(blocos) else None
        seg = linhas[b.fim:(proximo.inicio if proximo else len(linhas))]
        # A última linha do trecho costuma ser o título do bloco seguinte ("Minas Gerais: ..."),
        # que não descreve este bloco.
        if proximo and proximo.antes and seg and seg[-1].strip() == proximo.antes[-1]:
            seg = seg[:-1]
        b.depois = "\n".join(seg)
    return blocos


def classificar_rotulo(rotulo: str) -> Optional[Dict[str, str]]:
    """
    Devolve {"tipo": "candidato"|"branco"|"indeciso", "nome": canônico} ou None se desconhecido.
    Candidato = rótulo com partido entre parênteses ou nome já conhecido (ex.: 2º turno sem partido).
    """
    limpo = re.sub(r"\s+", " ", rotulo).strip(" ;.")
    if REGEX_INDECISO.search(limpo) and not REGEX_BRANCO.search(limpo):
        return {"tipo": "indeciso", "nome": "Indeciso/Não Sabe"}
    if REGEX_BRANCO.search(limpo):
        return {"tipo": "branco", "nome": "Branco/Nulo"}
    m = REGEX_PARTIDO.search(limpo)
    nome = REGEX_PARTIDO.sub("", limpo).strip() if m else limpo
    nome = PREFIXOS_TITULO.sub("", nome).strip()
    if not nome or len(nome.split()) > 4:
        return None
    if m:
        return {"tipo": "candidato", "nome": nome}
    return {"tipo": "sem_partido", "nome": nome}


def extrair_cenarios(texto: str, candidatos_conhecidos: Set[str]) -> List[Cenario]:
    """Converte blocos de lista em cenários. Blocos que não são intenção de voto são ignorados."""
    cenarios: List[Cenario] = []
    conhecidos = {_sem_acento(n) for n in candidatos_conhecidos}
    for bloco in segmentar_blocos(texto):
        classes = [classificar_rotulo(l["rotulo"]) for l in bloco.linhas]
        if any(c is None for c in classes):
            continue

        # "sem_partido" só vale se o nome é de candidato conhecido; senão o bloco não é de voto
        # (ex.: "Mais um mandato de Lula: 49%" ou "Tenho medo dos dois").
        if any(c["tipo"] == "sem_partido" and _sem_acento(c["nome"]) not in conhecidos for c in classes):
            continue

        nominais = [c["nome"] for c in classes if c["tipo"] in ("candidato", "sem_partido")]
        if len(nominais) < 2 or len(set(nominais)) != len(nominais):
            continue
        # Bloco de presidente tem ao menos um candidato monitorado; o resto (governador, senador)
        # é de outra disputa e não interessa aqui.
        if not any(_sem_acento(n) in conhecidos for n in nominais):
            continue

        resultados: Dict[str, float] = {}
        duplicado = False
        for c, l in zip(classes, bloco.linhas):
            if c["nome"] in resultados:
                duplicado = True
                break
            resultados[c["nome"]] = l["percentual"] if l["percentual"] is not None else 0.0
        if duplicado:
            continue

        if len(nominais) == 2:
            turno, nome = 2, f"2º Turno - {nominais[0]} x {nominais[1]}"
        else:
            contexto = _sem_acento(" ".join(bloco.antes))
            m = re.search(r"cenario\s+(\d)\b", contexto)
            turno = 1
            nome = "Espontânea" if "espontanea" in contexto else f"Estimulada {m.group(1) if m else 1}"
        erro = None
        if bloco.linhas_ilegiveis:
            erro = f"lista com item(ns) sem percentual legível: {bloco.linhas_ilegiveis}"
        cenarios.append(Cenario(turno=turno, nome=nome, resultados=resultados, bloco=bloco, erro=erro))
    return cenarios


def _estados_em(texto: str, ignorar: Optional[List[str]] = None) -> Set[str]:
    """
    Estados citados no texto, por nome ou por 'em/no/na/de/do/da SIGLA'.
    `ignorar` remove antes nomes que contêm o de um estado (ex.: 'Paraná Pesquisas').
    """
    # Nomes casados com maiúscula e acento exatos: sem acento, "Pará" viraria a preposição "para".
    base = texto
    for termo in ignorar or []:
        base = re.sub(re.escape(termo), " ", base, flags=re.IGNORECASE)
    base = base.replace("Mato Grosso do Sul", "Mato-Grosso-do-Sul")  # não confundir com Mato Grosso

    achados: Set[str] = set()
    for uf, nome in ESTADOS.items():
        alvo = nome.replace("Mato Grosso do Sul", "Mato-Grosso-do-Sul")
        if re.search(rf"\b{re.escape(alvo)}\b", base):
            achados.add(uf)
    for uf in re.findall(r"\b(?:em|no|na|de|do|da)\s+([A-Z]{2})\b", texto):
        if uf in ESTADOS:
            achados.add(uf)
    return achados


def detectar_abrangencia(
    titulo: str, url: str, todos_codigos: Set[str], bloco: Bloco, ignorar: Optional[List[str]] = None
) -> str:
    """'BR' (nacional), sigla da UF, ou 'INDEFINIDA' quando os sinais se contradizem."""
    # Contexto local: só as linhas coladas ao bloco (o restante da matéria pode citar outros estados).
    local = _estados_em(" ".join(bloco.antes[-1:]) + "\n" + "\n".join(bloco.depois.splitlines()[:2]), ignorar)
    if len(local) == 1:
        return next(iter(local))
    if len(local) > 1:
        return "INDEFINIDA"

    globais = _estados_em(titulo, ignorar)
    m = re.search(r"/([a-z]{2})/[a-z-]+/", url)
    if m and m.group(1).upper() in ESTADOS:
        globais.add(m.group(1).upper())
    globais |= {c[:2] for c in todos_codigos if not c.startswith("BR-") and c[:2] in ESTADOS}
    if len(globais) == 1:
        return next(iter(globais))
    if len(globais) > 1:
        return "INDEFINIDA"
    return "BR"


def _amostras_e_codigo(
    bloco: Bloco, texto_completo: str, codigos_br_materia: Set[str]
) -> Dict[str, Any]:
    """
    Descobre o código BR e as amostras que valem para o bloco.

    Amostra: a citada logo após o bloco. Só se ali não houver nenhuma se usa a da matéria
    inteira, e apenas quando ela cita um único tamanho de amostra (senão não dá para saber
    a qual pesquisa pertence e o conjunto fica vazio).
    Código: o único BR da matéria; em resumos com vários, o único BR logo após o bloco.
    """
    amostras = extrair_amostras(bloco.depois)
    if not amostras:
        todas = extrair_amostras(texto_completo)
        amostras = todas if len(todas) == 1 else set()

    if len(codigos_br_materia) == 1:
        return {"codigo": next(iter(codigos_br_materia)), "amostras": amostras}
    locais = {c for c in extrair_codigos(bloco.depois) if c.startswith("BR-")}
    if len(locais) == 1:
        return {"codigo": next(iter(locais)), "amostras": amostras}
    return {"codigo": None, "amostras": set()}


def _conflita(a: Dict[str, float], b: Dict[str, float]) -> bool:
    """
    Duas versões do mesmo cenário se contradizem se algum candidato em comum tem valor diferente
    ou se um candidato ausente de um lado tem valor diferente de zero no outro.
    (Resumos listam só quem pontuou; a matéria completa traz os zerados.)
    """
    return any(a.get(c, 0.0) != b.get(c, 0.0) for c in set(a) | set(b))


def _sugerir_registro_por_amostra(
    conn: sqlite3.Connection, amostras: Set[int], instituto_tse: str, data_divulgacao: str
) -> List[str]:
    if not amostras:
        return []
    marcadores = ",".join("?" for _ in amostras)
    linhas = conn.execute(
        f"""
        SELECT registro_tse FROM registro_tse_oficial
        WHERE empresa_nome = ? AND data_divulgacao = ? AND amostra IN ({marcadores})
        """,
        [instituto_tse, data_divulgacao, *sorted(amostras)],
    ).fetchall()
    return [r["registro_tse"] for r in linhas]


def _nome_instituto(empresa_nome: Optional[str], institutos: List[Dict[str, Any]]) -> Optional[str]:
    base = (empresa_nome or "").upper()
    for inst in institutos:
        if any(t.upper() in base for t in inst["tse"]):
            return inst["nome"]
    return empresa_nome or None


def _quarentena(conn, motivo, registro, portal, url, extra=None):
    with conn:
        registrar_quarentena(
            conn, motivo, registro_tse=registro, portal=portal, url=url,
            dados_json=json.dumps(extra or {}, ensure_ascii=False),
        )


def extrair_e_gravar(
    conn: sqlite3.Connection,
    config: Dict[str, Any],
    portal: str,
    url: str,
    titulo: str,
    texto: str,
) -> Dict[str, int]:
    """Extrai os cenários da matéria e grava só os que passam em todas as verificações."""
    stats = {"cenarios_gravados": 0, "cenarios_quarentena": 0}
    institutos = config.get("coleta", {}).get("institutos", [])
    candidatos = set(config.get("modelo", {}).get("candidatos_monitorados", []))
    min_soma = config.get("validacao", {}).get("min_soma_percentual", 90.0)
    max_soma = config.get("validacao", {}).get("max_soma_percentual", 105.0)

    nomes_institutos = [t for i in institutos for t in i["texto"]]
    codigos_todos = extrair_codigos(texto)
    codigos_br = {c for c in codigos_todos if c.startswith("BR-")}
    if not codigos_br:
        return stats  # pesquisa presidencial sempre traz código BR; sem ele não há o que atribuir

    for cen in extrair_cenarios(texto, candidatos):
        def rejeitar(motivo: str, registro: Optional[str] = None, extra: Optional[dict] = None):
            stats["cenarios_quarentena"] += 1
            _quarentena(conn, f"Extração: {motivo}", registro, portal, url,
                        {"cenario": cen.nome, "resultados": cen.resultados, **(extra or {})})

        if cen.erro:
            rejeitar(cen.erro)
            continue

        soma = validar_soma_percentuais(list(cen.resultados.values()), min_soma, max_soma)
        if not soma.valido:
            rejeitar(soma.motivo or "soma inválida")
            continue

        ref = _amostras_e_codigo(cen.bloco, texto, codigos_br)
        if ref["codigo"] is None:
            rejeitar(f"não foi possível ligar o bloco a um único registro BR ({sorted(codigos_br)})")
            continue

        oficial = conn.execute(
            "SELECT * FROM registro_tse_oficial WHERE registro_tse = ?", (ref["codigo"],)
        ).fetchone()
        if oficial is None:
            rejeitar("registro inexistente na base oficial do TSE", ref["codigo"])
            continue

        if oficial["amostra"] not in ref["amostras"]:
            sugestao = _sugerir_registro_por_amostra(
                conn, ref["amostras"], oficial["empresa_nome"], oficial["data_divulgacao"]
            )
            rejeitar(
                f"amostra da matéria {sorted(ref['amostras']) or 'ausente'} difere do TSE ({oficial['amostra']})",
                ref["codigo"], {"registro_sugerido_pela_amostra": sugestao},
            )
            continue

        abrangencia = detectar_abrangencia(titulo, url, codigos_todos, cen.bloco, nomes_institutos)
        if abrangencia == "INDEFINIDA":
            rejeitar("abrangência (nacional/UF) ambígua", ref["codigo"])
            continue

        inst_nome = _nome_instituto(oficial["empresa_nome"], institutos)
        existente = conn.execute(
            "SELECT id, uf FROM pesquisa WHERE registro_tse = ?", (ref["codigo"],)
        ).fetchone()
        if existente and existente["uf"] != abrangencia:
            rejeitar(f"abrangência {abrangencia} contradiz a já gravada ({existente['uf']})", ref["codigo"])
            continue

        gravado = None
        if existente:
            cen_row = conn.execute(
                "SELECT id FROM cenario WHERE pesquisa_id = ? AND turno = ? AND cenario = ?",
                (existente["id"], cen.turno, cen.nome),
            ).fetchone()
            if cen_row:
                gravado = {
                    r["candidato"]: r["percentual"]
                    for r in conn.execute(
                        "SELECT candidato, percentual FROM resultado WHERE cenario_id = ?", (cen_row["id"],)
                    )
                }
        if gravado is not None and _conflita(gravado, cen.resultados):
            rejeitar("contradiz números já gravados por outra matéria", ref["codigo"], {"gravado": gravado})
            continue

        with conn:
            inst_id = salvar_instituto(conn, inst_nome)
            pesq_id = salvar_pesquisa(
                conn, inst_id, ref["codigo"], oficial["data_inicio"], oficial["data_fim"],
                oficial["amostra"], data_divulgacao=oficial["data_divulgacao"], uf=abrangencia,
                cargo="Presidente", metodologia=oficial["metodologia"],
            )
            cen_id = salvar_cenario(conn, pesq_id, cen.turno, cen.nome)
            for cand, pct in cen.resultados.items():
                salvar_resultado(conn, cen_id, cand, pct)
            salvar_fonte(conn, pesq_id, url, portal)
        stats["cenarios_gravados"] += 1

    return stats
