"""Regras que valem para todo texto que a pessoa lê, em todas as telas.

Os nomes técnicos (grupo de logs, métrica) vão em `html.Code` e ficam de fora:
são para quem confere no CloudWatch, e têm hífen no nome real.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

import pytest
from dash import html
from dash.development.base_component import Component

import painel.app
from painel.componentes.menu import TELAS

HIFENS = "-‐‑‒–—−"
ATRIBUTOS_LIDOS = ("aria-label", "title")
NOMES_DAS_TELAS = [nome for nome, _, _ in TELAS]


def _props(no: Component) -> dict[str, Any]:
    return no.to_plotly_json()["props"]


def _textos(no: Any) -> Iterator[str]:
    if isinstance(no, str):
        yield no
    elif isinstance(no, (int, float)):
        yield str(no)
    elif isinstance(no, (list, tuple)):
        for filho in no:
            yield from _textos(filho)
    elif isinstance(no, Component):
        if isinstance(no, html.Code):
            return
        props = _props(no)
        for atributo in ATRIBUTOS_LIDOS:
            if isinstance(props.get(atributo), str):
                yield props[atributo]
        for opcao in props.get("options") or []:
            if isinstance(opcao, dict):
                yield str(opcao.get("label", ""))
        yield from _textos(props.get("children"))


def _componentes(no: Any) -> Iterator[Component]:
    if isinstance(no, (list, tuple)):
        for filho in no:
            yield from _componentes(filho)
    elif isinstance(no, Component):
        yield no
        yield from _componentes(_props(no).get("children"))


def _classes(no: Component) -> set[str]:
    return set(str(_props(no).get("className") or "").split())


def _sem_hifen(textos: list[str]) -> None:
    com_hifen = [t for t in textos if any(h in t for h in HIFENS)]
    assert not com_hifen, f"texto com hífen: {com_hifen}"


def test_todas_as_telas_do_menu_estao_registradas(layout_da_tela: Callable[[str], Any]) -> None:
    for nome in NOMES_DAS_TELAS:
        assert layout_da_tela(nome) is not None


@pytest.mark.parametrize("nome", NOMES_DAS_TELAS)
def test_nenhuma_tela_tem_hifen_nem_sem_dados(nome: str, cenario: str, layout_da_tela: Callable[[str], Any]) -> None:
    textos = list(_textos(layout_da_tela(nome)))
    _sem_hifen(textos)
    assert not [t for t in textos if "sem dados" in t.lower()]


def test_a_moldura_e_o_menu_nao_tem_hifen() -> None:
    _sem_hifen(list(_textos(painel.app.app.layout)))


@pytest.mark.parametrize("nome", NOMES_DAS_TELAS)
def test_todo_indicador_e_quadro_mostra_fonte_e_hora(nome: str, cenario: str, layout_da_tela: Callable[[str], Any]) -> None:
    blocos = [c for c in _componentes(layout_da_tela(nome)) if {"indicador", "quadro"} & _classes(c)]
    assert blocos
    for bloco in blocos:
        notas = [c for c in _componentes(bloco) if "fonte-curta" in _classes(c)]
        assert notas, f"{nome}: bloco sem fonte: {_props(bloco).get('className')}"
        # O espaço reservado diz de onde veio a pendência, mas não há leitura para ter hora.
        if "reservado" not in _classes(bloco):
            assert "lido " in "".join(_textos(notas[0])), f"{nome}: fonte sem hora"


@pytest.mark.parametrize("nome", NOMES_DAS_TELAS)
def test_vazio_e_falha_tem_texto_proprio_em_cada_indicador(nome: str, cenario: str, layout_da_tela: Callable[[str], Any]) -> None:
    if cenario == "normal":
        return
    classe = "texto-vazio" if cenario == "vazio" else "texto-aviso"
    indicadores = [c for c in _componentes(layout_da_tela(nome)) if "indicador" in _classes(c) and "reservado" not in _classes(c)]
    for ind in indicadores:
        avisos = [c for c in _componentes(ind) if classe in _classes(c)]
        assert avisos and "".join(_textos(avisos[0])).strip(), f"{nome}: indicador sem texto de {cenario}"


@pytest.mark.parametrize("nome", ["Agora", "Credencial do Verde", "Relatório do dia"])
def test_fonte_que_faltou_aparece_nas_listas_de_regra(nome: str, cenario: str, layout_da_tela: Callable[[str], Any]) -> None:
    texto = " ".join(_textos(layout_da_tela(nome)))
    assert ("Faltou ler:" in texto) == (cenario != "normal")


@pytest.mark.parametrize("nome", NOMES_DAS_TELAS)
def test_buscas_que_nao_acharam_a_pessoa_so_aparecem_com_a_credencial(nome: str, layout_da_tela: Callable[[str], Any]) -> None:
    """Onde "não achou a pessoa" aparece, a credencial está no mesmo quadro."""
    for bloco in _componentes(layout_da_tela(nome)):
        if "quadro" not in _classes(bloco):
            continue
        texto = " ".join(_textos(bloco)).lower()
        if "não achou a pessoa" in texto or "não acharam a pessoa" in texto:
            assert "credencial" in texto, f"{nome}: o não achou apareceu sem a credencial"


@pytest.mark.parametrize("nome", NOMES_DAS_TELAS)
def test_a_lista_de_fontes_traz_o_nome_tecnico(nome: str, layout_da_tela: Callable[[str], Any]) -> None:
    lista = next(c for c in _componentes(layout_da_tela(nome)) if "lista-de-fontes" in _classes(c))
    codigos = [str(_props(c)["children"]) for c in _componentes(lista) if isinstance(c, html.Code)]
    assert codigos and all(codigos)
