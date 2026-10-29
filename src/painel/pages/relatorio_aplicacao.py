"""Tela Relatório da Aplicação: de onde vem o gasto, em que dia e em que mês?

Escrita para quem lê de finanças: nenhum nome técnico nos rótulos. "Texto lido"
e "texto escrito" são os tokens de entrada e de saída da inteligência
artificial; "busca por semelhança", os embeddings. Os nomes técnicos ficam só em
"De onde vem cada número", no pé da tela.

O período vem do filtro do cabeçalho. Os três gastos e as barras por dia ficam
ancorados no último dia do período; "De onde vem o gasto" e "Qual atendimento
custa mais" cobrem o período inteiro, como o atendimento humano: quantos
atendimentos a Maria resolveu, quantos foram para pessoa, por que motivo e com
que tipo de problema. Esses saem dos encerramentos nos logs, só contados.

O que não dá para medir fica visível, dizendo o que falta e de quem depende:
nenhum número inventado. A fonte do banco fica de fora (nada lê o banco antes
da #309).
"""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html
from dash.exceptions import PreventUpdate

from painel import gasto, lateral
from painel.componentes import graficos
from painel.componentes.blocos import (
    Pendencia,
    Tom,
    Valor,
    indicador,
    lista_de_fontes,
    nota_de_fonte,
    quadro,
    reservado,
    selo,
    texto_de_falha,
)
from painel.componentes.cabecalho import cabecalho, filtro_de_ambiente, filtro_de_periodo
from painel.componentes.formato import MESES, data_curta, dia_da_semana_e_data, dinheiro, numero
from painel.dados.fontes import DIAS_DO_REGISTRO, MODELO_DE_CHAT, MODELO_DE_EMBEDDING, REGISTRO_DO
from painel.dados.modelo import (
    FUSO,
    NOME_DO_AMBIENTE,
    NOME_DO_ASSUNTO,
    TIPOS_DE_PROBLEMA,
    Ambiente,
    Assunto,
    Destino,
    EncaminhamentoNoDia,
    Estado,
    GastoDeIA,
    GastoDoAssunto,
    Leitura,
    TipoDeProblema,
    TokensRegistrados,
    nome_do_desfecho,
    nome_do_fluxo,
    tipo_do_motivo,
)
from painel.dados.telas import LeiturasDaAplicacao, ler_aplicacao
from painel.funcoes_de_ia import FUNCOES
from painel.lateral import coluna, com_lateral
from painel.periodo import Escolha, Periodo, descrever
from painel.periodo import montar as montar_periodo
from painel.precos import NOME_DA_PARCELA, NOME_DOS_SERVIDORES, PRECOS, Parcela, custo_do_assunto, parcelas, total

dash.register_page(__name__, path="/aplicacao", name="Relatório da Aplicação", order=5, title="Relatório da Aplicação · Visor Maria")

ID_DO_PERIODO = "aplicacao-periodo"
ID_DO_AMBIENTE = "aplicacao-ambiente"
ID_DOS_DIAS = "aplicacao-grafico-dias"
ID_DOS_MESES = "aplicacao-grafico-meses"
# Cor no gráfico e na legenda; na barra da tabela, a busca fica no tom neutro.
COR_DA_PARCELA = {Parcela.LIDO: "azul", Parcela.ESCRITO: "rosa", Parcela.BUSCA: "outro"}
TOM_DA_PARCELA: dict[Parcela, Tom] = {Parcela.LIDO: "azul", Parcela.ESCRITO: "rosa", Parcela.BUSCA: "neutro"}
CURTO_DA_PARCELA = {Parcela.LIDO: "texto lido", Parcela.ESCRITO: "texto escrito", Parcela.BUSCA: "busca por semelhança"}


def _mes(dia: date) -> str:
    return MESES[dia.month - 1]


def _valor(leitura: Leitura[GastoDeIA]) -> float:
    """Período sem gasto contado vale zero na comparação, e não "sem leitura"."""
    return total(leitura.valor) if leitura.valor is not None else 0.0


# ── Gasto do dia, da semana e do mês ──────────────────────────────────────


def _comparado(
    dados: LeiturasDaAplicacao, rotulo: str, nome_do_icone: str, atual: gasto.Trecho, anterior: gasto.Trecho, referencia: str, vazio: str
) -> html.Section:
    leitura = dados.gasto(atual.primeiro, atual.ultimo)
    antes = dados.gasto(anterior.primeiro, anterior.ultimo)
    # O período anterior sem gasto entra como zero; a falha dele aparece.
    leituras = [leitura, antes] if antes.estado is Estado.INDISPONIVEL else [leitura]
    return indicador(
        rotulo,
        nome_do_icone,
        leituras,
        lambda: Valor(dinheiro(_valor(leitura)), legenda=gasto.variacao(_valor(leitura), _valor(antes), referencia)),
        vazio,
        dados.agora,
    )


def _rotulo_do_periodo(periodo: Periodo, agora: datetime) -> str:
    primeiro, ultimo = periodo.primeiro_dia, periodo.ultimo_dia
    if periodo.escolha is Escolha.MES:
        return f"Gasto em {_mes(ultimo)}" + ("" if ultimo == gasto.ultimo_do_mes(ultimo) else f", até {data_curta(ultimo)}")
    dias = (ultimo - primeiro).days + 1
    return f"Gasto em {dias} dias, {data_curta(primeiro)} a {data_curta(ultimo)}" + (f", até {agora:%H:%M}" if periodo.termina_hoje else "")


def _referencia(periodo: Periodo, anterior: gasto.Trecho) -> str:
    """Com quem o período se compara, em palavras: completa "12% a mais que ..."."""
    trecho = f"{data_curta(anterior.primeiro)} a {data_curta(anterior.ultimo)}"
    if periodo.escolha is Escolha.MES:
        if anterior.ultimo == gasto.ultimo_do_mes(anterior.ultimo):
            return f"em {_mes(anterior.primeiro)} inteiro"
        return f"no mesmo trecho de {_mes(anterior.primeiro)} ({trecho})"
    return f"nos {len(anterior.dias)} dias antes ({trecho})"


