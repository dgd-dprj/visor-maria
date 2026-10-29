"""A linha do tempo da credencial, montada a partir dos dados.

Cada evento sai de uma leitura (credencial, incidente, renovação), nunca de
texto escrito à mão: se a fonte não trouxer o fato, ele não aparece.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from painel.componentes.formato import data_e_hora_curta, duracao, numero
from painel.dados.modelo import Ambiente, Credencial, IncidenteDeCredencial, Renovacao

Tipo = Literal["gerada", "renovada", "recusou", "resolvido", "venceu", "a vencer"]
TOM_DO_TIPO = {
    "gerada": "neutro",
    "renovada": "bom",
    "recusou": "ruim",
    "resolvido": "bom",
    "venceu": "ruim",
    "a vencer": "atencao",
}
DE = {Ambiente.PRODUCAO: "de produção", Ambiente.RELEASE: "do release"}
NOME = {Ambiente.PRODUCAO: "Produção", Ambiente.RELEASE: "Release"}
JANELA_DIAS = 30


@dataclass(frozen=True)
class Evento:
    momento: datetime
    tipo: Tipo
    texto: str


def montar(
    credenciais: dict[Ambiente, Credencial],
    incidentes: list[IncidenteDeCredencial],
    renovacoes: list[Renovacao],
    agora: datetime,
) -> list[Evento]:
    eventos: list[Evento] = []
    for ambiente, credencial in credenciais.items():
        if credencial.emitida_em is not None:
            eventos.append(
                Evento(
                    credencial.emitida_em,
                    "gerada",
                    f"Credencial {DE[ambiente]} em uso, válida até {data_e_hora_curta(credencial.valida_ate)}.",
                )
            )
        if credencial.valida_ate <= agora:
            eventos.append(Evento(credencial.valida_ate, "venceu", f"A credencial {DE[ambiente]} vence."))
        else:
            eventos.append(Evento(credencial.valida_ate, "a vencer", f"A credencial {DE[ambiente]} vence, se não for renovada antes."))

    for incidente in incidentes:
        nome = NOME[incidente.ambiente]
        fim = incidente.fim or agora
        eventos.append(
            Evento(
                incidente.inicio,
                "recusou",
                f"{nome} começa a levar recusa: {numero(incidente.recusadas)} consultas negadas em {duracao(fim - incidente.inicio)}"
                + ("." if incidente.fim else ", e contando."),
            )
        )
        if incidente.fim is not None:
            eventos.append(
                Evento(
                    incidente.fim,
                    "resolvido",
                    f"{nome}: o Verde volta a aceitar, {duracao(incidente.fim - incidente.inicio)} depois do início.",
                )
            )

    for renovacao in renovacoes:
        if renovacao.container_novo_no_ar:
            texto = f"Renovação automática {DE[renovacao.ambiente]}. O container novo subiu com a credencial nova."
        else:
            texto = f"Renovação automática {DE[renovacao.ambiente]}. O container novo não subiu, e o antigo ficou com a credencial invalidada."
        eventos.append(Evento(renovacao.momento, "renovada", texto))

    limite = agora - timedelta(days=JANELA_DIAS)
    return sorted((e for e in eventos if e.momento >= limite), key=lambda e: e.momento)
