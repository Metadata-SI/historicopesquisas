"""
Módulo Principal do Modelo de Agregação:
Integra decaimento temporal, ponderação amostral, efeitos de instituto (house effects),
bootstrap não-paramétrico e normalização de votos válidos para gerar os JSONs de saída.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from modelo.bootstrap import calcular_intervalo_bootstrap
from modelo.config import carregar_config, obter_candidatos_nao_validos
from modelo.database import carregar_pesquisas_completas, get_connection
from modelo.house_effects import (
    aplicar_ajuste_house_effects,
    calcular_house_effects,
    gerar_relatorio_institutos,
)
from modelo.pesos import calcular_pesos_compostos
from modelo.votos_validos import converter_para_votos_validos


def calcular_serie_temporal(
    df: pd.DataFrame,
    data_inicio_serie: str,
    data_fim_serie: Optional[str] = None,
    meia_vida_dias: float = 14.0,
    n_bootstraps: int = 2000,
    percentis: tuple[float, float] = (2.5, 97.5),
    peso_amostra_habilitado: bool = True,
    janela_maxima_dias: int = 90,
    seed: Optional[int] = 42
) -> List[Dict[str, Any]]:
    """
    Gera a série histórica diária de médias ponderadas e intervalos de confiança
    para cada candidato presente no DataFrame.
    """
    if df.empty:
        return []

    dados = df.copy()
    dados["data_fim"] = pd.to_datetime(dados["data_fim"])
    
    coluna_valor = "percentual_ajustado" if "percentual_ajustado" in dados.columns else "percentual"

    # Determina o intervalo diário da série
    dt_inicio = pd.to_datetime(data_inicio_serie)
    primeira_pesquisa = dados["data_fim"].min()
    dt_inicio_real = max(dt_inicio, primeira_pesquisa)
    
    if data_fim_serie:
        dt_fim = pd.to_datetime(data_fim_serie)
    else:
        dt_fim = max(dados["data_fim"].max(), pd.Timestamp.now().normalize())

    if dt_inicio_real > dt_fim:
        dt_inicio_real = dt_fim

    dias_serie = pd.date_range(dt_inicio_real, dt_fim, freq="D")
    
    resultado_serie: List[Dict[str, Any]] = []

    for dia in dias_serie:
        # Pesquisas elegíveis: concluídas até a data de referência 'dia' e dentro da janela máxima
        limite_passado = dia - pd.Timedelta(days=janela_maxima_dias)
        filtro_dia = (dados["data_fim"] <= dia) & (dados["data_fim"] >= limite_passado)
        df_dia = dados[filtro_dia]
        
        if df_dia.empty:
            continue
            
        # Ponderação composta para o dia
        pesos_dia = calcular_pesos_compostos(
            df_dia,
            data_referencia=dia,
            meia_vida_dias=meia_vida_dias,
            peso_amostra_habilitado=peso_amostra_habilitado
        )
        df_dia = df_dia.assign(peso_calculado=pesos_dia)
        
        # Filtra pesos não-nulos
        df_dia = df_dia[df_dia["peso_calculado"] > 0]
        if df_dia.empty:
            continue

        candidatos = df_dia["candidato"].unique()
        dia_str = dia.strftime("%Y-%m-%d")

        for cand in candidatos:
            df_cand = df_dia[df_dia["candidato"] == cand]
            if df_cand.empty:
                continue

            valores = df_cand[coluna_valor].values
            pesos = df_cand["peso_calculado"].values
            amostras = df_cand["amostra"].values if "amostra" in df_cand.columns else None
            margens = df_cand["margem_erro"].values if "margem_erro" in df_cand.columns else None
            n_pesquisas = int(df_cand["pesquisa_id"].nunique())

            media, ic_inf, ic_sup = calcular_intervalo_bootstrap(
                valores=valores,
                pesos=pesos,
                amostras=amostras,
                margens_erro=margens,
                n_bootstraps=n_bootstraps,
                percentis=percentis,
                seed=seed
            )

            resultado_serie.append({
                "data": dia_str,
                "candidato": cand,
                "media": media,
                "ic_inferior": ic_inf,
                "ic_superior": ic_sup,
                "pesquisas_ativas": n_pesquisas
            })

    return resultado_serie


def estruturar_pesquisas_recentes(df: pd.DataFrame, limite: int = 50) -> List[Dict[str, Any]]:
    """
    Estrutura a lista de pesquisas recentes com resultados e metadados para o JSON.
    """
    if df.empty:
        return []

    lista_pesquisas: List[Dict[str, Any]] = []
    
    # Agrupa por pesquisa única
    pesquisas_ids = df.sort_values("data_fim", ascending=False)["pesquisa_id"].unique()[:limite]
    
    for pid in pesquisas_ids:
        df_p = df[df["pesquisa_id"] == pid]
        primeira = df_p.iloc[0]
        
        cenarios_dict: List[Dict[str, Any]] = []
        for (turno, cenario_nome), df_cen in df_p.groupby(["turno", "cenario"]):
            resultados = {
                str(row["candidato"]): float(row["percentual"])
                for _, row in df_cen.iterrows()
            }
            cenarios_dict.append({
                "turno": int(turno),
                "cenario": cenario_nome,
                "resultados": resultados
            })
            
        lista_pesquisas.append({
            "pesquisa_id": int(pid),
            "instituto": str(primeira["instituto_nome"]),
            "registro_tse": str(primeira["registro_tse"]),
            "uf": str(primeira["uf"]),
            "cargo": str(primeira["cargo"]),
            "data_inicio": str(pd.to_datetime(primeira["data_inicio"]).strftime("%Y-%m-%d")),
            "data_fim": str(pd.to_datetime(primeira["data_fim"]).strftime("%Y-%m-%d")),
            "data_divulgacao": str(pd.to_datetime(primeira["data_divulgacao"]).strftime("%Y-%m-%d")) if pd.notnull(primeira.get("data_divulgacao")) else None,
            "amostra": int(primeira["amostra"]),
            "margem_erro": float(primeira["margem_erro"]) if pd.notnull(primeira.get("margem_erro")) else None,
            "metodologia": str(primeira["metodologia"]) if pd.notnull(primeira.get("metodologia")) else None,
            "impugnada": bool(primeira["impugnada"]),
            "cenarios": cenarios_dict
        })
        
    return lista_pesquisas


def executar_pipeline_modelo(
    caminho_config: str | Path = "config.yaml"
) -> Dict[str, Any]:
    """
    Executa o modelo completo de agregação:
    1. Carrega dados válidos do banco SQLite.
    2. Calcula House Effects.
    3. Gera séries para 1º e 2º turnos (Intenção Total e Votos Válidos).
    4. Gera e persiste os 3 arquivos JSON versionados em dados/.
    """
    config = carregar_config(caminho_config)
    banco_path = config.get("caminhos", {}).get("banco_sqlite", "dados/pesquisas.db")
    caminho_json_serie = Path(config.get("caminhos", {}).get("saida_json_serie", "dados/serie_diaria.json"))
    caminho_json_pesquisas = Path(config.get("caminhos", {}).get("saida_json_pesquisas", "dados/pesquisas_recentes.json"))
    caminho_json_institutos = Path(config.get("caminhos", {}).get("saida_json_institutos", "dados/tendencia_institutos.json"))

    cfg_mod = config.get("modelo", {})
    meia_vida = float(cfg_mod.get("meia_vida_dias", 14.0))
    dt_inicio = str(cfg_mod.get("data_inicio_serie", "2026-01-01"))
    n_boot = int(cfg_mod.get("n_bootstraps", 2000))
    p_inf = float(cfg_mod.get("intervalo_confianca", {}).get("percentil_inferior", 2.5))
    p_sup = float(cfg_mod.get("intervalo_confianca", {}).get("percentil_superior", 97.5))
    peso_amostra = bool(cfg_mod.get("peso_amostra_habilitado", True))
    min_inst = int(cfg_mod.get("house_effects", {}).get("min_pesquisas_instituto", 5))
    house_effects_habilitado = bool(cfg_mod.get("house_effects", {}).get("habilitado", True))
    nao_validos = cfg_mod.get("categorias_nao_validas", [])

    # Carrega dados do banco SQLite
    conn = get_connection(banco_path)
    df_completo = carregar_pesquisas_completas(conn, cargo="Presidente", uf="BR", apenas_nao_impugnadas=True)
    conn.close()

    agora_iso = datetime.now(timezone.utc).isoformat()

    if df_completo.empty:
        vazio_json = {
            "gerado_em": agora_iso,
            "total_pesquisas": 0,
            "mensagem": "Nenhuma pesquisa elegível encontrada no banco de dados."
        }
        caminho_json_serie.parent.mkdir(parents=True, exist_ok=True)
        with open(caminho_json_serie, "w", encoding="utf-8") as f:
            json.dump(vazio_json, f, indent=2, ensure_ascii=False)
        return vazio_json

    # 1. House Effects (calculado sobre pesquisas de 1º turno)
    df_t1_base = df_completo[df_completo["turno"] == 1]
    if house_effects_habilitado:
        house_effects = calcular_house_effects(df_t1_base, min_pesquisas=min_inst)
        df_ajustado = aplicar_ajuste_house_effects(df_completo, house_effects)
    else:
        house_effects = {}
        df_ajustado = df_completo.copy()
        df_ajustado["percentual_ajustado"] = df_ajustado["percentual"]

    # 2. Votos Válidos
    df_validos = converter_para_votos_validos(df_ajustado, nao_validos)

    # 3. Séries Temporais para 1º Turno
    df_t1_total = df_ajustado[df_ajustado["turno"] == 1]
    df_t1_val = df_validos[df_validos["turno"] == 1]

    serie_t1_total = calcular_serie_temporal(
        df_t1_total,
        data_inicio_serie=dt_inicio,
        meia_vida_dias=meia_vida,
        n_bootstraps=n_boot,
        percentis=(p_inf, p_sup),
        peso_amostra_habilitado=peso_amostra
    )
    serie_t1_val = calcular_serie_temporal(
        df_t1_val,
        data_inicio_serie=dt_inicio,
        meia_vida_dias=meia_vida,
        n_bootstraps=n_boot,
        percentis=(p_inf, p_sup),
        peso_amostra_habilitado=peso_amostra
    )

    # 4. Séries Temporais para 2º Turno
    df_t2_total = df_ajustado[df_ajustado["turno"] == 2]
    df_t2_val = df_validos[df_validos["turno"] == 2]

    serie_t2_total = calcular_serie_temporal(
        df_t2_total,
        data_inicio_serie=dt_inicio,
        meia_vida_dias=meia_vida,
        n_bootstraps=n_boot,
        percentis=(p_inf, p_sup),
        peso_amostra_habilitado=peso_amostra
    )
    serie_t2_val = calcular_serie_temporal(
        df_t2_val,
        data_inicio_serie=dt_inicio,
        meia_vida_dias=meia_vida,
        n_bootstraps=n_boot,
        percentis=(p_inf, p_sup),
        peso_amostra_habilitado=peso_amostra
    )

    # 5. Formatação dos 3 arquivos JSON
    json_serie_data = {
        "gerado_em": agora_iso,
        "parametros": {
            "meia_vida_dias": meia_vida,
            "n_bootstraps": n_boot,
            "percentis": [p_inf, p_sup],
            "peso_amostra_habilitado": peso_amostra,
            "house_effects_habilitado": house_effects_habilitado
        },
        "turno_1": {
            "total": serie_t1_total,
            "validos": serie_t1_val
        },
        "turno_2": {
            "total": serie_t2_total,
            "validos": serie_t2_val
        }
    }

    pesquisas_recentes_data = {
        "gerado_em": agora_iso,
        "total_pesquisas": int(df_completo["pesquisa_id"].nunique()),
        "pesquisas": estruturar_pesquisas_recentes(df_completo)
    }

    relatorio_institutos_data = gerar_relatorio_institutos(
        df_t1_base,
        house_effects=house_effects,
        min_pesquisas=min_inst
    )
    relatorio_institutos_data["gerado_em"] = agora_iso

    # Persistência dos JSONs na pasta dados/ e cópia para site/dados/ para deploy estático
    caminho_json_serie.parent.mkdir(parents=True, exist_ok=True)
    site_dados_dir = Path("site/dados")
    site_dados_dir.mkdir(parents=True, exist_ok=True)

    for destino in [caminho_json_serie, site_dados_dir / "serie_diaria.json"]:
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(json_serie_data, f, indent=2, ensure_ascii=False)

    for destino in [caminho_json_pesquisas, site_dados_dir / "pesquisas_recentes.json"]:
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(pesquisas_recentes_data, f, indent=2, ensure_ascii=False)

    for destino in [caminho_json_institutos, site_dados_dir / "tendencia_institutos.json"]:
        with open(destino, "w", encoding="utf-8") as f:
            json.dump(relatorio_institutos_data, f, indent=2, ensure_ascii=False)

    return {
        "sucesso": True,
        "total_pesquisas": int(df_completo["pesquisa_id"].nunique()),
        "pontos_serie_t1_total": len(serie_t1_total),
        "pontos_serie_t1_validos": len(serie_t1_val),
        "pontos_serie_t2_total": len(serie_t2_total),
        "pontos_serie_t2_validos": len(serie_t2_val),
    }
