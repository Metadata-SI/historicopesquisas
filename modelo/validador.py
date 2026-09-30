"""
Módulo de Validação de Dados de Pesquisas Eleitorais.
Aplica regras estritas antes da inserção no banco de dados e no modelo:
1. Formato do registro TSE (UF-NNNNN/AAAA).
2. Validação da amostra (> 0).
3. Coerência dos percentuais (soma entre 90% e 105%).
4. Coerência das datas (data_fim >= data_inicio).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class ResultadoValidacao:
    valido: bool
    motivo: Optional[str] = None


def normalizar_registro_tse(registro: str) -> Optional[str]:
    """
    Converte o protocolo do TSE para a forma canônica UF-NNNNN/AAAA.
    Aceita 'BR079722026' (dados abertos), 'BR-07972/2026' e variações de caixa/espaço.
    Retorna None se não reconhecer o formato.
    """
    if not registro or not isinstance(registro, str):
        return None
    bruto = re.sub(r"[\s\-/]", "", registro.strip().upper())
    m = re.match(r"^([A-Z]{2})(\d{5})(\d{4})$", bruto)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}/{m.group(3)}"


def validar_registro_tse(registro: str, padrao: str = r"^[A-Z]{2}-\d{5}/\d{4}$") -> ResultadoValidacao:
    """
    Valida se o registro no TSE obedece à máscara padrão UF-NNNNN/AAAA.
    Exemplo: BR-00001/2026, SP-12345/2026.
    """
    if not registro or not isinstance(registro, str):
        return ResultadoValidacao(False, "Registro TSE ausente ou não é texto")
    
    registro_limpo = registro.strip().upper()
    if not re.match(padrao, registro_limpo):
        return ResultadoValidacao(
            False,
            f"Registro TSE '{registro}' não obedece ao padrão '{padrao}'"
        )
    return ResultadoValidacao(True)


def validar_amostra(amostra: Any, amostra_minima: int = 100) -> ResultadoValidacao:
    """
    Valida se o tamanho da amostra é um inteiro positivo acima do limite mínimo.
    """
    try:
        amostra_int = int(amostra)
        if amostra_int < amostra_minima:
            return ResultadoValidacao(
                False,
                f"Amostra ({amostra_int}) menor que o mínimo permitido ({amostra_minima})"
            )
        return ResultadoValidacao(True)
    except (ValueError, TypeError):
        return ResultadoValidacao(False, f"Valor de amostra inválido: '{amostra}'")


def validar_datas(data_inicio: str, data_fim: str) -> ResultadoValidacao:
    """
    Garante que data_fim não seja anterior a data_inicio.
    """
    if not data_inicio or not data_fim:
        return ResultadoValidacao(False, "Data de início ou de fim ausente")
    if str(data_fim) < str(data_inicio):
        return ResultadoValidacao(
            False,
            f"Data final ({data_fim}) anterior à data inicial ({data_inicio})"
        )
    return ResultadoValidacao(True)


def validar_soma_percentuais(
    percentuais: List[float],
    min_soma: float = 90.0,
    max_soma: float = 105.0
) -> ResultadoValidacao:
    """
    Valida se a soma dos percentuais de um cenário de pesquisa
    está dentro de uma faixa razoável (por conta de arredondamentos e múltiplos candidatos).
    """
    if not percentuais:
        return ResultadoValidacao(False, "Nenhum percentual informado para o cenário")
    
    soma = sum(percentuais)
    if soma < min_soma or soma > max_soma:
        return ResultadoValidacao(
            False,
            f"Soma dos percentuais ({soma:.2f}%) fora do intervalo permitido [{min_soma}%, {max_soma}%]"
        )
    return ResultadoValidacao(True)
