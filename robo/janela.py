"""Janela de início: período, pasta e colaboradores com caixinhas de marcar.

Usa o tkinter, que já vem com o Python do Windows. Se não estiver disponível, o robô
volta para as perguntas no terminal.
"""

from __future__ import annotations

from datetime import date, datetime
from itertools import groupby

from .interacao import MESES, Periodo
from .planilha import Colaborador

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # Python sem tkinter
    tk = None


def janela_disponivel() -> bool:
    if tk is None:
        return False
    try:
        raiz = tk.Tk()
        raiz.destroy()
        return True
    except tk.TclError:  # sem tela (ex.: servidor)
        return False


class JanelaInicio:
    """Monta a janela. `confirmar()` valida e guarda o resultado em `self.resultado`."""

    def __init__(self, raiz, colaboradores: list[Colaborador], sugestao: Periodo):
        self.raiz = raiz
        self.colaboradores = colaboradores
        self.resultado: tuple[Periodo, str, list[Colaborador]] | None = None
        self._pasta_editada = False

        raiz.title("Robô da Variável")
        raiz.resizable(True, True)
        quadro = ttk.Frame(raiz, padding=12)
        quadro.pack(fill="both", expand=True)

        # período e pasta
        topo = ttk.LabelFrame(quadro, text="Período das respostas e pasta", padding=8)
        topo.pack(fill="x")
        self.inicio = tk.StringVar(value=sugestao.inicio.strftime("%d/%m/%Y"))
        self.fim = tk.StringVar(value=sugestao.fim.strftime("%d/%m/%Y"))
        self.pasta = tk.StringVar(value=self._pasta_sugerida())
        ttk.Label(topo, text="Data início").grid(row=0, column=0, sticky="w")
        ttk.Entry(topo, textvariable=self.inicio, width=12).grid(row=0, column=1, padx=(4, 16))
        ttk.Label(topo, text="Data fim").grid(row=0, column=2, sticky="w")
        ttk.Entry(topo, textvariable=self.fim, width=12).grid(row=0, column=3, padx=(4, 16))
        ttk.Label(topo, text="Pasta na Área de Trabalho").grid(row=0, column=4, sticky="w")
        entrada_pasta = ttk.Entry(topo, textvariable=self.pasta, width=24)
        entrada_pasta.grid(row=0, column=5, padx=(4, 0))
        entrada_pasta.bind("<Key>", lambda _e: setattr(self, "_pasta_editada", True))
        self.inicio.trace_add("write", lambda *_: self._atualizar_pasta())

        # colaboradores
        meio = ttk.LabelFrame(quadro, text="Quem vamos puxar?", padding=8)
        meio.pack(fill="both", expand=True, pady=(10, 0))
        self.todos = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            meio, text="Selecionar todos", variable=self.todos, command=self._marcar_todos
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        self.marcado: dict[str, tk.BooleanVar] = {}
        self.grupo: dict[str, tk.BooleanVar] = {}
        por_pasta = groupby(sorted(colaboradores, key=lambda c: c.pasta), key=lambda c: c.pasta)
        for coluna, (pasta, membros) in enumerate(por_pasta):
            membros = list(membros)
            caixa = ttk.Frame(meio)
            caixa.grid(row=1, column=coluna, sticky="nw", padx=(0, 18))
            supervisor = membros[0].supervisor.split()[0]
            self.grupo[pasta] = tk.BooleanVar(value=False)
            ttk.Checkbutton(
                caixa,
                text=f"{pasta} — todos de {supervisor}",
                variable=self.grupo[pasta],
                command=lambda p=pasta: self._marcar_grupo(p),
            ).pack(anchor="w", pady=(0, 4))
            ttk.Separator(caixa).pack(fill="x", pady=(0, 4))
            for colab in membros:
                self.marcado[colab.codigo] = tk.BooleanVar(value=False)
                ttk.Checkbutton(
                    caixa,
                    text=colab.rotulo,
                    variable=self.marcado[colab.codigo],
                    command=self._sincronizar,
                ).pack(anchor="w")

        # rodapé
        baixo = ttk.Frame(quadro)
        baixo.pack(fill="x", pady=(10, 0))
        self.contador = ttk.Label(baixo, text="")
        self.contador.pack(side="left")
        ttk.Button(baixo, text="Cancelar", command=self.cancelar).pack(side="right")
        ttk.Button(baixo, text="Abrir o Chrome e começar", command=self.confirmar).pack(
            side="right", padx=(0, 8)
        )
        self._sincronizar()

    # ---------- marcação ----------

    def _membros(self, pasta: str) -> list[Colaborador]:
        return [c for c in self.colaboradores if c.pasta == pasta]

    def _marcar_todos(self) -> None:
        for var in self.marcado.values():
            var.set(self.todos.get())
        self._sincronizar()

    def _marcar_grupo(self, pasta: str) -> None:
        for colab in self._membros(pasta):
            self.marcado[colab.codigo].set(self.grupo[pasta].get())
        self._sincronizar()

    def _sincronizar(self) -> None:
        for pasta, var in self.grupo.items():
            var.set(all(self.marcado[c.codigo].get() for c in self._membros(pasta)))
        self.todos.set(all(v.get() for v in self.marcado.values()))
        qtd = len(self.escolhidos())
        self.contador.config(text=f"{qtd} de {len(self.colaboradores)} selecionado(s)")

    def escolhidos(self) -> list[Colaborador]:
        return [c for c in self.colaboradores if self.marcado[c.codigo].get()]

    # ---------- pasta e datas ----------

    def _pasta_sugerida(self) -> str:
        try:
            mes = datetime.strptime(self.inicio.get(), "%d/%m/%Y").month
        except ValueError:
            mes = date.today().month
        return f"Variavel {MESES[mes - 1]}"

    def _atualizar_pasta(self) -> None:
        if not self._pasta_editada:
            self.pasta.set(self._pasta_sugerida())

    def _avisar(self, texto: str) -> None:
        messagebox.showwarning("Robô da Variável", texto, parent=self.raiz)

    def confirmar(self) -> None:
        try:
            inicio = datetime.strptime(self.inicio.get().strip(), "%d/%m/%Y").date()
            fim = datetime.strptime(self.fim.get().strip(), "%d/%m/%Y").date()
        except ValueError:
            self._avisar("Data inválida. Use DD/MM/AAAA, por exemplo 01/11/2026.")
            return
        if inicio > fim:
            self._avisar("A data início precisa ser antes da data fim.")
            return
        pasta = self.pasta.get().strip()
        if not pasta:
            self._avisar("Informe o nome da pasta na Área de Trabalho.")
            return
        escolhidos = self.escolhidos()
        if not escolhidos:
            self._avisar("Marque pelo menos um colaborador.")
            return
        self.resultado = (Periodo(inicio, fim), pasta, escolhidos)
        self.raiz.destroy()

    def cancelar(self) -> None:
        self.resultado = None
        self.raiz.destroy()


def escolher_na_janela(
    colaboradores: list[Colaborador], sugestao: Periodo
) -> tuple[Periodo, str, list[Colaborador]] | None:
    raiz = tk.Tk()
    janela = JanelaInicio(raiz, colaboradores, sugestao)
    raiz.protocol("WM_DELETE_WINDOW", janela.cancelar)
    raiz.attributes("-topmost", True)  # aparece na frente
    raiz.after(800, lambda: raiz.attributes("-topmost", False))
    raiz.focus_force()
    raiz.mainloop()
    return janela.resultado
