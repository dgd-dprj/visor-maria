"""A forma de toda leitura que uma tela mostra.

Todo número do painel chega como `Leitura`: o valor, de onde ele saiu e quando
foi lido. A tela nunca recebe um número solto, e por isso nunca mostra um número
sem a fonte e a hora ao lado (regra 3 do pedido de 2026-10-26).

Os valores são sempre agregados. Nenhum tipo daqui tem `chatId`, telefone, IP ou
texto digitado: o painel nunca lista conversa (levantamento de 23/10, seção 5).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")


class Ambiente(StrEnum):
    PRODUCAO = "producao"
    RELEASE = "release"


NOME_DO_AMBIENTE = {Ambiente.PRODUCAO: "Produção", Ambiente.RELEASE: "Release"}


class Origem(StrEnum):
    """De onde vêm os atendimentos. Produção se divide no corte de versão (23/10,
    12:31): os dois pedaços ficam separados, em vez de somados num número só."""

    PRODUCAO_TS = "producao_ts"
    PRODUCAO_PY = "producao_py"
    RELEASE = "release"


NOME_DA_ORIGEM = {
    Origem.PRODUCAO_TS: "Produção, TypeScript",
    Origem.PRODUCAO_PY: "Produção, Python",
    Origem.RELEASE: "Release",
}
AMBIENTE_DA_ORIGEM = {
    Origem.PRODUCAO_TS: Ambiente.PRODUCAO,
    Origem.PRODUCAO_PY: Ambiente.PRODUCAO,
    Origem.RELEASE: Ambiente.RELEASE,
}


class Estado(StrEnum):
    OK = "ok"
    # A consulta rodou e não achou nada. Cada quadro tem o seu texto para isso.
    VAZIO = "vazio"
    # A fonte não respondeu, ou falta permissão. `motivo` diz qual e de quem depende.
    INDISPONIVEL = "indisponivel"


@dataclass(frozen=True)
class Fonte:
    """De onde o número sai.

    `curto` vai ao lado do número ("logs de produção"); `nome` e `identificador`
    vão na lista "De onde vem cada número", no pé da tela. `identificador` é o
    nome técnico (grupo de logs, métrica), para conferir no CloudWatch.
    """

    curto: str
    nome: str
    identificador: str
    atraso: str


@dataclass(frozen=True)
class Leitura[T]:
    valor: T | None
    estado: Estado
    fonte: Fonte
    lido_em: datetime
    motivo: str | None = None


# ── Agora e Sistema ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class SaudeServico:
    hosts_saudaveis: int
    hosts_desejados: int


@dataclass(frozen=True)
class ResumoDoDia:
    """Desde 0h do dia, num ambiente."""

    comecaram: int
    terminaram: int
    consultas_verde: int
    aceitas_verde: int
    perguntas: int
    # Conversas que a troca de versão cortou (evento atendimento_sem_checkpoint).
    sem_checkpoint: int


@dataclass(frozen=True)
class TempoDeResposta:
    """Tempo de resposta da Maria nas últimas 24 horas, em segundos."""

    requisicoes: int
    metade_ate: float
    nove_em_dez_ate: float
    mais_lenta: float


@dataclass(frozen=True)
class DuracaoDoVerde:
    chamada: str
    consultas: int
    media: float
    maximo: float


@dataclass(frozen=True)
class ResultadoDoVerde:
    """Consultas ao Verde num período, pelo que cada resultado quer dizer.

    `nao_encontrado` só tem sentido ao lado de `credencial_recusada`: no
    incidente de 22/10, as buscas que não acharam a pessoa subiram porque a
    credencial tinha sido recusada, e não por falta de RG.
    """

    aceitas: int
    credencial_recusada: int
    erro_do_verde: int
    nao_encontrado: int


@dataclass(frozen=True)
class RespostasComErro:
    """Respostas 4xx e 5xx da Maria nas últimas 24 horas. A varredura de robôs
    (/.env, /.git/config, phpMyAdmin) é separada pelo caminho pedido."""

    de_gente: int
    de_robo: int
    de_servidor: int


@dataclass(frozen=True)
class TokensDoDia:
    dia: date
    entrada: int
    saida: int
    chamadas: int


@dataclass(frozen=True)
class Rotina:
    """Uma rotina automática do GitHub. `falhando_desde` é None quando a
    última execução passou."""

    nome: str
    desde: date
    passaram: int
    falharam: int
    falhando_desde: datetime | None
    canceladas: int = 0
    ultima_falha: datetime | None = None


@dataclass(frozen=True)
class DiaDoVerde:
    """Consultas ao Verde num dia. `recusadas` são as recusas da credencial
    (status 401 ou 403); `outras` são o resto, aberto em `nao_achou` (processo
    que não existe), `sem_resposta` (a consulta não voltou) e `erro_do_verde`."""

    dia: date
    aceitas: int
    recusadas: int
    outras: int
    nao_achou: int = 0
    sem_resposta: int = 0

    @property
    def erro_do_verde(self) -> int:
        """O Verde respondeu com erro dele: o que sobra das outras."""
        return max(self.outras - self.nao_achou - self.sem_resposta, 0)

    @property
    def total(self) -> int:
        return self.aceitas + self.recusadas + self.outras


# Os resultados de uma consulta ao Verde, na ordem dos gráficos:
# (campo de DiaDoVerde, nome, tom, o que quer dizer). Levantamento de 28/10.
RESULTADOS_DO_VERDE = (
    ("aceitas", "Respondeu", "bom", "O Verde atendeu a consulta. Inclui o RG sem pessoa: o Verde responde, só que vazio."),
    (
        "recusadas",
        "Credencial recusada",
        "ruim",
        "O Verde recusou a credencial da Maria (401 ou 403). É problema nosso: venceu, ou o container ficou com a antiga.",
    ),
    ("nao_achou", "Não achou o processo", "outro", "O número de processo não existe no Verde (400, 404 ou 422). Não é falha."),
    ("erro_do_verde", "Erro do Verde", "atencao", "O Verde respondeu com erro dele (500 ou 503). É problema do outro lado."),
    ("sem_resposta", "Sem resposta", "rosa", "A consulta não voltou: tempo esgotado ou falha de rede."),
)


# ── Credencial do Verde ───────────────────────────────────────────────────


@dataclass(frozen=True)
class Credencial:
    """A credencial do Verde de um ambiente, pela conferência diária. O painel
    nunca lê o segredo: a validade vem do log da conferência."""

    emitida_em: datetime | None
    valida_ate: datetime
    ultima_aceita: datetime | None
    ultima_conferencia: datetime | None
    conferencia_passou: bool | None


@dataclass(frozen=True)
class IncidenteDeCredencial:
    """Um bloco de recusas da credencial. `fim` None é incidente aberto;
    `atendimentos` None é "não medido"."""

    ambiente: Ambiente
    inicio: datetime
    fim: datetime | None
    recusadas: int
    atendimentos: int | None


@dataclass(frozen=True)
class Renovacao:
    """Uma renovação feita pela conferência diária."""

    ambiente: Ambiente
    momento: datetime
    container_novo_no_ar: bool


# ── Atendimento ───────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResumoDoPeriodo:
    inicio: datetime
    fim: datetime
    comecaram: int
    terminaram: int
    perguntas: int
    paradas: int


@dataclass(frozen=True)
class TrechoDeNaoEncontrado:
    """Encerramentos por "RG não encontrado" num trecho, com a credencial no
    mesmo trecho: os dois números nunca aparecem separados."""

    rotulo: str
    encerramentos: int
    nao_encontrado: int
    credencial: ResultadoDoVerde


@dataclass(frozen=True)
class ResumoDoOrquestrador:
    identificou: int
    era_da_tykhe: int
    nao_entendeu: int
    perguntou_de_novo: int


# ── Relatório do dia ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class SistemaNoDia:
    minutos_fora_do_ar: int
    reinicios: list[datetime] = field(default_factory=list)
    erros_de_servidor: int = 0
    subidas: int = 0
    testes_com_falha: int = 0


# ── Relatório da Aplicação (gasto) ────────────────────────────────────────


@dataclass(frozen=True)
class GastoDeIA:
    """Tokens contados pelo Bedrock num dia ou num mês, para a conta AWS inteira.

    `inicio` é o dia, ou o primeiro dia do mês. `lido` e `escrito` são os tokens
    de entrada e de saída do modelo de conversa; `busca`, os do modelo de
    embeddings (a busca por semelhança)."""

    inicio: date
    lido: int
    escrito: int
    busca: int


class Assunto(StrEnum):
    PESSOA_PRESA = "pessoa_presa"
    VIOLENCIA_DOMESTICA = "violencia_domestica"
    TRIAGEM = "triagem"
    # Fluxo que o painel não conhece pelo código (fluxo novo ou planejado).
    OUTROS = "outros"


NOME_DO_ASSUNTO = {
    Assunto.PESSOA_PRESA: "Pessoa presa",
    Assunto.VIOLENCIA_DOMESTICA: "Violência doméstica",
    Assunto.TRIAGEM: "Triagem por escrita livre",
    Assunto.OUTROS: "Outros assuntos",
}


@dataclass(frozen=True)
class GastoDoAssunto:
    """Tokens que a aplicação registrou num dia, por assunto, num ambiente.

    `lido` e `escrito` vêm do evento atendimento_finalizado: só entra o
    atendimento que terminou. `so_total` vem dos eventos orquestrador_*, que
    registram só o total, sem separar entrada de saída (#340 na Maria)."""

    assunto: Assunto
    atendimentos: int
    lido: int
    escrito: int
    so_total: int = 0


# ── Coluna da direita das telas ───────────────────────────────────────────


@dataclass(frozen=True)
class ContagemPorHora:
    """Atendimentos que começaram e terminaram numa hora (início da hora, Brasília)."""

    hora: datetime
    comecaram: int
    terminaram: int


@dataclass(frozen=True)
class ContagemPorDia:
    """Atendimentos que começaram e terminaram num dia de Brasília."""

    dia: date
    comecaram: int
    terminaram: int


@dataclass(frozen=True)
class Desfecho:
    """Como os atendimentos terminaram: o motivo do encaminhamento, ou "" sem motivo."""

    motivo: str
    atendimentos: int


# O nome de cada motivo de encaminhamento, como a pessoa lê. O código fica na
# lista de fontes; motivo novo aparece com o código, até entrar aqui.
NOME_DO_DESFECHO = {
    "origem_processo_nao_suportada": "Origem do processo não atendida",
    "sem_numero_processo": "Sem número de processo",
    "rg_nao_encontrado": "RG não encontrado",
    "falha_infra_verde": "Falha ao consultar o Verde",
    "dados_pessoa_nao_atendidos": "Pessoa fora do atendimento",
    "nome_nao_confirmado": "Nome não confirmado",
    # Violência doméstica e problemas com plano de saúde (release, levantamento de 28/10).
    "nao_e_vitima": "Não é a vítima",
    "municipio_nao_identificado": "Município não identificado",
    "situacao_nao_informada": "Situação não informada",
    "fora_do_rio": "Fora do estado do Rio",
    "imagens_pendentes": "Imagens pendentes",
    "outra_pessoa": "Pedido para outra pessoa",
    "dados_nao_confirmados": "Dados não confirmados",
    "canal_nao_entendido": "Canal não entendido",
    "renda_nao_entendida": "Renda não entendida",
    # Os outros motivos dos três fluxos (src/maria/fluxos/*/state.py, MotivoHandoff*).
    "cpf_nao_encontrado": "CPF não encontrado",
    "assistido_nao_confirmado": "Assistido não confirmado",
    "falha_cadastro": "Falha ao cadastrar",
    "falha_encaminhamento": "Falha ao encaminhar ao órgão",
    "sem_orgao_disponivel": "Nenhum órgão disponível",
    # A triagem por escrita livre que manda direto para atendimento humano, antes de um fluxo.
    "triagem_sem_fluxo": "A triagem não achou um fluxo",
    "triagem_inconsistente": "A triagem se contradisse",
    "": "Terminou sem motivo de encaminhamento",
}


def nome_do_desfecho(motivo: str) -> str:
    return NOME_DO_DESFECHO.get(motivo, motivo.replace("_", " "))


@dataclass(frozen=True)
class OrigemNaoAtendida:
    """O desfecho "origem do processo não atendida", aberto pelo que a consulta ao
    processo devolveu na mesma conversa (levantamento de 26/10)."""

    finalizados: int
    total: int
    processo_com_outra_origem: int
    processo_nao_encontrado: int
    consulta_falhou: int


@dataclass(frozen=True)
class RequisicoesPorHora:
    hora: datetime
    requisicoes: int
    erros_de_servidor: int


@dataclass(frozen=True)
class RecursosDoServico:
    """CPU e memória usadas, como fração do que a tarefa reserva."""

    cpu_agora: float
    cpu_maxima: float
    memoria_agora: float
    memoria_maxima: float


@dataclass(frozen=True)
class HorarioDaConferencia:
    """A que horas a conferência diária começou, contra o agendado (9h)."""

    dia: date
    comecou: datetime
    passou: bool


# ── Observatório da IA ────────────────────────────────────────────────────


@dataclass(frozen=True)
class ErroDaIA:
    """Falhas de uma função de IA da Maria: cada uma grava "[função] falha ..."."""

    funcao: str
    falhas: int


@dataclass(frozen=True)
class UsoDaIA:
    perguntas: int
    escritas_pela_ia: int


@dataclass(frozen=True)
class DiaDoModelo:
    """O modelo de conversa num dia, pelas métricas da AWS (conta inteira)."""

    dia: date
    chamadas: int
    erros_do_pedido: int
    erros_do_servico: int
    limitadas: int
    demora_media: float
    escritos_por_chamada: float


@dataclass(frozen=True)
class MudancaNaIA:
    """Um commit que mexeu no módulo de IA da Maria (src/maria/ia), em develop."""

    quando: datetime
    titulo: str
    codigo: str


@dataclass(frozen=True)
class TokensRegistrados:
    """Os tokens que as conversas da Maria registraram num dia, num ambiente: o
    texto lido e o escrito ao fim de cada atendimento, e a triagem, que só registra
    o total. Comparados com a medição da conta, dizem quanto do gasto é da Maria."""

    dia: date
    lido: int
    escrito: int
    so_total: int

    @property
    def total(self) -> int:
        return self.lido + self.escrito + self.so_total


# ── Fluxos ────────────────────────────────────────────────────────────────
# Tudo contado por conversa dentro da consulta: o identificador da conversa
# junta os eventos dela e nunca sai da consulta. Nenhum texto é lido.

# Os fluxos da Maria (src/maria/fluxos/__init__.py, develop em 28/10).
NOME_DO_FLUXO = {
    "3df874f2-675a-4c43-9ec7-480f7c702f50": "Pessoa presa",
    "cabb2495-4e12-4f4a-9956-3d20649059bc": "Violência doméstica",
    "84433c84-4776-4b05-a5a0-af8012d8eced": "Problemas com plano de saúde",
}

# Os tipos de caso que a triagem devolve à Tykhe (src/maria/fluxos/tipos_tykhe.py).
NOME_DO_TIPO_DE_CASO = {
    "saude": "Saúde",
    "novo-processo": "Novo processo",
    "andamento-processo": "Andamento de processo",
    "agendamentos": "Agendamentos",
    "ajuda-app": "Ajuda com o aplicativo",
    "outros": "Outros assuntos",
    "sair": "Pediu para sair",
}

# O que conta como problema no caminho de uma conversa: a chave é o evento, ou o
# motivo `falha_infra_verde` do encerramento.
NOME_DO_PROBLEMA = {
    "falha_infra_verde": "O Verde falhou, e a conversa foi encaminhada",
    "atendimento_expirado": "A conversa expirou sem resposta",
    "atendimento_sem_checkpoint": "A conversa foi cortada na troca de versão",
    "orquestrador_inconsistencia": "A triagem se contradisse",
    "whatsapp_envio_falhou": "O WhatsApp recusou a mensagem",
    "whatsapp_envio_erro": "Erro ao enviar ao WhatsApp",
    "whatsapp_status_entrega": "A mensagem não chegou à pessoa",
    "whatsapp_bridge_erro": "Erro na ponte com o WhatsApp",
}


def nome_do_fluxo(fluxo: str) -> str:
    """Fluxo novo aparece pelo começo do código, até entrar em NOME_DO_FLUXO."""
    return NOME_DO_FLUXO.get(fluxo, f"Fluxo {fluxo[:8]}" if fluxo else "Sem fluxo")


def nome_do_tipo_de_caso(tipo: str) -> str:
    return NOME_DO_TIPO_DE_CASO.get(tipo, tipo.replace("-", " ").replace("_", " ") or "Sem tipo")


class FimDaConversa(StrEnum):
    """Como uma conversa terminou, contada pela consulta."""

    CONCLUIU = "concluiu"
    ENCAMINHOU = "encaminhou"
    EXPIROU = "expirou"
    PAROU = "parou"


@dataclass(frozen=True)
class ConversasDoFluxo:
    """Conversas que começaram num fluxo, juntas pelo número de respostas que a
    pessoa deu e por como terminaram."""

    fluxo: str
    respostas: int
    fim: FimDaConversa
    conversas: int


@dataclass(frozen=True)
class DesfechoDoFluxo:
    """Encerramentos de um fluxo por motivo e destino ("" quando concluiu na Maria)."""

    fluxo: str
    motivo: str
    destino: str
    atendimentos: int


class SaidaDaTriagem(StrEnum):
    IDENTIFICOU = "identificou"
    REDIRECIONOU = "redirecionou"
    SEM_FLUXO = "sem_fluxo"
    PERGUNTOU = "perguntou"
    INCONSISTENCIA = "inconsistencia"


@dataclass(frozen=True)
class RodadaDaTriagem:
    """Como a triagem por escrita livre (o orquestrador) terminou uma rodada:
    `alvo` é o fluxo, o tipo de caso da Tykhe ou o destino."""

    saida: SaidaDaTriagem
    alvo: str
    vezes: int


@dataclass(frozen=True)
class FluxoNoDia:
    dia: date
    fluxo: str
    comecaram: int
    terminaram: int
    encaminhadas: int


@dataclass(frozen=True)
class ProblemaNoDia:
    """Problemas de um dia, por tipo (chave de NOME_DO_PROBLEMA) e fluxo ("" fora de um fluxo)."""

    dia: date
    problema: str
    fluxo: str
    vezes: int


# ── Atendimento humano (Relatório da Aplicação) ───────────────────────────


class Destino(StrEnum):
    """Para onde o atendimento foi, ao terminar (campo `destino` do encerramento)."""

    IA = "ia"
    HUMANO = "humano"
    SAIU = "saiu"


def destino_do_log(destino: str) -> Destino:
    """`atendimento_humano` vai para pessoa; `sessao_expirada` e `saida_manual`, a
    pessoa saiu; o resto (`agendamento`, vazio) a Maria resolveu sozinha."""
    if destino == "atendimento_humano":
        return Destino.HUMANO
    if destino in ("sessao_expirada", "saida_manual"):
        return Destino.SAIU
    return Destino.IA


@dataclass(frozen=True)
class EncaminhamentoNoDia:
    """Atendimentos que terminaram num dia, por fluxo ("" na triagem), destino e motivo."""

    dia: date
    fluxo: str
    destino: Destino
    motivo: str
    atendimentos: int


class TipoDeProblema(StrEnum):
    FALHA = "falha"
    IDENTIFICACAO = "identificacao"
    ENTENDIMENTO = "entendimento"
    FORA = "fora"
    SEM_MOTIVO = "sem_motivo"


# Cada tipo: o nome, o tom e o que quer dizer, em palavras de quem lê.
TIPOS_DE_PROBLEMA: dict[TipoDeProblema, tuple[str, str, str]] = {
    TipoDeProblema.FALHA: (
        "Falha técnica",
        "ruim",
        "Um sistema falhou no meio: o Verde, o cadastro ou o envio ao órgão. É problema nosso ou de quem a Maria chama, e dá para corrigir.",
    ),
    TipoDeProblema.IDENTIFICACAO: (
        "Pessoa ou processo não identificados",
        "atencao",
        "A Maria não localizou a pessoa ou o processo, ou a pessoa não confirmou os dados. Uma pessoa da equipe confere melhor.",
    ),
    TipoDeProblema.ENTENDIMENTO: (
        "A Maria não entendeu",
        "rosa",
        "A resposta da pessoa não deu para entender (canal, renda, município, situação) ou a triagem não achou o assunto.",
    ),
    TipoDeProblema.FORA: (
        "Fora do que a Maria atende",
        "azul",
        "O caso existe, mas a Maria não atende: outra origem de processo, outro estado, outra pessoa. Encaminhar é o caminho certo.",
    ),
    TipoDeProblema.SEM_MOTIVO: (
        "Sem motivo, ou motivo novo",
        "outro",
        "O encerramento foi para atendimento humano sem dizer por quê, ou com um motivo que o painel ainda não conhece (aparece com o código).",
    ),
}

TIPO_DO_MOTIVO: dict[str, TipoDeProblema] = {
    "falha_infra_verde": TipoDeProblema.FALHA,
    "falha_cadastro": TipoDeProblema.FALHA,
    "falha_encaminhamento": TipoDeProblema.FALHA,
    "sem_orgao_disponivel": TipoDeProblema.FALHA,
    "triagem_inconsistente": TipoDeProblema.FALHA,
    "rg_nao_encontrado": TipoDeProblema.IDENTIFICACAO,
    "cpf_nao_encontrado": TipoDeProblema.IDENTIFICACAO,
    "nome_nao_confirmado": TipoDeProblema.IDENTIFICACAO,
    "assistido_nao_confirmado": TipoDeProblema.IDENTIFICACAO,
    "dados_nao_confirmados": TipoDeProblema.IDENTIFICACAO,
    "sem_numero_processo": TipoDeProblema.IDENTIFICACAO,
    "canal_nao_entendido": TipoDeProblema.ENTENDIMENTO,
    "renda_nao_entendida": TipoDeProblema.ENTENDIMENTO,
    "situacao_nao_informada": TipoDeProblema.ENTENDIMENTO,
    "municipio_nao_identificado": TipoDeProblema.ENTENDIMENTO,
    "imagens_pendentes": TipoDeProblema.ENTENDIMENTO,
    "triagem_sem_fluxo": TipoDeProblema.ENTENDIMENTO,
    "origem_processo_nao_suportada": TipoDeProblema.FORA,
    "dados_pessoa_nao_atendidos": TipoDeProblema.FORA,
    "nao_e_vitima": TipoDeProblema.FORA,
    "fora_do_rio": TipoDeProblema.FORA,
    "outra_pessoa": TipoDeProblema.FORA,
}


def tipo_do_motivo(motivo: str) -> TipoDeProblema:
    """Motivo novo, que ainda não entrou na lista, conta como sem motivo até entrar."""
    return TIPO_DO_MOTIVO.get(motivo, TipoDeProblema.SEM_MOTIVO)


# As faixas de duração, do começo ao fim da conversa, na ordem dos gráficos.
FAIXAS_DE_DURACAO = {"ate2": "até 2 min", "ate5": "2 a 5 min", "ate15": "5 a 15 min", "ate60": "15 min a 1 h", "mais": "mais de 1 h"}


@dataclass(frozen=True)
class DuracaoDasConversas:
    """Conversas que terminaram, por fluxo e faixa de duração (chave de FAIXAS_DE_DURACAO)."""

    fluxo: str
    faixa: str
    conversas: int


@dataclass(frozen=True)
class EnvioDoWhatsapp:
    """Envios ao WhatsApp por resultado (o evento) e código (HTTP ou do WhatsApp)."""

    evento: str
    codigo: str
    vezes: int


def juntar[T, R](leituras: Sequence[Leitura[T]], combinar: Callable[[list[T]], R]) -> Leitura[R]:
    """Uma leitura feita de várias (os dias de um mês, por exemplo).

    Uma falha faz o todo falhar, com o motivo dela: um total sem um dos dias
    seria um número errado. A hora é a da leitura mais nova, porque as outras são
    de janelas já fechadas, que não mudam depois de fechar (dados/consultas.py).
    """
    if not leituras:
        raise ValueError("juntar precisa de pelo menos uma leitura")
    lido_em = max(leitura.lido_em for leitura in leituras)
    falha = next((leitura for leitura in leituras if leitura.estado is Estado.INDISPONIVEL), None)
    if falha is not None:
        return Leitura(None, Estado.INDISPONIVEL, falha.fonte, lido_em, falha.motivo)
    valores = [leitura.valor for leitura in leituras if leitura.estado is Estado.OK and leitura.valor is not None]
    if not valores:
        return Leitura(None, Estado.VAZIO, leituras[0].fonte, lido_em)
    return Leitura(combinar(valores), Estado.OK, leituras[0].fonte, lido_em)
