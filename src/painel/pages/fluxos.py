"""Tela Fluxos: por onde as conversas passam, e onde travam?

Quais fluxos da Maria são mais procurados, se a triagem por escrita livre
consegue direcionar a pessoa, até onde cada conversa chega, como cada fluxo
termina e onde o caminho dá problema. Tudo sai dos logs, contado por conversa
dentro da consulta: nenhum texto é lido e nenhuma conversa é listada (regra 4).

Todo gráfico de dia, de fluxo, de motivo ou de problema filtra a tela
(componentes/filtro_de_dia.py): o dia ou a hora refazem as consultas nessa
janela; o fluxo, o motivo e o problema filtram os quadros que têm essa categoria.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from functools import partial
from typing import Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from painel import lateral
from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import Valor, indicador, lista_de_fontes, quadro, texto_de_falha
from painel.componentes.cabecalho import cabecalho, filtro_de_ambiente
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import data_curta, numero
from painel.dados.fontes import DIAS_DOS_FLUXOS
from painel.dados.modelo import (
    FAIXAS_DE_DURACAO,
    FUSO,
    NOME_DO_PROBLEMA,
    Ambiente,
    ConversasDoFluxo,
    Desfecho,
    Destino,
    Estado,
    FimDaConversa,
    SaidaDaTriagem,
    nome_do_desfecho,
    nome_do_fluxo,
    nome_do_tipo_de_caso,
)
from painel.dados.telas import LeiturasDosFluxos, dias_passados, ler_fluxos, montar_ja, preparar
from painel.lateral import coluna, com_lateral

dash.register_page(__name__, path="/fluxos", name="Fluxos", order=2, title="Fluxos · Visor Maria")

TELA = "fluxos"
ID_DO_AMBIENTE = "fluxos-ambiente"
FILTRADO = "Os números, os fluxos, a triagem, onde as conversas param e como terminam mostram o que foi escolhido."
DE_AGORA = "O histórico, quanto a Maria resolve e os problemas mostram os 30 dias, com o dia em destaque."
filtro_de_dia.registrar(TELA, FILTRADO, DE_AGORA)

# Como a conversa terminou: o rótulo e o tom de cada fim, na ordem das barras.
FINS = {
    FimDaConversa.CONCLUIU: ("concluiu na Maria", "bom"),
    FimDaConversa.ENCAMINHOU: ("encaminhada a atendimento humano", "azul"),
    FimDaConversa.PAROU: ("parou no meio", "atencao"),
    FimDaConversa.EXPIROU: ("expirou", "ruim"),
}
# As cores das séries de fluxo e de problema, em ordem.
CORES_EM_ORDEM = ("azul", "rosa", "bom", "atencao", "outro", "ruim")
# Respostas acima disto vão juntas no gráfico de onde as conversas param.
RESPOSTAS_NO_GRAFICO = 20


def _janela(d: LeiturasDosFluxos) -> str:
    return f"nos últimos {DIAS_DOS_FLUXOS} dias" if d.dia is None else f"em {filtro_de_dia.rotulo(d.dia)}"


def _conversas(d: LeiturasDosFluxos, escolha: Filtro) -> list[ConversasDoFluxo]:
    """As conversas da janela, só do fluxo escolhido quando há um."""
    todas = d.conversas.valor or []
    return [c for c in todas if escolha.fluxo is None or c.fluxo == escolha.fluxo]


def _rgba(cor: str, opacidade: float) -> str:
    cor = cor.lstrip("#")
    vermelho, verde, azul = (int(cor[i : i + 2], 16) for i in (0, 2, 4))
    return f"rgba({vermelho},{verde},{azul},{opacidade})"


def _layout(figura: go.Figure, tema: str | None, altura: int) -> go.Figure:
    c = graficos.cores(tema)
    figura.update_layout(**graficos.layout_base(tema), height=altura, separators=",.")
    figura.update_xaxes(showgrid=False, fixedrange=True)
    figura.update_yaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero")
    return figura


# ── Indicadores ───────────────────────────────────────────────────────────


def _uma_em_cada(parte: int, todo: int) -> str:
    if not parte or not todo:
        return "nenhuma"
    vezes = round(todo / parte)
    return "quase todas" if vezes <= 1 else f"uma em cada {vezes}"


def _problemas_na_janela(d: LeiturasDosFluxos, escolha: Filtro) -> int:
    """Os problemas da janela: os 7 dias, ou o dia escolhido (os problemas são contados por dia)."""
    hoje = d.agora.date()
    dias = {filtro_de_dia.dia_de(d.dia)} if d.dia is not None else {hoje - timedelta(days=n) for n in range(DIAS_DOS_FLUXOS)}
    return sum(
        p.vezes
        for p in d.problemas.valor or []
        if p.dia in dias and (escolha.fluxo is None or p.fluxo == escolha.fluxo) and (escolha.problema is None or p.problema == escolha.problema)
    )


def _indicadores(d: LeiturasDosFluxos, escolha: Filtro) -> html.Div:
    conversas, janela = _conversas(d, escolha), _janela(d)
    por_fim = Counter[FimDaConversa]()
    for c in conversas:
        por_fim[c.fim] += c.conversas
    total = sum(por_fim.values())
    vazio = f"Nenhuma conversa começou {janela}."

    def contagem(fim: FimDaConversa, legenda: str) -> Any:
        return lambda: Valor(numero(por_fim[fim]), legenda=legenda)

    parou = por_fim[FimDaConversa.PAROU] + por_fim[FimDaConversa.EXPIROU]
    em_andamento = d.dia is None or filtro_de_dia.dia_de(d.dia) == d.agora.date()
    problemas = _problemas_na_janela(d, escolha)
    no_dia = "no dia" if d.dia is not None else f"em {DIAS_DOS_FLUXOS} dias"
    return html.Div(
        [
            indicador("Conversas", "conversa", [d.conversas], lambda: Valor(numero(total), legenda=janela), vazio, d.agora),
            indicador("Concluíram na Maria", "certo", [d.conversas], contagem(FimDaConversa.CONCLUIU, "sem precisar de pessoa"), vazio, d.agora),
            indicador("Encaminhadas", "encaminhar", [d.conversas], contagem(FimDaConversa.ENCAMINHOU, "a atendimento humano, com o motivo"), vazio, d.agora),
            indicador(
                "Pararam no meio",
                "alerta",
                [d.conversas],
                lambda: Valor(
                    numero(parou),
                    "atencao" if parou else "neutro",
                    legenda=_uma_em_cada(parou, total) + (", com as que ainda estão em andamento" if em_andamento else ""),
                ),
                vazio,
                d.agora,
            ),
            indicador(
                "Problemas no caminho",
                "servidor",
                [d.problemas],
                lambda: Valor(numero(problemas), "ruim" if problemas else "bom", legenda=no_dia),
                "Nenhum problema registrado.",
                d.agora,
            ),
        ],
        className="grade-indicadores",
    )


# ── Fluxos mais acessados ─────────────────────────────────────────────────


def _fluxos(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    leitura, c = d.conversas, graficos.cores(tema)
    todas = leitura.valor or []
    por_fluxo: dict[str, Counter[FimDaConversa]] = {}
    for conversa in todas:
        por_fluxo.setdefault(conversa.fluxo, Counter())[conversa.fim] += conversa.conversas
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not por_fluxo:
        corpo = html.P(f"Nenhuma conversa começou {_janela(d)}.", className="texto-vazio")
    else:
        ordem = sorted(por_fluxo, key=lambda f: sum(por_fluxo[f].values()))
        nomes = [nome_do_fluxo(f) for f in ordem]
        figura = go.Figure()
        for fim, (rotulo, tom) in FINS.items():
            figura.add_bar(
                x=[por_fluxo[f][fim] for f in ordem],
                y=nomes,
                orientation="h",
                name=rotulo,
                marker={"color": c[tom], "opacity": [1.0 if escolha.fluxo in (None, f) else filtro_de_dia.APAGADO for f in ordem]},
                # O fluxo de cada barra: o clique filtra a tela por ele.
                customdata=[[rotulo, f"{filtro_de_dia.FLUXO}{f}"] for f in ordem],
                hovertemplate="%{y}: %{x} %{customdata[0]}<extra></extra>",
            )
        figura.update_layout(barmode="stack", margin={"l": 0, "r": 8, "t": 8, "b": 0})
        figura.update_yaxes(showgrid=False, automargin=True)
        mais = max(por_fluxo, key=lambda f: sum(por_fluxo[f].values()))
        total = sum(sum(v.values()) for v in por_fluxo.values())
        do_mais = sum(por_fluxo[mais].values())
        resumo = f"{nome_do_fluxo(mais)} recebe {round(do_mais / total * 100)}% das conversas ({numero(do_mais)} de {numero(total)})."
        corpo = [
            filtro_de_dia.grafico(TELA, "fluxos", _layout(figura, tema, 70 + 46 * len(ordem)), por="categoria"),
            _legenda_dos_fins(),
            html.P(resumo, className="quadro-explicacao miolo"),
        ]
    return quadro("Fluxos mais acessados", corpo, [leitura], d.agora, lateral=f"{_janela(d)}; clique num fluxo")


def _legenda_dos_fins() -> html.Div:
    return html.Div([html.Span([html.Span(className=f"legenda-cor tom-{tom}"), rotulo]) for rotulo, tom in FINS.values()], className="legenda")


# ── Triagem ───────────────────────────────────────────────────────────────

NOME_DA_SAIDA = {
    SaidaDaTriagem.IDENTIFICOU: ("Entrou num fluxo da Maria", "bom"),
    SaidaDaTriagem.REDIRECIONOU: ("Devolvida à Tykhe", "azul"),
    SaidaDaTriagem.SEM_FLUXO: ("Sem fluxo", "atencao"),
    SaidaDaTriagem.PERGUNTOU: ("Perguntou de novo", "outro"),
    SaidaDaTriagem.INCONSISTENCIA: ("Triagem inconsistente", "ruim"),
}


def _triagem(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    leitura, c = d.triagem, graficos.cores(tema)
    rodadas = leitura.valor or []
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not rodadas:
        corpo = html.P("A triagem por escrita livre não rodou neste ambiente no período: as conversas entraram direto num fluxo.", className="texto-vazio")
    else:
        nos = ["Escrita livre"]
        cores_dos_nos = [c["suave"]]
        fontes_, alvos, valores, cores_das_ligacoes = [], [], [], []

        def no(rotulo: str, cor: str) -> int:
            if rotulo not in nos:
                nos.append(rotulo)
                cores_dos_nos.append(cor)
            return nos.index(rotulo)

        por_saida = Counter[SaidaDaTriagem]()
        for r in rodadas:
            por_saida[r.saida] += r.vezes
        for saida, vezes in por_saida.items():
            rotulo, tom = NOME_DA_SAIDA[saida]
            fontes_.append(0)
            alvos.append(no(rotulo, c[tom]))
            valores.append(vezes)
            cores_das_ligacoes.append(_rgba(c[tom], 0.35))
        for r in rodadas:
            if r.saida not in (SaidaDaTriagem.IDENTIFICOU, SaidaDaTriagem.REDIRECIONOU, SaidaDaTriagem.SEM_FLUXO) or not r.alvo:
                continue
            rotulo, tom = NOME_DA_SAIDA[r.saida]
            folha = nome_do_fluxo(r.alvo) if r.saida is SaidaDaTriagem.IDENTIFICOU else f"Tykhe: {nome_do_tipo_de_caso(r.alvo)}"
            # O fluxo escolhido fica aceso; os outros caminhos, apagados.
            aceso = escolha.fluxo is None or (r.saida is SaidaDaTriagem.IDENTIFICOU and r.alvo == escolha.fluxo)
            fontes_.append(no(rotulo, c[tom]))
            alvos.append(no(folha, c[tom]))
            valores.append(r.vezes)
            cores_das_ligacoes.append(_rgba(c[tom], 0.45 if aceso else 0.1))
        figura = go.Figure(
            go.Sankey(
                node={"label": nos, "color": cores_dos_nos, "pad": 14, "thickness": 14, "line": {"width": 0}},
                link={"source": fontes_, "target": alvos, "value": valores, "color": cores_das_ligacoes},
                textfont={"color": c["texto"], "size": 12},
            )
        )
        # Altura pelo número de destinos: rótulos com pouco espaço se sobrepõem.
        figura.update_layout(**graficos.layout_base(tema), height=max(300, 34 * len(nos)))
        total = sum(por_saida.values())
        direcionou = por_saida[SaidaDaTriagem.IDENTIFICOU] + por_saida[SaidaDaTriagem.REDIRECIONOU]
        resumo = (
            f"A triagem direcionou {round(direcionou / total * 100)}% das rodadas ({numero(direcionou)} de {numero(total)}): "
            f"{numero(por_saida[SaidaDaTriagem.IDENTIFICOU])} para um fluxo da Maria e {numero(por_saida[SaidaDaTriagem.REDIRECIONOU])} para a Tykhe. "
            f"{numero(por_saida[SaidaDaTriagem.SEM_FLUXO])} ficaram sem fluxo e {numero(por_saida[SaidaDaTriagem.PERGUNTOU])} precisaram de outra pergunta."
        )
        corpo = [graficos_sem_clique(figura), html.P(resumo, className="quadro-explicacao miolo")]
    return quadro("Como a triagem direcionou", corpo, [leitura], d.agora, lateral=f"{_janela(d)}; cada rodada da escrita livre")


def graficos_sem_clique(figura: go.Figure) -> dcc.Graph:
    """Um gráfico que não filtra: o que ele mostra não é dia, hora nem categoria da tela."""
    return dcc.Graph(figure=figura, config={"displayModeBar": False}, className="grafico")


# ── Onde as conversas param ───────────────────────────────────────────────


def _onde_param(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    leitura, c = d.conversas, graficos.cores(tema)
    conversas = _conversas(d, escolha)
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not conversas:
        corpo = html.P(f"Nenhuma conversa começou {_janela(d)}.", className="texto-vazio")
    else:
        maior = min(max(x.respostas for x in conversas), RESPOSTAS_NO_GRAFICO)
        passos = list(range(maior + 1))
        chegaram = [sum(x.conversas for x in conversas if x.respostas >= k) for k in passos]
        pararam = [
            sum(x.conversas for x in conversas if x.fim in (FimDaConversa.PAROU, FimDaConversa.EXPIROU) and min(x.respostas, maior) == k) for k in passos
        ]
        rotulos = [str(k) if k < RESPOSTAS_NO_GRAFICO else f"{k} ou mais" for k in passos]
        figura = go.Figure()
        figura.add_bar(x=rotulos, y=pararam, name="pararam", marker_color=c["atencao"], hovertemplate="%{y} pararam depois de %{x} respostas<extra></extra>")
        figura.add_scatter(
            x=rotulos,
            y=chegaram,
            yaxis="y2",
            mode="lines+markers",
            name="chegaram",
            line={"color": c["azul"]},
            hovertemplate="%{y} chegaram a %{x} respostas<extra></extra>",
        )
        _layout(figura, tema, 250)
        figura.update_layout(
            barmode="overlay",
            xaxis={"type": "category", "title": {"text": "respostas que a pessoa deu", "font": {"size": 11}}},
            yaxis2={"overlaying": "y", "side": "right", "showgrid": False, "fixedrange": True, "rangemode": "tozero"},
        )
        sem_resposta = pararam[0]
        # O ponto em que mais param depois de começar a responder: onde o fluxo trava no meio.
        depois = max(passos[1:], key=lambda k: pararam[k], default=None)
        partes = []
        if sem_resposta:
            partes.append(f"{numero(sem_resposta)} pararam sem responder nem a primeira pergunta.")
        if depois is not None and pararam[depois]:
            plural = "resposta" if depois == 1 else "respostas"
            partes.append(f"Das que começaram a responder, mais param depois de {rotulos[depois]} {plural} ({numero(pararam[depois])} conversas).")
        resumo = " ".join(partes) or "Nenhuma conversa parou no meio."
        corpo = [
            graficos_sem_clique(figura),
            html.Div(
                [
                    html.Span([html.Span(className="legenda-cor tom-atencao"), "pararam nesse ponto"]),
                    html.Span([html.Span(className="legenda-cor tom-azul"), "chegaram até ele, à direita"]),
                ],
                className="legenda",
            ),
            html.P(resumo, className="quadro-explicacao miolo"),
        ]
    alcance = "todos os fluxos" if escolha.fluxo is None else nome_do_fluxo(escolha.fluxo)
    return quadro("Onde as conversas param", corpo, [leitura], d.agora, lateral=f"{alcance}, {_janela(d)}; segue o filtro, sem filtrar")


# ── Como cada fluxo termina e quanto leva ─────────────────────────────────


def _como_terminam(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    leitura = d.desfechos
    por_motivo = Counter[str]()
    for x in leitura.valor or []:
        if escolha.fluxo is None or x.fluxo == escolha.fluxo:
            por_motivo[x.motivo] += x.atendimentos
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not por_motivo:
        corpo = html.P(f"Nenhuma conversa terminou {_janela(d)}.", className="texto-vazio")
    else:
        desfechos = [Desfecho(m, n) for m, n in por_motivo.items()]
        corpo = lateral.barras_de_desfechos(desfechos, tema, TELA, escolha)
        if escolha.motivo is not None:
            deste = por_motivo[escolha.motivo]
            corpo = [*corpo, html.P(f"{nome_do_desfecho(escolha.motivo)}: {numero(deste)} de {numero(sum(por_motivo.values()))}.", className="lateral-resumo")]
    alcance = "todos os fluxos" if escolha.fluxo is None else nome_do_fluxo(escolha.fluxo)
    return quadro("Como terminam", corpo, [leitura], d.agora, lateral=f"{alcance}; clique num motivo")


def _quanto_leva(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    leitura, c = d.duracao, graficos.cores(tema)
    por_faixa = Counter[str]()
    for x in leitura.valor or []:
        if escolha.fluxo is None or x.fluxo == escolha.fluxo:
            por_faixa[x.faixa] += x.conversas
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not por_faixa:
        corpo = html.P(f"Nenhuma conversa terminou {_janela(d)}.", className="texto-vazio")
    else:
        figura = go.Figure(
            go.Bar(
                x=list(FAIXAS_DE_DURACAO.values()),
                y=[por_faixa[f] for f in FAIXAS_DE_DURACAO],
                marker_color=c["azul"],
                hovertemplate="%{x}: %{y} conversas<extra></extra>",
            )
        )
        total = sum(por_faixa.values())
        ate5 = por_faixa["ate2"] + por_faixa["ate5"]
        resumo = f"{round(ate5 / total * 100)}% terminaram em até 5 minutos; {numero(por_faixa['mais'])} levaram mais de uma hora."
        corpo = [graficos_sem_clique(_layout(figura, tema, 200)), html.P(resumo, className="quadro-explicacao miolo")]
    return quadro("Quanto a conversa leva", corpo, [leitura], d.agora, lateral="do começo ao fim, só as que terminaram; segue o filtro, sem filtrar")


# ── Histórico e problemas, dia a dia ──────────────────────────────────────


def _meio_dia(dia: date) -> datetime:
    return datetime.combine(dia, time(12), tzinfo=FUSO)


def _historico(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    leitura, c = d.por_dia, graficos.cores(tema)
    dias = leitura.valor or []
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not any(x.comecaram for x in dias):
        corpo = html.P("Nenhuma conversa começou nos últimos 30 dias.", className="texto-vazio")
    else:
        fluxos = sorted({x.fluxo for x in dias}, key=lambda f: -sum(x.comecaram for x in dias if x.fluxo == f))
        todos_os_dias = sorted({x.dia for x in dias})
        figura = go.Figure()
        for n, fluxo in enumerate(fluxos):
            do_fluxo = {x.dia: x for x in dias if x.fluxo == fluxo}
            figura.add_bar(
                x=[_meio_dia(dia) for dia in todos_os_dias],
                y=[do_fluxo[dia].comecaram if dia in do_fluxo else 0 for dia in todos_os_dias],
                name=nome_do_fluxo(fluxo),
                marker_color=c[CORES_EM_ORDEM[n % len(CORES_EM_ORDEM)]],
                customdata=[[nome_do_fluxo(fluxo), do_fluxo[dia].terminaram if dia in do_fluxo else 0] for dia in todos_os_dias],
                hovertemplate="%{x|%d/%m}, %{customdata[0]}: %{y} começaram, %{customdata[1]} terminaram<extra></extra>",
            )
        series = tuple(f"{filtro_de_dia.FLUXO}{f}" for f in fluxos)
        _layout(figura, tema, 220)
        figura.update_layout(barmode="stack", barcornerradius=2)
        figura.update_xaxes(tickformat="%d/%m")
        graficos.marcar_corte_de_versao(
            figura, _meio_dia(todos_os_dias[0]) - timedelta(hours=12), _meio_dia(todos_os_dias[-1]) + timedelta(hours=12), c["suave"]
        )
        figura = filtro_de_dia.destacar(figura, escolha, tema, series)
        por_dia = Counter[date]()
        for x in dias:
            if escolha.fluxo is None or x.fluxo == escolha.fluxo:
                por_dia[x.dia] += x.comecaram
        if por_dia and any(por_dia.values()):
            pico = max(por_dia, key=lambda k: por_dia[k])
            resumo = f"Em média, {numero(round(sum(por_dia.values()) / len(por_dia)))} conversas por dia; o dia com mais foi {data_curta(pico)}, com {numero(por_dia[pico])}."
        else:
            # O fluxo escolhido não roda neste ambiente.
            resumo = f"O {filtro_de_dia.nome_da_serie(escolha.serie or '')} não teve conversa neste ambiente nos últimos 30 dias."
        corpo = [
            filtro_de_dia.grafico(TELA, "historico", figura, series=series),
            html.Div(
                [
                    html.Span([html.Span(className=f"legenda-cor tom-{CORES_EM_ORDEM[n % len(CORES_EM_ORDEM)]}"), nome_do_fluxo(f)])
                    for n, f in enumerate(fluxos)
                ],
                className="legenda",
            ),
            html.P(resumo, className="quadro-explicacao miolo"),
        ]
    return quadro("Histórico, conversas por dia", corpo, [leitura], d.agora, lateral="30 dias; clique num dia ou num fluxo")


def _resolucao(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    """A parte que a Maria resolve sozinha, em cada fluxo, dia a dia: se o fluxo está
    melhorando ou piorando. O histórico mostra quantas conversas; este, o resultado delas."""
    leitura, c = d.encaminhamentos, graficos.cores(tema)
    titulo = "Quanto a Maria resolve sozinha, dia a dia"
    if leitura is None:
        return quadro(titulo, html.P("Esta leitura não entrou nesta rodada.", className="texto-vazio"), [], d.agora)
    encerrados = [e for e in leitura.valor or [] if e.fluxo]
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not encerrados:
        corpo = html.P("Nenhum atendimento terminou num fluxo nos últimos 30 dias.", className="texto-vazio")
    else:
        por_fluxo_e_dia: dict[str, dict[date, Counter[Destino]]] = {}
        for e in encerrados:
            por_fluxo_e_dia.setdefault(e.fluxo, {}).setdefault(e.dia, Counter())[e.destino] += e.atendimentos
        todos_os_dias = sorted({e.dia for e in encerrados})
        fluxos = sorted(por_fluxo_e_dia, key=lambda f: -sum(sum(x.values()) for x in por_fluxo_e_dia[f].values()))
        figura = go.Figure()
        for n, fluxo in enumerate(fluxos):
            dias = por_fluxo_e_dia[fluxo]

            def parte(dia: date, dias: dict[date, Counter[Destino]] = dias) -> float | None:
                total = sum(dias[dia].values()) if dia in dias else 0
                return round(dias[dia][Destino.IA] / total * 100) if total else None

            figura.add_scatter(
                x=[_meio_dia(dia) for dia in todos_os_dias],
                y=[parte(dia) for dia in todos_os_dias],
                mode="lines+markers",
                connectgaps=True,
                name=nome_do_fluxo(fluxo),
                line={"color": c[CORES_EM_ORDEM[n % len(CORES_EM_ORDEM)]], "width": 3 if escolha.fluxo in (None, fluxo) else 1},
                opacity=1.0 if escolha.fluxo in (None, fluxo) else filtro_de_dia.APAGADO,
                marker={"size": 8},
                customdata=[nome_do_fluxo(fluxo)] * len(todos_os_dias),
                hovertemplate="%{x|%d/%m}, %{customdata}: %{y}% resolvidos pela Maria<extra></extra>",
            )
        _layout(figura, tema, 220)
        figura.update_xaxes(tickformat="%d/%m")
        figura.update_yaxes(ticksuffix="%", range=[0, 100])
        figura = filtro_de_dia.destacar(figura, escolha, tema)
        totais = {f: Counter[Destino]() for f in fluxos}
        for fluxo, dias in por_fluxo_e_dia.items():
            for contas in dias.values():
                totais[fluxo].update(contas)

        def frase(fluxo: str) -> str:
            t = totais[fluxo]
            return f"{nome_do_fluxo(fluxo)}, {round(t[Destino.IA] / sum(t.values()) * 100)}% ({numero(t[Destino.IA])} de {numero(sum(t.values()))})"

        corpo = [
            filtro_de_dia.grafico(TELA, "resolucao", figura),
            html.Div(
                [
                    html.Span([html.Span(className=f"legenda-cor tom-{CORES_EM_ORDEM[n % len(CORES_EM_ORDEM)]}"), nome_do_fluxo(f)])
                    for n, f in enumerate(fluxos)
                ],
                className="legenda",
            ),
            html.P(
                f"Em 30 dias, a parte resolvida sem pessoa: {'; '.join(frase(f) for f in fluxos)}. "
                'O resto foi para atendimento humano, ou a pessoa saiu; os motivos estão em "Como terminam" e no Relatório da Aplicação.',
                className="quadro-explicacao miolo",
            ),
        ]
    return quadro(titulo, corpo, [leitura], d.agora, lateral="30 dias, em porcentagem; clique num dia")


def _problemas(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> html.Section:
    leitura, c = d.problemas, graficos.cores(tema)
    problemas = [p for p in leitura.valor or [] if escolha.fluxo is None or p.fluxo == escolha.fluxo]
    if leitura.estado is Estado.INDISPONIVEL:
        corpo: Any = texto_de_falha(leitura)
    elif not problemas:
        corpo = html.P("Nenhum problema registrado no caminho das conversas nos últimos 30 dias.", className="texto-vazio")
    else:
        hoje = d.agora.date()
        todos_os_dias = [hoje - timedelta(days=n) for n in range(29, -1, -1)]
        tipos = sorted({p.problema for p in problemas}, key=lambda t: -sum(p.vezes for p in problemas if p.problema == t))
        figura = go.Figure()
        for n, tipo in enumerate(tipos):
            por_dia = Counter[date]()
            for p in problemas:
                if p.problema == tipo:
                    por_dia[p.dia] += p.vezes
            nome = NOME_DO_PROBLEMA.get(tipo, tipo)
            figura.add_bar(
                x=[_meio_dia(dia) for dia in todos_os_dias],
                y=[por_dia[dia] for dia in todos_os_dias],
                name=nome,
                marker_color=c[("ruim", "atencao", "rosa", "outro", "azul", "bom")[n % 6]],
                customdata=[nome] * len(todos_os_dias),
                hovertemplate="%{x|%d/%m}: %{y}, %{customdata}<extra></extra>",
            )
        series = tuple(f"{filtro_de_dia.PROBLEMA}{t}" for t in tipos)
        _layout(figura, tema, 200)
        figura.update_layout(barmode="stack", barcornerradius=2)
        figura.update_xaxes(tickformat="%d/%m")
        figura = filtro_de_dia.destacar(figura, escolha, tema, series)
        totais = [(NOME_DO_PROBLEMA.get(t, t), sum(p.vezes for p in problemas if p.problema == t)) for t in tipos]
        corpo = [
            filtro_de_dia.grafico(TELA, "problemas", figura, series=series),
            filtro_de_dia.legenda(
                TELA,
                [
                    (f"{filtro_de_dia.PROBLEMA}{t}", ("ruim", "atencao", "rosa", "outro", "azul", "bom")[n % 6], NOME_DO_PROBLEMA.get(t, t))
                    for n, t in enumerate(tipos)
                ],
                escolha.serie if escolha.problema else None,
            ),
            html.Ul([html.Li(f"{nome}: {numero(vezes)} em 30 dias") for nome, vezes in totais], className="lista-simples miolo"),
        ]
    alcance = "todos os fluxos" if escolha.fluxo is None else nome_do_fluxo(escolha.fluxo)
    return quadro("Onde deu problema, por dia", corpo, [leitura], d.agora, lateral=f"{alcance}; clique num dia ou num problema")


# ── Montagem ──────────────────────────────────────────────────────────────

NOTA_DO_PE = html.P(
    "Cada conversa é contada dentro da consulta, pelo identificador dela, que nunca sai do registro: o painel não lê o que a pessoa escreveu. "
    "Uma conversa parou no meio quando começou e não terminou nem expirou; hoje, isso inclui as que ainda estão em andamento.",
    className="nota-do-pe",
)


def _corpo(d: LeiturasDosFluxos, tema: str | None, escolha: Filtro) -> list[Any]:
    return [
        _indicadores(d, escolha),
        html.Div([_fluxos(d, tema, escolha), _triagem(d, tema, escolha)], className="grade-dupla"),
        _onde_param(d, tema, escolha),
        html.Div([_como_terminam(d, tema, escolha), _quanto_leva(d, tema, escolha)], className="grade-dupla"),
        _historico(d, tema, escolha),
        _resolucao(d, tema, escolha),
        _problemas(d, tema, escolha),
        NOTA_DO_PE,
        lista_de_fontes(d.todas(), d.agora),
    ]


def blocos(ambiente: Ambiente, escolha: Filtro = Filtro(), tema: str | None = None) -> list[Any]:
    return _corpo(ler_fluxos(ambiente, escolha.quando), tema, escolha)


def layout(dia: str | None = None, **_: str) -> html.Div:
    agora = datetime.now(FUSO)
    escolha = Filtro(filtro_de_dia.ler(dia, agora))
    # Os dias mais novos do histórico, lidos por trás: o clique num deles já encontra a leitura.
    for passado in dias_passados(DIAS_DOS_FLUXOS * 2, agora):
        for consulta in ("conversas_por_fluxo", "desfechos_por_fluxo", "triagem", "duracao_das_conversas", "envios_do_whatsapp"):
            preparar(consulta, Ambiente.PRODUCAO, passado)
    lado = montar_ja(partial(lateral.dos_fluxos, Ambiente.PRODUCAO, None, escolha))
    tela = html.Div(
        [
            cabecalho(
                "Fluxos",
                "Por onde as conversas passam, e onde travam?",
                [html.Span("Ambiente", className="rotulo-filtro"), filtro_de_ambiente(ID_DO_AMBIENTE)],
            ),
            filtro_de_dia.armazem(TELA, escolha),
            filtro_de_dia.faixa(TELA, escolha),
            html.Div(blocos(Ambiente.PRODUCAO, escolha), id="fluxos-corpo", className="tela-corpo"),
        ],
        className="tela",
    )
    return com_lateral(tela, coluna("fluxos-lateral", lado.result()))


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador.
@callback(
    Output("fluxos-corpo", "children"),
    Input("relogio", "n_intervals"),
    Input(ID_DO_AMBIENTE, "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada(TELA),
)
def atualizar(_: int | None, ambiente: str | None, tema: str | None, guardado: Any) -> list[Any]:
    return blocos(Ambiente(ambiente or Ambiente.PRODUCAO.value), filtro_de_dia.filtro(guardado), tema)


@callback(
    Output("fluxos-lateral", "children"),
    Input("relogio", "n_intervals"),
    Input(ID_DO_AMBIENTE, "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada(TELA),
)
def atualizar_a_lateral(_: int | None, ambiente: str | None, tema: str | None, guardado: Any) -> list[Any]:
    return lateral.dos_fluxos(Ambiente(ambiente or Ambiente.PRODUCAO.value), tema, filtro_de_dia.filtro(guardado))
