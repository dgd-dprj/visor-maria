"""O aplicativo Dash: moldura (menu e área da tela), tema, relógio e páginas.

Cada tela é um módulo em `pages/` (Dash Pages). O tema, o menu móvel e o relógio
da barra lateral rodam no navegador, por callbacks de cliente (navegador.py).
O relógio `relogio` dispara a atualização de todas as telas a cada minuto.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import dash
from dash import ALL, Dash, Input, Output, State, clientside_callback, dcc, html

from painel import navegador
from painel.componentes.cabecalho import TEMAS
from painel.componentes.menu import menu
from painel.dados import fonte_simulada_ligada, obter_fonte, sem_credencial_da_aws

PASTA = Path(__file__).parent
ATUALIZACAO_MS = 60_000

# Archivo é a fonte do painel (painel-maria-LEIA.md, confirmada em 26/10); a mono,
# JetBrains Mono, é provisória. Sem internet, o CSS cai nas fontes do sistema.
FONTES = "https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"

# lang="pt-BR", e o script que aplica o tema e liga o Esc antes da primeira pintura.
PAGINA = (
    """<!DOCTYPE html>
<html lang="pt-BR">
<head>
{%metas%}
<title>{%title%}</title>
{%favicon%}
{%css%}
<script>"""
    + navegador.NO_CABECALHO_DA_PAGINA
    + """</script>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>"""
)

app = Dash(
    __name__,
    use_pages=True,
    pages_folder=str(PASTA / "pages"),
    assets_folder=str(PASTA / "assets"),
    external_stylesheets=[FONTES],
    title="Visor Maria",
    # O Dash aceita None (desliga o "Updating..." no título), mas o tipo diz str.
    update_title=None,  # type: ignore[arg-type]
    index_string=PAGINA,
    meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}],
    # Os botões de tema moram no cabeçalho de cada tela, que entra e sai com a página.
    suppress_callback_exceptions=True,
)
server = app.server

# Falha na subida, e não na primeira tela, se PAINEL_FONTE pedir uma fonte que não existe.
obter_fonte()

# Enquanto a fonte for a simulada, nenhum número é medido, e toda tela diz isso
# no topo (aprovado em 26/10). A faixa some quando a fonte real for ligada.
FAIXA_DE_SIMULADO = html.P(
    [html.Strong("Dados simulados:"), " nenhum número desta tela é medido. Eles só servem para conferir o desenho."],
    className="faixa-de-simulado",
    role="note",
)

# Quem acaba de baixar o painel e roda sem credencial da AWS vê quase toda tela
# vazia (a Agora inteira); a faixa diz por quê e o que fazer, antes de cada quadro.
FAIXA_SEM_AWS = html.P(
    [
        html.Strong("Sem acesso à AWS:"),
        " esta máquina não tem credencial da AWS, então os números que vêm do CloudWatch não aparecem; só os do GitHub. "
        "Faça o login e reinicie o painel (README, em Primeira vez), ou rode com PAINEL_FONTE=simulado para ver o desenho.",
    ],
    className="faixa-de-simulado",
    role="note",
)
if sem_credencial_da_aws():
    logging.getLogger(__name__).warning("Sem credencial da AWS nesta máquina: os quadros do CloudWatch vão aparecer sem número (README, em Primeira vez).")

app.layout = html.Div(
    [
        dcc.Location(id="url"),
        dcc.Store(id="tema", storage_type="local"),
        dcc.Interval(id="relogio", interval=ATUALIZACAO_MS),
        *menu(),
        html.Main(
            [FAIXA_DE_SIMULADO if fonte_simulada_ligada() else None, FAIXA_SEM_AWS if sem_credencial_da_aws() else None, dash.page_container],
            id="conteudo",
            className="conteudo",
        ),
    ],
    className="moldura",
)

clientside_callback(
    navegador.ALTERNAR_MENU,
    Output("menu", "className"),
    Output("menu-fundo", "className"),
    Output("menu-botao", "aria-expanded"),
    Input("menu-botao", "n_clicks"),
    Input("menu-fundo", "n_clicks"),
    Input("url", "pathname"),
    State("menu", "className"),
)

clientside_callback(
    navegador.MARCAR_TELA_ATUAL,
    Output({"tipo": "menu-link", "caminho": ALL}, "className"),
    Input("url", "pathname"),
    State({"tipo": "menu-link", "caminho": ALL}, "id"),
)

# Os três botões do seletor de tema: o clique grava o tema, e a subida do
# cabeçalho (botões novos na tela) marca o botão do tema guardado.
clientside_callback(
    navegador.ESCOLHER_TEMA,
    Output("tema", "data"),
    *(Output(f"tema-{valor}", "className") for valor, _, _ in TEMAS),
    *(Output(f"tema-{valor}", "aria-pressed") for valor, _, _ in TEMAS),
    *(Input(f"tema-{valor}", "n_clicks") for valor, _, _ in TEMAS),
    State("tema", "data"),
)

clientside_callback(
    navegador.MOSTRAR_RELOGIO,
    Output("relogio-texto", "children"),
    Input("relogio", "n_intervals"),
)


if __name__ == "__main__":
    # PAINEL_DEPURACAO=1 liga o recarregamento e a barra de depuração do Dash.
    app.run(host="127.0.0.1", port=8050, debug=os.environ.get("PAINEL_DEPURACAO") == "1")
