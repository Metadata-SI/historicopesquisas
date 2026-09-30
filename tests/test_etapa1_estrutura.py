"""
Testes de integridade da Etapa 1: Estrutura do projeto, arquivos de configuração e dados de exemplo.
"""

from pathlib import Path
import pytest
import pandas as pd

from modelo.config import carregar_config
from modelo.importar_csv import importar_csv_pesquisas
from modelo.database import get_connection


class TestEtapa1Estrutura:
    def test_pastas_obrigatorias_existem(self):
        pastas = ["coleta", "modelo", "dados", "site", "tests"]
        for pasta in pastas:
            p = Path(pasta)
            assert p.exists() and p.is_dir(), f"Pasta obrigatória {pasta} não encontrada."

    def test_arquivos_principais_existem(self):
        arquivos = [
            "config.yaml",
            "run_pipeline.py",
            "README.md",
            "requirements.txt",
            "dados/schema.sql",
            "dados/schema_postgres.sql",
            "dados/exemplos/pesquisas_ficticias_2026.csv",
        ]
        for arq in arquivos:
            p = Path(arq)
            assert p.exists() and p.is_file(), f"Arquivo essencial {arq} não encontrado."

    def test_config_yaml_conteudo(self):
        config = carregar_config("config.yaml")
        assert "modelo" in config
        assert config["modelo"]["meia_vida_dias"] == 14.0
        assert config["modelo"]["n_bootstraps"] == 2000
        assert "candidatos_monitorados" in config["modelo"]
        assert "Lula" in config["modelo"]["candidatos_monitorados"]
        assert "Flávio Bolsonaro" in config["modelo"]["candidatos_monitorados"]

    def test_csv_ficticio_e_importacao(self, tmp_path):
        csv_exemplo = Path("dados/exemplos/pesquisas_ficticias_2026.csv")
        assert csv_exemplo.exists()

        # Verifica marcação explícita de dado fictício
        df = pd.read_csv(csv_exemplo, comment="#")
        assert "dado_ficticio" in df.columns
        assert (df["dado_ficticio"] == "SIMULADO").all()

        # Testa importação para um banco SQLite temporário
        db_temp = tmp_path / "test_import.db"
        config_temp = {
            "caminhos": {
                "banco_sqlite": str(db_temp),
                "csv_quarentena": str(tmp_path / "quarentena.csv"),
                "dados_exemplos": str(csv_exemplo),
            }
        }
        import yaml
        cfg_file = tmp_path / "config_test.yaml"
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(config_temp, f)

        res = importar_csv_pesquisas(csv_exemplo, caminho_config=cfg_file)
        assert res["pesquisas_processadas"] > 0
        assert res["resultados_processados"] > 0

        # Verifica no banco
        conn = get_connection(db_temp)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pesquisa")
        total_p = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM resultado")
        total_r = cur.fetchone()[0]
        conn.close()

        assert total_p > 0
        assert total_r > 0