def _indicadores_do_periodo(dados: LeiturasDaAplicacao) -> html.Div:
    """7 dias, 30 dias e mês: o gasto do período, a média por dia e o dia mais caro,
    cada um comparado com o período anterior do mesmo tamanho."""
    periodo, agora = dados.periodo, dados.agora.astimezone(FUSO)
    atual = gasto.Trecho(periodo.primeiro_dia, periodo.ultimo_dia)
    anterior = gasto.anterior_ao_periodo(atual.primeiro, atual.ultimo, periodo.escolha is Escolha.MES)
    leitura, antes = dados.gasto(atual.primeiro, atual.ultimo), dados.gasto(anterior.primeiro, anterior.ultimo)
    leituras = [leitura, antes] if antes.estado is Estado.INDISPONIVEL else [leitura]
    referencia = _referencia(periodo, anterior)
    vazio = "A AWS não contou gasto nenhum no período."

    def media() -> Valor:
        # Hoje conta como um dia, mesmo antes de terminar: a legenda diz isso.
        # Os dois períodos têm os mesmos dias, então a variação seria a do total: a legenda
        # mostra, em vez dela, quanto era o dia antes.
        por_dia, antes_por_dia = _valor(leitura) / len(atual.dias), _valor(antes) / len(anterior.dias)
        legenda = f"em {len(atual.dias)} dias; antes, {dinheiro(antes_por_dia)} por dia"
        return Valor(dinheiro(por_dia), legenda=legenda + (", com hoje ainda em curso" if periodo.termina_hoje else ""))

    def mais_caro() -> Valor:
        dias = [(d, _valor(dados.dias[d])) for d in atual.dias]
        dia, valor = max(dias, key=lambda par: par[1], default=(atual.ultimo, 0.0))
        parte = round(valor / _valor(leitura) * 100) if _valor(leitura) else 0
        return Valor(dinheiro(valor), legenda=f"em {dia_da_semana_e_data(dia)}, {parte}% do período")

    return html.Div(
        [
            _comparado(dados, _rotulo_do_periodo(periodo, agora), "carteira", atual, anterior, referencia, vazio),
            indicador("Média por dia no período", "relogio", leituras, media, vazio, dados.agora),
            indicador("Dia mais caro do período", "arquivo", [leitura], mais_caro, vazio, dados.agora),
        ],
        className="grade-tripla",
    )


def _indicadores(dados: LeiturasDaAplicacao) -> html.Div:
    periodo, agora = dados.periodo, dados.agora.astimezone(FUSO)
    if len(periodo.dias) > 1:
        return _indicadores_do_periodo(dados)
    # Um dia só (hoje ou uma data): o dia, os 7 dias até ele e o mês até ele.
    ancora = periodo.ultimo_dia
    t = gasto.trechos(ancora)
    if periodo.termina_hoje:
        rotulo_do_dia, referencia_do_dia = f"Gasto de hoje, até {agora:%H:%M}", f"no dia {data_curta(t.dia_anterior.primeiro)} inteiro"
    else:
        rotulo_do_dia, referencia_do_dia = f"Gasto em {data_curta(ancora)}", f"no dia {data_curta(t.dia_anterior.primeiro)}"
    mes_inteiro = ancora == gasto.ultimo_do_mes(ancora)
    rotulo_do_mes = f"Gasto em {_mes(ancora)}" + ("" if mes_inteiro else f", até {data_curta(ancora)}")
    anterior = t.mes_anterior
    return html.Div(
        [
            _comparado(dados, rotulo_do_dia, "carteira", t.dia, t.dia_anterior, referencia_do_dia, "A AWS não contou gasto nenhum neste dia."),
            _comparado(
                dados,
                f"Gasto em 7 dias, {data_curta(t.semana.primeiro)} a {data_curta(ancora)}",
                "relogio",
                t.semana,
                t.semana_anterior,
                f"nos 7 dias antes ({data_curta(t.semana_anterior.primeiro)} a {data_curta(t.semana_anterior.ultimo)})",
                "A AWS não contou gasto nenhum nestes 7 dias.",
            ),
            _comparado(
                dados,
                rotulo_do_mes,
                "arquivo",
                t.mes,
                anterior,
                f"no mesmo trecho de {_mes(anterior.primeiro)} ({data_curta(anterior.primeiro)} a {data_curta(anterior.ultimo)})",
                f"A AWS não contou gasto nenhum em {_mes(ancora)}.",
            ),
        ],
        className="grade-tripla",
    )


# ── Gráficos ──────────────────────────────────────────────────────────────


def _detalhe(titulo: str, g: GastoDeIA) -> str:
    """O texto que aparece ao passar o mouse numa barra."""
    p = parcelas(g)
    linhas = [f"<b>{titulo}: {dinheiro(total(g))}</b>"] + [f"{CURTO_DA_PARCELA[parcela]}: {dinheiro(valor)}" for parcela, valor in p.items()]
    return "<br>".join(linhas)


def _barras(
    figura: go.Figure, x: list[Any], gastos: list[GastoDeIA], destaque: list[bool], titulos: list[str], tema: str | None, largura: float | None
) -> None:
    c = graficos.cores(tema)
    textos = [_detalhe(titulo, g) for titulo, g in zip(titulos, gastos, strict=True)]
    for numero_da_serie, (parcela, cor) in enumerate(COR_DA_PARCELA.items()):
        figura.add_bar(
            x=x,
            y=[parcelas(g)[parcela] for g in gastos],
            name=CURTO_DA_PARCELA[parcela],
            marker={"color": c[cor], "opacity": [1.0 if d else 0.45 for d in destaque]},
            width=largura,
            customdata=textos,
            hovertemplate="%{customdata}<extra></extra>",
            # Uma caixa só por coluna: o resumo do dia já traz as três parcelas.
            hoverinfo=None if numero_da_serie == 0 else "skip",
        )
    # A coluna inteira responde ao mouse e ao clique, mesmo com a barra baixa.
    figura.update_layout(hovermode="x")


def _eixo_y(tema: str | None) -> dict[str, Any]:
    return {"showgrid": True, "gridcolor": graficos.cores(tema)["grade"], "fixedrange": True, "tickprefix": "US$ ", "tickformat": ".2f"}


def figura_dos_dias(dias: list[GastoDeIA], ancora: date, tema: str | None, destaque: set[date] | None = None) -> go.Figure:
    """`destaque`: os dias do período escolhido (sem ele, só a âncora)."""
    figura = go.Figure()
    meio_dia = [datetime.combine(g.inicio, time(12), tzinfo=FUSO) for g in dias]
    titulos = [data_curta(g.inicio) for g in dias]
    _barras(figura, meio_dia, dias, [g.inicio in (destaque or {ancora}) for g in dias], titulos, tema, 0.72 * 86_400_000)
    inicio = datetime.combine(gasto.primeiro_do_mes(ancora), time(), tzinfo=FUSO)
    fim = datetime.combine(gasto.ultimo_do_mes(ancora) + timedelta(days=1), time(), tzinfo=FUSO)
    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="stack",
        barcornerradius=3,
        height=240,
        separators=",.",
        xaxis={"showgrid": False, "fixedrange": True, "tickformat": "%d/%m", "range": [inicio, fim]},
        yaxis=_eixo_y(tema),
    )
    # A medição é da conta inteira, que inclui produção: cruza o corte de versão.
    return graficos.marcar_corte_de_versao(figura, inicio, fim, graficos.cores(tema)["suave"])


def _rotulo_do_mes(mes: date) -> str:
    return f"{MESES[mes.month - 1][:3]}/{mes:%y}"


