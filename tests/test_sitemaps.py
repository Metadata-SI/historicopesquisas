"""
Testes da varredura histórica por sitemaps e da coleta incremental (sem acesso à rede).
"""

from datetime import date
from pathlib import Path

import pytest

from coleta.descoberta import ItemFeed, coletar_materias
from coleta.sitemaps import (
    descobrir_urls,
    listar_sitemaps_diarios,
    termos_de_institutos,
    url_relevante,
)
from coleta.tse_oficial import salvar_registros_oficiais
from modelo.database import get_connection, init_db

INSTITUTOS = [
    {"nome": "Quaest", "texto": ["quaest"], "tse": ["QUAEST"]},
    {"nome": "Paraná Pesquisas", "texto": ["paraná pesquisas"], "tse": ["INSTITUTO PARANA"]},
    {"nome": "CNT/MDA", "texto": ["cnt/mda", "mda"], "tse": ["MDA-PESQUISA"]},
]
G1 = {"indice": "https://g1/sitemap.xml", "regex_data": r"/g1/(?P<y>\d{4})/(?P<m>\d{2})/(?P<d>\d{2})_"}

INDICE_G1 = """<sitemapindex>
<sitemap><loc>https://g1/sitemap/g1/2026/09/29_1.xml</loc></sitemap>
<sitemap><loc>https://g1/sitemap/g1/2026/09/29_2.xml</loc></sitemap>
<sitemap><loc>https://g1/sitemap/g1/2026/01/10_1.xml</loc></sitemap>
<sitemap><loc>https://g1/sitemap/g1/2025/12/31_1.xml</loc></sitemap>
<sitemap><loc>https://g1/sitemap/g1/lixo.xml</loc></sitemap>
</sitemapindex>"""

SITEMAP_DIA = """<urlset>
<url><loc>https://g1.globo.com/politica/eleicoes/2026/noticia/2026/09/29/quaest-lula-tem-39percent.ghtml</loc></url>
<url><loc>https://g1.globo.com/politica/noticia/2026/09/29/pesquisa-mostra-rejeicao-de-candidatos.ghtml</loc></url>
<url><loc>https://g1.globo.com/economia/noticia/2026/09/29/pesquisa-mostra-alta-do-dolar.ghtml</loc></url>
<url><loc>https://g1.globo.com/rr/roraima/noticia/2026/09/29/quaest-em-roraima-intencao-de-voto.ghtml</loc></url>
<url><loc>https://g1.globo.com/politica/noticia/2026/09/29/lula-visita-obra.ghtml</loc></url>
<url><loc>https://g1.globo.com/politica/noticia/2026/09/29/quaest-lula-tem-39percent.ghtml?a=1&amp;b=2</loc></url>
</urlset>"""


def fake_baixar(mapa):
    def _b(url, ua):
        return mapa[url]
    return _b


class TestFiltroDeUrl:
    def test_termos_ignoram_sigla_curta(self):
        termos = termos_de_institutos(INSTITUTOS)
        assert "quaest" in termos and "paranapesquisas" in termos and "parana-pesquisas" in termos
        assert "mda" not in termos

    @pytest.mark.parametrize("url,esperado", [
        ("https://g1.globo.com/politica/eleicoes/2026/noticia/2026/09/29/quaest-lula.ghtml", True),
        ("https://g1.globo.com/rr/roraima/noticia/2026/09/29/quaest-em-roraima.ghtml", True),  # instituto, fora de /politica/
        ("https://g1.globo.com/politica/noticia/2026/09/29/pesquisa-mostra-rejeicao.ghtml", True),
        ("https://g1.globo.com/economia/noticia/2026/09/29/pesquisa-mostra-alta-do-dolar.ghtml", False),
        ("https://g1.globo.com/politica/noticia/2026/09/29/lula-visita-obra.ghtml", False),
        ("https://www.estadao.com.br/politica/eleicoes/datafolha-lula/", True),
    ])
    def test_relevancia(self, url, esperado):
        assert url_relevante(url, termos_de_institutos(INSTITUTOS + [{"texto": ["datafolha"]}])) is esperado


class TestVarredura:
    def test_lista_sitemaps_do_periodo_mais_recente_primeiro(self):
        dias = listar_sitemaps_diarios(G1["indice"], G1["regex_data"], date(2026, 1, 1), None, "ua",
                                       baixar=fake_baixar({G1["indice"]: INDICE_G1}))
        assert [(d.isoformat(), u[-8:]) for d, u in dias] == [
            ("2026-09-29", "29_1.xml"), ("2026-09-29", "29_2.xml"), ("2026-01-10", "10_1.xml"),
        ]

    def test_descobre_urls_relevantes_sem_duplicar(self):
        mapa = {
            G1["indice"]: INDICE_G1,
            "https://g1/sitemap/g1/2026/09/29_1.xml": SITEMAP_DIA,
            "https://g1/sitemap/g1/2026/09/29_2.xml": SITEMAP_DIA,  # mesmas URLs no 2º arquivo do dia
            "https://g1/sitemap/g1/2026/01/10_1.xml": "<urlset></urlset>",
        }
        itens = descobrir_urls("g1", G1, INSTITUTOS, date(2026, 1, 1), None, "ua",
                               baixar=fake_baixar(mapa), pausa=lambda s: None)
        urls = [i.url for i in itens]
        assert len(urls) == len(set(urls)) == 4
        assert all(i.titulo_provisorio and i.publicado == date(2026, 9, 29) for i in itens)
        assert any("a=1&b=2" in u for u in urls)  # &amp; do XML foi decodificado

    def test_ignora_urls_ja_processadas(self):
        mapa = {G1["indice"]: INDICE_G1, "https://g1/sitemap/g1/2026/09/29_1.xml": SITEMAP_DIA,
                "https://g1/sitemap/g1/2026/09/29_2.xml": "<urlset></urlset>",
                "https://g1/sitemap/g1/2026/01/10_1.xml": "<urlset></urlset>"}
        feitas = {"https://g1.globo.com/politica/eleicoes/2026/noticia/2026/09/29/quaest-lula-tem-39percent.ghtml"}
        itens = descobrir_urls("g1", G1, INSTITUTOS, date(2026, 1, 1), None, "ua", ja_processadas=feitas,
                               baixar=fake_baixar(mapa), pausa=lambda s: None)
        assert len(itens) == 3


