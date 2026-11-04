"""Como números e horários aparecem para a pessoa.

Sem hífen em nenhum texto: datas como "23/10, 12:31", nunca "2026-10-23", e
dia da semana sem o "feira" ("quinta, 23 de outubro").
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from painel.dados.modelo import FUSO

DIAS_DA_SEMANA = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")
MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)
POR_EXTENSO = ("nenhum", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove", "dez")


def numero(valor: int) -> str:
    return f"{valor:,}".replace(",", ".")


def contagem(valor: int, singular: str, plural: str) -> str:
    """ "1 recusada", "2 recusadas"."""
    return f"{numero(valor)} {singular if valor == 1 else plural}"


def por_extenso(valor: int) -> str:
    return POR_EXTENSO[valor] if 0 <= valor < len(POR_EXTENSO) else numero(valor)


def dias(quantos: int) -> str:
    if quantos <= 0:
        return "menos de 1 dia"
    return f"{quantos} dia{'s' if quantos > 1 else ''}"


def _local(momento: datetime | date) -> datetime | date:
    return momento.astimezone(FUSO) if isinstance(momento, datetime) else momento


def data_curta(momento: datetime | date) -> str:
    return f"{_local(momento):%d/%m}"


def data_e_hora_curta(momento: datetime) -> str:
    return f"{momento.astimezone(FUSO):%d/%m, %H:%M}"


def data_e_hora(momento: datetime) -> str:
    return momento.astimezone(FUSO).strftime("%d/%m às %H:%M")


def dia_por_extenso(momento: datetime, com_ano: bool = False) -> str:
    local = momento.astimezone(FUSO)
    texto = f"{DIAS_DA_SEMANA[local.weekday()]}, {local.day} de {MESES[local.month - 1]}"
    if com_ano:
        texto += f" de {local.year}"
    return texto[0].upper() + texto[1:]


def lista(itens: list[str]) -> str:
    if len(itens) <= 1:
        return "".join(itens)
    return ", ".join(itens[:-1]) + " e " + itens[-1]


def duracao(intervalo: timedelta) -> str:
    """ "54 minutos", "23 horas", "19 dias": a maior unidade inteira."""
    minutos = int(intervalo.total_seconds() // 60)
    if minutos < 60:
        return contagem(max(minutos, 1), "minuto", "minutos")
    horas = minutos // 60
    if horas < 48:
        return contagem(horas, "hora", "horas")
    return contagem(horas // 24, "dia", "dias")


def dinheiro(valor: float, casas: int = 2) -> str:
    """ "US$ 2,38"; abaixo da última casa, "menos de US$ 0,01". `casas=4` serve
    para valores por atendimento, que ficam em frações de centavo."""
    if 0 < valor < 0.5 / 10**casas:
        return f"menos de US$ 0,{'0' * (casas - 1)}1"
    inteiro, _, centavos = f"{valor:,.{casas}f}".partition(".")
    return f"US$ {inteiro.replace(',', '.')},{centavos}"


def sem_hifen(texto: str) -> str:
    """Texto de fora (título de commit) sem hífen nem travessão, como a regra 9 pede,
    e sem o código de emoji (":bug:")."""
    texto = re.sub(r":[a-z_]+:\s*", "", texto)
    texto = re.sub(r"\s*[–—]\s*", ", ", texto)
    return re.sub(r"[-‐‑‒−]", " ", texto).strip()


def segundos(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",")


def dia_da_semana_e_data(dia: date) -> str:
    """ "sábado, 22/11"."""
    return f"{DIAS_DA_SEMANA[dia.weekday()]}, {dia:%d/%m}"


def hora_da_leitura(lido_em: datetime, agora: datetime) -> str:
    lido = lido_em.astimezone(FUSO)
    if lido.date() == agora.astimezone(FUSO).date():
        return f"lido às {lido:%H:%M}"
    return f"lido em {lido:%d/%m} às {lido:%H:%M}"


def ha_quanto(momento: datetime, agora: datetime) -> str:
    minutos = int((agora - momento).total_seconds() // 60)
    if minutos < 1:
        return "agora há pouco"
    if minutos < 60:
        return f"há {minutos} minuto{'s' if minutos > 1 else ''}"
    horas = minutos // 60
    if horas < 24:
        return f"há {horas} hora{'s' if horas > 1 else ''}"
    return f"há {dias(horas // 24)}"
