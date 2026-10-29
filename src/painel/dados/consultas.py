"""A janela e a validade de cada consulta, declaradas uma a uma.

O cache é requisito, não otimização: o Logs Insights cobra pelo que varre, a
leitura de métrica cobra por métrica, e as telas ficam abertas o dia todo. Por
isso toda consulta do `FonteDeDados` tem aqui:

- a janela, em palavras: o período que ela lê;
- a validade: quanto tempo a leitura de uma janela ainda aberta vale;
- quando a janela fecha, se fecha. Janela fechada não muda mais (o dia 25/10
  continua igual amanhã), então é lida uma vez e guardada sem prazo. Janela que
  anda com o relógio ("últimas 24 horas") nunca fecha.

Um teste (tests/test_cache.py) falha se o `FonteDeDados` ganhar uma consulta que
não esteja aqui, e o cache recusa chamar uma consulta não declarada.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any

from painel.dados.modelo import FUSO

UM_MINUTO = timedelta(minutes=1)
CINCO_MINUTOS = timedelta(minutes=5)
QUINZE_MINUTOS = timedelta(minutes=15)
# A métrica do Bedrock chega com cerca de 1 minuto de atraso, e um log pode
# chegar alguns segundos depois do fim do dia. Uma hora de folga cobre os dois.
FOLGA_PARA_FECHAR = timedelta(hours=1)


@dataclass(frozen=True)
class Consulta:
    janela: str
    validade: timedelta
    # Recebe os mesmos argumentos da consulta e diz quando a janela fecha (None: não fecha).
    fecha_em: Callable[..., datetime | None] | None = None


def fim_do_dia(dia: date) -> datetime:
    return datetime.combine(dia + timedelta(days=1), time(), tzinfo=FUSO) + FOLGA_PARA_FECHAR


def fim_do_mes(mes: date) -> datetime:
    proximo = (mes.replace(day=28) + timedelta(days=4)).replace(day=1)
    return datetime.combine(proximo, time(), tzinfo=FUSO) + FOLGA_PARA_FECHAR


def _dia_do_assunto(_ambiente: Any, dia: date) -> datetime:
    return fim_do_dia(dia)


def _dia_escolhido(*argumentos: Any) -> datetime | None:
    """Com o dia escolhido na tela, a janela é aquele dia, e fecha no fim dele; com a
    hora escolhida (o começo dela, um `datetime`), fecha no fim da hora. Sem os dois,
    a janela anda com o relógio e nunca fecha."""
    escolhido = next((a for a in argumentos if isinstance(a, date)), None)
    if isinstance(escolhido, datetime):
        return escolhido + timedelta(hours=1) + FOLGA_PARA_FECHAR
    return fim_do_dia(escolhido) if escolhido is not None else None


# A janela de quem aceita o dia escolhido, dita quando ele vem.
COM_DIA = ", ou o dia escolhido na tela"


CONSULTAS: dict[str, Consulta] = {
    # Agora e Sistema
    "saude_servico": Consulta("o último minuto da métrica do balanceador", UM_MINUTO),
    "implantacoes_em_curso": Consulta("o último minuto da métrica do ECS", UM_MINUTO),
    "ultimo_reinicio": Consulta("os 30 dias de logs, até a subida mais recente", CINCO_MINUTOS),
    "resumo_do_dia": Consulta("hoje, de 0h até agora" + COM_DIA, UM_MINUTO, _dia_escolhido),
    "credencial": Consulta("as conferências diárias desde 19/09 e a última consulta aceita, nos 30 dias de logs", CINCO_MINUTOS),
    "rotinas": Consulta("as execuções desde 19/09", CINCO_MINUTOS),
    "renovacoes": Consulta("as execuções da conferência diária desde 19/09", CINCO_MINUTOS),
    "verde_por_dia": Consulta("os 8 dias até hoje, de 0h do primeiro até agora", UM_MINUTO),
    "incidentes_de_credencial": Consulta("os 30 dias de logs", CINCO_MINUTOS),
    "tempo_de_resposta": Consulta("as últimas 24 horas" + COM_DIA, UM_MINUTO, _dia_escolhido),
    "duracao_do_verde": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "resultado_do_verde": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "respostas_com_erro": Consulta("as últimas 24 horas" + COM_DIA, UM_MINUTO, _dia_escolhido),
    "tokens_por_dia": Consulta("os 30 dias até hoje, de 0h do primeiro até agora", UM_MINUTO),
    # Atendimento
    "resumo_do_periodo": Consulta(
        "o trecho da origem: o TypeScript de 16/10 ao corte, o Python do corte até agora, o release nos últimos 7 dias" + COM_DIA, UM_MINUTO, _dia_escolhido
    ),
    "nao_encontrado": Consulta("o trecho da origem, como em resumo_do_periodo" + COM_DIA, UM_MINUTO, _dia_escolhido),
    "orquestrador": Consulta("os últimos 7 dias" + COM_DIA, UM_MINUTO, _dia_escolhido),
    # Relatório do dia
    "sistema_no_dia": Consulta("hoje, de 0h até agora" + COM_DIA, UM_MINUTO, _dia_escolhido),
    # Relatório da Aplicação
    "gasto_do_dia": Consulta("o dia pedido, de 0h a 24h em Brasília", UM_MINUTO, fim_do_dia),
    "gasto_do_mes": Consulta("o mês pedido, do dia 1 ao último dia, em Brasília", UM_MINUTO, fim_do_mes),
    # Hoje relê a cada 5 minutos: cada leitura varre o dia inteiro de logs.
    # Quanto do gasto é da Maria: 30 dias de registro, relidos a cada 15 minutos.
    "tokens_registrados": Consulta("os 30 dias até hoje, de 0h do primeiro até agora", QUINZE_MINUTOS),
    "gasto_por_assunto": Consulta("o dia pedido, de 0h a 24h em Brasília, num ambiente", CINCO_MINUTOS, _dia_do_assunto),
    # Coluna da direita das telas
    "atendimentos_por_hora": Consulta("o dia pedido, hora a hora, de 0h a 24h em Brasília", UM_MINUTO, _dia_do_assunto),
    "atendimentos_por_dia": Consulta("os 30 dias até hoje, de 0h do primeiro até agora", CINCO_MINUTOS),
    "desfechos": Consulta("o trecho da origem, como em resumo_do_periodo" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "desfechos_do_dia": Consulta("o dia pedido, de 0h a 24h em Brasília", CINCO_MINUTOS, _dia_do_assunto),
    "origem_nao_atendida": Consulta("o trecho da origem, como em resumo_do_periodo" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "requisicoes_por_hora": Consulta("as últimas 24 horas, hora a hora" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "recursos_do_servico": Consulta("os últimos 10 minutos e o máximo das últimas 24 horas", UM_MINUTO),
    "cpu_e_latencia": Consulta("as últimas 24 horas, hora a hora, dos dois ambientes" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "horarios_da_conferencia": Consulta("as conferências diárias dos últimos 30 dias", CINCO_MINUTOS),
    "verde_do_mes": Consulta("os 30 dias até hoje, de 0h do primeiro até agora", CINCO_MINUTOS),
    # Observatório da IA
    "erros_da_ia": Consulta("os 30 dias de logs" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "uso_da_ia": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "saude_do_modelo": Consulta("os 14 dias até hoje, de 0h do primeiro até agora", CINCO_MINUTOS),
    "mudancas_na_ia": Consulta("os 30 commits mais novos em src/maria/ia, na develop", CINCO_MINUTOS),
    # Fluxos: os detalhes em 7 dias, ou no dia ou hora escolhidos.
    "conversas_por_fluxo": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "desfechos_por_fluxo": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "triagem": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "duracao_das_conversas": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    "envios_do_whatsapp": Consulta("os últimos 7 dias" + COM_DIA, CINCO_MINUTOS, _dia_escolhido),
    # O histórico e os problemas varrem 30 dias: relidos a cada 15 minutos, para
    # a tela aberta não varrer 30 dias de logs a cada volta do relógio.
    "fluxos_por_dia": Consulta("os 30 dias até hoje, de 0h do primeiro até agora", QUINZE_MINUTOS),
    "problemas_por_dia": Consulta("os 30 dias até hoje, de 0h do primeiro até agora", QUINZE_MINUTOS),
    "encaminhamentos_por_dia": Consulta("os 30 dias até hoje, de 0h do primeiro até agora", QUINZE_MINUTOS),
}
