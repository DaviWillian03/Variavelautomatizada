# CLAUDE.md — Variável Automatizada

Robô de automação web (Python 3.12+, Playwright) para o sistema FlagCloud. Roda no Windows do usuário
a cada 15 dias. Tudo em português brasileiro.

## Regras inegociáveis
- **Login é sempre manual.** O robô nunca digita usuário/senha nem tenta passar pelo Microsoft
  Authenticator/MFA. Ele abre a tela de login e espera a pessoa confirmar com Enter.
- Nenhum segredo no Git nem no código (senha, cookies, `perfil-navegador/`, `.env`).
- Ações que alteram dados no sistema precisam ser confirmadas com o usuário antes de implementar.
- Testes usam o site falso em `tests/site_falso/`; nunca acessar o FlagCloud real a partir da nuvem.
- Se algo não foi executado de verdade, escrever **NÃO EXECUTADO** — nunca inventar resultado.

## Comandos
- `python -m robo` (ou `executar.bat` no Windows)
- `python -m pytest`
- Dependências com versão exata em `requirements*.txt`.

## Convenções
- Usar o logger `robo` (`robo/registro.py`); só `Terminal` (`robo/interacao.py`) conversa com a pessoa.
- Seletores preferidos: `get_by_role` / `get_by_label` / texto visível, não XPath frágil.
- Em erro: print em `saida/*_erro.png` + traceback no log.
- Planilha de colaboradores tem dados pessoais: nunca versionar (`*.xlsx` no .gitignore); testes usam nomes fictícios.
- Passo que falhar no site real → `ConnectMerchan._passo` pede ajuda à pessoa (print + Enter/pular/sair), nunca trava.
- Seletores do Connect Merchan vieram de um vídeo, não do HTML real: ajustar com prints `saida/*_ajuda.png`.
