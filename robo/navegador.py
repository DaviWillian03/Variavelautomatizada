"""Abre um Chrome comum e espera você deixar o Connect Merchan aberto.

O robô NUNCA digita senha nem aprova o MFA: quem faz o login é você, na janela que ele abre.
O perfil do navegador fica em `perfil-navegador/` (fora do Git); se a sessão do sistema ainda
estiver válida, ele já começa logado.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Iterator
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, Playwright

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
def navegador_aberto(pw: Playwright, cfg: Config) -> Iterator[BrowserContext]:
    """Abre um Chrome NORMAL (sem modo automação) e só depois o robô se conecta a ele.

    Assim o login e o "Não sou um robô" acontecem num navegador comum, feitos por você.
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
