"""Testes do coletor do Plano Político (sem acessar a internet)."""

import json

import pytest

from coleta import planopolitico

DADOS = {"presidente_t1": {}, "presidente_t2": {}, "presidente_state": {"states": {}}}


def _html(dados):
    return f'<html><script id="agg-data" type="application/json">{json.dumps(dados)}</script></html>'


def test_extrai_json_embutido():
    assert planopolitico.extrair_dados(_html(DADOS)) == DADOS


def test_layout_sem_bloco_falha_com_mensagem_clara():
    with pytest.raises(ValueError, match="agg-data"):
        planopolitico.extrair_dados("<html></html>")


def test_bloco_sem_campos_esperados_falha():
    with pytest.raises(ValueError, match="presidente_t2"):
        planopolitico.extrair_dados(_html({"presidente_t1": {}}))


def test_extrai_bloco_de_cargo():
    html = f'<script id="agg-data" type="application/json">{json.dumps({"senado": {"states": {"RN": {}}}})}</script>'
    assert planopolitico._extrair_cargo(html, "senado") == {"states": {"RN": {}}}


def test_cargo_ausente_falha():
    html = '<script id="agg-data" type="application/json">{}</script>'
    with pytest.raises(ValueError, match="governador"):
        planopolitico._extrair_cargo(html, "governador")
