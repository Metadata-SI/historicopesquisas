"""
Módulo de Cálculo de Pesos: Temporal, Tamanho de Amostra e Ponderação Geral.
"""

from __future__ import annotations

import math
from typing import Union
import numpy as np
import pandas as pd


def calcular_peso_temporal(dias_decorridos: Union[float, int, np.ndarray], meia_vida_dias: float = 14.0) -> Union[float, np.ndarray]:
    """
    Calcula o peso exponencial baseado na distância em dias da data de fim de campo:
        w = exp(-ln(2) * delta_t / meia_vida) = 2^(-delta_t / meia_vida)
    Para pesquisas no futuro em relação à data de corte (delta_t < 0), o peso é 0.0.
    """
    if meia_vida_dias <= 0:
        raise ValueError("meia_vida_dias deve ser estritamente positiva.")
        
    decay_constant = np.log(2.0) / meia_vida_dias
    
    if isinstance(dias_decorridos, (int, float)):
        if dias_decorridos < 0:
            return 0.0
        return float(np.exp(-decay_constant * dias_decorridos))
    
    # Suporte a arrays NumPy ou Series Pandas
    arr = np.asarray(dias_decorridos, dtype=float)
    pesos = np.where(arr < 0, 0.0, np.exp(-decay_constant * arr))
    return pesos


def calcular_peso_amostra(amostra: Union[int, float, np.ndarray]) -> Union[float, np.ndarray]:
    """
    Calcula o peso proporcional à raiz quadrada do tamanho da amostra (sqrt(N)).
    Garante que pesquisas maiores tenham peso maior, com retornos marginais decrescentes.
    """
    if isinstance(amostra, (int, float)):
        if amostra <= 0:
            return 0.0
        return float(np.sqrt(amostra))
        
    arr = np.asarray(amostra, dtype=float)
    return np.where(arr <= 0, 0.0, np.sqrt(arr))


def calcular_pesos_compostos(
    df: pd.DataFrame,
    data_referencia: pd.Timestamp,
    meia_vida_dias: float = 14.0,
    peso_amostra_habilitado: bool = True
) -> pd.Series:
    """
    Calcula o peso final composto de cada linha de pesquisa com base na data de referência:
        W = W_temporal * W_amostra * W_instituto
    """
    if df.empty:
        return pd.Series(dtype=float)
        
    data_fim = pd.to_datetime(df["data_fim"])
    dias_diff = (data_referencia - data_fim).dt.total_seconds() / 86400.0
    
    pesos_temporais = calcular_peso_temporal(dias_diff.values, meia_vida_dias=meia_vida_dias)
    
    if peso_amostra_habilitado and "amostra" in df.columns:
        pesos_amostrais = calcular_peso_amostra(df["amostra"].values)
    else:
        pesos_amostrais = np.ones(len(df), dtype=float)
        
    if "instituto_peso" in df.columns:
        pesos_instituto = df["instituto_peso"].fillna(1.0).values
    else:
        pesos_instituto = np.ones(len(df), dtype=float)
        
    pesos_finais = pesos_temporais * pesos_amostrais * pesos_instituto
    return pd.Series(pesos_finais, index=df.index, dtype=float)
