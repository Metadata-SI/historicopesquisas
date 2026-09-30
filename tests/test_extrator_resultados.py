"""
Testes da extração de percentuais (coleta/extrator_resultados.py), sem acesso à rede.
Os textos reproduzem o formato real das matérias do g1 de 29/09/2026.
"""

import json
from pathlib import Path

import pytest

from coleta.extrator_resultados import (
    detectar_abrangencia,
    extrair_cenarios,
    extrair_e_gravar,
    segmentar_blocos,
)
from coleta.tse_oficial import salvar_registros_oficiais
from modelo.database import get_connection, init_db

CANDIDATOS = {"Lula", "Flávio Bolsonaro", "Ronaldo Caiado", "Romeu Zema", "Augusto Cury", "Renan Santos"}
CONFIG = {
    "coleta": {"institutos": [
        {"nome": "Quaest", "texto": ["quaest"], "tse": ["QUAEST"]},
        {"nome": "Paraná Pesquisas", "texto": ["paraná pesquisas", "parana pesquisas"], "tse": ["INSTITUTO PARANA"]},
    ]},
    "modelo": {"candidatos_monitorados": sorted(CANDIDATOS)},
    "validacao": {"min_soma_percentual": 90.0, "max_soma_percentual": 105.0},
}

BLOCO_1T = """- Flávio Bolsonaro (PL): 38% (eram 33%)
- Lula (PT): 32% (eram 32%)
- Ronaldo Caiado (PSD): 8% (eram 8%)
- Escritor Augusto Cury (Avante): 5% (eram 7%)
- Renan Santos (Missão): 3% (eram 3%)
- Romeu Zema (Novo): 0% (eram 1%)
- Branco/nulo/não vai votar: 6% (eram 8%)
- Indecisos: 8% (eram 8%)"""

BLOCO_2T = """- Flávio Bolsonaro (PL): 48% (eram 49%)
- Lula (PT): 37% (eram 38%)
- Branco/nulo/não vai votar: 12% (eram 11%)
- Indecisos: 3% (eram 1%)"""

MATERIA_DF = f"""Pesquisa Quaest mostra a disputa pela Presidência entre os eleitores do Distrito Federal.
Veja, abaixo, os resultados da pesquisa estimulada:
{BLOCO_1T}
Para 86% dos eleitores ouvidos, a escolha é definitiva.
A Quaest ouviu 1.104 pessoas entre os dias 25 e 28 de setembro. Os números de registro são DF-02515/2026 e BR-00531/2026.
Segundo turno
Pela terceira vez, a Quaest questionou os eleitores do Distrito Federal sobre o segundo turno.
{BLOCO_2T}
Maior 'medo' na eleição
- Mais um mandato de Lula: 49% (eram 46%)
- A volta da família Bolsonaro ao poder: 37% (eram 39%)
"""


def _reg(codigo, amostra, empresa="QUAEST PESQUISAS LTDA", divulgacao="2026-09-29"):
    return {
        "registro_tse": codigo, "protocolo_original": codigo, "uf": "BR", "cargo": "Presidente",
        "empresa_cnpj": None, "empresa_nome": empresa, "data_registro": None,
        "data_inicio": "2026-09-25", "data_fim": "2026-09-28", "data_divulgacao": divulgacao,
        "amostra": amostra, "valor": None, "metodologia": "Metodo", "plano_amostral": None,
        "pesquisa_propria": False,
    }


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "t.db"
    init_db(db, "dados/schema.sql")
    c = get_connection(db)
    salvar_registros_oficiais(c, [
        _reg("BR-00531/2026", 1104), _reg("BR-05155/2026", 1800),
        _reg("BR-08467/2026", 1506), _reg("BR-03534/2026", 1302),
    ])
    yield c
    c.close()


