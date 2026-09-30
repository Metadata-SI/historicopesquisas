"""
Testes da descoberta de matérias e do vínculo com registros do TSE (sem acesso à rede).
"""

from datetime import date
from pathlib import Path

import pytest

from coleta.descoberta import (
    ItemFeed,
    casar_materia,
    coletar_materias,
    detectar_institutos,
    extrair_codigos,
)
from coleta.tse_oficial import salvar_registros_oficiais
from modelo.database import get_connection, init_db

INSTITUTOS = [
    {"nome": "Quaest", "texto": ["quaest"], "tse": ["QUAEST"]},
    {"nome": "Paraná Pesquisas", "texto": ["paraná pesquisas"], "tse": ["INSTITUTO PARANA DE PESQUISAS"]},
]


def _reg(codigo, empresa, divulgacao):
    return {
        "registro_tse": codigo, "protocolo_original": codigo.replace("-", "").replace("/", ""),
        "uf": "BR", "cargo": "Presidente", "empresa_cnpj": None, "empresa_nome": empresa,
        "data_registro": None, "data_inicio": "2026-09-01", "data_fim": "2026-09-05",
        "data_divulgacao": divulgacao, "amostra": 2000, "valor": None, "metodologia": None,
        "plano_amostral": None, "pesquisa_propria": False,
    }


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "t.db"
    init_db(db, "dados/schema.sql")
    c = get_connection(db)
    salvar_registros_oficiais(c, [
        _reg("BR-00001/2026", "QUAEST PESQUISAS LTDA", "2026-09-10"),
        _reg("BR-00002/2026", "QUAEST PESQUISAS LTDA", "2026-09-11"),
        _reg("BR-00003/2026", "INSTITUTO PARANA DE PESQUISAS E ANALISE LTDA", "2026-09-20"),
    ])
    yield c
    c.close()


class TestExtracao:
    def test_codigos_em_varios_formatos(self):
        texto = "Registrada no TSE sob BR-00001/2026 e também SP 01590 / 2026."
        assert extrair_codigos(texto) == {"BR-00001/2026", "SP-01590/2026"}

    def test_sem_codigo(self):
        assert extrair_codigos("Nada aqui, só 12345/2026") == set()

    def test_detecta_instituto_sem_acento_e_caixa(self):
        achados = detectar_institutos("Pesquisa PARANA PESQUISAS divulgada", INSTITUTOS)
        assert [i["nome"] for i in achados] == ["Paraná Pesquisas"]


class TestCasamento:
    def test_codigo_oficial(self, conn):
        r = casar_materia(conn, "Pesquisa para presidente, registro BR-00001/2026.", date(2026, 9, 10), INSTITUTOS)
        assert r["registros"] == ["BR-00001/2026"] and r["metodo"] == "codigo"

    def test_codigo_inexistente_no_tse(self, conn):
        r = casar_materia(conn, "Pesquisa presidente BR-77777/2026", date(2026, 9, 10), INSTITUTOS)
        assert r["registros"] == [] and "não constam" in r["motivo"]

    def test_codigo_estadual_nao_vincula(self, conn):
        # Código de outra UF é ignorado; sem código BR cai na regra de instituto (nenhum detectado).
        r = casar_materia(conn, "Pesquisa para presidente em SP-01590/2026", date(2026, 9, 10), INSTITUTOS)
        assert r["registros"] == []

    def test_instituto_e_data_unico_candidato(self, conn):
        r = casar_materia(conn, "Paraná Pesquisas: Lula lidera para presidente", date(2026, 9, 20), INSTITUTOS)
        assert r["registros"] == ["BR-00003/2026"] and r["metodo"] == "instituto+data"

    def test_instituto_e_data_ambiguo_vai_para_revisao(self, conn):
        r = casar_materia(conn, "Quaest: Lula lidera para presidente", date(2026, 9, 11), INSTITUTOS)
        assert r["registros"] == [] and "2 registros" in r["motivo"]

    def test_fora_da_janela(self, conn):
        r = casar_materia(conn, "Paraná Pesquisas presidente", date(2026, 10, 30), INSTITUTOS)
        assert r["registros"] == []

    def test_sem_mencao_a_presidente(self, conn):
        r = casar_materia(conn, "Paraná Pesquisas governador", date(2026, 9, 20), INSTITUTOS)
        assert r["registros"] == []


class TestColeta:
    def test_fluxo_completo(self, conn, monkeypatch):
        monkeypatch.setattr("coleta.descoberta._permitido_por_robots", lambda *a, **k: True)
        config = {"coleta": {
            "feeds": {"g1": "x"}, "institutos": INSTITUTOS, "janela_dias_match": 3,
            "intervalo_minimo_segundos": 0,
        }}
        itens = [
            ItemFeed("Quaest: Lula tem 40%", "https://g1.globo.com/a", date(2026, 9, 10)),
            ItemFeed("Receita de bolo", "https://g1.globo.com/b", date(2026, 9, 10)),
            ItemFeed("Pesquisa para governador em SP", "https://g1.globo.com/d", date(2026, 9, 10)),
            ItemFeed("Pesquisa para presidente sem registro", "https://g1.globo.com/c", date(2026, 9, 10)),
        ]
        textos = {
            "https://g1.globo.com/a": "Para presidente. Registro BR-00001/2026.",
            "https://g1.globo.com/d": "Governador. Registro SP-01590/2026.",
            "https://g1.globo.com/c": "Pesquisa para presidente, sem código e sem instituto.",
        }
        stats = coletar_materias(
            conn, config,
            ler_feed_fn=lambda url, ua: itens,
            baixar_fn=lambda url, ua: textos.get(url),
            historico=False,
            pausa=lambda s: None,
        )
        assert stats["vinculadas"] == 1
        assert stats["quarentena"] == 1
        assert conn.execute("SELECT registro_tse, metodo_match FROM materia_pesquisa").fetchall()[0][:] == (
            "BR-00001/2026", "codigo",
        )
