"""A barra lateral do rascunho, que no celular vira menu hambúrguer.

Acima de 900 px a barra fica fixa à esquerda. Abaixo disso some, e o botão no
topo abre a barra por cima da tela, com um fundo escuro que fecha ao toque. Abrir
e fechar roda no navegador (painel.js), sem ida ao servidor.

As oito telas estão sempre no menu. As que ainda não foram construídas aparecem
desativadas, sem link, até a Agora ser aprovada.
"""

from __future__ import annotations

import dash
from dash import dcc, html

from painel.componentes.blocos import aria, icone

# (nome da tela registrada, rótulo curto no menu, ícone)
TELAS = (
    ("Agora", "Agora", "atividade"),
    ("Credencial do Verde", "Credencial", "chave"),
    ("Atendimento", "Atendimento", "conversa"),
    ("Fluxos", "Fluxos", "fluxo"),
    ("Sistema", "Sistema", "servidor"),
    ("Relatório do dia", "Relatório do dia", "arquivo"),
    ("Relatório da Aplicação", "Relatório da Aplicação", "carteira"),
    ("Observatório da IA", "Observatório da IA", "ia"),
)


def _itens() -> list[dcc.Link | html.Span]:
    caminhos = {p["name"]: p["relative_path"] for p in dash.page_registry.values()}
    itens: list[dcc.Link | html.Span] = []
    for nome, rotulo, nome_do_icone in TELAS:
        if nome in caminhos:
            # O id carrega o caminho: o callback de cliente `marcarTelaAtual` destaca a tela aberta.
            itens.append(
                dcc.Link(
                    [icone(nome_do_icone), rotulo],
                    href=caminhos[nome],
                    className="menu-item",
                    id={"tipo": "menu-link", "caminho": caminhos[nome]},
                )
            )
        else:
            itens.append(
                html.Span(
                    [icone(nome_do_icone), html.Span([rotulo, html.Small("em breve")])],
                    className="menu-item menu-item-desativado",
                    **aria(disabled="true"),
                )
            )
    return itens


def topo_movel() -> html.Div:
    return html.Div(
        [
            html.Button(
                [icone("menu"), "Menu"],
                id="menu-botao",
                className="menu-botao",
                n_clicks=0,
                **aria(controls="menu", expanded="false", label="Abrir o menu"),
            ),
            html.Span("Visor Maria", className="topo-marca"),
        ],
        className="topo-movel",
    )


def menu() -> list[html.Div | html.Nav]:
    return [
        topo_movel(),
        html.Div(id="menu-fundo", className="menu-fundo", n_clicks=0),
        html.Nav(
            [
                html.Div(
                    [html.P("Defensoria Pública RJ", className="menu-instituicao"), html.P("Visor Maria", className="menu-marca")],
                    className="menu-topo",
                ),
                html.Div(_itens(), className="menu-itens"),
                html.Div(
                    [
                        html.P([html.Span(className="ponto tom-bom"), "ao vivo"], className="ao-vivo"),
                        html.P(id="relogio-texto", className="relogio-texto"),
                        html.P("atualiza a cada minuto", className="relogio-texto"),
                    ],
                    className="menu-relogio",
                ),
            ],
            id="menu",
            className="menu",
            **aria(label="Telas do painel"),
        ),
    ]