def figura_dos_meses(meses: list[GastoDeIA], ancora: date, tema: str | None, destaque: set[date] | None = None) -> go.Figure:
    """`destaque`: o primeiro dia dos meses que o período escolhido toca (sem ele, o mês da âncora)."""
    figura = go.Figure()
    mes_da_ancora = gasto.primeiro_do_mes(ancora)
    titulos = [f"{_mes(g.inicio)} de {g.inicio.year}" + (f", até {data_curta(ancora)}" if g.inicio == mes_da_ancora else "") for g in meses]
    # O valor do eixo é o mês ("2026-09"), que o clique devolve; o rótulo é "set/26".
    x = [f"{g.inicio:%Y-%m}" for g in meses]
    _barras(figura, x, meses, [g.inicio in (destaque or {mes_da_ancora}) for g in meses], titulos, tema, None)
    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="stack",
        barcornerradius=3,
        height=220,
        separators=",.",
        xaxis={"showgrid": False, "fixedrange": True, "type": "category", "tickvals": x, "ticktext": [_rotulo_do_mes(g.inicio) for g in meses]},
        yaxis=_eixo_y(tema),
    )
    return figura


def _legenda() -> html.Div:
    return html.Div(
        [html.Span([html.Span(className=f"legenda-cor tom-{COR_DA_PARCELA[p]}"), NOME_DA_PARCELA[p]]) for p in Parcela],
        className="legenda",
    )


def _grafico(id_: str, leitura: Leitura[list[GastoDeIA]], desenhar: Any, vazio: str) -> list[Any]:
    if leitura.estado is Estado.INDISPONIVEL:
        return [texto_de_falha(leitura)]
    if not leitura.valor or not any(total(g) for g in leitura.valor):
        return [html.P(vazio, className="texto-vazio")]
    return [dcc.Graph(id=id_, figure=desenhar(leitura.valor), config={"displayModeBar": False}, className="grafico grafico-clicavel"), _legenda()]


def _quadro_dos_dias(dados: LeiturasDaAplicacao, tema: str | None) -> html.Section:
    ancora = dados.periodo.ultimo_dia
    leitura = dados.dias_do_mes()
    periodo = set(dados.periodo.dias)
    corpo = _grafico(ID_DOS_DIAS, leitura, lambda dias: figura_dos_dias(dias, ancora, tema, periodo), f"A AWS não contou gasto nenhum em {_mes(ancora)}.")
    destaque = data_curta(ancora) if len(periodo) == 1 else "o período escolhido"
    return quadro(f"Gasto por dia em {_mes(ancora)}", corpo, [leitura], dados.agora, lateral=f"{destaque} em destaque; clique num dia para ver só ele")


def _quadro_dos_meses(dados: LeiturasDaAplicacao, tema: str | None) -> html.Section:
    ancora = dados.periodo.ultimo_dia
    leitura = dados.doze_meses()
    meses_do_periodo = {gasto.primeiro_do_mes(d) for d in dados.periodo.dias}
    corpo = _grafico(
        ID_DOS_MESES, leitura, lambda meses: figura_dos_meses(meses, ancora, tema, meses_do_periodo), "A AWS não contou gasto nenhum nos últimos 12 meses."
    )
    lateral = "clique num mês para ver o mês inteiro"
    if ancora != gasto.ultimo_do_mes(ancora):
        lateral = f"{_mes(ancora)} vai até {data_curta(ancora)}; {lateral}"
    return quadro("Gasto por mês, últimos 12 meses", corpo, [leitura], dados.agora, lateral=lateral)


# ── De onde vem o gasto ───────────────────────────────────────────────────


# O que é cada gasto, em palavras de quem lê de finanças.
O_QUE_E = {
    Parcela.LIDO: (
        "Tudo o que a Maria manda o modelo de inteligência artificial ler a cada chamada: a instrução de como responder, "
        "o que a pessoa escreveu e o que a conversa já tem. É a maior parte dos tokens."
    ),
    Parcela.ESCRITO: (
        "O que o modelo escreve de volta: o assunto escolhido, os dados tirados do relato, a pergunta reescrita. "
        "São poucos tokens, mas cada um custa 5 vezes o lido."
    ),
    Parcela.BUSCA: (
        "Transforma textos em números para achar, no catálogo dos fluxos, o mais parecido com o relato da pessoa. "
        "Roda quando o serviço da Maria sobe e na triagem."
    ),
}


def _milhoes(tokens: int) -> str:
    return f"{tokens / 1_000_000:.1f}".replace(".", ",") + " milhões de tokens" if tokens >= 100_000 else f"{numero(tokens)} tokens"


def _precos() -> html.Ul:
    chat, embedding = PRECOS[MODELO_DE_CHAT], PRECOS[MODELO_DE_EMBEDDING]
    # Sem o nome do modelo: a tela é para quem lê de finanças, e ele fica em "De onde vem cada número".
    itens = [
        (NOME_DA_PARCELA[Parcela.LIDO], chat.entrada),
        (NOME_DA_PARCELA[Parcela.ESCRITO], chat.saida),
        (NOME_DA_PARCELA[Parcela.BUSCA], embedding.entrada),
    ]
    return html.Ul([html.Li([html.Strong(nome), f": {dinheiro(preco)} por milhão de tokens"]) for nome, preco in itens], className="lista-simples")


def _quem_chama() -> html.Ul:
    """As funções da Maria que chamam a inteligência artificial, como o código as descreve."""
    return html.Ul([html.Li([html.Strong(f.nome), f" ({f.onde}): {f.faz}"]) for f in FUNCOES], className="lista-simples")


