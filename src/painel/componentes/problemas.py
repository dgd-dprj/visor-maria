"""O quadro "Problemas e defeitos" da tela Atendimento: uma linha por ocorrência.

Pedido de 10/11: entender os bugs, com tudo detalhado e filtrável. A regra 4 passou
de "nunca listar conversa" para "nunca identificar a conversa" (decisão da Nicole):
cada linha tem a hora, o tipo, a etapa, o código, a demora e o que aconteceu com a
conversa depois, sem `chatId` e sem texto. Para ver a linha inteira do log, cada
ocorrência traz a consulta pronta para o Logs Insights, com o grupo e a janela.

Os filtros (tipo, fluxo, código e o que aconteceu depois) ficam fora da área que o
relógio refaz, para a escolha não se perder a cada minuto. O clique num gráfico
filtra como no resto do painel: um dia, uma hora ou um tipo.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, cast

import plotly.graph_objects as go
from dash import dcc, html

from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import nota_de_fonte, texto_de_falha
from painel.componentes.filtro_de_dia import OCORRENCIA, Filtro
from painel.componentes.formato import contagem, ha_quanto, numero, segundos
from painel.dados.fontes import GRUPO_DE_LOGS
from painel.dados.modelo import (
    FUSO,
    NOME_DO_DEPOIS,
    NOME_DO_FLUXO,
    TIPOS_DE_OCORRENCIA,
    Ambiente,
    Estado,
    Fonte,
    Leitura,
    Ocorrencia,
    OcorrenciasDoPeriodo,
    nome_da_ocorrencia,
    nome_do_desfecho,
    nome_do_fluxo,
)

TELA = "atendimento"
# Os ids dos filtros do quadro.
FILTRO_DO_TIPO = "problemas-tipo"
FILTRO_DO_FLUXO = "problemas-fluxo"
FILTRO_DO_CODIGO = "problemas-codigo"
FILTRO_DO_DEPOIS = "problemas-depois"
CONTEUDO = "problemas-conteudo"
# Acima disso, a lista mostra as mais novas e diz quantas ficaram de fora.
# 100 linhas: com 300, o quadro mandava cerca de 300 KB ao navegador a cada volta.
LINHAS_NA_LISTA = 100
# O quadro se refaz na validade da leitura (5 minutos, dados/consultas.py), e não a cada minuto.
RELOGIO = "problemas-relogio"
VOLTA_DO_RELOGIO_MS = 5 * 60 * 1000
# As cores dos tipos, pela ordem de quantas vezes cada um apareceu.
PALETA = ("ruim", "atencao", "rosa", "azul", "outro", "bom")
SEM_FLUXO = "sem_fluxo"
# A janela da consulta sugerida, em volta da ocorrência.
FOLGA_DA_CONSULTA = timedelta(minutes=2)


@dataclass(frozen=True)
class Escolhas:
    """O que foi escolhido nos filtros do quadro (None: todos)."""

    tipo: str | None = None
    fluxo: str | None = None
    codigo: str | None = None
    depois: str | None = None


def _opcoes(pares: Sequence[tuple[str, str]]) -> Any:
    # O tipo do Dash não aceita lista de dicionários, que ele aceita na prática.
    return cast(Any, [{"label": rotulo, "value": valor} for valor, rotulo in pares])


def _lista(id_: str, rotulo: str, opcoes: Sequence[tuple[str, str]]) -> html.Label:
    return html.Label(
        [
            html.Span(rotulo, className="rotulo-pequeno"),
            dcc.Dropdown(id=id_, options=_opcoes(opcoes), value=None, clearable=True, searchable=True, placeholder="Todos", className="filtro-data"),
        ],
        className="filtro-do-quadro",
    )


def filtros() -> html.Div:
    """A linha de filtros, montada uma vez com a tela."""
    tipos = [(t, nome) for t, (nome, _, _) in TIPOS_DE_OCORRENCIA.items()]
    fluxos = [*NOME_DO_FLUXO.items(), (SEM_FLUXO, "Sem fluxo")]
    depois = list(NOME_DO_DEPOIS.items())
    return html.Div(
        [
            _lista(FILTRO_DO_TIPO, "Tipo", tipos),
            _lista(FILTRO_DO_FLUXO, "Fluxo", fluxos),
            _lista(FILTRO_DO_CODIGO, "Código", []),
            _lista(FILTRO_DO_DEPOIS, "Depois", depois),
        ],
        className="filtros-do-quadro miolo",
    )


def opcoes_de_codigo(leitura: Leitura[OcorrenciasDoPeriodo]) -> Any:
    """Os códigos que apareceram na janela, do mais comum ao mais raro."""
    contados = Counter(o.codigo for o in (leitura.valor.ocorrencias if leitura.valor else []))
    return _opcoes([(c, f"{c} ({numero(n)})") for c, n in contados.most_common()])


def filtrar(ocorrencias: Sequence[Ocorrencia], escolhas: Escolhas, escolha: Filtro) -> list[Ocorrencia]:
    tipo = escolha.ocorrencia or escolhas.tipo
    return [
        o
        for o in ocorrencias
        if (tipo is None or o.tipo == tipo)
        and (escolhas.fluxo is None or (o.fluxo or SEM_FLUXO) == escolhas.fluxo)
        and (escolhas.codigo is None or o.codigo == escolhas.codigo)
        and (escolhas.depois is None or o.depois == escolhas.depois)
    ]


# ── Números ───────────────────────────────────────────────────────────────


def hora_de_pico(ocorrencias: Sequence[Ocorrencia]) -> tuple[int, int] | None:
    """A hora do dia com mais ocorrências na janela, e quantas."""
    por_hora = Counter(o.hora.astimezone(FUSO).hour for o in ocorrencias)
    return max(por_hora.items(), key=lambda par: (par[1], -par[0])) if por_hora else None


def _numeros(lista: Sequence[Ocorrencia], todas: OcorrenciasDoPeriodo) -> html.Div:
    pico = hora_de_pico(lista)
    tipos = Counter(o.tipo for o in lista)
    mais_comum = tipos.most_common(1)[0] if tipos else None
    colunas = (
        (
            "Ocorrências",
            numero(len(lista)),
            f"de {numero(len(todas.ocorrencias))} na janela" if len(lista) != len(todas.ocorrencias) else "na janela",
            "neutro",
        ),
        ("Conversas com problema", numero(todas.conversas), "pelo menos uma ocorrência", "neutro"),
        ("Hora de pico", f"{pico[0]}h" if pico else "nenhuma", contagem(pico[1], "ocorrência", "ocorrências") if pico else "", "atencao" if pico else "neutro"),
        ("Mais comum", nome_da_ocorrencia(mais_comum[0]) if mais_comum else "nenhum", contagem(mais_comum[1], "vez", "vezes") if mais_comum else "", "neutro"),
    )
    return html.Div(
        [
            html.Div(
                [
                    html.P(rotulo, className="coluna-rotulo"),
                    html.P(valor, className=f"numero-medio tom-{tom}"),
                    html.P(legenda, className="indicador-legenda"),
                ]
            )
            for rotulo, valor, legenda, tom in colunas
        ],
        className="numeros-dos-problemas miolo",
    )


# ── Os graves, um a um ────────────────────────────────────────────────────
# Pedido de 10/11: os quatro tipos graves separados, cada um com o que dá para
# entender dele, em vez de um número só.

GRAVES = ("erro_da_maria", "resposta_cortada", "fluxo", "email")
BOTAO_DO_GRAVE = "problemas-ver-grave"
NOME_DO_DEPOIS_CURTO = {
    "encerrou": ("encerrou", "encerraram"),
    "seguiu": ("seguiu", "seguiram"),
    "expirou": ("expirou", "expiraram"),
    "parou": ("parou", "pararam"),
    "recente": ("ainda recente", "ainda recentes"),
    "ja_encerrada": ("já estava encerrada", "já estavam encerradas"),
    "sem_conversa": ("sem conversa ligada", "sem conversa ligada"),
}


def _mais_comuns(valores: Sequence[str], quantos: int = 2) -> str:
    return "; ".join(f"{v} ({numero(n)})" for v, n in Counter(valores).most_common(quantos))


def _depois_contado(lista: Sequence[Ocorrencia]) -> str:
    contados = Counter(o.depois for o in lista).most_common()
    return ", ".join(f"{numero(n)} {NOME_DO_DEPOIS_CURTO.get(d, (d, d))[0 if n == 1 else 1]}" for d, n in contados)


def _motivos_do_fim(lista: Sequence[Ocorrencia]) -> str:
    return _mais_comuns([nome_do_desfecho(o.motivo) for o in lista if o.depois == "encerrou" and o.motivo])


def _cartao_do_grave(tipo: str, lista: Sequence[Ocorrencia], agora: datetime) -> html.Section:
    nome, _, explicacao = TIPOS_DE_OCORRENCIA[tipo]
    deste = [o for o in lista if o.tipo == tipo]
    topo = html.Div(
        [
            html.P([html.Span(className=f"ponto tom-{'ruim' if deste else 'bom'}"), nome], className="cartao-grave-nome"),
            html.P(numero(len(deste)) if deste else "nenhum", className=f"numero-medio tom-{'ruim' if deste else 'bom'}"),
        ],
        className="cartao-grave-topo",
    )
    corpo: list[Any] = [topo, html.P(explicacao, className="cartao-grave-explicacao")]
    if deste:
        ultima = max(deste, key=lambda o: o.hora).hora.astimezone(FUSO)
        pico = hora_de_pico(deste)
        demoras = [o.demora for o in deste if o.demora is not None]
        linhas: list[tuple[str, str]] = [
            ("Última", f"{ultima:%d/%m} às {ultima:%H:%M}, {ha_quanto(ultima, agora)}"),
            ("Onde", _mais_comuns([o.etapa for o in deste])),
            ("Código", _mais_comuns([o.codigo for o in deste])),
            ("Fluxo", _mais_comuns([nome_do_fluxo(o.fluxo) for o in deste])),
        ]
        if demoras:
            linhas.append(("Demora", f"média de {segundos(sum(demoras) / len(demoras))} s; a maior, {segundos(max(demoras))} s"))
        if pico is not None:
            linhas.append(("Pico", f"{pico[0]}h, {contagem(pico[1], 'vez', 'vezes')}"))
        linhas.append(("Depois", _depois_contado(deste)))
        motivos = _motivos_do_fim(deste)
        if motivos:
            linhas.append(("Encerrou por", motivos))
        corpo += [
            html.Dl([peca for rotulo, valor in linhas for peca in (html.Dt(rotulo), html.Dd(valor))], className="definicoes cartao-grave-dados"),
            html.Button("Ver na lista", id={"tipo": BOTAO_DO_GRAVE, "grave": tipo}, n_clicks=0, className="botao-pequeno"),
        ]
    return html.Section(corpo, className=f"cartao-grave {'cartao-grave-com' if deste else 'cartao-grave-sem'}")


def _graves(lista: Sequence[Ocorrencia], agora: datetime) -> html.Div:
    return html.Div(
        [
            html.P("Os graves, um a um", className="rotulo-pequeno"),
            html.Div([_cartao_do_grave(t, lista, agora) for t in GRAVES], className="cartoes-graves"),
        ],
        className="miolo",
    )


# ── Gráficos ──────────────────────────────────────────────────────────────


def _cores_dos_tipos(lista: Sequence[Ocorrencia]) -> dict[str, str]:
    ordem = [t for t, _ in Counter(o.tipo for o in lista).most_common()]
    return {t: PALETA[n % len(PALETA)] for n, t in enumerate(ordem)}


def _quando(lista: Sequence[Ocorrencia], todas: OcorrenciasDoPeriodo, escolha: Filtro, tema: str | None) -> dcc.Graph:
    """Por dia na janela, ou hora a hora com um dia escolhido: barras empilhadas por tipo."""
    c, cores = graficos.cores(tema), _cores_dos_tipos(lista)
    por_hora = escolha.dia is not None
    if por_hora:
        assert escolha.dia is not None
        inicio = datetime.combine(escolha.dia, time(), tzinfo=FUSO)
        pontos = [inicio + timedelta(hours=n) for n in range(24)]

        def chave(o: Ocorrencia) -> Any:
            return o.hora.astimezone(FUSO).replace(minute=0, second=0, microsecond=0)
    else:
        primeiro, ultimo = todas.inicio.astimezone(FUSO).date(), todas.fim.astimezone(FUSO).date()
        pontos = [datetime.combine(primeiro + timedelta(days=n), time(12), tzinfo=FUSO) for n in range((ultimo - primeiro).days + 1)]

        def chave(o: Ocorrencia) -> Any:
            return datetime.combine(o.hora.astimezone(FUSO).date(), time(12), tzinfo=FUSO)

    figura = go.Figure()
    tipos = list(cores)
    for tipo in tipos:
        contados = Counter(chave(o) for o in lista if o.tipo == tipo)
        figura.add_bar(
            x=pontos,
            y=[contados.get(p, 0) for p in pontos],
            name=nome_da_ocorrencia(tipo),
            marker_color=c[cores[tipo]],
            customdata=[p.isoformat() for p in pontos] if por_hora else None,
            hovertemplate=("%{x|%Hh}" if por_hora else "%{x|%d/%m}") + f": %{{y}}, {nome_da_ocorrencia(tipo)}<extra></extra>",
        )
    figura.update_layout(**graficos.layout_base(tema), barmode="stack", barcornerradius=2, height=210)
    figura.update_xaxes(showgrid=False, fixedrange=True, tickformat="%Hh" if por_hora else "%d/%m")
    figura.update_yaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero")
    if por_hora:
        return filtro_de_dia.grafico(TELA, "problemas-por-hora", filtro_de_dia.destacar_hora(figura, escolha), por="hora")
    series = tuple(f"{OCORRENCIA}{t}" for t in tipos)
    return filtro_de_dia.grafico(TELA, "problemas-por-dia", filtro_de_dia.destacar(figura, escolha, tema, series), series=series)


def _hora_do_dia(lista: Sequence[Ocorrencia], tema: str | None) -> dcc.Graph:
    """As 24 horas do dia, somadas na janela: em que hora os problemas se juntam."""
    c, cores = graficos.cores(tema), _cores_dos_tipos(lista)
    figura = go.Figure()
    horas = list(range(24))
    for tipo in cores:
        contados = Counter(o.hora.astimezone(FUSO).hour for o in lista if o.tipo == tipo)
        figura.add_bar(
            x=horas,
            y=[contados.get(h, 0) for h in horas],
            name=nome_da_ocorrencia(tipo),
            marker_color=c[cores[tipo]],
            hovertemplate=f"%{{x}}h: %{{y}}, {nome_da_ocorrencia(tipo)}<extra></extra>",
        )
    pico = hora_de_pico(lista)
    if pico is not None:
        figura.add_annotation(x=pico[0], y=1, yref="paper", text="pico", showarrow=False, yanchor="bottom", font={"size": 11, "color": c["ruim"]})
    figura.update_layout(**graficos.layout_base(tema), barmode="stack", barcornerradius=2, height=210)
    # Eixo de números, com o rótulo a cada 3 horas: em texto, o Plotly lia "10h" como data.
    figura.update_xaxes(showgrid=False, fixedrange=True, range=[-0.6, 23.6], tickvals=list(range(0, 24, 3)), ticktext=[f"{h}h" for h in range(0, 24, 3)])
    figura.update_yaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero")
    return dcc.Graph(figure=figura, config={"displayModeBar": False}, className="grafico")


def _por_tipo(lista: Sequence[Ocorrencia], escolha: Filtro, tema: str | None) -> dcc.Graph:
    """Uma barra por tipo; o clique filtra a lista por ele."""
    c, cores = graficos.cores(tema), _cores_dos_tipos(lista)
    contados = Counter(o.tipo for o in lista).most_common()
    tipos = [t for t, _ in reversed(contados)]
    figura = go.Figure(
        go.Bar(
            y=[nome_da_ocorrencia(t) for t in tipos],
            x=[n for _, n in reversed(contados)],
            orientation="h",
            marker_color=[c[cores[t]] for t in tipos],
            marker_opacity=[1.0 if escolha.ocorrencia in (None, t) else filtro_de_dia.APAGADO for t in tipos],
            customdata=[[f"{OCORRENCIA}{t}"] for t in tipos],
            hovertemplate="%{y}: %{x}<extra></extra>",
        )
    )
    figura.update_layout(**graficos.layout_base(tema), height=max(140, 34 * len(tipos) + 40))
    figura.update_xaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero")
    figura.update_yaxes(fixedrange=True, automargin=True)
    return filtro_de_dia.grafico(TELA, "problemas-por-tipo", figura, por="categoria")


def _legenda(lista: Sequence[Ocorrencia]) -> html.Div:
    return html.Div(
        [html.Span([html.Span(className=f"legenda-cor tom-{tom}"), nome_da_ocorrencia(t)]) for t, tom in _cores_dos_tipos(lista).items()],
        className="legenda legenda-em-linhas",
    )


# ── A lista ───────────────────────────────────────────────────────────────


def consulta_do_log(o: Ocorrencia, ambiente: Ambiente) -> str:
    """A consulta para ver as linhas inteiras no Logs Insights."""
    if o.pedido:
        return f'fields @timestamp, level, msg, res.statusCode, responseTime, err.type | filter reqId = "{o.pedido}" | sort @timestamp'
    if o.tipo == "verde":
        return 'fields @timestamp, level, msg, chamada, status, tipoErro, duracaoMs, tentativa, err.type | filter evento = "verde_chamada" and resultado != "sucesso"'
    return "fields @timestamp, level, msg, evento, err.type | filter level >= 40 | sort @timestamp"


def _detalhe_do_log(o: Ocorrencia, ambiente: Ambiente) -> html.Details:
    local = o.hora.astimezone(FUSO)
    de, ate = local - FOLGA_DA_CONSULTA, local + FOLGA_DA_CONSULTA + timedelta(seconds=o.demora or 0)
    return html.Details(
        [
            html.Summary("consulta"),
            html.P(f"No Logs Insights, de {de:%d/%m %H:%M} a {ate:%H:%M} (Brasília), no grupo:", className="tom-suave"),
            html.Code(GRUPO_DE_LOGS[ambiente], className="codigo-de-log"),
            html.Code(consulta_do_log(o, ambiente), className="codigo-de-log"),
        ],
        className="detalhe-do-log",
    )


def _depois(o: Ocorrencia) -> list[Any]:
    """O que aconteceu e, embaixo, o motivo do encerramento."""
    texto = NOME_DO_DEPOIS.get(o.depois, o.depois)
    if o.motivo and o.depois in ("encerrou", "ja_encerrada"):
        return [texto, html.Br(), html.Span(nome_do_desfecho(o.motivo), className="tom-suave")]
    return [texto]


def _linha(o: Ocorrencia, ambiente: Ambiente) -> html.Tr:
    nome, tom, _ = TIPOS_DE_OCORRENCIA.get(o.tipo, (o.tipo, "outro", ""))
    local = o.hora.astimezone(FUSO)
    return html.Tr(
        [
            html.Td([html.Span(f"{local:%d/%m}", className="tom-suave"), html.Br(), f"{local:%H:%M:%S}"], className="mono"),
            html.Td([html.Span(className=f"ponto tom-{tom}"), nome], className="coluna-tipo"),
            # Onde: a etapa e, embaixo, o fluxo; o código e, embaixo, a tentativa.
            html.Td([html.Span(o.etapa, className="mono"), html.Br(), html.Span(nome_do_fluxo(o.fluxo), className="tom-suave")]),
            html.Td(
                [html.Span(o.codigo, className="mono"), *([html.Br(), html.Span(f"tentativa {o.tentativa}", className="tom-suave")] if o.tentativa else [])]
            ),
            html.Td(f"{segundos(o.demora)} s" if o.demora is not None else "", className="numero"),
            html.Td(_depois(o)),
            html.Td(_detalhe_do_log(o, ambiente)),
        ]
    )


def _tabela(lista: Sequence[Ocorrencia], ambiente: Ambiente) -> list[Any]:
    cabeca = ("Hora", "Tipo", "Onde", "Código", "Demora", "Depois", "Log")
    partes: list[Any] = [
        html.Div(
            html.Table(
                [
                    html.Thead(html.Tr([html.Th(t, className="numero" if t == "Demora" else None) for t in cabeca])),
                    html.Tbody([_linha(o, ambiente) for o in lista[:LINHAS_NA_LISTA]]),
                ],
                className="tabela tabela-compacta tabela-de-ocorrencias",
            ),
            className="rolagem-da-tabela",
        )
    ]
    if len(lista) > LINHAS_NA_LISTA:
        partes.append(
            html.P(
                f"Mostrando as {numero(LINHAS_NA_LISTA)} mais novas de {numero(len(lista))}. Escolha um dia, um tipo ou um código para ver as outras.",
                className="quadro-explicacao miolo",
            )
        )
    return partes


def _tipos_explicados(lista: Sequence[Ocorrencia]) -> html.Details:
    presentes = {o.tipo for o in lista}
    return html.Details(
        [
            html.Summary("O que é cada tipo"),
            html.Ul(
                [html.Li([html.Strong(nome + ". "), texto]) for t, (nome, _, texto) in TIPOS_DE_OCORRENCIA.items() if t in presentes or not presentes],
                className="lista-simples",
            ),
        ],
        className="tipos-explicados miolo",
    )


# ── Montagem ──────────────────────────────────────────────────────────────


def _janela(todas: OcorrenciasDoPeriodo, quando: date | None) -> str:
    if quando is not None:
        return f"em {filtro_de_dia.rotulo(quando)}"
    inicio, fim = todas.inicio.astimezone(FUSO), todas.fim.astimezone(FUSO)
    return f"de {inicio:%d/%m %H:%M} a {fim:%d/%m %H:%M}"


def conteudo(leitura: Leitura[OcorrenciasDoPeriodo], ambiente: Ambiente, escolha: Filtro, escolhas: Escolhas, tema: str | None, agora: datetime) -> list[Any]:
    """O miolo do quadro, com a fonte e a hora no pé."""
    pe = html.Footer(nota_de_fonte([leitura], agora), className="quadro-pe")
    if leitura.estado is Estado.INDISPONIVEL:
        return [html.Div(texto_de_falha(leitura), className="miolo"), pe]
    if leitura.valor is None or not leitura.valor.ocorrencias:
        quando = f"em {filtro_de_dia.rotulo(escolha.quando)}" if escolha.quando is not None else "no trecho desta origem"
        return [html.P(f"Nenhum problema registrado {quando}: nem erro da Maria, nem resposta cortada, nem falha do Verde.", className="texto-vazio miolo"), pe]
    todas = leitura.valor
    lista = filtrar(todas.ocorrencias, escolhas, escolha)
    partes: list[Any] = [html.P(f"Janela: {_janela(todas, escolha.quando)}.", className="quadro-explicacao miolo")]
    if todas.cortada:
        partes.append(html.P("A consulta bateu o limite de linhas: escolha um dia para ver todas as ocorrências dele.", className="faixa-de-aviso"))
    if not lista:
        partes += [html.P("Nenhuma ocorrência com esses filtros.", className="texto-vazio miolo"), pe]
        return partes
    partes += [
        _numeros(lista, todas),
        # Os graves não seguem o filtro de tipo: os quatro aparecem sempre, cada um com o seu número.
        _graves(filtrar(todas.ocorrencias, Escolhas(None, escolhas.fluxo, escolhas.codigo, escolhas.depois), Filtro()), agora),
        html.Div(
            [
                html.Div([html.P("Quando aconteceram", className="rotulo-pequeno"), _quando(lista, todas, escolha, tema)]),
                html.Div([html.P("Em que hora do dia: o pico", className="rotulo-pequeno"), _hora_do_dia(lista, tema)]),
            ],
            # Um embaixo do outro: lado a lado, no espaço da tela com a coluna da direita, os eixos se atropelavam.
            className="miolo graficos-empilhados",
        ),
        _legenda(lista),
        html.Div([html.P("Por tipo (clique para filtrar)", className="rotulo-pequeno"), _por_tipo(lista, escolha, tema)], className="miolo"),
        _tipos_explicados(lista),
        *_tabela(lista, ambiente),
        pe,
    ]
    return partes


def lendo(fonte: Fonte, agora: datetime) -> list[Any]:
    """Enquanto a primeira leitura não chega: a tela abre sem esperar por ela."""
    return [
        html.P("Lendo os problemas nos logs. Eles aparecem aqui em alguns segundos.", className="texto-vazio miolo"),
        html.Footer(html.P(f"{fonte.curto}, lendo desde as {agora.astimezone(FUSO):%H:%M}", className="fonte-curta"), className="quadro-pe"),
    ]


def quadro(leitura: Leitura[OcorrenciasDoPeriodo] | None, fonte: Fonte, ambiente: Ambiente, escolha: Filtro, tema: str | None, agora: datetime) -> html.Section:
    """O quadro inteiro, com os filtros fixos e o miolo que se refaz. Sem a leitura
    pronta, o miolo diz que está lendo, e o callback o preenche quando ela chega."""
    miolo = conteudo(leitura, ambiente, escolha, Escolhas(), tema, agora) if leitura is not None else lendo(fonte, agora)
    return html.Section(
        [
            html.Header(
                [html.H2("Problemas e defeitos"), html.Div("uma linha por ocorrência; sem dado de quem conversa", className="quadro-lateral")],
                className="quadro-topo",
            ),
            filtros(),
            dcc.Interval(id=RELOGIO, interval=VOLTA_DO_RELOGIO_MS),
            html.Div(miolo, id=CONTEUDO),
        ],
        className="quadro quadro-de-problemas",
    )
