#!/usr/bin/env python3
"""
Pipeline Principal do Agregador de Pesquisas Eleitorais 2026.

Uso mais comum (faz tudo: baixa registros do TSE, coleta matérias, roda o modelo):
    python run_pipeline.py

Variações:
    python run_pipeline.py --servir      # ao final, abre o site em http://localhost:8000
    python run_pipeline.py --offline     # sem internet: só recalcula o modelo com o que já está no banco
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import logging
import socketserver
import sys
import webbrowser
from pathlib import Path

from coleta import planopolitico
from coleta.descoberta import coletar_materias
from coleta.tse_oficial import atualizar_base_tse, conferir_pesquisas_com_tse
from modelo.config import carregar_config
from modelo.database import init_db, get_connection
from modelo.importar_csv import importar_csv_pesquisas
from modelo.importar_reais import importar_dados_reais
from modelo.agregador import executar_pipeline_modelo

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("pipeline")


def executar_pipeline(
    caminho_config: str = "config.yaml",
    forcar_init_db: bool = False,
    importar_exemplo: bool = False,
    carga_legada: bool = False,
    executar_modelo: bool = True,
    online: bool = True,
    historico: bool = True,
    reprocessar: bool = False
) -> int:
    logger.info("=" * 65)
    logger.info("Iniciando Agregador de Pesquisas Eleitorais 2026")
    logger.info("=" * 65)

    config = carregar_config(caminho_config)
    banco_path = config.get("caminhos", {}).get("banco_sqlite", "dados/pesquisas.db")
    exemplo_path = config.get("caminhos", {}).get("dados_exemplos", "dados/exemplos/pesquisas_ficticias_2026.csv")

    # 1. Banco: cria se não existe; init_db é idempotente e atualiza bancos antigos com tabelas novas.
    if forcar_init_db or not Path(banco_path).exists():
        logger.info(f"Inicializando banco de dados em: {banco_path}")
    init_db(banco_path)

    # 2. Cargas explícitas (nunca rodam por padrão, porque apagam o que foi coletado)
    if carga_legada:
        logger.warning("Carga legada: substitui as pesquisas do banco pelos 12 registros digitados à mão.")
        res = importar_dados_reais(caminho_config, limpar_anteriores=True)
        logger.info(f"Carga legada: {res['pesquisas_inseridas']} pesquisas, {res['cenarios_inseridos']} cenários.")
    elif importar_exemplo:
        if Path(exemplo_path).exists():
            logger.warning("Importando dados FICTÍCIOS de exemplo.")
            res = importar_csv_pesquisas(exemplo_path, caminho_config)
            logger.info(f"Importação concluída: {res['pesquisas_processadas']} cenários de pesquisas.")
        else:
            logger.warning(f"Arquivo de exemplo não encontrado: {exemplo_path}")

    # 3. Coleta online. Falha de rede não derruba o pipeline: segue com o que já está no banco.
    if online:
        try:
            planopolitico.atualizar()
        except Exception as e:
            logger.warning(f"Não foi possível baixar o Plano Político ({e}). Seguindo com os dados locais.")
        conn = get_connection(banco_path)
        try:
            try:
                total_tse = atualizar_base_tse(
                    conn,
                    int(config.get("projeto", {}).get("eleicao_ano", 2026)),
                    cargo=config.get("projeto", {}).get("cargo_padrao", "Presidente"),
                    uf=config.get("projeto", {}).get("uf_padrao", "BR"),
                )
                logger.info(f"Base oficial do TSE atualizada: {total_tse} registros.")
                for p in conferir_pesquisas_com_tse(conn):
                    logger.warning(f"Conferência TSE: {p}")
            except Exception as e:
                logger.warning(f"Não foi possível atualizar a base do TSE ({e}). Seguindo com os dados locais.")

            try:
                logger.info("Lendo matérias dos portais (a 1ª execução pode levar de 30 a 60 min; depois é rápido)...")
                logger.info(f"Matérias: {coletar_materias(conn, config, historico=historico, reprocessar=reprocessar)}")
            except Exception as e:
                logger.warning(f"Não foi possível coletar matérias ({e}). Seguindo com os dados locais.")
        finally:
            conn.close()
    else:
        logger.info("Modo offline: coleta ignorada.")

    # 4. Status
    conn = get_connection(banco_path)
    total_pesquisas = conn.execute("SELECT COUNT(*) FROM pesquisa").fetchone()[0]
    total_nacionais = conn.execute("SELECT COUNT(*) FROM pesquisa WHERE uf = 'BR'").fetchone()[0]
    total_quarentena = conn.execute("SELECT COUNT(*) FROM quarentena WHERE resolvido = 0").fetchone()[0]
    conn.close()
    logger.info(
        f"Banco: {total_pesquisas} pesquisas ({total_nacionais} nacionais usadas no modelo), "
        f"{total_quarentena} itens em quarentena para revisão."
    )
    if total_nacionais == 0:
        logger.warning("Nenhuma pesquisa nacional no banco: o gráfico ficará vazio.")

    # 5. Modelo
    if executar_modelo:
        logger.info("Calculando modelo de agregação...")
        r = executar_pipeline_modelo(caminho_config)
        logger.info(
            f"Modelo concluído: 1º turno {r.get('pontos_serie_t1_validos')} pts válidos, "
            f"2º turno {r.get('pontos_serie_t2_validos')} pts válidos. JSONs gerados em dados/ e site/dados/."
        )

    logger.info("Pipeline executado com sucesso.")
    return 0


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Serve o site e expõe POST /api/atualizar (botão "Atualizar" da página)."""

    def log_message(self, *a, **k):
        pass

    def do_POST(self):
        if self.path.split("?")[0] != "/api/atualizar":
            self.send_error(404)
            return
        try:
            dados = planopolitico.atualizar()
            corpo, status = {"ok": True, "atualizado_em": dados.get("coletado_em")}, 200
        except Exception as e:  # rede fora, layout mudou etc.
            logger.warning(f"Falha ao atualizar pelo site: {e}")
            corpo, status = {"ok": False, "erro": str(e)}, 502
        payload = json.dumps(corpo).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def servir_site(config_path: str, porta: int = 8000) -> None:
    """Serve a pasta do site e abre o navegador. Encerra com Ctrl+C."""
    site_dir = carregar_config(config_path).get("caminhos", {}).get("site_dir", "site")
    handler = functools.partial(_Handler, directory=site_dir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", porta), handler) as httpd:
        url = f"http://localhost:{porta}"
        logger.info(f"Site no ar em {url} (Ctrl+C para encerrar)")
        webbrowser.open(url)
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Servidor encerrado.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agregador de Pesquisas Eleitorais Brasil 2026")
    parser.add_argument("--config", default="config.yaml", help="Caminho para o config.yaml")
    parser.add_argument("--servir", action="store_true", help="Ao final, abre o site em http://localhost:8000")
    parser.add_argument("--offline", action="store_true", help="Não acessa a internet; só recalcula o modelo")
    parser.add_argument("--rapido", action="store_true", help="Só o RSS (últimas matérias); pula o histórico dos sitemaps")
    parser.add_argument("--reprocessar", action="store_true", help="Analisa de novo matérias já processadas (após mudar regras)")
    parser.add_argument("--skip-model", action="store_true", help="Pula o cálculo do modelo")
    parser.add_argument("--init-db", action="store_true", help="Recria/inicializa o esquema do banco")
    parser.add_argument("--import-exemplo", "--dados-ficticios", action="store_true",
                        help="Importa dados FICTÍCIOS de exemplo (só para demonstração)")
    parser.add_argument("--carga-legada", action="store_true",
                        help="APAGA as pesquisas e recarrega os 12 registros digitados à mão (não verificados)")

    args = parser.parse_args()
    codigo = executar_pipeline(
        caminho_config=args.config,
        forcar_init_db=args.init_db,
        importar_exemplo=args.import_exemplo,
        carga_legada=args.carga_legada,
        executar_modelo=not args.skip_model,
        online=not args.offline,
        historico=not args.rapido,
        reprocessar=args.reprocessar,
    )
    if args.servir:
        servir_site(args.config)
    sys.exit(codigo)


if __name__ == "__main__":
    main()
