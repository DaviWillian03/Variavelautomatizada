# Variável Automatizada

Robô de automação (Python + Playwright) para o sistema FlagCloud, usado a cada 15 dias.

## Como funciona

1. O robô abre o **Microsoft Edge** numa janela própria, na tela de login.
2. **Você** faz o login: usuário, senha e aprovação no Microsoft Authenticator.
   O robô **nunca** digita senha nem aprova o MFA.
3. Quando você estiver dentro do sistema, aperte **Enter** no terminal do robô.
4. A partir daí o robô executa as tarefas e salva os resultados em `saida/`.

> Situação atual: as tarefas **ainda não foram definidas**. Por enquanto o robô só salva
> um print da tela inicial em `saida/` (para mapearmos os menus). Nada é alterado no sistema.

## Primeira vez no Windows

1. Instale o **Python 3.12 ou mais novo** em <https://www.python.org/downloads/>
   (marque **“Add python.exe to PATH”** na instalação).
2. Baixe este repositório (botão **Code → Download ZIP** no GitHub, ou `git clone`).
3. Dê dois cliques em **`executar.bat`**.
   Na primeira vez ele prepara tudo sozinho (pode levar alguns minutos).

Nas próximas vezes, é só dar dois cliques em `executar.bat` de novo.

## Onde ficam as coisas

| Pasta / arquivo      | O que é                                                          | Vai para o Git? |
|----------------------|------------------------------------------------------------------|-----------------|
| `perfil-navegador/`  | Cookies/sessão do navegador do robô (é como estar logado)        | **Não**         |
| `saida/`             | Arquivos e prints gerados (inclui `*_erro.png` quando algo falha)| **Não**         |
| `logs/`              | Registro de cada execução (`robo-AAAA-MM-DD.log`)                | **Não**         |
| `.env`               | Configurações (URL, navegador) — **sem senha**                   | **Não**         |

Trate `perfil-navegador/` como uma senha: não compartilhe essa pasta.

## Configuração (`.env`)

Criado automaticamente a partir de `.env.example`:

- `URL_SISTEMA` — endereço da tela de login.
- `NAVEGADOR` — `msedge` (padrão), `chrome` ou `chromium`.
- `TIMEOUT_MS` — quanto tempo esperar cada elemento da tela (padrão 30000 = 30 s).

## Para desenvolvedores

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # no Windows: .venv\Scripts\pip ...
.venv/bin/python -m pytest
```

Os testes usam um site falso local (`tests/site_falso/`) e nunca acessam o FlagCloud.

Estrutura:

- `robo/config.py` — lê o `.env`.
- `robo/navegador.py` — abre o navegador, espera o login manual, tira prints.
- `robo/tarefas.py` — **o que o robô faz dentro do sistema** (a preencher).
- `robo/__main__.py` — junta tudo; em caso de erro salva print e log.
