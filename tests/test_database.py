"""
Testes unitários para o banco de dados SQLite e consultas analíticas (modelo/database.py).
"""

import tempfile
from pathlib import Path
import pytest
import sqlite3

from modelo.database import (
    get_connection,
    init_db,
    salvar_instituto,
    salvar_pesquisa,
    salvar_cenario,
    salvar_resultado,
    salvar_fonte,
    carregar_pesquisas_completas,
)


@pytest.fixture
def temp_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        schema_path = Path("dados/schema.sql")
        init_db(db_path, schema_path)
        yield db_path


class TestDatabase:
    def test_schema_inicializacao(self, temp_db):
        conn = get_connection(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tabelas = {row["name"] for row in cursor.fetchall()}
        conn.close()

        assert "instituto" in tabelas
        assert "pesquisa" in tabelas
        assert "cenario" in tabelas
        assert "resultado" in tabelas
        assert "fonte" in tabelas
        assert "quarentena" in tabelas

    def test_insercao_e_relacionamentos(self, temp_db):
        conn = get_connection(temp_db)
        
        # 1. Inserir instituto
        inst_id = salvar_instituto(conn, "Datafolha", peso=1.0)
        assert inst_id > 0

        # 2. Inserir pesquisa
        pesq_id = salvar_pesquisa(
            conn=conn,
            instituto_id=inst_id,
            registro_tse="BR-00001/2026",
            data_inicio="2026-03-01",
            data_fim="2026-03-03",
            amostra=2000,
            margem_erro=2.2
        )
        assert pesq_id > 0

        # 3. Inserir cenários (1º turno e 2º turno)
        cen1_id = salvar_cenario(conn, pesq_id, turno=1, cenario="Estimulada 1")
        cen2_id = salvar_cenario(conn, pesq_id, turno=2, cenario="2º Turno - Lula x Tarcísio")
        assert cen1_id > 0
        assert cen2_id > 0

        # 4. Inserir resultados
        salvar_resultado(conn, cen1_id, "Lula", 38.0)
        salvar_resultado(conn, cen1_id, "Tarcísio de Freitas", 30.0)
        salvar_resultado(conn, cen1_id, "Branco/Nulo", 10.0)

        # 5. Inserir fonte
        fonte_id = salvar_fonte(conn, pesq_id, "https://g1.globo.com/teste", "g1")
        assert fonte_id > 0

        # 6. Carregar via DataFrame consolidado
        df = carregar_pesquisas_completas(conn, cargo="Presidente", uf="BR", turno=1)
        conn.close()

        assert len(df) == 3
        assert "Lula" in df["candidato"].values
        assert "Tarcísio de Freitas" in df["candidato"].values
        assert df["instituto_nome"].iloc[0] == "Datafolha"
