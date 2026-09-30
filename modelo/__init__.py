"""
Módulo de Modelo e Agregação Estatística:
- database: Gerenciamento do SQLite / PostgreSQL
- config: Leitura e validação do config.yaml
- validador: Regras de consistência e conformidade TSE
- importar_csv: Leitura e carga de pesquisas tabulares
"""

from modelo.config import carregar_config
from modelo.database import get_connection, init_db
from modelo.validador import validar_registro_tse, validar_amostra, validar_datas, validar_soma_percentuais

__all__ = [
    "carregar_config",
    "get_connection",
    "init_db",
    "validar_registro_tse",
    "validar_amostra",
    "validar_datas",
    "validar_soma_percentuais",
]
