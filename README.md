# Variável Automatizada

Robô (Python + Playwright) que baixa, a cada 15 dias, o **caderno PDF das pesquisas de variável**
de cada promotor no **Connect Merchan** (portal Broker 3.0 / FlagCloud) e salva na pasta do
supervisor, na Área de Trabalho.

## O que ele faz

1. **Antes de abrir o Chrome**, aparece uma janela com:
   - **período** (já vem com a última quinzena fechada, ex.: 01/11/2026 a 15/11/2026);
   - **pasta** na Área de Trabalho (acompanha o mês: `Variavel Novembro`);
   - **colaboradores com caixinhas**, separados por supervisor (V EMI / V FLA / V RUA), com
     **“Selecionar todos”** e **“todos de &lt;supervisor&gt;”**.
   Clique em **Abrir o Chrome e começar**. (Sem janela disponível, as mesmas perguntas
   aparecem no terminal; para forçar o terminal use `INTERFACE=terminal` no `.env`.)
2. Abre o **Google Chrome** (perfil próprio do robô) na tela de login do Broker 3.0 e **você**
   faz o login: usuário, senha, “Não sou um robô” e Microsoft Authenticator. Durante o login o
   robô **não está conectado** ao Chrome — ele só olha o endereço das abas. O robô **nunca**
   digita senha, nem resolve captcha, nem mexe no MFA.
3. Quando o portal abrir, o robô **começa sozinho** (não precisa apertar nada): passa o mouse
   no menu e clica em **Connect Merchan**. Sempre que precisar de você, a janela preta vem
   para a frente e apita.
4. Para cada colaborador, igual ao vídeo de referência:
   Pesquisas → **Todos Filtros** → Período Começo das Respostas, Situação *Respondida*,
   Tipo *Pesquisa*, Colaborador → **Aplicar** → 100 por página → marca **só** as pesquisas
   com “Variavel” no nome → **Exportar → 7. Export do Caderno (PDF)** → baixa no painel
   **Relatórios** → salva como `Área de Trabalho\<pasta>\V EMI|V FLA|V RUA\<PrimeiroNome>.pdf`.
5. No fim mostra um **resumo** (salvos, sem pesquisa de variável, pulados, erros) e grava em `saida/`.

Regras:
- Colaborador **sem** pesquisa de variável no período (ou lista com **“Nenhuma linha”**):
  não exporta, pula para o próximo e aparece no resumo.
- Mesmo primeiro nome na mesma pasta: usa nome + sobrenome (ex.: `Daniela Aparecida.pdf`).
- Arquivo já existente **não é sobrescrito**: vira `Allan (2).pdf`.
- **Trava de segurança**: só exporta se o filtro na tela estiver no colaborador certo.
- Se o robô não achar algum botão, ele **não trava**: salva um print, pede para você fazer
  aquele passo na janela e continua (ou você digita `pular` / `sair`).

## Primeira vez no Windows

1. Instale o **Python 3.12+** em <https://www.python.org/downloads/>
   (marque **“Add python.exe to PATH”**).
2. Baixe este repositório (**Code → Download ZIP**) e extraia, por exemplo, em `Documentos\Robo`.
3. Coloque a planilha de colaboradores nessa pasta com o nome **`colaboradores.xlsx`**
   (colunas: `Cod. Colaborador`, `Nome`, `Usuario`, `Nome Superior`).
4. Dê dois cliques em **`executar.bat`**.

O Chrome do robô usa um perfil separado (`perfil-navegador/`), então ele não mexe no seu Chrome
normal. Trate essa pasta como senha: não compartilhe.

## Onde ficam as coisas

| Pasta / arquivo      | O que é                                                    | Vai para o Git? |
|----------------------|------------------------------------------------------------|-----------------|
| `colaboradores.xlsx` | Lista de promotores e supervisores (dados pessoais)        | **Não**         |
| `perfil-navegador/`  | Sessão do Chrome do robô                                   | **Não**         |
| `saida/`             | Resumos e prints (`*_ajuda.png`, `*_erro.png`)             | **Não**         |
| `logs/`              | Registro de cada execução                                  | **Não**         |
| `.env`               | Configurações (sem senha)                                  | **Não**         |

## Para desenvolvedores

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # Windows: .venv\Scripts\pip ...
.venv/bin/python -m pytest
```

Os testes usam um **Connect Merchan falso** (`tests/site_falso/pesquisas/`) e dados fictícios;
nunca acessam o FlagCloud.

- `robo/planilha.py` — lê a planilha, define pasta (`V EMI`…) e nome do arquivo.
- `robo/interacao.py` — perguntas do terminal (período, pasta, quem puxar).
- `robo/navegador.py` — abre o Chrome e espera o Connect Merchan aberto.
- `robo/connect.py` — os cliques dentro do Connect Merchan (seletores tirados do vídeo).
- `robo/tarefas.py` — roteiro: um colaborador por vez + resumo.
