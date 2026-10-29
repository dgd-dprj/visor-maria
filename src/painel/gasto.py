"""As contas da tela financeira: somar dias, escolher os trechos de comparação e
dizer a variação em palavras.

A variação nunca usa sinal ("+12%", "−5%"): o texto que a pessoa lê não tem
hífen nem travessão (regra 9), e "a mais" e "a menos" se leem sem esforço.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta

from painel.dados.modelo import GastoDeIA, TokensRegistrados
from painel.precos import Parcela, parcelas


def somar(inicio: date, gastos: Iterable[GastoDeIA]) -> GastoDeIA:
    lido = escrito = busca = 0
    for g in gastos:
        lido, escrito, busca = lido + g.lido, escrito + g.escrito, busca + g.busca
    return GastoDeIA(inicio, lido, escrito, busca)


@dataclass(frozen=True)
class Trecho:
    primeiro: date
    ultimo: date

    @property
    def dias(self) -> list[date]:
        return [self.primeiro + timedelta(days=n) for n in range((self.ultimo - self.primeiro).days + 1)]


def primeiro_do_mes(dia: date) -> date:
    return dia.replace(day=1)


def mes_anterior(mes: date) -> date:
    return (primeiro_do_mes(mes) - timedelta(days=1)).replace(day=1)


def ultimo_do_mes(dia: date) -> date:
    return dia.replace(day=monthrange(dia.year, dia.month)[1])


@dataclass(frozen=True)
class Trechos:
    """O dia, a semana e o mês que terminam na âncora, e com quem cada um se compara."""

    dia: Trecho
    dia_anterior: Trecho
    semana: Trecho
    semana_anterior: Trecho
    mes: Trecho
    mes_anterior: Trecho


def trechos(ancora: date) -> Trechos:
    ontem = ancora - timedelta(days=1)
    inicio_da_semana = ancora - timedelta(days=6)
    anterior = mes_anterior(ancora)
    # O mesmo trecho do mês anterior: do dia 1 ao mesmo dia, ou ao último dia
    # quando o mês anterior é mais curto (31/10 compara com 01/09 a 30/09).
    fim_do_anterior = anterior.replace(day=min(ancora.day, monthrange(anterior.year, anterior.month)[1]))
    return Trechos(
        dia=Trecho(ancora, ancora),
        dia_anterior=Trecho(ontem, ontem),
        semana=Trecho(inicio_da_semana, ancora),
        semana_anterior=Trecho(inicio_da_semana - timedelta(days=7), inicio_da_semana - timedelta(days=1)),
        mes=Trecho(primeiro_do_mes(ancora), ancora),
        mes_anterior=Trecho(anterior, fim_do_anterior),
    )


def anterior_ao_periodo(primeiro: date, ultimo: date, mes: bool) -> Trecho:
    """Com quem o período escolhido se compara. Um mês: o mês anterior inteiro, se
    o escolhido já fechou, ou o mesmo trecho dele (do dia 1 ao mesmo dia). Os outros
    períodos: os mesmos tantos dias, logo antes."""
    if mes:
        if ultimo == ultimo_do_mes(ultimo):
            anterior = mes_anterior(primeiro)
            return Trecho(anterior, ultimo_do_mes(anterior))
        return trechos(ultimo).mes_anterior
    dias = (ultimo - primeiro).days + 1
    return Trecho(primeiro - timedelta(days=dias), primeiro - timedelta(days=1))


def variacao(atual: float, anterior: float, referencia: str) -> str:
    """`referencia` completa a frase: "no dia 25/10", "de 13/10 a 19/10"."""
    if anterior <= 0:
        return f"também nenhum gasto {referencia}" if atual <= 0 else f"nenhum gasto {referencia}"
    pontos = round(abs(atual - anterior) / anterior * 100)
    if pontos == 0:
        return f"igual ao gasto {referencia}"
    return f"{pontos}% a {'mais' if atual > anterior else 'menos'} que {referencia}"


@dataclass(frozen=True)
class GastoDividido:
    """O gasto de um dia, dividido: o que as conversas da Maria registraram, o que
    veio de fora delas com o mesmo modelo, e a busca por semelhança, que a Maria não registra."""

    dia: date
    maria: float
    fora: float
    busca: float


def dividir(medido: GastoDeIA, registrados: list[TokensRegistrados]) -> GastoDividido:
    """A parte da Maria é a fração dos tokens do modelo de conversa que as conversas
    registraram, aplicada ao gasto dele; nunca mais que o medido."""
    p = parcelas(medido)
    do_modelo = p[Parcela.LIDO] + p[Parcela.ESCRITO]
    tokens_medidos = medido.lido + medido.escrito
    fracao = min(sum(r.total for r in registrados) / tokens_medidos, 1.0) if tokens_medidos else 0.0
    return GastoDividido(medido.inicio, do_modelo * fracao, do_modelo * (1 - fracao), p[Parcela.BUSCA])
