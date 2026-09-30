"""
Coletor de matérias de pesquisas eleitorais do portal Estadão.
Implementação detalhada a ser expandida na Etapa 4.
"""

from typing import Any, Dict, List
from coleta.base import BaseColetor


class ColetorEstadao(BaseColetor):
    def __init__(self, intervalo_minimo: float = 2.0, user_agent: str = ""):
        super().__init__("estadao", intervalo_minimo, user_agent)
        self.rss_feed = "https://www.estadao.com.br/arc/outboundfeeds/rss/category/politica/"

    def descobrir_noticias(self) -> List[str]:
        return []

    def extrair_materia(self, url: str) -> Dict[str, Any]:
        return {"portal": self.portal_nome, "url": url}