def _origem(dados: LeiturasDaAplicacao) -> html.Section:
    periodo = dados.periodo
    leitura = dados.gasto(periodo.primeiro_dia, periodo.ultimo_dia)
    titulo, lateral = "De onde vem o gasto", descrever(periodo)
    if leitura.estado is Estado.INDISPONIVEL:
        return quadro(titulo, texto_de_falha(leitura), [leitura], dados.agora, lateral=lateral)
    if leitura.valor is None or not total(leitura.valor):
        return quadro(titulo, html.P("A AWS não contou gasto nenhum no período.", className="texto-vazio"), [leitura], dados.agora, lateral=lateral)
    p, soma = parcelas(leitura.valor), total(leitura.valor)
    tokens = {Parcela.LIDO: leitura.valor.lido, Parcela.ESCRITO: leitura.valor.escrito, Parcela.BUSCA: leitura.valor.busca}
    linhas: list[Any] = []
    for parcela, valor in p.items():
        fracao = valor / soma
        linhas.append(
            html.Tr(
                [
                    html.Th([html.Span(className=f"legenda-cor tom-{COR_DA_PARCELA[parcela]}"), NOME_DA_PARCELA[parcela]], scope="row"),
                    html.Td(
                        [O_QUE_E[parcela], html.Br(), html.Span(f"No período: {_milhoes(tokens[parcela])}.", className="tom-suave")], className="coluna-o-que-e"
                    ),
                    html.Td(dinheiro(valor), className="numero mono"),
                    html.Td(f"{round(fracao * 100)}%", className="numero mono"),
                ]
            )
        )
    linhas.append(
        html.Tr(
            [
                html.Th(NOME_DOS_SERVIDORES, scope="row"),
                html.Td(
                    [
                        "As máquinas em que a Maria roda, o banco de dados, a rede e o balanceador. Só a fatura da AWS diz quanto custam, e devem ser a maior parte. ",
                        html.Span(["Depende de ", html.Strong("Ícaro"), "."], className="reservado-dono"),
                    ],
                    className="coluna-o-que-e",
                ),
                html.Td(selo("Espera a fatura", "atencao"), className="numero"),
                html.Td(""),
            ]
        )
    )
    linhas.append(
        html.Tr(
            [html.Th("Total medido", scope="row"), html.Td(""), html.Td(html.Strong(dinheiro(soma)), className="numero mono"), html.Td("")],
            className="linha-total",
        )
    )
    tabela = html.Table(
        [
            html.Thead(
                html.Tr(
                    [
                        html.Th("Gasto"),
                        html.Th("O que é"),
                        html.Th("Valor", className="numero"),
                        html.Th("Parte", className="numero"),
                    ]
                )
            ),
            html.Tbody(linhas),
        ],
        className="tabela tabela-de-gastos",
    )
    explicacao = html.Div(
        [
            html.P("Como a AWS mede", className="rotulo-pequeno"),
            html.P(
                "A AWS conta, hora a hora, os tokens de cada modelo de inteligência artificial usado na conta. Token é um pedaço de palavra: "
                "1 milhão de tokens são cerca de 750 mil palavras. O painel multiplica pelo preço de tabela abaixo; a fatura pode sair um pouco diferente. "
                "A medição é da conta inteira: qualquer programa da conta que use os mesmos modelos entra nela (veja o quadro seguinte).",
                className="quadro-explicacao",
            ),
            html.P("Quem chama a inteligência artificial na Maria", className="rotulo-pequeno"),
            _quem_chama(),
            html.P("Preço de tabela usado", className="rotulo-pequeno"),
            _precos(),
            html.P("Ainda não conferido contra a fatura; o da busca por semelhança também não está confirmado.", className="quadro-explicacao"),
        ],
        className="miolo",
    )
    return quadro(titulo, [tabela, explicacao], [leitura], dados.agora, lateral=lateral)


# ── Quanto do gasto é da Maria ────────────────────────────────────────────

ID_DE_QUEM = "aplicacao-grafico-de-quem"
AVISOS_DE_QUEM = [
    "A parte da Maria é o que as conversas dela registram: as que terminaram e a triagem. A conversa abandonada no meio também gasta e não "
    "registra, por isso, num dia comum, sobra um pouco fora.",
    "Um defeito na contagem da Maria (issue #230) pode contar a mais; a parte da Maria nunca passa do que a conta mediu.",
    "Quem chamou o modelo fora das conversas não aparece nestes números: falta ligar o registro de chamadas da inteligência artificial ou a "
    "leitura do registro de auditoria da conta. Ver as pendências, no pé da tela.",
]


def _divididos(dados: LeiturasDaAplicacao) -> list[gasto.GastoDividido]:
    por_dia: dict[date, list[TokensRegistrados]] = {}
    for leitura in dados.registrados.values():
        for r in leitura.valor or []:
            por_dia.setdefault(r.dia, []).append(r)
    return [gasto.dividir(dados.dias[d].valor or GastoDeIA(d, 0, 0, 0), por_dia.get(d, [])) for d in dados.dias_do_registro()]


def _figura_de_quem(divididos: list[gasto.GastoDividido], periodo: set[date], tema: str | None) -> go.Figure:
    c = graficos.cores(tema)
    figura = go.Figure()
    meio_dia = [datetime.combine(g.dia, time(12), tzinfo=FUSO) for g in divididos]
    for campo, nome, cor in (
        ("maria", "conversas da Maria", "bom"),
        ("fora", "fora das conversas da Maria", "atencao"),
        ("busca", "busca por semelhança", "outro"),
    ):
        figura.add_bar(
            x=meio_dia,
            y=[getattr(g, campo) for g in divididos],
            name=nome,
            marker={"color": c[cor], "opacity": [1.0 if g.dia in periodo else 0.45 for g in divididos]},
            width=0.72 * 86_400_000,
            hovertemplate=f"%{{x|%d/%m}}, {nome}: US$ %{{y:.2f}}<extra></extra>",
        )
    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="stack",
        barcornerradius=3,
        height=240,
        separators=",.",
        xaxis={"showgrid": False, "fixedrange": True, "tickformat": "%d/%m"},
        yaxis=_eixo_y(tema),
    )
    return figura


def _de_quem(dados: LeiturasDaAplicacao, tema: str | None) -> html.Section:
    titulo = "Quanto do gasto é da Maria"
    registro = set(dados.dias_do_registro())
    periodo = [d for d in dados.periodo.dias if d in registro]
    leitura = dados.gasto(min(registro), max(registro))
    leituras: list[Leitura[Any]] = [leitura, *dados.registrados.values()]
    falha = next((x for x in leituras if x.estado is Estado.INDISPONIVEL), None)
    if falha is not None:
        return quadro(titulo, texto_de_falha(falha), leituras, dados.agora, lateral="30 dias")
    divididos = _divididos(dados)
    if not any(g.maria + g.fora + g.busca for g in divididos):
        return quadro(titulo, html.P("A AWS não contou gasto nenhum nos últimos 30 dias.", className="texto-vazio"), leituras, dados.agora, lateral="30 dias")
    no_periodo = [g for g in divididos if g.dia in periodo]
    maria, fora, busca = (sum(getattr(g, campo) for g in no_periodo) for campo in ("maria", "fora", "busca"))
    soma = maria + fora + busca
    if not periodo:
        resumo = "O período escolhido começa antes dos 30 dias que o registro da Maria guarda: o gráfico mostra os 30 dias até hoje."
    elif not soma:
        resumo = "Nenhum gasto medido no período."
    else:
        resumo = (
            f"No período, {dinheiro(maria)} ({round(maria / soma * 100)}%) vieram das conversas da Maria e {dinheiro(fora)} "
            f"({round(fora / soma * 100)}%) de fora delas, com o mesmo modelo; a busca por semelhança somou {dinheiro(busca)}."
        )
    # Os dias em que mais da metade do gasto do modelo veio de fora das conversas.
    estranhos = sorted((g for g in divididos if g.fora > 0.5 and g.fora > g.maria), key=lambda g: -g.fora)[:3]
    alerta: list[Any] = []
    if estranhos:
        dias = ", ".join(f"{data_curta(g.dia)} ({dinheiro(g.fora)} de fora)" for g in estranhos)
        alerta = [
            html.P(
                [
                    html.Strong("Gasto que não veio das conversas da Maria. "),
                    f"Nos últimos 30 dias, os dias em que a maior parte veio de fora foram: {dias}. A Maria não registrou esse uso, e os serviços dela "
                    "no ar seguiram no ritmo normal nessas horas: outro programa da conta usou o mesmo modelo, como uma rotina de teste ou outro projeto.",
                ],
                className="faixa-de-conclusao",
            )
        ]
    corpo = [
        dcc.Graph(id=ID_DE_QUEM, figure=_figura_de_quem(divididos, set(periodo), tema), config={"displayModeBar": False}, className="grafico grafico-clicavel"),
        html.Div(
            [
                html.Span([html.Span(className="legenda-cor tom-bom"), "conversas da Maria"]),
                html.Span([html.Span(className="legenda-cor tom-atencao"), "fora das conversas da Maria, mesmo modelo"]),
                html.Span([html.Span(className="legenda-cor tom-outro"), "busca por semelhança"]),
            ],
            className="legenda",
        ),
        html.P(resumo, className="quadro-explicacao miolo"),
        *alerta,
        html.Div(
            [html.P("Antes de ler", className="rotulo-pequeno"), html.Ul([html.Li(a) for a in AVISOS_DE_QUEM], className="lista-simples")], className="miolo"
        ),
    ]
    return quadro(titulo, corpo, leituras, dados.agora, lateral="30 dias, o período em destaque; clique num dia")


