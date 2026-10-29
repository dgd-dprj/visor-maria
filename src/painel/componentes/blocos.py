"""Os blocos das telas, no desenho do rascunho: indicador, quadro, selo e ponto.

Todo bloco que mostra um número recebe as `Leitura`s de onde ele saiu, para três
regras valerem sem depender de quem escreve a tela:

- a fonte curta e a hora da leitura aparecem ao lado do número;
- o vazio tem texto próprio, nunca "sem dados";
- a fonte indisponível diz o motivo.

A lista completa, com o nome técnico de cada fonte, fica no pé da tela
(`lista_de_fontes`).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from dash import html

from painel.componentes.formato import hora_da_leitura, lista
from painel.dados.modelo import Estado, Fonte, Leitura

Tom = Literal["neutro", "bom", "atencao", "ruim", "azul", "rosa"]


def aria(**pares: str) -> dict[str, Any]:
    """Atributos aria-* para os componentes do Dash: `aria(label="Tema")` vira
    `{"aria-label": "Tema"}`. O dicionário solto não passa nos tipos do Dash."""
    return {f"aria-{nome}": valor for nome, valor in pares.items()}


def icone(nome: str) -> html.Span:
    """Ícone desenhado em CSS (máscara SVG em painel.css), na cor do texto."""
    return html.Span(className=f"icone icone-{nome}", **aria(hidden="true"))


def nota_de_fonte(leituras: Sequence[Leitura[Any]], agora: datetime) -> html.P:
    """ "logs de produção, lido às 11:58", ao lado do número."""
    # "GitHub e logs de produção" e "logs de produção" viram "GitHub e logs de produção".
    curtos = list(dict.fromkeys(parte for leitura in leituras for parte in re.split(r",\s*|\s+e\s+", leitura.fonte.curto)))
    mais_antiga = min(leituras, key=lambda leitura: leitura.lido_em)
    # O nome técnico fica só na lista do pé da tela, em código: aqui é texto lido.
    return html.P([lista(curtos), ", ", hora_da_leitura(mais_antiga.lido_em, agora)], className="fonte-curta")


def _problema(leituras: Sequence[Leitura[Any]]) -> Leitura[Any] | None:
    for estado in (Estado.INDISPONIVEL, Estado.VAZIO):
        for leitura in leituras:
            if leitura.estado is estado:
                return leitura
    return None


def texto_de_falha(leitura: Leitura[Any]) -> html.P:
    return html.P(["Não deu para ler agora. ", leitura.motivo or ""], className="texto-aviso")


@dataclass(frozen=True)
class Valor:
    texto: str
    tom: Tom = "neutro"
    unidade: str | None = None
    legenda: str | None = None
    tom_da_legenda: Tom = "neutro"
    # Frase em vez de número (o período da tela Atendimento): letra menor.
    longo: bool = False


def indicador(
    rotulo: str,
    nome_do_icone: str,
    leituras: Sequence[Leitura[Any]],
    montar: Callable[[], Valor],
    texto_vazio: str,
    agora: datetime,
) -> html.Section:
    problema = _problema(leituras)
    classe = "indicador"
    if problema is None:
        valor = montar()
        corpo: list[Any] = [
            html.P(
                [valor.texto, html.Span(valor.unidade, className="unidade") if valor.unidade else None],
                className=f"indicador-valor tom-{valor.tom}" + (" indicador-valor-texto" if valor.longo else ""),
            )
        ]
        if valor.legenda:
            corpo.append(html.P(valor.legenda, className=f"indicador-legenda tom-{valor.tom_da_legenda}"))
        if valor.tom == "ruim":
            classe += " indicador-alerta"
    elif problema.estado is Estado.INDISPONIVEL:
        corpo = [texto_de_falha(problema)]
    else:
        corpo = [html.P(texto_vazio, className="texto-vazio")]
    rotulo_da_classe = "indicador-rotulo tom-ruim" if "indicador-alerta" in classe else "indicador-rotulo"
    return html.Section(
        [html.P([icone(nome_do_icone), rotulo], className=rotulo_da_classe), *corpo, nota_de_fonte(leituras, agora)],
        className=classe,
    )


def quadro(
    titulo: str,
    corpo: Any,
    leituras: Sequence[Leitura[Any]],
    agora: datetime,
    lateral: Any = None,
    classe: str = "",
) -> html.Section:
    return html.Section(
        [
            html.Header([html.H2(titulo), html.Div(lateral, className="quadro-lateral")], className="quadro-topo"),
            html.Div(corpo, className="quadro-corpo"),
            html.Footer(nota_de_fonte(leituras, agora), className="quadro-pe"),
        ],
        className=f"quadro {classe}".strip(),
    )


def selo(texto: str, tom: Tom) -> html.Span:
    return html.Span(texto, className=f"selo tom-{tom}")


def ponto(texto: str, tom: Tom, legenda: str | None = None) -> html.Div:
    pecas: list[Any] = [html.P([html.Span(className=f"ponto tom-{tom}"), texto], className=f"ponto-texto tom-{tom}")]
    if legenda:
        pecas.append(html.P(legenda, className="ponto-legenda"))
    return html.Div(pecas)


def celula_de_leitura(leitura: Leitura[Any], montar: Callable[[Any], Any], texto_vazio: str) -> Any:
    """Uma célula de tabela: o valor, ou o texto do vazio, ou o aviso da falha."""
    if leitura.estado is Estado.OK and leitura.valor is not None:
        return montar(leitura.valor)
    if leitura.estado is Estado.INDISPONIVEL:
        return html.P("não deu para ler", className="texto-aviso", title=leitura.motivo or "")
    return html.P(texto_vazio, className="texto-vazio")


def definicoes(pares: Sequence[tuple[str, Any]]) -> html.Dl:
    """Linhas "rótulo ... valor", como na tela da credencial do rascunho."""
    return html.Dl([peca for rotulo, valor in pares for peca in (html.Dt(rotulo), html.Dd(valor))], className="definicoes")


def barra(fracao: float, tom: Tom, marca: float | None = None) -> html.Div:
    """Barra horizontal de 0 a 1. `marca` desenha um traço vertical (máximo, hoje)."""
    pecas: list[Any] = [html.Div(className=f"barra-cheia fundo-{tom}", style={"width": f"{max(0.0, min(fracao, 1.0)) * 100:.1f}%"})]
    if marca is not None:
        pecas.append(html.Div(className="barra-marca", style={"left": f"{max(0.0, min(marca, 1.0)) * 100:.1f}%"}))
    return html.Div(pecas, className="barra", role="presentation")


def barra_rotulada(rotulo: str, valor: str, fracao: float, tom: Tom, marca: float | None = None) -> html.Div:
    return html.Div(
        [
            html.Div(
                [html.P(rotulo, className="barra-rotulo"), html.P(valor, className=f"barra-valor tom-{tom if tom == 'ruim' else 'neutro'}")],
                className="barra-topo",
            ),
            barra(fracao, tom, marca),
        ],
        className="barra-rotulada",
    )


def dica(titulo: str, texto: str, tom: Tom) -> html.Section:
    """Orientação fixa, sem número: o que fazer quando o estado aparecer."""
    return html.Section([html.P(titulo, className=f"dica-titulo tom-{tom}"), html.P(texto, className="dica-texto")], className="dica")


@dataclass(frozen=True)
class Pendencia:
    titulo: str
    falta: str
    depende_de: str


def reservado(titulo: str, pendencias: Sequence[Pendencia], origem: Any) -> html.Section:
    """O espaço de um número que ainda não dá para ler: diz o que falta e de quem
    depende, em vez de mostrar zero ou esconder o quadro."""
    linhas = [
        html.Li(
            [
                selo("Espera", "atencao"),
                html.Div([html.P(p.titulo, className="atencao-titulo"), html.P(p.falta, className="atencao-descricao")]),
                html.P(["depende de ", html.Strong(p.depende_de)], className="reservado-dono"),
            ],
            className="atencao-linha",
        )
        for p in pendencias
    ]
    return html.Section(
        [
            html.Header([html.H2(titulo), html.Div(f"{len(pendencias)} pendências", className="quadro-lateral")], className="quadro-topo"),
            html.Ul(linhas, className="atencao-lista"),
            html.Footer(html.P(origem, className="fonte-curta"), className="quadro-pe"),
        ],
        className="quadro reservado",
    )


def lista_de_fontes(leituras: Sequence[Leitura[Any]], agora: datetime) -> html.Details:
    """O pé da tela: cada fonte usada, com o nome técnico para conferir no CloudWatch."""
    vistas: dict[Fonte, Leitura[Any]] = {}
    for leitura in leituras:
        vistas.setdefault(leitura.fonte, leitura)
    itens = [
        html.Li(
            [
                html.P(fonte.nome, className="fonte-nome"),
                html.Code(fonte.identificador),
                html.P(f"Atraso de {fonte.atraso}; {hora_da_leitura(leitura.lido_em, agora)}.", className="fonte-atraso"),
            ]
        )
        for fonte, leitura in vistas.items()
    ]
    return html.Details(
        [html.Summary("De onde vem cada número"), html.Ul(itens)],
        className="lista-de-fontes",
    )
