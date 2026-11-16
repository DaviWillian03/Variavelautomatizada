"""O que o robô faz depois que você já está dentro do sistema.

AINDA NÃO DEFINIDO: os passos reais entram aqui quando o passo a passo e os prints
das telas forem enviados. Por enquanto, ele só registra a tela inicial para mapearmos
os menus e campos.
"""

from __future__ import annotations

import logging

from playwright.sync_api import Page

from .config import Config
from .navegador import capturar_tela


def executar_tarefas(page: Page, cfg: Config, log: logging.Logger) -> None:
    arquivo = capturar_tela(page, cfg.pasta_saida, "tela-inicial")
    log.info("Tela inicial salva em %s", arquivo)
    log.warning("Nenhuma tarefa configurada ainda — nada foi alterado no sistema.")
