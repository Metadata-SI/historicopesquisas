"""
Coletor de matérias de pesquisas eleitorais do portal G1 (Globo).
Implementação detalhada a ser expandida na Etapa 4.
"""

from typing import Any, Dict, List
from coleta.base import BaseColetor


class ColetorG1(BaseColetor):
    def __init__(self, intervalo_minimo: float = 2.0, user_agent: str = ""):
        super().__init__("g1", intervalo_minimo, user_agent)
        self.rss_feed = "https://g1.globo.com/rss/g1/politica/"

    def descobrir_noticias(self) -> List[str]:
        # Implementação de descoberta na Etapa 4
        return []

    def extrair_materia(self, url: str) -> Dict[str, Any]:
        # Implementação com trafilatura na Etapa 4
        return {"portal": self.portal_nome, "url": url}
