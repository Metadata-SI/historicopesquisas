"""
Testes unitários para o módulo de validação de pesquisas (modelo/validador.py).
"""

import pytest
from modelo.validador import (
    validar_registro_tse,
    validar_amostra,
    validar_datas,
    validar_soma_percentuais,
)


class TestValidador:
    def test_registro_tse_valido(self):
        val1 = validar_registro_tse("BR-00001/2026")
        assert val1.valido is True
        assert val1.motivo is None

        val2 = validar_registro_tse("SP-98765/2026")
        assert val2.valido is True

    def test_registro_tse_invalido(self):
        assert validar_registro_tse("").valido is False
        assert validar_registro_tse("BR-123/2026").valido is False
        assert validar_registro_tse("BR000012026").valido is False
        assert validar_registro_tse("12345/2026").valido is False
        assert validar_registro_tse(None).valido is False

    def test_validar_amostra(self):
        assert validar_amostra(2000).valido is True
        assert validar_amostra("1500").valido is True
        assert validar_amostra(50).valido is False
        assert validar_amostra(0).valido is False
        assert validar_amostra(-100).valido is False
        assert validar_amostra("abc").valido is False

    def test_validar_datas(self):
        assert validar_datas("2026-03-01", "2026-03-03").valido is True
        assert validar_datas("2026-03-03", "2026-03-03").valido is True
        assert validar_datas("2026-03-05", "2026-03-02").valido is False
        assert validar_datas("", "2026-03-02").valido is False

    def test_validar_soma_percentuais(self):
        # Soma 100%
        assert validar_soma_percentuais([38.0, 30.0, 10.0, 10.0, 12.0]).valido is True
        # Soma 98% (aceitável com margem de arredondamento)
        assert validar_soma_percentuais([38.0, 30.0, 10.0, 20.0]).valido is True
        # Soma muito baixa (< 90%)
        assert validar_soma_percentuais([30.0, 20.0]).valido is False
        # Soma muito alta (> 105%)
        assert validar_soma_percentuais([60.0, 50.0]).valido is False
