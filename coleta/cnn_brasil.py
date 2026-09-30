"""
Coletor de matérias de pesquisas eleitorais da CNN Brasil.
Implementação detalhada a ser expandida na Etapa 4.
"""

from typing import Any, Dict, List
from coleta.base import BaseColetor


class ColetorCNNBrasil(BaseColetor):
    def __init__(self, intervalo_minimo: float = 2.0, user_agent: str = ""):
        super().__init__("cnn_brasil", intervalo_minimo, user_agent)
        self.rss_feed = "https://www.cnnbrasil.com.br/feed/"

    def descobrir_noticias(self) -> List[str]:
        return []

    def extrair_materia(self, url: str) -> Dict[str, Any]:
        return {"portal": self.portal_nome, "url": url}
