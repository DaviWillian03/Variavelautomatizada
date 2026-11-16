"""Testes com um site falso local (não acessa o FlagCloud)."""

from __future__ import annotations

import logging
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from robo.config import carregar_config
from robo.navegador import (
    LoginCancelado,
    abrir_navegador,
    aguardar_login_manual,
    esta_logado,
)
from robo.tarefas import executar_tarefas

SITE = Path(__file__).parent / "site_falso"
CHROMIUM_NUVEM = Path("/opt/pw-browsers/chromium-1243/chrome-linux64/chrome")


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401
        pass


@pytest.fixture(scope="module")
def servidor():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencioso, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture
def cfg(servidor, tmp_path, monkeypatch):
    monkeypatch.setenv("URL_SISTEMA", f"{servidor}/login.html")
    monkeypatch.setenv("NAVEGADOR", "chromium")
    monkeypatch.setenv("HEADLESS", "1")
    for var in ("PASTA_PERFIL", "PASTA_SAIDA", "PASTA_LOGS"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    if CHROMIUM_NUVEM.exists():
        monkeypatch.setenv("CAMINHO_NAVEGADOR", str(CHROMIUM_NUVEM))
    return carregar_config(tmp_path / "inexistente.env")


@pytest.fixture
def pagina(cfg):
    with sync_playwright() as pw:
        contexto = abrir_navegador(pw, cfg)
        yield contexto.new_page()
        contexto.close()


LOG = logging.getLogger("teste")


def test_navegador_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("NAVEGADOR", "firefox")
    with pytest.raises(ValueError):
        carregar_config(tmp_path / "x.env")


def test_detecta_tela_de_login(pagina, cfg):
    pagina.goto(cfg.url_sistema)
    assert not esta_logado(pagina)


def test_espera_pessoa_logar(pagina, cfg):
    chamadas = []

    def pessoa_faz_login(_mensagem: str) -> str:
        chamadas.append(1)
        if len(chamadas) == 2:  # na 1ª vez aperta Enter sem logar; na 2ª já entrou
            pagina.click("#entrar")
            pagina.wait_for_url("**/inicio.html")
        return ""

    aguardar_login_manual(pagina, cfg, LOG, perguntar=pessoa_faz_login)
    assert esta_logado(pagina)
    assert len(chamadas) == 2


def test_pessoa_pode_sair(pagina, cfg):
    with pytest.raises(LoginCancelado):
        aguardar_login_manual(pagina, cfg, LOG, perguntar=lambda _m: "sair")


def test_tarefas_salvam_tela_inicial(pagina, cfg, servidor):
    pagina.goto(f"{servidor}/inicio.html")
    executar_tarefas(pagina, cfg, LOG)
    assert list(cfg.pasta_saida.glob("*_tela-inicial.png"))
