"""
Descoberta de matérias sobre pesquisas presidenciais e ligação com o registro oficial do TSE.

Fluxo:
  1. Lê o RSS de cada portal e separa matérias que falam de pesquisa ou de um instituto conhecido.
  2. Baixa o texto e procura códigos de registro (UF-NNNNN/AAAA).
  3. Confirma o código na base oficial. Sem código, aceita instituto + data apenas se
     houver um único registro candidato; qualquer dúvida vai para a quarentena.

Só o vínculo matéria <-> registro é gravado aqui. A extração dos percentuais é uma etapa à parte.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
import unicodedata
import urllib.robotparser
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

import requests
import trafilatura

from modelo.database import registrar_quarentena
from modelo.validador import normalizar_registro_tse

logger = logging.getLogger("coleta.descoberta")

REGEX_CODIGO = re.compile(r"\b([A-Z]{2})[\s-]?(\d{5})\s*/\s*(\d{4})\b")
REGEX_AMOSTRA = re.compile(
    r"(\d{1,3}(?:\.\d{3})+|\d{3,5})\s+(?:pessoas|eleitores|entrevistad[oa]s|entrevistas)", re.IGNORECASE
)
REGEX_TITULO = re.compile(r"pesquisa|levantamento|sondagem", re.IGNORECASE)
REGEX_PRESIDENTE = re.compile(r"presidente|presidencial|planalto", re.IGNORECASE)


@dataclass
class ItemFeed:
    titulo: str
    url: str
    publicado: Optional[date]
    titulo_provisorio: bool = False  # vindo do slug da URL; o título real sai da página


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    ).lower()


def ler_feed(url: str, user_agent: str, timeout: int = 30) -> List[ItemFeed]:
    """Lê um feed RSS e devolve título, link e data de publicação de cada item."""
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()
    itens: List[ItemFeed] = []
    for item in ET.fromstring(resp.content).iter("item"):
        titulo, link = item.findtext("title"), item.findtext("link")
        if not titulo or not link:
            continue
        publicado: Optional[date] = None
        bruto = item.findtext("pubDate")
        if bruto:
            try:
                publicado = parsedate_to_datetime(bruto).date()
            except (TypeError, ValueError):
                pass
        itens.append(ItemFeed(titulo.strip(), link.strip(), publicado))
    return itens


def extrair_codigos(texto: str) -> Set[str]:
    """Todos os códigos de registro citados no texto, na forma canônica UF-NNNNN/AAAA."""
    codigos: Set[str] = set()
    for uf, num, ano in REGEX_CODIGO.findall(texto or ""):
        canonico = normalizar_registro_tse(f"{uf}{num}{ano}")
        if canonico:
            codigos.add(canonico)
    return codigos


def extrair_amostras(texto: str) -> Set[int]:
    """Tamanhos de amostra citados no texto (ex.: '2.004 pessoas')."""
    return {int(m.replace(".", "")) for m in REGEX_AMOSTRA.findall(texto or "")}


def detectar_institutos(texto: str, institutos: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Institutos configurados que aparecem no texto (sem diferenciar acento ou caixa)."""
    base = _sem_acento(texto or "")
    achados = []
    for inst in institutos:
        for termo in inst["texto"]:
            if re.search(rf"\b{re.escape(_sem_acento(termo))}\b", base):
                achados.append(inst)
                break
    return achados


def _candidatos_por_instituto(
    conn: sqlite3.Connection,
    instituto: Dict[str, Any],
    publicado: date,
    janela_dias: int,
) -> List[str]:
    """Registros nacionais do instituto divulgados perto da data de publicação."""
    inicio = (publicado - timedelta(days=janela_dias)).isoformat()
    fim = (publicado + timedelta(days=1)).isoformat()
    filtro = " OR ".join("UPPER(empresa_nome) LIKE ?" for _ in instituto["tse"])
    params = [f"%{t.upper()}%" for t in instituto["tse"]] + [inicio, fim]
    linhas = conn.execute(
        f"""
        SELECT registro_tse FROM registro_tse_oficial
        WHERE ({filtro}) AND data_divulgacao BETWEEN ? AND ?
        ORDER BY registro_tse;
        """,
        params,
    ).fetchall()
    return [r["registro_tse"] for r in linhas]


