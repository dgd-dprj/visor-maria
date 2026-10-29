"""Tela Observatório da IA: a IA está respondendo bem, e onde ela erra?

O que a inteligência artificial faz na Maria, como cada função se comporta e o
que mudou nela. Tudo sai do código da Maria, dos logs e das métricas da AWS,
sempre agregado: nenhuma conversa é lida nem listada (regra 4).

O que esta tela ainda não consegue dizer é se a resposta da IA está certa. Isso
pede ler o conteúdo, que o painel não lê, ou um conjunto de casos fictícios com
a resposta esperada. Fica no quadro "O que ainda não dá para medir", com quem
decide.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, html

from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import Pendencia, Valor, indicador, lista_de_fontes, quadro, reservado, texto_de_falha
from painel.componentes.cabecalho import cabecalho, filtro_de_ambiente
from painel.componentes.formato import data_curta, numero, sem_hifen
from painel.dados.modelo import FUSO, NOME_DO_AMBIENTE, Ambiente, DiaDoModelo, Estado
from painel.dados.telas import LeiturasDaIA, dias_passados, ler_ia, preparar
from painel.funcoes_de_ia import FUNCOES
from painel.lateral import coluna, com_lateral

dash.register_page(__name__, path="/ia", name="Observatório da IA", order=6, title="Observatório da IA · Visor Maria")

ID_DO_AMBIENTE = "ia-ambiente"
COMMIT = "https://github.com/dgd-dprj/maria-langgraph-pp/commit/"


def _janela(d: LeiturasDaIA, padrao: str) -> str:
    """A janela padrão ("em 30 dias") ou o dia escolhido num gráfico ("em 22/10")."""
    return padrao if d.dia is None else f"em {data_curta(d.dia)}"


def _dias_do_modelo(d: LeiturasDaIA) -> list[DiaDoModelo]:
    """Os 14 dias do modelo, ou só o dia escolhido."""
    dias = d.modelo.valor or []
    return dias if d.dia is None else [x for x in dias if x.dia == d.dia]


# ── Indicadores ───────────────────────────────────────────────────────────


def _indicadores(d: LeiturasDaIA) -> html.Div:
    modelo = _dias_do_modelo(d)
    em_14_dias = _janela(d, "em 14 dias")

    def falhas() -> Valor:
        assert d.erros.valor is not None
        soma = sum(e.falhas for e in d.erros.valor)
        piores = [e for e in d.erros.valor if e.falhas]
        legenda = "nenhuma função falhou" if not piores else "em " + ", ".join(f"{e.funcao} ({numero(e.falhas)})" for e in piores)
        return Valor(numero(soma), "ruim" if soma else "bom", legenda=legenda, tom_da_legenda="ruim" if soma else "bom")

    def escritas() -> Valor:
        assert d.uso.valor is not None
        u = d.uso.valor
        parte = round(u.escritas_pela_ia / u.perguntas * 100) if u.perguntas else 0
        return Valor(f"{parte}%", legenda=f"{numero(u.escritas_pela_ia)} de {numero(u.perguntas)} perguntas {_janela(d, 'em 7 dias')}")

    def chamadas() -> Valor:
        return Valor(numero(sum(x.chamadas for x in modelo)), legenda=f"conta inteira, {_janela(d, '14 dias')}")

    def demora() -> Valor:
        com = [x for x in modelo if x.chamadas]
        media = sum(x.demora_media * x.chamadas for x in com) / sum(x.chamadas for x in com) if com else 0.0
        return Valor(f"{media:.1f}".replace(".", ","), unidade=" s", legenda=f"por chamada, média {_janela(d, 'de 14 dias')}")

    def recusas() -> Valor:
        erros = sum(x.erros_do_pedido + x.erros_do_servico for x in modelo)
        limite = sum(x.limitadas for x in modelo)
        soma = erros + limite
        return Valor(numero(soma), "ruim" if soma else "bom", legenda=f"{numero(erros)} com erro, {numero(limite)} por limite de uso")

    sem_chamada = f"O modelo não foi chamado {em_14_dias}."
    return html.Div(
        [
            indicador(f"Falhas {_janela(d, 'em 30 dias')}", "alerta", [d.erros], falhas, "A IA não foi chamada no período.", d.agora),
            indicador("Perguntas escritas pela IA", "conversa", [d.uso], escritas, f"Nenhuma pergunta foi enviada {_janela(d, 'em 7 dias')}.", d.agora),
            indicador("Chamadas ao modelo", "ia", [d.modelo], chamadas, sem_chamada, d.agora),
            indicador("Demora do modelo", "relogio", [d.modelo], demora, sem_chamada, d.agora),
            indicador("Chamadas recusadas", "servidor", [d.modelo], recusas, sem_chamada, d.agora),
        ],
        className="grade-indicadores",
    )


# ── O que a IA faz ────────────────────────────────────────────────────────


def _funcoes(d: LeiturasDaIA) -> html.Section:
    falhas = {e.funcao: e.falhas for e in (d.erros.valor or [])}

    def coluna_de_falhas(codigo: str) -> Any:
        if d.erros.estado is Estado.INDISPONIVEL:
            return html.Span("não deu para ler", className="texto-aviso", title=d.erros.motivo or "")
        n = falhas.get(codigo, 0)
        return html.Span(numero(n), className="tom-ruim" if n else "tom-bom")

    linhas = [
        html.Tr(
            [
                html.Th([html.Strong(f.nome), html.Br(), html.Code(f.codigo)], scope="row"),
                html.Td(f.faz),
                html.Td(f.onde),
                html.Td(f.se_falha),
                html.Td(coluna_de_falhas(f.codigo), className="numero mono"),
            ]
        )
        for f in FUNCOES
    ]
    linhas.append(
        html.Tr(
            [
                html.Th([html.Strong("Busca por semelhança"), html.Br(), html.Code("embeddings")], scope="row"),
                html.Td("Transforma os fluxos planejados em números, para achar o mais parecido com o relato."),
                html.Td("catálogo dos fluxos"),
                html.Td("Não grava falha com o mesmo padrão: fica sem medida aqui."),
                html.Td(html.Span("não medido", className="texto-vazio"), className="numero"),
            ]
        )
    )
    tabela = html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Função"),
                        html.Th("O que faz"),
                        html.Th("Onde"),
                        html.Th("Se falha"),
                        html.Th(f"Falhas {_janela(d, 'em 30 dias')}", className="numero"),
                    ]
                )
            ),
            html.Tbody(linhas),
        ],
        className="tabela tabela-funcoes",
    )
    nota = html.P(
        [
            "O que cada função faz vem do código da Maria (",
            html.Code("src/maria/ia"),
            ", develop, lido em 26/10). Modelo de conversa: Claude Haiku 4.5; busca por semelhança: Titan Text Embeddings v2.",
        ],
        className="quadro-explicacao miolo",
    )
    return quadro("O que a IA faz na Maria", [tabela, nota], [d.erros], d.agora, lateral=f"falhas: {NOME_DO_AMBIENTE[d.ambiente].lower()}")


# ── Saúde do modelo ───────────────────────────────────────────────────────


def _figura_do_modelo(dias: list[DiaDoModelo], tema: str | None) -> go.Figure:
    c = graficos.cores(tema)
    figura = go.Figure()
    figura.add_bar(
        x=[x.dia for x in dias], y=[x.chamadas for x in dias], marker_color=c["azul"], name="chamadas", hovertemplate="%{x|%d/%m}: %{y} chamadas<extra></extra>"
    )
    com_erro = [x for x in dias if x.erros_do_pedido or x.erros_do_servico or x.limitadas]
    if com_erro:
        figura.add_bar(
            x=[x.dia for x in com_erro],
            y=[x.erros_do_pedido + x.erros_do_servico + x.limitadas for x in com_erro],
            marker_color=c["ruim"],
            name="recusadas",
            hovertemplate="%{x|%d/%m}: %{y} recusadas<extra></extra>",
        )
    figura.add_scatter(
        x=[x.dia for x in dias],
        y=[x.demora_media for x in dias],
        yaxis="y2",
        mode="lines+markers",
        line={"color": c["atencao"]},
        name="demora",
        hovertemplate="%{x|%d/%m}: %{y:.2f} s por chamada<extra></extra>",
    )
    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="overlay",
        height=230,
        separators=",.",
        xaxis={"showgrid": False, "fixedrange": True, "tickformat": "%d/%m"},
        yaxis={"showgrid": True, "gridcolor": c["grade"], "fixedrange": True, "rangemode": "tozero"},
        yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "fixedrange": True, "rangemode": "tozero", "ticksuffix": " s"},
    )
    return figura


def _modelo(d: LeiturasDaIA, tema: str | None) -> html.Section:
    leitura = d.modelo
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not leitura.valor or not any(x.chamadas for x in leitura.valor):
        corpo = html.P("O modelo não foi chamado em 14 dias.", className="texto-vazio")
    else:
        corpo = [
            filtro_de_dia.grafico("ia", "modelo", filtro_de_dia.destacar(_figura_do_modelo(leitura.valor, tema), d.dia, tema)),
            html.Div(
                [
                    html.Span([html.Span(className="legenda-cor tom-azul"), "chamadas"]),
                    html.Span([html.Span(className="legenda-cor tom-ruim"), "recusadas (erro ou limite)"]),
                    html.Span([html.Span(className="legenda-cor tom-atencao"), "demora por chamada, à direita"]),
                ],
                className="legenda",
            ),
        ]
    return quadro("Como o modelo respondeu, 14 dias", corpo, [leitura], d.agora, lateral="conta inteira: não separa ambiente; clique num dia")


# ── Mudanças na IA ────────────────────────────────────────────────────────


def _mudancas(d: LeiturasDaIA) -> html.Section:
    leitura = d.mudancas
    mudancas = [m for m in leitura.valor or [] if d.dia is None or m.quando.astimezone(FUSO).date() == d.dia]
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not mudancas:
        vazio = "Ninguém mexeu no módulo de IA da Maria." if d.dia is None else f"Ninguém mexeu no módulo de IA da Maria em {data_curta(d.dia)}."
        corpo = html.P(vazio, className="texto-vazio")
    else:
        corpo = html.Ul(
            [
                html.Li(
                    [
                        html.Span(data_curta(m.quando), className="linha-hora mono"),
                        html.Span(sem_hifen(m.titulo), className="linha-texto"),
                        html.A(html.Code(m.codigo), href=COMMIT + m.codigo, target="_blank", rel="noopener", className="linha-codigo"),
                    ],
                    className="linha-mudanca",
                )
                for m in mudancas[:15]
            ],
            className="lista-de-mudancas",
        )
    return quadro("O que mudou na IA", corpo, [leitura], d.agora, lateral="commits em develop, os 15 mais novos")


APRENDE = html.Section(
    [
        html.Header([html.H2("A IA aprende com as conversas?")], className="quadro-topo"),
        html.Div(
            [
                html.P(
                    [
                        html.Strong("Não. "),
                        "O modelo é o mesmo para todo mundo e não é treinado com os atendimentos. Dentro de uma conversa ele vê o que a pessoa já "
                        "disse; de uma conversa para outra, não guarda nada.",
                    ]
                ),
                html.P(
                    "O comportamento só muda quando alguém muda o código ou as instruções da Maria (o quadro ao lado), ou quando a AWS troca a "
                    "versão do modelo. Por isso cada mudança aparece aqui com data: se uma taxa de falha muda, a primeira pergunta é o que mudou antes."
                ),
            ],
            className="miolo texto-corrido",
        ),
        html.Footer(
            html.P(["código da Maria, ", html.Code("src/maria/ia"), " e o checkpointer por conversa, develop em 26/10"], className="fonte-curta"),
            className="quadro-pe",
        ),
    ],
    className="quadro reservado",
)


PENDENCIAS = reservado(
    "O que ainda não dá para medir",
    [
        Pendencia(
            "Se a resposta da IA está certa",
            "Nenhum registro diz se o que a IA tirou do relato ou escreveu está certo, nem se ela inventou algo (alucinação). O painel não lê "
            "conversas. O caminho que não toca dado real: um conjunto de casos fictícios com a resposta esperada, rodado todo dia contra o modelo, "
            "com a nota de acerto vindo para cá.",
            "Nicole decide; a rotina é na Maria",
        ),
        Pendencia(
            "Saída fora do esperado",
            "A saída da IA não é validada (issue #212): um parentesco fora da lista passa adiante. Com a validação, cada saída recusada vira um "
            "evento contável, e a taxa aparece aqui.",
            "issue #212, aprovada",
        ),
        Pendencia(
            "Falhas da busca por semelhança",
            "A busca por semelhança não grava a falha no mesmo padrão das outras funções.",
            "mudança no log da Maria",
        ),
        Pendencia(
            "Revisão de conversas reais",
            "Ler uma amostra de conversas para conferir a IA fere a regra de nunca listar conversa. Só com decisão de proteção de dados.",
            "Nicole",
        ),
    ],
    ["proposta desta tela, 26/10"],
)


# ── Montagem ──────────────────────────────────────────────────────────────


def _corpo(d: LeiturasDaIA, tema: str | None) -> list[Any]:
    return [
        _indicadores(d),
        _funcoes(d),
        _modelo(d, tema),
        html.Div([_mudancas(d), APRENDE], className="grade-dupla"),
        PENDENCIAS,
        lista_de_fontes(d.todas(), d.agora),
    ]


def _lateral(d: LeiturasDaIA) -> list[Any]:
    """Na coluna da direita: as falhas por função, numa leitura rápida."""
    linhas: list[Any] = [html.P("Mais sinais", className="lateral-titulo")]
    leitura = d.erros
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not leitura.valor:
        corpo = html.P("A IA não foi chamada no período.", className="texto-vazio")
    else:
        maior = max((e.falhas for e in leitura.valor), default=0) or 1
        corpo = html.Div(
            [
                html.Div(
                    [
                        html.Div([html.P(e.funcao, className="barra-rotulo"), html.P(numero(e.falhas), className="barra-valor")], className="barra-topo"),
                        html.Div(
                            html.Div(
                                className=f"barra-cheia fundo-{'ruim' if e.falhas else 'bom'}", style={"width": f"{max(e.falhas / maior, 0.02) * 100:.0f}%"}
                            ),
                            className="barra",
                        ),
                    ],
                    className="barra-rotulada",
                )
                for e in leitura.valor
            ],
            className="miolo",
        )
    titulo = "Falhas por função, " + ("30 dias" if d.dia is None else data_curta(d.dia))
    linhas.append(quadro(titulo, corpo, [leitura], d.agora, lateral=NOME_DO_AMBIENTE[d.ambiente].lower(), classe="compacto"))
    return linhas


FILTRADO = "As falhas, as perguntas escritas pela IA, os números do modelo e as mudanças no código mostram esse dia."
filtro_de_dia.registrar("ia", FILTRADO)


def layout(dia: str | None = None, **_: str) -> html.Div:
    agora = datetime.now(FUSO)
    # Os 14 dias do gráfico do modelo, lidos por trás: o clique num deles já encontra a leitura.
    for passado in dias_passados(14, agora):
        for consulta in ("erros_da_ia", "uso_da_ia"):
            preparar(consulta, Ambiente.PRODUCAO, passado)
    d = ler_ia(Ambiente.PRODUCAO, filtro_de_dia.ler(dia, agora))
    tela = html.Div(
        [
            cabecalho(
                "Observatório da IA",
                "A IA está respondendo bem, e onde ela erra?",
                [html.Span("Ambiente", className="rotulo-filtro"), filtro_de_ambiente(ID_DO_AMBIENTE)],
            ),
            filtro_de_dia.armazem("ia", d.dia),
            filtro_de_dia.faixa("ia", d.dia),
            html.Div(_corpo(d, None), id="ia-corpo", className="tela-corpo"),
        ],
        className="tela",
    )
    return com_lateral(tela, coluna("ia-lateral", _lateral(d)))


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador.
@callback(
    Output("ia-corpo", "children"),
    Output("ia-lateral", "children"),
    Input("relogio", "n_intervals"),
    Input(ID_DO_AMBIENTE, "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada("ia"),
)
def atualizar(_: int | None, ambiente: str | None, tema: str | None, dia: str | None) -> tuple[Any, Any]:
    d = ler_ia(Ambiente(ambiente or Ambiente.PRODUCAO.value), filtro_de_dia.escolhido(dia))
    return _corpo(d, tema), _lateral(d)
