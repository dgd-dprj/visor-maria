"""A coluna da direita de cada tela: mais sinais, no espaço que sobrava.

Em tela larga (1600 px ou mais), a coluna fica ao lado da tela, presa no topo ao
rolar. Em tela menor, ela desce para depois do conteúdo. Cada bloco segue as
mesmas regras dos outros: fonte e hora ao lado, vazio com texto próprio, falha
dizendo o motivo, ambiente como filtro.

Os blocos saem do que a proposta de 26/10 aprovou para cada tela, menos o mapa
de dia da semana contra hora e "o banco aguenta" (cortados pela Nicole).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping
from datetime import date, datetime, time, timedelta
from functools import partial
from typing import Any

import plotly.graph_objects as go
from dash import dcc, html

from painel import gasto
from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import Tom, aria, barra_rotulada, quadro, texto_de_falha
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import MESES, contagem, data_curta, dinheiro, numero, segundos
from painel.dados import obter_fonte
from painel.dados.fontes import DIAS_DOS_FLUXOS
from painel.dados.modelo import (
    FUSO,
    NOME_DO_AMBIENTE,
    NOME_DO_PROBLEMA,
    RESULTADOS_DO_VERDE,
    Ambiente,
    ContagemPorHora,
    ConversasDoFluxo,
    Desfecho,
    Destino,
    DiaDoModelo,
    DiaDoVerde,
    EncaminhamentoNoDia,
    EnvioDoWhatsapp,
    Estado,
    HorarioDaConferencia,
    Leitura,
    Origem,
    OrigemNaoAtendida,
    ProblemaNoDia,
    RecursosDoServico,
    RequisicoesPorHora,
    TempoDeResposta,
    TipoDeProblema,
    TrechoDeNaoEncontrado,
    nome_do_desfecho,
    nome_do_fluxo,
    tipo_do_motivo,
)
from painel.dados.telas import LeiturasDaAplicacao, ler_ja
from painel.precos import total

DESTAQUE = "origem_processo_nao_suportada"
# O gráfico de texto escrito por chamada, na tela financeira: o clique escolhe a data do período.
ID_DOS_ESCRITOS = "aplicacao-grafico-escritos"


# ── Peças ─────────────────────────────────────────────────────────────────


def _mini(
    figura: go.Figure,
    tema: str | None,
    altura: int = 170,
    clicavel: tuple[str, str] | None = None,
    por: str = "dia",
    series: tuple[str, ...] = (),
    id_: str | None = None,
) -> dcc.Graph:
    """Um gráfico compacto. Com `clicavel` (a tela e o nome do gráfico nela), o clique
    filtra a tela; `por` e `series` dizem o que ele escolhe (componentes/filtro_de_dia.py).
    Com `id_`, um gráfico clicável que a própria tela trata (a financeira)."""
    figura.update_layout(**graficos.layout_base(tema), height=altura, bargap=0.25, separators=",.")
    figura.update_xaxes(showgrid=False, fixedrange=True)
    figura.update_yaxes(showgrid=True, gridcolor=graficos.cores(tema)["grade"], fixedrange=True, rangemode="tozero")
    if clicavel is not None:
        return filtro_de_dia.grafico(*clicavel, figura, "grafico grafico-compacto", por=por, series=series)
    if id_ is not None:
        return dcc.Graph(id=id_, figure=figura, config={"displayModeBar": False}, className="grafico grafico-compacto grafico-clicavel")
    return dcc.Graph(figure=figura, config={"displayModeBar": False}, className="grafico grafico-compacto")


def bloco(
    titulo: str, leitura: Leitura[Any], montar: Callable[[Any], Any], vazio: str, agora: datetime, lateral: Any = None, extras: list[Leitura[Any]] | None = None
) -> html.Section:
    """Um quadro compacto: o conteúdo, ou o texto do vazio, ou o motivo da falha."""
    leituras = [leitura, *(extras or [])]
    falha = next((item for item in leituras if item.estado is Estado.INDISPONIVEL), None)
    if falha is not None:
        corpo: Any = texto_de_falha(falha)
    elif leitura.valor is None or leitura.valor == []:
        corpo = html.P(vazio, className="texto-vazio")
    else:
        corpo = montar(leitura.valor)
    return quadro(titulo, corpo, leituras, agora, lateral=lateral, classe="compacto")


def _legenda(itens: list[tuple[str, str]]) -> html.Div:
    return html.Div([html.Span([html.Span(className=f"legenda-cor tom-{tom}"), texto]) for tom, texto in itens], className="legenda")


def _titulo_da_lateral() -> html.P:
    return html.P("Mais sinais", className="lateral-titulo")


# ── Atendimentos por hora ─────────────────────────────────────────────────


def barras_por_hora(
    horas: list[ContagemPorHora],
    tema: str | None,
    comparar: list[ContagemPorHora] | None = None,
    tela: str = "",
    escolha: Filtro = Filtro(),
    largo: bool = False,
) -> Any:
    """Os atendimentos hora a hora. `largo`, para a largura inteira da tela: toda
    hora no eixo, e os que terminaram ao lado dos que começaram."""
    c = graficos.cores(tema)
    figura = go.Figure()
    figura.add_bar(
        x=[h.hora.hour for h in horas],
        y=[h.comecaram for h in horas],
        name="começaram",
        marker_color=c["bom"],
        # A hora de cada barra, para o clique filtrar a tela nela.
        customdata=[h.hora.isoformat() for h in horas],
        hovertemplate="%{x}h: %{y} começaram<extra></extra>",
    )
    if largo:
        figura.add_bar(
            x=[h.hora.hour for h in horas],
            y=[h.terminaram for h in horas],
            name="terminaram",
            marker_color=c["azul"],
            customdata=[h.hora.isoformat() for h in horas],
            hovertemplate="%{x}h: %{y} terminaram<extra></extra>",
        )
        figura.update_layout(barmode="group")
    filtro_de_dia.destacar_hora(figura, escolha)
    if comparar is not None:
        figura.add_scatter(
            x=[h.hora.hour for h in comparar],
            y=[h.comecaram for h in comparar],
            mode="lines",
            line={"color": c["suave"], "dash": "dot", "width": 2},
            hovertemplate="%{x}h, uma semana antes: %{y}<extra></extra>",
        )
    marcas = list(range(24)) if largo else [0, 6, 12, 18, 23]
    figura.update_xaxes(range=[-0.5, 23.5], tickvals=marcas, ticktext=[f"{h}h" for h in marcas])
    total_hoje = sum(h.comecaram for h in horas)
    resumo = f"{numero(total_hoje)} começaram"
    if largo:
        pico = max(horas, key=lambda h: h.comecaram, default=None)
        resumo += f" e {numero(sum(h.terminaram for h in horas))} terminaram"
        if pico is not None and pico.comecaram:
            resumo += f"; a hora mais cheia foi a das {pico.hora.hour}h, com {numero(pico.comecaram)}"
    if comparar is not None:
        ate = len(horas)
        antes = sum(h.comecaram for h in comparar[:ate])
        resumo += f"; até esta hora, uma semana antes, foram {numero(antes)}"
    itens = [("bom", "começaram")] + ([("azul", "terminaram")] if largo else []) + ([("neutro", "mesmo dia, uma semana antes")] if comparar is not None else [])
    grafico = _mini(figura, tema, 260 if largo else 170, clicavel=(tela, "horas"), por="hora")
    return [grafico, _legenda(itens), html.P(resumo + ".", className="lateral-resumo")]


# ── Requisições e recursos ────────────────────────────────────────────────


def barras_de_requisicoes(horas: list[RequisicoesPorHora], tema: str | None, tela: str, escolha: Filtro = Filtro(), largo: bool = False) -> Any:
    """As requisições hora a hora. `largo`, para a largura inteira da tela: toda hora no eixo."""
    c = graficos.cores(tema)
    figura = go.Figure()
    figura.add_bar(
        x=[h.hora for h in horas],
        y=[h.requisicoes for h in horas],
        marker_color=c["outro"],
        customdata=[h.hora.isoformat() for h in horas],
        hovertemplate="%{x|%Hh}: %{y} requisições<extra></extra>",
    )
    filtro_de_dia.destacar_hora(figura, escolha)
    erros = [h for h in horas if h.erros_de_servidor]
    if erros:
        figura.add_scatter(
            x=[h.hora for h in erros],
            y=[h.requisicoes for h in erros],
            mode="markers",
            marker={"color": c["ruim"], "size": 9},
            customdata=[h.erros_de_servidor for h in erros],
            hovertemplate="%{x|%Hh}: %{customdata} erros de servidor<extra></extra>",
        )
    figura.update_xaxes(tickformat="%Hh", dtick=3_600_000 if largo else None)
    soma_erros = sum(h.erros_de_servidor for h in horas)
    janela = "em 24 horas" if escolha.dia is None else f"em {data_curta(escolha.dia)}"
    resumo = f"{numero(sum(h.requisicoes for h in horas))} requisições {janela}, com a varredura de robôs; "
    resumo += "nenhum erro de servidor." if not soma_erros else f"{numero(soma_erros)} erros de servidor, em vermelho."
    return [_mini(figura, tema, 240 if largo else 170, clicavel=(tela, "requisicoes"), por="hora"), html.P(resumo, className="lateral-resumo")]


def quadro_de_recursos(recursos: dict[Ambiente, Leitura[RecursosDoServico]], agora: datetime) -> html.Section:
    linhas: list[Any] = []
    for ambiente, leitura in recursos.items():
        linhas.append(html.P(NOME_DO_AMBIENTE[ambiente], className="rotulo-pequeno"))
        if leitura.estado is Estado.INDISPONIVEL:
            linhas.append(texto_de_falha(leitura))
            continue
        if leitura.valor is None:
            linhas.append(html.P("O ECS não mandou a medição.", className="texto-vazio"))
            continue
        r = leitura.valor
        for rotulo, atual, maxima in (("CPU", r.cpu_agora, r.cpu_maxima), ("Memória", r.memoria_agora, r.memoria_maxima)):
            tom: Tom = "ruim" if maxima >= 0.9 else "atencao" if maxima >= 0.75 else "bom"
            valor = f"{round(atual * 100)}% agora, até {round(maxima * 100)}% em 24 h"
            linhas.append(barra_rotulada(rotulo, valor, atual, tom, marca=maxima))
    return quadro("CPU e memória", html.Div(linhas, className="miolo"), list(recursos.values()), agora, lateral="parte do reservado", classe="compacto")


# ── Verde e conferência ───────────────────────────────────────────────────


LEGENDA_DO_VERDE = [(campo, tom, nome) for campo, nome, tom, _ in RESULTADOS_DO_VERDE]


def _verde_do_mes(dias: list[DiaDoVerde], ambiente: Ambiente, tema: str | None, escolha: Filtro = Filtro()) -> Any:
    c = graficos.cores(tema)
    figura = go.Figure()
    x = [datetime.combine(d.dia, time(12), tzinfo=FUSO) for d in dias]
    for campo, cor, rotulo in LEGENDA_DO_VERDE:
        figura.add_bar(
            x=x, y=[getattr(d, campo) for d in dias], marker_color=c[cor], name=rotulo, hovertemplate=f"%{{x|%d/%m}}: %{{y}}, {rotulo.lower()}<extra></extra>"
        )
    figura.update_layout(barmode="stack")
    figura.update_xaxes(tickformat="%d/%m")
    if ambiente is Ambiente.PRODUCAO:
        graficos.marcar_corte_de_versao(figura, x[0], x[-1], c["suave"])
    resultado = escolha.resultado_do_verde
    campo = resultado or "recusadas"
    com = [d for d in dias if getattr(d, campo)]
    nome = filtro_de_dia.nome_da_serie(campo)
    if resultado is None:
        resumo = "Nenhuma recusa da credencial em 30 dias." if not com else f"{numero(sum(d.recusadas for d in com))} recusas em {len(com)} dias."
    else:
        resumo = f"{nome}: nenhuma em 30 dias." if not com else f"{nome}: {numero(sum(getattr(d, campo) for d in com))}, em {len(com)} dias."
    figura = filtro_de_dia.destacar(figura, escolha, tema, filtro_de_dia.SERIES_DO_VERDE)
    return [
        _mini(figura, tema, 180, clicavel=("credencial", "verde-do-mes"), series=filtro_de_dia.SERIES_DO_VERDE),
        filtro_de_dia.legenda("credencial", LEGENDA_DO_VERDE, resultado),
        html.P(resumo, className="lateral-resumo"),
    ]


def _horarios(horarios: list[HorarioDaConferencia], tema: str | None, dia: date | None = None) -> Any:
    c = graficos.cores(tema)
    figura = go.Figure()
    figura.add_scatter(
        x=[h.dia for h in horarios],
        y=[h.comecou.hour + h.comecou.minute / 60 for h in horarios],
        mode="markers",
        marker={"color": [c["bom"] if h.passou else c["ruim"] for h in horarios], "size": 8},
        customdata=[f"{h.comecou:%d/%m, %H:%M}, {'passou' if h.passou else 'falhou'}" for h in horarios],
        hovertemplate="%{customdata}<extra></extra>",
    )
    figura.add_hline(y=9, line_dash="dot", line_color=c["suave"], annotation_text="agendada às 9h", annotation_font_color=c["suave"])
    figura.update_yaxes(range=[8, 17], tickvals=[9, 12, 15], ticktext=["9h", "12h", "15h"])
    figura.update_xaxes(tickformat="%d/%m")
    atrasos = [(h.comecou.hour * 60 + h.comecou.minute) - 9 * 60 for h in horarios]
    resumo = ""
    if atrasos:
        resumo = f"Começou entre {min(atrasos) // 60}h{min(atrasos) % 60:02d} e {max(atrasos) // 60}h{max(atrasos) % 60:02d} depois do agendado."
    return [
        _mini(filtro_de_dia.destacar(figura, dia, tema), tema, clicavel=("credencial", "horarios")),
        _legenda([("bom", "passou"), ("ruim", "falhou")]),
        html.P(resumo, className="lateral-resumo"),
    ]


# ── Como terminaram ───────────────────────────────────────────────────────


def barras_de_desfechos(desfechos: list[Desfecho], tema: str | None, tela: str, escolha: Filtro = Filtro()) -> Any:
    c = graficos.cores(tema)
    ordem = sorted(desfechos, key=lambda d: d.atendimentos)
    soma = sum(d.atendimentos for d in desfechos) or 1
    figura = go.Figure(
        go.Bar(
            x=[d.atendimentos for d in ordem],
            y=[nome_do_desfecho(d.motivo) for d in ordem],
            orientation="h",
            marker_color=[c["atencao"] if d.motivo == DESTAQUE else c["outro"] for d in ordem],
            # A parte e o código do motivo: o clique filtra a tela por ele.
            customdata=[[f"{round(d.atendimentos / soma * 100)}%", d.motivo] for d in ordem],
            hovertemplate="%{y}: %{x} (%{customdata[0]})<extra></extra>",
        )
    )
    figura.update_layout(margin={"l": 0, "r": 8, "t": 8, "b": 0})
    figura.update_yaxes(showgrid=False, automargin=True)
    filtro_de_dia.destacar_categoria(figura, [d.motivo for d in ordem], escolha)
    return [_mini(figura, tema, 40 + 30 * len(ordem), clicavel=(tela, "desfechos"), por="categoria")]


def _origem_em_destaque(leitura: Leitura[OrigemNaoAtendida], trechos: Leitura[list[TrechoDeNaoEncontrado]], no_periodo: str = "no período") -> Any:
    """O desfecho em destaque, aberto pelo que a consulta ao processo devolveu."""
    if leitura.estado is Estado.INDISPONIVEL:
        return texto_de_falha(leitura)
    if leitura.valor is None:
        return html.P(f"Nenhum atendimento terminou {no_periodo}.", className="texto-vazio")
    o = leitura.valor
    parte = round(o.total / o.finalizados * 100) if o.finalizados else 0
    pecas: list[Any] = [
        html.P(
            [html.Strong(f"{numero(o.total)} de {numero(o.finalizados)}"), f" atendimentos terminados ({parte}%) acabaram em origem do processo não atendida."],
            className="lateral-resumo",
        ),
        html.Ul(
            [
                html.Li(f"{numero(o.processo_com_outra_origem)}: o processo foi achado, com origem diferente de SEEU."),
                html.Li(
                    [
                        f"{numero(o.processo_nao_encontrado)}: o processo não foi achado, e a pessoa ouve que a origem não é atendida. ",
                        html.Span("Mensagem errada (issue #239).", className="tom-atencao"),
                    ]
                ),
                html.Li(f"{numero(o.consulta_falhou)}: a consulta ao processo falhou."),
            ],
            className="lista-simples",
        ),
    ]
    # Regra 6: o "RG não encontrado" do gráfico só se lê com a credencial do mesmo período.
    if trechos.estado is Estado.OK and trechos.valor:
        recusas = sum(t.credencial.credencial_recusada for t in trechos.valor)
        pecas.append(html.P(f"A credencial do Verde, no mesmo período: {numero(recusas)} consultas recusadas.", className="lateral-resumo"))
    return html.Div(pecas, className="miolo")


# ── Cada tela ─────────────────────────────────────────────────────────────
# Cada função recebe o filtro da tela (componentes/filtro_de_dia.py): as consultas
# leem `escolha.quando` (o dia ou a hora), e os gráficos destacam o que foi clicado.


def _quando(quando: date | None, agora: datetime) -> str:
    """ "hoje", ou o que foi escolhido num gráfico da tela: "em 22/10", "em 22/10, das 14h às 15h"."""
    return "hoje" if quando is None or quando == agora.date() else f"em {filtro_de_dia.rotulo(quando)}"


def da_credencial(tema: str | None, escolha: Filtro = Filtro()) -> list[Any]:
    fonte, agora = obter_fonte(), datetime.now(FUSO)
    verde = ler_ja(partial(fonte.verde_do_mes, Ambiente.PRODUCAO))
    horarios = ler_ja(fonte.horarios_da_conferencia)
    return [
        _titulo_da_lateral(),
        bloco(
            "Consultas ao Verde, 30 dias",
            verde.result(),
            lambda v: _verde_do_mes(v, Ambiente.PRODUCAO, tema, escolha),
            "Ninguém consultou o Verde nos últimos 30 dias.",
            agora,
            lateral="produção; clique num dia ou na legenda",
        ),
        bloco(
            "A que horas a conferência rodou",
            horarios.result(),
            lambda v: _horarios(v, tema, escolha.dia),
            "Nenhuma conferência agendada rodou em 30 dias.",
            agora,
            lateral="30 dias; clique num dia",
        ),
    ]


def do_atendimento(origem: Origem, tema: str | None, escolha: Filtro = Filtro()) -> list[Any]:
    fonte, agora = obter_fonte(), datetime.now(FUSO)
    quando = escolha.quando
    desfechos = ler_ja(partial(fonte.desfechos, origem, quando))
    destaque = ler_ja(partial(fonte.origem_nao_atendida, origem, quando))
    trechos = ler_ja(partial(fonte.nao_encontrado, origem, quando))
    leitura_do_destaque, leitura_dos_trechos = destaque.result(), trechos.result()
    no_periodo = "no período" if quando is None else _quando(quando, agora)
    return [
        _titulo_da_lateral(),
        bloco(
            "Como terminaram",
            desfechos.result(),
            lambda v: barras_de_desfechos(v, tema, "atendimento", escolha),
            f"Nenhum atendimento terminou {no_periodo}.",
            agora,
            lateral="clique num motivo",
        ),
        quadro(
            "Origem do processo não atendida",
            _origem_em_destaque(leitura_do_destaque, leitura_dos_trechos, no_periodo),
            [leitura_do_destaque, leitura_dos_trechos],
            agora,
            lateral="aberta pela consulta",
            classe="compacto destaque",
        ),
    ]


DIAS_DO_TEMPO = 14


def _dia_a_dia[T](leituras: dict[date, Leitura[T]]) -> Leitura[list[tuple[date, T]]]:
    """Leituras de vários dias numa só, sem perder o dia de cada uma: o dia vazio fica de fora."""
    itens = list(leituras.items())
    lido_em = max(leitura.lido_em for _, leitura in itens)
    falha = next((leitura for _, leitura in itens if leitura.estado is Estado.INDISPONIVEL), None)
    if falha is not None:
        return Leitura(None, Estado.INDISPONIVEL, falha.fonte, lido_em, falha.motivo)
    valores = [(d, leitura.valor) for d, leitura in itens if leitura.estado is Estado.OK and leitura.valor is not None]
    return Leitura(valores or None, Estado.OK if valores else Estado.VAZIO, itens[0][1].fonte, lido_em)


def _tempo_por_dia(dias: list[tuple[date, TempoDeResposta]], tema: str | None, escolha: Filtro) -> Any:
    """O tempo de resposta de cada dia: se a Maria ficou mais lenta, em que dia começou."""
    c = graficos.cores(tema)
    meio_dia = [datetime.combine(d, time(12), tzinfo=FUSO) for d, _ in dias]
    figura = go.Figure()
    for campo, nome, cor in (("metade_ate", "metade das respostas", "bom"), ("nove_em_dez_ate", "nove em dez", "atencao")):
        figura.add_scatter(
            x=meio_dia,
            y=[getattr(t, campo) for _, t in dias],
            mode="lines+markers",
            line={"color": c[cor]},
            # Pontos grandes: o clique num dia filtra a tela.
            marker={"size": 9},
            name=nome,
            hovertemplate=f"%{{x|%d/%m}}: {nome} em até %{{y:.1f}} s<extra></extra>",
        )
    figura.update_xaxes(tickformat="%d/%m")
    figura.update_yaxes(ticksuffix=" s", rangemode="tozero")
    filtro_de_dia.destacar(figura, escolha.dia, tema)
    pior = max(dias, key=lambda par: par[1].nove_em_dez_ate)
    resumo = f"O dia mais lento foi {data_curta(pior[0])}: nove em dez respostas em até {segundos(pior[1].nove_em_dez_ate)} s."
    return [
        _mini(figura, tema, 190, clicavel=("sistema", "tempo")),
        _legenda([("bom", "metade das respostas"), ("atencao", "nove em dez")]),
        html.P(resumo, className="lateral-resumo"),
    ]


def _erros_por_hora(horas: list[RequisicoesPorHora], tema: str | None, escolha: Filtro) -> Any:
    """Os erros de servidor (5xx) hora a hora, sem as requisições, que ficam na Agora."""
    c = graficos.cores(tema)
    total = sum(h.erros_de_servidor for h in horas)
    topo = max(3, max((h.erros_de_servidor for h in horas), default=0) + 1)
    figura = go.Figure()
    # Uma coluna clara por hora, atrás: sem erro nenhum, ainda dá para clicar na hora.
    figura.add_bar(
        x=[h.hora for h in horas],
        y=[topo] * len(horas),
        marker_color=c["grade"],
        customdata=[h.hora.isoformat() for h in horas],
        hovertemplate="%{x|%Hh}<extra></extra>",
    )
    figura.add_bar(
        x=[h.hora for h in horas],
        y=[h.erros_de_servidor for h in horas],
        marker_color=c["ruim"],
        customdata=[h.hora.isoformat() for h in horas],
        hovertemplate="%{x|%Hh}: %{y} erros de servidor<extra></extra>",
    )
    figura.update_layout(barmode="overlay")
    filtro_de_dia.destacar_hora(figura, escolha)
    figura.update_xaxes(tickformat="%Hh")
    figura.update_yaxes(range=[0, topo])
    janela = "em 24 horas" if escolha.dia is None else f"em {data_curta(escolha.dia)}"
    if total:
        pior = max(horas, key=lambda h: h.erros_de_servidor)
        resumo = (
            f"{contagem(total, 'erro de servidor', 'erros de servidor')} {janela}; a pior hora foi a das {pior.hora:%H}h, com {numero(pior.erros_de_servidor)}."
        )
    else:
        resumo = f"Nenhum erro de servidor {janela}: o que deu errado não foi a Maria cair."
    return [_mini(figura, tema, 150, clicavel=("sistema", "requisicoes"), por="hora"), html.P(resumo, className="lateral-resumo")]


def do_sistema(ambiente: Ambiente, tema: str | None, escolha: Filtro = Filtro()) -> list[Any]:
    """Só o que é do Sistema: o tempo de resposta dia a dia e os erros de servidor hora a hora.
    As requisições e CPU e memória ficam na Agora; a demora do modelo, no Observatório da IA."""
    fonte, agora = obter_fonte(), datetime.now(FUSO)
    hoje = agora.date()
    pedidos = ler_ja(partial(fonte.requisicoes_por_hora, ambiente, escolha.dia))
    tempos = {d: ler_ja(partial(fonte.tempo_de_resposta, ambiente, d)) for d in (hoje - timedelta(days=n) for n in range(DIAS_DO_TEMPO - 1, -1, -1))}
    nome = NOME_DO_AMBIENTE[ambiente].lower()
    return [
        _titulo_da_lateral(),
        bloco(
            f"Tempo de resposta, {DIAS_DO_TEMPO} dias",
            _dia_a_dia({d: f.result() for d, f in tempos.items()}),
            lambda v: _tempo_por_dia(v, tema, escolha),
            f"Nenhuma resposta em {DIAS_DO_TEMPO} dias.",
            agora,
            lateral=f"{nome}; clique num dia",
        ),
        bloco(
            "Erros de servidor por hora",
            pedidos.result(),
            lambda v: _erros_por_hora(v, tema, escolha),
            "O balanceador não contou requisição nas últimas 24 horas."
            if escolha.dia is None
            else f"O balanceador não contou requisição {_quando(escolha.dia, agora)}.",
            agora,
            lateral=f"{nome}; clique numa hora",
        ),
    ]


def _contas_do_dia(encerrados: list[EncaminhamentoNoDia], dia: date) -> dict[str, int]:
    do_dia = [e for e in encerrados if e.dia == dia]
    humano = [e for e in do_dia if e.destino is Destino.HUMANO]
    return {
        "terminaram": sum(e.atendimentos for e in do_dia),
        "maria": sum(e.atendimentos for e in do_dia if e.destino is Destino.IA),
        "humano": sum(e.atendimentos for e in humano),
        "falha": sum(e.atendimentos for e in humano if tipo_do_motivo(e.motivo) is TipoDeProblema.FALHA),
    }


def _contra_a_semana(encerrados: list[EncaminhamentoNoDia], dia: date, hoje: date) -> Any:
    """O dia ao lado da média dos 7 dias antes. As partes (quanto a Maria resolveu) se
    comparam mesmo com o dia em curso; as contagens de hoje ainda vão crescer."""
    no_dia = _contas_do_dia(encerrados, dia)
    semana = [_contas_do_dia(encerrados, dia - timedelta(days=n)) for n in range(1, 8)]
    media = {campo: sum(s[campo] for s in semana) / 7 for campo in no_dia}

    def parte(contas: Mapping[str, float], campo: str) -> float:
        return contas[campo] / contas["terminaram"] * 100 if contas["terminaram"] else 0.0

    def diferenca(agora_: float, antes: float, unidade: str, melhor_se_menor: bool, contagem_do_dia: bool = False) -> html.Td:
        # A contagem de hoje ainda vai crescer: comparar com o dia inteiro seria alarme falso.
        if contagem_do_dia and dia == hoje:
            return html.Td("dia em curso", className="tom-suave")
        if abs(agora_ - antes) < 0.5:
            return html.Td("igual", className="tom-suave")
        mais = agora_ > antes
        tom = "ruim" if mais == melhor_se_menor else "bom"
        return html.Td(f"{round(abs(agora_ - antes))}{unidade} a {'mais' if mais else 'menos'}", className=f"tom-{tom}")

    linhas = [
        (
            "Terminaram",
            numero(no_dia["terminaram"]),
            numero(round(media["terminaram"])),
            diferenca(no_dia["terminaram"], media["terminaram"], "", False, contagem_do_dia=True),
        ),
        (
            "Resolvidos pela Maria",
            f"{round(parte(no_dia, 'maria'))}%",
            f"{round(parte(media, 'maria'))}%",
            diferenca(parte(no_dia, "maria"), parte(media, "maria"), " pontos", False),
        ),
        (
            "Foram para pessoa",
            f"{round(parte(no_dia, 'humano'))}%",
            f"{round(parte(media, 'humano'))}%",
            diferenca(parte(no_dia, "humano"), parte(media, "humano"), " pontos", True),
        ),
        (
            "Por falha técnica",
            numero(no_dia["falha"]),
            f"{media['falha']:.1f}".replace(".", ","),
            diferenca(no_dia["falha"], media["falha"], "", True, contagem_do_dia=True),
        ),
    ]
    tabela = html.Table(
        [
            html.Thead(html.Tr([html.Th(""), html.Th("No dia", className="numero"), html.Th("Média", className="numero"), html.Th("Diferença")])),
            html.Tbody(
                [html.Tr([html.Th(n, scope="row"), html.Td(a, className="numero mono"), html.Td(b, className="numero mono"), d]) for n, a, b, d in linhas]
            ),
        ],
        className="tabela tabela-compacta",
    )
    nota = "Hoje ainda está em curso: compare as partes; as contagens vão crescer." if dia == hoje else "A média é a dos 7 dias antes, dia a dia."
    return [tabela, html.P(nota, className="lateral-resumo")]


# O que aconteceu com a conversa em cada problema do caminho (dados/modelo.py, NOME_DO_PROBLEMA).
PARA_PESSOA = "A conversa foi para atendimento humano."
NAO_CHEGOU = "A resposta não chegou à pessoa."
DESTINO_DO_PROBLEMA = {
    "falha_infra_verde": PARA_PESSOA,
    "orquestrador_inconsistencia": PARA_PESSOA,
    "atendimento_expirado": "A conversa terminou sem resposta da pessoa.",
    "atendimento_sem_checkpoint": "A conversa perdeu o ponto em que estava.",
    "whatsapp_envio_falhou": NAO_CHEGOU,
    "whatsapp_envio_erro": NAO_CHEGOU,
    "whatsapp_status_entrega": NAO_CHEGOU,
    "whatsapp_bridge_erro": NAO_CHEGOU,
}


def _problemas_do_dia(problemas: list[ProblemaNoDia], encerrados: list[EncaminhamentoNoDia], dia: date) -> Any:
    por_problema = Counter[str]()
    for p in problemas:
        if p.dia == dia:
            por_problema[p.problema] += p.vezes
    linhas = [(n, NOME_DO_PROBLEMA.get(nome, nome), DESTINO_DO_PROBLEMA.get(nome, "A conversa seguiu.")) for nome, n in por_problema.items()]
    # As outras falhas de sistema que levaram a pessoa ao atendimento humano (o Verde já está acima).
    for motivo in ("falha_cadastro", "falha_encaminhamento", "sem_orgao_disponivel"):
        n = sum(e.atendimentos for e in encerrados if e.dia == dia and e.motivo == motivo and e.destino is Destino.HUMANO)
        if n:
            linhas.append((n, nome_do_desfecho(motivo), PARA_PESSOA))
    if not linhas:
        return html.P("Nenhum problema registrado no caminho das conversas neste dia.", className="texto-vazio miolo")
    itens = [
        html.Li(
            [
                html.Span(numero(n), className="mono problema-vezes"),
                html.Div([html.P(nome, className="atencao-titulo"), html.P(destino, className="atencao-descricao")]),
            ]
        )
        for n, nome, destino in sorted(linhas, key=lambda linha: -linha[0])
    ]
    return html.Ul(itens, className="problemas-do-dia")


def do_dia(tema: str | None, escolha: Filtro = Filtro()) -> list[Any]:
    """Só o que é do relatório: o dia contra a semana e o que aconteceu em cada problema.
    O dia hora a hora e como terminaram ficam na Agora."""
    del tema
    fonte, agora = obter_fonte(), datetime.now(FUSO)
    dia = escolha.dia or agora.date()
    encaminhamentos = ler_ja(partial(fonte.encaminhamentos_por_dia, Ambiente.PRODUCAO))
    problemas = ler_ja(partial(fonte.problemas_por_dia, Ambiente.PRODUCAO))
    encerrados, de_problemas = encaminhamentos.result(), problemas.result()
    no_dia = _quando(escolha.dia, agora)
    return [
        _titulo_da_lateral(),
        bloco(
            "O dia contra a semana anterior",
            encerrados,
            lambda v: _contra_a_semana(v, dia, agora.date()),
            f"Nenhum atendimento terminou {no_dia}.",
            agora,
            lateral="produção",
        ),
        bloco(
            "Os problemas do dia",
            de_problemas,
            lambda v: _problemas_do_dia(v, encerrados.valor or [], dia),
            "Nenhum problema registrado no caminho das conversas em 30 dias.",
            agora,
            lateral=f"produção, {no_dia}; e o que aconteceu com a conversa",
            extras=[encerrados],
        ),
    ]


NOME_DO_ENVIO = {
    "whatsapp_envio_ok": "Enviadas ao WhatsApp",
    "whatsapp_envio_falhou": "Recusadas pelo WhatsApp",
    "whatsapp_envio_erro": "Erro ao enviar",
    "whatsapp_bridge_erro": "Erro na ponte com o WhatsApp",
    "whatsapp_status_entrega": "Não chegaram à pessoa",
}


def _envios(envios: list[EnvioDoWhatsapp]) -> Any:
    por_rotulo: dict[str, int] = {}
    for e in envios:
        rotulo = NOME_DO_ENVIO.get(e.evento, e.evento) + (f", código {e.codigo}" if e.codigo else "")
        por_rotulo[rotulo] = por_rotulo.get(rotulo, 0) + e.vezes
    maior = max(por_rotulo.values()) or 1
    enviadas = sum(e.vezes for e in envios if e.evento == "whatsapp_envio_ok")
    problemas = sum(e.vezes for e in envios if e.evento != "whatsapp_envio_ok")
    linhas = [
        barra_rotulada(rotulo, numero(vezes), vezes / maior, "bom" if rotulo.startswith("Enviadas") else "ruim")
        for rotulo, vezes in sorted(por_rotulo.items(), key=lambda par: -par[1])
    ]
    resumo = f"{numero(problemas)} com problema para {numero(enviadas)} enviadas."
    return html.Div([html.Div(linhas, className="lista-de-barras"), html.P(resumo, className="lateral-resumo")], className="miolo")


def _sem_resposta(conversas: list[ConversasDoFluxo], escolha: Filtro) -> Any:
    """Conversas em que a pessoa não respondeu nem a primeira pergunta, por fluxo."""
    total: dict[str, int] = {}
    sem: dict[str, int] = {}
    for c in conversas:
        if escolha.fluxo is not None and c.fluxo != escolha.fluxo:
            continue
        total[c.fluxo] = total.get(c.fluxo, 0) + c.conversas
        if c.respostas == 0:
            sem[c.fluxo] = sem.get(c.fluxo, 0) + c.conversas
    linhas = [
        barra_rotulada(
            nome_do_fluxo(f),
            f"{numero(sem.get(f, 0))} de {numero(total[f])}",
            sem.get(f, 0) / total[f] if total[f] else 0,
            "ruim" if total[f] and sem.get(f, 0) / total[f] > 0.3 else "atencao" if sem.get(f, 0) else "bom",
        )
        for f in sorted(total, key=lambda f: -total[f])
    ]
    return html.Div(
        [
            html.Div(linhas, className="lista-de-barras"),
            html.P("Quando a parte sem resposta sobe, a primeira pergunta do fluxo pode não estar chegando ou não estar clara.", className="lateral-resumo"),
        ],
        className="miolo",
    )


def dos_fluxos(ambiente: Ambiente, tema: str | None, escolha: Filtro = Filtro()) -> list[Any]:
    """`tema` fica pela forma das outras colunas: os blocos daqui não têm gráfico."""
    fonte, agora = obter_fonte(), datetime.now(FUSO)
    envios = ler_ja(partial(fonte.envios_do_whatsapp, ambiente, escolha.quando))
    conversas = ler_ja(partial(fonte.conversas_por_fluxo, ambiente, escolha.quando))
    janela = f"{DIAS_DOS_FLUXOS} dias" if escolha.quando is None else filtro_de_dia.rotulo(escolha.quando)
    return [
        _titulo_da_lateral(),
        bloco(
            "Mensagens pelo WhatsApp",
            envios.result(),
            _envios,
            "Nenhum envio direto ao WhatsApp registrado neste ambiente no período.",
            agora,
            lateral=janela,
        ),
        bloco(
            "Sem nenhuma resposta",
            conversas.result(),
            lambda v: _sem_resposta(v, escolha),
            "Nenhuma conversa começou no período.",
            agora,
            lateral=f"por fluxo, {janela}",
        ),
    ]


def _projecao(dados: LeiturasDaAplicacao) -> Any:
    """Se o ritmo do mês continuar: o gasto até a âncora, dividido pelos dias que
    passaram, vezes os dias do mês. É conta sobre o medido, e diz isso."""
    ancora = dados.periodo.ultimo_dia
    t = gasto.trechos(ancora).mes
    leitura = dados.gasto(t.primeiro, t.ultimo)
    if leitura.estado is Estado.INDISPONIVEL:
        return texto_de_falha(leitura)
    if leitura.valor is None or not total(leitura.valor):
        return html.P("Nenhum gasto medido no mês até aqui.", className="texto-vazio")
    passados = (ancora - t.primeiro).days + 1
    dias_do_mes = gasto.ultimo_do_mes(ancora).day
    ate_agora = total(leitura.valor)
    if passados == dias_do_mes:
        return html.Div(
            html.P([html.Strong(dinheiro(ate_agora)), f" em {MESES[ancora.month - 1]}, mês inteiro."], className="lateral-resumo"),
            className="miolo",
        )
    projecao = ate_agora / passados * dias_do_mes
    return html.Div(
        [
            html.P([f"Se o ritmo de {MESES[ancora.month - 1]} continuar, o mês fecha em ", html.Strong(dinheiro(projecao)), "."], className="lateral-resumo"),
            html.P(
                f"Conta: {dinheiro(ate_agora)} em {passados} dias, até {data_curta(ancora)}, vezes {dias_do_mes} dias. Só a inteligência artificial; servidores e rede esperam a fatura.",
                className="quadro-explicacao",
            ),
        ],
        className="miolo",
    )


def da_aplicacao(dados: LeiturasDaAplicacao, tema: str | None) -> list[Any]:
    modelo = obter_fonte().saude_do_modelo()
    t = gasto.trechos(dados.periodo.ultimo_dia).mes
    leitura_do_mes = dados.gasto(t.primeiro, t.ultimo)
    return [
        _titulo_da_lateral(),
        quadro("Projeção do mês", _projecao(dados), [leitura_do_mes], dados.agora, lateral="conta sobre o medido", classe="compacto"),
        bloco(
            "Texto escrito por chamada",
            modelo,
            lambda dias: _escritos(dias, tema),
            "O modelo não foi chamado em 14 dias.",
            dados.agora,
            lateral="14 dias",
        ),
    ]


def _escritos(dias: list[DiaDoModelo], tema: str | None) -> Any:
    """O texto escrito custa 5 vezes o lido: se cada chamada passa a escrever mais, o gasto sobe."""
    c = graficos.cores(tema)
    figura = go.Figure()
    figura.add_bar(
        x=[d.dia for d in dias],
        y=[d.escritos_por_chamada for d in dias],
        marker_color=c["rosa"],
        hovertemplate="%{x|%d/%m}: %{y:.0f} tokens por chamada<extra></extra>",
    )
    figura.update_xaxes(tickformat="%d/%m")
    com_chamada = [d for d in dias if d.chamadas]
    media = sum(d.escritos_por_chamada for d in com_chamada) / len(com_chamada) if com_chamada else 0.0
    return [
        # A tela financeira tem o filtro de período dela: o clique num dia escolhe a data (pages/relatorio_aplicacao.py).
        _mini(figura, tema, id_=ID_DOS_ESCRITOS),
        html.P(
            f"Em média, {round(media)} tokens escritos por chamada. O texto escrito custa 5 vezes o lido: se este número sobe, o gasto sobe junto.",
            className="lateral-resumo",
        ),
    ]


def coluna(id_: str, filhos: list[Any]) -> html.Aside:
    return html.Aside(filhos, id=id_, className="tela-lateral", **aria(label="Mais sinais"))


def com_lateral(tela: Any, lateral: html.Aside) -> html.Div:
    return html.Div([tela, lateral], className="tela-e-lateral")
