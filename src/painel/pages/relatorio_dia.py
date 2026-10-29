"""Tela Relatório do dia: como foi o dia?

Segue o rascunho: o dia em uma frase, cinco indicadores de produção, o Verde e
o sistema no dia, e o que fica para amanhã. Na coluna da direita, o que só o
relatório tem: o dia contra a média da semana anterior e os problemas do dia,
com o que aconteceu com a conversa em cada um. O dia hora a hora e como
terminaram ficam na Agora, sem repetir.

Duas diferenças do rascunho, pelas regras do painel:
- a frase e o "o que fica para amanhã" saem de regra sobre os dados
  (`painel/frase_do_dia.py` e `painel/atencao.py`), e não de texto fixo;
- "Enviar por email" fica desligado: não há endereço de grupo para os avisos (#308).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from functools import partial
from typing import Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, html

from painel import frase_do_dia, lateral
from painel.atencao import itens_de_atencao
from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import (
    Tom,
    Valor,
    celula_de_leitura,
    definicoes,
    indicador,
    lista_de_fontes,
    nota_de_fonte,
    ponto,
    quadro,
    selo,
    texto_de_falha,
)
from painel.componentes.cabecalho import acao_em_breve, cabecalho
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import contagem, data_curta, dia_por_extenso, lista, numero
from painel.dados import obter_fonte
from painel.dados.fontes import DIAS_DO_GRAFICO_DO_VERDE
from painel.dados.modelo import FUSO, NOME_DO_AMBIENTE, Ambiente, ContagemPorDia, Credencial, DiaDoVerde, Estado, Leitura, Rotina
from painel.dados.telas import LeiturasDoDia, dias_passados, ler_dia, montar_ja, preparar
from painel.lateral import coluna, com_lateral

dash.register_page(__name__, path="/dia", name="Relatório do dia", order=4, title="Relatório do dia · Visor Maria")

FILTRADO = "O relatório inteiro passa a ser do que foi escolhido: a frase, os números, o Verde, o sistema, o dia contra a semana e os problemas do dia."
DE_AGORA = "A credencial e o que fica para amanhã continuam sendo de agora."
filtro_de_dia.registrar("dia", FILTRADO, DE_AGORA)


def _quando(dados: LeiturasDoDia) -> str:
    """ "hoje", "em 22/10", ou "em 22/10, das 14h às 15h" com a hora escolhida no gráfico hora a hora."""
    return "hoje" if dados.quando == dados.agora.date() else f"em {filtro_de_dia.rotulo(dados.quando)}"


def _subtitulo(dados: LeiturasDoDia) -> str:
    return dia_por_extenso(datetime.combine(dados.dia, time(12), tzinfo=FUSO), com_ano=True)


def _frase(dados: LeiturasDoDia) -> html.Section:
    leituras = [dados.resumo[Ambiente.PRODUCAO], dados.verde[Ambiente.PRODUCAO], *dados.credenciais.values()]
    frase = frase_do_dia.montar(
        dados.resumo[Ambiente.PRODUCAO], dados.verde[Ambiente.PRODUCAO], dados.credenciais, dados.agora, _quando(dados), isinstance(dados.quando, datetime)
    )
    return html.Section(
        [html.P("O dia em uma frase", className="frase-rotulo"), html.P(frase, className="frase-texto"), nota_de_fonte(leituras, dados.agora)],
        className="frase-do-dia",
    )


def _indicadores(dados: LeiturasDoDia, escolha: Filtro = Filtro()) -> list[html.Section]:
    resumo, agora = dados.resumo[Ambiente.PRODUCAO], dados.agora

    def r() -> Any:
        assert resumo.valor is not None
        return resumo.valor

    vazio = "Nada ainda hoje." if _quando(dados) == "hoje" else f"Nada {_quando(dados)}."
    terminaram = filtro_de_dia.terminaram_no_motivo(dados.desfechos, escolha.motivo, vazio, agora)
    return [
        indicador("Começaram", "conversa", [resumo], lambda: Valor(numero(r().comecaram)), vazio, agora),
        terminaram or indicador("Terminaram", "certo", [resumo], lambda: Valor(numero(r().terminaram)), vazio, agora),
        indicador("Em aberto", "relogio", [resumo], lambda: Valor(numero(r().comecaram - r().terminaram)), vazio, agora),
        indicador("Perguntas feitas", "busca", [resumo], lambda: Valor(numero(r().perguntas)), vazio, agora),
        indicador(
            "Cortadas pela troca",
            "alerta",
            [resumo],
            lambda: Valor(numero(r().sem_checkpoint), "atencao" if r().sem_checkpoint else "neutro"),
            vazio,
            agora,
        ),
    ]


def _credencial_curta(credencial: Credencial, agora: Any) -> html.Div:
    if credencial.valida_ate <= agora:
        return ponto("Vencida", "ruim")
    faltam = (credencial.valida_ate.date() - agora.date()).days
    if faltam <= 10:
        return ponto(f"Vence em {contagem(faltam, 'dia', 'dias')}", "atencao")
    return ponto(f"Vale até {data_curta(credencial.valida_ate)}", "bom")


def _verde_hoje(dados: LeiturasDoDia) -> html.Section:
    def hoje(leitura: Leitura[list[DiaDoVerde]]) -> DiaDoVerde | None:
        # O último dia da lista é o do relatório (dados/telas.py), se ele estiver nos 8 dias do Verde.
        dia = leitura.valor[-1] if leitura.estado is Estado.OK and leitura.valor else None
        return dia if dia is not None and dia.dia == dados.dia else None

    linhas = []
    for a in Ambiente:
        dia = hoje(dados.verde[a])
        consultas = numero(dia.total) if dia else celula_de_leitura(dados.verde[a], lambda _: "", "sem consulta")
        aceitas = html.Span(numero(dia.aceitas), className="tom-bom" if dia and dia.aceitas else "") if dia else ""
        linhas.append(
            html.Tr(
                [
                    html.Th(NOME_DO_AMBIENTE[a], scope="row"),
                    html.Td(consultas, className="numero"),
                    html.Td(aceitas, className="numero"),
                    html.Td(celula_de_leitura(dados.credenciais[a], lambda c: _credencial_curta(c, dados.agora), "sem conferência")),
                ]
            )
        )
    tabela = html.Table(
        [
            html.Thead(html.Tr([html.Th("Ambiente"), html.Th("Consultas", className="numero"), html.Th("Aceitas", className="numero"), html.Th("Credencial")])),
            html.Tbody(linhas),
        ],
        className="tabela",
    )
    # O Verde é contado por dia: com a hora escolhida, o dia inteiro dela.
    no_dia = "hoje" if dados.dia == dados.agora.date() else f"em {data_curta(dados.dia)}"
    return quadro(f"O Verde {no_dia}", tabela, [*dados.verde.values(), *dados.credenciais.values()], dados.agora, lateral="credencial de agora")


def _sistema(dados: LeiturasDoDia) -> html.Section:
    leituras: list[Leitura[Any]] = [*dados.sistema.values(), dados.rotinas]
    sistemas = {a: s.valor for a, s in dados.sistema.items() if s.estado is Estado.OK and s.valor is not None}
    if not sistemas:
        problema = next(iter(dados.sistema.values()))
        corpo: Any = celula_de_leitura(problema, lambda _: "", f"Nada registrado {_quando(dados)}.")
        return quadro("Sistema e entregas", corpo, leituras, dados.agora)

    def por_ambiente(campo: Any) -> str:
        return lista([f"{campo(s)} {'em produção' if a is Ambiente.PRODUCAO else 'no release'}" for a, s in sistemas.items()])

    reinicios = [f"{m:%H:%M} {'em produção' if a is Ambiente.PRODUCAO else 'no release'}" for a, s in sistemas.items() for m in s.reinicios]
    falhando = []
    if dados.rotinas.estado is Estado.OK and dados.rotinas.valor is not None:
        falhando = [r.nome.lower() for r in dados.rotinas.valor if r.falhando_desde is not None]
        rotinas_com_falha: Any = html.Span(f"{len(falhando)}, {lista(falhando)}", className="tom-ruim") if falhando else "nenhuma"
    else:
        rotinas_com_falha = html.Span("não deu para ler", className="texto-aviso")
    pares = [
        ("Fora do ar", por_ambiente(lambda s: contagem(s.minutos_fora_do_ar, "minuto", "minutos"))),
        ("Reinícios", html.Span(lista(reinicios), className="mono") if reinicios else "nenhum"),
        ("Erros de servidor", por_ambiente(lambda s: numero(s.erros_de_servidor))),
        ("Subidas", por_ambiente(lambda s: numero(s.subidas))),
        ("Testes", "todos passaram" if all(s.testes_com_falha == 0 for s in sistemas.values()) else "com falha"),
        ("Rotinas com falha", rotinas_com_falha),
    ]
    return quadro("Sistema e entregas", html.Div(definicoes(pares), className="miolo"), leituras, dados.agora)


SELO: dict[str, tuple[str, Tom]] = {"parado": ("Parado", "ruim"), "atencao": ("Atenção", "atencao")}


def _para_amanha(dados: LeiturasDoDia) -> html.Section:
    verde = dados.verde
    rotinas: Leitura[list[Rotina]] = dados.rotinas
    itens = itens_de_atencao(dados.credenciais, verde, rotinas, dados.agora)
    leituras: list[Leitura[Any]] = [*dados.credenciais.values(), *verde.values(), rotinas]
    linhas: list[Any] = [
        html.Li(
            [
                selo(*SELO[i.nivel]),
                html.Div([html.P(i.titulo, className="atencao-titulo"), html.P(i.descricao, className="atencao-descricao")]),
            ],
            className="atencao-linha linha-dupla",
        )
        for i in itens
    ]
    faltaram = list(dict.fromkeys(leitura.fonte.curto for leitura in leituras if leitura.estado is not Estado.OK))
    if faltaram:
        linhas.append(html.Li(html.P(f"Faltou ler: {lista(faltaram)}. Esta lista pode estar incompleta.", className="texto-aviso"), className="atencao-linha"))
    elif not linhas:
        linhas = [html.Li(html.P("Nada fica para amanhã pelas regras do painel.", className="texto-vazio"), className="atencao-linha")]
    return quadro("O que fica para amanhã", html.Ul(linhas, className="atencao-lista"), leituras, dados.agora, lateral="em ordem de gravidade")


NOTA_DO_PE = html.P(
    "Este relatório cobre só o que a Maria enxerga. Comparar com meses anteriores ainda não é possível, porque o registro "
    "guarda trinta dias. E não sabemos se a pessoa encaminhada foi de fato atendida.",
    className="nota-do-pe",
)


def blocos(dados: LeiturasDoDia, escolha: Filtro = Filtro()) -> list[Any]:
    return [
        _frase(dados),
        html.Div(_indicadores(dados, escolha), className="grade-indicadores"),
        html.Div([_verde_hoje(dados), _sistema(dados)], className="grade-dupla"),
        _para_amanha(dados),
        NOTA_DO_PE,
        lista_de_fontes(dados.todas(), dados.agora),
    ]


# ── Os últimos 8 dias: o gráfico em que se escolhe o dia ──────────────────


def _figura_dos_dias(dias: list[ContagemPorDia], tema: str | None, dia: date | None) -> go.Figure:
    c = graficos.cores(tema)
    meio_dia = [datetime.combine(d.dia, time(12), tzinfo=FUSO) for d in dias]
    figura = go.Figure()
    figura.add_bar(x=meio_dia, y=[d.comecaram for d in dias], marker_color=c["bom"], hovertemplate="%{x|%d/%m}: %{y} começaram<extra></extra>")
    figura.update_layout(
        **graficos.layout_base(tema),
        barcornerradius=3,
        height=150,
        xaxis={"showgrid": False, "fixedrange": True, "tickformat": "%d/%m"},
        yaxis={"visible": False, "fixedrange": True},
    )
    graficos.marcar_corte_de_versao(figura, meio_dia[0] - timedelta(hours=12), meio_dia[-1] + timedelta(hours=12), c["suave"])
    return filtro_de_dia.destacar(figura, dia, tema)


def conteudo_dos_dias(leitura: Leitura[list[ContagemPorDia]], tema: str | None, agora: datetime, dia: date | None) -> list[Any]:
    """O miolo do quadro, com a fonte no pé. Clicar num dia faz o relatório daquele dia."""
    dias = (leitura.valor or [])[-DIAS_DO_GRAFICO_DO_VERDE:]
    if leitura.estado is Estado.INDISPONIVEL:
        miolo: list[Any] = [texto_de_falha(leitura)]
    elif not any(d.comecaram for d in dias):
        miolo = [html.P(f"Ninguém começou um atendimento em produção nos últimos {DIAS_DO_GRAFICO_DO_VERDE} dias.", className="texto-vazio")]
    else:
        miolo = [filtro_de_dia.grafico("dia", "dias", _figura_dos_dias(dias, tema, dia))]
    return [html.Div(miolo, className="quadro-corpo"), html.Footer(nota_de_fonte([leitura], agora), className="quadro-pe")]


def _quadro_dos_dias(dados: LeiturasDoDia) -> html.Section:
    return html.Section(
        [
            html.Header(
                [
                    html.H2(f"Os últimos {DIAS_DO_GRAFICO_DO_VERDE} dias"),
                    html.Div("atendimentos que começaram, produção; clique num dia", className="quadro-lateral"),
                ],
                className="quadro-topo",
            ),
            html.Div(conteudo_dos_dias(dados.por_dia, None, dados.agora, dados.dia if dados.escolhido else None), id="dia-dias"),
        ],
        className="quadro",
    )


def _tela(escolha: Filtro) -> html.Div:
    dados = ler_dia(escolha.quando)
    return html.Div(
        [
            cabecalho(
                "Relatório do dia",
                html.Span(_subtitulo(dados), id="dia-subtitulo"),
                [acao_em_breve("Enviar por email", "arquivo", "Depende do endereço de grupo que recebe os avisos (#308)")],
            ),
            filtro_de_dia.armazem("dia", escolha),
            filtro_de_dia.faixa("dia", escolha),
            _quadro_dos_dias(dados),
            html.Div(blocos(dados, escolha), id="dia-corpo", className="tela-corpo"),
        ],
        className="tela",
    )


@callback(
    Output("dia-corpo", "children"),
    Output("dia-subtitulo", "children"),
    Input("relogio", "n_intervals"),
    filtro_de_dia.entrada("dia"),
    prevent_initial_call=True,
)
def atualizar(_: int | None, guardado: Any) -> tuple[list[Any], str]:
    escolha = filtro_de_dia.filtro(guardado)
    dados = ler_dia(escolha.quando)
    return blocos(dados, escolha), _subtitulo(dados)


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador.
@callback(
    Output("dia-dias", "children"),
    Input("relogio", "n_intervals"),
    Input("tema", "data"),
    filtro_de_dia.entrada("dia"),
)
def atualizar_os_dias(_: int | None, tema: str | None, dia: str | None) -> list[Any]:
    leitura = obter_fonte().atendimentos_por_dia(Ambiente.PRODUCAO)
    return conteudo_dos_dias(leitura, tema, leitura.lido_em, filtro_de_dia.filtro(dia).dia)


def layout(dia: str | None = None, **_: str) -> html.Div:
    agora = datetime.now(FUSO)
    escolhido = filtro_de_dia.ler(dia, agora)
    # Os dias do gráfico, lidos por trás: o clique num deles já encontra a leitura.
    for passado in dias_passados(DIAS_DO_GRAFICO_DO_VERDE, agora):
        for ambiente in Ambiente:
            preparar("resumo_do_dia", ambiente, passado)
            preparar("sistema_no_dia", ambiente, passado)
        preparar("desfechos_do_dia", Ambiente.PRODUCAO, passado)
    lado = montar_ja(partial(lateral.do_dia, None, Filtro(escolhido)))
    return com_lateral(_tela(Filtro(escolhido)), coluna("dia-lateral", lado.result()))


# A coluna da direita: a cada minuto, com o tema guardado e com o filtro da tela.
@callback(
    Output("dia-lateral", "children"),
    Input("relogio", "n_intervals"),
    Input("tema", "data"),
    filtro_de_dia.entrada("dia"),
)
def atualizar_a_lateral(_: int | None, tema: str | None, dia: str | None) -> list[Any]:
    return lateral.do_dia(tema, filtro_de_dia.filtro(dia))
