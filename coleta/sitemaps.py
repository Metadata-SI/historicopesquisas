"""
Varredura histórica de matérias pelos sitemaps diários dos portais.

O RSS guarda só as últimas ~100 matérias. Os sitemaps diários (g1 e Estadão) listam tudo o que
foi publicado, dia a dia, desde anos atrás, então permitem cobrir todas as pesquisas do período.
Aqui só se descobrem URLs; o download e a extração ficam com `descoberta.coletar_materias`.
"""

from __future__ import annotations

import html
import logging
import re
import time
import unicodedata
from datetime import date
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import requests

from coleta.descoberta import ItemFeed

logger = logging.getLogger("coleta.sitemaps")

PALAVRAS_CHAVE = ("pesquisa", "sondagem", "levantamento", "intencao", "intencoes")
REGEX_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")


def _sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    ).lower()


def _baixar(url: str, user_agent: str, timeout: int = 60) -> str:
    resp = requests.get(url, headers={"User-Agent": user_agent}, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def _locs(xml: str) -> List[str]:
    return [html.unescape(m) for m in REGEX_LOC.findall(xml)]


def termos_de_institutos(institutos: List[Dict[str, Any]]) -> List[str]:
    """Nomes de instituto como aparecem em slugs de URL (ex.: 'paranapesquisas', 'parana-pesquisas')."""
    termos = set()
    for inst in institutos:
        for t in inst.get("texto", []):
            base = re.sub(r"[^a-z0-9]+", "-", _sem_acento(t)).strip("-")
            if len(base) >= 5:  # ignora siglas curtas como "mda", que casam com qualquer coisa
                termos.add(base)
                termos.add(base.replace("-", ""))
    return sorted(termos)


def url_relevante(url: str, termos_instituto: Iterable[str]) -> bool:
    """
    Vale a pena baixar? Slug fala de pesquisa/instituto, e a matéria é de política/eleições
    (ou o slug cita um instituto conhecido). O filtro fino é feito depois, no texto.
    """
    slug = _sem_acento(url.rstrip("/").rsplit("/", 1)[-1])
    cita_instituto = any(t in slug for t in termos_instituto)
    fala_de_pesquisa = cita_instituto or any(p in slug for p in PALAVRAS_CHAVE)
    if not fala_de_pesquisa:
        return False
    return cita_instituto or "/eleicoes/" in url or "/politica/" in url


def listar_sitemaps_diarios(
    url_indice: str,
    regex_data: str,
    desde: date,
    ate: Optional[date],
    user_agent: str,
    baixar: Callable[[str, str], str] = _baixar,
) -> List[Tuple[date, str]]:
    """
    Lê o índice do portal e devolve (data, url_do_sitemap) do período, do mais recente ao mais antigo.
    `regex_data` precisa ter os grupos nomeados y, m, d.
    """
    padrao = re.compile(regex_data)
    achados: List[Tuple[date, str]] = []
    for loc in _locs(baixar(url_indice, user_agent)):
        m = padrao.search(loc)
        if not m:
            continue
        try:
            dia = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
        except ValueError:
            continue
        if dia >= desde and (ate is None or dia <= ate):
            achados.append((dia, loc))
    return sorted(achados, key=lambda x: x[0], reverse=True)


def descobrir_urls(
    portal: str,
    cfg_portal: Dict[str, Any],
    institutos: List[Dict[str, Any]],
    desde: date,
    ate: Optional[date],
    user_agent: str,
    ja_processadas: Optional[set] = None,
    baixar: Callable[[str, str], str] = _baixar,
    pausa: Callable[[float], None] = time.sleep,
    intervalo: float = 0.2,
) -> List[ItemFeed]:
    """
    Varre os sitemaps diários do portal no período e devolve as matérias relevantes ainda não
    processadas. Sitemaps de dias passados não mudam, mas a checagem é barata (~0,3 s por dia).
    """
    termos = termos_de_institutos(institutos)
    dias = listar_sitemaps_diarios(
        cfg_portal["indice"], cfg_portal["regex_data"], desde, ate, user_agent, baixar
    )
    logger.info(f"[{portal}] {len(dias)} sitemaps diários entre {desde} e {ate or 'hoje'}")

    itens: List[ItemFeed] = []
    vistos: set = set()
    for dia, url_sitemap in dias:
        try:
            urls = _locs(baixar(url_sitemap, user_agent))
        except Exception as e:
            logger.warning(f"[{portal}] sitemap {url_sitemap} indisponível: {e}")
            continue
        for url in urls:
            if url in vistos or (ja_processadas and url in ja_processadas):
                continue
            if url_relevante(url, termos):
                vistos.add(url)
                slug = url.rstrip("/").rsplit("/", 1)[-1].replace(".ghtml", "").replace("-", " ")
                itens.append(ItemFeed(titulo=slug, url=url, publicado=dia, titulo_provisorio=True))
        pausa(intervalo)

    logger.info(f"[{portal}] {len(itens)} matérias novas para analisar")
    return itens
