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

_VARIANTES = {"a": "aáàâã", "e": "eéê", "i": "ií", "o": "oóôõ", "u": "uú", "c": "cç"}


def rx(texto: str, inteiro: bool = False) -> re.Pattern:
    """Regex que acha o texto com ou sem acento e sem diferenciar maiúsculas
    (o sistema escreve 'Periodo', 'formulario', 'Inicio'…)."""
    partes = []
    for letra in sem_acento(texto).lower():
        if letra in _VARIANTES:
            partes.append(f"[{_VARIANTES[letra]}]")
        elif letra.isspace():
            partes.append(r"\s+")
        else:
            partes.append(re.escape(letra))
    corpo = "".join(partes)
    return re.compile(rf"^\s*{corpo}\s*$" if inteiro else corpo, re.I)


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
        page.set_default_timeout(min(cfg.timeout_ms, 12_000))

    # ---------- utilitários ----------

    def _ajuda(self, descricao: str, erro: Exception) -> None:
        self.log.warning("Não consegui %s (%s).", descricao, str(erro).splitlines()[0])
        try:
            print_ = capturar_tela(self.page, self.cfg.pasta_saida, "ajuda")
            self.log.warning("Print: %s", print_)
            self._salvar_estrutura(print_.with_suffix(".html"))
        except PlaywrightError:
            pass
        resposta = self.term.perguntar(
            f"  >> Faça você: {descricao}. Depois aperte Enter "
            "(ou digite 'pular' para pular este colaborador, 'sair' para encerrar)"
        )
        if resposta.lower() == "pular":
            raise ColaboradorPulado(descricao)

    def _salvar_estrutura(self, arquivo: Path) -> None:
        """Guarda o HTML da janela de filtros (ou do painel/lista visível) para ajustar o robô."""
        try:
            dialogo = self._dialogo()
            if dialogo.count() and dialogo.first.is_visible():
                alvo = dialogo.first
            else:  # lista de pesquisas + rodapé (Registros por página, Exportar)
                alvo = self.page.get_by_text(rx("Todas as pesquisas")).first.locator(
                    "xpath=ancestor::*[.//*[contains(., 'Exportar')]][1]"
                )
            html = alvo.evaluate("e => e.outerHTML") if alvo.count() else None
            if html:
                arquivo.write_text(html, encoding="utf-8")
                self.log.warning("Estrutura da tela salva em %s", arquivo)
        except (PlaywrightError, OSError):
            pass

    def _passo(self, descricao: str, acao):
        try:
            return acao()
        except (PlaywrightError, PlaywrightTimeout, LookupError) as erro:
            self._ajuda(descricao, erro)
            return None

    def _aguardar_carregar(self) -> None:
        carregando = self.page.get_by_text(rx("Carregando"))
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
        return self.page.get_by_text(rx("Selecione filtros")).locator(
            "xpath=ancestor::*[.//button[normalize-space()='Aplicar']][1]"
        )

    def _preencher_data(self, ordem: int, valor: str) -> None:
        campo = self._dialogo().get_by_text(rx("Periodo Comeco das Respostas")).locator(
            f"xpath=following::input[{ordem}]"
        )
        campo.click()
        campo.press("Control+a")
        campo.press_sequentially(valor, delay=60)
        campo.press("Tab")

    def _escolher(self, rotulo: str, opcao: re.Pattern, termo: str) -> None:
        """Abre a lista do campo, digita na caixa 'Pesquisar' e marca a opção.

        As listas do filtro têm uma caixa 'Pesquisar' e checkboxes. Digitar antes deixa só a
        opção certa à vista (e evita clicar num texto igual que está atrás da janela).
        """
        dialogo = self._dialogo()
        campo = dialogo.get_by_text(rx(rotulo, inteiro=True)).locator("visible=true")
        if not campo.count():
            raise LookupError(f"não achei o campo '{rotulo}' na janela de filtros")
        try:
            campo.first.click(timeout=4000)
        except PlaywrightTimeout:
            # há uma camada por cima do texto (a caixa onde se digita): clica na posição dele
            campo.first.click(force=True)
        self.page.wait_for_timeout(500)
        caixa = self.page.get_by_placeholder(rx("Pesquisar")).locator("visible=true")
        if caixa.count():
            caixa.last.fill(termo)
        else:
            self.page.keyboard.type(termo, delay=60)
        self.page.wait_for_timeout(800)  # a lista filtra enquanto digita

        marcar = self.page.get_by_role("checkbox", name=opcao).locator("visible=true")
        if marcar.count():
            alvo = marcar.last
            if not alvo.is_checked():
                try:
                    alvo.check()
                except PlaywrightError:
                    self.page.get_by_text(opcao).locator("visible=true").last.click()
            if not alvo.is_checked():
                raise LookupError(f"a opção de '{rotulo}' não ficou marcada")
        else:
            opcoes = self.page.get_by_text(opcao).locator("visible=true")
            opcoes.last.wait_for(timeout=8000)  # a lista pode demorar para buscar
            opcoes.last.click()
        dialogo.get_by_text(rx("Selecione filtros")).first.click()  # fecha a lista
        self.page.wait_for_timeout(300)

    def aplicar_filtros(self, periodo: Periodo, colab: Colaborador) -> None:
        def abrir():
            self.page.get_by_role("button", name=rx("Todos Filtros")).click()
            self._dialogo().wait_for()
            limpar = self._dialogo().get_by_text(rx("Limpar", inteiro=True))
            if limpar.count() and limpar.first.is_visible():
                limpar.first.click()

        def aplicar():
            self._dialogo().get_by_role("button", name=rx("Aplicar", inteiro=True)).click()
            self._dialogo().wait_for(state="hidden")

        inicio, fim = periodo.texto(periodo.inicio), periodo.texto(periodo.fim)
        self._passo("clicar em 'Todos Filtros'", abrir)
        self._passo(
            f"em 'Periodo Começo das Respostas', preencher Data Inicio = {inicio}",
            lambda: self._preencher_data(1, inicio),
        )
        self._passo(
            f"em 'Periodo Começo das Respostas', preencher Data Fim = {fim}",
            lambda: self._preencher_data(2, fim),
        )
        self._passo(
            "em 'Situação', marcar Respondida",
            lambda: self._escolher("Situação", rx("Respondida", inteiro=True), "Respondida"),
        )
        self._passo(
            "em 'Tipo de formulario', escolher Pesquisa",
            lambda: self._escolher("Tipo de formulario", rx("Pesquisa", inteiro=True), "Pesquisa"),
        )
        self._passo(
            f"em 'Colaborador', escolher {colab.rotulo}",
            lambda: self._escolher(
                "Colaborador", re.compile(rf"^\s*{colab.codigo}\s*-"), colab.codigo
            ),
        )
        self._passo("clicar em 'Aplicar'", aplicar)
        self._aguardar_carregar()

        # Trava de segurança: nunca exportar com o colaborador errado no filtro.
        chip = self.page.get_by_text(re.compile(rf"Colaborador:\s*{colab.codigo}\b", re.I))
        try:
            chip.first.wait_for(timeout=5000)
        except PlaywrightTimeout:
            self._ajuda(f"conferir se o filtro está no colaborador {colab.rotulo}", LookupError(
                "não achei o filtro do colaborador na tela"
            ))

    def mostrar_100_por_pagina(self) -> None:
        def acao():
            rotulo = self.page.get_by_text(rx("Registros por pagina")).locator("visible=true")
            if not rotulo.count():
                raise LookupError("não achei 'Registros por página'")
            perto = rotulo.first.locator(
                "xpath=ancestor::*[.//select or .//*[@role='combobox' or @role='button']][1]"
            )
            nativo = perto.locator("select")
            if nativo.count():
                nativo.first.select_option("100")
            else:
                seletor = perto.locator("[role='combobox'], [role='button']").filter(
                    has_text=re.compile(r"^\s*\d+\s*$")
                ).first
                if seletor.inner_text().strip() == "100":
                    return
                seletor.click()
                opcao = self.page.get_by_role("option", name=re.compile(r"^\s*100\s*$"))
                if opcao.count():
                    opcao.first.click()
                else:
                    self._visivel(self.page.get_by_text("100", exact=True)).click()
            self._aguardar_carregar()
            self.page.wait_for_timeout(1000)

        self._passo("mudar 'Registros por página' para 100", acao)

    # ---------- seleção e exportação ----------

    def _linhas(self) -> Locator:
        """Linhas de dados da lista 'Todas as pesquisas' (tabela comum ou grade com role=row)."""
        grade = self.page.get_by_role("row").filter(
            has=self.page.locator("[role='gridcell'], [role='cell'], td")
        )
        return grade if grade.count() else self.page.locator("table tbody tr")

    def marcar_variavel(self) -> int:
        """Marca só as pesquisas cujo nome contém 'Variavel'. Devolve quantas marcou (-1 = manual)."""

        def acao() -> int:
            self._linhas().first.wait_for(timeout=self.cfg.timeout_ms)
            linhas = self._linhas()
            marcadas = 0
            for i in range(linhas.count()):
                linha = linhas.nth(i)
                caixa = linha.get_by_role("checkbox")
                if not caixa.count():
                    caixa = linha.locator("input[type='checkbox']")
                if not caixa.count():
                    continue
                caixa = caixa.first
                quer = bool(RE_VARIAVEL.search(sem_acento(linha.inner_text())))
                if caixa.is_checked() != quer:
                    try:
                        caixa.set_checked(quer, timeout=4000)
                    except PlaywrightError:
                        caixa.click(force=True)
                if caixa.is_checked() != quer:
                    raise LookupError(f"não consegui {'marcar' if quer else 'desmarcar'} a linha {i + 1}")
                marcadas += quer
            self.log.info("Linhas na lista: %d; marcadas (Variavel): %d.", linhas.count(), marcadas)
            total = self.page.get_by_text(re.compile(r"^\s*\d+\s+Respondidas?\s*$"))
            if total.count():
                qtd = int(re.search(r"\d+", total.first.inner_text())[0])
                if qtd > linhas.count():
                    self.log.warning(
                        "O sistema mostra %d respondidas e a lista tem %d linhas — confira se "
                        "há outra página.", qtd, linhas.count()
                    )
            return marcadas

        resultado = self._passo(
            "marcar apenas as pesquisas 'Variavel …' (e desmarcar as outras)", acao
        )
        return -1 if resultado is None else resultado

    def _painel_aberto(self) -> bool:
        return self.page.get_by_text(rx("Relatorios", inteiro=True)).locator("visible=true").count() > 0

    def abrir_relatorios(self) -> bool:
        if self._painel_aberto():
            return True
        try:
            self.page.locator(self.cfg.seletor_relatorios).locator("visible=true").first.click(
                timeout=3000
            )
            self.page.get_by_text(rx("Relatorios", inteiro=True)).first.wait_for(timeout=3000)
        except PlaywrightError:
            return False
        return True

    def fechar_relatorios(self) -> None:
        if self._painel_aberto():
            self.page.keyboard.press("Escape")
            if self._painel_aberto():
                self.page.get_by_text(rx("Todas as pesquisas")).first.click()

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
                self.page.get_by_text(rx("Export do Caderno (PDF)"))
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
