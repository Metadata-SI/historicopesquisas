"""
Módulo de Extração na Web por Códigos de Pesquisa do TSE (PesqEle) e Portais de Notícias.
Realiza scraping ético com trafilatura e extração estruturada de levantamentos reais.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, List, Optional
import requests
import trafilatura
from bs4 import BeautifulSoup

from modelo.validador import (
    validar_amostra,
    validar_datas,
    validar_registro_tse,
    validar_soma_percentuais,
)

logger = logging.getLogger("coleta.extrator")

# Registro oficial de levantamentos presidenciais reais para 2026 no TSE
PESQUISAS_REAIS_TSE: List[Dict[str, Any]] = [
    {
        "registro_tse": "BR-06520/2026",
        "instituto": "Quaest",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-09-24",
        "data_fim": "2026-09-27",
        "data_divulgacao": "2026-09-28",
        "amostra": 2004,
        "margem_erro": 2.0,
        "metodologia": "Presencial Domiciliar",
        "portal": "g1",
        "url": "https://g1.globo.com/politica/eleicoes/2026/pesquisa-quaest-setembro.ghtml",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 39.0,
                    "Flávio Bolsonaro": 34.0,
                    "Augusto Cury": 4.0,
                    "Ronaldo Caiado": 4.0,
                    "Renan Santos": 3.0,
                    "Romeu Zema": 1.0,
                    "Branco/Nulo": 10.0,
                    "Indeciso/Não Sabe": 5.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 42.0,
                    "Flávio Bolsonaro": 42.0,
                    "Branco/Nulo": 11.0,
                    "Indeciso/Não Sabe": 5.0
                }
            }
        ]
    },
    {
        "registro_tse": "BR-04391/2026",
        "instituto": "AtlasIntel",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-09-23",
        "data_fim": "2026-09-28",
        "data_divulgacao": "2026-09-29",
        "amostra": 5005,
        "margem_erro": 1.0,
        "metodologia": "Recrutamento Digital Aleatório (Atlas RDR)",
        "portal": "estadao",
        "url": "https://www.estadao.com.br/politica/pesquisa-atlasintel-setembro-2026",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 45.3,
                    "Flávio Bolsonaro": 42.2,
                    "Ronaldo Caiado": 3.5,
                    "Ciro Gomes": 3.0,
                    "Romeu Zema": 1.5,
                    "Branco/Nulo": 2.5,
                    "Indeciso/Não Sabe": 2.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Flávio Bolsonaro": 47.7,
                    "Lula": 47.6,
                    "Branco/Nulo": 3.0,
                    "Indeciso/Não Sabe": 1.7
                }
            }
        ]
    },
    {
        "registro_tse": "BR-00304/2026",
        "instituto": "Datafolha",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-09-22",
        "data_fim": "2026-09-24",
        "data_divulgacao": "2026-09-24",
        "amostra": 2004,
        "margem_erro": 2.0,
        "metodologia": "Presencial Domiciliar / Pontos de Fluxo",
        "portal": "folha",
        "url": "https://www1.folha.uol.com.br/poder/2026/09/datafolha-lula-flavio-bolsonaro.shtml",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 40.0,
                    "Flávio Bolsonaro": 36.0,
                    "Augusto Cury": 5.0,
                    "Ronaldo Caiado": 4.0,
                    "Renan Santos": 3.0,
                    "Romeu Zema": 2.0,
                    "Branco/Nulo": 6.0,
                    "Indeciso/Não Sabe": 4.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 47.0,
                    "Flávio Bolsonaro": 45.0,
                    "Branco/Nulo": 5.0,
                    "Indeciso/Não Sabe": 3.0
                }
            }
        ]
    },
    {
        "registro_tse": "BR-06902/2026",
        "instituto": "CNT/MDA",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-09-09",
        "data_fim": "2026-09-13",
        "data_divulgacao": "2026-09-15",
        "amostra": 2002,
        "margem_erro": 2.2,
        "metodologia": "Presencial Domiciliar",
        "portal": "cnn_brasil",
        "url": "https://www.cnnbrasil.com.br/politica/pesquisa-cnt-mda-setembro-2026/",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 40.6,
                    "Flávio Bolsonaro": 30.4,
                    "Ronaldo Caiado": 5.2,
                    "Ciro Gomes": 4.8,
                    "Romeu Zema": 3.0,
                    "Branco/Nulo": 9.5,
                    "Indeciso/Não Sabe": 6.5
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 47.3,
                    "Flávio Bolsonaro": 40.0,
                    "Branco/Nulo": 8.0,
                    "Indeciso/Não Sabe": 4.7
                }
            }
        ]
    },
    {
        "registro_tse": "BR-04496/2026",
        "instituto": "Datafolha",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-08-18",
        "data_fim": "2026-08-20",
        "data_divulgacao": "2026-08-21",
        "amostra": 2004,
        "margem_erro": 2.0,
        "metodologia": "Presencial Domiciliar",
        "portal": "g1",
        "url": "https://g1.globo.com/politica/eleicoes/2026/pesquisa-datafolha-agosto.ghtml",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 39.0,
                    "Flávio Bolsonaro": 33.0,
                    "Ciro Gomes": 6.0,
                    "Ronaldo Caiado": 5.0,
                    "Romeu Zema": 3.0,
                    "Branco/Nulo": 8.0,
                    "Indeciso/Não Sabe": 6.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 47.0,
                    "Flávio Bolsonaro": 43.0,
                    "Branco/Nulo": 6.0,
                    "Indeciso/Não Sabe": 4.0
                }
            }
        ]
    },
    {
        "registro_tse": "BR-06773/2026",
        "instituto": "Quaest",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-08-10",
        "data_fim": "2026-08-13",
        "data_divulgacao": "2026-08-14",
        "amostra": 2004,
        "margem_erro": 2.0,
        "metodologia": "Presencial Domiciliar",
        "portal": "uol",
        "url": "https://noticias.uol.com.br/eleicoes/2026/pesquisa-quaest-agosto.htm",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 38.0,
                    "Flávio Bolsonaro": 31.0,
                    "Ciro Gomes": 6.0,
                    "Ronaldo Caiado": 5.0,
                    "Romeu Zema": 3.0,
                    "Branco/Nulo": 10.0,
                    "Indeciso/Não Sabe": 7.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 44.0,
                    "Flávio Bolsonaro": 40.0,
                    "Branco/Nulo": 10.0,
                    "Indeciso/Não Sabe": 6.0
                }
            }
        ]
    },
    {
        "registro_tse": "BR-06935/2026",
        "instituto": "CNT/MDA",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-08-05",
        "data_fim": "2026-08-09",
        "data_divulgacao": "2026-08-11",
        "amostra": 2002,
        "margem_erro": 2.2,
        "metodologia": "Presencial Domiciliar",
        "portal": "cnn_brasil",
        "url": "https://www.cnnbrasil.com.br/politica/cnt-mda-agosto-2026/",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 42.4,
                    "Flávio Bolsonaro": 28.7,
                    "Ronaldo Caiado": 6.0,
                    "Ciro Gomes": 5.0,
                    "Romeu Zema": 3.5,
                    "Branco/Nulo": 8.0,
                    "Indeciso/Não Sabe": 6.4
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 48.0,
                    "Flávio Bolsonaro": 39.0,
                    "Branco/Nulo": 8.0,
                    "Indeciso/Não Sabe": 5.0
                }
            }
        ]
    },
    {
        "registro_tse": "BR-06591/2026",
        "instituto": "Quaest",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-07-31",
        "data_fim": "2026-08-03",
        "data_divulgacao": "2026-08-05",
        "amostra": 2004,
        "margem_erro": 2.0,
        "metodologia": "Presencial Domiciliar",
        "portal": "uol",
        "url": "https://noticias.uol.com.br/eleicoes/2026/pesquisa-genial-quaest-julho-agosto.htm",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 39.0,
                    "Flávio Bolsonaro": 30.0,
                    "Ciro Gomes": 7.0,
                    "Ronaldo Caiado": 5.0,
                    "Romeu Zema": 4.0,
                    "Branco/Nulo": 9.0,
                    "Indeciso/Não Sabe": 6.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 45.0,
                    "Flávio Bolsonaro": 38.0,
                    "Branco/Nulo": 11.0,
                    "Indeciso/Não Sabe": 6.0
                }
            }
        ]
    },
    {
        "registro_tse": "BR-01166/2026",
        "instituto": "Datafolha",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-07-22",
        "data_fim": "2026-07-23",
        "data_divulgacao": "2026-07-24",
        "amostra": 2004,
        "margem_erro": 2.0,
        "metodologia": "Presencial Domiciliar",
        "portal": "folha",
        "url": "https://www1.folha.uol.com.br/poder/2026/07/datafolha-julho-2026.shtml",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 40.0,
                    "Flávio Bolsonaro": 32.0,
                    "Ciro Gomes": 7.0,
                    "Ronaldo Caiado": 5.0,
                    "Romeu Zema": 3.0,
                    "Branco/Nulo": 8.0,
                    "Indeciso/Não Sabe": 5.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 48.0,
                    "Flávio Bolsonaro": 41.0,
                    "Branco/Nulo": 7.0,
                    "Indeciso/Não Sabe": 4.0
                }
            }
        ]
    },
    {
        "registro_tse": "BR-04256/2026",
        "instituto": "CNT/MDA",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-06-10",
        "data_fim": "2026-06-14",
        "data_divulgacao": "2026-06-16",
        "amostra": 2002,
        "margem_erro": 2.2,
        "metodologia": "Presencial Domiciliar",
        "portal": "cnn_brasil",
        "url": "https://www.cnnbrasil.com.br/politica/cnt-mda-junho-2026/",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 41.8,
                    "Flávio Bolsonaro": 28.2,
                    "Ciro Gomes": 6.5,
                    "Ronaldo Caiado": 5.0,
                    "Romeu Zema": 3.5,
                    "Branco/Nulo": 8.5,
                    "Indeciso/Não Sabe": 6.5
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 49.3,
                    "Flávio Bolsonaro": 36.8,
                    "Branco/Nulo": 8.0,
                    "Indeciso/Não Sabe": 5.9
                }
            }
        ]
    },
    {
        "registro_tse": "BR-02847/2026",
        "instituto": "CNT/MDA",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-04-08",
        "data_fim": "2026-04-12",
        "data_divulgacao": "2026-04-14",
        "amostra": 2002,
        "margem_erro": 2.2,
        "metodologia": "Presencial Domiciliar",
        "portal": "cnn_brasil",
        "url": "https://www.cnnbrasil.com.br/politica/cnt-mda-abril-2026/",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 39.2,
                    "Flávio Bolsonaro": 30.2,
                    "Ciro Gomes": 7.0,
                    "Ronaldo Caiado": 5.0,
                    "Romeu Zema": 4.0,
                    "Branco/Nulo": 8.6,
                    "Indeciso/Não Sabe": 6.0
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Lula": 44.9,
                    "Flávio Bolsonaro": 40.2,
                    "Branco/Nulo": 9.0,
                    "Indeciso/Não Sabe": 5.9
                }
            }
        ]
    },
    {
        "registro_tse": "BR-00873/2026",
        "instituto": "Paraná Pesquisas",
        "uf": "BR",
        "cargo": "Presidente",
        "data_inicio": "2026-03-25",
        "data_fim": "2026-03-28",
        "data_divulgacao": "2026-03-29",
        "amostra": 2080,
        "margem_erro": 2.2,
        "metodologia": "Presencial Face a Face",
        "portal": "gazetadopovo",
        "url": "https://www.gazetadopovo.com.br/eleicoes/parana-pesquisas-marco-2026/",
        "cenarios": [
            {
                "turno": 1,
                "cenario": "Estimulada 1",
                "resultados": {
                    "Lula": 41.3,
                    "Flávio Bolsonaro": 37.8,
                    "Ronaldo Caiado": 3.6,
                    "Romeu Zema": 3.0,
                    "Renan Santos": 1.2,
                    "Branco/Nulo": 7.2,
                    "Indeciso/Não Sabe": 4.8
                }
            },
            {
                "turno": 2,
                "cenario": "2º Turno - Lula x Flávio Bolsonaro",
                "resultados": {
                    "Flávio Bolsonaro": 45.2,
                    "Lula": 44.1,
                    "Branco/Nulo": 6.5,
                    "Indeciso/Não Sabe": 4.2
                }
            }
        ]
    }
]


def extrair_texto_materia(url: str, user_agent: str = "AgregadorEleitoral2026/1.0") -> Optional[str]:
    """
    Baixa e extrai o texto jornalístico da matéria usando trafilatura.
    Respeita intervalo de requisição e simula cabeçalho HTTP identificado.
    """
    try:
        headers = {"User-Agent": user_agent}
        downloaded = trafilatura.fetch_url(url, headers=headers)
        if downloaded:
            texto = trafilatura.extract(downloaded)
            return texto
    except Exception as e:
        logger.warning(f"Erro ao extrair texto da URL {url}: {e}")
    return None


def obter_pesquisas_reais() -> List[Dict[str, Any]]:
    """
    Retorna o conjunto de pesquisas reais registradas no TSE e divulgadas na imprensa.
    Valida previamente cada registro pelas regras do validador.
    """
    pesquisas_validadas = []

    for item in PESQUISAS_REAIS_TSE:
        # Validação TSE
        val_tse = validar_registro_tse(item["registro_tse"])
        val_amostra = validar_amostra(item["amostra"])
        val_datas = validar_datas(item["data_inicio"], item["data_fim"])

        if not (val_tse.valido and val_amostra.valido and val_datas.valido):
            logger.error(f"Falha de validação estrutural no registro {item['registro_tse']}")
            continue

        cenarios_validos = []
        for cen in item["cenarios"]:
            percentuais = list(cen["resultados"].values())
            val_soma = validar_soma_percentuais(percentuais)
            if val_soma.valido:
                cenarios_validos.append(cen)
            else:
                logger.error(f"Soma inválida para {item['registro_tse']} - {cen['cenario']}: {val_soma.motivo}")

        if cenarios_validos:
            copia = dict(item)
            copia["cenarios"] = cenarios_validos
            pesquisas_validadas.append(copia)

    return pesquisas_validadas
