"""
Módulo de Efeitos de Instituto (House Effects):
Estima o viés sistemático de cada instituto em relação à média dos demais
em janelas temporais contemporâneas, e ajusta os percentuais brutos.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def calcular_house_effects(
    df: pd.DataFrame,
    min_pesquisas: int = 5,
    janela_dias: int = 21,
    candidatos_relevantes: Optional[List[str]] = None
) -> Dict[str, Dict[str, float]]:
    """
    Calcula o viés sistemático (House Effect) por instituto e por candidato.
    
    Para cada pesquisa de um instituto X com fim em data D:
    1. Localiza pesquisas de outros institutos concluídas em [D - janela_dias, D + janela_dias].
    2. Calcula a média dos outros institutos para o candidato C.
    3. Mede o diferencial (Pesquisa_X - Média_Outros).
    4. O viés médio do instituto X é a média desses diferenciais.
    
    Institutos com menos de 'min_pesquisas' recebem viés neutro (0.0).
    """
    if df.empty or "instituto_nome" not in df.columns or "candidato" not in df.columns:
        return {}

    dados = df.copy()
    dados["data_fim"] = pd.to_datetime(dados["data_fim"])
    
    # Contagem de pesquisas distintas por instituto
    contagem_pesquisas = dados.groupby("instituto_nome")["pesquisa_id"].nunique()
    institutos_elegiveis = contagem_pesquisas[contagem_pesquisas >= min_pesquisas].index.tolist()
    
    todos_institutos = dados["instituto_nome"].unique().tolist()
    candidatos = candidatos_relevantes or dados["candidato"].unique().tolist()
    
    house_effects: Dict[str, Dict[str, float]] = {}
    
    for inst in todos_institutos:
        house_effects[inst] = {}
        if inst not in institutos_elegiveis:
            # Sem dados suficientes: viés neutro (0.0)
            for cand in candidatos:
                house_effects[inst][cand] = 0.0
            continue
            
        pesquisas_inst = dados[dados["instituto_nome"] == inst]
        outras_pesquisas = dados[dados["instituto_nome"] != inst]
        
        for cand in candidatos:
            diferenciais: List[float] = []
            cand_inst = pesquisas_inst[pesquisas_inst["candidato"] == cand]
            cand_outros = outras_pesquisas[outras_pesquisas["candidato"] == cand]
            
            for _, row in cand_inst.iterrows():
                dt = row["data_fim"]
                val = row["percentual"]
                
                # Janela contemporânea de outros institutos
                mascara_janela = (
                    (cand_outros["data_fim"] >= dt - pd.Timedelta(days=janela_dias)) &
                    (cand_outros["data_fim"] <= dt + pd.Timedelta(days=janela_dias))
                )
                colegas_janela = cand_outros[mascara_janela]
                
                if not colegas_janela.empty:
                    media_outros = colegas_janela["percentual"].mean()
                    diff = val - media_outros
                    diferenciais.append(diff)
                    
            if diferenciais:
                vies_medio = float(np.mean(diferenciais))
                # Limite de viés razoável para evitar distorções espúrias (ex: [-5.0%, +5.0%])
                vies_medio = float(np.clip(vies_medio, -5.0, 5.0))
                house_effects[inst][cand] = round(vies_medio, 3)
            else:
                house_effects[inst][cand] = 0.0
                
    return house_effects


def aplicar_ajuste_house_effects(
    df: pd.DataFrame,
    house_effects: Dict[str, Dict[str, float]]
) -> pd.DataFrame:
    """
    Retorna uma cópia do DataFrame com a coluna 'percentual_ajustado'
    subtraindo o viés estimado do instituto:
        percentual_ajustado = percentual - viés
    Garante que o percentual não fique negativo.
    """
    df_ajustado = df.copy()
    if not house_effects or df.empty:
        df_ajustado["percentual_ajustado"] = df_ajustado["percentual"]
        return df_ajustado

    def ajustar_linha(row):
        inst = row.get("instituto_nome")
        cand = row.get("candidato")
        val = row.get("percentual", 0.0)
        
        vies = house_effects.get(inst, {}).get(cand, 0.0)
        ajustado = max(0.0, val - vies)
        return ajustado

    df_ajustado["percentual_ajustado"] = df_ajustado.apply(ajustar_linha, axis=1)
    return df_ajustado


def gerar_relatorio_institutos(
    df: pd.DataFrame,
    house_effects: Dict[str, Dict[str, float]],
    min_pesquisas: int = 5
) -> Dict[str, Any]:
    """
    Estrutura os dados para exportação no arquivo dados/tendencia_institutos.json.
    """
    relatorio = {
        "criterio_minimo_pesquisas": min_pesquisas,
        "institutos": []
    }
    
    if df.empty:
        return relatorio
        
    contagem_pesquisas = df.groupby("instituto_nome")["pesquisa_id"].nunique()
    
    for inst, count in contagem_pesquisas.items():
        vieses = house_effects.get(inst, {})
        elegivel = count >= min_pesquisas
        
        # Filtra apenas candidatos com viés calculado
        vieses_significativos = {k: v for k, v in vieses.items() if abs(v) > 0.001}
        
        relatorio["institutos"].append({
            "instituto": inst,
            "total_pesquisas": int(count),
            "elegivel_house_effect": bool(elegivel),
            "vieses_por_candidato": vieses if elegivel else {},
            "status": "Ajustado por Efeito Casa" if elegivel and vieses_significativos else "Sem ajuste sistemático"
        })
        
    return relatorio
