"""O filtro de dia das telas: Hoje, 7 dias, 30 dias ou uma data específica.

O cabeçalho de toda tela diz o período que ela cobre ("26/10, de 0h às 15:40").
Na tela financeira, os três gastos e as barras por dia ficam ancorados no último
dia do período: em "7 dias", o dia é hoje; numa data específica, é ela.

A data específica vai até 12 meses para trás, o mesmo alcance do gráfico por
mês. Os quadros que leem o registro da aplicação têm um limite menor, de 30
dias, e cada um diz isso quando o período passa dele.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum

from painel.componentes.formato import DIAS_DA_SEMANA, MESES
from painel.dados.modelo import FUSO

DIAS_PARA_TRAS = 365


class Escolha(StrEnum):
    HOJE = "hoje"
    SETE_DIAS = "7dias"
    TRINTA_DIAS = "30dias"
    MES = "mes"
    DATA = "data"


ROTULOS = {
    Escolha.HOJE: "Hoje",
    Escolha.SETE_DIAS: "7 dias",
    Escolha.TRINTA_DIAS: "30 dias",
    Escolha.MES: "Mês",
    Escolha.DATA: "Data específica",
}


@dataclass(frozen=True)
class Periodo:
    escolha: Escolha
    primeiro_dia: date
    ultimo_dia: date
    agora: datetime

    @property
    def dias(self) -> list[date]:
        return [self.primeiro_dia + timedelta(days=n) for n in range((self.ultimo_dia - self.primeiro_dia).days + 1)]

    @property
    def termina_hoje(self) -> bool:
        return self.ultimo_dia == self.agora.astimezone(FUSO).date()


def montar(escolha: str | None, data: str | None, agora: datetime, mes: str | None = None) -> Periodo:
    """Escolha desconhecida vira Hoje; data inválida, futura ou fora do alcance vira
    hoje. O mês ("2026-09") vai do dia 1 ao último dia, ou até hoje no mês corrente."""
    hoje = agora.astimezone(FUSO).date()
    try:
        qual = Escolha(escolha or Escolha.HOJE)
    except ValueError:
        qual = Escolha.HOJE
    if qual is Escolha.SETE_DIAS:
        return Periodo(qual, hoje - timedelta(days=6), hoje, agora)
    if qual is Escolha.TRINTA_DIAS:
        return Periodo(qual, hoje - timedelta(days=29), hoje, agora)
    if qual is Escolha.DATA:
        dia = _data(data, hoje)
        return Periodo(qual, dia, dia, agora)
    if qual is Escolha.MES:
        primeiro = _data(f"{mes}-01" if mes else None, hoje).replace(day=1)
        ultimo = min((primeiro.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1), hoje)
        return Periodo(qual, primeiro, ultimo, agora)
    return Periodo(qual, hoje, hoje, agora)


def _data(texto: str | None, hoje: date) -> date:
    try:
        dia = date.fromisoformat(texto or "")
    except ValueError:
        return hoje
    return dia if hoje - timedelta(days=DIAS_PARA_TRAS) <= dia <= hoje else hoje


def _dia(dia: date, agora: datetime) -> str:
    return f"{dia:%d/%m}" if dia.year == agora.year else f"{dia:%d/%m/%Y}"


def descrever(periodo: Periodo) -> str:
    """ "26/10, de 0h às 15:40"; "25/10, dia inteiro"; "20/10 a 26/10, hoje até 15:40"."""
    agora = periodo.agora.astimezone(FUSO)
    primeiro, ultimo = _dia(periodo.primeiro_dia, agora), _dia(periodo.ultimo_dia, agora)
    if periodo.escolha is Escolha.MES:
        nome = f"{MESES[periodo.primeiro_dia.month - 1]} de {periodo.primeiro_dia.year}"
        return f"{nome}, hoje até {agora:%H:%M}" if periodo.termina_hoje else f"{nome}, mês inteiro"
    if periodo.primeiro_dia == periodo.ultimo_dia:
        return f"{ultimo}, de 0h às {agora:%H:%M}" if periodo.termina_hoje else f"{ultimo}, dia inteiro"
    texto = f"{primeiro} a {ultimo}"
    return f"{texto}, hoje até {agora:%H:%M}" if periodo.termina_hoje else texto


def opcoes_de_data(agora: datetime) -> list[dict[str, str]]:
    """Os dias que a data específica aceita, do mais novo ao mais antigo: "26/10/2026, segunda"."""
    hoje = agora.astimezone(FUSO).date()
    dias = (hoje - timedelta(days=n) for n in range(DIAS_PARA_TRAS + 1))
    return [{"label": f"{d:%d/%m/%Y}, {DIAS_DA_SEMANA[d.weekday()]}", "value": d.isoformat()} for d in dias]


def opcoes_de_mes(agora: datetime) -> list[dict[str, str]]:
    """Os 12 meses do gráfico por mês, do mais novo ao mais antigo: "outubro de 2026"."""
    mes = agora.astimezone(FUSO).date().replace(day=1)
    opcoes = []
    for _ in range(12):
        opcoes.append({"label": f"{MESES[mes.month - 1]} de {mes.year}", "value": f"{mes:%Y-%m}"})
        mes = (mes - timedelta(days=1)).replace(day=1)
    return opcoes
