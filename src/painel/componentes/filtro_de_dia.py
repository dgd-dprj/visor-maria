"""O filtro das telas: o clique num gráfico refaz a tela inteira no que foi clicado.

Como no Power BI, todo gráfico filtra a tela, sem mexer nos outros filtros dela
(ambiente, origem). O filtro tem três partes, e cada gráfico escolhe a sua:

- o dia: uma barra de um gráfico por dia (`por="dia"`);
- a hora: uma barra de um gráfico hora a hora (`por="hora"`), dentro do dia;
- a categoria (`serie`): o resultado do Verde (aceitou, recusou, outro), por um
  segmento da barra ou pela legenda, ou o motivo de "Como terminaram"
  (`por="categoria"`).

Clicar de novo no mesmo ponto desfaz a parte que ele escolheu; "Tirar o filtro"
desfaz tudo. O filtro fica num `dcc.Store` da tela (`armazem`), e cada callback
que refaz um quadro o recebe como entrada (`entrada`). Um link com
`?dia=2026-10-22` abre a tela já filtrada no dia.

As consultas recebem `quando`: o dia, ou o começo da hora escolhida (um
`datetime`), e leem só esse trecho. O que não tem dia (a saúde do serviço agora,
a validade da credencial) continua sendo de agora, e a faixa no topo da tela
diz quais quadros são esses.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from typing import Any

import dash
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, dcc, html
from dash.exceptions import PreventUpdate

from painel.componentes import graficos
from painel.componentes.blocos import Valor, indicador
from painel.componentes.formato import dia_da_semana_e_data, numero
from painel.dados.fontes import DIAS_DO_REGISTRO
from painel.dados.modelo import FUSO, NOME_DO_PROBLEMA, RESULTADOS_DO_VERDE, Desfecho, Leitura, nome_do_desfecho, nome_do_fluxo

GRAFICO = "grafico-de-dia"
ARMAZEM = "dia-escolhido"
FAIXA = "faixa-do-filtro"
LIMPAR = "tirar-o-filtro"
LEGENDA = "legenda-do-filtro"
APAGADO = 0.3

# Os resultados do Verde, na ordem das séries dos gráficos do Verde.
SERIES_DO_VERDE = tuple(campo for campo, _, _, _ in RESULTADOS_DO_VERDE)
NOME_DA_SERIE = {campo: nome for campo, nome, _, _ in RESULTADOS_DO_VERDE}
# As categorias com código: o motivo de "Como terminaram", o fluxo e o tipo de problema (tela Fluxos).
MOTIVO = "motivo:"
FLUXO = "fluxo:"
PROBLEMA = "problema:"

# O que o filtro muda em cada tela, e o que continua sendo de agora (`registrar`).
_TEXTOS: dict[str, tuple[str, str | None]] = {}


def registrar(tela: str, filtrado: str, de_agora: str | None = None) -> None:
    _TEXTOS[tela] = (filtrado, de_agora)


@dataclass(frozen=True)
class Filtro:
    dia: date | None = None
    hora: int | None = None
    serie: str | None = None

    @property
    def quando(self) -> date | None:
        """O que as consultas recebem: o dia, o começo da hora escolhida, ou nada."""
        if self.dia is None:
            return None
        if self.hora is None:
            return self.dia
        return datetime.combine(self.dia, time(self.hora), tzinfo=FUSO)

    @property
    def motivo(self) -> str | None:
        """O motivo de "Como terminaram", se é ele a categoria escolhida."""
        return self.serie[len(MOTIVO) :] if self.serie and self.serie.startswith(MOTIVO) else None

    @property
    def resultado_do_verde(self) -> str | None:
        return self.serie if self.serie in SERIES_DO_VERDE else None

    @property
    def fluxo(self) -> str | None:
        """O fluxo escolhido num gráfico da tela Fluxos."""
        return self.serie[len(FLUXO) :] if self.serie and self.serie.startswith(FLUXO) else None

    @property
    def problema(self) -> str | None:
        """O tipo de problema escolhido (chave de NOME_DO_PROBLEMA)."""
        return self.serie[len(PROBLEMA) :] if self.serie and self.serie.startswith(PROBLEMA) else None

    def guardar(self) -> dict[str, Any] | None:
        if self == Filtro():
            return None
        return {"dia": self.dia.isoformat() if self.dia else None, "hora": self.hora, "serie": self.serie}


def ler(texto: str | None, agora: datetime) -> date | None:
    """O dia de um texto ("2026-10-22", "2026-10-22 12:00"). Fora dos 30 dias de
    registro, no futuro ou inválido, nenhum: a tela volta à janela padrão."""
    try:
        dia = date.fromisoformat((texto or "")[:10])
    except ValueError:
        return None
    hoje = agora.astimezone(FUSO).date()
    return dia if hoje - timedelta(days=DIAS_DO_REGISTRO - 1) <= dia <= hoje else None


def filtro(guardado: Any) -> Filtro:
    """O filtro guardado no `armazem`, para os callbacks da tela."""
    if not isinstance(guardado, dict):
        return Filtro()
    dia = ler(guardado.get("dia"), datetime.now(FUSO))
    hora = guardado.get("hora")
    serie = guardado.get("serie")
    return Filtro(dia, hora if dia is not None and isinstance(hora, int) and 0 <= hora < 24 else None, serie if isinstance(serie, str) else None)


def escolhido(guardado: Any) -> date | None:
    """O `quando` do filtro guardado: o dia, o começo da hora escolhida, ou nada."""
    return filtro(guardado).quando


def dia_de(quando: date | None) -> date | None:
    """O dia de um `quando`, que pode ser o começo de uma hora."""
    return quando.astimezone(FUSO).date() if isinstance(quando, datetime) else quando


def rotulo(quando: date) -> str:
    """ "25/10", ou "25/10, das 14h às 15h" com a hora escolhida."""
    if isinstance(quando, datetime):
        local = quando.astimezone(FUSO)
        return f"{local:%d/%m}, das {local.hour}h às {local.hour + 1}h"
    return f"{quando:%d/%m}"


def nome_da_serie(serie: str) -> str:
    if serie.startswith(MOTIVO):
        return nome_do_desfecho(serie[len(MOTIVO) :])
    if serie.startswith(FLUXO):
        return f"fluxo {nome_do_fluxo(serie[len(FLUXO) :])}"
    if serie.startswith(PROBLEMA):
        return NOME_DO_PROBLEMA.get(serie[len(PROBLEMA) :], serie[len(PROBLEMA) :])
    return NOME_DA_SERIE.get(serie, serie)


def armazem(tela: str, inicial: Filtro | date | None) -> dcc.Store:
    f = inicial if isinstance(inicial, Filtro) else Filtro(inicial)
    return dcc.Store(id={"tipo": ARMAZEM, "tela": tela}, data=f.guardar())


def entrada(tela: str) -> Input:
    """O filtro escolhido, como entrada de um callback da tela."""
    return Input({"tipo": ARMAZEM, "tela": tela}, "data")


def grafico(tela: str, nome: str, figura: go.Figure, classe: str = "grafico", por: str = "dia", series: tuple[str, ...] = ()) -> dcc.Graph:
    """Um gráfico em que o clique filtra a tela. `por` diz o que o clique escolhe
    ("dia", "hora" ou "categoria"); `series`, a categoria de cada série, na ordem."""
    return dcc.Graph(
        id={"tipo": GRAFICO, "tela": tela, "nome": nome, "por": por, "series": "|".join(series)},
        figure=figura,
        config={"displayModeBar": False},
        className=f"{classe} grafico-clicavel",
    )


def legenda(tela: str, itens: list[tuple[str, str, str]], escolhida: str | None) -> html.Div:
    """Uma legenda em que cada item filtra a categoria: (série, tom, texto)."""
    return html.Div(
        [
            html.Button(
                [html.Span(className=f"legenda-cor tom-{tom}"), texto],
                id={"tipo": LEGENDA, "tela": tela, "serie": serie},
                n_clicks=0,
                className="legenda-item" + (" legenda-escolhida" if serie == escolhida else " legenda-apagada" if escolhida else ""),
                title="Clique para filtrar a tela por este resultado",
            )
            for serie, tom, texto in itens
        ],
        className="legenda legenda-clicavel",
    )


# ── O destaque nos gráficos ───────────────────────────────────────────────


def _dia_do_ponto(x: Any) -> date | None:
    if isinstance(x, datetime):
        return x.astimezone(FUSO).date()
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(str(x)[:10])
    except ValueError:
        return None


def _hora_do_ponto(x: Any) -> datetime | None:
    if isinstance(x, datetime):
        return x.astimezone(FUSO).replace(minute=0, second=0, microsecond=0)
    try:
        momento = datetime.fromisoformat(str(x))
    except ValueError:
        return None
    momento = momento if momento.tzinfo else momento.replace(tzinfo=FUSO)
    return momento.astimezone(FUSO).replace(minute=0, second=0, microsecond=0)


def destacar(figura: go.Figure, escolha: Filtro | date | None, tema: str | None, series: tuple[str, ...] = ()) -> go.Figure:
    """Num gráfico por dia: as barras dos outros dias apagadas e uma faixa sobre o
    dia; com uma categoria de `series` escolhida, as outras séries apagadas."""
    f = escolha if isinstance(escolha, Filtro) else Filtro(dia_de(escolha))
    serie = f.serie if f.serie in series else None
    if f.dia is None and serie is None:
        return figura
    for n, trace in enumerate(figura.data):
        if trace.type != "bar" or trace.x is None:
            continue
        outra_serie = serie is not None and n < len(series) and series[n] != serie
        trace.marker.opacity = [APAGADO if outra_serie or (f.dia is not None and _dia_do_ponto(x) != f.dia) else 1.0 for x in trace.x]
    if f.dia is not None:
        inicio = datetime.combine(f.dia, time(), tzinfo=FUSO)
        figura.add_vrect(x0=inicio, x1=inicio + timedelta(days=1), fillcolor=graficos.cores(tema)["suave"], opacity=0.18, layer="below", line_width=0)
    return figura


def destacar_hora(figura: go.Figure, escolha: Filtro) -> go.Figure:
    """Num gráfico hora a hora: as barras das outras horas apagadas. Cada barra
    diz a hora dela no `customdata` (texto) ou no próprio x (data e hora)."""
    escolhida = escolha.quando if isinstance(escolha.quando, datetime) else None
    if escolhida is None:
        return figura
    for trace in figura.data:
        if trace.type != "bar" or trace.x is None:
            continue
        chaves = trace.customdata if trace.customdata is not None and all(isinstance(c, str) for c in trace.customdata) else trace.x
        trace.marker.opacity = [1.0 if _hora_do_ponto(c) == escolhida else APAGADO for c in chaves]
    return figura


def destacar_categoria(figura: go.Figure, motivos: list[str], escolha: Filtro) -> go.Figure:
    """Num gráfico de categorias (uma barra por motivo): as outras apagadas."""
    if escolha.motivo is None:
        return figura
    for trace in figura.data:
        if trace.type == "bar":
            trace.marker.opacity = [1.0 if m == escolha.motivo else APAGADO for m in motivos]
    return figura


# ── Os números com o motivo escolhido ─────────────────────────────────────


def terminaram_no_motivo(desfechos: Leitura[list[Desfecho]], motivo: str | None, vazio: str, agora: datetime) -> html.Section | None:
    """Com um motivo escolhido em "Como terminaram", o indicador "Terminaram" conta só ele.
    Sem motivo, None: a tela mostra o indicador de sempre."""
    if motivo is None:
        return None

    def valor() -> Valor:
        todos = desfechos.valor or []
        deste = sum(d.atendimentos for d in todos if d.motivo == motivo)
        return Valor(numero(deste), legenda=f"de {numero(sum(d.atendimentos for d in todos))} que terminaram")

    return indicador(f"Terminaram: {nome_do_desfecho(motivo)}", "certo", [desfechos], valor, vazio, agora)


# ── A faixa no topo da tela ───────────────────────────────────────────────


def _conteudo(tela: str, f: Filtro) -> Any:
    if f == Filtro():
        return html.P("Clique num gráfico para ver a tela inteira no que foi clicado: um dia, uma hora ou um resultado.", className="dica-do-filtro")
    filtrado, de_agora = _TEXTOS.get(tela, ("Os quadros ligados ao que foi clicado mostram só isso.", None))
    nome = nome_da_serie(f.serie) if f.serie is not None else ""
    if f.dia is None:
        # Só a categoria: "Filtrado: O Verde falhou, e a conversa foi encaminhada."
        cabeca = f"Filtrado: {nome[:1].upper()}{nome[1:]}. "
    else:
        quando = dia_da_semana_e_data(f.dia) + (f", das {f.hora}h às {f.hora + 1}h" if f.hora is not None else "")
        # No meio da frase, só a primeira letra desce: nomes próprios ("Verde", "Pessoa presa") ficam.
        cabeca = f"Filtrado em {quando}" + (f", {nome[:1].lower()}{nome[1:]}" if nome else "") + ". "
    texto: list[Any] = [html.Strong(cabeca)]
    texto.append(filtrado if f.dia is not None else "Os gráficos e os números ligados a esse resultado mostram só ele.")
    if de_agora and f.dia is not None:
        texto += [" ", html.Span(de_agora, className="tom-suave")]
    return html.Div(
        [
            html.P(texto, className="faixa-do-filtro-texto"),
            html.Button("Tirar o filtro", id={"tipo": LIMPAR, "tela": tela}, className="faixa-do-filtro-limpar", n_clicks=0),
        ],
        className="faixa-do-filtro",
        role="status",
    )


def faixa(tela: str, inicial: Filtro | date | None) -> html.Div:
    """No topo da tela: o que foi escolhido, o que isso filtra e o que continua
    sendo de agora. Sem filtro, só a dica de que os gráficos são clicáveis."""
    f = inicial if isinstance(inicial, Filtro) else Filtro(inicial)
    return html.Div(_conteudo(tela, f), id={"tipo": FAIXA, "tela": tela})


# ── O clique ──────────────────────────────────────────────────────────────


def proximo(atual: Filtro, gatilho: dict[str, Any], valor: Any, agora: datetime) -> Filtro | None:
    """O filtro depois de um clique; None quando o clique não escolhe nada."""
    tipo = gatilho.get("tipo")
    if tipo == LIMPAR:
        return Filtro() if valor else None
    if tipo == LEGENDA:
        if not valor:
            return None
        serie = gatilho.get("serie")
        return replace(atual, serie=None if atual.serie == serie else serie)
    pontos = (valor or {}).get("points") if isinstance(valor, dict) else None
    if not pontos:
        return None
    ponto = pontos[0]
    por = gatilho.get("por", "dia")
    if por == "categoria":
        dados = ponto.get("customdata")
        codigo = dados[-1] if isinstance(dados, list) and dados else None
        if not isinstance(codigo, str):
            return None
        # O último item do customdata é a categoria: "fluxo:..." e "problema:..." vêm com o prefixo; o motivo, sem.
        serie = codigo if codigo.startswith((FLUXO, PROBLEMA, MOTIVO)) else MOTIVO + codigo
        return replace(atual, serie=None if atual.serie == serie else serie)
    if por == "hora":
        dados = ponto.get("customdata")
        hora = _hora_do_ponto(dados if isinstance(dados, str) else ponto.get("x"))
        dia = ler(hora.isoformat() if hora else None, agora)
        if hora is None or dia is None:
            return None
        if atual.dia == dia and atual.hora == hora.hour:
            return replace(atual, hora=None)
        return replace(atual, dia=dia, hora=hora.hour)
    dia = ler(str(ponto.get("x", "")), agora)
    if dia is None:
        return None
    series = [s for s in str(gatilho.get("series") or "").split("|") if s]
    curva = ponto.get("curveNumber")
    if series and isinstance(curva, int) and curva < len(series):
        # Um segmento da barra: o dia e a categoria juntos; o mesmo segmento de novo desfaz.
        escolha = Filtro(dia, None, series[curva])
        return Filtro() if atual == escolha else escolha
    if atual.dia == dia and atual.hora is None:
        return replace(atual, dia=None)
    return replace(atual, dia=dia, hora=None)


# Os callbacks valem para todas as telas: só uma está aberta por vez, e o ALL
# acha os gráficos, o armazém e a faixa dela.
@callback(
    Output({"tipo": ARMAZEM, "tela": ALL}, "data"),
    Input({"tipo": GRAFICO, "tela": ALL, "nome": ALL, "por": ALL, "series": ALL}, "clickData"),
    Input({"tipo": LEGENDA, "tela": ALL, "serie": ALL}, "n_clicks"),
    Input({"tipo": LIMPAR, "tela": ALL}, "n_clicks"),
    State({"tipo": ARMAZEM, "tela": ALL}, "data"),
    prevent_initial_call=True,
)
def escolher(_cliques: list[Any], _legendas: list[Any], _limpar: list[Any], guardados: list[Any]) -> list[Any]:
    gatilho = dash.ctx.triggered_id
    valor = dash.ctx.triggered[0].get("value") if dash.ctx.triggered else None
    if not isinstance(gatilho, dict) or not guardados:
        raise PreventUpdate
    novo = proximo(filtro(guardados[0]), dict(gatilho), valor, datetime.now(FUSO))
    if novo is None:
        # Um gráfico ou botão que acabou de entrar na tela, ou um clique fora de um ponto.
        raise PreventUpdate
    return [novo.guardar() for _ in guardados]


@callback(
    Output({"tipo": FAIXA, "tela": ALL}, "children"),
    Input({"tipo": ARMAZEM, "tela": ALL}, "data"),
    prevent_initial_call=True,
)
def mostrar(guardados: list[Any]) -> list[Any]:
    telas = [saida["id"]["tela"] for saida in dash.ctx.outputs_list]
    return [_conteudo(tela, filtro(g)) for tela, g in zip(telas, guardados, strict=True)]
