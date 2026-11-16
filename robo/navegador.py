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
import urllib.request
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


def _ler_porta(arquivo: Path) -> int | None:
    try:
        primeira = arquivo.read_text(encoding="utf-8", errors="ignore").splitlines()[:1]
    except OSError:
        return None
    return int(primeira[0]) if primeira and primeira[0].strip().isdigit() else None


def _porta_responde(porta: int) -> bool:
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # local, sem proxy
    try:
        with abridor.open(f"http://127.0.0.1:{porta}/json/version", timeout=2) as resposta:
            return resposta.status == 200
    except (OSError, ValueError):
        return False


def _chrome_do_robo_aberto(arquivo: Path) -> int | None:
    """Porta de um Chrome do robô que ficou aberto de uma execução anterior (se houver)."""
    porta = _ler_porta(arquivo) if arquivo.exists() else None
    return porta if porta and _porta_responde(porta) else None


def _esperar_porta(
    arquivo: Path, processo: subprocess.Popen, log: logging.Logger, segundos: float = 90
) -> int:
    prazo = time.monotonic() + segundos
    while time.monotonic() < prazo:
        porta = _ler_porta(arquivo) if arquivo.exists() else None
        if porta and _porta_responde(porta):
            return porta
        time.sleep(0.5)
    log.error(
        "Chrome sem resposta: processo %s, arquivo de porta %s.",
        "ainda rodando" if processo.poll() is None else f"encerrado (código {processo.returncode})",
        "existe" if arquivo.exists() else "não existe",
    )
    raise RuntimeError(
        "O Chrome do robô não respondeu em 90 segundos. Feche todas as janelas do Chrome "
        "que o robô abriu (ou reinicie o computador) e rode o executar.bat de novo. "
        "Se continuar, mande o arquivo da pasta logs."
    )


def _encerrar(processo: subprocess.Popen) -> None:
    if processo.poll() is not None:
        return
    if os.name == "nt":  # fecha o Chrome e todos os processos filhos dele
        subprocess.run(
            ["taskkill", "/PID", str(processo.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        processo.terminate()
    try:
        processo.wait(timeout=10)
    except subprocess.TimeoutExpired:
        processo.kill()


@contextmanager
def navegador_aberto(
    pw: Playwright,
    cfg: Config,
    antes_de_conectar: Callable[[], object] | None = None,
    log: logging.Logger | None = None,
) -> Iterator[BrowserContext]:
    """Abre um Chrome comum e só depois o robô se conecta a ele.

    O robô só se conecta DEPOIS que você termina o login (`antes_de_conectar`), então
    durante o login, o "Não sou um robô" e o Authenticator nada é controlado pelo robô.
    O Chrome usa um perfil próprio (`perfil-navegador/`), separado do seu Chrome do dia a dia.
    Se um Chrome do robô ficou aberto de uma execução anterior, ele é reaproveitado.
    """
    log = log or logging.getLogger("robo")
    cfg.pasta_perfil.mkdir(parents=True, exist_ok=True)
    arquivo_porta = cfg.pasta_perfil / "DevToolsActivePort"

    processo: subprocess.Popen | None = None
    if porta := _chrome_do_robo_aberto(arquivo_porta):
        log.info("Reaproveitando o Chrome do robô que já estava aberto.")
    else:
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
        log.info("Abrindo o Chrome: %s", argumentos[0])
        processo = subprocess.Popen(
            argumentos, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    navegador = None
    try:
        if processo is not None:
            porta = _esperar_porta(arquivo_porta, processo, log)
        if antes_de_conectar is not None:
            antes_de_conectar()
        navegador = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{porta}")
        contexto = navegador.contexts[0]
        contexto.set_default_timeout(cfg.timeout_ms)
        yield contexto
    finally:
        if navegador is not None:
            try:  # fecha o Chrome do jeito normal (sem aviso de "não foi fechado corretamente")
                navegador.new_browser_cdp_session().send("Browser.close")
            except Exception:
                pass
            try:
                navegador.close()
            except Exception:
                pass
        if processo is not None:
            _encerrar(processo)


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


def clicar_no_menu(page: Page, nome: str) -> None:
    """Clica num item do menu lateral do portal, mesmo com o menu recolhido.

    Com o menu recolhido só aparecem os ícones; o nome do item fica escondido até o mouse
    passar por cima. Então: acha o item pelo nome (mesmo escondido), passa o mouse no item
    (o menu abre) e clica.
    """
    texto = page.get_by_text(re.compile(rf"^\s*{re.escape(nome)}\s*$", re.I))
    texto.first.wait_for(state="attached", timeout=10_000)
    if texto.locator("visible=true").count():
        texto.locator("visible=true").first.click()
        return
    item = texto.first.locator(
        "xpath=ancestor::*[self::a or self::button or self::li or @role='button' "
        "or @role='menuitem' or @role='link'][1]"
    )
    item.hover()
    page.wait_for_timeout(600)  # animação do menu abrindo
    if texto.locator("visible=true").count():
        texto.locator("visible=true").first.click()
    else:
        item.click()


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
            clicar_no_menu(portal, "Connect Merchan")
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
