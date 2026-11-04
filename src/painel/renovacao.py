"""Quando a conferência diária vai renovar uma credencial.

As regras vêm do `verificar-token-verde.yml` (lido em 26/10):

- agendamento `0 12 * * *`: todo dia às 12:00 UTC, 09:00 em Brasília;
- renova quando faltam 7 dias ou menos (`DIAS_LIMITE = 7`);
- depois de vencida, ainda renova por 5 dias (o grace period do Verde).

Na prática, o GitHub começa a execução com atraso: de 18 a 25/10, entre 12:13 e
15:10 (Brasília). Por isso a renovação pode cair no dia em que a credencial
chega a 7 dias ou no seguinte, e a tela mostra os dois. Foi assim que a de
produção caiu no domingo, 25/10, às 12:24, e não no sábado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from painel.dados.modelo import FUSO

HORA_DO_AGENDAMENTO = time(9, 0)
DIAS_LIMITE = 7
DIAS_DE_GRACA = 5
ATRASO_OBSERVADO = (time(12, 13), time(15, 10))


@dataclass(frozen=True)
class PrevisaoDeRenovacao:
    """`dias` tem um dia quando a renovação é certa nele; dois quando depende do
    atraso do GitHub. `fora_do_prazo` é a credencial vencida há mais de 5 dias:
    só uma nova, emitida à mão no Verde, resolve."""

    dias: tuple[date, ...]
    fora_do_prazo: bool = False


def prever_renovacao(valida_ate: datetime, agora: datetime) -> PrevisaoDeRenovacao:
    valida_ate = valida_ate.astimezone(FUSO)
    if agora >= valida_ate + timedelta(days=DIAS_DE_GRACA):
        return PrevisaoDeRenovacao((), fora_do_prazo=True)
    limiar = valida_ate - timedelta(days=DIAS_LIMITE)
    primeiro = max(limiar.date(), agora.astimezone(FUSO).date())
    if limiar <= agora or limiar.time() <= HORA_DO_AGENDAMENTO:
        # Toda execução desse dia já encontra 7 dias ou menos.
        return PrevisaoDeRenovacao((primeiro,))
    if limiar.time() < ATRASO_OBSERVADO[0]:
        # Mesmo com o atraso mínimo, a execução começa depois do limiar.
        return PrevisaoDeRenovacao((primeiro,))
    if limiar.time() > ATRASO_OBSERVADO[1]:
        # Nem com o atraso máximo a execução desse dia alcança o limiar.
        return PrevisaoDeRenovacao((primeiro + timedelta(days=1),))
    # O limiar cai dentro da faixa de atraso: depende de quando o GitHub começar.
    return PrevisaoDeRenovacao((primeiro, primeiro + timedelta(days=1)))
