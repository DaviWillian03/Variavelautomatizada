"""Abre um Chrome comum e espera você deixar o Connect Merchan aberto.

O robô NUNCA digita senha nem aprova o MFA: quem faz o login é você, na janela que ele abre.
O perfil do navegador fica em `perfil-navegador/` (fora do Git); se a sessão do sistema ainda
estiver válida, ele já começa logado.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Iterator
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright
from playwright.sync_api import Error as PlaywrightError

from .config import Config

if TYPE_CHECKING:
    from .interacao import Terminal


def localizar_navegador(cfg: Config) -> str:
    """Caminho do chrome.exe (ou msedge.exe) instalado no Windows."""
    if cfg.caminho_navegador:
        return cfg.caminho_navegador
    pastas = [os.environ.get(v, "") for v in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    relativos = {
        "chrome": [r"Google\Chrome\Application\chrome.exe"],
        "msedge": [r"Microsoft\Edge\Application\msedge.exe"],
    }.get(cfg.navegador, [])
    for pasta in filter(None, pastas):
        for relativo in relativos:
            if (exe := Path(pasta) / relativo).exists():
                return str(exe)
    for nome in ("google-chrome", "chrome", "chromium", "msedge"):
        if achado := shutil.which(nome):
            return achado
    raise FileNotFoundError(
        "Não achei o Google Chrome instalado. Instale o Chrome ou informe o caminho do chrome.exe "
        "em CAMINHO_NAVEGADOR no arquivo .env."
    )


def _esperar_porta(arquivo: Path, processo: subprocess.Popen, segundos: float = 30) -> int:
    prazo = time.monotonic() + segundos
    while time.monotonic() < prazo:
        if arquivo.exists():
            primeira = arquivo.read_text(encoding="utf-8", errors="ignore").splitlines()[:1]
            if primeira and primeira[0].strip().isdigit():
                return int(primeira[0])
        if processo.poll() is not None and not arquivo.exists():
            break
        time.sleep(0.2)
    raise RuntimeError(
        "O Chrome do robô não respondeu. Feche TODAS as janelas do Chrome que o robô abriu "
        "antes e rode o executar.bat de novo."
    )


@contextmanager
def navegador_aberto(
    pw: Playwright, cfg: Config, antes_de_conectar: Callable[[], object] | None = None
) -> Iterator[BrowserContext]:
    """Abre um Chrome NORMAL (sem modo automação) e só depois o robô se conecta a ele.

    O robô só se conecta DEPOIS que você termina o login (`antes_de_conectar`), então
    durante o login, o "Não sou um robô" e o Authenticator nada é controlado pelo robô.
    O Chrome usa um perfil próprio (`perfil-navegador/`), separado do seu Chrome do dia a dia.
    """
    cfg.pasta_perfil.mkdir(parents=True, exist_ok=True)
    arquivo_porta = cfg.pasta_perfil / "DevToolsActivePort"
    arquivo_porta.unlink(missing_ok=True)

    argumentos = [
        localizar_navegador(cfg),
        f"--user-data-dir={cfg.pasta_perfil}",
        "--remote-debugging-port=0",
        "--remote-debugging-address=127.0.0.1",
        "--no-first-run",
        "--no-default-browser-check",
        "--start-maximized",
    ]
    if cfg.headless:
        argumentos.append("--headless=new")
    if os.name != "nt" and os.geteuid() == 0:
        argumentos.append("--no-sandbox")  # só no contêiner de testes (root no Linux)
    argumentos.append(cfg.url_sistema)

    processo = subprocess.Popen(argumentos, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    navegador = None
    try:
        porta = _esperar_porta(arquivo_porta, processo)
        if antes_de_conectar is not None:
            antes_de_conectar()
        navegador = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        contexto = navegador.contexts[0]
        contexto.set_default_timeout(cfg.timeout_ms)
        yield contexto
    finally:
        if navegador is not None:
            try:
                navegador.close()
            except Exception:
                pass
        processo.terminate()
        try:
            processo.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processo.kill()


def _pronta(page: Page, host: str) -> bool:
    url = urlparse(page.url)
    caminho = url.path.lower()
    token = any(len(parte) > 60 for parte in caminho.split("/"))  # link de entrada com código
    return url.hostname == host and "login" not in caminho and caminho != "/connect" and not token


def pagina_do_sistema(contexto: BrowserContext, host: str) -> Page | None:
    """Aba em que o Connect Merchan já está aberto e logado (a mais recente)."""
    return next((p for p in reversed(contexto.pages) if _pronta(p, host)), None)


def pagina_do_portal(contexto: BrowserContext, host: str) -> Page | None:
    """Aba do portal Broker já depois do login (fora da tela /login)."""
    return next((p for p in reversed(contexto.pages) if _pronta(p, host)), None)


def pedir_login(term: "Terminal") -> None:
    term.mostrar(
        "\nNa janela do Chrome que abriu: faça o login (usuário, senha, 'Não sou um robô' e "
        "Microsoft Authenticator). O robô ainda NÃO está controlando o Chrome."
    )
    term.perguntar("Quando estiver na tela do portal, já liberado, aperte Enter (ou 'sair')")


def _esperar_connect(contexto: BrowserContext, cfg: Config) -> Page | None:
    prazo = time.monotonic() + cfg.timeout_ms / 1000 * 2
    while time.monotonic() < prazo:
        if page := pagina_do_sistema(contexto, cfg.host_sistema):
            return page
        contexto.pages[0].wait_for_timeout(500)
    return None


def abrir_connect_merchan(
    contexto: BrowserContext, cfg: Config, log: logging.Logger, term: "Terminal"
) -> Page:
    """Primeira tarefa do robô: a partir do portal, clicar para abrir o Connect Merchan."""
    if page := pagina_do_sistema(contexto, cfg.host_sistema):
        log.info("Connect Merchan já estava aberto.")
    else:
        while (portal := pagina_do_portal(contexto, cfg.host_portal)) is None:
            term.mostrar("Ainda não estou vendo o portal liberado (fora da tela de login).")
            pedir_login(term)
        portal.bring_to_front()
        log.info("Portal encontrado. Abrindo o Connect Merchan…")
        try:
            portal.get_by_text(re.compile(r"Connect\s*Merchan", re.I)).locator(
                "visible=true"
            ).first.click()
        except PlaywrightError as erro:
            log.warning("Não achei o botão do Connect Merchan (%s).", str(erro).splitlines()[0])
            log.warning("Print: %s", capturar_tela(portal, cfg.pasta_saida, "ajuda"))
        page = _esperar_connect(contexto, cfg)
        while page is None:
            term.perguntar(
                "  >> Faça você: clique para abrir o Connect Merchan no portal. "
                "Quando ele abrir, aperte Enter (ou 'sair')"
            )
            page = _esperar_connect(contexto, cfg)

    page.bring_to_front()
    page.wait_for_load_state("domcontentloaded")
    log.info("Connect Merchan aberto: %s", urlparse(page.url).hostname)
    return page


def capturar_tela(page: Page, pasta: Path, nome: str) -> Path:
    pasta.mkdir(parents=True, exist_ok=True)
    arquivo = pasta / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_{nome}.png"
    page.screenshot(path=str(arquivo), full_page=True)
    return arquivo
