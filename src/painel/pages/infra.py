"""Tela Infra: a infraestrutura está estável?

Pedido de 10/11: uma aba só para a infraestrutura da AWS, a instabilidade e a
saúde dela, em produção e no release (homologação). Cada parte por onde o
atendimento passa, hora a hora: a entrada (CloudFront), o tempo de resposta, os
containers, o banco, a saída para a internet, o Verde, o modelo de IA e a função
de email. O estado de cada hora sai dos limites de `dados/modelo.py`
(`estado_da_parte`), escritos em docs/decisoes.md.

O ambiente é filtro, no cabeçalho. "Saúde agora" é a exceção, de propósito: os dois
ambientes lado a lado. O banco, a saída, o modelo e o email são os mesmos nos dois.
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, html

from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import Tom, celula_de_leitura, lista_de_fontes, ponto, quadro
from painel.componentes.cabecalho import cabecalho, filtro_de_ambiente
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import contagem, dia_da_semana_e_data, numero, segundos
from painel.dados.fontes import DIAS_DA_INFRA
from painel.dados.modelo import (
    FUSO,
    LIMITE_DO_CORTE_S,
    NOME_DO_AMBIENTE,
    PARTES_DA_INFRA,
    Ambiente,
    Estado,
    EstadoDaParte,
    HoraDaInfra,
    Leitura,
    SaudeServico,
    estado_da_parte,
)
from painel.dados.telas import LeiturasDaInfra, ler_infra

dash.register_page(__name__, path="/infra", name="Infra", order=9, title="Infra · Visor Maria")

TELA = "infra"
TOM_DO_ESTADO: dict[EstadoDaParte, Tom] = {
    EstadoDaParte.BOM: "bom",
    EstadoDaParte.ATENCAO: "atencao",
    EstadoDaParte.RUIM: "ruim",
    EstadoDaParte.SEM_USO: "neutro",
}
NOME_DO_ESTADO = {
    EstadoDaParte.BOM: "estável",
    EstadoDaParte.ATENCAO: "instável",
    EstadoDaParte.RUIM: "com problema",
    EstadoDaParte.SEM_USO: "sem uso",
}
ORDEM_DO_ESTADO = {EstadoDaParte.SEM_USO: 0, EstadoDaParte.BOM: 1, EstadoDaParte.ATENCAO: 2, EstadoDaParte.RUIM: 3}

FILTRADO = "A instabilidade hora a hora, os picos e os gráficos mostram esse dia; com a hora escolhida, ela fica em destaque."
DE_AGORA = "A saúde agora e os 14 dias continuam sendo de agora."
filtro_de_dia.registrar(TELA, FILTRADO, DE_AGORA)


def _pior(*estados: EstadoDaParte) -> EstadoDaParte:
    return max(estados, key=lambda e: ORDEM_DO_ESTADO[e])


def _decimal(valor: float, casas: int = 0) -> str:
    return f"{valor:.{casas}f}".replace(".", ",")


def descrever(parte: str, h: HoraDaInfra) -> str:
    """Os números da parte naquela hora, como a pessoa lê."""
    if parte == "entrada":
        if not h.pedidos:
            return "nenhum pedido"
        return f"{contagem(h.pedidos, 'pedido', 'pedidos')}; {contagem(h.erros_5xx, 'erro 5xx', 'erros 5xx')} e {numero(h.erros_4xx)} 4xx"
    if parte == "tempo":
        if h.p99 is None:
            return "nenhum pedido medido"
        cortadas = f"; {contagem(h.respostas_cortadas, 'resposta', 'respostas')} acima de 30 s" if h.respostas_cortadas else ""
        return f"nove em cada dez em até {segundos(h.p99)} s (p99){cortadas}"
    if parte == "containers":
        if h.saudaveis is None:
            return "o balanceador não mandou a contagem"
        texto = f"{_decimal(h.saudaveis)} de {_decimal(h.desejados or 1)} no ar"
        if h.cpu is not None:
            texto += f"; CPU até {_decimal(h.cpu)}%"
        if h.memoria is not None:
            texto += f", memória até {_decimal(h.memoria)}%"
        if h.reinicios:
            texto += f"; {contagem(h.reinicios, 'reinício', 'reinícios')}"
        return texto
    if parte == "banco":
        if h.banco_cpu is None:
            return "o banco não mandou ponto"
        texto = f"CPU até {_decimal(h.banco_cpu)}%"
        if h.banco_conexoes is not None:
            texto += f"; {_decimal(h.banco_conexoes)} conexões"
        if h.banco_memoria_livre is not None:
            texto += f"; {_decimal(h.banco_memoria_livre / 1e9, 2)} GB de memória livre"
        return texto
    if parte == "saida":
        return contagem(h.saida_erros, "erro de porta ou pacote perdido", "erros de porta ou pacotes perdidos")
    if parte == "verde":
        return contagem(h.verde_falhas, "consulta com falha", "consultas com falha")
    if parte == "ia":
        return contagem(h.ia_recusas, "chamada recusada ou limitada", "chamadas recusadas ou limitadas") + ", conta inteira"
    if parte == "email":
        return contagem(h.email_erros, "erro da função", "erros da função")
    return ""


def _no_dia(dados: LeiturasDaInfra) -> str:
    return "nas últimas 24 horas" if dados.dia is None else f"em {filtro_de_dia.rotulo(dados.dia)}"


def _escolha(dados: LeiturasDaInfra) -> Filtro:
    quando = dados.dia
    return Filtro(filtro_de_dia.dia_de(quando), quando.astimezone(FUSO).hour if isinstance(quando, datetime) else None)


# ── Saúde agora, nos dois ambientes ───────────────────────────────────────


def _celula_de_agora(parte: str, leitura: Leitura[list[HoraDaInfra]], saude: Leitura[SaudeServico]) -> Any:
    def montar(horas: list[HoraDaInfra]) -> Any:
        # A hora corrente acabou de começar: o estado é o pior entre ela e a anterior.
        ultimas = horas[-2:]
        estado = _pior(*(estado_da_parte(parte, h) for h in ultimas))
        texto = descrever(parte, ultimas[-1]) if parte != "tempo" or ultimas[-1].p99 is not None else descrever(parte, ultimas[0])
        if parte == "containers" and saude.estado is Estado.OK and saude.valor is not None:
            s = saude.valor
            texto = f"{s.hosts_saudaveis} de {s.hosts_desejados} no ar agora; " + texto.split("; ", 1)[-1]
            if s.hosts_saudaveis < 1:
                estado = EstadoDaParte.RUIM
        return ponto(NOME_DO_ESTADO[estado], TOM_DO_ESTADO[estado], texto)

    return celula_de_leitura(leitura, montar, "sem leitura nas últimas 24 horas")


def _saude_agora(dados: LeiturasDaInfra) -> html.Section:
    linhas = [
        html.Tr(
            [
                html.Th(
                    [html.P(nome, className="etapa-nome"), html.P(faz + ("; a mesma nos dois ambientes" if junto else ""), className="etapa-faz")],
                    scope="row",
                    className="com-explicacao",
                ),
                *(html.Td(_celula_de_agora(parte, dados.dos_dois[a], dados.saude[a])) for a in Ambiente),
            ]
        )
        for parte, (nome, faz, junto) in PARTES_DA_INFRA.items()
    ]
    tabela = html.Table(
        [html.Thead(html.Tr([html.Th("Parte"), *(html.Th(NOME_DO_AMBIENTE[a]) for a in Ambiente)])), html.Tbody(linhas)],
        className="tabela tabela-do-caminho",
    )
    explicacao = html.P(
        "O estado da última hora inteira e da hora que está correndo, o pior dos dois. O release é a homologação. "
        "Estável: nada fora do normal. Instável: algo saiu do normal, sem parar o atendimento. Com problema: o atendimento foi afetado.",
        className="quadro-explicacao miolo",
    )
    leituras: list[Leitura[Any]] = [*dados.dos_dois.values(), *dados.saude.values()]
    return quadro("Saúde agora, nos dois ambientes", [explicacao, tabela], leituras, dados.agora, lateral="produção e release (homologação)")


# ── Os 14 dias ────────────────────────────────────────────────────────────


def _pior_da_hora(h: HoraDaInfra) -> EstadoDaParte:
    return _pior(*(estado_da_parte(p, h) for p in PARTES_DA_INFRA))


def _figura_dos_dias(horas: list[HoraDaInfra], escolha: Filtro, tema: str | None, hoje: date) -> go.Figure:
    c = graficos.cores(tema)
    dias = [hoje - timedelta(days=n) for n in range(DIAS_DA_INFRA - 1, -1, -1)]
    ruins, instaveis = Counter[date](), Counter[date]()
    partes_do_dia: dict[date, Counter[str]] = {d: Counter() for d in dias}
    for h in horas:
        dia = h.hora.astimezone(FUSO).date()
        pior = _pior_da_hora(h)
        if pior is EstadoDaParte.RUIM:
            ruins[dia] += 1
        elif pior is EstadoDaParte.ATENCAO:
            instaveis[dia] += 1
        for p in PARTES_DA_INFRA:
            if estado_da_parte(p, h) in (EstadoDaParte.RUIM, EstadoDaParte.ATENCAO) and dia in partes_do_dia:
                partes_do_dia[dia][PARTES_DA_INFRA[p][0]] += 1
    meio_dia = [datetime.combine(d, time(12), tzinfo=FUSO) for d in dias]
    quem = [", ".join(f"{nome} ({n} h)" for nome, n in partes_do_dia[d].most_common(3)) or "nada" for d in dias]
    figura = go.Figure()
    for contados, cor, rotulo in ((ruins, "ruim", "horas com problema"), (instaveis, "atencao", "horas instáveis")):
        figura.add_bar(
            x=meio_dia,
            y=[contados[d] for d in dias],
            name=rotulo,
            marker_color=c[cor],
            customdata=quem,
            hovertemplate=f"%{{x|%d/%m}}: %{{y}} {rotulo}<br>%{{customdata}}<extra></extra>",
        )
    figura.update_layout(**graficos.layout_base(tema), barmode="stack", barcornerradius=2, height=210)
    figura.update_xaxes(showgrid=False, fixedrange=True, tickformat="%d/%m")
    figura.update_yaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero", ticksuffix=" h")
    return filtro_de_dia.destacar(figura, escolha, tema)


def _instabilidades(horas: list[HoraDaInfra]) -> list[tuple[datetime, datetime, Counter[str]]]:
    """Os trechos de horas seguidas com alguma parte com problema, do mais novo ao mais velho."""
    trechos: list[tuple[datetime, datetime, Counter[str]]] = []
    for h in sorted(horas, key=lambda x: x.hora):
        ruins = [p for p in PARTES_DA_INFRA if estado_da_parte(p, h) is EstadoDaParte.RUIM]
        if not ruins:
            continue
        quanto = Counter[str]()
        for p in ruins:
            quanto[p] += _tamanho(p, h)
        if trechos and trechos[-1][1] == h.hora:
            inicio, _, junto = trechos[-1]
            trechos[-1] = (inicio, h.hora + timedelta(hours=1), junto + quanto)
        else:
            trechos.append((h.hora, h.hora + timedelta(hours=1), quanto))
    return list(reversed(trechos))


def _tamanho(parte: str, h: HoraDaInfra) -> int:
    """O número que pesa em cada parte, para o resumo do trecho."""
    return {
        "entrada": h.erros_5xx,
        "tempo": h.respostas_cortadas or 1,
        "containers": 1,
        "banco": 1,
        "saida": h.saida_erros,
        "verde": h.verde_falhas,
        "ia": h.ia_recusas,
        "email": h.email_erros,
    }.get(parte, 1)


UNIDADE_DO_TRECHO = {
    "entrada": ("erro 5xx", "erros 5xx"),
    "tempo": ("resposta acima de 30 s", "respostas acima de 30 s"),
    "containers": ("hora sem container no ar", "horas sem container no ar"),
    "banco": ("hora com CPU alta", "horas com CPU alta"),
    "saida": ("erro de saída", "erros de saída"),
    "verde": ("falha", "falhas"),
    "ia": ("recusa", "recusas"),
    "email": ("erro", "erros"),
}


def _lista_de_instabilidades(horas: list[HoraDaInfra]) -> Any:
    trechos = _instabilidades(horas)
    if not trechos:
        return html.P(f"Nenhuma hora com problema nos últimos {DIAS_DA_INFRA} dias.", className="texto-vazio miolo")
    itens = []
    for inicio, fim, quanto in trechos[:12]:
        local, final = inicio.astimezone(FUSO), fim.astimezone(FUSO)
        quando = f"{dia_da_semana_e_data(local.date())}, das {local.hour}h às {final.hour if final.date() == local.date() else 24}h"
        partes = [f"{PARTES_DA_INFRA[p][0]}, {contagem(n, *UNIDADE_DO_TRECHO[p])}" for p, n in quanto.most_common()]
        itens.append(html.Li([html.Strong(quando + ": "), "; ".join(partes)]))
    resto = len(trechos) - 12
    return html.Div(
        [
            html.Ul(itens, className="lista-simples"),
            html.P(f"E mais {contagem(resto, 'trecho', 'trechos')} antes.", className="tom-suave") if resto > 0 else None,
        ],
        className="miolo",
    )


def _quatorze_dias(dados: LeiturasDaInfra, tema: str | None) -> html.Div:
    leitura, escolha = dados.dias, _escolha(dados)

    def grafico(horas: list[HoraDaInfra]) -> list[Any]:
        return [
            filtro_de_dia.grafico(TELA, "dias", _figura_dos_dias(horas, escolha, tema, dados.agora.date())),
            html.Div(
                [
                    html.Span([html.Span(className="legenda-cor tom-ruim"), "horas com problema"]),
                    html.Span([html.Span(className="legenda-cor tom-atencao"), "horas instáveis"]),
                ],
                className="legenda",
            ),
        ]

    vazio = f"Nenhuma métrica nos últimos {DIAS_DA_INFRA} dias."
    ambiente = NOME_DO_AMBIENTE[dados.ambiente].lower()
    return html.Div(
        [
            quadro(
                f"Instabilidade por dia, {DIAS_DA_INFRA} dias",
                celula_de_leitura(leitura, grafico, vazio),
                [leitura],
                dados.agora,
                lateral=f"{ambiente}; clique num dia",
            ),
            quadro(
                "Quando a infraestrutura teve problema",
                celula_de_leitura(leitura, _lista_de_instabilidades, vazio),
                [leitura],
                dados.agora,
                lateral=f"{ambiente}; horas seguidas, da mais nova",
            ),
        ],
        className="grade-dupla",
    )


# ── Hora a hora ───────────────────────────────────────────────────────────


def _figura_hora_a_hora(horas: list[HoraDaInfra], escolha: Filtro, tema: str | None) -> go.Figure:
    """Uma linha por parte, um quadrado por hora, na cor do estado."""
    c = graficos.cores(tema)
    partes = list(PARTES_DA_INFRA)
    x = [h.hora for h in horas]
    z = [[ORDEM_DO_ESTADO[estado_da_parte(p, h)] for h in horas] for p in partes]
    texto = [[f"{PARTES_DA_INFRA[p][0]}, {h.hora:%Hh}: {NOME_DO_ESTADO[estado_da_parte(p, h)]}<br>{descrever(p, h)}" for h in horas] for p in partes]
    escala = [
        [0.0, c["grade"]],
        [1 / 6, c["grade"]],
        [1 / 6, c["bom"]],
        [0.5, c["bom"]],
        [0.5, c["atencao"]],
        [5 / 6, c["atencao"]],
        [5 / 6, c["ruim"]],
        [1.0, c["ruim"]],
    ]
    figura = go.Figure(
        go.Heatmap(
            x=x,
            y=[PARTES_DA_INFRA[p][0] for p in partes],
            z=z,
            zmin=0,
            zmax=3,
            colorscale=escala,
            showscale=False,
            xgap=2,
            ygap=2,
            text=texto,
            hovertemplate="%{text}<extra></extra>",
        )
    )
    figura.update_layout(**graficos.layout_base(tema), height=40 * len(partes) + 40)
    figura.update_xaxes(showgrid=False, fixedrange=True, tickformat="%Hh")
    figura.update_yaxes(fixedrange=True, autorange="reversed", automargin=True)
    escolhida = escolha.quando if isinstance(escolha.quando, datetime) else None
    if escolhida is not None:
        figura.add_vrect(
            x0=escolhida - timedelta(minutes=30), x1=escolhida + timedelta(minutes=30), line={"color": c["texto"], "width": 1}, fillcolor="rgba(0,0,0,0)"
        )
    return figura


def _picos(horas: list[HoraDaInfra]) -> html.Ul:
    """A pior hora de cada parte na janela, com os números dela."""
    medida: dict[str, Any] = {
        "entrada": lambda h: h.erros_5xx,
        "tempo": lambda h: h.p99 or 0,
        "containers": lambda h: (-(h.saudaveis or 0), h.cpu or 0),
        "banco": lambda h: h.banco_cpu or 0,
        "saida": lambda h: h.saida_erros,
        "verde": lambda h: h.verde_falhas,
        "ia": lambda h: h.ia_recusas,
        "email": lambda h: h.email_erros,
    }
    itens = []
    for parte, (nome, _, _) in PARTES_DA_INFRA.items():
        pior = max(horas, key=lambda h: (ORDEM_DO_ESTADO[estado_da_parte(parte, h)], medida[parte](h)))
        estado = estado_da_parte(parte, pior)
        if estado in (EstadoDaParte.BOM, EstadoDaParte.SEM_USO):
            texto = "sem pico: estável a janela toda" if estado is EstadoDaParte.BOM else "sem uso na janela"
            itens.append(
                html.Li([html.Span(className="ponto tom-bom" if estado is EstadoDaParte.BOM else "ponto tom-neutro"), html.Strong(nome + ": "), texto])
            )
            continue
        local = pior.hora.astimezone(FUSO)
        itens.append(
            html.Li(
                [
                    html.Span(className=f"ponto tom-{TOM_DO_ESTADO[estado]}"),
                    html.Strong(nome + ": "),
                    f"pico às {local.hour}h de {local:%d/%m}, {descrever(parte, pior)}",
                ]
            )
        )
    return html.Ul(itens, className="lista-de-picos")


def _hora_a_hora(dados: LeiturasDaInfra, tema: str | None) -> html.Section:
    leitura, escolha = dados.horas, _escolha(dados)

    def corpo(horas: list[HoraDaInfra]) -> list[Any]:
        return [
            filtro_de_dia.grafico(TELA, "hora-a-hora", _figura_hora_a_hora(horas, escolha, tema), por="hora"),
            html.Div(
                [
                    html.Span([html.Span(className=f"legenda-cor tom-{TOM_DO_ESTADO[e]}"), NOME_DO_ESTADO[e]])
                    for e in (EstadoDaParte.BOM, EstadoDaParte.ATENCAO, EstadoDaParte.RUIM)
                ]
                + [html.Span([html.Span(className="legenda-cor tom-outro"), "sem uso"])],
                className="legenda",
            ),
            html.Div([html.P("Os picos", className="rotulo-pequeno"), _picos(horas)], className="miolo"),
        ]

    vazio = f"Nenhuma métrica {_no_dia(dados)}."
    return quadro(
        "Hora a hora, cada parte",
        celula_de_leitura(leitura, corpo, vazio),
        [leitura],
        dados.agora,
        lateral=f"{NOME_DO_AMBIENTE[dados.ambiente].lower()}, {_no_dia(dados)}; passe o mouse para os números; clique numa hora",
    )


# ── Os gráficos de cada parte ─────────────────────────────────────────────


def _base(figura: go.Figure, tema: str | None, sufixo: str = "", altura: int = 200) -> go.Figure:
    c = graficos.cores(tema)
    figura.update_layout(**graficos.layout_base(tema), height=altura, separators=",.")
    figura.update_xaxes(showgrid=False, fixedrange=True, tickformat="%Hh")
    figura.update_yaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero", ticksuffix=sufixo)
    return figura


def _horas(horas: list[HoraDaInfra]) -> tuple[list[datetime], list[str]]:
    return [h.hora for h in horas], [h.hora.isoformat() for h in horas]


def _barras(horas: list[HoraDaInfra], series: list[tuple[str, str, str]], escolha: Filtro, tema: str | None) -> go.Figure:
    """Barras empilhadas por hora: (campo, cor, rótulo)."""
    c = graficos.cores(tema)
    x, chaves = _horas(horas)
    figura = go.Figure()
    for campo, cor, rotulo in series:
        figura.add_bar(
            x=x,
            y=[getattr(h, campo) for h in horas],
            name=rotulo,
            marker_color=c[cor],
            customdata=chaves,
            hovertemplate=f"%{{x|%Hh}}: %{{y}} {rotulo}<extra></extra>",
        )
    figura.update_layout(barmode="stack", barcornerradius=2)
    return filtro_de_dia.destacar_hora(_base(figura, tema), escolha)


def _linhas(horas: list[HoraDaInfra], series: list[tuple[str, str, str]], tema: str | None, sufixo: str, limite: float | None = None) -> go.Figure:
    c = graficos.cores(tema)
    x, chaves = _horas(horas)
    figura = go.Figure()
    for campo, cor, rotulo in series:
        figura.add_scatter(
            x=x,
            y=[getattr(h, campo) for h in horas],
            mode="lines+markers",
            line={"color": c[cor]},
            marker={"size": 7},
            name=rotulo,
            customdata=chaves,
            hovertemplate=f"%{{x|%Hh}}, {rotulo}: %{{y:.1f}}{sufixo}<extra></extra>",
        )
    _base(figura, tema, sufixo)
    if limite is not None and max((getattr(h, s[0]) or 0 for h in horas for s in series), default=0) >= limite / 2:
        figura.add_hline(y=limite, line={"color": c["ruim"], "dash": "dash", "width": 1})
    return figura


def _legenda(series: list[tuple[str, str, str]], extra: str | None = None) -> html.Div:
    itens = [html.Span([html.Span(className=f"legenda-cor tom-{cor}"), rotulo]) for _, cor, rotulo in series]
    if extra:
        itens.append(html.Span([html.Span(className="legenda-cor tom-ruim"), extra]))
    return html.Div(itens, className="legenda")


def _graficos_das_partes(dados: LeiturasDaInfra, tema: str | None) -> list[html.Div]:
    leitura, escolha, janela = dados.horas, _escolha(dados), _no_dia(dados)

    def um(titulo: str, lateral: str, nome: str, figura: Any, legenda: html.Div, explicacao: str) -> html.Section:
        def corpo(horas: list[HoraDaInfra]) -> list[Any]:
            return [filtro_de_dia.grafico(TELA, nome, figura(horas), por="hora"), legenda, html.P(explicacao, className="quadro-explicacao miolo")]

        return quadro(titulo, celula_de_leitura(leitura, corpo, f"Nenhuma métrica {janela}."), [leitura], dados.agora, lateral=lateral)

    entrada = [("erros_5xx", "ruim", "erros 5xx"), ("erros_4xx", "atencao", "erros 4xx")]
    tempo = [("p99", "azul", "p99")]
    containers = [("cpu", "azul", "CPU"), ("memoria", "rosa", "memória")]
    banco = [("banco_cpu", "azul", "CPU do banco")]
    de_fora = [
        ("verde_falhas", "ruim", "Verde"),
        ("ia_recusas", "rosa", "modelo de IA"),
        ("email_erros", "atencao", "email"),
        ("saida_erros", "azul", "saída (NAT)"),
    ]
    return [
        html.Div(
            [
                um(
                    "Erros na entrada (CloudFront)",
                    f"{janela}; clique numa hora",
                    "entrada",
                    lambda horas: _barras(horas, entrada, escolha, tema),
                    _legenda(entrada),
                    "O CloudFront responde 5xx quando a Maria não responde em 30 s ou está fora do ar: a Tykhe recebe o erro e encaminha a pessoa ao atendimento humano.",
                ),
                um(
                    "Tempo de resposta (p99)",
                    f"{janela}; corte em {LIMITE_DO_CORTE_S:.0f} s",
                    "tempo",
                    lambda horas: _linhas(horas, tempo, tema, " s", LIMITE_DO_CORTE_S),
                    _legenda(tempo, "corte do CloudFront"),
                    "Nove em cada dez respostas saem até esse tempo. Acima de 30 s, quem chamou não recebe a resposta (#344).",
                ),
            ],
            className="grade-dupla",
        ),
        html.Div(
            [
                um(
                    "Containers (ECS)",
                    f"{janela}; máximo de cada hora",
                    "containers",
                    lambda horas: _linhas(horas, containers, tema, "%", 80.0),
                    _legenda(containers),
                    "CPU e memória usadas pelo serviço, como parte do que ele reserva. Os reinícios e o container fora do ar aparecem no hora a hora.",
                ),
                um(
                    "Banco das conversas (RDS)",
                    "o mesmo nos dois ambientes",
                    "banco",
                    lambda horas: _linhas(horas, banco, tema, "%", 80.0),
                    _legenda(banco),
                    "O banco guarda onde cada conversa parou, e é um só para produção e release. As conexões e a memória livre estão no hora a hora.",
                ),
            ],
            className="grade-dupla",
        ),
        html.Div(
            um(
                "Serviços de fora e a saída para a internet",
                f"{janela}; falhas por hora",
                "de-fora",
                lambda horas: _barras(horas, de_fora, escolha, tema),
                _legenda(de_fora),
                "O Verde é consultado neste ambiente; o modelo de IA, o email e a saída (NAT) são os mesmos nos dois. "
                "O Verde fora do ar não é a infraestrutura da Maria, mas para o atendimento do mesmo jeito.",
            ),
        ),
    ]


# ── Montagem ──────────────────────────────────────────────────────────────


def blocos(ambiente: Ambiente, dia: date | None = None, tema: str | None = None) -> list[Any]:
    dados = ler_infra(ambiente, dia)
    return [
        _saude_agora(dados),
        _quatorze_dias(dados, tema),
        _hora_a_hora(dados, tema),
        *_graficos_das_partes(dados, tema),
        lista_de_fontes(dados.todas(), dados.agora),
    ]


def _tela(dia: date | None) -> html.Div:
    return html.Div(
        [
            cabecalho(
                "Infra",
                "A infraestrutura está estável?",
                [html.Span("Ambiente", className="rotulo-filtro"), filtro_de_ambiente("infra-ambiente")],
            ),
            filtro_de_dia.armazem(TELA, dia),
            filtro_de_dia.faixa(TELA, dia),
            html.Div(blocos(Ambiente.PRODUCAO, dia), id="infra-corpo", className="tela-corpo"),
        ],
        # Como a Agora, a largura toda: o hora a hora de cada parte pede espaço.
        className="tela tela-larga",
    )


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador aos gráficos.
@callback(
    Output("infra-corpo", "children"),
    Input("relogio", "n_intervals"),
    Input("infra-ambiente", "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada(TELA),
)
def atualizar(_: int | None, ambiente: str | None, tema: str | None, dia: str | None) -> list[Any]:
    return blocos(Ambiente(ambiente or Ambiente.PRODUCAO.value), filtro_de_dia.escolhido(dia), tema)


def layout(dia: str | None = None, **_: str) -> html.Div:
    return _tela(filtro_de_dia.ler(dia, datetime.now(FUSO)))
