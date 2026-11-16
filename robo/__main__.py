"""Ponto de entrada: `python -m robo`."""

from __future__ import annotations

import logging
import sys

from playwright.sync_api import BrowserContext, sync_playwright

from .config import Config, carregar_config
from .interacao import Sair, Terminal
from .navegador import abrir_connect_merchan, capturar_tela, navegador_aberto, pedir_login
from .registro import configurar_log
from .tarefas import executar_tarefas


def _trabalhar(contexto: BrowserContext, cfg: Config, log: logging.Logger, term: Terminal) -> int:
    page = None
    try:
        page = abrir_connect_merchan(contexto, cfg, log, term)
        executar_tarefas(page, cfg, log, term)
    except Sair:
        log.warning("Encerrado por você.")
        return 2
    except Exception:
        log.exception("Erro durante a execução.")
        if page is not None:
            try:
                log.error("Print do erro: %s", capturar_tela(page, cfg.pasta_saida, "erro"))
            except Exception:
                log.error("Não consegui salvar o print do erro.")
        return 1
    finally:
        if sys.stdin.isatty():
            try:
                input("\nAperte Enter para fechar o Chrome do robô: ")
            except (EOFError, KeyboardInterrupt):
                pass
    log.info("Robô terminou.")
    return 0


def main() -> int:
    cfg = carregar_config()
    log = configurar_log(cfg.pasta_logs)
    term = Terminal()
    log.info("Robô da Variável iniciado.")
    try:
        with sync_playwright() as pw, navegador_aberto(pw, cfg, lambda: pedir_login(term), log) as ctx:
            return _trabalhar(ctx, cfg, log, term)
    except (Sair, KeyboardInterrupt):
        log.warning("Encerrado por você.")
        return 2
    except (RuntimeError, FileNotFoundError) as erro:
        log.error("%s", erro)
        return 1


if __name__ == "__main__":
    sys.exit(main())
