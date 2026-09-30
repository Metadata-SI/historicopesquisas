"""
Carga dos registros oficiais de pesquisas eleitorais a partir dos dados abertos do TSE.

O TSE publica um zip por ano com os metadados de cada pesquisa registrada
(empresa, datas, amostra, metodologia). Os percentuais por candidato NÃO fazem
parte desses dados: eles vêm das matérias. Esta base serve como lista de
referência para validar que uma pesquisa noticiada realmente existe.
"""

from __future__ import annotations

import io
import logging
import sqlite3
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from modelo.validador import normalizar_registro_tse

logger = logging.getLogger("coleta.tse_oficial")

URL_ZIP_TSE = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/pesquisa_eleitoral/"
    "pesquisa_eleitoral_{ano}.zip"
)
CSV_NACIONAL = "pesquisa_eleitoral_{ano}_BRASIL.csv"
ENCODING_CSV = "latin1"
SEPARADOR_CSV = ";"


def baixar_zip_tse(
    ano: int,
    destino: str | Path = "dados/tse",
    timeout: int = 120,
    user_agent: str = "AgregadorEleitoral2026/1.0",
) -> Path:
    """Baixa o zip de registros do TSE para `destino` e retorna o caminho do arquivo."""
    destino_dir = Path(destino)
    destino_dir.mkdir(parents=True, exist_ok=True)
    arquivo = destino_dir / f"pesquisa_eleitoral_{ano}.zip"

    resp = requests.get(
        URL_ZIP_TSE.format(ano=ano),
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    resp.raise_for_status()
    if not zipfile.is_zipfile(io.BytesIO(resp.content)):
        raise ValueError(f"Resposta do TSE para {ano} não é um zip válido")

    arquivo.write_bytes(resp.content)
    logger.info(f"Zip do TSE salvo em {arquivo} ({len(resp.content) / 1e6:.1f} MB)")
    return arquivo


def _nome_empresa(fantasia: Any, razao: Any) -> Optional[str]:
    """O TSE usa '#NULO#' quando não há nome fantasia; nesse caso vale a razão social."""
    for valor in (fantasia, razao):
        if isinstance(valor, str) and valor.strip() and valor.strip() != "#NULO#":
            return valor.strip()
    return None


def _para_data(valor: Any) -> Optional[str]:
    if not isinstance(valor, str) or not valor.strip():
        return None
    return valor.strip()[:10]


def _para_float(valor: Any) -> Optional[float]:
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return float(valor.strip().replace(".", "").replace(",", "."))
    except ValueError:
        return None


def _para_int(valor: Any) -> Optional[int]:
    if not isinstance(valor, str) or not valor.strip():
        return None
    try:
        return int(valor.strip())
    except ValueError:
        return None


def ler_registros_zip(
    caminho_zip: str | Path,
    ano: int,
    cargo: str = "Presidente",
    uf: str = "BR",
) -> List[Dict[str, Any]]:
    """
    Lê o CSV nacional do zip e devolve os registros do cargo/UF pedidos,
    com o código normalizado (UF-NNNNN/AAAA). Linhas com protocolo ilegível são descartadas.
    """
    nome_csv = CSV_NACIONAL.format(ano=ano)
    with zipfile.ZipFile(caminho_zip) as z:
        if nome_csv not in z.namelist():
            raise FileNotFoundError(f"{nome_csv} não encontrado em {caminho_zip}")
        with z.open(nome_csv) as f:
            df = pd.read_csv(f, sep=SEPARADOR_CSV, encoding=ENCODING_CSV, dtype=str)

    df = df[(df["DS_CARGO"] == cargo) & (df["SG_UF"] == uf)]

    registros: List[Dict[str, Any]] = []
    descartados = 0
    for linha in df.to_dict("records"):
        canonico = normalizar_registro_tse(linha.get("NR_PROTOCOLO_REGISTRO", ""))
        if canonico is None:
            descartados += 1
            continue
        registros.append({
            "registro_tse": canonico,
            "protocolo_original": linha["NR_PROTOCOLO_REGISTRO"],
            "uf": linha["SG_UF"],
            "cargo": linha["DS_CARGO"],
            "empresa_cnpj": linha.get("NR_CNPJ_EMPRESA"),
            "empresa_nome": _nome_empresa(linha.get("NM_EMPRESA_FANTASIA"), linha.get("NM_EMPRESA")),
            "data_registro": linha.get("DT_REGISTRO"),
            "data_inicio": _para_data(linha.get("DT_INICIO_PESQUISA")),
            "data_fim": _para_data(linha.get("DT_FIM_PESQUISA")),
            "data_divulgacao": _para_data(linha.get("DT_DIVULGACAO")),
            "amostra": _para_int(linha.get("QT_ENTREVISTADO")),
            "valor": _para_float(linha.get("VR_PESQUISA")),
            "metodologia": linha.get("DS_METODOLOGIA_PESQUISA"),
            "plano_amostral": linha.get("DS_PLANO_AMOSTRAL"),
            "pesquisa_propria": linha.get("ST_PESQUISA_PROPRIA") == "S",
        })

    if descartados:
        logger.warning(f"{descartados} linhas do TSE descartadas por protocolo ilegível")
    return registros


def salvar_registros_oficiais(conn: sqlite3.Connection, registros: List[Dict[str, Any]]) -> int:
    """Insere ou atualiza os registros oficiais. Retorna a quantidade processada."""
    with conn:
        conn.executemany(
            """
            INSERT INTO registro_tse_oficial (
                registro_tse, protocolo_original, uf, cargo, empresa_cnpj, empresa_nome,
                data_registro, data_inicio, data_fim, data_divulgacao, amostra, valor,
                metodologia, plano_amostral, pesquisa_propria, atualizado_em
            )
            VALUES (
                :registro_tse, :protocolo_original, :uf, :cargo, :empresa_cnpj, :empresa_nome,
                :data_registro, :data_inicio, :data_fim, :data_divulgacao, :amostra, :valor,
                :metodologia, :plano_amostral, :pesquisa_propria, CURRENT_TIMESTAMP
            )
            ON CONFLICT(registro_tse) DO UPDATE SET
                protocolo_original = excluded.protocolo_original,
                uf = excluded.uf,
                cargo = excluded.cargo,
                empresa_cnpj = excluded.empresa_cnpj,
                empresa_nome = excluded.empresa_nome,
                data_registro = excluded.data_registro,
                data_inicio = excluded.data_inicio,
                data_fim = excluded.data_fim,
                data_divulgacao = excluded.data_divulgacao,
                amostra = excluded.amostra,
                valor = excluded.valor,
                metodologia = excluded.metodologia,
                plano_amostral = excluded.plano_amostral,
                pesquisa_propria = excluded.pesquisa_propria,
                atualizado_em = CURRENT_TIMESTAMP;
            """,
            registros,
        )
    return len(registros)


def atualizar_base_tse(
    conn: sqlite3.Connection,
    ano: int,
    cargo: str = "Presidente",
    uf: str = "BR",
    destino: str | Path = "dados/tse",
) -> int:
    """Baixa o zip do TSE, lê os registros do cargo/UF e grava no banco."""
    caminho = baixar_zip_tse(ano, destino)
    registros = ler_registros_zip(caminho, ano, cargo, uf)
    total = salvar_registros_oficiais(conn, registros)
    logger.info(f"{total} registros oficiais de {cargo}/{uf} ({ano}) gravados")
    return total


def conferir_pesquisas_com_tse(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """
    Compara cada pesquisa da tabela `pesquisa` com o registro oficial.
    Retorna uma lista de problemas: registro inexistente no TSE ou campos divergentes
    (amostra, data_inicio, data_fim).
    """
    linhas = conn.execute(
        """
        SELECT p.registro_tse, p.amostra, p.data_inicio, p.data_fim,
               o.registro_tse AS oficial,
               o.amostra AS amostra_tse, o.data_inicio AS inicio_tse, o.data_fim AS fim_tse
        FROM pesquisa p
        LEFT JOIN registro_tse_oficial o ON o.registro_tse = p.registro_tse
        ORDER BY p.registro_tse;
        """
    ).fetchall()

    problemas: List[Dict[str, Any]] = []
    for r in linhas:
        if r["oficial"] is None:
            problemas.append({"registro_tse": r["registro_tse"], "problema": "inexistente no TSE"})
            continue
        for campo, local, tse in (
            ("amostra", r["amostra"], r["amostra_tse"]),
            ("data_inicio", r["data_inicio"], r["inicio_tse"]),
            ("data_fim", r["data_fim"], r["fim_tse"]),
        ):
            if str(local) != str(tse):
                problemas.append({
                    "registro_tse": r["registro_tse"],
                    "problema": f"{campo} diverge",
                    "local": local,
                    "tse": tse,
                })
    return problemas
