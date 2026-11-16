"""Testes com um site falso local (nunca acessam o FlagCloud) e dados fictícios."""

from __future__ import annotations

import logging
import threading
from datetime import date
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import openpyxl
import pytest
from playwright.sync_api import sync_playwright

from robo.config import carregar_config
from robo.interacao import Sair, Terminal, interpretar_selecao, periodo_sugerido
from robo.navegador import (
    abrir_connect_merchan,
    esperar_login,
    navegador_aberto,
    pagina_do_sistema,
)
from robo.planilha import ler_planilha, pasta_do_supervisor
from robo.tarefas import executar, preparar

SITE = Path(__file__).parent / "site_falso"
CHROMIUM_NUVEM = Path("/opt/pw-browsers/chromium-1243/chrome-linux64/chrome")
LOG = logging.getLogger("teste")

PESSOAS = [
    (1001, "Ana Teste Souza", "ana.souza", "Emiliane Exemplo da Silva"),
    (1002, "Bruno Exemplo Lima", "bruno.lima", "Emiliane Exemplo da Silva"),
    (1003, "Carla Ficticia Dias", "carla.dias", "Ruan Exemplo Zeferino"),
    (1004, "Carla de Mendes", "carla.mendes", "Ruan Exemplo Zeferino"),
    (1005, "Davi Teste Rocha", "davi.rocha", "Flávio Exemplo Batista"),
]


def roteiro(*respostas: str):
    """Simula a pessoa respondendo no terminal, na ordem."""
    fila = list(respostas)
    perguntas: list[str] = []

    def responder(pergunta: str) -> str:
        perguntas.append(pergunta)
        return fila.pop(0)

    responder.perguntas = perguntas
    return responder


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def servidor():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencioso, directory=str(SITE)))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture
def planilha(tmp_path) -> Path:
    livro = openpyxl.Workbook()
    aba = livro.active
    aba.append(["Cod. Colaborador", "Nome", "Usuario", "Nome Superior"])
    for linha in PESSOAS:
        aba.append(list(linha))
    caminho = tmp_path / "colaboradores.xlsx"
    livro.save(caminho)
    return caminho


@pytest.fixture
def cfg(servidor, tmp_path, monkeypatch, planilha):
    monkeypatch.setenv("URL_SISTEMA", f"{servidor}/login.html")
    monkeypatch.setenv("HOST_SISTEMA", "localhost")  # portal em 127.0.0.1
    monkeypatch.setenv("NAVEGADOR", "chromium")
    monkeypatch.setenv("HEADLESS", "1")
    monkeypatch.setenv("TIMEOUT_MS", "8000")
    monkeypatch.setenv("TIMEOUT_RELATORIO_S", "40")
    monkeypatch.setenv("PLANILHA", str(planilha))
    monkeypatch.setenv("PASTA_AREA_TRABALHO", str(tmp_path / "Area de Trabalho"))
    for var in ("PASTA_PERFIL", "PASTA_SAIDA", "PASTA_LOGS"):
        monkeypatch.setenv(var, str(tmp_path / var.lower()))
    if CHROMIUM_NUVEM.exists():
        monkeypatch.setenv("CAMINHO_NAVEGADOR", str(CHROMIUM_NUVEM))
    return carregar_config(tmp_path / "inexistente.env")


@pytest.fixture
def contexto(cfg):
    with sync_playwright() as pw:
        with navegador_aberto(pw, cfg) as ctx:
            yield ctx


# ---------- planilha e perguntas ----------


def test_planilha_pastas_e_nomes(planilha):
    lista = ler_planilha(planilha)
    assert [c.pasta for c in lista] == ["V EMI", "V EMI", "V RUA", "V RUA", "V FLA"]
    # duas Carlas na mesma pasta → nome + sobrenome; o resto só o primeiro nome
    assert [c.arquivo for c in lista] == ["Ana", "Bruno", "Carla Ficticia", "Carla Mendes", "Davi"]
    assert lista[0].rotulo == "1001 - Ana Teste Souza"


def test_pasta_do_supervisor_reais():
    assert pasta_do_supervisor("Emiliane Kelly") == "V EMI"
    assert pasta_do_supervisor("Flávio Henrique") == "V FLA"
    assert pasta_do_supervisor("Ruan Henrique") == "V RUA"


def test_periodo_sugerido_quinzenas():
    p = periodo_sugerido(date(2026, 11, 16))
    assert (p.inicio, p.fim) == (date(2026, 11, 1), date(2026, 11, 15))
    p = periodo_sugerido(date(2026, 12, 2))
    assert (p.inicio, p.fim) == (date(2026, 11, 16), date(2026, 11, 30))
    p = periodo_sugerido(date(2027, 1, 5))
    assert (p.inicio, p.fim) == (date(2026, 12, 16), date(2026, 12, 31))


def test_selecao_de_colaboradores(planilha):
    lista = ler_planilha(planilha)
    assert interpretar_selecao("", lista) == lista
    assert [c.codigo for c in interpretar_selecao("rua", lista)] == ["1003", "1004"]
    assert [c.codigo for c in interpretar_selecao("1, 3-4", lista)] == ["1001", "1003", "1004"]
    with pytest.raises(ValueError):
        interpretar_selecao("9", lista)


