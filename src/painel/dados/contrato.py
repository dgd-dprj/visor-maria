"""O que o painel lê dos logs da Maria: nomes de evento e de campo.

A Maria mora em outro repositório (maria-langgraph-pp). Se ela renomear um
evento ou um campo daqui, a consulta do painel continua rodando e devolve zero,
sem erro: o painel quebra em silêncio. Por isso esta lista é contrato, conferido
por `tests/test_contrato_da_maria.py` contra:

- o retrato do código da Maria (`tests/fixtures/maria/contrato_extraido.json`,
  gerado por `scripts/extrair_contrato_da_maria.py`, refeito todo dia pelo CI);
- os logs de referência da Maria (`tests/fixtures/maria/logs/`).

Toda consulta nova a log entra aqui primeiro.
"""

from __future__ import annotations

# Evento -> campos que o painel lê dele (além de `evento`).
EVENTOS: dict[str, frozenset[str]] = {
    # `chatId` só entra nas consultas para juntar os eventos de uma conversa e contá-la;
    # nunca sai delas (tela Fluxos).
    "atendimento_criado": frozenset({"chatId", "fluxoId"}),
    "atendimento_finalizado": frozenset({"chatId", "fluxoId", "destino", "motivoHandoff", "tokensGastos"}),
    "atendimento_expirado": frozenset({"chatId", "fluxoId"}),
    "atendimento_sem_checkpoint": frozenset({"fluxoId"}),
    "pergunta_enviada": frozenset({"fluxoId", "tipoResposta", "viaIA", "tokensGastosTotal"}),
    "resposta_recebida": frozenset({"chatId", "fluxoId"}),
    "ttl_confirmacao_solicitada": frozenset({"fluxoId"}),
    "verde_chamada": frozenset({"chamada", "resultado", "status", "tipoErro", "duracaoMs", "tentativa", "err"}),
    # Problemas e defeitos (tela Atendimento): a falha do e-mail ao NUDECON.
    "email_nudecon_falha": frozenset({"motivo", "status", "tentativa", "tipoErro"}),
    "orquestrador_fluxo_identificado": frozenset({"flowId", "tokensGastosTotal", "rodada"}),
    "orquestrador_redirecionado": frozenset({"destino", "tipoCaso", "tokensGastosTotal", "rodada"}),
    "orquestrador_finalizado_sem_fluxo": frozenset({"destino", "tipoCaso", "tokensGastosTotal", "rodada"}),
    "orquestrador_pergunta_enviada": frozenset({"tipoResposta", "tokensGastosTotal", "rodada"}),
    "orquestrador_inconsistencia": frozenset({"destino", "flowId"}),
    # O envio pelo WhatsApp (src/maria/integracoes/whatsapp.py e api/webhook_whatsapp.py).
    "whatsapp_envio_ok": frozenset(),
    "whatsapp_envio_falhou": frozenset({"status"}),
    "whatsapp_envio_erro": frozenset(),
    "whatsapp_bridge_erro": frozenset({"status"}),
    "whatsapp_status_entrega": frozenset({"status", "erroCodigo"}),
    # O tom da pergunta de desambiguação, só em números (maria-langgraph-pp #508; Observatório da IA, visor-maria#12).
    "desambiguacao_tom": frozenset(
        {
            "modelo",
            "palavras",
            "ateLimiteDePalavras",
            "terminaEmPergunta",
            "semTermoTecnico",
            "ofereceAlternativas",
            "temAcolhimento",
            "comEmoji",
            "emojiTirado",
            "temaSensivel",
        }
    ),
}

# Campos que chegam por fora do `evento=` e que o retrato do código não enxerga:
# `reqId` vem do logger da requisição (`LogRequisicao`, api/pipeline.py) em toda linha
# de uma rota, e `chatId` e `fluxoId` vêm de `**contexto_atual()` nas linhas do Verde e
# da IA. As ocorrências da tela Atendimento leem os três; conferência manual (10/11, develop).
CAMPOS_DE_FORA_DO_EVENTO: frozenset[str] = frozenset({"reqId", "chatId", "fluxoId"})

# Linhas sem `evento` que a fonte real lê pela mensagem (`msg`) ou pelo texto da
# linha, com os campos de cada uma. O retrato do código da Maria ainda não
# extrai mensagens: por enquanto a conferência destas é manual (26/10, develop).
MENSAGENS: dict[str, frozenset[str]] = {
    "incoming request": frozenset({"reqId", "req.url", "req.method"}),
    "request completed": frozenset({"reqId", "res.statusCode", "responseTime"}),
    # A linha de erro da requisição (api/pipeline.py, `_tratar`): a mensagem é o texto
    # da exceção e o painel não a lê; lê só o tipo e o código.
    "(erro da requisição)": frozenset({"reqId", "err.type", "err.code", "res.statusCode"}),
    "[plano-saude] falha inesperada no fluxo": frozenset({"level", "no", "tipoErro"}),
    "Application startup complete.": frozenset(),
    "[classificar] falha": frozenset({"level"}),
    "[desambiguar] falha": frozenset({"level"}),
    "[extrair] falha": frozenset({"level"}),
    "[reescrever] falha": frozenset({"level"}),
    "[sumarizar] falha": frozenset({"level"}),
}

# Linhas da conferência diária (verificar-token-verde.yml) que o painel procura.
LINHAS_DO_WORKFLOW: frozenset[str] = frozenset({"status atual:", "expiraEm=", "token renovado, gravado no Secrets Manager", "container novo no ar"})

# O que os logs de referência da Maria ainda não mostram. Eles são da versão
# TypeScript (16/10) e não têm esses eventos nem campos; o código da Maria tem.
# Quando a Maria gravar logs novos, o teste avisa para tirar daqui o que passou
# a aparecer.
FORA_DOS_LOGS_DE_REFERENCIA: dict[str, frozenset[str]] = {
    "atendimento_sem_checkpoint": frozenset({"*"}),
    "verde_chamada": frozenset({"*"}),
    "email_nudecon_falha": frozenset({"*"}),
    "orquestrador_redirecionado": frozenset({"*"}),
    "pergunta_enviada": frozenset({"tokensGastosTotal"}),
    "orquestrador_fluxo_identificado": frozenset({"tokensGastosTotal", "rodada"}),
    "orquestrador_finalizado_sem_fluxo": frozenset({"tokensGastosTotal", "rodada"}),
    "orquestrador_pergunta_enviada": frozenset({"tokensGastosTotal", "rodada"}),
    "orquestrador_inconsistencia": frozenset({"*"}),
    "whatsapp_envio_ok": frozenset({"*"}),
    "whatsapp_envio_falhou": frozenset({"*"}),
    "whatsapp_envio_erro": frozenset({"*"}),
    "whatsapp_bridge_erro": frozenset({"*"}),
    "whatsapp_status_entrega": frozenset({"erroCodigo"}),
    # Evento novo de 17/11 (#508): nenhum log de referência o tem.
    "desambiguacao_tom": frozenset({"*"}),
}
