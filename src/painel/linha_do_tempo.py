"""A linha do tempo da credencial, montada a partir dos dados.

Cada evento sai de uma leitura (credencial, incidente, renovação), nunca de
texto escrito à mão: se a fonte não trouxer o fato, ele não aparece.

O vencimento de cada evento sai da validade que a conferência diária leu. Ela
lê o segredo antes de renovar, então a validade da credencial renovada é a da
conferência seguinte. A causa de cada incidente cruza a recusa com as
renovações e com essa validade.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from painel.componentes.formato import duracao, numero
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
# Uma renovação até 3 horas antes da primeira recusa (ou 1 hora depois) é a causa dela.
ANTES_DA_RECUSA = timedelta(hours=3)
DEPOIS_DA_RECUSA = timedelta(hours=1)
# A conferência que renova termina em minutos; a seguinte, no outro dia.
MESMA_CONFERENCIA = timedelta(hours=1)

Causa = Literal["container", "vencida", "no prazo", "sem validade"]
# O nome curto de cada causa, para a tabela, e o que ela quer dizer.
NOME_DA_CAUSA: dict[Causa, tuple[str, str]] = {
    "container": ("Container com a credencial antiga", "a rotina renovou, o container novo não subiu e o antigo ficou com a credencial invalidada"),
    "vencida": ("Credencial vencida", "a validade lida na conferência já tinha passado"),
    "no prazo": ("Recusa no prazo", "a credencial estava dentro da validade e o Verde recusou mesmo assim"),
    "sem validade": ("Sem validade conferida", "nenhuma conferência antes da recusa leu a validade deste ambiente"),
}


@dataclass(frozen=True)
class Evento:
    momento: datetime
    tipo: Tipo
    texto: str
    # Até quando valia a credencial do evento; None quando não se aplica ou não foi lido.
    vencimento: datetime | None = None


def validade_em(credencial: Credencial | None, momento: datetime) -> datetime | None:
    """A validade que a última conferência até o momento leu."""
    if credencial is None:
        return None
    return next((c.valida_ate for c in reversed(credencial.conferidas) if c.conferida_em <= momento), None)


def validade_depois(credencial: Credencial | None, momento: datetime) -> datetime | None:
    """A validade que a conferência seguinte leu: a da credencial renovada no momento.
    A conferência que renovou termina segundos depois, com a validade antiga: fica de fora."""
    if credencial is None:
        return None
    return next((c.valida_ate for c in credencial.conferidas if c.conferida_em > momento + MESMA_CONFERENCIA), None)


def causa(incidente: IncidenteDeCredencial, credenciais: dict[Ambiente, Credencial], renovacoes: list[Renovacao]) -> Causa:
    perto = [
        r for r in renovacoes if r.ambiente is incidente.ambiente and incidente.inicio - ANTES_DA_RECUSA <= r.momento <= incidente.inicio + DEPOIS_DA_RECUSA
    ]
    if any(not r.container_novo_no_ar for r in perto):
        return "container"
    validade = validade_em(credenciais.get(incidente.ambiente), incidente.inicio)
    if validade is None:
        return "sem validade"
    return "vencida" if validade <= incidente.inicio else "no prazo"


def montar(
    credenciais: dict[Ambiente, Credencial],
    incidentes: list[IncidenteDeCredencial],
    renovacoes: list[Renovacao],
    agora: datetime,
) -> list[Evento]:
    eventos: list[Evento] = []
    for ambiente, credencial in credenciais.items():
        if credencial.emitida_em is not None:
            eventos.append(Evento(credencial.emitida_em, "gerada", f"Credencial {DE[ambiente]} em uso.", credencial.valida_ate))
        if credencial.valida_ate <= agora:
            eventos.append(Evento(credencial.valida_ate, "venceu", f"A credencial {DE[ambiente]} vence.", credencial.valida_ate))
        else:
            eventos.append(Evento(credencial.valida_ate, "a vencer", f"A credencial {DE[ambiente]} vence, se não for renovada antes.", credencial.valida_ate))

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
        eventos.append(Evento(renovacao.momento, "renovada", texto, validade_depois(credenciais.get(renovacao.ambiente), renovacao.momento)))

    limite = agora - timedelta(days=JANELA_DIAS)
    return sorted((e for e in eventos if e.momento >= limite), key=lambda e: e.momento)
