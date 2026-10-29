"""Tela Atendimento: como as conversas terminam?

Segue o rascunho. A origem separa produção antes e depois do corte de versão
(23/10, 12:31) e o release: os pedaços ficam em botões separados, em vez de
somados num número só.

"Buscas que não acharam a pessoa" nunca aparece sozinho: o quadro mostra, ao
lado, a credencial do Verde no mesmo trecho, e a conclusão sai desses números.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import partial
from typing import Any, cast

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from painel import lateral
from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import (
    Tom,
    Valor,
    barra_rotulada,
    celula_de_leitura,
    indicador,
    lista_de_fontes,
    nota_de_fonte,
    quadro,
    texto_de_falha,
)
from painel.componentes.cabecalho import cabecalho
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import MESES, data_curta, dia_da_semana_e_data, numero
from painel.dados import obter_fonte
from painel.dados.fontes import DIAS_DO_REGISTRO
from painel.dados.modelo import (
    AMBIENTE_DA_ORIGEM,
    FUSO,
    NOME_DA_ORIGEM,
    Ambiente,
    ContagemPorDia,
    Estado,
    Leitura,
    Origem,
    ResumoDoOrquestrador,
    TrechoDeNaoEncontrado,
)
from painel.dados.telas import LeiturasDoAtendimento, dias_passados, ler_atendimento, montar_ja, preparar
from painel.lateral import coluna, com_lateral

dash.register_page(__name__, path="/atendimento", name="Atendimento", order=2, title="Atendimento · Visor Maria")

# O começo do trecho TypeScript, o mesmo de dados/real.py.
INICIO_DO_TYPESCRIPT = date(2026, 10, 16)
FILTRADO = "Os números, os encerramentos por RG não encontrado, a escrita livre e como terminaram mostram o que foi escolhido, dentro do trecho da origem."
filtro_de_dia.registrar("atendimento", FILTRADO)

DESCRICAO_DA_ORIGEM = {
    Origem.PRODUCAO_TS: "Produção na versão TypeScript",
    Origem.PRODUCAO_PY: "Produção na versão Python",
    Origem.RELEASE: "Release, onde a equipe testa",
}


def _uma_em_cada(parte: int, todo: int) -> str:
    if not parte or not todo:
        return "nenhuma"
    vezes = round(todo / parte)
    return "quase todas" if vezes <= 1 else f"uma em cada {vezes}"


def _no_periodo(dados: LeiturasDoAtendimento) -> str:
    return "no período" if dados.dia is None else f"em {data_curta(dados.dia)}"


def _periodo(dados: LeiturasDoAtendimento) -> str:
    resumo = dados.resumo.valor
    assert resumo is not None
    if dados.dia is not None:
        return f"{DESCRICAO_DA_ORIGEM[dados.origem]}, só {dia_da_semana_e_data(dados.dia)}."
    inicio, fim = resumo.inicio, resumo.fim
    if inicio.month == fim.month:
        trecho = f"de {inicio.day} a {fim.day} de {MESES[fim.month - 1]}"
    else:
        trecho = f"de {inicio.day} de {MESES[inicio.month - 1]} a {fim.day} de {MESES[fim.month - 1]}"
    return f"{DESCRICAO_DA_ORIGEM[dados.origem]}, {trecho}."


# ── Indicadores ───────────────────────────────────────────────────────────


def _indicadores(dados: LeiturasDoAtendimento, escolha: Filtro = Filtro()) -> list[html.Section]:
    resumo, agora = dados.resumo, dados.agora

    def r() -> Any:
        assert resumo.valor is not None
        return resumo.valor

    vazio = f"Nenhum atendimento {_no_periodo(dados)}."
    terminaram = filtro_de_dia.terminaram_no_motivo(dados.desfechos, escolha.motivo, vazio, agora)
    return [
        indicador("Começaram", "conversa", [resumo], lambda: Valor(numero(r().comecaram)), vazio, agora),
        terminaram or indicador("Terminaram", "certo", [resumo], lambda: Valor(numero(r().terminaram)), vazio, agora),
        indicador(
            "Pararam no meio",
            "alerta",
            [resumo],
            lambda: Valor(numero(r().comecaram - r().terminaram), legenda=_uma_em_cada(r().comecaram - r().terminaram, r().comecaram)),
            vazio,
            agora,
        ),
        indicador(
            "Perguntas por conversa",
            "busca",
            [resumo],
            lambda: Valor(
                f"{r().perguntas / r().comecaram:.1f}".replace(".", ",") if r().comecaram else "0",
                legenda=f"{numero(r().perguntas)} {_no_periodo(dados)}",
            ),
            vazio,
            agora,
        ),
        indicador("Período", "relogio", [resumo], lambda: Valor(_periodo(dados), longo=True), vazio, agora),
    ]


# ── Buscas que não acharam a pessoa ───────────────────────────────────────


def _conclusao(trecho: TrechoDeNaoEncontrado) -> str | None:
    c = trecho.credencial
    if c.credencial_recusada and not c.aceitas and trecho.nao_encontrado == trecho.encerramentos:
        return (
            f"Nenhum desses {numero(trecho.encerramentos)} atendimentos esbarrou num RG inexistente. O Verde estava "
            "recusando a credencial, e a Maria disse à pessoa que não encontrou o registro dela."
        )
    if c.credencial_recusada:
        return (
            f'No trecho "{trecho.rotulo.lower()}", a credencial foi recusada {numero(c.credencial_recusada)} vezes: parte '
            "desses encerramentos pode não ser RG inexistente."
        )
    return None


def _nao_acharam(trechos: list[TrechoDeNaoEncontrado]) -> list[Any]:
    barras = [
        barra_rotulada(
            t.rotulo,
            f"{numero(t.nao_encontrado)} de {numero(t.encerramentos)}, {round(100 * t.nao_encontrado / t.encerramentos) if t.encerramentos else 0}%",
            t.nao_encontrado / t.encerramentos if t.encerramentos else 0,
            "ruim" if t.encerramentos and t.nao_encontrado / t.encerramentos > 0.5 else "bom",
        )
        for t in trechos
    ]
    # A credencial do trecho com mais recusas: é ele que explica o "não achou".
    pior = max(trechos, key=lambda t: t.credencial.credencial_recusada)
    credencial = html.Dl(
        [
            peca
            for rotulo, valor, tom in (
                ("Consultas recusadas", pior.credencial.credencial_recusada, "ruim"),
                ("Erros do Verde", pior.credencial.erro_do_verde, "neutro"),
                ("Consultas aceitas", pior.credencial.aceitas, "neutro"),
            )
            for peca in (html.Dt(rotulo), html.Dd(numero(valor), className=f"numero-medio tom-{tom if valor else 'neutro'}"))
        ],
        className="definicoes definicoes-numeros",
    )
    colunas = html.Div(
        [
            html.Div([html.P('Encerramentos por "RG não encontrado"', className="rotulo-pequeno"), html.Div(barras, className="lista-de-barras")]),
            html.Div([html.P(f"A credencial do Verde no mesmo período: {pior.rotulo.lower()}", className="rotulo-pequeno"), credencial]),
        ],
        className="duas-colunas miolo",
    )
    conclusao = _conclusao(pior)
    return [colunas] + ([html.P(conclusao, className="faixa-de-conclusao")] if conclusao else [])


def _quadro_nao_acharam(dados: LeiturasDoAtendimento) -> html.Section:
    leitura = dados.nao_encontrado
    corpo = celula_de_leitura(leitura, _nao_acharam, f'Nenhum encerramento por "RG não encontrado" {_no_periodo(dados)}.')
    return quadro("Buscas que não acharam a pessoa", corpo, [leitura], dados.agora, lateral="este quadro nunca aparece sozinho")


# ── Escrita livre e o que ainda não se sabe ───────────────────────────────


def _orquestrador(resumo: ResumoDoOrquestrador) -> html.Div:
    linhas: tuple[tuple[str, int, Tom], ...] = (
        ("Entendeu e abriu um fluxo da Maria", resumo.identificou, "bom"),
        ("Era assunto da Tykhe e encaminhou", resumo.era_da_tykhe, "azul"),
        ("Não entendeu e mandou para outros", resumo.nao_entendeu, "atencao"),
        ("Precisou perguntar de novo", resumo.perguntou_de_novo, "rosa"),
    )
    maior = max(v for _, v, _ in linhas) or 1
    return html.Div([barra_rotulada(r, numero(v), v / maior, tom) for r, v, tom in linhas], className="lista-de-barras miolo")


def _quadro_orquestrador(dados: LeiturasDoAtendimento) -> html.Section:
    leitura = dados.orquestrador
    vazio = "Produção não chama o orquestrador hoje: nada a medir até a Tykhe usar a escrita livre."
    return quadro(
        "Quando a pessoa escreve livremente",
        celula_de_leitura(leitura, _orquestrador, vazio),
        [leitura],
        dados.agora,
        lateral="só no release",
    )


def _ainda_sem_resposta(dados: LeiturasDoAtendimento) -> html.Section:
    resumo = dados.resumo
    if resumo.estado is Estado.OK and resumo.valor is not None:
        paradas = resumo.valor.paradas
        texto_paradas = (
            "Nenhuma neste período. O aviso de inatividade de 24 horas não disparou nenhuma vez."
            if paradas == 0
            else f"{numero(paradas)} neste período receberam o aviso de inatividade de 24 horas."
        )
    elif resumo.estado is Estado.INDISPONIVEL:
        texto_paradas = "Não deu para ler agora."
    else:
        texto_paradas = "Sem atendimentos no período para contar."
    itens = html.Ul(
        [
            html.Li(
                [
                    html.P("Em que pergunta a pessoa para", className="atencao-titulo"),
                    html.P(
                        "O registro de cada pergunta não guarda qual pergunta foi feita. Com esse campo, este vira o quadro "
                        "mais útil do painel para o trabalho de linguagem simples.",
                        className="atencao-descricao",
                    ),
                ],
                className="atencao-linha linha-simples",
            ),
            html.Li(
                [html.P("Conversas que ficaram paradas", className="atencao-titulo"), html.P(texto_paradas, className="atencao-descricao")],
                className="atencao-linha linha-simples",
            ),
        ],
        className="atencao-lista",
    )
    return quadro("Ainda sem resposta", itens, [resumo], dados.agora, lateral="vazio tem texto próprio")


# ── Montagem ──────────────────────────────────────────────────────────────

CORTE = html.P(
    [
        html.Strong("Corte de versão. ", className="tom-atencao"),
        "Produção rodou TypeScript até 23/10 às 12:31 e Python depois. Os dois pedaços ficam em botões separados, em vez de somados num número só.",
    ],
    className="faixa-de-aviso",
)

NOTA_DO_PE = html.P(
    "O que este painel não sabe: se a pessoa foi atendida depois do encaminhamento, quanto esperou na fila e se o caso foi "
    "resolvido. Isso acontece na Tykhe, e nada disso chega aqui hoje.",
    className="nota-do-pe",
)


# ── Atendimentos por dia: o gráfico em que se escolhe o dia ───────────────


def _dias_do_trecho(origem: Origem, dias: list[ContagemPorDia], hoje: date) -> list[ContagemPorDia]:
    """Só os dias do trecho da origem: o TypeScript até o corte, o Python desde ele, o release em 7 dias."""
    corte = graficos.CORTE_DE_VERSAO.date()
    if origem is Origem.PRODUCAO_TS:
        primeiro, ultimo = INICIO_DO_TYPESCRIPT, corte
    elif origem is Origem.PRODUCAO_PY:
        primeiro, ultimo = corte, hoje
    else:
        primeiro, ultimo = hoje - timedelta(days=6), hoje
    return [d for d in dias if primeiro <= d.dia <= ultimo]


def _figura_por_dia(dias: list[ContagemPorDia], origem: Origem, tema: str | None, dia: Filtro | date | None) -> go.Figure:
    c = graficos.cores(tema)
    meio_dia = [datetime.combine(d.dia, time(12), tzinfo=FUSO) for d in dias]
    figura = go.Figure()
    for campo, cor, rotulo in (("comecaram", "bom", "começaram"), ("terminaram", "outro", "terminaram")):
        figura.add_bar(
            x=meio_dia, y=[getattr(d, campo) for d in dias], name=rotulo, marker_color=c[cor], hovertemplate=f"%{{x|%d/%m}}: %{{y}} {rotulo}<extra></extra>"
        )
    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="group",
        barcornerradius=3,
        height=200,
        xaxis={"showgrid": False, "fixedrange": True, "tickformat": "%d/%m"},
        yaxis={"showgrid": True, "gridcolor": c["grade"], "fixedrange": True, "rangemode": "tozero"},
    )
    if AMBIENTE_DA_ORIGEM[origem] is Ambiente.PRODUCAO:
        graficos.marcar_corte_de_versao(figura, meio_dia[0] - timedelta(hours=12), meio_dia[-1] + timedelta(hours=12), c["suave"])
    return filtro_de_dia.destacar(figura, dia, tema)


def conteudo_por_dia(leitura: Leitura[list[ContagemPorDia]], origem: Origem, tema: str | None, agora: datetime, dia: Filtro | date | None) -> list[Any]:
    """O miolo do quadro, com a fonte no pé. Clicar num dia filtra a tela naquele dia."""
    dias = _dias_do_trecho(origem, leitura.valor or [], agora.date())
    if leitura.estado is Estado.INDISPONIVEL:
        miolo: list[Any] = [texto_de_falha(leitura)]
    elif not any(d.comecaram or d.terminaram for d in dias):
        miolo = [html.P("Nenhum atendimento no trecho desta origem.", className="texto-vazio")]
    else:
        miolo = [
            filtro_de_dia.grafico("atendimento", "por-dia", _figura_por_dia(dias, origem, tema, dia)),
            html.Div(
                [html.Span([html.Span(className="legenda-cor tom-bom"), "começaram"]), html.Span([html.Span(className="legenda-cor tom-outro"), "terminaram"])],
                className="legenda",
            ),
        ]
        if origem is not Origem.RELEASE:
            miolo.append(
                html.P(
                    "A barra de 23/10 tem as duas versões, antes e depois do corte. Com esse dia escolhido, os quadros contam só a parte desta origem.",
                    className="quadro-explicacao miolo",
                )
            )
    return [html.Div(miolo, className="quadro-corpo"), html.Footer(nota_de_fonte([leitura], agora), className="quadro-pe")]


def _quadro_por_dia(dados: LeiturasDoAtendimento) -> html.Section:
    return html.Section(
        [
            html.Header([html.H2("Atendimentos por dia"), html.Div("o trecho da origem; clique num dia", className="quadro-lateral")], className="quadro-topo"),
            html.Div(conteudo_por_dia(dados.por_dia, dados.origem, None, dados.agora, dados.dia), id="atendimento-por-dia"),
        ],
        className="quadro",
    )


def _corpo(dados: LeiturasDoAtendimento, escolha: Filtro = Filtro()) -> list[Any]:
    return [
        html.Div(_indicadores(dados, escolha), className="grade-indicadores"),
        _quadro_nao_acharam(dados),
        html.Div([_quadro_orquestrador(dados), _ainda_sem_resposta(dados)], className="grade-dupla"),
        NOTA_DO_PE,
        lista_de_fontes(dados.todas(), dados.agora),
    ]


def blocos(origem: Origem, escolha: Filtro = Filtro()) -> list[Any]:
    return _corpo(ler_atendimento(origem, escolha.quando), escolha)


def _tela(escolha: Filtro) -> html.Div:
    dados = ler_atendimento(Origem.PRODUCAO_PY, escolha.quando)
    return html.Div(
        [
            cabecalho("Atendimento", "Como as conversas terminam?"),
            html.Div(
                [
                    html.Span("Origem", className="rotulo-pequeno"),
                    dcc.RadioItems(
                        id="atendimento-origem",
                        # O tipo do Dash não aceita lista de dicionários, que ele aceita na prática.
                        options=cast(Any, [{"label": NOME_DA_ORIGEM[o], "value": o.value} for o in Origem]),
                        value=Origem.PRODUCAO_PY.value,
                        inline=True,
                        className="seletor-de-origem",
                        inputClassName="filtro-ambiente-entrada",
                        labelClassName="origem-opcao",
                    ),
                ],
                className="linha-de-origem",
            ),
            CORTE,
            filtro_de_dia.armazem("atendimento", escolha),
            filtro_de_dia.faixa("atendimento", escolha),
            _quadro_por_dia(dados),
            html.Div(_corpo(dados, escolha), id="atendimento-corpo", className="tela-corpo"),
        ],
        className="tela",
    )


@callback(
    Output("atendimento-corpo", "children"),
    Input("relogio", "n_intervals"),
    Input("atendimento-origem", "value"),
    filtro_de_dia.entrada("atendimento"),
    prevent_initial_call=True,
)
def atualizar(_: int | None, origem: str | None, dia: str | None) -> list[Any]:
    return blocos(Origem(origem or Origem.PRODUCAO_PY.value), filtro_de_dia.filtro(dia))


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador.
@callback(
    Output("atendimento-por-dia", "children"),
    Input("relogio", "n_intervals"),
    Input("atendimento-origem", "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada("atendimento"),
)
def atualizar_o_grafico(_: int | None, origem: str | None, tema: str | None, dia: str | None) -> list[Any]:
    escolhida = Origem(origem or Origem.PRODUCAO_PY.value)
    leitura = obter_fonte().atendimentos_por_dia(AMBIENTE_DA_ORIGEM[escolhida])
    return conteudo_por_dia(leitura, escolhida, tema, leitura.lido_em, filtro_de_dia.filtro(dia))


def layout(dia: str | None = None, **_: str) -> html.Div:
    agora = datetime.now(FUSO)
    escolhido = filtro_de_dia.ler(dia, agora)
    # Os dias do trecho da origem que abre, lidos por trás: o clique num deles já encontra a leitura.
    for passado in dias_passados(DIAS_DO_REGISTRO, agora):
        if passado >= graficos.CORTE_DE_VERSAO.date():
            for consulta in ("resumo_do_periodo", "nao_encontrado", "orquestrador", "desfechos", "origem_nao_atendida"):
                preparar(consulta, Origem.PRODUCAO_PY, passado)
    lado = montar_ja(partial(lateral.do_atendimento, Origem.PRODUCAO_PY, None, Filtro(escolhido)))
    return com_lateral(_tela(Filtro(escolhido)), coluna("atendimento-lateral", lado.result()))


# A coluna da direita: a cada minuto, com o tema guardado e com o filtro da tela.
@callback(
    Output("atendimento-lateral", "children"),
    Input("relogio", "n_intervals"),
    Input("tema", "data"),
    Input("atendimento-origem", "value"),
    filtro_de_dia.entrada("atendimento"),
)
def atualizar_a_lateral(_: int | None, tema: str | None, filtro: str | None, dia: str | None) -> list[Any]:
    return lateral.do_atendimento(Origem(filtro or Origem.PRODUCAO_PY.value), tema, filtro_de_dia.filtro(dia))