class TestExtracaoDeCenarios:
    def test_primeiro_turno(self):
        cen = extrair_cenarios(MATERIA_DF, CANDIDATOS)
        c1 = cen[0]
        assert (c1.turno, c1.nome) == (1, "Estimulada 1")
        assert c1.resultados["Augusto Cury"] == 5.0  # prefixo "Escritor" removido
        assert c1.resultados["Branco/Nulo"] == 6.0
        assert c1.resultados["Indeciso/Não Sabe"] == 8.0
        assert round(sum(c1.resultados.values())) == 100

    def test_segundo_turno(self):
        c2 = extrair_cenarios(MATERIA_DF, CANDIDATOS)[1]
        assert c2.turno == 2
        assert c2.nome == "2º Turno - Flávio Bolsonaro x Lula"

    def test_lista_de_medo_e_ignorada(self):
        assert len(extrair_cenarios(MATERIA_DF, CANDIDATOS)) == 2

    def test_bloco_de_governador_e_ignorado(self):
        texto = "- Tarcísio de Freitas (Republicanos): 44%\n- Fernando Haddad (PT): 24%\n- Indecisos: 16%"
        assert extrair_cenarios(texto, CANDIDATOS) == []

    def test_item_sem_numero_nao_quebra_o_bloco(self):
        texto = (
            "- Flávio Bolsonaro (PL): 36%\n- Lula (PT): 30%\n- Renan Santos (Missão): 3%\n"
            "- Veterinário Wilson Grassi (Democrata): % (era 0%)\n- Indecisos: 12%\n- Branco/nulo: 9%"
        )
        blocos = segmentar_blocos(texto)
        assert len(blocos) == 1
        cen = extrair_cenarios(texto, CANDIDATOS)
        assert len(cen) == 1 and "sem percentual legível" in cen[0].erro

    def test_virgula_decimal(self):
        texto = "- Lula (PT): 40,5%\n- Flávio Bolsonaro (PL): 35,5%\n- Ronaldo Caiado (PSD): 4%\n- Indecisos: 10%\n- Branco/nulo: 10%"
        assert extrair_cenarios(texto, CANDIDATOS)[0].resultados["Lula"] == 40.5


class TestAbrangencia:
    def _bloco(self, antes="", depois=""):
        return segmentar_blocos(f"{antes}\n- Lula (PT): 40%\n- Flávio Bolsonaro (PL): 40%\n{depois}")[0]

    def test_estadual_pelo_titulo(self):
        assert detectar_abrangencia("Quaest em PE: Lula, 58%", "https://g1.globo.com/x", set(), self._bloco()) == "PE"

    def test_estadual_pela_url(self):
        url = "https://g1.globo.com/df/distrito-federal/eleicoes/x.ghtml"
        assert detectar_abrangencia("Quaest: Lula, 40%", url, set(), self._bloco()) == "DF"

    def test_estadual_por_codigo_de_uf(self):
        assert detectar_abrangencia("Quaest", "https://x/", {"SP-01590/2026", "BR-00001/2026"}, self._bloco()) == "SP"

    def test_nacional(self):
        assert detectar_abrangencia("Quaest, 1º turno: Lula tem 39%", "https://g1.globo.com/politica/x", set(), self._bloco()) == "BR"

    def test_para_preposicao_nao_e_o_estado_pará(self):
        titulo = "Pesquisa para presidente: Lula vence"
        assert detectar_abrangencia(titulo, "https://x/", set(), self._bloco("Veja os números para o 1º turno")) == "BR"

    def test_nome_de_instituto_nao_e_estado(self):
        assert detectar_abrangencia(
            "Paraná Pesquisas: Lula 40%", "https://x/", set(), self._bloco(), ["paraná pesquisas"]
        ) == "BR"

    def test_titulo_do_bloco_prevalece_sobre_titulo_da_materia(self):
        bloco = self._bloco(antes="São Paulo: Flávio Bolsonaro 36% x 30% Lula")
        assert detectar_abrangencia("Quaest: Flávio lidera no RJ e em SP", "https://x/", set(), bloco) == "SP"

    def test_sinais_conflitantes_sao_indefinidos(self):
        assert detectar_abrangencia("Quaest em PE e em SP", "https://x/", set(), self._bloco()) == "INDEFINIDA"


