"""Tela QA: o QA está pegando os defeitos, e quanto custa?

Decisão da Nicole em 16/11 (visor-maria#10): o QA mostra o gasto e o que apareceu de
defeito para acertar, sem repetir o que as outras telas já mostram. Por isso:

- a contagem das execuções do CI ("Testes a cada mudança") fica na Agora, no
  Sistema e no Relatório do dia; aqui entra só o que o QA conferiu, conferência
  por conferência;
- o gasto total do release fica no Relatório da Aplicação; aqui entra só o gasto de
  cada rodada de QA, contra o teto de US$ 0,10 por rodada.

As duas rodadas de QA da Maria (maria-langgraph-pp #502): o ponta a ponta do CI,
com o Verde, a IA e o e-mail simulados (não gasta nada), e o QA da staging, que
conversa com o release de verdade. A largura toda, como a Infra: as listas pedem espaço.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, html

from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import Valor, celula_de_leitura, indicador, lista_de_fontes, quadro, selo, texto_de_falha
from painel.componentes.cabecalho import cabecalho
from painel.componentes.formato import contagem, data_curta, data_e_hora_curta, dinheiro, numero, sem_hifen
from painel.dados.fontes import INICIO_DO_QA
from painel.dados.modelo import FUSO, QA, TETO_DA_RODADA, TIPOS_DE_RODADA, AlertaDeCodigo, DefeitoDoQA, Estado, Leitura, RodadaDoQA
from painel.dados.telas import LeiturasDoQA, ler_qa

dash.register_page(__name__, path="/qa", name="QA", order=10, title="QA · Visor Maria")

TELA = "qa"
FILTRADO = "Os defeitos, as rodadas e o gasto passam a ser só os daquele dia."
DE_AGORA = "Os alertas do CodeQL continuam sendo os abertos agora."
filtro_de_dia.registrar(TELA, FILTRADO, DE_AGORA)
# Na lista de rodadas, as mais novas; acima disso, a tela diz quantas ficaram de fora.
RODADAS_NA_LISTA = 30
GRAVIDADE = {"critical": "crítica", "high": "alta", "medium": "média", "media": "média", "low": "baixa", "error": "erro", "warning": "aviso", "note": "nota"}


def _do_dia(itens: list[Any], dia: date | None) -> list[Any]:
    return [i for i in itens if dia is None or i.quando.astimezone(FUSO).date() == dia]


def _no_periodo(dia: date | None) -> str:
    return f"em {data_curta(dia)}" if dia else f"desde {data_curta(INICIO_DO_QA)}"


def _pr(numero_do_pr: int | None, commit: str) -> html.Span:
    partes: list[Any] = [f"PR {numero_do_pr}, " if numero_do_pr else "sem PR, "]
    if commit:
        partes.append(html.Code(commit))
    return html.Span(partes)


# ── Indicadores ───────────────────────────────────────────────────────────


def _indicadores(dados: LeiturasDoQA) -> list[html.Section]:
    leitura, agora, dia = dados.qa, dados.agora, dados.dia

    def valor() -> QA:
        assert leitura.valor is not None
        return leitura.valor

    def defeitos() -> list[DefeitoDoQA]:
        return _do_dia(list(valor().defeitos), dia)

    def da_staging() -> list[RodadaDoQA]:
        return [r for r in _do_dia(list(valor().rodadas), dia) if r.tipo == "staging"]

    def abertos() -> Valor:
        n = sum(d.resolvido_em is None for d in defeitos())
        return Valor(numero(n), "ruim" if n else "bom", legenda="para acertar" if n else "nada para acertar")

    def resolvidos() -> Valor:
        n = sum(d.resolvido_em is not None for d in defeitos())
        return Valor(numero(n), "bom" if n else "neutro", legenda="uma rodada seguinte passou inteira")

    def gasto() -> Valor:
        rodadas = da_staging()
        total = sum(r.custo for r in rodadas)
        return Valor(dinheiro(total, 4), legenda=f"{contagem(len(rodadas), 'rodada', 'rodadas')} da staging; o ponta a ponta não gasta")

    def mais_cara() -> Valor:
        rodadas = da_staging()
        if not rodadas:
            return Valor("nenhuma", legenda=f"nenhuma rodada da staging {_no_periodo(dia)}")
        maior = max(r.custo for r in rodadas)
        passou = maior > TETO_DA_RODADA
        return Valor(
            dinheiro(maior, 4),
            "ruim" if passou else "bom",
            legenda=f"teto de {dinheiro(TETO_DA_RODADA)} por rodada",
            tom_da_legenda="ruim" if passou else "neutro",
        )

    vazio = f"Nenhuma rodada de QA {_no_periodo(dia)}."
    return [
        indicador("Defeitos em aberto", "alerta", [leitura], abertos, vazio, agora),
        indicador("Defeitos resolvidos", "certo", [leitura], resolvidos, vazio, agora),
        indicador("Gasto de IA do QA", "carteira", [leitura], gasto, vazio, agora),
        indicador("Rodada mais cara", "busca", [leitura], mais_cara, vazio, agora),
    ]


# ── Os defeitos ───────────────────────────────────────────────────────────


def _situacao(defeito: DefeitoDoQA) -> Any:
    if defeito.resolvido_em is None:
        return selo("Aberto", "ruim")
    return html.Span([selo("Resolvido", "bom"), f" {data_e_hora_curta(defeito.resolvido_em)}"])


def _defeitos(dados: LeiturasDoQA) -> html.Section:
    leitura = dados.qa
    titulo = "O que o QA pegou para acertar"
    if leitura.estado is not Estado.OK or leitura.valor is None:
        corpo: Any = celula_de_leitura(leitura, lambda _: "", f"Nenhuma rodada de QA {_no_periodo(dados.dia)}.")
        return quadro(titulo, corpo, [leitura], dados.agora)
    # Os abertos primeiro; dentro de cada grupo, do mais novo para o mais velho.
    defeitos = sorted(_do_dia(list(leitura.valor.defeitos), dados.dia), key=lambda d: (d.resolvido_em is not None, -d.quando.timestamp()))
    if not defeitos:
        corpo = html.P(f"O QA não pegou nenhum defeito {_no_periodo(dados.dia)}.", className="texto-vazio")
        return quadro(titulo, corpo, [leitura], dados.agora)
    linhas = [
        html.Tr(
            [
                html.Td(data_e_hora_curta(d.quando), className="mono"),
                html.Td(TIPOS_DE_RODADA.get(d.tipo, d.tipo)),
                html.Td(sem_hifen(d.cenario)),
                html.Td(sem_hifen(d.detalhe) or "sem detalhe no resumo", className="texto-detalhe"),
                html.Td(_pr(d.pr, d.commit)),
                html.Td(_situacao(d)),
            ]
        )
        for d in defeitos
    ]
    tabela = html.Table(
        [
            html.Thead(html.Tr([html.Th(t) for t in ("Quando", "QA", "Conferência", "O que veio", "Onde", "Situação")])),
            html.Tbody(linhas),
        ],
        className="tabela",
    )
    abertos = sum(d.resolvido_em is None for d in defeitos)
    return quadro(titulo, tabela, [leitura], dados.agora, lateral=f"{contagem(abertos, 'aberto', 'abertos')}, os abertos primeiro")


# ── As rodadas e o gasto ──────────────────────────────────────────────────


def _custo(rodada: RodadaDoQA) -> Any:
    if rodada.tipo == "ponta_a_ponta":
        return html.Span("sem gasto (simulado)", className="texto-vazio")
    return html.Span(dinheiro(rodada.custo, 4), className="tom-ruim" if rodada.custo > TETO_DA_RODADA else "")


def _rodadas(dados: LeiturasDoQA) -> html.Section:
    leitura = dados.qa
    titulo = "Rodadas e gasto"
    if leitura.estado is not Estado.OK or leitura.valor is None:
        corpo: Any = celula_de_leitura(leitura, lambda _: "", f"Nenhuma rodada de QA {_no_periodo(dados.dia)}.")
        return quadro(titulo, corpo, [leitura], dados.agora)
    rodadas = _do_dia(list(leitura.valor.rodadas), dados.dia)
    if not rodadas:
        return quadro(titulo, html.P(f"Nenhuma rodada de QA {_no_periodo(dados.dia)}.", className="texto-vazio"), [leitura], dados.agora)
    mostradas = rodadas[:RODADAS_NA_LISTA]
    linhas = [
        html.Tr(
            [
                html.Td(data_e_hora_curta(r.quando), className="mono"),
                html.Td(TIPOS_DE_RODADA.get(r.tipo, r.tipo)),
                html.Td(_pr(r.pr, r.commit)),
                html.Td(
                    html.Span(f"{numero(r.passaram)} de {numero(r.total)}", className="tom-bom" if r.passou else "tom-ruim")
                    if r.total
                    else html.Span("não chegou às conferências", className="tom-ruim"),
                    className="numero",
                ),
                html.Td(_custo(r), className="numero"),
            ]
        )
        for r in mostradas
    ]
    pecas: list[Any] = [
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [html.Th("Quando"), html.Th("QA"), html.Th("Onde"), html.Th("Passaram", className="numero"), html.Th("Gasto de IA", className="numero")]
                    )
                ),
                html.Tbody(linhas),
            ],
            className="tabela",
        )
    ]
    if len(rodadas) > len(mostradas):
        pecas.append(html.P(f"E mais {contagem(len(rodadas) - len(mostradas), 'rodada', 'rodadas')} antes destas.", className="texto-vazio"))
    lateral = f"teto de {dinheiro(TETO_DA_RODADA)} por rodada da staging"
    return quadro(titulo, html.Div(pecas), [leitura], dados.agora, lateral=lateral)


# ── O CodeQL ──────────────────────────────────────────────────────────────


def _alertas(dados: LeiturasDoQA) -> html.Section:
    leitura: Leitura[list[AlertaDeCodigo]] = dados.alertas
    titulo = "Alertas do CodeQL"
    if leitura.estado is Estado.INDISPONIVEL:
        return quadro(titulo, texto_de_falha(leitura), [leitura], dados.agora)
    alertas = leitura.valor or []
    if not alertas:
        return quadro(titulo, html.P("Nenhum alerta aberto no código da Maria.", className="texto-vazio"), [leitura], dados.agora, lateral="abertos agora")
    linhas = [
        html.Tr(
            [
                html.Td(sem_hifen(a.regra)),
                html.Td(GRAVIDADE.get(a.gravidade, sem_hifen(a.gravidade))),
                html.Td(html.Code(f"{a.arquivo}:{a.linha}")),
                html.Td(data_curta(a.desde), className="mono"),
            ]
        )
        for a in alertas
    ]
    tabela = html.Table(
        [html.Thead(html.Tr([html.Th("Regra"), html.Th("Gravidade"), html.Th("Onde"), html.Th("Desde")])), html.Tbody(linhas)],
        className="tabela",
    )
    return quadro(titulo, tabela, [leitura], dados.agora, lateral="abertos agora")


# ── O gráfico dos dias ────────────────────────────────────────────────────


def _figura(leitura: Leitura[QA], agora: datetime, tema: str | None, dia: date | None) -> go.Figure:
    c = graficos.cores(tema)
    hoje = agora.astimezone(FUSO).date()
    primeiro = max(INICIO_DO_QA, hoje - timedelta(days=13))
    dias = [primeiro + timedelta(days=n) for n in range((hoje - primeiro).days + 1)]
    valor = leitura.valor
    achados = Counter(d.quando.astimezone(FUSO).date() for d in (valor.defeitos if valor else ()))
    rodadas = Counter(r.quando.astimezone(FUSO).date() for r in (valor.rodadas if valor else ()))
    meio_dia = [datetime.combine(d, time(12), tzinfo=FUSO) for d in dias]
    figura = go.Figure()
    figura.add_bar(x=meio_dia, y=[rodadas[d] for d in dias], name="rodadas", marker_color=c["suave"], hovertemplate="%{x|%d/%m}: %{y} rodadas<extra></extra>")
    figura.add_bar(x=meio_dia, y=[achados[d] for d in dias], name="defeitos", marker_color=c["ruim"], hovertemplate="%{x|%d/%m}: %{y} defeitos<extra></extra>")
    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="group",
        barcornerradius=3,
        height=160,
        xaxis={"showgrid": False, "fixedrange": True, "tickformat": "%d/%m"},
        yaxis={"visible": False, "fixedrange": True},
    )
    return filtro_de_dia.destacar(figura, dia, tema)


def _dias(dados: LeiturasDoQA, tema: str | None) -> html.Section:
    leitura = dados.qa
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    else:
        corpo = filtro_de_dia.grafico(TELA, "dias", _figura(leitura, dados.agora, tema, dados.dia))
    return quadro(
        "Os dias do QA",
        corpo,
        [leitura],
        dados.agora,
        lateral="rodadas (cinza) e defeitos (vermelho) por dia; clique num dia",
    )


NOTA_DO_PE = html.P(
    "O ponta a ponta roda no CI com o Verde, a IA e o email simulados, e por isso não gasta nada. O gasto de cada rodada "
    "da staging é o que o roteiro somou pelos tokens, no preço do Haiku, o teto seguro: o Qwen do release custa menos. "
    "O gasto total do release fica no Relatório da Aplicação.",
    className="nota-do-pe",
)


def blocos(dia: date | None, tema: str | None = None) -> list[Any]:
    dados = ler_qa(dia)
    return [
        _dias(dados, tema),
        html.Div(_indicadores(dados), className="grade-indicadores"),
        _defeitos(dados),
        html.Div([_rodadas(dados), _alertas(dados)], className="grade-dupla"),
        NOTA_DO_PE,
        lista_de_fontes(dados.todas(), dados.agora),
    ]


def _tela(dia: date | None) -> html.Div:
    return html.Div(
        [
            cabecalho("QA", "O QA está pegando os defeitos, e quanto custa?"),
            filtro_de_dia.armazem(TELA, dia),
            filtro_de_dia.faixa(TELA, dia),
            html.Div(blocos(dia), id="qa-corpo", className="tela-corpo"),
        ],
        className="tela tela-larga",
    )


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador ao gráfico.
@callback(
    Output("qa-corpo", "children"),
    Input("relogio", "n_intervals"),
    Input("tema", "data"),
    filtro_de_dia.entrada(TELA),
)
def atualizar(_: int | None, tema: str | None, guardado: Any) -> list[Any]:
    return blocos(filtro_de_dia.filtro(guardado).dia, tema)


def layout(dia: str | None = None, **_: str) -> html.Div:
    return _tela(filtro_de_dia.ler(dia, datetime.now(FUSO)))
