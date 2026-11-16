"""Roteiro do robô: perguntas iniciais e um colaborador de cada vez."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from .config import Config, area_de_trabalho
from .connect import ColaboradorPulado, ConnectMerchan
from .interacao import Periodo, Terminal
from .navegador import capturar_tela
from .planilha import Colaborador, ler_planilha


@dataclass(frozen=True)
class Plano:
    periodo: Periodo
    pasta_base: Path
    colaboradores: list[Colaborador]


def preparar(cfg: Config, log: logging.Logger, term: Terminal, hoje: date | None = None) -> Plano | None:
    """Perguntas feitas ANTES de abrir o Chrome (período, pasta e quem puxar)."""
    colaboradores = ler_planilha(cfg.planilha)
    log.info("Planilha: %d colaboradores.", len(colaboradores))

    periodo = term.perguntar_periodo(hoje or date.today())
    pasta_base: Path = area_de_trabalho(cfg) / term.perguntar_pasta_mae(periodo)
    escolhidos = term.escolher_colaboradores(colaboradores)

    term.mostrar(
        f"\nVou puxar {len(escolhidos)} colaborador(es), período "
        f"{periodo.texto(periodo.inicio)} a {periodo.texto(periodo.fim)}, salvando em {pasta_base}"
    )
    if not term.confirmar("Abrir o Chrome e começar?"):
        log.info("Cancelado antes de começar.")
        return None
    return Plano(periodo, pasta_base, escolhidos)


def executar(page: Page, cfg: Config, log: logging.Logger, term: Terminal, plano: Plano) -> list[tuple[str, str]]:
    robo = ConnectMerchan(page, cfg, log, term)
    resumo: list[tuple[str, str]] = []
    total = len(plano.colaboradores)
    for n, colab in enumerate(plano.colaboradores, 1):
        log.info("[%d/%d] %s (%s)", n, total, colab.rotulo, colab.pasta)
        try:
            situacao = robo.processar(colab, plano.periodo, plano.pasta_base)
        except ColaboradorPulado as passo:
            situacao = f"pulado por você ({passo})"
        except (PlaywrightError, TimeoutError) as erro:
            situacao = f"ERRO: {str(erro).splitlines()[0]}"
            log.exception("Erro com %s.", colab.rotulo)
            try:
                log.error("Print: %s", capturar_tela(page, cfg.pasta_saida, "erro"))
            except PlaywrightError:
                pass
        log.info("  → %s", situacao)
        resumo.append((colab.rotulo, situacao))

    _gravar_resumo(cfg, resumo, log)
    term.chamar_atencao()
    return resumo


def _gravar_resumo(cfg: Config, resumo: list[tuple[str, str]], log: logging.Logger) -> None:
    cfg.pasta_saida.mkdir(parents=True, exist_ok=True)
    arquivo = cfg.pasta_saida / f"{datetime.now():%Y-%m-%d_%H-%M-%S}_resumo.txt"
    linhas = [f"{nome}: {situacao}" for nome, situacao in resumo]
    arquivo.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    ok = sum(s.startswith("ok") for _, s in resumo)
    log.info("RESUMO: %d de %d salvos. Detalhes em %s", ok, len(resumo), arquivo)
    for linha in linhas:
        if not linha.split(": ", 1)[1].startswith("ok"):
            log.warning("  %s", linha)
