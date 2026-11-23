"""O código de navegador fica em Python (painel/navegador.py), nunca em arquivo .js.

Mesma regra do test_sem_typescript do maria-langgraph-pp, onde o painel nasceu:
o arquivo assets/painel.js fez aquele teste falhar em 26/10.
"""

from __future__ import annotations

from pathlib import Path

from painel import navegador

RAIZ = Path(__file__).resolve().parents[1]
EXTENSOES = {".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx"}
IGNORAR = {".git", ".venv", "node_modules", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"}


def test_nenhum_arquivo_javascript_ou_typescript() -> None:
    achados = [
        caminho.relative_to(RAIZ).as_posix()
        for caminho in RAIZ.rglob("*")
        if caminho.is_file() and caminho.suffix in EXTENSOES and not IGNORAR & set(caminho.relative_to(RAIZ).parts)
    ]
    assert not achados


def test_as_funcoes_de_navegador_sao_funcoes_completas() -> None:
    for nome in ("ALTERNAR_MENU", "MARCAR_TELA_ATUAL", "ESCOLHER_TEMA", "MOSTRAR_RELOGIO"):
        codigo = getattr(navegador, nome).strip()
        assert codigo.startswith("function (") and codigo.endswith("}"), nome
    assert '["claro", "escuro", "noturno"]' in navegador.ESCOLHER_TEMA
    assert "Escape" in navegador.NO_CABECALHO_DA_PAGINA
