"""
Testes da carga de registros oficiais do TSE (coleta/tse_oficial.py), sem acesso à rede.
"""

import zipfile
from pathlib import Path

import pytest

from coleta.tse_oficial import (
    atualizar_base_tse,
    conferir_pesquisas_com_tse,
    ler_registros_zip,
    salvar_registros_oficiais,
)
from modelo.database import (
    get_connection,
    init_db,
    salvar_instituto,
    salvar_pesquisa,
)
from modelo.validador import normalizar_registro_tse

CABECALHO = (
    "NR_PROTOCOLO_REGISTRO;SG_UF;DS_CARGO;NR_CNPJ_EMPRESA;NM_EMPRESA;NM_EMPRESA_FANTASIA;"
    "DT_REGISTRO;DT_INICIO_PESQUISA;DT_FIM_PESQUISA;DT_DIVULGACAO;QT_ENTREVISTADO;"
    "VR_PESQUISA;DS_METODOLOGIA_PESQUISA;DS_PLANO_AMOSTRAL;ST_PESQUISA_PROPRIA"
)
LINHAS = [
    "BR079722026;BR;Presidente;111;ATLAS INTEL LTDA;ATLASINTEL;2026-08-25 10:00:00;"
    "2026-08-26 00:00:00;2026-08-30 00:00:00;2026-08-31 00:00:00;5000;95.000,50;Metodo A;Plano A;N",
    "BR036902026;BR;Presidente;222;IPEMS INSTITUTO LTDA;#NULO#;2026-09-22 19:05:03;"
    "2026-09-22 00:00:00;2026-09-27 00:00:00;2026-09-28 00:00:00;820;40000,00;Metodo B;Plano B;S",
    "SP012342026;SP;Governador;333;OUTRA LTDA;OUTRA;2026-09-01 00:00:00;"
    "2026-09-01 00:00:00;2026-09-02 00:00:00;2026-09-03 00:00:00;900;1000,00;M;P;N",
    "XX-invalido;BR;Presidente;444;RUIM LTDA;RUIM;2026-09-01 00:00:00;"
    "2026-09-01 00:00:00;2026-09-02 00:00:00;2026-09-03 00:00:00;900;1000,00;M;P;N",
]


@pytest.fixture
def zip_tse(tmp_path: Path) -> Path:
    caminho = tmp_path / "pesquisa_eleitoral_2026.zip"
    conteudo = "\n".join([CABECALHO, *LINHAS]) + "\n"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("pesquisa_eleitoral_2026_BRASIL.csv", conteudo.encode("latin1"))
    return caminho


@pytest.fixture
def conn(tmp_path: Path):
    db = tmp_path / "t.db"
    init_db(db, "dados/schema.sql")
    c = get_connection(db)
    yield c
    c.close()


class TestNormalizacao:
    @pytest.mark.parametrize("entrada", ["BR079722026", "BR-07972/2026", " br-07972/2026 ", "BR 07972 2026"])
    def test_formatos_aceitos(self, entrada):
        assert normalizar_registro_tse(entrada) == "BR-07972/2026"

    @pytest.mark.parametrize("entrada", ["", None, "XX-invalido", "BR-7972/2026", "07972/2026"])
    def test_formatos_rejeitados(self, entrada):
        assert normalizar_registro_tse(entrada) is None


class TestLeituraZip:
    def test_filtra_cargo_uf_e_protocolo_invalido(self, zip_tse):
        regs = ler_registros_zip(zip_tse, 2026)
        assert [r["registro_tse"] for r in regs] == ["BR-07972/2026", "BR-03690/2026"]

    def test_campos_convertidos(self, zip_tse):
        atlas = ler_registros_zip(zip_tse, 2026)[0]
        assert atlas["amostra"] == 5000
        assert atlas["valor"] == 95000.50
        assert atlas["data_fim"] == "2026-08-30"
        assert atlas["empresa_nome"] == "ATLASINTEL"
        assert atlas["pesquisa_propria"] is False

    def test_nulo_usa_razao_social(self, zip_tse):
        ipems = ler_registros_zip(zip_tse, 2026)[1]
        assert ipems["empresa_nome"] == "IPEMS INSTITUTO LTDA"
        assert ipems["pesquisa_propria"] is True

    def test_csv_ausente(self, tmp_path):
        vazio = tmp_path / "x.zip"
        with zipfile.ZipFile(vazio, "w") as z:
            z.writestr("outro.csv", "a;b\n")
        with pytest.raises(FileNotFoundError):
            ler_registros_zip(vazio, 2026)


class TestPersistencia:
    def test_salvar_e_atualizar_sao_idempotentes(self, conn, zip_tse):
        regs = ler_registros_zip(zip_tse, 2026)
        salvar_registros_oficiais(conn, regs)
        regs[0]["amostra"] = 5001
        salvar_registros_oficiais(conn, regs)

        n = conn.execute("SELECT COUNT(*) FROM registro_tse_oficial").fetchone()[0]
        amostra = conn.execute(
            "SELECT amostra FROM registro_tse_oficial WHERE registro_tse='BR-07972/2026'"
        ).fetchone()[0]
        assert n == 2
        assert amostra == 5001

    def test_atualizar_base_usa_download(self, conn, zip_tse, monkeypatch):
        monkeypatch.setattr("coleta.tse_oficial.baixar_zip_tse", lambda ano, destino: zip_tse)
        assert atualizar_base_tse(conn, 2026) == 2


class TestConferencia:
    def _pesquisa(self, conn, registro, amostra, inicio, fim):
        inst = salvar_instituto(conn, "Inst")
        salvar_pesquisa(conn, inst, registro, inicio, fim, amostra)
        conn.commit()

    def test_pesquisa_conferida_sem_problemas(self, conn, zip_tse):
        salvar_registros_oficiais(conn, ler_registros_zip(zip_tse, 2026))
        self._pesquisa(conn, "BR-07972/2026", 5000, "2026-08-26", "2026-08-30")
        assert conferir_pesquisas_com_tse(conn) == []

    def test_detecta_registro_inexistente(self, conn, zip_tse):
        salvar_registros_oficiais(conn, ler_registros_zip(zip_tse, 2026))
        self._pesquisa(conn, "BR-99999/2026", 1000, "2026-08-26", "2026-08-30")
        assert conferir_pesquisas_com_tse(conn) == [
            {"registro_tse": "BR-99999/2026", "problema": "inexistente no TSE"}
        ]

    def test_detecta_divergencia_de_amostra(self, conn, zip_tse):
        salvar_registros_oficiais(conn, ler_registros_zip(zip_tse, 2026))
        self._pesquisa(conn, "BR-07972/2026", 5005, "2026-08-26", "2026-08-30")
        probs = conferir_pesquisas_com_tse(conn)
        assert len(probs) == 1
        assert probs[0]["problema"] == "amostra diverge"
        assert (probs[0]["local"], probs[0]["tse"]) == (5005, 5000)
