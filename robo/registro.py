"""Logs no terminal e em arquivo (logs/robo-AAAA-MM-DD.log)."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

FORMATO = "%(asctime)s  %(levelname)-7s  %(message)s"


def configurar_log(pasta_logs: Path) -> logging.Logger:
    pasta_logs.mkdir(parents=True, exist_ok=True)
    log = logging.getLogger("robo")
    log.setLevel(logging.INFO)
    log.handlers.clear()

    terminal = logging.StreamHandler()
    terminal.setFormatter(logging.Formatter(FORMATO, "%H:%M:%S"))
    log.addHandler(terminal)

    arquivo = logging.FileHandler(
        pasta_logs / f"robo-{datetime.now():%Y-%m-%d}.log", encoding="utf-8"
    )
    arquivo.setFormatter(logging.Formatter(FORMATO))
    log.addHandler(arquivo)
    return log