def test_navegador_invalido(monkeypatch, tmp_path):
    monkeypatch.setenv("NAVEGADOR", "firefox")
    with pytest.raises(ValueError):
        carregar_config(tmp_path / "x.env")


# ---------- navegador ----------


def test_abre_connect_merchan_a_partir_do_portal(contexto, cfg):
    page = contexto.pages[0]
    page.wait_for_url("**/login.html")

    def pessoa(_pergunta: str) -> str:
        # 1ª pergunta: ainda na tela de login → a pessoa termina o login agora
        page.click("#entrar")
        page.wait_for_url("**/portal.html")
        pessoa.vezes += 1
        return ""

    pessoa.vezes = 0
    connect = abrir_connect_merchan(contexto, cfg, LOG, Terminal(pessoa, lambda _m: None))
    assert connect.url.startswith("http://localhost:") and "/pesquisas" in connect.url
    assert pessoa.vezes == 1
    # o robô abriu a nova aba sozinho clicando em "Connect Merchan" no portal
    assert len(contexto.pages) == 2


def test_pessoa_pode_sair(contexto, cfg):
    contexto.pages[0].wait_for_url("**/login.html")
    with pytest.raises(Sair):
        abrir_connect_merchan(contexto, cfg, LOG, Terminal(lambda _m: "sair", lambda _m: None))
    assert pagina_do_sistema(contexto, cfg.host_sistema) is None


def test_percebe_sozinho_quando_o_login_termina(cfg):
    portas = []
    with sync_playwright() as pw, navegador_aberto(pw, cfg, portas.append) as ctx:
        page = ctx.pages[0]
        page.wait_for_url("**/login.html")
        with pytest.raises(RuntimeError):  # ainda na tela de login → não começa
            esperar_login(portas[0], cfg, LOG, minutos=0.05)
        page.click("#entrar")
        page.wait_for_url("**/portal.html")
        esperar_login(portas[0], cfg, LOG, minutos=0.5)  # agora começa, sem Enter


def test_reaproveita_chrome_do_robo_que_ficou_aberto(cfg):
    with sync_playwright() as pw, navegador_aberto(pw, cfg) as primeiro:
        primeiro.pages[0].wait_for_url("**/login.html")
        with navegador_aberto(pw, cfg) as segundo:  # 2ª execução com o Chrome ainda aberto
            assert any(p.url.endswith("/login.html") for p in segundo.pages)


# ---------- fluxo completo no site falso ----------


def test_fluxo_completo(contexto, cfg, servidor):
    page = contexto.new_page()
    page.goto(f"{servidor}/pesquisas/")
    respostas = roteiro(
        "",  # data início sugerida (01/11/2026)
        "",  # data fim sugerida (15/11/2026)
        "",  # pasta "Variavel Novembro"
        "1,2,3",  # Ana (2 variáveis), Bruno (nenhuma), Carla (1)
        "s",  # começar
    )
    term = Terminal(respostas, lambda _m: None)
    plano = preparar(cfg, LOG, term, hoje=date(2026, 11, 16))  # perguntas antes do Chrome
    resumo = executar(page, cfg, LOG, term, plano)

    base = cfg.pasta_area_trabalho / "Variavel Novembro"
    assert (base / "V EMI" / "Ana.pdf").read_bytes().startswith(b"%PDF")
    assert (base / "V RUA" / "Carla Ficticia.pdf").exists()
    assert not (base / "V EMI" / "Bruno.pdf").exists()

    situacoes = dict(resumo)
    assert situacoes["1002 - Bruno Exemplo Lima"] == "sem pesquisa de variável"
    assert situacoes["1001 - Ana Teste Souza"].startswith("ok")

    # só as pesquisas de variável foram exportadas, nunca as "Antes E Depois"
    assert page.evaluate("window.exportados") == [[401, 402], [600]]
    filtros = page.evaluate("window.filtrosAplicados")
    assert filtros[0] == {
        "ini": "01/11/2026",
        "fim": "15/11/2026",
        "situacao": "Respondida",
        "tipo": "Pesquisa",
        "colaborador": "1001 - Ana Teste Souza",
    }
    assert [f["colaborador"] for f in filtros] == [
        "1001 - Ana Teste Souza",
        "1002 - Bruno Exemplo Lima",
        "1003 - Carla Ficticia Dias",
    ]
    assert list(cfg.pasta_saida.glob("*_resumo.txt"))


def test_textos_com_ou_sem_acento():
    from robo.connect import rx

    assert rx("Período Começo das Respostas").search("Periodo Começo das Respostas")
    assert rx("Tipo de formulário", inteiro=True).search("Tipo de formulario")
    assert rx("Relatorios", inteiro=True).search("  Relatórios ")
    assert not rx("Pesquisa", inteiro=True).search("Pesquisa Prioritária")
    assert rx("Export do Caderno (PDF)").search("7. Export do Caderno (PDF)")
