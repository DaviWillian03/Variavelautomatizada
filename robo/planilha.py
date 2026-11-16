"""Leitura da planilha de colaboradores (código, nome e supervisor)."""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import openpyxl

PROIBIDOS_EM_ARQUIVO = re.compile(r'[<>:"/\\|?*]')
PARTICULAS = {"de", "da", "do", "dos", "das", "e"}


def sem_acento(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )


def _cabecalho(valor) -> str:
    return re.sub(r"[^a-z]", "", sem_acento(str(valor or "")).lower())


@dataclass(frozen=True)
class Colaborador:
    codigo: str
    nome: str
    supervisor: str
    pasta: str  # ex.: "V EMI"
    arquivo: str  # nome do PDF sem extensão, ex.: "Allan"

    @property
    def rotulo(self) -> str:
        """Como aparece no filtro do sistema: '1710 - Allan Vidal Nunes de Oliveira'."""
        return f"{self.codigo} - {self.nome}"


def pasta_do_supervisor(supervisor: str) -> str:
    """'Emiliane Kelly…' → 'V EMI'; 'Flavio …' → 'V FLA'; 'Ruan …' → 'V RUA'."""
    letras = re.sub(r"[^A-Z]", "", sem_acento(supervisor).upper())
    if not letras:
        raise ValueError(f"Supervisor sem nome: {supervisor!r}")
    return f"V {letras[:3]}"


def _nomes_de_arquivo(lista: list[tuple[str, str]]) -> list[str]:
    """Primeiro nome; se repetir na mesma pasta, usa nome + sobrenome (e assim por diante)."""
    partes = [
        (pasta, [p for i, p in enumerate(nome.split()) if i == 0 or p.lower() not in PARTICULAS])
        for pasta, nome in lista
    ]
    tamanho = [1] * len(partes)
    while True:
        atuais = [
            (pasta, " ".join(p[: tamanho[i]]).title()) for i, (pasta, p) in enumerate(partes)
        ]
        contagem = Counter(atuais)
        repetidos = [
            i
            for i, chave in enumerate(atuais)
            if contagem[chave] > 1 and tamanho[i] < len(partes[i][1])
        ]
        if not repetidos:
            return [PROIBIDOS_EM_ARQUIVO.sub("", nome) for _, nome in atuais]
        for i in repetidos:
            tamanho[i] += 1


def ler_planilha(caminho: Path) -> list[Colaborador]:
    if not caminho.exists():
        raise FileNotFoundError(
            f"Planilha não encontrada: {caminho}. Coloque a lista de colaboradores nesse lugar "
            "(ou ajuste PLANILHA no arquivo .env)."
        )
    planilha = openpyxl.load_workbook(caminho, read_only=True, data_only=True).active
    linhas = planilha.iter_rows(values_only=True)
    cabecalho = [_cabecalho(c) for c in next(linhas)]

    def coluna(*nomes: str) -> int:
        for nome in nomes:
            if nome in cabecalho:
                return cabecalho.index(nome)
        raise ValueError(
            f"A planilha precisa de uma coluna {nomes[0]!r}. Colunas encontradas: {cabecalho}"
        )

    i_cod = coluna("codcolaborador", "codigo", "cod")
    i_nome = coluna("nome", "colaborador", "promotor")
    i_sup = coluna("nomesuperior", "superior", "supervisor")

    brutos: list[tuple[str, str, str]] = []
    for linha in linhas:
        if not linha or not any(linha):
            continue
        cod, nome, sup = linha[i_cod], linha[i_nome], linha[i_sup]
        if cod is None or not nome or not sup:
            raise ValueError(f"Linha incompleta na planilha: {linha}")
        codigo = str(int(cod)) if isinstance(cod, float) else str(cod).strip()
        brutos.append((codigo, " ".join(str(nome).split()), " ".join(str(sup).split())))

    pastas = [pasta_do_supervisor(sup) for _, _, sup in brutos]
    arquivos = _nomes_de_arquivo([(p, nome) for p, (_, nome, _) in zip(pastas, brutos)])
    return [
        Colaborador(codigo, nome, sup, pasta, arquivo)
        for (codigo, nome, sup), pasta, arquivo in zip(brutos, pastas, arquivos)
    ]