# ── Qual atendimento custa mais ───────────────────────────────────────────

AVISOS_DO_ASSUNTO = [
    "Só entram atendimentos que terminaram. A conversa abandonada no meio também gasta, e não aparece aqui.",
    "Um defeito na contagem (issue #230 na Maria) faz alguns caminhos contarem até 6 vezes o gasto real. A comparação entre assuntos pode estar distorcida até a correção.",
    "A triagem por escrita livre registra só o total, sem separar texto lido de texto escrito. O custo dela fica de fora até a issue #340 na Maria.",
]


def _linha_do_assunto(assunto: Assunto, gasto_do_assunto: GastoDoAssunto | None) -> html.Tr:
    nome = html.Th(NOME_DO_ASSUNTO[assunto], scope="row")
    if gasto_do_assunto is None or not gasto_do_assunto.atendimentos:
        return html.Tr([nome, html.Td(html.Span("nenhum no período", className="texto-vazio"), colSpan=3)])
    a = gasto_do_assunto
    if assunto is Assunto.TRIAGEM:
        return html.Tr(
            [
                nome,
                html.Td(numero(a.atendimentos), className="numero mono"),
                html.Td(selo("A medir", "atencao"), className="numero"),
                html.Td(html.Span("só o total é registrado", className="texto-vazio"), className="numero"),
            ]
        )
    valor = custo_do_assunto(a)
    return html.Tr(
        [
            nome,
            html.Td(numero(a.atendimentos), className="numero mono"),
            html.Td(dinheiro(valor), className="numero mono"),
            html.Td(dinheiro(valor / a.atendimentos, casas=4), className="numero mono"),
        ]
    )


def _assuntos(dados: LeiturasDaAplicacao) -> tuple[Any, Any]:
    """O corpo e o pé do quadro. O título e o filtro de ambiente ficam fora, para
    o filtro não voltar ao padrão a cada minuto."""
    hoje = dados.agora.astimezone(FUSO).date()
    leitura = dados.assuntos
    if leitura is None:
        primeiro = hoje - timedelta(days=DIAS_DO_REGISTRO - 1)
        corpo: Any = html.P(
            f"O registro da aplicação guarda {DIAS_DO_REGISTRO} dias. Para ver os assuntos, escolha um dia a partir de {data_curta(primeiro)}.",
            className="texto-vazio",
        )
        pe = html.P(f"{REGISTRO_DO[dados.ambiente]}, não lido neste período", className="fonte-curta")
        return corpo, pe
    avisos = html.Ul([html.Li(a) for a in AVISOS_DO_ASSUNTO], className="lista-simples")
    if leitura.estado is Estado.INDISPONIVEL:
        corpo = [texto_de_falha(leitura), html.Div(avisos, className="miolo")]
    elif not leitura.valor or not any(a.atendimentos for a in leitura.valor):
        corpo = [html.P("Nenhum atendimento terminou neste ambiente no período.", className="texto-vazio"), html.Div(avisos, className="miolo")]
    else:
        por_assunto = {a.assunto: a for a in leitura.valor}
        tabela = html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Assunto"),
                            html.Th("Atendimentos", className="numero"),
                            html.Th("Gasto", className="numero"),
                            html.Th("Por atendimento", className="numero"),
                        ]
                    )
                ),
                html.Tbody([_linha_do_assunto(a, por_assunto.get(a)) for a in Assunto]),
            ],
            className="tabela",
        )
        corpo = [tabela, html.Div([html.P("Antes de comparar", className="rotulo-pequeno"), avisos], className="miolo")]
    return corpo, nota_de_fonte([leitura], dados.agora)


def _quadro_dos_assuntos(dados: LeiturasDaAplicacao) -> html.Section:
    corpo, pe = _assuntos(dados)
    return html.Section(
        [
            html.Header(
                [html.H2("Qual atendimento custa mais"), html.Div(filtro_de_ambiente(ID_DO_AMBIENTE, dados.ambiente), className="quadro-lateral")],
                className="quadro-topo",
            ),
            html.Div(corpo, id="aplicacao-assunto-corpo", className="quadro-corpo"),
            html.Footer(pe, id="aplicacao-assunto-pe", className="quadro-pe"),
        ],
        className="quadro",
    )


# ── Atendimento humano ────────────────────────────────────────────────────

ID_DO_HUMANO = "aplicacao-grafico-humano"
DESTINOS = {
    Destino.IA: ("resolvidos pela Maria", "bom"),
    Destino.HUMANO: ("foram para atendimento humano", "azul"),
    Destino.SAIU: ("a pessoa saiu ou a conversa expirou", "outro"),
}


def _parte(parte: int, todo: int) -> str:
    return f"{round(parte / todo * 100)}%" if todo else "0%"


def _no_periodo(dados: LeiturasDaAplicacao) -> list[EncaminhamentoNoDia]:
    dias = set(dados.periodo.dias)
    return [e for e in dados.encaminhamentos.valor or [] if e.dia in dias]


