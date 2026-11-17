"""A forma de toda leitura que uma tela mostra.

Todo número do painel chega como `Leitura`: o valor, de onde ele saiu e quando
foi lido. A tela nunca recebe um número solto, e por isso nunca mostra um número
sem a fonte e a hora ao lado (regra 3 do pedido de 2026-10-26).

Nenhum tipo daqui tem `chatId`, telefone, IP ou texto digitado: o painel nunca
identifica a conversa (regra 4, revista pela Nicole em 10/11). Os valores são
agregados, com uma exceção: as ocorrências de problema da tela Atendimento
(`Ocorrencia`), uma por linha, com a hora, a etapa e o código, sem nada que diga
de quem é a conversa.
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
class ValidadeConferida:
    """A validade que uma conferência diária leu no segredo, antes de renovar."""

    conferida_em: datetime
    valida_ate: datetime


@dataclass(frozen=True)
class Credencial:
    """A credencial do Verde de um ambiente, pela conferência diária. O painel
    nunca lê o segredo: a validade vem do log da conferência. `conferidas`, da
    mais velha para a mais nova: até quando valia a credencial em cada dia."""

    emitida_em: datetime | None
    valida_ate: datetime
    ultima_aceita: datetime | None
    ultima_conferencia: datetime | None
    conferencia_passou: bool | None
    conferidas: tuple[ValidadeConferida, ...] = ()


@dataclass(frozen=True)
class IncidenteDeCredencial:
    """Um bloco de recusas da credencial. `fim` None é incidente aberto;
    `atendimentos` (as conversas que bateram na recusa) None é "não medido"."""

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
    # Plano de saúde, o envio ao NUDECON (#405 e #423).
    "falha_envio_email": "Falha ao enviar o email",
    "imagens_nao_anexadas": "Imagens não anexadas ao email",
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


class EstadoDoAlarme(StrEnum):
    """O estado de um alarme do CloudWatch, com o valor que a AWS usa."""

    NORMAL = "OK"
    DISPARADO = "ALARM"
    SEM_DADO = "INSUFFICIENT_DATA"


class TipoDeAlarme(StrEnum):
    """Os alarmes de infra/alertas. O nome na AWS é visor-maria-<ambiente>-<tipo>."""

    SEM_HOST_SAUDAVEL = "sem-host-saudavel"
    ERROS_5XX = "erros-5xx"
    CPU_ALTA = "cpu-alta"
    LATENCIA_P99 = "latencia-p99"
    VERDE_RECUSOU = "verde-recusou"


PREFIXO_DOS_ALARMES = "visor-maria-"


@dataclass(frozen=True)
class Alarme:
    """Um alarme de infra/alertas: o estado de agora e quantas vezes disparou em 7 dias."""

    tipo: TipoDeAlarme
    ambiente: Ambiente
    estado: EstadoDoAlarme
    desde: datetime
    disparos_na_semana: int


def alarme_do_nome(nome: str) -> tuple[Ambiente, TipoDeAlarme] | None:
    """visor-maria-producao-cpu-alta vira (produção, cpu-alta). Nome de fora de infra/alertas: None."""
    if not nome.startswith(PREFIXO_DOS_ALARMES):
        return None
    ambiente, _, tipo = nome.removeprefix(PREFIXO_DOS_ALARMES).partition("-")
    try:
        return Ambiente(ambiente), TipoDeAlarme(tipo)
    except ValueError:
        return None


@dataclass(frozen=True)
class CpuELatencia:
    """Uma hora de um ambiente: a CPU média do serviço ECS (%) e a latência p99 do
    balanceador (s), os dois gráficos que o Grafana mostrava. None: a hora sem ponto."""

    hora: datetime
    ambiente: Ambiente
    cpu: float | None
    p99: float | None


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
    "falha_envio_email": TipoDeProblema.FALHA,
    "imagens_nao_anexadas": TipoDeProblema.FALHA,
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


# ── Problemas e defeitos (tela Atendimento) ───────────────────────────────
# Uma linha por ocorrência, para investigar bug (decisão da Nicole, 10/11): a regra
# 4 passou de "nunca listar conversa" para "nunca identificar a conversa". Nenhuma
# ocorrência traz `chatId`, telefone ou texto: o identificador da conversa só serve,
# dentro da fonte, para saber o que aconteceu com ela depois, e não sai de lá.

# Cada tipo: o nome, o tom e o que quer dizer, na ordem em que a tela mostra.
TIPOS_DE_OCORRENCIA: dict[str, tuple[str, str, str]] = {
    "erro_da_maria": ("Erro da Maria", "ruim", "A Maria quebrou ao responder (5xx). É bug no código: o tipo da exceção diz onde olhar."),
    "resposta_cortada": (
        "Resposta depois de 30 s",
        "ruim",
        "A Maria respondeu, mas depois dos 30 s em que o CloudFront corta: quem chamou não recebeu a resposta (#344).",
    ),
    "fluxo": ("Falha dentro do fluxo", "ruim", "Uma exceção dentro do fluxo, que encerrou a conversa com atendimento humano."),
    "email": ("Email ao NUDECON falhou", "ruim", "A função que envia o pedido ao NUDECON falhou, recusou ou passou do prazo."),
    "verde": (
        "O Verde falhou",
        "atencao",
        "A consulta ao Verde voltou com erro, recusa da credencial ou sem resposta. Não conta a pessoa ou o processo que não existem.",
    ),
    "ia": ("A IA falhou", "atencao", "Uma função de IA deu erro, e a Maria seguiu com o texto padrão ou sem o que ela daria."),
    "whatsapp": ("O WhatsApp falhou", "atencao", "O envio direto pelo WhatsApp foi recusado, deu erro ou a mensagem não chegou."),
    "conversa_cortada": ("Conversa cortada", "rosa", "A conversa perdeu onde estava (sem checkpoint), em geral numa troca de versão."),
    "triagem": ("A triagem se contradisse", "rosa", "A escrita livre apontou um fluxo que não existe no catálogo."),
    "recusa": (
        "Pedido recusado",
        "azul",
        "A Maria recusou o pedido (4xx): campo faltando, atendimento que não existe ou já encerrado. Pode ser erro de quem chama.",
    ),
}

# O que aconteceu com a conversa depois da ocorrência.
NOME_DO_DEPOIS = {
    "encerrou": "Encerrou",
    "seguiu": "A conversa seguiu",
    "expirou": "Expirou sem resposta",
    "parou": "A pessoa não respondeu mais",
    "recente": "Há menos de 30 min, ainda sem resposta",
    "ja_encerrada": "Já estava encerrada",
    "sem_conversa": "Sem conversa ligada",
}


def nome_da_ocorrencia(tipo: str) -> str:
    return TIPOS_DE_OCORRENCIA.get(tipo, (tipo.replace("_", " "), "", ""))[0]


@dataclass(frozen=True)
class Ocorrencia:
    """Um problema, como aconteceu: a hora, o tipo (chave de TIPOS_DE_OCORRENCIA),
    a etapa (a rota, a consulta ao Verde, a função de IA), o código (status HTTP,
    tipo da exceção, `tipoErro`), quanto demorou e o que aconteceu depois.

    `pedido` é o `reqId` da requisição, quando a linha tem um: é aleatório, não diz
    de quem é a conversa, e acha a linha inteira no CloudWatch."""

    hora: datetime
    tipo: str
    etapa: str
    codigo: str
    demora: float | None
    fluxo: str
    depois: str
    motivo: str = ""
    tentativa: str = ""
    pedido: str = ""


@dataclass(frozen=True)
class OcorrenciasDoPeriodo:
    """As ocorrências da janela, da mais nova à mais velha. `conversas` é quantas
    conversas tiveram pelo menos uma, contadas antes de o identificador sair da fonte;
    `cortada` diz que a consulta bateu o limite de linhas."""

    inicio: datetime
    fim: datetime
    ocorrencias: list[Ocorrencia]
    conversas: int
    cortada: bool = False


# ── Infra (tela Infra) ────────────────────────────────────────────────────
# Hora a hora, cada parte da infraestrutura por onde o atendimento passa. O banco,
# o proxy, a saída para a internet (NAT), o modelo de IA e a função de e-mail são
# os mesmos para os dois ambientes: o número deles é igual nos dois.


@dataclass(frozen=True)
class HoraDaInfra:
    """Uma hora de um ambiente. None: a métrica não mandou ponto nessa hora."""

    hora: datetime
    # A entrada (CloudFront): pedidos e respostas com erro.
    pedidos: int
    erros_5xx: int
    erros_4xx: int
    # O balanceador e os containers.
    p99: float | None
    saudaveis: float | None
    desejados: float | None
    cpu: float | None
    memoria: float | None
    reinicios: int
    # Compartilhados: o banco, a saída para a internet, o modelo de IA e o e-mail.
    banco_cpu: float | None
    banco_conexoes: float | None
    banco_memoria_livre: float | None
    saida_erros: int
    ia_recusas: int
    email_erros: int
    # O Verde, de fora da AWS, pelo que a Maria registrou neste ambiente.
    verde_falhas: int
    respostas_cortadas: int


class EstadoDaParte(StrEnum):
    BOM = "bom"
    ATENCAO = "atencao"
    RUIM = "ruim"
    SEM_USO = "sem_uso"


# As partes da infraestrutura, na ordem em que a mensagem passa: o nome, o que faz e
# se é a mesma nos dois ambientes.
PARTES_DA_INFRA: dict[str, tuple[str, str, bool]] = {
    "entrada": ("Entrada (CloudFront)", "recebe o pedido da Tykhe e repassa ao balanceador; corta em 30 s", False),
    "tempo": ("Tempo de resposta", "quanto a Maria leva para responder, pelo balanceador (p99)", False),
    "containers": ("Containers (ECS)", "rodam a Maria: no ar, CPU, memória e reinícios", False),
    "banco": ("Banco das conversas (RDS)", "guarda onde cada conversa parou", True),
    "saida": ("Saída para a internet (NAT)", "leva as consultas ao Verde e à Tykhe para fora da rede", True),
    "verde": ("Verde", "o sistema da Defensoria que a Maria consulta, fora da AWS", False),
    "ia": ("Modelo de IA (Bedrock)", "recusas e limitações do modelo, na conta inteira", True),
    "email": ("Email ao NUDECON (Lambda)", "a função que envia o pedido de plano de saúde", True),
}

# Os limites de cada estado, por hora. Decididos em 10/11 para começar e ajustáveis:
# ver docs/decisoes.md, "a tela Infra".
LIMITE_DO_CORTE_S = 30.0
LIMITE_DE_LENTIDAO_S = 10.0
LIMITE_DA_CPU = 80.0
LIMITE_DA_MEMORIA = 90.0
LIMITE_DA_CPU_DO_BANCO = (60.0, 80.0)


def estado_da_parte(parte: str, h: HoraDaInfra) -> EstadoDaParte:
    """O estado de uma parte numa hora, pelos limites acima."""
    e = EstadoDaParte
    if parte == "entrada":
        if not h.pedidos:
            return e.SEM_USO
        if h.erros_5xx >= 5 or h.erros_5xx / h.pedidos >= 0.05:
            return e.RUIM
        return e.ATENCAO if h.erros_5xx else e.BOM
    if parte == "tempo":
        if h.p99 is None:
            return e.SEM_USO
        if h.p99 >= LIMITE_DO_CORTE_S or h.respostas_cortadas:
            return e.RUIM
        return e.ATENCAO if h.p99 >= LIMITE_DE_LENTIDAO_S else e.BOM
    if parte == "containers":
        if h.saudaveis is None:
            return e.SEM_USO
        desejados = h.desejados or 1
        if h.saudaveis < 1:
            return e.RUIM
        if h.saudaveis < desejados or h.reinicios or (h.cpu or 0) >= LIMITE_DA_CPU or (h.memoria or 0) >= LIMITE_DA_MEMORIA:
            return e.ATENCAO
        return e.BOM
    if parte == "banco":
        if h.banco_cpu is None:
            return e.SEM_USO
        atencao, ruim = LIMITE_DA_CPU_DO_BANCO
        return e.RUIM if h.banco_cpu >= ruim else e.ATENCAO if h.banco_cpu >= atencao else e.BOM
    if parte == "saida":
        return e.RUIM if h.saida_erros >= 100 else e.ATENCAO if h.saida_erros else e.BOM
    if parte == "verde":
        return e.RUIM if h.verde_falhas >= 5 else e.ATENCAO if h.verde_falhas else e.BOM
    if parte == "ia":
        return e.RUIM if h.ia_recusas >= 10 else e.ATENCAO if h.ia_recusas else e.BOM
    if parte == "email":
        return e.RUIM if h.email_erros else e.BOM
    raise ValueError(f"parte desconhecida: {parte}")


# ── QA ────────────────────────────────────────────────────────────────────

# O QA de ponta a ponta do CI (maria-langgraph-pp #502) roda com o Verde, a IA e o
# e-mail simulados: não gasta nada. O QA da staging conversa com o release de verdade.
TIPOS_DE_RODADA = {"ponta_a_ponta": "Ponta a ponta (CI)", "staging": "QA da staging"}
# Teto de IA de cada rodada do QA da staging (decisão da Nicole, 16/11): passou, o QA para e avisa.
TETO_DA_RODADA = 0.10


@dataclass(frozen=True)
class RodadaDoQA:
    """Uma rodada de QA: quantas conferências passaram e o gasto de IA dela.

    `custo` é em dólares. No ponta a ponta é zero (tudo simulado); no QA da
    staging, é o que o roteiro somou pelos `tokensGastos`, no preço do Haiku (o
    teto seguro: o Qwen do release custa menos)."""

    quando: datetime
    tipo: str
    pr: int | None
    commit: str
    passaram: int
    total: int
    custo: float

    @property
    def passou(self) -> bool:
        return self.total > 0 and self.passaram == self.total


@dataclass(frozen=True)
class DefeitoDoQA:
    """Uma conferência que falhou numa rodada: o que a equipe precisa acertar.

    `detalhe` é o que o roteiro disse (o passo, o esperado e o que veio), sempre
    com dados inventados. `resolvido_em` é a primeira rodada seguinte do mesmo PR
    (ou da staging) que passou inteira; None enquanto o defeito está aberto."""

    quando: datetime
    tipo: str
    cenario: str
    detalhe: str
    pr: int | None
    commit: str
    resolvido_em: datetime | None = None


@dataclass(frozen=True)
class QA:
    rodadas: tuple[RodadaDoQA, ...]
    defeitos: tuple[DefeitoDoQA, ...]


@dataclass(frozen=True)
class AlertaDeCodigo:
    """Um alerta aberto do CodeQL: a regra, a gravidade e onde."""

    regra: str
    gravidade: str
    arquivo: str
    linha: int
    desde: datetime


# ── Tom da IA (maria-langgraph-pp #508) ───────────────────────────────────

# As versões da comparação, na ordem da tela.
VERSOES_DO_TOM = {"haiku": "Haiku (produção)", "qwen": "Qwen, sem o tom", "qwen_tom": "Qwen com o tom"}
REGRAS_DO_TOM = {
    "tem_acolhimento": "tem acolhimento",
    "ate_25_palavras": "até 25 palavras",
    "termina_em_pergunta": "termina em pergunta",
    "oferece_as_alternativas": "oferece as alternativas",
    "sem_termo_tecnico": "sem termo técnico",
    "sem_emoji_no_tema_sensivel": "sem emoji no tema sensível",
}


@dataclass(frozen=True)
class VersaoDoTom:
    """Uma versão da comparação: quantas perguntas passaram em cada regra automática."""

    versao: str
    perguntas: int
    regras: tuple[tuple[str, int], ...]
    palavras_em_media: float
    com_emoji: int
    custo: float


@dataclass(frozen=True)
class CasoDoTom:
    """Um relato inventado da comparação e a pergunta de cada versão (`perguntas`: versão e pergunta).
    `exemplo` é o relato inventado: nenhum é de atendimento real."""

    caso: int
    exemplo: str
    sensivel: bool
    perguntas: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class NotaDoTom:
    """A nota de uma pessoa da equipe para uma pergunta, de 1 a 5, sem saber de que versão ela era."""

    caso: int
    versao: str
    acolhedor: int
    simples: int
    por: str
    em: datetime


@dataclass(frozen=True)
class TomDaIA:
    rodado_em: datetime
    custo: float
    relatos: int
    passadas: int
    versoes: tuple[VersaoDoTom, ...]
    amostra: tuple[CasoDoTom, ...]
    notas: tuple[NotaDoTom, ...] = ()


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
