"""
Módulo de Normalização para Votos Válidos:
Calcula a proporção dos votos expurgando votos em branco, nulos e indecisos.
"""

from __future__ import annotations

from typing import List, Set
import pandas as pd


def identificar_categorias_nao_validas(
    candidatos_nao_validos: List[str]
) -> Set[str]:
    """
    Retorna um conjunto de strings normalizadas em minúsculas
    para identificar votos não válidos.
    """
    return {c.strip().lower() for c in candidatos_nao_validos}


def converter_para_votos_validos(
    df: pd.DataFrame,
    categorias_nao_validas: List[str]
) -> pd.DataFrame:
    """
    Renormaliza os percentuais de cada cenário para a base de 100% dos votos válidos:
        Voto_Valido_Candidato = (Percentual / Soma_Percentuais_Validos) * 100.0
    
    Cenários onde não há votos válidos permanecem inalterados.
    Linhas com categorias não válidas (brancos, nulos, indecisos) são removidas do resultado final.
    """
    if df.empty:
        return df.copy()

    nao_validos_set = identificar_categorias_nao_validas(categorias_nao_validas)
    
    df_copia = df.copy()
    df_copia["is_nao_valido"] = df_copia["candidato"].str.strip().str.lower().isin(nao_validos_set)
    
    # Agrupamos por cenário (ou pesquisa + turno + cenario)
    chave_agrupamento = "cenario_id" if "cenario_id" in df_copia.columns else ["pesquisa_id", "turno", "cenario"]
    
    # Calcula a soma dos votos válidos em cada cenário
    soma_validos = (
        df_copia[~df_copia["is_nao_valido"]]
        .groupby(chave_agrupamento)["percentual"]
        .transform("sum")
    )
    
    # Associa a soma calculada às linhas válidas
    df_copia.loc[~df_copia["is_nao_valido"], "soma_validos"] = soma_validos
    
    # Renormaliza para 100%
    linhas_validas = ~df_copia["is_nao_valido"] & (df_copia["soma_validos"] > 0)
    df_copia.loc[linhas_validas, "percentual"] = (
        df_copia.loc[linhas_validas, "percentual"] / df_copia.loc[linhas_validas, "soma_validos"]
    ) * 100.0
    df_copia["percentual"] = df_copia["percentual"].round(2)
    
    # Mantém apenas os candidatos válidos
    df_resultado = df_copia[~df_copia["is_nao_valido"]].drop(columns=["is_nao_valido", "soma_validos"], errors="ignore")
    return df_resultado.reset_index(drop=True)
