"""
Módulo de Importação e Ingestão de Pesquisas Reais do TSE no Banco SQLite.
Limpa registros de simulação e consolida os dados reais apurados na web.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from coleta.extrator_web import obter_pesquisas_reais
from modelo.config import carregar_config
from modelo.database import (
    get_connection,
    init_db,
    salvar_cenario,
    salvar_fonte,
    salvar_instituto,
    salvar_pesquisa,
    salvar_resultado,
)


def exportar_csv_reais(pesquisas: List[Dict[str, Any]], destino_csv: str | Path = "dados/pesquisas_reais_2026.csv") -> Path:
    """
    Exporta a relação de pesquisas reais para um arquivo CSV plano auditável.
    """
    destino = Path(destino_csv)
    destino.parent.mkdir(parents=True, exist_ok=True)

    linhas: List[Dict[str, Any]] = []
    for p in pesquisas:
        for c in p["cenarios"]:
            for cand, pct in c["resultados"].items():
                linhas.append({
                    "registro_tse": p["registro_tse"],
                    "instituto": p["instituto"],
                    "uf": p["uf"],
                    "cargo": p["cargo"],
                    "data_inicio": p["data_inicio"],
                    "data_fim": p["data_fim"],
                    "data_divulgacao": p["data_divulgacao"],
                    "amostra": p["amostra"],
                    "margem_erro": p["margem_erro"],
                    "metodologia": p["metodologia"],
                    "turno": c["turno"],
                    "cenario": c["cenario"],
                    "candidato": cand,
                    "percentual": pct,
                    "impugnada": 0,
                    "fonte_portal": p.get("portal", ""),
                    "fonte_url": p.get("url", ""),
                    "dado_real": "VERDADEIRO"
                })

    df = pd.DataFrame(linhas)
    df.to_csv(destino, index=False, encoding="utf-8")
    return destino


def importar_dados_reais(caminho_config: str | Path = "config.yaml", limpar_anteriores: bool = True) -> Dict[str, int]:
    """
    Obtém as pesquisas reais auditadas do TSE e persiste no SQLite.
    """
    config = carregar_config(caminho_config)
    banco_path = config.get("caminhos", {}).get("banco_sqlite", "dados/pesquisas.db")

    init_db(banco_path)
    conn = get_connection(banco_path)

    pesquisas = obter_pesquisas_reais()

    if limpar_anteriores:
        with conn:
            conn.execute("DELETE FROM resultado;")
            conn.execute("DELETE FROM cenario;")
            conn.execute("DELETE FROM fonte;")
            conn.execute("DELETE FROM pesquisa;")
            conn.execute("DELETE FROM quarentena;")

    total_pesquisas = 0
    total_cenarios = 0
    total_resultados = 0

    with conn:
        for item in pesquisas:
            inst_id = salvar_instituto(conn, item["instituto"])
            pesq_id = salvar_pesquisa(
                conn=conn,
                instituto_id=inst_id,
                registro_tse=item["registro_tse"],
                data_inicio=item["data_inicio"],
                data_fim=item["data_fim"],
                data_divulgacao=item.get("data_divulgacao"),
                amostra=item["amostra"],
                uf=item["uf"],
                cargo=item["cargo"],
                margem_erro=item.get("margem_erro"),
                metodologia=item.get("metodologia"),
                impugnada=False
            )
            total_pesquisas += 1

            if item.get("url"):
                salvar_fonte(conn, pesq_id, item["url"], item.get("portal", "web"))

            for cen in item["cenarios"]:
                cen_id = salvar_cenario(
                    conn=conn,
                    pesquisa_id=pesq_id,
                    turno=cen["turno"],
                    cenario=cen["cenario"]
                )
                total_cenarios += 1

                for cand, pct in cen["resultados"].items():
                    salvar_resultado(conn, cen_id, cand, float(pct))
                    total_resultados += 1

    conn.close()

    # Gera CSV auditável
    exportar_csv_reais(pesquisas)

    return {
        "pesquisas_inseridas": total_pesquisas,
        "cenarios_inseridos": total_cenarios,
        "resultados_inseridos": total_resultados
    }
