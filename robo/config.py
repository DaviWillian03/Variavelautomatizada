"""Configuração do robô, lida do arquivo .env (nunca coloque senha aqui)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent

NAVEGADORES_VALIDOS = ("chrome", "msedge", "chromium")

SELETOR_RELATORIOS_PADRAO = (
    '[title*="Relat" i], [aria-label*="Relat" i], [data-tooltip*="Relat" i]'
)


@dataclass(frozen=True)
class Config:
    url_sistema: str
    host_sistema: str
    host_portal: str
    navegador: str
    caminho_navegador: str | None
    headless: bool
    timeout_ms: int
    timeout_relatorio_s: int
    seletor_relatorios: str
    planilha: Path
    pasta_area_trabalho: Path | None
    pasta_perfil: Path
    pasta_saida: Path
    pasta_logs: Path


def _booleano(valor: str | None) -> bool:
    return (valor or "").strip().lower() in ("1", "sim", "true", "s", "yes")


def carregar_config(arquivo_env: Path | None = None) -> Config:
    load_dotenv(arquivo_env or RAIZ / ".env")

    navegador = os.getenv("NAVEGADOR", "chrome").strip().lower()
    if navegador not in NAVEGADORES_VALIDOS:
        raise ValueError(
            f"NAVEGADOR inválido: {navegador!r}. Use um de: {', '.join(NAVEGADORES_VALIDOS)}."
        )

    def caminho(nome_var: str, padrao: str) -> Path:
        valor = Path(os.path.expandvars(os.path.expanduser(os.getenv(nome_var, padrao))))
        return valor if valor.is_absolute() else RAIZ / valor

    area = os.getenv("PASTA_AREA_TRABALHO")
    url_sistema = os.getenv("URL_SISTEMA", "https://broker3.flagcloud.com.br/login").strip()
    return Config(
        url_sistema=url_sistema,
        host_sistema=os.getenv("HOST_SISTEMA", "connectmerchan.flagcloud.com.br").strip().lower(),
        host_portal=(urlparse(url_sistema).hostname or "").lower(),
        navegador=navegador,
        caminho_navegador=os.getenv("CAMINHO_NAVEGADOR") or None,
        headless=_booleano(os.getenv("HEADLESS")),
        timeout_ms=int(os.getenv("TIMEOUT_MS", "30000")),
        timeout_relatorio_s=int(os.getenv("TIMEOUT_RELATORIO_S", "300")),
        seletor_relatorios=os.getenv("SELETOR_RELATORIOS") or SELETOR_RELATORIOS_PADRAO,
        planilha=caminho("PLANILHA", "colaboradores.xlsx"),
        pasta_area_trabalho=caminho("PASTA_AREA_TRABALHO", area) if area else None,
        pasta_perfil=caminho("PASTA_PERFIL", "perfil-navegador"),
        pasta_saida=caminho("PASTA_SAIDA", "saida"),
        pasta_logs=caminho("PASTA_LOGS", "logs"),
    )


def area_de_trabalho(cfg: Config) -> Path:
    """Área de Trabalho real do Windows (inclusive quando está no OneDrive)."""
    if cfg.pasta_area_trabalho:
        return cfg.pasta_area_trabalho
    if os.name == "nt":
        import ctypes

        buffer = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, 0x0010, None, 0, buffer) == 0:
            return Path(buffer.value)
    return Path.home() / "Desktop"
