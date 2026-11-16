"""Passos dentro do Connect Merchan, como no vídeo de referência.

Os seletores foram tirados do vídeo (textos visíveis). Se o sistema mudar ou algum passo
não for encontrado, o robô NÃO trava: ele salva um print, pede para você fazer aquele passo
na janela do Chrome e continua dali.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from .config import Config
from .interacao import Periodo, Terminal
from .navegador import capturar_tela
from .planilha import Colaborador, sem_acento

RE_CADERNO = re.compile(r"#\s*ID\s*(\d+)\s*-\s*Caderno", re.I)
RE_VARIAVEL = re.compile(r"variavel", re.I)


class ColaboradorPulado(Exception):
    """Você escolheu pular o colaborador atual."""


def caminho_livre(destino: Path) -> Path:
    """Não sobrescreve: 'Allan.pdf' → 'Allan (2).pdf' se já existir."""
    if not destino.exists():
        return destino
    n = 2
    while (alternativa := destino.with_name(f"{destino.stem} ({n}){destino.suffix}")).exists():
        n += 1
    return alternativa


class ConnectMerchan:
    def __init__(self, page: Page, cfg: Config, log: logging.Logger, term: Terminal):
        self.page = page
        self.cfg = cfg
        self.log = log
        self.term = term

    # ---------- utilitários ----------

    def _ajuda(self, descricao: str, erro: Exception) -> None:
        self.log.warning("Não consegui %s (%s).", descricao, str(erro).splitlines()[0])
        try:
            self.log.warning("Print: %s", capturar_tela(self.page, self.cfg.pasta_saida, "ajuda"))
        except PlaywrightError:
            pass
        resposta = self.term.perguntar(
            f"  >> Faça você: {descricao}. Depois aperte Enter "
            "(ou digite 'pular' para pular este colaborador, 'sair' para encerrar)"
        )
        if resposta.lower() == "pular":
            raise ColaboradorPulado(descricao)

    def _passo(self, descricao: str, acao):
        try:
            return acao()
        except (PlaywrightError, PlaywrightTimeout, LookupError) as erro:
            self._ajuda(descricao, erro)
            return None

    def _aguardar_carregar(self) -> None:
        carregando = self.page.get_by_text(re.compile(r"^\s*Carregando", re.I))
        try:
            carregando.first.wait_for(state="visible", timeout=1500)
        except PlaywrightTimeout:
            pass
        carregando.first.wait_for(state="hidden", timeout=self.cfg.timeout_ms * 2)

    def _visivel(self, alvo: Locator) -> Locator:
        return alvo.locator("visible=true").first

    # ---------- navegação e filtros ----------

    def ir_para_pesquisas(self) -> None:
        def acao():
            url = urlparse(self.page.url)
            if not url.path.rstrip("/").endswith("/pesquisas"):
                self.page.goto(f"{url.scheme}://{url.netloc}/pesquisas")
            self.page.get_by_role("button", name=re.compile("Todos Filtros", re.I)).wait_for()

        self._passo("abrir a tela Pesquisas (menu Pesquisas → Painel de pesquisas)", acao)

    def _dialogo(self) -> Locator:
        return self.page.get_by_text("Selecione filtros").locator(
            "xpath=ancestor::*[.//button[normalize-space()='Aplicar']][1]"
        )

    def _preencher_data(self, dialogo: Locator, ordem: int, valor: str) -> None:
        campo = dialogo.get_by_text("Período Começo das Respostas").locator(
            f"xpath=following::input[{ordem}]"
        )
        campo.click()
        campo.press("Control+a")
        campo.press_sequentially(valor, delay=40)
        campo.press("Tab")

    def _escolher(self, dialogo: Locator, rotulo: str, opcao: re.Pattern, busca: str = "") -> None:
        dialogo.get_by_text(rotulo, exact=True).first.click()
        if busca:
            caixa = self.page.get_by_placeholder("Pesquisar").locator("visible=true")
            if caixa.count():
                caixa.first.fill(busca)
            else:
                self.page.keyboard.type(busca, delay=40)
        self._visivel(self.page.get_by_text(opcao)).click()
        dialogo.get_by_text("Selecione filtros").click()  # fecha a lista

    def aplicar_filtros(self, periodo: Periodo, colab: Colaborador) -> None:
        def acao():
            self.page.get_by_role("button", name=re.compile("Todos Filtros", re.I)).click()
            dialogo = self._dialogo()
            dialogo.wait_for()
            limpar = dialogo.get_by_text("Limpar", exact=True)
            if limpar.count() and limpar.first.is_visible():
                limpar.first.click()
            self._preencher_data(dialogo, 1, periodo.texto(periodo.inicio))
            self._preencher_data(dialogo, 2, periodo.texto(periodo.fim))
            self._escolher(dialogo, "Situação", re.compile(r"^\s*Respondida\s*$"))
            self._escolher(dialogo, "Tipo de formulário", re.compile(r"^\s*Pesquisa\s*$"))
            self._escolher(
                dialogo,
                "Colaborador",
                re.compile(rf"^\s*{colab.codigo}\s*-"),
                busca=colab.codigo,
            )
            dialogo.get_by_role("button", name="Aplicar").click()
            dialogo.wait_for(state="hidden")
            self._aguardar_carregar()

        self._passo(
            f"filtrar: Período Começo das Respostas {periodo.texto(periodo.inicio)} a "
            f"{periodo.texto(periodo.fim)}, Situação Respondida, Tipo Pesquisa, "
            f"Colaborador {colab.rotulo} → Aplicar",
            acao,
        )
        # Trava de segurança: nunca exportar com o colaborador errado no filtro.
        chip = self.page.get_by_text(re.compile(rf"Colaborador:\s*{colab.codigo}\b"))
        try:
            chip.first.wait_for(timeout=5000)
        except PlaywrightTimeout:
            self._ajuda(f"conferir se o filtro está no colaborador {colab.rotulo}", LookupError(
                "não achei o filtro do colaborador na tela"
            ))

    def mostrar_100_por_pagina(self) -> None:
        def acao():
            rotulo = self.page.get_by_text("Registros por página")
            if not rotulo.count():
                return
            seletor = rotulo.first.locator("xpath=preceding-sibling::*[1]")
            if "100" in seletor.inner_text():
                return
            seletor.click()
            self._visivel(self.page.get_by_text("100", exact=True)).click()
            self._aguardar_carregar()

        self._passo("mudar a lista para 100 registros por página", acao)

    # ---------- seleção e exportação ----------

    def marcar_variavel(self) -> int:
        """Marca só as pesquisas cujo nome contém 'Variavel'. Devolve quantas marcou (-1 = manual)."""

        def acao() -> int:
            linhas = self.page.locator("table tbody tr")
            linhas.first.wait_for(timeout=self.cfg.timeout_ms)
            marcadas = 0
            for i in range(linhas.count()):
                linha = linhas.nth(i)
                caixa = linha.get_by_role("checkbox").first
                if not caixa.count():
                    continue
                quer = bool(RE_VARIAVEL.search(sem_acento(linha.inner_text())))
                if caixa.is_checked() != quer:
                    try:
                        caixa.set_checked(quer)
                    except PlaywrightError:
                        caixa.click(force=True)
                marcadas += quer
            total = self.page.get_by_text(re.compile(r"^\s*\d+\s+Respondidas?\s*$"))
            if total.count():
                qtd = int(re.search(r"\d+", total.first.inner_text())[0])
                if qtd > linhas.count():
                    raise LookupError(
                        f"há {qtd} pesquisas e só {linhas.count()} na página — confira as outras páginas"
                    )
            return marcadas

        resultado = self._passo("marcar apenas as pesquisas 'Variavel …'", acao)
        return -1 if resultado is None else resultado

    def _painel_aberto(self) -> bool:
        return self.page.get_by_text("Relatórios", exact=True).locator("visible=true").count() > 0

    def abrir_relatorios(self) -> bool:
        if self._painel_aberto():
            return True
        try:
            self.page.locator(self.cfg.seletor_relatorios).locator("visible=true").first.click(
                timeout=3000
            )
            self.page.get_by_text("Relatórios", exact=True).first.wait_for(timeout=3000)
        except PlaywrightError:
            return False
        return True

    def fechar_relatorios(self) -> None:
        if self._painel_aberto():
            self.page.keyboard.press("Escape")
            if self._painel_aberto():
                self.page.get_by_text("Todas as pesquisas").first.click()

    def ids_cadernos(self) -> set[int] | None:
        """IDs dos 'Caderno Pesquisas Pdf' já listados no painel Relatórios (None = não consegui ver)."""
        try:
            if not self.abrir_relatorios():
                return None
            self.page.wait_for_timeout(800)
            textos = self.page.get_by_text(RE_CADERNO).all_inner_texts()
            return {int(m[1]) for t in textos if (m := RE_CADERNO.search(t))}
        except PlaywrightError:
            return None

    def exportar_caderno(self) -> None:
        def acao():
            self.page.get_by_role("button", name=re.compile(r"^\s*Exportar", re.I)).click()
            self._visivel(
                self.page.get_by_text(re.compile(r"Export do Caderno\s*\(PDF\)", re.I))
            ).click()

        self._passo("clicar em Exportar → 7. Export do Caderno (PDF)", acao)

    def _tentar_baixar(self, antes: set[int] | None):
        if not self.abrir_relatorios():
            return None
        ids = sorted(
            {int(m[1]) for t in self.page.get_by_text(RE_CADERNO).all_inner_texts()
             if (m := RE_CADERNO.search(t))},
            reverse=True,
        )
        novos = [i for i in ids if antes is None or i not in antes]
        if not novos:
            return None
        item = self.page.get_by_text(re.compile(rf"#\s*ID\s*{novos[0]}\b")).first
        linha = item.locator("xpath=ancestor-or-self::*[.//a or .//button][1]")
        try:
            with self.page.expect_download(timeout=8000) as espera:
                linha.locator("a, button").last.click()
            self.log.info("Baixando o relatório #ID %s.", novos[0])
            return espera.value
        except PlaywrightTimeout:
            return None  # ainda está sendo gerado

    def baixar_caderno(self, antes: set[int] | None, destino: Path) -> Path:
        prazo = time.monotonic() + self.cfg.timeout_relatorio_s
        download = None
        while download is None and time.monotonic() < prazo:
            try:
                download = self._tentar_baixar(antes)
            except PlaywrightError as erro:
                self.log.debug("Ainda não deu para baixar: %s", erro)
            if download is None:
                self.page.wait_for_timeout(4000)

        if download is None:
            self.log.warning("Não consegui baixar sozinho. Print: %s",
                             capturar_tela(self.page, self.cfg.pasta_saida, "ajuda"))
            self.term.mostrar(
                "  >> Faça você: no painel Relatórios (topo da tela), clique para baixar o "
                "caderno NOVO. Estou esperando o download…"
            )
            with self.page.expect_download(timeout=self.cfg.timeout_relatorio_s * 1000) as espera:
                pass
            download = espera.value

        destino.parent.mkdir(parents=True, exist_ok=True)
        final = caminho_livre(destino)
        download.save_as(final)
        return final

    # ---------- um colaborador do começo ao fim ----------

    def processar(self, colab: Colaborador, periodo: Periodo, pasta_base: Path) -> str:
        self.ir_para_pesquisas()
        self.aplicar_filtros(periodo, colab)
        self.mostrar_100_por_pagina()
        marcadas = self.marcar_variavel()
        if marcadas == 0:
            return "sem pesquisa de variável"
        antes = self.ids_cadernos()
        self.fechar_relatorios()
        self.exportar_caderno()
        arquivo = self.baixar_caderno(antes, pasta_base / colab.pasta / f"{colab.arquivo}.pdf")
        self.fechar_relatorios()
        qtd = "?" if marcadas < 0 else str(marcadas)
        self.log.info("Salvo: %s (%s pesquisas de variável).", arquivo, qtd)
        return f"ok → {arquivo}"
