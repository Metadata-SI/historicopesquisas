"""
Testes unitários para o modelo estatístico de agregação eleitoral (Etapa 2):
- Decaimento temporal e pesos de amostra
- Efeitos de instituto (House Effects)
- Reamostragem bootstrap não-paramétrica
- Normalização de votos válidos
- Geração dos arquivos JSON de saída
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from modelo.bootstrap import calcular_intervalo_bootstrap
from modelo.house_effects import (
    aplicar_ajuste_house_effects,
    calcular_house_effects,
    gerar_relatorio_institutos,
)
from modelo.pesos import (
    calcular_peso_amostra,
    calcular_peso_temporal,
    calcular_pesos_compostos,
)
from modelo.votos_validos import converter_para_votos_validos
from modelo.agregador import (
    calcular_serie_temporal,
    executar_pipeline_modelo,
    estruturar_pesquisas_recentes,
)
from modelo.database import init_db, get_connection
from modelo.importar_csv import importar_csv_pesquisas


class TestPesos:
    def test_decaimento_temporal_meia_vida(self):
        # delta = 0 -> peso 1.0
        assert pytest.approx(calcular_peso_temporal(0, meia_vida_dias=14.0), 0.001) == 1.0
        
        # delta = 14 dias (meia-vida) -> peso 0.5
        assert pytest.approx(calcular_peso_temporal(14, meia_vida_dias=14.0), 0.001) == 0.5
        
        # delta = 28 dias (duas meias-vidas) -> peso 0.25
        assert pytest.approx(calcular_peso_temporal(28, meia_vida_dias=14.0), 0.001) == 0.25
        
        # delta negativo (pesquisa no futuro em relação ao corte) -> peso 0.0
        assert calcular_peso_temporal(-2, meia_vida_dias=14.0) == 0.0

    def test_peso_amostra_raiz_quadrada(self):
        # Amostra 100 -> raiz = 10
        assert pytest.approx(calcular_peso_amostra(100), 0.001) == 10.0
        # Amostra 2500 -> raiz = 50
        assert pytest.approx(calcular_peso_amostra(2500), 0.001) == 50.0
        # Amostra inválida <= 0
        assert calcular_peso_amostra(0) == 0.0
        assert calcular_peso_amostra(-500) == 0.0


class TestVotosValidos:
    def test_renormalizacao_votos_validos(self):
        df_cenario = pd.DataFrame([
            {"cenario_id": 1, "candidato": "Lula", "percentual": 40.0},
            {"cenario_id": 1, "candidato": "Flávio Bolsonaro", "percentual": 30.0},
            {"cenario_id": 1, "candidato": "Branco/Nulo", "percentual": 10.0},
            {"cenario_id": 1, "candidato": "Indeciso/Não Sabe", "percentual": 20.0},
        ])
        nao_validos = ["Branco/Nulo", "Indeciso/Não Sabe"]
        
        df_val = converter_para_votos_validos(df_cenario, nao_validos)
        
        # Apenas candidatos válidos devem permanecer
        assert set(df_val["candidato"].tolist()) == {"Lula", "Flávio Bolsonaro"}
        
        # Total de válidos original = 40 + 30 = 70%
        # Lula: 40 / 70 * 100 = 57.14%
        # Flávio: 30 / 70 * 100 = 42.86%
        lula_val = df_val.loc[df_val["candidato"] == "Lula", "percentual"].iloc[0]
        flavio_val = df_val.loc[df_val["candidato"] == "Flávio Bolsonaro", "percentual"].iloc[0]
        
        assert pytest.approx(lula_val, 0.02) == 57.14
        assert pytest.approx(flavio_val, 0.02) == 42.86
        assert pytest.approx(lula_val + flavio_val, 0.02) == 100.0


class TestBootstrap:
    def test_bootstrap_consistencia_limites(self):
        valores = np.array([38.0, 39.0, 37.0, 40.0])
        pesos = np.array([1.0, 1.2, 0.8, 1.1])
        amostras = np.array([2000, 2000, 2000, 2000])
        
        media, ic_inf, ic_sup = calcular_intervalo_bootstrap(
            valores, pesos, amostras=amostras, n_bootstraps=1000, seed=42
        )
        
        # Limite inferior <= média <= limite superior
        assert ic_inf <= media
        assert media <= ic_sup
        # Valores razoáveis na vizinhança da média
        assert 35.0 <= ic_inf <= 39.0
        assert 38.0 <= ic_sup <= 42.0

    def test_bootstrap_pesquisa_unica(self):
        valores = np.array([45.0])
        pesos = np.array([1.0])
        margens = np.array([2.0])
        
        media, ic_inf, ic_sup = calcular_intervalo_bootstrap(
            valores, pesos, margens_erro=margens, n_bootstraps=500, seed=42
        )
        
        assert media == 45.0
        assert ic_inf < media
        assert ic_sup > media


class TestHouseEffects:
    def test_house_effects_identificacao_vies(self):
        # Cria dados onde Instituto A pontua consistentemente +4% acima dos demais
        datas = pd.date_range("2026-03-01", periods=6, freq="10D")
        linhas = []
        for i, dt in enumerate(datas):
            dt_str = dt.strftime("%Y-%m-%d")
            # Instituto A (6 pesquisas -> atinge o limiar de 5)
            linhas.append({
                "pesquisa_id": i * 2 + 1,
                "instituto_nome": "Instituto A",
                "data_fim": dt_str,
                "candidato": "Lula",
                "percentual": 44.0
            })
            # Instituto B (outros institutos na mesma janela)
            linhas.append({
                "pesquisa_id": i * 2 + 2,
                "instituto_nome": "Instituto B",
                "data_fim": dt_str,
                "candidato": "Lula",
                "percentual": 40.0
            })
            
        df = pd.DataFrame(linhas)
        effects = calcular_house_effects(df, min_pesquisas=5, janela_dias=15)
        
        # Instituto A deve ter viés positivo de aproximadamente +4.0
        assert "Instituto A" in effects
        vies_a = effects["Instituto A"].get("Lula", 0.0)
        assert pytest.approx(vies_a, 0.1) == 4.0
        
        # Aplicação do ajuste: 44.0 - 4.0 = 40.0
        df_ajustado = aplicar_ajuste_house_effects(df, effects)
        val_ajustado = df_ajustado.loc[df_ajustado["instituto_nome"] == "Instituto A", "percentual_ajustado"].iloc[0]
        assert pytest.approx(val_ajustado, 0.1) == 40.0


class TestPipelineModeloIntegracao:
    def test_executar_pipeline_completo(self, tmp_path):
        db_path = tmp_path / "test_agregador.db"
        json_serie = tmp_path / "serie_diaria.json"
        json_pesquisas = tmp_path / "pesquisas_recentes.json"
        json_inst = tmp_path / "tendencia_institutos.json"

        # Config temporária
        import yaml
        cfg = {
            "caminhos": {
                "banco_sqlite": str(db_path),
                "dados_exemplos": "dados/exemplos/pesquisas_ficticias_2026.csv",
                "saida_json_serie": str(json_serie),
                "saida_json_pesquisas": str(json_pesquisas),
                "saida_json_institutos": str(json_inst),
            },
            "modelo": {
                "meia_vida_dias": 14.0,
                "data_inicio_serie": "2026-03-01",
                "n_bootstraps": 500,  # Reduzido para rapidez no teste
                "intervalo_confianca": {"percentil_inferior": 2.5, "percentil_superior": 97.5},
                "peso_amostra_habilitado": True,
                "house_effects": {"habilitado": True, "min_pesquisas_instituto": 5},
                "categorias_nao_validas": ["Branco/Nulo", "Indeciso/Não Sabe"],
                "candidatos_monitorados": ["Lula", "Flávio Bolsonaro"]
            }
        }
        cfg_file = tmp_path / "config_teste.yaml"
        with open(cfg_file, "w", encoding="utf-8") as f:
            yaml.dump(cfg, f)

        # Importa dados de exemplo
        init_db(db_path)
        importar_csv_pesquisas("dados/exemplos/pesquisas_ficticias_2026.csv", caminho_config=cfg_file)

        # Executa o modelo
        res = executar_pipeline_modelo(caminho_config=cfg_file)
        assert res["sucesso"] is True
        assert res["total_pesquisas"] > 0

        # Valida existência e estrutura dos JSONs
        assert json_serie.exists()
        assert json_pesquisas.exists()
        assert json_inst.exists()

        with open(json_serie, "r", encoding="utf-8") as f:
            serie_data = json.load(f)
            assert "turno_1" in serie_data
            assert "total" in serie_data["turno_1"]
            assert "validos" in serie_data["turno_1"]
            assert len(serie_data["turno_1"]["total"]) > 0

        with open(json_pesquisas, "r", encoding="utf-8") as f:
            pesq_data = json.load(f)
            assert "pesquisas" in pesq_data
            assert len(pesq_data["pesquisas"]) > 0

        with open(json_inst, "r", encoding="utf-8") as f:
            inst_data = json.load(f)
            assert "institutos" in inst_data
