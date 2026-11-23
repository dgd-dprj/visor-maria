"""Tela Credencial do Verde: está valendo, e por quanto tempo?

Segue o rascunho: um cartão por ambiente (validade, barra do prazo, última
consulta aceita, última conferência e próxima renovação), os incidentes de
recusa, com a causa e os atendimentos afetados, a linha do tempo, com o
vencimento de cada evento, os gráficos das consultas e da hora da conferência,
na largura inteira, e três orientações.

A próxima renovação sai das regras do verificar-token-verde.yml
(`painel/renovacao.py`), e a linha do tempo, dos dados (`painel/linha_do_tempo.py`).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import partial
from typing import Any, cast

import dash
from dash import Input, Output, callback, dcc, html

from painel import lateral, linha_do_tempo
from painel.componentes import filtro_de_dia
from painel.componentes.blocos import (
    Tom,
    aria,
    barra,
    definicoes,
    dica,
    lista_de_fontes,
    ponto,
    quadro,
    selo,
    texto_de_falha,
)
from painel.componentes.cabecalho import TEXTOS_DA_LISTA, cabecalho
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import (
    contagem,
    data_curta,
    data_e_hora_curta,
    dia_da_semana_e_data,
    duracao,
    hora_curta,
    lista,
    numero,
    por_extenso,
)
from painel.dados.modelo import FUSO, NOME_DO_AMBIENTE, Ambiente, Credencial, Estado, IncidenteDeCredencial, Leitura, Renovacao
from painel.dados.telas import LeiturasDaCredencial, ler_credencial, montar_ja
from painel.periodo import opcoes_de_mes
from painel.renovacao import ATRASO_OBSERVADO, DIAS_DE_GRACA, prever_renovacao

dash.register_page(__name__, path="/credencial", name="Credencial do Verde", order=1, title="Credencial do Verde · Visor Maria")

PRAZO_DE_AVISO_DIAS = 10


# ── Um cartão por ambiente ────────────────────────────────────────────────


def _selo_da_credencial(credencial: Credencial, agora: datetime) -> html.Span:
    if credencial.valida_ate <= agora:
        return selo(f"Vencida há {duracao(agora - credencial.valida_ate)}", "ruim")
    faltam = (credencial.valida_ate.date() - agora.date()).days
    if faltam <= PRAZO_DE_AVISO_DIAS:
        return selo(f"Vence em {contagem(faltam, 'dia', 'dias')}", "atencao")
    return selo("Válida", "bom")


def _proxima_renovacao(credencial: Credencial, agora: datetime) -> Any:
    previsao = prever_renovacao(credencial.valida_ate, agora)
    if previsao.fora_do_prazo:
        return html.Span(f"fora do prazo de {DIAS_DE_GRACA} dias: só uma credencial nova resolve", className="mono tom-ruim")
    datas = lista([dia_da_semana_e_data(d) for d in previsao.dias]).replace(" e ", " ou ")
    fim_de_semana = any(d.weekday() >= 5 for d in previsao.dias)
    pecas: list[Any] = [html.Span(datas, className=f"mono tom-{'atencao' if fim_de_semana else 'neutro'}")]
    if len(previsao.dias) > 1:
        inicio, fim = (f"{h:%H:%M}" for h in ATRASO_OBSERVADO)
        pecas.append(html.Small(f"depende do atraso do GitHub, que tem começado entre {inicio} e {fim}", className="ponto-legenda"))
    return html.Span(pecas, className="coluna")


def _conferencia(credencial: Credencial) -> Any:
    if credencial.ultima_conferencia is None:
        return html.Span("sem registro", className="texto-vazio")
    resultado = {True: ("passou", "neutro"), False: ("falhou", "ruim"), None: ("sem resultado", "neutro")}
    texto, tom = resultado[credencial.conferencia_passou]
    return html.Span(f"{data_e_hora_curta(credencial.ultima_conferencia)}, {texto}", className=f"mono tom-{tom}")


def _corpo_do_cartao(credencial: Credencial, agora: datetime) -> list[Any]:
    vencida = credencial.valida_ate <= agora
    tom: Tom = "ruim" if vencida else ("atencao" if (credencial.valida_ate - agora).days < PRAZO_DE_AVISO_DIAS else "bom")
    pecas: list[Any] = [
        html.P("Venceu em" if vencida else "Válida até", className="rotulo-pequeno"),
        html.P(data_e_hora_curta(credencial.valida_ate), className=f"data-grande tom-{'ruim' if vencida else 'neutro'}"),
    ]
    if credencial.emitida_em is not None:
        total = (credencial.valida_ate - credencial.emitida_em).total_seconds()
        passado = (agora - credencial.emitida_em).total_seconds()
        pecas += [
            barra(passado / total if total else 1.0, tom, marca=passado / total if total and not vencida else None),
            html.Div(
                [
                    html.Span(data_curta(credencial.emitida_em)),
                    html.Span("hoje" if not vencida else f"venceu {data_curta(credencial.valida_ate)}"),
                    html.Span(data_curta(credencial.valida_ate) if not vencida else "hoje"),
                ],
                className="barra-escala mono",
            ),
        ]
    else:
        pecas.append(html.P("A emissão não aparece no log da conferência.", className="texto-vazio"))
    aceita = (
        html.Span(data_e_hora_curta(credencial.ultima_aceita), className="mono")
        if credencial.ultima_aceita
        else html.Span("nenhuma nos 30 dias de logs", className="texto-vazio")
    )
    pecas.append(
        definicoes(
            [
                ("Última consulta aceita", aceita),
                ("Última conferência", _conferencia(credencial)),
                ("Renovação automática" if vencida else "Próxima renovação", _proxima_renovacao(credencial, agora)),
            ]
        )
    )
    return pecas


def _cartao(ambiente: Ambiente, leitura: Leitura[Credencial], agora: datetime) -> html.Section:
    if leitura.estado is Estado.OK and leitura.valor is not None:
        corpo: Any = html.Div(_corpo_do_cartao(leitura.valor, agora), className="cartao-credencial")
        lateral: Any = _selo_da_credencial(leitura.valor, agora)
        classe = "borda-ruim" if leitura.valor.valida_ate <= agora else ""
    elif leitura.estado is Estado.INDISPONIVEL:
        corpo, lateral, classe = html.Div(texto_de_falha(leitura), className="cartao-credencial"), None, ""
    else:
        corpo = html.Div(html.P("A conferência diária não trouxe esta credencial.", className="texto-vazio"), className="cartao-credencial")
        lateral, classe = None, ""
    return quadro(NOME_DO_AMBIENTE[ambiente], corpo, [leitura], agora, lateral=lateral, classe=classe)


# ── Incidentes ────────────────────────────────────────────────────────────


COLUNAS_DOS_INCIDENTES = (
    ("Data", ""),
    ("Hora", ""),
    ("Ambiente", ""),
    ("Causa", ""),
    ("Duração", ""),
    ("Recusadas", "numero"),
    ("Atendimentos", "numero"),
    ("Estado", ""),
)


def _linha_do_incidente(incidente: IncidenteDeCredencial, causa: linha_do_tempo.Causa, agora: datetime) -> html.Tr:
    aberto = incidente.fim is None
    tempo = duracao((incidente.fim or agora) - incidente.inicio) + (" e contando" if aberto else "")
    atendimentos = numero(incidente.atendimentos) if incidente.atendimentos is not None else html.Span("não medido", className="texto-vazio")
    ambiente: Any = NOME_DO_AMBIENTE[incidente.ambiente]
    if incidente.ambiente is Ambiente.PRODUCAO:
        # Só produção atende pessoas; o release é o ambiente de teste.
        ambiente = html.Span([ambiente, html.Small("atinge o público", className="tom-ruim")], className="celula-empilhada")
    return html.Tr(
        [
            html.Td(data_curta(incidente.inicio), className="mono"),
            html.Td(hora_curta(incidente.inicio), className="mono"),
            html.Td(ambiente),
            html.Td(linha_do_tempo.NOME_DA_CAUSA[causa][0]),
            html.Td(tempo, className=f"mono {'tom-ruim' if aberto else ''}"),
            html.Td(numero(incidente.recusadas), className="numero"),
            html.Td(atendimentos, className="numero"),
            html.Td(ponto("Aberto", "ruim") if aberto else ponto("Resolvido", "bom")),
        ]
    )


def _credenciais_e_renovacoes(dados: LeiturasDaCredencial) -> tuple[dict[Ambiente, Credencial], list[Renovacao]]:
    """O que foi lido das credenciais e das renovações; o que faltou fica de fora."""
    credenciais = {a: c.valor for a, c in dados.credenciais.items() if c.estado is Estado.OK and c.valor is not None}
    renovacoes = dados.renovacoes.valor if dados.renovacoes.estado is Estado.OK and dados.renovacoes.valor else []
    return credenciais, renovacoes


def _incidentes(dados: LeiturasDaCredencial, dia: date | None) -> html.Section:
    leitura = dados.incidentes
    if leitura.estado is Estado.INDISPONIVEL:
        return quadro("Incidentes de credencial", texto_de_falha(leitura), [leitura], dados.agora)
    incidentes = sorted(leitura.valor or [], key=lambda i: i.inicio)
    if dia is not None:
        # Com o dia escolhido, os incidentes que estavam abertos em algum momento dele.
        incidentes = [i for i in incidentes if i.inicio.date() <= dia <= (i.fim or dados.agora).date()]
    if not incidentes:
        vazio = "Nenhuma recusa da credencial nos 30 dias de logs." if dia is None else f"Nenhuma recusa da credencial em {data_curta(dia)}."
        return quadro("Incidentes de credencial", html.P(vazio, className="texto-vazio"), [leitura], dados.agora)
    resumo = _como_se_resolveram(incidentes, dados.agora)
    abertos = sum(1 for i in incidentes if i.fim is None)
    resolvidos = len(incidentes) - abertos
    partes = []
    if resolvidos:
        partes.append(f"{por_extenso(resolvidos)} {'resolvido' if resolvidos == 1 else 'resolvidos'}")
    if abertos:
        partes.append(f"{por_extenso(abertos)} {'aberto' if abertos == 1 else 'abertos'}")
    credenciais, renovacoes = _credenciais_e_renovacoes(dados)
    causas = [linha_do_tempo.causa(i, credenciais, renovacoes) for i in incidentes]
    tabela = html.Table(
        [
            html.Thead(html.Tr([html.Th(t, className=c) for t, c in COLUNAS_DOS_INCIDENTES])),
            html.Tbody([_linha_do_incidente(i, c, dados.agora) for i, c in zip(incidentes, causas, strict=True)]),
        ],
        className="tabela",
    )
    # O que cada causa da tabela quer dizer, na ordem em que aparece.
    explicacao = html.Ul(
        [html.Li([html.Strong(linha_do_tempo.NOME_DA_CAUSA[c][0]), f": {linha_do_tempo.NOME_DA_CAUSA[c][1]}."]) for c in dict.fromkeys(causas)],
        className="lista-simples miolo",
    )
    janela = "em trinta dias" if dia is None else f"abertos em {data_curta(dia)}"
    return quadro("Incidentes de credencial", [resumo, tabela, explicacao], [leitura], dados.agora, lateral=f"{lista(partes)}, {janela}")


def _como_se_resolveram(incidentes: list[IncidenteDeCredencial], agora: datetime) -> html.Div:
    """Em cima da tabela: quanto tempo cada recusa levou para ser resolvida, e o que ela custou em atendimentos."""
    resolvidos = [i for i in incidentes if i.fim is not None]
    duracoes = [(i.fim or agora) - i.inicio for i in resolvidos]
    afetados = [i.atendimentos for i in incidentes if i.atendimentos is not None]
    colunas = [
        ("Tempo até resolver", duracao(sum(duracoes, timedelta()) / len(duracoes)) if duracoes else "nenhum resolvido", "em média, do primeiro ao último erro"),
        ("O mais longo", duracao(max(duracoes)) if duracoes else "nenhum resolvido", "entre os resolvidos"),
        ("Recusas", numero(sum(i.recusadas for i in incidentes)), "consultas que o Verde recusou"),
        ("Atendimentos afetados", numero(sum(afetados)) if afetados else "não medido", "conversas que bateram na recusa"),
    ]
    return html.Div(
        [
            html.Div([html.P(rotulo, className="coluna-rotulo"), html.P(valor, className="numero-medio"), html.P(legenda, className="indicador-legenda")])
            for rotulo, valor, legenda in colunas
        ],
        className="trio quarteto miolo",
    )


# ── Linha do tempo ────────────────────────────────────────────────────────


def _vencimento(evento: linha_do_tempo.Evento) -> Any:
    if evento.vencimento is not None:
        return data_curta(evento.vencimento)
    if evento.tipo == "renovada":
        # A conferência lê o segredo antes de renovar: a validade nova sai na do dia seguinte.
        return html.Span("na próxima conferência", className="texto-vazio")
    return ""


def _linha_do_evento(evento: linha_do_tempo.Evento) -> html.Tr:
    tom = linha_do_tempo.TOM_DO_TIPO[evento.tipo]
    tom_da_hora = "tom-suave" if evento.tipo == "gerada" else f"tom-{tom}"
    return html.Tr(
        [
            html.Td(data_curta(evento.momento), className=f"mono {tom_da_hora}"),
            html.Td(hora_curta(evento.momento), className=f"mono {tom_da_hora}"),
            html.Td(html.Span(evento.tipo, className=f"tempo-tipo tom-{tom}")),
            html.Td(_vencimento(evento), className="mono"),
            html.Td(evento.texto),
        ],
        className=f"tempo-{evento.tipo.replace(' ', '')}",
    )


def _linha_do_tempo(dados: LeiturasDaCredencial, dia: date | None) -> html.Section:
    leituras: list[Leitura[Any]] = dados.todas()
    credenciais, renovacoes = _credenciais_e_renovacoes(dados)
    incidentes = dados.incidentes.valor if dados.incidentes.estado is Estado.OK and dados.incidentes.valor else []
    eventos = linha_do_tempo.montar(credenciais, incidentes, renovacoes, dados.agora)
    if dia is not None:
        eventos = [e for e in eventos if e.momento.astimezone(FUSO).date() == dia]
    pecas: list[Any] = []
    if eventos:
        pecas.append(
            html.Table(
                [
                    html.Thead(html.Tr([html.Th(t) for t in ("Data", "Hora", "Tipo", "Vencimento", "O que aconteceu")])),
                    html.Tbody([_linha_do_evento(e) for e in eventos]),
                ],
                className="tabela tabela-do-tempo",
            )
        )
    faltaram = list(dict.fromkeys(leitura.fonte.curto for leitura in leituras if leitura.estado is not Estado.OK))
    if faltaram:
        pecas.append(html.P(f"Faltou ler: {lista(faltaram)}. A linha pode estar incompleta.", className="texto-aviso miolo"))
    if not pecas:
        vazio = "Nenhuma troca nem recusa nos últimos 30 dias." if dia is None else f"Nenhuma troca nem recusa em {data_curta(dia)}."
        pecas = [html.P(vazio, className="texto-vazio miolo")]
    lateral = "cada troca e cada recusa, em ordem; vencimento, até quando valia a credencial" if dia is None else f"o que aconteceu em {data_curta(dia)}"
    return quadro("Linha do tempo", pecas, leituras, dados.agora, lateral=lateral)


# ── Orientações ───────────────────────────────────────────────────────────

DICAS = html.Div(
    [
        dica(
            "Recusada",
            "Confira primeiro se o container foi reiniciado depois da última gravação do segredo. Na maioria das vezes a "
            "credencial está certa e o container é que ficou com a antiga.",
            "ruim",
        ),
        dica(
            "Vence em poucos dias",
            "Deixe a rotina renovar, de preferência em horário útil, com alguém acompanhando o reinício. Não renove à mão "
            "por fora da rotina: o Verde invalida a credencial antiga na hora.",
            "atencao",
        ),
        dica(
            "Sem consulta",
            "Se ninguém chamou o Verde no período, não dá para dizer que está tudo bem. Foi assim que a credencial do "
            "release passou dezenove dias vencida sem aparecer.",
            "neutro",
        ),
    ],
    className="grade-tripla",
)


# ── Montagem ──────────────────────────────────────────────────────────────


def blocos(dados: LeiturasDaCredencial, dia: date | None = None) -> list[Any]:
    return [
        html.Div([_cartao(a, dados.credenciais[a], dados.agora) for a in Ambiente], className="grade-dupla"),
        _incidentes(dados, dia),
        _linha_do_tempo(dados, dia),
    ]


def pe(dados: LeiturasDaCredencial) -> list[Any]:
    return [DICAS, lista_de_fontes(dados.todas(), dados.agora)]


FILTRADO = "Os incidentes e a linha do tempo mostram só o que aconteceu nesse dia."
DE_AGORA = "A validade das credenciais, nos dois cartões, continua sendo a de agora."
filtro_de_dia.registrar("credencial", FILTRADO, DE_AGORA)


# Os dois gráficos do fim da tela mostram os últimos 30 dias ou um mês escolhido.
ID_DO_PERIODO = "credencial-graficos-periodo"
DIAS, MES = "dias", "mes"
# A conferência diária roda desde 19/09/2026: antes disso, não há mês para escolher.
PRIMEIRO_MES = "2026-09"


def _periodo_dos_graficos(agora: datetime) -> html.Div:
    meses = [m for m in opcoes_de_mes(agora) if m["value"] >= PRIMEIRO_MES]
    return html.Div(
        [
            html.Span("Gráficos", className="rotulo-filtro"),
            dcc.RadioItems(
                id=ID_DO_PERIODO,
                options=cast(Any, [{"label": "Dias", "value": DIAS}, {"label": "Mês", "value": MES}]),
                value=DIAS,
                inline=True,
                className="filtro-ambiente",
                inputClassName="filtro-ambiente-entrada",
                labelClassName="filtro-ambiente-opcao",
            ),
            html.Div(
                dcc.Dropdown(
                    id=f"{ID_DO_PERIODO}-mes",
                    options=cast(Any, meses),
                    value=meses[0]["value"],
                    clearable=False,
                    searchable=False,
                    labels=cast(Any, TEXTOS_DA_LISTA),
                    className="filtro-data",
                ),
                id=f"{ID_DO_PERIODO}-caixa-do-mes",
                className="filtro-data-caixa",
                hidden=True,
            ),
            html.P("Dias: os últimos 30, um por dia. Mês: os dias do mês escolhido.", className="periodo-texto"),
        ],
        className="filtro-periodo",
        role="group",
        **aria(label="Período dos gráficos"),
    )


def _mes_escolhido(periodo: str | None, mes: str | None) -> date | None:
    if periodo != MES or not mes:
        return None
    try:
        return date.fromisoformat(f"{mes}-01")
    except ValueError:
        return None


def layout(dia: str | None = None, **_: str) -> html.Div:
    agora = datetime.now(FUSO)
    escolhido = filtro_de_dia.ler(dia, agora)
    graficos = montar_ja(partial(lateral.graficos_da_credencial, None, Filtro(escolhido)))
    dados = ler_credencial()
    # Sem a coluna da direita e sem limite de largura: a tela ocupa o monitor todo, e os
    # gráficos ficam no fim dela, para ler dia a dia as consultas e a hora da conferência
    # (pedido de 09/11).
    return html.Div(
        [
            cabecalho("Credencial do Verde", "Está valendo, e por quanto tempo?"),
            filtro_de_dia.armazem("credencial", escolhido),
            filtro_de_dia.faixa("credencial", escolhido),
            html.Div(blocos(dados, escolhido), id="credencial-corpo", className="tela-corpo"),
            _periodo_dos_graficos(agora),
            html.Div(graficos.result(), id="credencial-graficos", className="tela-corpo"),
            html.Div(pe(dados), id="credencial-pe", className="tela-corpo"),
        ],
        className="tela tela-inteira",
    )


@callback(
    Output("credencial-corpo", "children"),
    Output("credencial-pe", "children"),
    Input("relogio", "n_intervals"),
    filtro_de_dia.entrada("credencial"),
    prevent_initial_call=True,
)
def atualizar(_: int, dia: str | None) -> tuple[list[Any], list[Any]]:
    dados = ler_credencial()
    return blocos(dados, filtro_de_dia.filtro(dia).dia), pe(dados)


# Os gráficos: a cada minuto, com o tema guardado, o filtro da tela e o período deles.
@callback(
    Output("credencial-graficos", "children"),
    Output(f"{ID_DO_PERIODO}-caixa-do-mes", "hidden"),
    Input("relogio", "n_intervals"),
    Input("tema", "data"),
    filtro_de_dia.entrada("credencial"),
    Input(ID_DO_PERIODO, "value"),
    Input(f"{ID_DO_PERIODO}-mes", "value"),
)
def atualizar_os_graficos(_: int | None, tema: str | None, dia: str | None, periodo: str | None, mes: str | None) -> tuple[list[Any], bool]:
    return lateral.graficos_da_credencial(tema, filtro_de_dia.filtro(dia), _mes_escolhido(periodo, mes)), periodo != MES