class TestGravacao:
    def _rodar(self, conn, texto, titulo="Quaest no DF: Flávio, 38%", url="https://g1.globo.com/df/distrito-federal/a.ghtml"):
        return extrair_e_gravar(conn, CONFIG, "g1", url, titulo, texto)

    def test_grava_com_dados_do_tse(self, conn):
        stats = self._rodar(conn, MATERIA_DF)
        assert stats == {"cenarios_gravados": 2, "cenarios_quarentena": 0}
        p = conn.execute("SELECT uf, amostra, data_fim, instituto_id FROM pesquisa").fetchone()
        assert (p["uf"], p["amostra"], p["data_fim"]) == ("DF", 1104, "2026-09-28")  # amostra/data do TSE
        assert conn.execute("SELECT nome FROM instituto").fetchone()["nome"] == "Quaest"
        assert conn.execute("SELECT COUNT(*) FROM fonte").fetchone()[0] == 1

    def test_pesquisa_estadual_fica_fora_do_modelo_nacional(self, conn):
        from modelo.database import carregar_pesquisas_completas
        self._rodar(conn, MATERIA_DF)
        assert carregar_pesquisas_completas(conn, uf="BR").empty
        assert not carregar_pesquisas_completas(conn, uf="DF").empty

    def test_amostra_diferente_do_tse_vai_para_quarentena_com_sugestao(self, conn):
        # Caso real: matéria de MG (1.506) citou o código de SP (BR-05155, 1.800).
        texto = MATERIA_DF.replace("1.104", "1.506").replace("BR-00531/2026", "BR-05155/2026")
        stats = self._rodar(conn, texto)
        assert stats["cenarios_gravados"] == 0 and stats["cenarios_quarentena"] == 2
        q = conn.execute("SELECT motivo_rejeicao, dados_brutos_json FROM quarentena").fetchone()
        assert "difere do TSE" in q["motivo_rejeicao"]
        assert json.loads(q["dados_brutos_json"])["registro_sugerido_pela_amostra"] == ["BR-08467/2026"]
        assert conn.execute("SELECT COUNT(*) FROM pesquisa").fetchone()[0] == 0

    def test_sem_amostra_na_materia_nao_grava(self, conn):
        stats = self._rodar(conn, MATERIA_DF.replace("1.104 pessoas", "vários eleitores"))
        assert stats["cenarios_gravados"] == 0 and stats["cenarios_quarentena"] == 2

    def test_registro_inexistente_no_tse(self, conn):
        stats = self._rodar(conn, MATERIA_DF.replace("BR-00531/2026", "BR-77777/2026"))
        assert stats["cenarios_gravados"] == 0
        assert "inexistente" in conn.execute("SELECT motivo_rejeicao FROM quarentena").fetchone()[0]

    def test_sem_codigo_br_nao_faz_nada(self, conn):
        stats = self._rodar(conn, MATERIA_DF.replace("BR-00531/2026", ""))
        assert stats == {"cenarios_gravados": 0, "cenarios_quarentena": 0}
        assert conn.execute("SELECT COUNT(*) FROM quarentena").fetchone()[0] == 0

    def test_soma_fora_da_faixa(self, conn):
        texto = MATERIA_DF.replace("Indecisos: 8%", "Indecisos: 40%")
        stats = self._rodar(conn, texto)
        assert stats["cenarios_gravados"] == 1  # só o 2º turno
        assert "Soma dos percentuais" in conn.execute("SELECT motivo_rejeicao FROM quarentena").fetchone()[0]

    def test_mesma_materia_duas_vezes_e_idempotente(self, conn):
        self._rodar(conn, MATERIA_DF)
        stats = self._rodar(conn, MATERIA_DF)
        assert stats["cenarios_gravados"] == 2
        assert conn.execute("SELECT COUNT(*) FROM pesquisa").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM cenario").fetchone()[0] == 2

    def test_numeros_diferentes_em_outra_materia_sao_conflito(self, conn):
        self._rodar(conn, MATERIA_DF)
        stats = self._rodar(conn, MATERIA_DF.replace("Lula (PT): 32%", "Lula (PT): 30%").replace("Indecisos: 8%", "Indecisos: 10%"),
                            url="https://g1.globo.com/df/distrito-federal/b.ghtml")
        assert stats["cenarios_quarentena"] == 1
        assert "contradiz" in conn.execute("SELECT motivo_rejeicao FROM quarentena").fetchone()[0]
        lula = conn.execute("SELECT percentual FROM resultado WHERE candidato='Lula' AND percentual IN (30, 32) ORDER BY id LIMIT 1").fetchone()[0]
        assert lula == 32.0  # o valor original foi preservado

    def test_resumo_sem_zerados_nao_conflita_com_materia_completa(self, conn):
        completa = MATERIA_DF
        resumo = MATERIA_DF.replace("- Romeu Zema (Novo): 0% (eram 1%)\n", "")
        self._rodar(conn, resumo)
        stats = self._rodar(conn, completa, url="https://g1.globo.com/df/distrito-federal/b.ghtml")
        assert stats["cenarios_quarentena"] == 0
        assert conn.execute("SELECT COUNT(*) FROM resultado WHERE candidato='Romeu Zema'").fetchone()[0] == 1

    def test_resumo_com_varios_codigos_usa_o_codigo_de_cada_bloco(self, conn):
        resumo = (
            "Pesquisas Quaest mostram a corrida em SP e MG.\n"
            "São Paulo: Flávio Bolsonaro 36% x 30% Lula\n"
            "- Flávio Bolsonaro (PL): 36% (eram 34%)\n- Lula (PT): 30% (eram 31%)\n"
            "- Augusto Cury (Avante): 5% (eram 7%)\n- Ronaldo Caiado (PSD): 4% (eram 4%)\n"
            "- Renan Santos (Missão): 3% (eram 3%)\n- Romeu Zema (Novo): 1% (era 1%)\n"
            "- Indecisos: 12% (eram 11%)\n- Em branco/nulo/não vai votar: 9% (eram 9%)\n"
            "Foram entrevistadas 1.800 pessoas em São Paulo. A pesquisa foi registrada sob o número BR-05155/2026.\n"
            "Minas Gerais: Lula 35% x 31% Flávio Bolsonaro\n"
            "- Lula (PT): 35% (eram 35%)\n- Flávio Bolsonaro (PL): 31% (eram 30%)\n"
            "- Augusto Cury (Avante): 5% (eram 5%)\n- Ronaldo Caiado (PSD): 3% (eram 4%)\n"
            "- Renan Santos (Missão): 3% (eram 2%)\n- Romeu Zema (Novo): 3% (eram 2%)\n"
            "- Indecisos: 14% (eram 13%)\n- Branco/nulo/não vai votar: 6% (eram 9%)\n"
            "Foram entrevistadas 1.506 pessoas em Minas Gerais. A pesquisa foi registrada sob o número BR-05155/2026.\n"
        )
        stats = extrair_e_gravar(conn, CONFIG, "g1", "https://g1.globo.com/politica/r.ghtml",
                                 "Quaest: Flávio lidera em SP e Lula em MG", resumo)
        # SP confere (1.800); MG cita o código de SP com amostra 1.506 e é rejeitado.
        assert stats == {"cenarios_gravados": 1, "cenarios_quarentena": 1}
        assert conn.execute("SELECT uf FROM pesquisa").fetchone()["uf"] == "SP"
