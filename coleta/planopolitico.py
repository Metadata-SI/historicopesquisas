"""
Coletor do agregador Plano Político (https://planopolitico.com.br/agregador/).

As páginas já trazem os dados prontos em blocos <script type="application/json">:
  - id="agg-data":     séries, pesquisas e estimativas (presidente, governador ou senado);
  - id="br-map-data":  desenho SVG dos estados (usado no mapa do site).
Não há HTML para raspar: basta baixar cada página e ler o JSON.

Uso:
    python -m coleta.planopolitico
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import requests

logger = logging.getLogger(__name__)

BASE = "https://planopolitico.com.br/agregador/"
URL_PADRAO = BASE + "presidente/"          # mantido por compatibilidade
URL_GOVERNADOR = BASE + "governadores/"
URL_SENADO = BASE + "senado/"
USER_AGENT = "Mozilla/5.0 (compatible; AgregadorPesquisas/1.0)"


def _bloco(html: str, id_: str) -> Dict[str, Any] | None:
    m = re.search(rf'<script[^>]*id="{re.escape(id_)}"[^>]*>(.*?)</script>', html, re.DOTALL)
    return json.loads(m.group(1)) if m else None


def _dicionario_js(html: str, nome: str) -> Dict[str, str]:
    """Lê um dicionário literal da página (var NOME = { 'Candidato': 'valor', ... };)."""
    m = re.search(rf"var {nome} = \{{(.*?)\n\s*\}};", html, re.DOTALL)
    return dict(re.findall(r"'([^']+)'\s*:\s*'([^']*)'", m.group(1))) if m else {}


def extrair_dados(html: str) -> Dict[str, Any]:
    """Extrai e valida o JSON da página de presidente."""
    dados = _bloco(html, "agg-data")
    if dados is None:
        raise ValueError("Bloco 'agg-data' não encontrado: o layout do Plano Político mudou.")
    for chave in ("presidente_t1", "presidente_t2", "presidente_state"):
        if chave not in dados:
            raise ValueError(f"Campo '{chave}' ausente nos dados do Plano Político.")
    return dados


def _baixar_html(url: str, timeout: int = 60) -> str:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def _extrair_cargo(html: str, chave: str) -> Dict[str, Any]:
    dados = _bloco(html, "agg-data")
    if dados is None or chave not in dados or "states" not in dados[chave]:
        raise ValueError(f"Campo '{chave}' ausente: o layout do Plano Político mudou.")
    return dados[chave]


def baixar(url: str = URL_PADRAO, timeout: int = 60) -> Dict[str, Any]:
    """Presidente (obrigatório) + governador e senado (opcionais: falha neles não derruba a coleta)."""
    html = _baixar_html(url, timeout)
    dados = extrair_dados(html)
    dados["mapa"] = _bloco(html, "br-map-data")
    # Partido e cor de cada candidato (governador/presidente); o senado traz isso nos próprios dados
    dados["meta"] = {"partido": _dicionario_js(html, "PARTY"), "cores": _dicionario_js(html, "COLORS")}

    for chave, pagina in (("governador", URL_GOVERNADOR), ("senado", URL_SENADO)):
        try:
            dados[chave] = _extrair_cargo(_baixar_html(pagina, timeout), chave)
        except Exception as e:
            logger.warning("Plano Político: não foi possível coletar '%s' (%s).", chave, e)

    dados["coletado_em"] = datetime.now(timezone.utc).isoformat()
    dados["fonte_url"] = url
    return dados


def atualizar(destinos=("dados", "site/dados"), url: str = URL_PADRAO) -> Dict[str, Any]:
    """Baixa os dados e grava planopolitico.json em cada pasta de destino."""
    dados = baixar(url)
    for pasta in destinos:
        p = Path(pasta)
        p.mkdir(parents=True, exist_ok=True)
        with open(p / "planopolitico.json", "w", encoding="utf-8") as f:
            json.dump(dados, f, ensure_ascii=False, separators=(",", ":"))
    t1 = dados["presidente_t1"]
    logger.info(
        "Plano Político: presidente (%d pesquisas 1º turno, %d 2º turno), governador (%d UFs), senado (%d UFs); atualizado em %s.",
        len(t1.get("recent_polls", {}).get("t1", [])),
        len(t1.get("recent_polls", {}).get("t2", [])),
        len(dados.get("governador", {}).get("states", {})),
        len(dados.get("senado", {}).get("states", {})),
        dados.get("generated_at"),
    )
    return dados


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    atualizar()