def _reg():
    return {
        "registro_tse": "BR-00001/2026", "protocolo_original": "BR000012026", "uf": "BR", "cargo": "Presidente",
        "empresa_cnpj": None, "empresa_nome": "QUAEST PESQUISAS LTDA", "data_registro": None,
        "data_inicio": "2026-09-24", "data_fim": "2026-09-27", "data_divulgacao": "2026-09-28",
        "amostra": 2004, "valor": None, "metodologia": None, "plano_amostral": None, "pesquisa_propria": False,
    }


TEXTO_NACIONAL = """Quaest para presidente, 1º turno.
- Lula (PT): 39% (eram 38%)
- Flávio Bolsonaro (PL): 34% (eram 33%)
- Ronaldo Caiado (PSD): 4% (eram 4%)
- Augusto Cury (Avante): 4% (eram 5%)
- Renan Santos (Missão): 3% (eram 3%)
- Romeu Zema (Novo): 1% (eram 1%)
- Branco/nulo/não vai votar: 10% (eram 10%)
- Indecisos: 5% (eram 6%)
A Quaest ouviu 2.004 pessoas. Registro BR-00001/2026.
"""

URL_ITEM = "https://g1.globo.com/politica/eleicoes/2026/noticia/2026/09/28/quaest.ghtml"


class TestColetaIncremental:
    @pytest.fixture
    def conn(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr("coleta.descoberta._permitido_por_robots", lambda *a, **k: True)
        db = tmp_path / "t.db"
        init_db(db, "dados/schema.sql")
        c = get_connection(db)
        salvar_registros_oficiais(c, [_reg()])
        yield c
        c.close()

    def _config(self):
        return {
            "coleta": {"feeds": {}, "sitemaps": {"g1": G1}, "institutos": INSTITUTOS,
                       "intervalo_minimo_segundos": 0, "historico_desde": "2026-01-01"},
            "modelo": {"candidatos_monitorados": ["Lula", "Flávio Bolsonaro", "Ronaldo Caiado",
                                                  "Augusto Cury", "Renan Santos", "Romeu Zema"]},
            "validacao": {},
        }

    def _rodar(self, conn, baixados, **kw):
        item = ItemFeed("quaest lula", URL_ITEM, date(2026, 9, 28), titulo_provisorio=True)

        def baixar(url, ua):
            baixados.append(url)
            return ("Quaest: Lula tem 39%", TEXTO_NACIONAL)

        return coletar_materias(
            conn, self._config(), baixar_fn=baixar, pausa=lambda s: None, ler_feed_fn=lambda u, a: [],
            descobrir_urls_fn=lambda *a, **k: [item], **kw,
        )

    def test_historico_grava_pesquisa_nacional_com_titulo_real(self, conn):
        stats = self._rodar(conn, [])
        assert stats["cenarios_gravados"] == 1
        assert conn.execute("SELECT uf FROM pesquisa").fetchone()["uf"] == "BR"
        assert conn.execute("SELECT titulo FROM materia_pesquisa").fetchone()["titulo"] == "Quaest: Lula tem 39%"

    def test_segunda_execucao_nao_baixa_de_novo(self, conn):
        baixados = []
        self._rodar(conn, baixados)
        self._rodar(conn, baixados)
        assert len(baixados) == 1

    def test_reprocessar_baixa_de_novo(self, conn):
        baixados = []
        self._rodar(conn, baixados)
        self._rodar(conn, baixados, reprocessar=True)
        assert len(baixados) == 2

    def test_falha_de_download_nao_marca_como_processada(self, conn):
        item = ItemFeed("quaest", URL_ITEM, date(2026, 9, 28), titulo_provisorio=True)
        coletar_materias(conn, self._config(), baixar_fn=lambda u, a: None, pausa=lambda s: None,
                         ler_feed_fn=lambda u, a: [], descobrir_urls_fn=lambda *a, **k: [item])
        assert conn.execute("SELECT COUNT(*) FROM url_processada").fetchone()[0] == 0

    def test_modo_rapido_nao_varre_sitemaps(self, conn):
        chamado = []
        coletar_materias(conn, self._config(), baixar_fn=lambda u, a: None, pausa=lambda s: None,
                         ler_feed_fn=lambda u, a: [], descobrir_urls_fn=lambda *a, **k: chamado.append(1) or [],
                         historico=False)
        assert chamado == []
