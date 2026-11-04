"""Sobe o app uma vez (Dash Pages só registra telas depois de o app existir)."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable, Iterator
from typing import Any

import dash
import pytest

os.environ.setdefault("PAINEL_FONTE", "simulado")
# Cada execução dos testes com o seu cache, longe do cache do painel aberto.
os.environ.setdefault("PAINEL_CACHE", tempfile.mkdtemp(prefix="painel-testes-"))

import painel.app  # noqa: E402,F401  (registra as telas)
from painel.dados import obter_fonte  # noqa: E402


@pytest.fixture(params=["normal", "vazio", "falha"])
def cenario(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("PAINEL_CENARIO", request.param)
    obter_fonte.cache_clear()
    yield request.param
    obter_fonte.cache_clear()


@pytest.fixture
def layout_da_tela() -> Callable[[str], Any]:
    def montar(nome: str) -> Any:
        pagina = next(p for p in dash.page_registry.values() if p["name"] == nome)
        return pagina["layout"]()

    return montar
