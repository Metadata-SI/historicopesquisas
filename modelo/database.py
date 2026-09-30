"""
Módulo de Banco de Dados: Gerenciamento do SQLite / Conexões e Operações CRUD.
Desenvolvido com tipagem estática e suporte a transações seguras.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd


def get_connection(db_path: str | Path = "dados/pesquisas.db") -> sqlite3.Connection:
    """
    Retorna uma conexão configurada com o SQLite.
    Habilita suporte a chaves estrangeiras e acesso a linhas por nome de coluna.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db(
    db_path: str | Path = "dados/pesquisas.db",
    schema_path: str | Path = "dados/schema.sql"
) -> None:
    """
    Inicializa o banco de dados SQLite aplicando o arquivo de esquema DDL.
    """
    conn = get_connection(db_path)
    schema_path = Path(schema_path)
    
    if not schema_path.exists():
        raise FileNotFoundError(f"Arquivo de esquema SQL não encontrado em: {schema_path}")
        
    with open(schema_path, "r", encoding="utf-8") as f:
        schema_sql = f.read()
        
    with conn:
        conn.executescript(schema_sql)
    conn.close()


def salvar_instituto(
    conn: sqlite3.Connection,
    nome: str,
    peso: float = 1.0,
    vies_historico: float = 0.0
) -> int:
    """
    Insere ou atualiza um instituto na tabela 'instituto'.
    Retorna o ID do registro.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO instituto (nome, peso, vies_historico)
        VALUES (?, ?, ?)
        ON CONFLICT(nome) DO UPDATE SET
            peso = excluded.peso,
            vies_historico = excluded.vies_historico
        RETURNING id;
        """,
        (nome.strip(), peso, vies_historico)
    )
    row = cursor.fetchone()
    return int(row["id"])


def salvar_pesquisa(
    conn: sqlite3.Connection,
    instituto_id: int,
    registro_tse: str,
    data_inicio: str,
    data_fim: str,
    amostra: int,
    data_divulgacao: Optional[str] = None,
    uf: str = "BR",
    cargo: str = "Presidente",
    margem_erro: Optional[float] = None,
    metodologia: Optional[str] = None,
    impugnada: bool = False,
    observacoes: Optional[str] = None
) -> int:
    """
    Insere ou atualiza os metadados de uma pesquisa na tabela 'pesquisa'.
    Retorna o ID da pesquisa.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO pesquisa (
            instituto_id, registro_tse, uf, cargo, data_inicio, data_fim,
            data_divulgacao, amostra, margem_erro, metodologia, impugnada, observacoes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(registro_tse) DO UPDATE SET
            instituto_id = excluded.instituto_id,
            uf = excluded.uf,
            cargo = excluded.cargo,
            data_inicio = excluded.data_inicio,
            data_fim = excluded.data_fim,
            data_divulgacao = excluded.data_divulgacao,
            amostra = excluded.amostra,
            margem_erro = excluded.margem_erro,
            metodologia = excluded.metodologia,
            impugnada = excluded.impugnada,
            observacoes = excluded.observacoes
        RETURNING id;
        """,
        (
            instituto_id, registro_tse.strip(), uf.upper(), cargo,
            data_inicio, data_fim, data_divulgacao, amostra,
            margem_erro, metodologia, 1 if impugnada else 0, observacoes
        )
    )
    row = cursor.fetchone()
    return int(row["id"])


def salvar_cenario(
    conn: sqlite3.Connection,
    pesquisa_id: int,
    turno: int,
    cenario: str,
    descricao: Optional[str] = None
) -> int:
    """
    Insere ou atualiza um cenário vinculado a uma pesquisa.
    Retorna o ID do cenário.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO cenario (pesquisa_id, turno, cenario, descricao)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(pesquisa_id, turno, cenario) DO UPDATE SET
            descricao = excluded.descricao
        RETURNING id;
        """,
        (pesquisa_id, turno, cenario.strip(), descricao)
    )
    row = cursor.fetchone()
    return int(row["id"])


def salvar_resultado(
    conn: sqlite3.Connection,
    cenario_id: int,
    candidato: str,
    percentual: float
) -> int:
    """
    Insere ou atualiza o resultado percentual de um candidato em um cenário.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO resultado (cenario_id, candidato, percentual)
        VALUES (?, ?, ?)
        ON CONFLICT(cenario_id, candidato) DO UPDATE SET
            percentual = excluded.percentual
        RETURNING id;
        """,
        (cenario_id, candidato.strip(), float(percentual))
    )
    row = cursor.fetchone()
    return int(row["id"])


def salvar_fonte(
    conn: sqlite3.Connection,
    pesquisa_id: int,
    url: str,
    portal: str
) -> int:
    """
    Registra uma URL de origem associada à pesquisa.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO fonte (pesquisa_id, url, portal)
        VALUES (?, ?, ?)
        ON CONFLICT(pesquisa_id, url) DO UPDATE SET
            data_coleta = CURRENT_TIMESTAMP
        RETURNING id;
        """,
        (pesquisa_id, url.strip(), portal.strip().lower())
    )
    row = cursor.fetchone()
    return int(row["id"])


def registrar_quarentena(
    conn: sqlite3.Connection,
    motivo: str,
    registro_tse: Optional[str] = None,
    portal: Optional[str] = None,
    url: Optional[str] = None,
    dados_json: Optional[str] = None
) -> int:
    """
    Salva uma ocorrência de pesquisa na quarentena por falha na validação.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO quarentena (registro_tse, portal, url, motivo_rejeicao, dados_brutos_json)
        VALUES (?, ?, ?, ?, ?)
        RETURNING id;
        """,
        (registro_tse, portal, url, motivo, dados_json)
    )
    row = cursor.fetchone()
    return int(row["id"])


def carregar_pesquisas_completas(
    conn: sqlite3.Connection,
    cargo: str = "Presidente",
    uf: str = "BR",
    turno: Optional[int] = None,
    apenas_nao_impugnadas: bool = True
) -> pd.DataFrame:
    """
    Carrega os dados tabulares consolidados a partir da view vw_pesquisas_completas.
    Retorna um DataFrame pandas ideal para o pipeline estatístico.
    """
    query = """
        SELECT 
            resultado_id,
            pesquisa_id,
            cenario_id,
            instituto_id,
            instituto_nome,
            instituto_peso,
            instituto_vies,
            registro_tse,
            uf,
            cargo,
            data_inicio,
            data_fim,
            data_divulgacao,
            amostra,
            margem_erro,
            metodologia,
            impugnada,
            turno,
            cenario,
            candidato,
            percentual
        FROM vw_pesquisas_completas
        WHERE cargo = ? AND uf = ?
    """
    params: List[Any] = [cargo, uf]
    
    if apenas_nao_impugnadas:
        query += " AND impugnada = 0"
        
    if turno is not None:
        query += " AND turno = ?"
        params.append(turno)
        
    query += " ORDER BY data_fim ASC, pesquisa_id ASC, cenario_id ASC;"
    
    df = pd.read_sql_query(query, conn, params=params)
    if not df.empty:
        df["data_fim"] = pd.to_datetime(df["data_fim"])
        df["data_inicio"] = pd.to_datetime(df["data_inicio"])
        if "data_divulgacao" in df.columns:
            df["data_divulgacao"] = pd.to_datetime(df["data_divulgacao"])
    return df