def _indicadores_do_humano(dados: LeiturasDaAplicacao, encerrados: list[EncaminhamentoNoDia]) -> html.Div:
    leituras, agora = [dados.encaminhamentos], dados.agora
    por_destino = Counter[Destino]()
    for e in encerrados:
        por_destino[e.destino] += e.atendimentos
    total, humano = sum(por_destino.values()), por_destino[Destino.HUMANO]
    falhas = sum(e.atendimentos for e in encerrados if e.destino is Destino.HUMANO and tipo_do_motivo(e.motivo) is TipoDeProblema.FALHA)
    dias_com_registro = len({e.dia for e in encerrados}) or 1
    vazio = "Nenhum atendimento terminou no período."
    return html.Div(
        [
            indicador(
                "Atendimentos que terminaram",
                "conversa",
                leituras,
                lambda: Valor(numero(total), legenda=f"{numero(round(total / dias_com_registro))} por dia, em média"),
                vazio,
                agora,
            ),
            indicador(
                "Resolvidos pela Maria",
                "ia",
                leituras,
                lambda: Valor(numero(por_destino[Destino.IA]), legenda=f"{_parte(por_destino[Destino.IA], total)} sem precisar de pessoa"),
                vazio,
                agora,
            ),
            indicador(
                "Foram para atendimento humano",
                "encaminhar",
                leituras,
                lambda: Valor(
                    numero(humano),
                    legenda=f"{_parte(humano, total)} dos que terminaram; em {numero(por_destino[Destino.SAIU])}, a pessoa saiu",
                ),
                vazio,
                agora,
            ),
            indicador(
                "Por falha técnica",
                "alerta",
                leituras,
                lambda: Valor(
                    numero(falhas),
                    "ruim" if falhas else "bom",
                    legenda=f"{_parte(falhas, humano)} dos encaminhados; o resto foi por regra ou pelos dados da pessoa",
                ),
                vazio,
                agora,
            ),
        ],
        className="grade-indicadores grade-quatro",
    )


def _custo_por_atendimento(dados: LeiturasDaAplicacao, encerrados: list[EncaminhamentoNoDia]) -> html.Section:
    """O gasto de inteligência artificial que as conversas registraram, dividido por
    atendimento: quanto custa cada um, cada um que a Maria resolveu sozinha, e quanto
    foi gasto, pela média, nos que acabaram com uma pessoa."""
    titulo = "Quanto custa cada atendimento"
    leitura = dados.assuntos
    if leitura is None or leitura.estado is not Estado.OK or not leitura.valor:
        vazio = "Os gastos por atendimento só existem nos 30 dias que o registro guarda." if leitura is None else "Nenhum atendimento terminou no período."
        corpo: Any = texto_de_falha(leitura) if leitura is not None and leitura.estado is Estado.INDISPONIVEL else html.P(vazio, className="texto-vazio")
        return quadro(titulo, corpo, [x for x in (leitura, dados.encaminhamentos) if x is not None], dados.agora)
    conversas = [a for a in leitura.valor if a.assunto is not Assunto.TRIAGEM]
    gasto_total = sum(custo_do_assunto(a) for a in conversas)
    atendimentos = sum(a.atendimentos for a in conversas)
    por_destino = Counter[Destino]()
    for e in encerrados:
        por_destino[e.destino] += e.atendimentos
    resolvidos, com_pessoa = por_destino[Destino.IA], por_destino[Destino.HUMANO]
    medio = gasto_total / atendimentos if atendimentos else 0.0
    colunas = [
        ("Por atendimento", dinheiro(medio, casas=4), f"{dinheiro(gasto_total)} em {numero(atendimentos)} atendimentos que terminaram"),
        (
            "Por atendimento resolvido pela Maria",
            dinheiro(gasto_total / resolvidos, casas=4) if resolvidos else "nenhum resolvido",
            f"todo o gasto dividido pelos {numero(resolvidos)} que não precisaram de pessoa",
        ),
        (
            "Nos que foram para pessoa",
            dinheiro(medio * com_pessoa),
            f"pela média, nos {numero(com_pessoa)} encaminhados: gasto que não evitou o atendimento humano",
        ),
    ]
    trio = html.Div(
        [
            html.Div([html.P(rotulo, className="coluna-rotulo"), html.P(valor, className="numero-medio"), html.P(legenda, className="indicador-legenda")])
            for rotulo, valor, legenda in colunas
        ],
        className="trio miolo",
    )
    explicacao = html.P(
        "Conta só o que as conversas registraram, sem a triagem por escrita livre (que ainda registra só o total) e sem o gasto de fora das "
        "conversas. Para dizer quanto a Maria economiza, falta saber quanto custa um atendimento feito por uma pessoa da equipe.",
        className="quadro-explicacao miolo",
    )
    return quadro(titulo, [trio, explicacao], [leitura, dados.encaminhamentos], dados.agora, lateral=f"{NOME_DO_AMBIENTE[dados.ambiente].lower()}, no período")


def _figura_do_humano(dados: LeiturasDaAplicacao, tema: str | None) -> go.Figure:
    """Os 30 dias, empilhados por destino, com o período em destaque. O clique num dia escolhe a data."""
    c = graficos.cores(tema)
    dias, periodo = dados.dias_do_registro(), set(dados.periodo.dias)
    por_dia: dict[tuple[date, Destino], int] = {}
    for e in dados.encaminhamentos.valor or []:
        por_dia[(e.dia, e.destino)] = por_dia.get((e.dia, e.destino), 0) + e.atendimentos
    figura = go.Figure()
    meio_dia = [datetime.combine(d, time(12), tzinfo=FUSO) for d in dias]
    for destino, (nome, cor) in DESTINOS.items():
        figura.add_bar(
            x=meio_dia,
            y=[por_dia.get((d, destino), 0) for d in dias],
            name=nome,
            marker={"color": c[cor], "opacity": [1.0 if d in periodo else 0.45 for d in dias]},
            width=0.72 * 86_400_000,
            hovertemplate=f"%{{x|%d/%m}}: %{{y}} {nome}<extra></extra>",
        )
    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="stack",
        barcornerradius=3,
        height=240,
        separators=",.",
        xaxis={"showgrid": False, "fixedrange": True, "tickformat": "%d/%m"},
        yaxis={"showgrid": True, "gridcolor": c["grade"], "fixedrange": True, "rangemode": "tozero"},
    )
    return figura


def _figura_dos_motivos(por_motivo: Counter[str], tema: str | None) -> go.Figure:
    c = graficos.cores(tema)
    ordem = sorted(por_motivo, key=lambda m: por_motivo[m])
    figura = go.Figure(
        go.Bar(
            x=[por_motivo[m] for m in ordem],
            y=[nome_do_desfecho(m) for m in ordem],
            orientation="h",
            marker={"color": [c[TIPOS_DE_PROBLEMA[tipo_do_motivo(m)][1]] for m in ordem]},
            customdata=[TIPOS_DE_PROBLEMA[tipo_do_motivo(m)][0] for m in ordem],
            hovertemplate="%{y}: %{x} atendimentos<br>%{customdata}<extra></extra>",
        )
    )
    figura.update_layout(**graficos.layout_base(tema), height=60 + 30 * len(ordem), separators=",.")
    figura.update_layout(margin={"l": 0, "r": 8, "t": 8, "b": 0}, showlegend=False)
    figura.update_xaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero")
    figura.update_yaxes(showgrid=False, fixedrange=True, automargin=True)
    return figura