def casar_materia(
    conn: sqlite3.Connection,
    texto: str,
    publicado: Optional[date],
    institutos: List[Dict[str, Any]],
    janela_dias: int = 3,
) -> Dict[str, Any]:
    """
    Decide a qual registro oficial a matéria se refere.
    Retorna {"registros": [...], "metodo": str | None, "motivo": str | None}.
    Quando `registros` está vazio, `motivo` explica o descarte.
    """
    codigos_br = {c for c in extrair_codigos(texto) if c.startswith("BR-")}

    if codigos_br:
        marcadores = ",".join("?" for _ in codigos_br)
        oficiais = {
            r["registro_tse"]: r["amostra"]
            for r in conn.execute(
                f"SELECT registro_tse, amostra FROM registro_tse_oficial WHERE registro_tse IN ({marcadores})",
                sorted(codigos_br),
            )
        }
        # Matérias às vezes citam o código de outra pesquisa: se a matéria informa a amostra,
        # ela precisa bater com a do TSE para o vínculo valer.
        amostras = extrair_amostras(texto)
        if amostras:
            divergentes = sorted(c for c, a in oficiais.items() if a not in amostras)
            oficiais = {c: a for c, a in oficiais.items() if a in amostras}
            if not oficiais and divergentes:
                return {
                    "registros": [], "metodo": None,
                    "motivo": f"Amostra(s) da matéria {sorted(amostras)} não batem com a do TSE para {divergentes}",
                }
        if oficiais:
            return {"registros": sorted(oficiais), "metodo": "codigo", "motivo": None}
        return {
            "registros": [], "metodo": None,
            "motivo": f"Código(s) {sorted(codigos_br)} não constam na base oficial do TSE (Presidente/BR)",
        }

    if not REGEX_PRESIDENTE.search(texto or ""):
        return {"registros": [], "metodo": None, "motivo": "Sem código BR e sem menção a presidente"}
    if publicado is None:
        return {"registros": [], "metodo": None, "motivo": "Sem código BR e sem data de publicação"}

    detectados = detectar_institutos(texto, institutos)
    if len(detectados) != 1:
        return {
            "registros": [], "metodo": None,
            "motivo": f"Sem código BR; {len(detectados)} institutos detectados (esperado 1)",
        }

    candidatos = _candidatos_por_instituto(conn, detectados[0], publicado, janela_dias)
    if len(candidatos) == 1:
        return {"registros": candidatos, "metodo": "instituto+data", "motivo": None}
    return {
        "registros": [], "metodo": None,
        "motivo": f"Sem código BR; {len(candidatos)} registros de {detectados[0]['nome']} na janela (esperado 1)",
    }


