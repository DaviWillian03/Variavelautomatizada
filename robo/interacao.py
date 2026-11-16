"""Perguntas feitas no terminal ao iniciar o robô."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Callable

from .planilha import Colaborador

MESES = (
    "Janeiro Fevereiro Março Abril Maio Junho Julho Agosto Setembro Outubro Novembro Dezembro"
).split()


class Sair(Exception):
    """A pessoa pediu para encerrar o robô."""


@dataclass(frozen=True)
class Periodo:
    inicio: date
    fim: date

    def texto(self, d: date) -> str:
        return d.strftime("%d/%m/%Y")


def periodo_sugerido(hoje: date) -> Periodo:
    """Quinzena fechada mais recente: dia 16 → 01 a 15 do mês; dia 1 a 15 → 16 ao fim do mês anterior."""
    if hoje.day >= 16:
        return Periodo(hoje.replace(day=1), hoje.replace(day=15))
    ano, mes = (hoje.year, hoje.month - 1) if hoje.month > 1 else (hoje.year - 1, 12)
    return Periodo(date(ano, mes, 16), date(ano, mes, calendar.monthrange(ano, mes)[1]))


def interpretar_selecao(texto: str, colaboradores: list[Colaborador]) -> list[Colaborador]:
    """'' ou 'todos' → todos; 'EMI' → pasta V EMI; '1,3,5-8' → por número da lista."""
    texto = texto.strip().upper()
    if texto in ("", "TODOS", "T"):
        return list(colaboradores)
    pastas = {c.pasta.removeprefix("V ") for c in colaboradores}
    escolhidos: list[int] = []
    for parte in re.split(r"[,\s;]+", texto):
        if not parte:
            continue
        if parte in pastas:
            escolhidos += [i for i, c in enumerate(colaboradores) if c.pasta == f"V {parte}"]
        elif m := re.fullmatch(r"(\d+)-(\d+)", parte):
            a, b = int(m[1]), int(m[2])
            escolhidos += list(range(min(a, b) - 1, max(a, b)))
        elif parte.isdigit():
            escolhidos.append(int(parte) - 1)
        else:
            raise ValueError(f"Não entendi {parte!r}.")
    if any(i < 0 or i >= len(colaboradores) for i in escolhidos):
        raise ValueError(f"Use números de 1 a {len(colaboradores)}.")
    return [colaboradores[i] for i in dict.fromkeys(escolhidos)]


class Terminal:
    def __init__(self, entrada: Callable[[str], str] = input, saida: Callable[[str], None] = print):
        self._entrada = entrada
        self.mostrar = saida

    def perguntar(self, mensagem: str, padrao: str | None = None) -> str:
        sufixo = f" [{padrao}]" if padrao else ""
        resposta = self._entrada(f"{mensagem}{sufixo}: ").strip()
        if resposta.lower() == "sair":
            raise Sair("Encerrado por você.")
        return resposta or (padrao or "")

    def confirmar(self, mensagem: str) -> bool:
        return self.perguntar(f"{mensagem} (s/n)", "s").lower().startswith("s")

    def _data(self, mensagem: str, padrao: date) -> date:
        while True:
            texto = self.perguntar(mensagem, padrao.strftime("%d/%m/%Y"))
            try:
                return datetime.strptime(texto, "%d/%m/%Y").date()
            except ValueError:
                self.mostrar("  Data inválida. Use DD/MM/AAAA, por exemplo 01/11/2026.")

    def perguntar_periodo(self, hoje: date) -> Periodo:
        sugestao = periodo_sugerido(hoje)
        self.mostrar("\nPeríodo das respostas (Enter aceita o valor entre colchetes):")
        while True:
            inicio = self._data("  Data início", sugestao.inicio)
            fim = self._data("  Data fim", sugestao.fim)
            if inicio <= fim:
                return Periodo(inicio, fim)
            self.mostrar("  A data início precisa ser antes da data fim.")

    def perguntar_pasta_mae(self, periodo: Periodo) -> str:
        padrao = f"Variavel {MESES[periodo.inicio.month - 1]}"
        self.mostrar("\nPasta na Área de Trabalho onde ficam V EMI / V FLA / V RUA:")
        return self.perguntar("  Nome da pasta", padrao)

    def escolher_colaboradores(self, colaboradores: list[Colaborador]) -> list[Colaborador]:
        self.mostrar("\nColaboradores da planilha:")
        for i, c in enumerate(colaboradores, 1):
            self.mostrar(f"  {i:>3}. [{c.pasta}] {c.rotulo}")
        self.mostrar(
            "\nQuem vamos puxar? Enter = todos | EMI, FLA ou RUA = do supervisor | "
            "números, ex.: 1,4,10-15"
        )
        while True:
            try:
                escolhidos = interpretar_selecao(self.perguntar("  Escolha"), colaboradores)
            except ValueError as erro:
                self.mostrar(f"  {erro}")
                continue
            if escolhidos:
                return escolhidos
            self.mostrar("  Nenhum colaborador escolhido.")
