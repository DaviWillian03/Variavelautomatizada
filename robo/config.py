"""Configuração do robô, lida do arquivo .env (nunca coloque senha aqui)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

NAVEGADORES_VALIDOS = ("msedge", "chrome", "chromium")


@dataclass(frozen=True)
class Config:
    url_sistema: str
    navegador: str
    caminho_navegador: str | None
    headless: bool
    timeout_ms: int
    pasta_perfil: Path
    pasta_saida: Path
    pasta_logs: Path


def _booleano(valor: str | None) -> bool:
    return (valor or "").strip().lower() in ("1", "sim", "true", "s", "yes")


def carregar_config(arquivo_env: Path | None = None) -> Config:
    load_dotenv(arquivo_env or RAIZ / ".env")

    navegador = os.getenv("NAVEGADOR", "msedge").strip().lower()
    if navegador not in NAVEGADORES_VALIDOS:
        raise ValueError(
            f"NAVEGADOR inválido: {navegador!r}. Use um de: {', '.join(NAVEGADORES_VALIDOS)}."
        )

    def pasta(nome_var: str, padrao: str) -> Path:
        caminho = Path(os.getenv(nome_var, padrao))
        return caminho if caminho.is_absolute() else RAIZ / caminho

    return Config(
        url_sistema=os.getenv("URL_SISTEMA", "https://broker3.flagcloud.com.br/login").strip(),
        navegador=navegador,
        caminho_navegador=os.getenv("CAMINHO_NAVEGADOR") or None,
        headless=_booleano(os.getenv("HEADLESS")),
        timeout_ms=int(os.getenv("TIMEOUT_MS", "30000")),
        pasta_perfil=pasta("PASTA_PERFIL", "perfil-navegador"),
        pasta_saida=pasta("PASTA_SAIDA", "saida"),
        pasta_logs=pasta("PASTA_LOGS", "logs"),
    )
