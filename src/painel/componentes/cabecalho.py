"""O cabeçalho de cada tela, como no rascunho: o nome da tela em destaque, a
pergunta que ela responde logo abaixo, e à direita o tema e as ações da tela."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from dash import dcc, html

from painel.componentes.blocos import aria, icone
from painel.dados.modelo import FUSO, NOME_DO_AMBIENTE, Ambiente
from painel.periodo import ROTULOS, Escolha, opcoes_de_data, opcoes_de_mes

TEMAS = (("claro", "Claro", "sol"), ("escuro", "Escuro", "lua"), ("noturno", "Noturno", "noturno"))


def seletor_de_tema() -> html.Div:
    """Os três temas do rascunho. A troca roda no navegador (painel.js)."""
    return html.Div(
        [
            html.Button(
                [icone(nome_do_icone), rotulo],
                id=f"tema-{valor}",
                className="tema-opcao",
                n_clicks=0,
                **aria(pressed="false"),
            )
            for valor, rotulo, nome_do_icone in TEMAS
        ],
        className="seletor-de-tema",
        role="group",
        **aria(label="Tema"),
    )


def filtro_de_ambiente(id_: str, valor: Ambiente = Ambiente.PRODUCAO) -> dcc.RadioItems:
    """Ambiente é filtro, nunca duas séries no mesmo gráfico."""
    return dcc.RadioItems(
        id=id_,
        # O tipo do Dash não aceita lista de dicionários, que ele aceita na prática.
        options=cast(Any, [{"label": NOME_DO_AMBIENTE[a], "value": a.value} for a in Ambiente]),
        value=valor.value,
        inline=True,
        className="filtro-ambiente",
        inputClassName="filtro-ambiente-entrada",
        labelClassName="filtro-ambiente-opcao",
    )


def acao_em_breve(texto: str, nome_do_icone: str, motivo: str = "Tela em breve") -> html.Span:
    """Botão desligado: aparece, mas não leva a lugar nenhum. `motivo` vai na dica."""
    return html.Span(
        [icone(nome_do_icone), texto],
        className="botao botao-desativado",
        title=motivo,
        **aria(disabled="true"),
    )


# Os textos da lista do Dash 4 (a busca e o vazio), que viriam em inglês.
TEXTOS_DA_LISTA = {"search": "Procurar um dia", "clear_search": "Limpar a busca", "no_options_found": "Nenhum dia com esse texto", "clear_selection": "Limpar"}


def filtro_de_periodo(id_: str, agora: datetime) -> html.Div:
    """Hoje, 7 dias, 30 dias ou uma data, com o período coberto escrito ao lado.

    A data é uma lista de dias, e não o calendário do Dash: o calendário escreve
    os meses em inglês. Os ids derivados: `{id_}-data` (a lista, que só aparece
    na data específica), `{id_}-mes` (a lista de meses, que só aparece em Mês) e `{id_}-texto` (o período, refeito a cada minuto)."""
    return html.Div(
        [
            dcc.RadioItems(
                id=id_,
                options=cast(Any, [{"label": rotulo, "value": escolha.value} for escolha, rotulo in ROTULOS.items()]),
                value=Escolha.HOJE.value,
                inline=True,
                className="filtro-ambiente",
                inputClassName="filtro-ambiente-entrada",
                labelClassName="filtro-ambiente-opcao",
            ),
            html.Div(
                dcc.Dropdown(
                    id=f"{id_}-data",
                    options=cast(Any, opcoes_de_data(agora)),
                    value=agora.astimezone(FUSO).date().isoformat(),
                    clearable=False,
                    searchable=True,
                    placeholder="Escolha o dia",
                    labels=cast(Any, TEXTOS_DA_LISTA),
                    className="filtro-data",
                ),
                id=f"{id_}-caixa-da-data",
                className="filtro-data-caixa",
                hidden=True,
            ),
            html.Div(
                dcc.Dropdown(
                    id=f"{id_}-mes",
                    options=cast(Any, opcoes_de_mes(agora)),
                    value=f"{agora.astimezone(FUSO):%Y-%m}",
                    clearable=False,
                    searchable=False,
                    labels=cast(Any, TEXTOS_DA_LISTA),
                    className="filtro-data",
                ),
                id=f"{id_}-caixa-do-mes",
                className="filtro-data-caixa",
                hidden=True,
            ),
            html.P(id=f"{id_}-texto", className="periodo-texto", **aria(live="polite")),
        ],
        className="filtro-periodo",
        role="group",
        **aria(label="Período"),
    )


def cabecalho(nome: str, pergunta: Any, acoes: list[Any] | None = None, filtro: Any = None) -> html.Header:
    """`filtro` vai numa linha própria, abaixo da pergunta (o filtro de período).
    `pergunta` pode ser um componente com id, para um callback trocá-la."""
    return html.Header(
        [
            html.Div([html.H1(nome, className="tela-nome"), html.P(pergunta, className="tela-pergunta")]),
            html.Div([seletor_de_tema(), *(acoes or [])], className="tela-acoes"),
            html.Div(filtro, className="tela-filtro") if filtro is not None else None,
        ],
        className="tela-cabecalho",
    )
