"""Testes da janela de início (caixinhas). Pulados se não houver tkinter/tela."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import openpyxl
import pytest

from robo.interacao import Periodo
from robo.janela import JanelaInicio, janela_disponivel
from robo.planilha import ler_planilha

pytestmark = pytest.mark.skipif(not janela_disponivel(), reason="sem tkinter ou sem tela")


@pytest.fixture
def janela(tmp_path: Path):
    import tkinter as tk

    livro = openpyxl.Workbook()
    aba = livro.active
    aba.append(["Cod. Colaborador", "Nome", "Usuario", "Nome Superior"])
    aba.append([1001, "Ana Teste Souza", "a", "Emiliane Exemplo"])
    aba.append([1002, "Bruno Exemplo Lima", "b", "Emiliane Exemplo"])
    aba.append([1003, "Carla Ficticia Dias", "c", "Ruan Exemplo"])
    aba.append([1005, "Davi Teste Rocha", "d", "Flávio Exemplo"])
    livro.save(tmp_path / "c.xlsx")

    raiz = tk.Tk()
    j = JanelaInicio(raiz, ler_planilha(tmp_path / "c.xlsx"),
                     Periodo(date(2026, 11, 1), date(2026, 11, 15)))
    j.avisos = []
    j._avisar = j.avisos.append  # sem caixa de mensagem nos testes
    yield j
    try:
        raiz.destroy()
    except tk.TclError:
        pass


def test_comeca_sem_ninguem_marcado(janela):
    assert janela.escolhidos() == []
    assert janela.pasta.get() == "Variavel Novembro"
    assert janela.inicio.get() == "01/11/2026" and janela.fim.get() == "15/11/2026"


def test_selecionar_todos_e_desmarcar(janela):
    janela.todos.set(True)
    janela._marcar_todos()
    assert len(janela.escolhidos()) == 4
    assert all(v.get() for v in janela.grupo.values())
    janela.todos.set(False)
    janela._marcar_todos()
    assert janela.escolhidos() == []


def test_todos_de_um_supervisor(janela):
    janela.grupo["V EMI"].set(True)
    janela._marcar_grupo("V EMI")
    assert [c.codigo for c in janela.escolhidos()] == ["1001", "1002"]
    assert not janela.todos.get()
    # desmarcar um da Emiliane desmarca o "todos de Emiliane"
    janela.marcado["1002"].set(False)
    janela._sincronizar()
    assert not janela.grupo["V EMI"].get()


def test_marcar_um_a_um_completa_o_todos(janela):
    for var in janela.marcado.values():
        var.set(True)
    janela._sincronizar()
    assert janela.todos.get()


def test_confirmar_valida_e_devolve_escolha(janela):
    janela.confirmar()
    assert janela.avisos == ["Marque pelo menos um colaborador."]
    janela.marcado["1003"].set(True)
    janela.inicio.set("31/02/2026")
    janela.confirmar()
    assert "Data inválida" in janela.avisos[-1]
    janela.inicio.set("16/11/2026")
    janela.fim.set("30/11/2026")
    janela.confirmar()
    periodo, pasta, escolhidos = janela.resultado
    assert (periodo.inicio, periodo.fim) == (date(2026, 11, 16), date(2026, 11, 30))
    assert pasta == "Variavel Novembro"
    assert [c.codigo for c in escolhidos] == ["1003"]


def test_pasta_acompanha_o_mes_da_data(janela):
    janela.inicio.set("01/12/2026")
    assert janela.pasta.get() == "Variavel Dezembro"
