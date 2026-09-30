"""
Testes de integridade do Front-end Estático (Etapa 3):
Verifica existência de arquivos, estrutura do HTML, estilos CSS e dados em site/dados/.
"""

import json
from pathlib import Path
import pytest


class TestSiteEstatico:
    def test_arquivos_frontend_existem(self):
        arquivos = [
            "site/index.html",
            "site/style.css",
            "site/app.js",
            "site/dados/planopolitico.json",
            "site/dados/serie_diaria.json",
            "site/dados/pesquisas_recentes.json",
            "site/dados/tendencia_institutos.json",
        ]
        for arq in arquivos:
            p = Path(arq)
            assert p.exists() and p.is_file(), f"Arquivo do front-end {arq} ausente."

    def test_html_elementos_obrigatorios(self):
        conteudo = Path("site/index.html").read_text(encoding="utf-8")
        
        # Gráficos
        assert 'id="grafico-serie"' in conteudo
        assert 'id="grafico-institutos"' in conteudo
        
        # Alternadores
        assert 'data-turno="1"' in conteudo
        assert 'data-turno="2"' in conteudo
        assert 'data-voto="validos"' in conteudo
        assert 'data-voto="total"' in conteudo
        
        # Tabela e Metodologia
        assert 'id="tabela-corpo"' in conteudo
        assert 'id="tabela-busca"' in conteudo
        assert 'id="sel-territorio"' in conteudo
        assert 'id="mapa-brasil"' in conteudo
        assert 'id="btn-atualizar"' in conteudo
        assert 'id="painel-linhas"' in conteudo
        assert 'id="slider-data"' in conteudo
        assert 'data-cargo="governador"' in conteudo
        assert 'data-cargo="senado"' in conteudo

    def test_jsons_validos_em_site_dados(self):
        p_serie = Path("site/dados/serie_diaria.json")
        p_pesq = Path("site/dados/pesquisas_recentes.json")
        p_inst = Path("site/dados/tendencia_institutos.json")

        with open(p_serie, "r", encoding="utf-8") as f:
            d_serie = json.load(f)
            assert "turno_1" in d_serie
            assert "turno_2" in d_serie

        with open(p_pesq, "r", encoding="utf-8") as f:
            d_pesq = json.load(f)
            assert "pesquisas" in d_pesq
            assert d_pesq["total_pesquisas"] > 0

        with open(p_inst, "r", encoding="utf-8") as f:
            d_inst = json.load(f)
            assert "institutos" in d_inst