def _permitido_por_robots(url: str, user_agent: str, cache: Dict[str, Any]) -> bool:
    host = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    if host not in cache:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(f"{host}/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None  # sem robots.txt legível: segue o padrão de permitir
        cache[host] = rp
    rp = cache[host]
    return True if rp is None else rp.can_fetch(user_agent, url)


def baixar_pagina(url: str, user_agent: str, timeout: int = 30) -> Optional[Tuple[str, str]]:
    """Baixa a página e devolve (título, texto da matéria), ou None se falhar."""
    try:
        resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
        resp.raise_for_status()
        texto = trafilatura.extract(resp.content)
        if not texto:
            return None
        meta = trafilatura.extract_metadata(resp.content)
        return (meta.title if meta and meta.title else ""), texto
    except Exception as e:
        logger.warning(f"Falha ao baixar {url}: {e}")
        return None


def baixar_texto(url: str, user_agent: str, timeout: int = 30) -> Optional[str]:
    """Só o texto da matéria (compatibilidade)."""
    pagina = baixar_pagina(url, user_agent, timeout)
    return pagina[1] if pagina else None


def _salvar_materia(
    conn: sqlite3.Connection, registro: str, item: ItemFeed, portal: str, metodo: str
) -> None:
    conn.execute(
        """
        INSERT INTO materia_pesquisa (registro_tse, url, portal, titulo, data_publicacao, metodo_match)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(registro_tse, url) DO UPDATE SET metodo_match = excluded.metodo_match;
        """,
        (registro, item.url, portal, item.titulo, item.publicado.isoformat() if item.publicado else None, metodo),
    )


def _urls_processadas(conn: sqlite3.Connection) -> set:
    return {r[0] for r in conn.execute("SELECT url FROM url_processada")}


def _marcar_processada(conn: sqlite3.Connection, url: str, portal: str) -> None:
    with conn:
        conn.execute("INSERT OR IGNORE INTO url_processada (url, portal) VALUES (?, ?)", (url, portal))


def coletar_materias(
    conn: sqlite3.Connection,
    config: Dict[str, Any],
    ler_feed_fn: Callable[[str, str], List[ItemFeed]] = ler_feed,
    baixar_fn: Callable[[str, str], Any] = baixar_pagina,
    pausa: Callable[[float], None] = time.sleep,
    descobrir_urls_fn: Optional[Callable[..., List[ItemFeed]]] = None,
    reprocessar: bool = False,
    historico: bool = True,
) -> Dict[str, int]:
    """
    Descobre matérias (RSS para o que é recente, sitemaps diários para o histórico), baixa cada
    uma só uma vez e grava o vínculo matéria <-> registro TSE e os percentuais.
    O progresso é salvo a cada URL: dá para interromper (Ctrl+C) e retomar sem perder nada.
    As funções de rede são injetáveis para permitir testes sem internet.
    """
    from coleta.extrator_resultados import extrair_e_gravar  # import tardio: evita ciclo
    if descobrir_urls_fn is None:
        from coleta.sitemaps import descobrir_urls as descobrir_urls_fn

    cfg = config.get("coleta", {})
    ua = cfg.get("user_agent", "AgregadorEleitoral2026/1.0")
    intervalo = float(cfg.get("intervalo_minimo_segundos", 2.0))
    janela = int(cfg.get("janela_dias_match", 3))
    institutos = cfg.get("institutos", [])
    termos_inst = [_sem_acento(t) for i in institutos for t in i["texto"]]
    ja_feitas = set() if reprocessar else _urls_processadas(conn)

    stats = {
        "cenarios_gravados": 0, "cenarios_quarentena": 0, "vistas": 0, "candidatas": 0,
        "vinculadas": 0, "quarentena": 0, "bloqueadas_robots": 0, "ja_processadas": 0,
    }
    cache_robots: Dict[str, Any] = {}

    # Fila: (portal, item). RSS primeiro (mais recente), depois o histórico dos sitemaps.
    fila: List[Tuple[str, ItemFeed]] = []
    for portal, url_feed in cfg.get("feeds", {}).items():
        try:
            fila += [(portal, i) for i in ler_feed_fn(url_feed, ua)]
        except Exception as e:
            logger.error(f"Feed do portal '{portal}' indisponível: {e}")

    if historico:
        desde = date.fromisoformat(str(cfg.get("historico_desde", "2026-01-01")))
        for portal, cfg_portal in cfg.get("sitemaps", {}).items():
            try:
                fila += [(portal, i) for i in descobrir_urls_fn(
                    portal, cfg_portal, institutos, desde, None, ua, ja_feitas
                )]
            except Exception as e:
                logger.error(f"Sitemaps do portal '{portal}' indisponíveis: {e}")

    # Sem repetir a mesma URL vinda do RSS e do sitemap
    vistas_urls: set = set()
    fila = [(p, i) for p, i in fila if not (i.url in vistas_urls or vistas_urls.add(i.url))]  # type: ignore[func-returns-value]
    logger.info(f"Fila de análise: {len(fila)} matérias")

    for n, (portal, item) in enumerate(fila, 1):
        stats["vistas"] += 1
        if item.url in ja_feitas:
            stats["ja_processadas"] += 1
            continue
        if not item.titulo_provisorio:
            titulo_base = _sem_acento(item.titulo)
            if not (REGEX_TITULO.search(item.titulo) or any(t in titulo_base for t in termos_inst)):
                _marcar_processada(conn, item.url, portal)
                continue
        stats["candidatas"] += 1

        if not _permitido_por_robots(item.url, ua, cache_robots):
            stats["bloqueadas_robots"] += 1
            continue

        pausa(intervalo)
        pagina = baixar_fn(item.url, ua)
        if isinstance(pagina, str):  # função de download só de texto (testes)
            pagina = (item.titulo, pagina)
        if not pagina:
            continue  # falha de rede: não marca, tenta de novo na próxima execução
        titulo, texto = pagina
        if item.titulo_provisorio and titulo:
            item.titulo = titulo

        res = casar_materia(conn, f"{item.titulo}\n{texto}", item.publicado, institutos, janela)
        if res["registros"]:
            with conn:
                for reg in res["registros"]:
                    _salvar_materia(conn, reg, item, portal, res["metodo"])
            stats["vinculadas"] += 1
        elif REGEX_PRESIDENTE.search(texto):
            # Só vai para revisão quando fala de presidente; pesquisa de governador etc. é ruído.
            with conn:
                registrar_quarentena(
                    conn, res["motivo"], portal=portal, url=item.url,
                    dados_json=json.dumps({"titulo": item.titulo}, ensure_ascii=False),
                )
            stats["quarentena"] += 1

        # Extração dos percentuais roda mesmo sem vínculo: ela faz a própria verificação
        # por bloco e quarentena o que não fecha.
        ext = extrair_e_gravar(conn, config, portal, item.url, item.titulo, texto)
        stats["cenarios_gravados"] += ext["cenarios_gravados"]
        stats["cenarios_quarentena"] += ext["cenarios_quarentena"]
        _marcar_processada(conn, item.url, portal)

        if stats["candidatas"] % 25 == 0:
            logger.info(
                f"  progresso: {n}/{len(fila)} | {stats['vinculadas']} vinculadas, "
                f"{stats['cenarios_gravados']} cenários gravados"
            )

    logger.info(f"Coleta de matérias: {stats}")
    return stats
