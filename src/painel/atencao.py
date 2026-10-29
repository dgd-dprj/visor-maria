"""O que pede atenção: incidentes e itens do quadro "Exige atenção".

Regras puras, sobre leituras já feitas, para a tela só desenhar. Cada item diz
o que está acontecendo com o número dentro da frase, e não com um código.

- Credencial vencida: o ambiente está sem acesso ao Verde. É PARADO, e conta
  como incidente aberto.
- Rotina automática cuja última execução falhou: PARADO (a conferência diária
  falhou 30 dias sem ninguém ver, levantamento de 23/10).
- Credencial que vence em até `PRAZO_DE_AVISO_DIAS`: ATENÇÃO.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from painel.componentes.formato import data_curta, data_e_hora_curta, dias
from painel.dados.modelo import Ambiente, Credencial, DiaDoVerde, Estado, Leitura, Rotina

PRAZO_DE_AVISO_DIAS = 10

Nivel = Literal["parado", "atencao"]

NOME_NA_FRASE = {Ambiente.PRODUCAO: "A produção", Ambiente.RELEASE: "O release"}
DO_AMBIENTE = {Ambiente.PRODUCAO: "de produção", Ambiente.RELEASE: "do release"}


@dataclass(frozen=True)
class ItemDeAtencao:
    nivel: Nivel
    titulo: str
    descricao: str
    acao: str
    # Nome da tela do menu para onde a ação leva.
    tela: str


@dataclass(frozen=True)
class Incidente:
    ambiente: Ambiente
    desde: datetime


def incidentes_abertos(credenciais: dict[Ambiente, Leitura[Credencial]], agora: datetime) -> list[Incidente]:
    abertos = [
        Incidente(ambiente, leitura.valor.valida_ate)
        for ambiente, leitura in credenciais.items()
        if leitura.estado is Estado.OK and leitura.valor is not None and leitura.valor.valida_ate <= agora
    ]
    return sorted(abertos, key=lambda i: i.desde)


def _semana(dias_do_verde: list[DiaDoVerde]) -> list[DiaDoVerde]:
    return dias_do_verde[-7:]


def _frase_da_semana(leitura: Leitura[list[DiaDoVerde]] | None) -> str:
    if leitura is None or leitura.estado is not Estado.OK or leitura.valor is None:
        return ""
    semana = _semana(leitura.valor)
    total = sum(d.total for d in semana)
    recusadas = sum(d.recusadas for d in semana)
    if total == 0:
        return " Ninguém consultou o Verde na semana."
    if recusadas == total:
        return f" As {recusadas} consultas da semana foram todas recusadas."
    return f" {recusadas} de {total} consultas da semana foram recusadas."


def itens_de_atencao(
    credenciais: dict[Ambiente, Leitura[Credencial]],
    verde: dict[Ambiente, Leitura[list[DiaDoVerde]]],
    rotinas: Leitura[list[Rotina]],
    agora: datetime,
) -> list[ItemDeAtencao]:
    parados: list[ItemDeAtencao] = []
    atencao: list[ItemDeAtencao] = []

    for ambiente, leitura in credenciais.items():
        if leitura.estado is not Estado.OK or leitura.valor is None:
            continue
        valida_ate = leitura.valor.valida_ate
        if valida_ate <= agora:
            parados.append(
                ItemDeAtencao(
                    "parado",
                    f"{NOME_NA_FRASE[ambiente]} está sem acesso ao Verde há {dias((agora - valida_ate).days)}",
                    f"A credencial venceu em {data_curta(valida_ate)}." + _frase_da_semana(verde.get(ambiente)),
                    "Ver credencial",
                    "Credencial do Verde",
                )
            )
        elif valida_ate - agora <= timedelta(days=PRAZO_DE_AVISO_DIAS):
            faltam = (valida_ate.date() - agora.date()).days
            atencao.append(
                ItemDeAtencao(
                    "atencao",
                    f"A credencial {DO_AMBIENTE[ambiente]} vence em {dias(faltam)}",
                    f"Vale até {data_e_hora_curta(valida_ate)}. Renove em horário útil, com alguém acompanhando o reinício.",
                    "Ver prazo",
                    "Credencial do Verde",
                )
            )

    if rotinas.estado is Estado.OK and rotinas.valor is not None:
        for rotina in rotinas.valor:
            if rotina.falhando_desde is None:
                continue
            ha = (agora.date() - rotina.falhando_desde.date()).days
            parados.append(
                ItemDeAtencao(
                    "parado",
                    f"{rotina.nome} falhando há {dias(ha)}",
                    f"{rotina.passaram} com sucesso e {rotina.falharam} com falha desde {data_curta(rotina.desde)}.",
                    "Ver rotinas",
                    "Sistema",
                )
            )

    return parados + atencao
