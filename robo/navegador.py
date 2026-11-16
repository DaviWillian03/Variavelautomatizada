"""Abre o Chrome e espera você deixar o Connect Merchan aberto.

O robô NUNCA digita senha nem aprova o MFA: quem faz o login é você, na janela que ele abre.
O perfil do navegador fica em `perfil-navegador/` (fora do Git); se a sessão do sistema ainda
estiver válida, ele já começa logado.
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright

from .config import Config

if TYPE_CHECKING:
    from .interacao import Terminal


def abrir_navegador(pw: Playwright, cfg: Config) -> BrowserContext:
    cfg.pasta_perfil.mkdir(parents=True, exist_ok=True)
    opcoes: dict = {
        "user_data_dir": str(cfg.pasta_perfil),
        "headless": cfg.headless,
        "accept_downloads": True,
        "no_viewport": not cfg.headless,
        "args": [] if cfg.headless else ["--start-maximized"],
    }
    if cfg.caminho_navegador:
        opcoes["executable_path"] = cfg.caminho_navegador
    elif cfg.navegador != "chromium":
        opcoes["channel"] = cfg.navegador  # usa o Chrome/Edge já instalado no Windows

    contexto = pw.chromium.launch_persistent_context(**opcoes)
    contexto.set_default_timeout(cfg.timeout_ms)
    return contexto


def pagina_do_sistema(contexto: BrowserContext, host: str) -> Page | None:
    """Aba em que o Connect Merchan já está aberto e logado (a mais recente)."""
    for page in reversed(contexto.pages):
        url = urlparse(page.url)
        if url.hostname == host and "login" not in url.path.lower() and url.path != "/connect":
            return page
    return None


def aguardar_sistema(
    contexto: BrowserContext, cfg: Config, log: logging.Logger, term: "Terminal"
) -> Page:
    inicial = contexto.pages[0] if contexto.pages else contexto.new_page()
    if inicial.url in ("", "about:blank"):
        log.info("Abrindo %s", cfg.url_sistema)
        inicial.goto(cfg.url_sistema)

    while (page := pagina_do_sistema(contexto, cfg.host_sistema)) is None:
        term.mostrar(
            "\nNa janela do Chrome que abriu: faça o login (usuário, senha e Authenticator) e "
            "abra o Connect Merchan, como você faz normalmente."
        )
        term.perguntar("Quando o Connect Merchan estiver na tela, aperte Enter (ou 'sair')")

    page.bring_to_front()
    page.wait_for_load_state("domcontentloaded")
    log.info("Connect Merchan encontrado: %s", urlparse(page.url).hostname)
    return page


def capturar_tela(page: Page, pasta: Path, nome: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{nome}.png"
    page.screenshot(path=str(arquivo), full_page=True)
    return arquivo
