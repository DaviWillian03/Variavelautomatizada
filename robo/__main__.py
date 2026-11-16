"""Ponto de entrada: `python -m robo`."""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

from .config import carregar_config
from .navegador import LoginCancelado, abrir_navegador, aguardar_login_manual, capturar_tela
from .registro import configurar_log
from .tarefas import executar_tarefas


def main() -> int:
    cfg = carregar_config()
    log = configurar_log(cfg.pasta_logs)
    log.info("Robô iniciado (navegador: %s).", cfg.navegador)

    with sync_playwright() as pw:
        contexto = abrir_navegador(pw, cfg)
        page = contexto.pages[0] if contexto.pages else contexto.new_page()
        try:
            aguardar_login_manual(page, cfg, log)
            executar_tarefas(page, cfg, log)
        except LoginCancelado as erro:
            log.warning("%s", erro)
            return 2
        except Exception:
            log.exception("Erro durante a execução.")
            try:
                log.error("Print do erro: %s", capturar_tela(page, cfg.pasta_saida, "erro"))
            except Exception:
                log.error("Não consegui salvar o print do erro.")
            return 1
        finally:
            contexto.close()

    log.info("Robô terminou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