def _tipos_de_problema(por_motivo: Counter[str]) -> html.Table:
    humano = sum(por_motivo.values())
    por_tipo: dict[TipoDeProblema, list[str]] = {}
    for motivo in sorted(por_motivo, key=lambda m: -por_motivo[m]):
        por_tipo.setdefault(tipo_do_motivo(motivo), []).append(motivo)
    linhas = []
    for tipo, (nome, cor, explicacao) in TIPOS_DE_PROBLEMA.items():
        motivos = por_tipo.get(tipo, [])
        n = sum(por_motivo[m] for m in motivos)
        if not n:
            continue
        principais = "; ".join(f"{nome_do_desfecho(m)} ({numero(por_motivo[m])})" for m in motivos[:3])
        linhas.append(
            html.Tr(
                [
                    html.Th(
                        [
                            html.P([html.Span(className=f"legenda-cor tom-{cor}"), nome], className="tipo-de-problema"),
                            html.P(explicacao, className="tipo-de-problema-explicacao"),
                            html.P(f"Mais comuns: {principais}.", className="tipo-de-problema-explicacao"),
                        ],
                        scope="row",
                        className="com-explicacao",
                    ),
                    html.Td(numero(n), className="numero mono"),
                    html.Td(_parte(n, humano), className="numero mono"),
                ]
            )
        )
    return html.Table(
        [
            html.Thead(html.Tr([html.Th("Tipo de problema"), html.Th("Atendimentos", className="numero"), html.Th("Parte", className="numero")])),
            html.Tbody(linhas),
        ],
        className="tabela",
    )


def _por_fluxo(encerrados: list[EncaminhamentoNoDia]) -> html.Table:
    por_fluxo: dict[str, Counter[Destino]] = {}
    motivos: dict[str, Counter[str]] = {}
    for e in encerrados:
        por_fluxo.setdefault(e.fluxo, Counter())[e.destino] += e.atendimentos
        if e.destino is Destino.HUMANO:
            motivos.setdefault(e.fluxo, Counter())[e.motivo] += e.atendimentos
    linhas = []
    for fluxo in sorted(por_fluxo, key=lambda f: -sum(por_fluxo[f].values())):
        d = por_fluxo[fluxo]
        total = sum(d.values())
        comum = motivos.get(fluxo, Counter()).most_common(1)
        linhas.append(
            html.Tr(
                [
                    html.Th(nome_do_fluxo(fluxo) if fluxo else "Triagem, antes de um fluxo", scope="row"),
                    html.Td(numero(total), className="numero mono"),
                    html.Td(numero(d[Destino.IA]), className="numero mono"),
                    html.Td(numero(d[Destino.HUMANO]), className="numero mono"),
                    html.Td(_parte(d[Destino.HUMANO], total), className="numero mono"),
                    html.Td(nome_do_desfecho(comum[0][0]) if comum else "nenhum encaminhado"),
                ]
            )
        )
    cabeca = ["Fluxo", "Terminaram", "Pela Maria", "Atendimento humano", "Parte humana", "Motivo mais comum"]
    return html.Table(
        [html.Thead(html.Tr([html.Th(t, className="numero" if 0 < i < 5 else None) for i, t in enumerate(cabeca)])), html.Tbody(linhas)],
        className="tabela",
    )


def _humano(dados: LeiturasDaAplicacao, tema: str | None) -> list[Any]:
    """IA e atendimento humano no período: quantos, em que dia, por que motivo e com que problema.
    O ambiente é o do filtro em "Qual atendimento custa mais", logo acima."""
    leitura, agora = dados.encaminhamentos, dados.agora
    leituras: list[Leitura[Any]] = [leitura]
    ambiente = NOME_DO_AMBIENTE[dados.ambiente].lower()
    titulo = "IA e atendimento humano, dia a dia"
    if leitura.estado is Estado.INDISPONIVEL:
        return [quadro(titulo, texto_de_falha(leitura), leituras, agora, lateral=ambiente)]
    encerrados = _no_periodo(dados)
    if not set(dados.periodo.dias) & set(dados.dias_do_registro()):
        aviso = f"O registro da aplicação guarda {DIAS_DO_REGISTRO} dias. Para ver o atendimento humano, escolha um período a partir de {data_curta(dados.dias_do_registro()[0])}."
        return [quadro(titulo, html.P(aviso, className="texto-vazio"), leituras, agora, lateral=ambiente)]
    por_motivo = Counter[str]()
    for e in encerrados:
        if e.destino is Destino.HUMANO:
            por_motivo[e.motivo] += e.atendimentos
    legenda = html.Div([html.Span([html.Span(className=f"legenda-cor tom-{cor}"), nome]) for nome, cor in DESTINOS.values()], className="legenda")
    dia_a_dia = quadro(
        titulo,
        [
            dcc.Graph(id=ID_DO_HUMANO, figure=_figura_do_humano(dados, tema), config={"displayModeBar": False}, className="grafico grafico-clicavel"),
            legenda,
        ],
        leituras,
        agora,
        lateral=f"{ambiente}; 30 dias, o período em destaque; clique num dia",
    )
    if por_motivo:
        motivos: Any = dcc.Graph(figure=_figura_dos_motivos(por_motivo, tema), config={"displayModeBar": False}, className="grafico")
        tipos: Any = _tipos_de_problema(por_motivo)
    else:
        motivos = tipos = html.P("Nenhum atendimento foi para pessoa no período.", className="texto-vazio")
    return [
        _indicadores_do_humano(dados, encerrados),
        _custo_por_atendimento(dados, encerrados),
        dia_a_dia,
        html.Div(
            [
                html.Div(quadro("Por que foi para atendimento humano", motivos, leituras, agora, lateral="no período, a cor é o tipo de problema")),
                html.Div(quadro("Que problema levou ao atendimento humano", tipos, leituras, agora, lateral="no período")),
            ],
            className="grade-dupla",
        ),
        quadro(
            "Em cada fluxo",
            _por_fluxo(encerrados) if encerrados else html.P("Nenhum atendimento terminou no período.", className="texto-vazio"),
            leituras,
            agora,
            lateral=f"{ambiente}, no período",
        ),
    ]


# ── O que ainda não dá para medir ─────────────────────────────────────────

