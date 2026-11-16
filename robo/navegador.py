"""Abre o navegador e espera a pessoa fazer o login (usuário, senha e Authenticator).

O robô NUNCA digita senha nem aprova o MFA: quem faz o login é você, na janela que ele abre.
O perfil do navegador fica em `perfil-navegador/` (fora do Git), então se a sessão do
sistema ainda estiver válida, o robô já começa logado.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright

from .config import Config


class LoginCancelado(Exception):
    """A pessoa escolheu sair antes de concluir o login."""


def abrir_navegador(pw: Playwright, cfg: Config) -> BrowserContext:
    cfg.pasta_perfil.mkdir(parents=True, exist_ok=True)
    opcoes: dict = {
        "user_data_dir": str(cfg.pasta_perfil),
        "headless": cfg.headless,
        "accept_downloads": True,
        "viewport": {"width": 1366, "height": 768},
    }
    if cfg.caminho_navegador:
        opcoes["executable_path"] = cfg.caminho_navegador
    elif cfg.navegador != "chromium":
        opcoes["channel"] = cfg.navegador  # usa o Edge/Chrome já instalado no Windows

    contexto = pw.chromium.launch_persistent_context(**opcoes)
    contexto.set_default_timeout(cfg.timeout_ms)
    return contexto


def esta_logado(page: Page) -> bool:
    """Considera logado quando a página atual não é a tela de login."""
    caminho = urlparse(page.url).path.lower()
    return page.url not in ("", "about:blank") and "login" not in caminho


def aguardar_login_manual(
    page: Page,
    cfg: Config,
    log: logging.Logger,
    perguntar: Callable[[str], str] = input,
) -> None:
    log.info("Abrindo %s", cfg.url_sistema)
    page.goto(cfg.url_sistema)
    page.wait_for_load_state("domcontentloaded")

    while not esta_logado(page):
        log.info("Faça o login na janela do navegador (usuário, senha e Microsoft Authenticator).")
        resposta = perguntar(
            "Quando estiver DENTRO do sistema, aperte Enter aqui (ou digite 'sair'): "
        )
        if resposta.strip().lower() == "sair":
            raise LoginCancelado("Login cancelado por você.")
        page.wait_for_load_state("domcontentloaded")
        if not esta_logado(page):
            log.warning("Ainda estou vendo a tela de login (%s).", page.url)

    log.info("Login confirmado. Página atual: %s", page.url)


def capturar_tela(page: Page, pasta: Path, nome: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{nome}.png"
    page.screenshot(path=str(arquivo), full_page=True)
    return arquivo
