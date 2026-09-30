"""
Módulo de Bootstrap Não-Paramétrico:
Estimação de intervalos de confiança (2,5% e 97,5%) para a média ponderada
sem pressupor normalidade ou distribuição a priori dos erros.
"""

from __future__ import annotations

from typing import Optional, Tuple
import numpy as np


def calcular_intervalo_bootstrap(
    valores: np.ndarray,
    pesos: np.ndarray,
    amostras: Optional[np.ndarray] = None,
    margens_erro: Optional[np.ndarray] = None,
    n_bootstraps: int = 2000,
    percentis: Tuple[float, float] = (2.5, 97.5),
    seed: Optional[int] = 42
) -> Tuple[float, float, float]:
    """
    Executa o bootstrap não-paramétrico com reamostragem das pesquisas e
    incorporação da incerteza amostral de cada levantamento.
    
    Retorna:
        (media_estimada, limite_inferior, limite_superior)
    """
    valores = np.asarray(valores, dtype=float)
    pesos = np.asarray(pesos, dtype=float)
    
    n_pontos = len(valores)
    if n_pontos == 0:
        return 0.0, 0.0, 0.0
        
    soma_pesos = np.sum(pesos)
    if soma_pesos <= 0:
        return float(np.mean(valores)), float(np.min(valores)), float(np.max(valores))
        
    # Média ponderada analítica de referência
    pesos_norm = pesos / soma_pesos
    media_ponderada = float(np.sum(valores * pesos_norm))
    
    rng = np.random.default_rng(seed)
    
    # Erro padrão amostral de cada pesquisa (SE = ME / 1.96 ou sqrt(p*(1-p)/N))
    erros_padrao = np.zeros(n_pontos, dtype=float)
    if margens_erro is not None:
        me_arr = np.asarray(margens_erro, dtype=float)
        erros_padrao = np.where(me_arr > 0, me_arr / 1.96, erros_padrao)
    elif amostras is not None:
        n_arr = np.asarray(amostras, dtype=float)
        # p em proporção [0, 1]
        p_prop = np.clip(valores / 100.0, 0.01, 0.99)
        erros_padrao = np.where(n_arr > 0, 100.0 * np.sqrt(p_prop * (1.0 - p_prop) / n_arr), 1.5)
    else:
        # Padrão conservador se nem ME nem amostra forem informados
        erros_padrao = np.full(n_pontos, 1.5)

    # Caso tenhamos apenas 1 pesquisa isolada
    if n_pontos == 1:
        se = erros_padrao[0]
        # Simula perturbações da própria pesquisa
        simulacoes = valores[0] + rng.normal(0, se, size=n_bootstraps)
        simulacoes = np.clip(simulacoes, 0.0, 100.0)
        ic_inf = float(np.percentile(simulacoes, percentis[0]))
        ic_sup = float(np.percentile(simulacoes, percentis[1]))
        return round(media_ponderada, 2), round(ic_inf, 2), round(ic_sup, 2)

    # Para N >= 2: Reamostragem com reposição (matriz de índices n_bootstraps x n_pontos)
    # Amostramos pesquisas proporcionalmente à sua relevância
    indices_bootstrap = rng.choice(n_pontos, size=(n_bootstraps, n_pontos), replace=True, p=pesos_norm)
    
    valores_amostrados = valores[indices_bootstrap]
    pesos_amostrados = pesos[indices_bootstrap]
    erros_amostrados = erros_padrao[indices_bootstrap]
    
    # Perturbação de amostragem finita para cada ponto sorteado
    ruido = rng.normal(0, 1.0, size=(n_bootstraps, n_pontos)) * erros_amostrados
    valores_perturbados = np.clip(valores_amostrados + ruido, 0.0, 100.0)
    
    # Médias ponderadas de cada uma das 2.000 iterações
    soma_pesos_boot = np.sum(pesos_amostrados, axis=1, keepdims=True)
    medias_bootstrap = np.sum(valores_perturbados * pesos_amostrados, axis=1, keepdims=True) / soma_pesos_boot
    medias_bootstrap = medias_bootstrap.flatten()
    
    ic_inf = float(np.percentile(medias_bootstrap, percentis[0]))
    ic_sup = float(np.percentile(medias_bootstrap, percentis[1]))
    
    # Assegura coerência matemática
    ic_inf = max(0.0, ic_inf)
    ic_sup = min(100.0, ic_sup)
    if ic_inf > media_ponderada:
        ic_inf = media_ponderada
    if ic_sup < media_ponderada:
        ic_sup = media_ponderada
        
    return round(media_ponderada, 2), round(ic_inf, 2), round(ic_sup, 2)
