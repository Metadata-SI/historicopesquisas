"""
Módulo de Configuração: Leitura e validação das definições em config.yaml.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List
import yaml


def carregar_config(caminho_config: str | Path = "config.yaml") -> Dict[str, Any]:
    """
    Lê e retorna as configurações do projeto a partir do arquivo YAML especificado.
    """
    caminho = Path(caminho_config)
    if not caminho.exists():
        raise FileNotFoundError(f"Arquivo de configuração não encontrado em: {caminho}")

    with open(caminho, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    return config or {}


def obter_candidatos_nao_validos(config: Dict[str, Any]) -> List[str]:
    """
    Retorna a lista de categorias consideradas 'não válidas' para apuração
    de votos válidos (ex: Branco, Nulo, Indeciso, Não Sabe).
    """
    categorias = config.get("modelo", {}).get("categorias_nao_validas", [])
    return [str(c).strip().lower() for c in categorias]
