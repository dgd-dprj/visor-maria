"""O que cada tela pergunta à camada de dados, e de onde cada resposta vem.

`FonteDeDados` é o contrato. O simulado e a fonte real (CloudWatch e GitHub,
ainda por fazer) implementam o mesmo contrato e devolvem as mesmas `Fonte`s,
para a tela não saber qual dos dois está ligado.

Os nomes técnicos seguem o levantamento de 23/10: produção e release se separam
pelo grupo de logs, pelo serviço do ECS e pelo target group. Nada aqui lê o
banco: a #309 bloqueia o banco como fonte. Nada lê o segredo da credencial.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from painel.dados.modelo import (
    AMBIENTE_DA_ORIGEM,
    Ambiente,
    ContagemPorDia,
    ContagemPorHora,
    ConversasDoFluxo,
    Credencial,
    Desfecho,
    DesfechoDoFluxo,
    DiaDoModelo,
    DiaDoVerde,
    DuracaoDasConversas,
    DuracaoDoVerde,
    EncaminhamentoNoDia,
    EnvioDoWhatsapp,
    ErroDaIA,
    FluxoNoDia,
    Fonte,
    GastoDeIA,
    GastoDoAssunto,
    HorarioDaConferencia,
    IncidenteDeCredencial,
    Leitura,
    MudancaNaIA,
    Origem,
    OrigemNaoAtendida,
    ProblemaNoDia,
    RecursosDoServico,
    Renovacao,
    RequisicoesPorHora,
    RespostasComErro,
    ResultadoDoVerde,
    ResumoDoDia,
    ResumoDoOrquestrador,
    ResumoDoPeriodo,
    RodadaDaTriagem,
    Rotina,
    SaudeServico,
    SistemaNoDia,
    TempoDeResposta,
    TokensDoDia,
    TokensRegistrados,
    TrechoDeNaoEncontrado,
    UsoDaIA,
)

GRUPO_DE_LOGS = {
    Ambiente.PRODUCAO: "/ecs/maria-langgraph-pp/api",
    Ambiente.RELEASE: "/ecs/maria-langgraph-pp-release/api",
}
SERVICO_ECS = {Ambiente.PRODUCAO: "api", Ambiente.RELEASE: "api-release"}
TARGET_GROUP = {
    Ambiente.PRODUCAO: "maria-langgraph-pp-api",
    Ambiente.RELEASE: "maria-langgraph-pp-api-release",
}
LOGS_DO = {Ambiente.PRODUCAO: "logs de produção", Ambiente.RELEASE: "logs do release"}
# Na tela financeira, para quem lê de finanças: o mesmo grupo de logs, sem a palavra técnica.
REGISTRO_DO = {Ambiente.PRODUCAO: "registro da aplicação em produção", Ambiente.RELEASE: "registro da aplicação no release"}
MODELO_DE_CHAT = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
MODELO_DE_EMBEDDING = "amazon.titan-embed-text-v2:0"

# O Logs Insights cobra pelo que varre, e as telas ficam abertas o dia todo:
# as janelas são as menores que respondem à pergunta (levantamento, seção 5).
DIAS_DO_GRAFICO_DO_VERDE = 8
DIAS_DO_CUSTO = 30
# Os logs da aplicação guardam 30 dias (retention_in_days nos .tf de produção e do
# release, develop em 26/10): antes disso, só as métricas.
DIAS_DO_REGISTRO = 30


def _quando(padrao: str, dia: date | None) -> str:
    """A janela no nome da fonte: a padrão ("nas últimas 24 horas"), o dia escolhido
    na tela, ou a hora escolhida (o `dia` é então o começo dela, um `datetime`)."""
    if dia is None:
        return padrao
    if isinstance(dia, datetime):
        return f"em {dia:%d/%m/%Y}, das {dia.hour}h às {dia.hour + 1}h"
    return f"em {dia:%d/%m/%Y}"


def _logs(ambiente: Ambiente, nome: str, eventos: str) -> Fonte:
    return Fonte(curto=LOGS_DO[ambiente], nome=f"Logs da aplicação, {nome}", identificador=f"{GRUPO_DE_LOGS[ambiente]}, {eventos}", atraso="segundos")


def fonte_saude_servico(ambiente: Ambiente) -> Fonte:
    return Fonte(
        curto="balanceador",
        nome="Métrica do balanceador, containers saudáveis",
        identificador=f"AWS/ApplicationELB HealthyHostCount, {TARGET_GROUP[ambiente]}",
        atraso="cerca de 1 minuto",
    )


def fonte_implantacoes(ambiente: Ambiente) -> Fonte:
    return Fonte(
        curto="ECS",
        nome="Métrica do ECS, implantações em curso",
        identificador=f"ECS/ContainerInsights DeploymentCount, serviço {SERVICO_ECS[ambiente]}",
        atraso="cerca de 1 minuto",
    )


def fonte_ultimo_reinicio(ambiente: Ambiente) -> Fonte:
    return _logs(ambiente, "última subida do container", 'linha "Application startup complete."')


def fonte_resumo_do_dia(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        _quando("desde 0h", dia),
        "eventos atendimento_criado, atendimento_finalizado, pergunta_enviada, verde_chamada e atendimento_sem_checkpoint",
    )


def fonte_credencial(ambiente: Ambiente) -> Fonte:
    # A validade vem do log da conferência diária ("status atual ... expiraEm"),
    # e não do segredo: o painel nunca lê a credencial.
    return Fonte(
        curto=f"GitHub e {LOGS_DO[ambiente]}",
        nome="Validade pelo log da conferência diária da credencial; última consulta aceita pelos logs",
        identificador=f'verificar-token-verde.yml, linha "status atual"; {GRUPO_DE_LOGS[ambiente]}, evento verde_chamada',
        atraso="até 1 dia na validade, segundos na última consulta",
    )


def fonte_rotinas() -> Fonte:
    return Fonte(
        curto="GitHub",
        nome="Execuções das rotinas automáticas desde 19/09",
        identificador="GitHub Actions, dgd-dprj/maria-langgraph-pp",
        atraso="minutos",
    )


def fonte_renovacoes() -> Fonte:
    return Fonte(
        curto="GitHub",
        nome="Renovações feitas pela conferência diária da credencial",
        identificador='verificar-token-verde.yml, linhas "token renovado" e "container novo no ar"',
        atraso="minutos",
    )


def fonte_verde_por_dia(ambiente: Ambiente) -> Fonte:
    return _logs(
        ambiente,
        f"consultas ao Verde por dia, últimos {DIAS_DO_GRAFICO_DO_VERDE} dias",
        "evento verde_chamada, campos resultado e status",
    )


def fonte_incidentes() -> Fonte:
    return Fonte(
        curto="logs de produção e logs do release",
        nome="Blocos de recusa da credencial (status 401 ou 403) nos 30 dias de logs",
        identificador=f"{GRUPO_DE_LOGS[Ambiente.PRODUCAO]} e {GRUPO_DE_LOGS[Ambiente.RELEASE]}, evento verde_chamada",
        atraso="segundos",
    )


def fonte_tempo_de_resposta(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"tempo de resposta das rotas de atendimento {_quando('nas últimas 24 horas', dia)}",
        'linhas "incoming request" (req.url) e "request completed" (responseTime), ligadas pelo reqId',
    )


def fonte_duracao_do_verde(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(ambiente, f"duração das consultas ao Verde {_quando('nos últimos 7 dias', dia)}", "evento verde_chamada, campos chamada e duracaoMs")


def fonte_resultado_do_verde(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente, f"resultado das consultas ao Verde {_quando('nos últimos 7 dias', dia)}", "evento verde_chamada, campos resultado, status e tipoErro"
    )


def fonte_respostas_com_erro(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"respostas 4xx e 5xx {_quando('nas últimas 24 horas', dia)}",
        'linhas "incoming request" (req.url) e "request completed" (res.statusCode), ligadas pelo reqId',
    )


def fonte_tokens_por_dia() -> Fonte:
    return Fonte(
        curto="Bedrock da conta inteira",
        nome="Tokens contados pelo Bedrock, por dia, para a conta AWS inteira (não separa ambiente nem projeto)",
        identificador=f"AWS/Bedrock InputTokenCount e OutputTokenCount, ModelId {MODELO_DE_CHAT}",
        atraso="cerca de 1 minuto",
    )


def fonte_gasto_de_ia() -> Fonte:
    return Fonte(
        curto="medição da AWS para a conta inteira",
        nome=(
            "Texto lido e escrito pela inteligência artificial e busca por semelhança, contados pela AWS dia a dia para a conta "
            "inteira (não separa ambiente nem projeto), vezes o preço de tabela"
        ),
        identificador=f"AWS/Bedrock InputTokenCount e OutputTokenCount, ModelId {MODELO_DE_CHAT} e {MODELO_DE_EMBEDDING}, períodos de 1 dia em Brasília",
        atraso="cerca de 1 minuto",
    )


def fonte_gasto_por_assunto(ambiente: Ambiente) -> Fonte:
    return Fonte(
        curto=REGISTRO_DO[ambiente],
        nome=f"Atendimentos que terminaram e triagens, por assunto, com os tokens que a aplicação registrou ({REGISTRO_DO[ambiente]})",
        identificador=f"{GRUPO_DE_LOGS[ambiente]}, eventos atendimento_finalizado (fluxoId, tokensGastos) e orquestrador_* (tokensGastosTotal)",
        atraso="segundos",
    )


def fonte_resumo_do_periodo(origem: Origem, dia: date | None = None) -> Fonte:
    return _logs(
        AMBIENTE_DA_ORIGEM[origem],
        f"atendimentos {_quando('no período', dia)}",
        "eventos atendimento_criado, atendimento_finalizado, pergunta_enviada e ttl_confirmacao_solicitada",
    )


def fonte_nao_encontrado(origem: Origem) -> Fonte:
    return _logs(
        AMBIENTE_DA_ORIGEM[origem],
        'encerramentos por "RG não encontrado" e a credencial no mesmo período',
        "eventos atendimento_finalizado (motivoHandoff) e verde_chamada",
    )


def fonte_orquestrador() -> Fonte:
    return _logs(
        Ambiente.RELEASE,
        "conversas por escrita livre",
        "eventos orquestrador_fluxo_identificado, orquestrador_redirecionado, orquestrador_finalizado_sem_fluxo e orquestrador_pergunta_enviada",
    )


def fonte_sistema_no_dia(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return Fonte(
        curto=f"balanceador, {LOGS_DO[ambiente]} e GitHub",
        nome=f"O sistema {_quando('desde 0h', dia)}: tempo fora do ar, reinícios, erros de servidor, subidas e testes",
        identificador=(
            f"AWS/ApplicationELB HealthyHostCount e HTTPCode_Target_5XX_Count, {TARGET_GROUP[ambiente]}; "
            f'{GRUPO_DE_LOGS[ambiente]}, linha "Application startup complete."; GitHub Actions'
        ),
        atraso="cerca de 1 minuto",
    )


def fonte_atendimentos_por_hora(ambiente: Ambiente) -> Fonte:
    return _logs(ambiente, "atendimentos por hora num dia", "eventos atendimento_criado e atendimento_finalizado")


def fonte_atendimentos_por_dia(ambiente: Ambiente) -> Fonte:
    return _logs(ambiente, f"atendimentos por dia, últimos {DIAS_DO_REGISTRO} dias", "eventos atendimento_criado e atendimento_finalizado")


def fonte_desfechos(ambiente: Ambiente) -> Fonte:
    return _logs(ambiente, "como os atendimentos terminaram", "evento atendimento_finalizado, campo motivoHandoff")


def fonte_origem_nao_atendida(ambiente: Ambiente) -> Fonte:
    return _logs(
        ambiente,
        '"origem do processo não atendida", aberta pela consulta ao processo na mesma conversa',
        'eventos atendimento_finalizado (motivoHandoff) e verde_chamada (chamada "processo", resultado, tipoErro), contados por conversa',
    )


def fonte_requisicoes_por_hora(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return Fonte(
        curto="balanceador",
        nome=f"Requisições e erros de servidor por hora, {_quando('nas últimas 24 horas', dia)} (inclui a varredura de robôs)",
        identificador=f"AWS/ApplicationELB RequestCount e HTTPCode_Target_5XX_Count, {TARGET_GROUP[ambiente]}",
        atraso="cerca de 1 minuto",
    )


def fonte_recursos_do_servico(ambiente: Ambiente) -> Fonte:
    return Fonte(
        curto="ECS",
        nome="CPU e memória usadas pelo serviço, como parte do que a tarefa reserva",
        identificador=f"ECS/ContainerInsights CpuUtilized, CpuReserved, MemoryUtilized e MemoryReserved, serviço {SERVICO_ECS[ambiente]}",
        atraso="cerca de 1 minuto",
    )


def fonte_horarios_da_conferencia() -> Fonte:
    return Fonte(
        curto="GitHub",
        nome="Hora em que cada conferência diária começou, nos últimos 30 dias",
        identificador="GitHub Actions, verificar-token-verde.yml (agendada para 0 12 * * *, 9h em Brasília)",
        atraso="minutos",
    )


def fonte_verde_do_mes(ambiente: Ambiente) -> Fonte:
    return _logs(ambiente, "consultas ao Verde por dia, últimos 30 dias", "evento verde_chamada, campos resultado e status")


def fonte_erros_da_ia(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"falhas das funções de inteligência artificial {_quando('nos últimos 30 dias', dia)}",
        'linhas de erro "[classificar] falha", "[desambiguar] falha", "[extrair] falha", "[reescrever] falha" e "[sumarizar] falha"',
    )


def fonte_uso_da_ia(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(ambiente, f"perguntas escritas pela inteligência artificial {_quando('nos últimos 7 dias', dia)}", "evento pergunta_enviada, campo viaIA")


def fonte_saude_do_modelo() -> Fonte:
    return Fonte(
        curto="medição da AWS para a conta inteira",
        nome="Chamadas, erros, limitação e demora do modelo de conversa, por dia, nos últimos 14 dias (conta inteira)",
        identificador=(
            "AWS/Bedrock Invocations, InvocationClientErrors, InvocationServerErrors, InvocationThrottles, InvocationLatency e "
            f"OutputTokenCount, ModelId {MODELO_DE_CHAT}"
        ),
        atraso="cerca de 1 minuto",
    )


def fonte_mudancas_na_ia() -> Fonte:
    return Fonte(
        curto="GitHub",
        nome="Mudanças no módulo de inteligência artificial da Maria, na branch develop",
        identificador="GitHub, dgd-dprj/maria-langgraph-pp, commits em src/maria/ia",
        atraso="minutos",
    )


def fonte_tokens_registrados(ambiente: Ambiente) -> Fonte:
    return Fonte(
        curto=REGISTRO_DO[ambiente],
        nome=f"Tokens que as conversas da Maria registraram, por dia, nos últimos {DIAS_DO_REGISTRO} dias ({REGISTRO_DO[ambiente]})",
        identificador=(
            f"{GRUPO_DE_LOGS[ambiente]}, evento atendimento_finalizado (tokensGastos) e eventos orquestrador_fluxo_identificado, "
            "orquestrador_redirecionado, orquestrador_finalizado_sem_fluxo e orquestrador_pergunta_enviada (tokensGastosTotal)"
        ),
        atraso="segundos",
    )


# ── Fluxos ────────────────────────────────────────────────────────────────
# As janelas da tela Fluxos: os detalhes em 7 dias (ou no dia escolhido), o
# histórico e os problemas em 30, dia a dia.
DIAS_DOS_FLUXOS = 7


def fonte_conversas_por_fluxo(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"conversas por fluxo, por respostas e por como terminaram, {_quando(f'nos últimos {DIAS_DOS_FLUXOS} dias', dia)}",
        "eventos atendimento_criado, atendimento_finalizado (destino), atendimento_expirado e resposta_recebida, juntados por conversa (chatId) e só contados",
    )


def fonte_desfechos_por_fluxo(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"como cada fluxo terminou {_quando(f'nos últimos {DIAS_DOS_FLUXOS} dias', dia)}",
        "evento atendimento_finalizado, campos fluxoId, motivoHandoff e destino",
    )


def fonte_triagem(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"como a triagem por escrita livre direcionou {_quando(f'nos últimos {DIAS_DOS_FLUXOS} dias', dia)}",
        "eventos orquestrador_fluxo_identificado (flowId), orquestrador_redirecionado e orquestrador_finalizado_sem_fluxo (tipoCaso, destino), "
        "orquestrador_pergunta_enviada e orquestrador_inconsistencia",
    )


def fonte_fluxos_por_dia(ambiente: Ambiente) -> Fonte:
    return _logs(
        ambiente,
        f"conversas por fluxo e por dia, últimos {DIAS_DO_REGISTRO} dias",
        "eventos atendimento_criado e atendimento_finalizado (destino), campo fluxoId",
    )


def fonte_problemas_por_dia(ambiente: Ambiente) -> Fonte:
    return _logs(
        ambiente,
        f"problemas no caminho das conversas, por dia, últimos {DIAS_DO_REGISTRO} dias",
        "evento atendimento_finalizado com motivoHandoff falha_infra_verde; eventos atendimento_expirado, atendimento_sem_checkpoint, "
        "orquestrador_inconsistencia, whatsapp_envio_falhou, whatsapp_envio_erro, whatsapp_bridge_erro e whatsapp_status_entrega com status failed",
    )


def fonte_encaminhamentos(ambiente: Ambiente) -> Fonte:
    return _logs(
        ambiente,
        f"atendimentos que terminaram, por dia, destino e motivo, últimos {DIAS_DO_REGISTRO} dias",
        "evento atendimento_finalizado (fluxoId, destino, motivoHandoff); eventos orquestrador_finalizado_sem_fluxo e "
        "orquestrador_inconsistencia, só os que mandam para pessoa (campo destino)",
    )


def fonte_duracao_das_conversas(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"quanto as conversas que terminaram levaram, do começo ao fim, {_quando(f'nos últimos {DIAS_DOS_FLUXOS} dias', dia)}",
        "eventos atendimento_criado e atendimento_finalizado, juntados por conversa (chatId) e só contados",
    )


def fonte_envios_do_whatsapp(ambiente: Ambiente, dia: date | None = None) -> Fonte:
    return _logs(
        ambiente,
        f"envios ao WhatsApp e avisos de entrega {_quando(f'nos últimos {DIAS_DOS_FLUXOS} dias', dia)}",
        "eventos whatsapp_envio_ok, whatsapp_envio_falhou (status), whatsapp_envio_erro, whatsapp_bridge_erro e whatsapp_status_entrega (status, erroCodigo)",
    )


class FonteDeDados(Protocol):
    """As consultas com `dia` leem, com ele, aquele dia de Brasília, de 0h a 24h
    (ou até agora, se for hoje), em vez da janela padrão. É o filtro de dia das
    telas: o clique num dia de um gráfico refaz a tela inteira naquele dia."""

    # Entra na chave do cache: duas fontes nunca dividem leitura guardada.
    @property
    def nome(self) -> str: ...

    def saude_servico(self, ambiente: Ambiente) -> Leitura[SaudeServico]: ...

    def implantacoes_em_curso(self, ambiente: Ambiente) -> Leitura[int]: ...

    def ultimo_reinicio(self, ambiente: Ambiente) -> Leitura[datetime]: ...

    def resumo_do_dia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[ResumoDoDia]: ...

    def credencial(self, ambiente: Ambiente) -> Leitura[Credencial]: ...

    def rotinas(self) -> Leitura[list[Rotina]]: ...

    def renovacoes(self) -> Leitura[list[Renovacao]]: ...

    def verde_por_dia(self, ambiente: Ambiente) -> Leitura[list[DiaDoVerde]]: ...

    def incidentes_de_credencial(self) -> Leitura[list[IncidenteDeCredencial]]: ...

    def tempo_de_resposta(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[TempoDeResposta]: ...

    def duracao_do_verde(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DuracaoDoVerde]]: ...

    def resultado_do_verde(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[ResultadoDoVerde]: ...

    def respostas_com_erro(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[RespostasComErro]: ...

    def tokens_por_dia(self) -> Leitura[list[TokensDoDia]]: ...

    def gasto_do_dia(self, dia: date) -> Leitura[GastoDeIA]: ...

    def gasto_do_mes(self, mes: date) -> Leitura[GastoDeIA]: ...

    def gasto_por_assunto(self, ambiente: Ambiente, dia: date) -> Leitura[list[GastoDoAssunto]]: ...

    def tokens_registrados(self, ambiente: Ambiente) -> Leitura[list[TokensRegistrados]]: ...

    def atendimentos_por_hora(self, ambiente: Ambiente, dia: date) -> Leitura[list[ContagemPorHora]]: ...

    def atendimentos_por_dia(self, ambiente: Ambiente) -> Leitura[list[ContagemPorDia]]: ...

    def desfechos(self, origem: Origem, dia: date | None = None) -> Leitura[list[Desfecho]]: ...

    def desfechos_do_dia(self, ambiente: Ambiente, dia: date) -> Leitura[list[Desfecho]]: ...

    def origem_nao_atendida(self, origem: Origem, dia: date | None = None) -> Leitura[OrigemNaoAtendida]: ...

    def requisicoes_por_hora(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[RequisicoesPorHora]]: ...

    def recursos_do_servico(self, ambiente: Ambiente) -> Leitura[RecursosDoServico]: ...

    def horarios_da_conferencia(self) -> Leitura[list[HorarioDaConferencia]]: ...

    def verde_do_mes(self, ambiente: Ambiente) -> Leitura[list[DiaDoVerde]]: ...

    def erros_da_ia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[ErroDaIA]]: ...

    def uso_da_ia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[UsoDaIA]: ...

    def saude_do_modelo(self) -> Leitura[list[DiaDoModelo]]: ...

    def mudancas_na_ia(self) -> Leitura[list[MudancaNaIA]]: ...

    def resumo_do_periodo(self, origem: Origem, dia: date | None = None) -> Leitura[ResumoDoPeriodo]: ...

    def nao_encontrado(self, origem: Origem, dia: date | None = None) -> Leitura[list[TrechoDeNaoEncontrado]]: ...

    def orquestrador(self, origem: Origem, dia: date | None = None) -> Leitura[ResumoDoOrquestrador]: ...

    def sistema_no_dia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[SistemaNoDia]: ...

    # Tela Fluxos
    def conversas_por_fluxo(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[ConversasDoFluxo]]: ...

    def desfechos_por_fluxo(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DesfechoDoFluxo]]: ...

    def triagem(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[RodadaDaTriagem]]: ...

    def fluxos_por_dia(self, ambiente: Ambiente) -> Leitura[list[FluxoNoDia]]: ...

    def problemas_por_dia(self, ambiente: Ambiente) -> Leitura[list[ProblemaNoDia]]: ...

    def duracao_das_conversas(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DuracaoDasConversas]]: ...

    def envios_do_whatsapp(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[EnvioDoWhatsapp]]: ...

    # Relatório da Aplicação: atendimento humano
    def encaminhamentos_por_dia(self, ambiente: Ambiente) -> Leitura[list[EncaminhamentoNoDia]]: ...