PENDENCIAS = reservado(
    "O que ainda não dá para medir",
    [
        Pendencia(
            "A fatura e os servidores",
            "O valor real, com servidores, rede, balanceador e armazenamento, está na fatura da AWS. O painel precisa de permissão "
            "para ler o custo, ou de uma exportação mensal do faturamento.",
            "Ícaro",
        ),
        Pendencia(
            "Separar a Maria dos outros projetos",
            "A conta da AWS também roda outros projetos da Defensoria. Os recursos da Maria já têm etiqueta; falta ativar essa etiqueta no faturamento.",
            "Ícaro",
        ),
        Pendencia(
            "Saber quem chama o modelo de fora da Maria",
            "Em 27 e 28/10, quase todo o gasto de inteligência artificial medido não veio das conversas da Maria, e os serviços dela seguiram no "
            "ritmo normal. Para saber quem chamou, falta ligar o registro de chamadas da inteligência artificial na AWS, ou dar ao painel a leitura "
            "do registro de auditoria. O jeito de separar de vez é a Maria usar um perfil de inferência próprio: a medição dela fica só dela.",
            "Ícaro",
        ),
        Pendencia(
            "Separar produção do release",
            "Hoje a medição da inteligência artificial soma os dois ambientes. Separar exige uma mudança na infraestrutura da Maria, com janela.",
            "Ícaro e Nicole",
        ),
        Pendencia(
            "Dividir o que é compartilhado",
            "Parte da rede e do banco de dados vem de um sistema antigo, usado por mais de um projeto. Falta a regra de rateio.",
            "Nicole",
        ),
        Pendencia(
            "Custos fora da AWS",
            "Ferramentas de acompanhamento, a automação do GitHub, o contrato com a Tykhe e, se entrar, horas de equipe.",
            "Nicole",
        ),
        Pendencia(
            "Valor em reais",
            "Saber se a fatura vem em dólar ou da AWS Brasil, em reais e com impostos. Em dólar, a cotação PTAX do Banco Central é fonte gratuita e conferível.",
            "Nicole",
        ),
    ],
    ["levantamento de custos de 26/10, ", html.Code("relatorio-aplicacao-custos.md")],
)

LIMITES = html.Div(
    [
        html.P(
            "A inteligência artificial medida é da conta inteira da AWS. A busca por semelhança pode incluir outros projetos da conta.",
            className="nota-do-pe",
        ),
        html.P(
            "Os gastos se refazem a cada minuto. Dia e mês que já fecharam são lidos uma vez e guardados; só o período em curso é lido de novo.",
            className="nota-do-pe",
        ),
    ]
)


# ── Montagem ──────────────────────────────────────────────────────────────


def _antes(dados: LeiturasDaAplicacao, tema: str | None) -> list[Any]:
    return [_indicadores(dados), _origem(dados), _de_quem(dados, tema), _quadro_dos_dias(dados, tema), _quadro_dos_meses(dados, tema)]


def _depois(dados: LeiturasDaAplicacao) -> list[Any]:
    return [PENDENCIAS, LIMITES, lista_de_fontes(dados.todas(), dados.agora)]


def _ler(escolha: str | None, data: str | None, ambiente: str | None, mes: str | None = None) -> LeiturasDaAplicacao:
    periodo: Periodo = montar_periodo(escolha, data, datetime.now(FUSO), mes)
    return ler_aplicacao(periodo, Ambiente(ambiente or Ambiente.PRODUCAO))


def layout(**_: str) -> html.Div:
    dados = _ler(None, None, None)
    tela = html.Div(
        [
            cabecalho(
                "Relatório da Aplicação",
                "De onde vem o gasto, em que dia e em que mês?",
                filtro=filtro_de_periodo(ID_DO_PERIODO, dados.agora),
            ),
            html.Div(_antes(dados, None), id="aplicacao-antes", className="tela-corpo"),
            _quadro_dos_assuntos(dados),
            html.Div(_humano(dados, None), id="aplicacao-humano", className="tela-corpo"),
            html.Div(_depois(dados), id="aplicacao-depois", className="tela-corpo"),
        ],
        className="tela",
    )
    return com_lateral(tela, coluna("aplicacao-lateral", lateral.da_aplicacao(dados, None)))


# Sem prevent_initial_call: na subida, escreve o período e aplica o tema guardado.
@callback(
    Output(f"{ID_DO_PERIODO}-texto", "children"),
    Output(f"{ID_DO_PERIODO}-caixa-da-data", "hidden"),
    Output(f"{ID_DO_PERIODO}-caixa-do-mes", "hidden"),
    Output("aplicacao-antes", "children"),
    Output("aplicacao-assunto-corpo", "children"),
    Output("aplicacao-assunto-pe", "children"),
    Output("aplicacao-humano", "children"),
    Output("aplicacao-depois", "children"),
    Output("aplicacao-lateral", "children"),
    Input("relogio", "n_intervals"),
    Input(ID_DO_PERIODO, "value"),
    Input(f"{ID_DO_PERIODO}-data", "value"),
    Input(f"{ID_DO_PERIODO}-mes", "value"),
    Input(ID_DO_AMBIENTE, "value"),
    Input("tema", "data"),
)
def atualizar(_: int | None, escolha: str | None, data: str | None, mes: str | None, ambiente: str | None, tema: str | None) -> tuple[Any, ...]:
    dados = _ler(escolha, data, ambiente, mes)
    corpo, pe = _assuntos(dados)
    return (
        descrever(dados.periodo),
        escolha != "data",
        escolha != "mes",
        _antes(dados, tema),
        corpo,
        pe,
        _humano(dados, tema),
        _depois(dados),
        lateral.da_aplicacao(dados, tema),
    )


# O clique numa barra muda o filtro, e o filtro refaz todos os números da tela:
# um dia leva à data específica; um mês, ao mês inteiro.
@callback(
    Output(ID_DO_PERIODO, "value"),
    Output(f"{ID_DO_PERIODO}-data", "value"),
    Output(f"{ID_DO_PERIODO}-mes", "value"),
    Input(ID_DOS_DIAS, "clickData"),
    Input(ID_DOS_MESES, "clickData"),
    # O texto escrito por chamada, na coluna da direita, e quanto é da Maria: um dia, como no gráfico por dia.
    Input(lateral.ID_DOS_ESCRITOS, "clickData"),
    Input(ID_DE_QUEM, "clickData"),
    Input(ID_DO_HUMANO, "clickData"),
    prevent_initial_call=True,
)
def escolher_no_grafico(
    dia: dict[str, Any] | None,
    mes: dict[str, Any] | None,
    escritos: dict[str, Any] | None,
    de_quem: dict[str, Any] | None = None,
    humano: dict[str, Any] | None = None,
) -> tuple[Any, Any, Any]:
    gatilho = dash.ctx.triggered_id
    clique = {ID_DOS_DIAS: dia, ID_DOS_MESES: mes, lateral.ID_DOS_ESCRITOS: escritos, ID_DE_QUEM: de_quem, ID_DO_HUMANO: humano}.get(gatilho)
    # O Plotly devolve a posição da barra no eixo: "2026-10-22 12:00" num dia, "2026-09" num mês.
    pontos = (clique or {}).get("points") or []
    if not pontos or not isinstance(pontos[0].get("x"), str):
        raise PreventUpdate
    escolhido = pontos[0]["x"]
    if gatilho != ID_DOS_MESES:
        return Escolha.DATA.value, escolhido[:10], dash.no_update
    return Escolha.MES.value, dash.no_update, escolhido[:7]
