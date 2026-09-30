"""
Módulo de Importação de Pesquisas a partir de CSV.
Valida cada registro, grava em quarentena caso falhe, e insere no banco SQLite com suporte a múltiplos turnos e cenários.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from modelo.config import carregar_config
from modelo.database import (
    get_connection,
    init_db,
    registrar_quarentena,
    salvar_cenario,
    salvar_fonte,
    salvar_instituto,
    salvar_pesquisa,
    salvar_resultado,
)
from modelo.validador import (
    validar_amostra,
    validar_datas,
    validar_registro_tse,
    validar_soma_percentuais,
)


def importar_csv_pesquisas(
    caminho_csv: str | Path,
    caminho_config: str | Path = "config.yaml"
) -> Dict[str, int]:
    """
    Lê um arquivo CSV de pesquisas, agrupa por registro TSE e cenário,
    valida todas as regras de negócio e persiste no banco SQLite.
    Se inválido, grava na tabela de quarentena e no arquivo dados/quarentena.csv.
    """
    config = carregar_config(caminho_config)
    banco_path = config.get("caminhos", {}).get("banco_sqlite", "dados/pesquisas.db")
    quarentena_csv_path = Path(config.get("caminhos", {}).get("csv_quarentena", "dados/quarentena.csv"))
    
    # Assegura que o banco existe
    init_db(banco_path)
    conn = get_connection(banco_path)

    # Lê CSV ignorando linhas de comentário iniciadas por '#'
    df = pd.read_csv(caminho_csv, comment="#")
    
    total_linhas = len(df)
    pesquisas_inseridas = 0
    cenarios_inseridos = 0
    resultados_inseridos = 0
    itens_quarentena = 0
    
    quarentena_registros: List[Dict[str, Any]] = []

    # Agrupa por pesquisa e cenário para validar a soma dos percentuais
    grupos = df.groupby(["registro_tse", "turno", "cenario"])
    
    for (registro_tse, turno, cenario), group in grupos:
        primeira_linha = group.iloc[0]
        
        instituto_nome = str(primeira_linha["instituto"]).strip()
        uf = str(primeira_linha.get("uf", "BR")).strip().upper()
        cargo = str(primeira_linha.get("cargo", "Presidente")).strip()
        data_inicio = str(primeira_linha["data_inicio"]).strip()
        data_fim = str(primeira_linha["data_fim"]).strip()
        data_divulgacao = str(primeira_linha.get("data_divulgacao", "")).strip() or None
        amostra = primeira_linha["amostra"]
        margem_erro = float(primeira_linha["margem_erro"]) if pd.notnull(primeira_linha.get("margem_erro")) else None
        metodologia = str(primeira_linha.get("metodologia", "")).strip() or None
        impugnada = bool(int(primeira_linha.get("impugnada", 0)))
        fonte_portal = str(primeira_linha.get("fonte_portal", "desconhecido")).strip()
        fonte_url = str(primeira_linha.get("fonte_url", "")).strip()

        # Validações
        val_tse = validar_registro_tse(registro_tse)
        if not val_tse.valido:
            motivo = f"Registro TSE inválido: {val_tse.motivo}"
            registrar_quarentena(conn, motivo, registro_tse, fonte_portal, fonte_url)
            quarentena_registros.append({"registro_tse": registro_tse, "motivo": motivo, "portal": fonte_portal, "url": fonte_url})
            itens_quarentena += 1
            continue

        val_amostra = validar_amostra(amostra)
        if not val_amostra.valido:
            motivo = f"Amostra inválida: {val_amostra.motivo}"
            registrar_quarentena(conn, motivo, registro_tse, fonte_portal, fonte_url)
            quarentena_registros.append({"registro_tse": registro_tse, "motivo": motivo, "portal": fonte_portal, "url": fonte_url})
            itens_quarentena += 1
            continue

        val_datas = validar_datas(data_inicio, data_fim)
        if not val_datas.valido:
            motivo = f"Datas inconsistentes: {val_datas.motivo}"
            registrar_quarentena(conn, motivo, registro_tse, fonte_portal, fonte_url)
            quarentena_registros.append({"registro_tse": registro_tse, "motivo": motivo, "portal": fonte_portal, "url": fonte_url})
            itens_quarentena += 1
            continue

        percentuais = [float(p) for p in group["percentual"].tolist()]
        val_soma = validar_soma_percentuais(percentuais)
        if not val_soma.valido:
            motivo = f"Soma dos percentuais inválida: {val_soma.motivo}"
            registrar_quarentena(conn, motivo, registro_tse, fonte_portal, fonte_url)
            quarentena_registros.append({"registro_tse": registro_tse, "motivo": motivo, "portal": fonte_portal, "url": fonte_url})
            itens_quarentena += 1
            continue

        # Inserção no banco em transação atômica
        with conn:
            inst_id = salvar_instituto(conn, instituto_nome)
            pesq_id = salvar_pesquisa(
                conn=conn,
                instituto_id=inst_id,
                registro_tse=registro_tse,
                data_inicio=data_inicio,
                data_fim=data_fim,
                amostra=int(amostra),
                data_divulgacao=data_divulgacao,
                uf=uf,
                cargo=cargo,
                margem_erro=margem_erro,
                metodologia=metodologia,
                impugnada=impugnada
            )
            pesquisas_inseridas += 1

            if fonte_url:
                salvar_fonte(conn, pesq_id, fonte_url, fonte_portal)

            cen_id = salvar_cenario(
                conn=conn,
                pesquisa_id=pesq_id,
                turno=int(turno),
                cenario=cenario
            )
            cenarios_inseridos += 1

            for _, row in group.iterrows():
                candidato = str(row["candidato"]).strip()
                percentual = float(row["percentual"])
                salvar_resultado(conn, cen_id, candidato, percentual)
                resultados_inseridos += 1

    conn.close()

    # Grava quarentena em CSV caso haja registros rejeitados
    if quarentena_registros:
        quarentena_csv_path.parent.mkdir(parents=True, exist_ok=True)
        existe = quarentena_csv_path.exists()
        with open(quarentena_csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["registro_tse", "motivo", "portal", "url"])
            if not existe:
                writer.writeheader()
            writer.writerows(quarentena_registros)

    return {
        "total_linhas": total_linhas,
        "pesquisas_processadas": pesquisas_inseridas,
        "cenarios_processados": cenarios_inseridos,
        "resultados_processados": resultados_inseridos,
        "itens_quarentena": itens_quarentena,
    }
