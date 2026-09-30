"""
Pacote de Coletores de Notícias e Registros de Pesquisas Eleitorais.
Cada coletor herda de BaseColetor e implementa descoberta via RSS/sitemaps,
extração com trafilatura e validação contra regras do TSE.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseColetor(ABC):
    """
    Classe base para coletores de portais de notícias.
    Garante respeito ao intervalo mínimo de requisições e formato padronizado de saída.
    """

    def __init__(self, portal_nome: str, intervalo_minimo: float = 2.0, user_agent: str = ""):
        self.portal_nome = portal_nome
        self.intervalo_minimo = intervalo_minimo
        self.user_agent = user_agent

    @abstractmethod
    def descobrir_noticias(self) -> List[str]:
        """Descobre URLs relevantes a partir de RSS ou sitemaps."""
        pass

    @abstractmethod
    def extrair_materia(self, url: str) -> Dict[str, Any]:
        """Extrai texto e metadados da matéria jornalística."""
        pass
