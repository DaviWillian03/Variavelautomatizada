"""Ponto de entrada: `python -m robo`."""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

from .config import carregar_config
from .interacao import Sair, Terminal
from .navegador import abrir_navegador, aguardar_sistema, capturar_tela
from .registro import configurar_log
from .tarefas import executar_tarefas


def main() -> int:
    cfg = carregar_config()
    log = configurar_log(cfg.pasta_logs)
    term = Terminal()
    log.info("Robô da Variável iniciado.")

    with sync_playwright() as pw:
        contexto = abrir_navegador(pw, cfg)
        page = None
        try:
            page = aguardar_sistema(contexto, cfg, log, term)
            executar_tarefas(page, cfg, log, term)
        except (Sair, KeyboardInterrupt):
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
            contexto.close()

    log.info("Robô terminou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
