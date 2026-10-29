"""A fonte real: CloudWatch (logs e métricas) e GitHub, só leitura e só agregado.

Cada consulta devolve contagens, somas e horários. Nenhuma traz `chatId`, IP,
telefone ou texto digitado: quando um identificador entra numa consulta, é só
para contar (`count_distinct`) ou para ligar duas linhas da mesma requisição, e
nunca sai dela. Nada lê o banco (#309) nem o segredo da credencial do Verde: a
validade vem do log da conferência diária.

Credenciais: as da máquina ou da tarefa, pela cadeia padrão do boto3 (na máquina
da Nicole, o perfil padrão). O GitHub usa `GITHUB_TOKEN` ou, sem ele, o login do
`gh` da máquina.

Os dias são os de Brasília (UTC menos 3 horas, sem horário de verão desde 2019).
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
import time as relogio
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    CredentialRetrievalError,
    LoginError,
    NoCredentialsError,
    PartialCredentialsError,
    SSOError,
    TokenRetrievalError,
)

from painel.dados import fontes
from painel.dados.cache import CacheEmDisco
from painel.dados.modelo import (
    AMBIENTE_DA_ORIGEM,
    FUSO,
    Ambiente,
    Assunto,
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
    Estado,
    FimDaConversa,
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
    SaidaDaTriagem,
    SaudeServico,
    SistemaNoDia,
    TempoDeResposta,
    TokensDoDia,
    TokensRegistrados,
    TrechoDeNaoEncontrado,
    UsoDaIA,
    destino_do_log,
)

registro = logging.getLogger(__name__)

REGIAO = "us-east-1"
REPOSITORIO = "dgd-dprj/maria-langgraph-pp"
CLUSTER = "maria-langgraph-pp"
INICIO_DAS_ROTINAS = date(2026, 9, 19)
# Produção passou a rodar a versão Python em 23/10, às 12:31; o incidente da
# credencial de produção foi de 22/10, 13:27, até 23/10, 12:34 (levantamento de 23/10).
CORTE_DE_VERSAO = datetime(2026, 10, 23, 12, 31, tzinfo=FUSO)
INICIO_DO_TYPESCRIPT = datetime(2026, 10, 16, tzinfo=FUSO)
INICIO_DO_INCIDENTE = datetime(2026, 10, 22, 13, 27, tzinfo=FUSO)
# Códigos de fluxo da Maria (src/maria/fluxos/__init__.py, develop em 26/10).
ASSUNTO_DO_FLUXO = {
    "3df874f2-675a-4c43-9ec7-480f7c702f50": Assunto.PESSOA_PRESA,
    "cabb2495-4e12-4f4a-9956-3d20649059bc": Assunto.VIOLENCIA_DOMESTICA,
}
EVENTOS_DO_ORQUESTRADOR = (
    "orquestrador_fluxo_identificado",
    "orquestrador_redirecionado",
    "orquestrador_finalizado_sem_fluxo",
    "orquestrador_pergunta_enviada",
)
# Um bloco de recusas só vira incidente a partir de 3 recusas: uma recusa solta
# (credencial trocando no meio de uma consulta) não é incidente.
RECUSAS_PARA_INCIDENTE = 3
ESPERA_DA_CONSULTA = 60.0
ROTINAS = {
    "ci.yml": "Testes a cada mudança",
    "deploy-release.yml": "Subidas no release",
    "deploy-prod.yml": "Subidas em produção",
    "verificar-token-verde.yml": "Conferência diária da credencial",
}
# Os eventos que são problema por si (o encerramento por falha do Verde e o aviso de entrega
# com falha entram à parte, na consulta).
PROBLEMAS_POR_EVENTO = (
    "atendimento_expirado",
    "atendimento_sem_checkpoint",
    "orquestrador_inconsistencia",
    "whatsapp_envio_falhou",
    "whatsapp_envio_erro",
    "whatsapp_bridge_erro",
)
FUNCOES_DE_IA = ("classificar", "desambiguar", "extrair", "reescrever", "sumarizar")
SUBIDAS_DO = {Ambiente.PRODUCAO: "deploy-prod.yml", Ambiente.RELEASE: "deploy-release.yml"}
NOME_NA_CONFERENCIA = {Ambiente.PRODUCAO: "prod", Ambiente.RELEASE: "release"}


# Sem credencial na máquina, ou com o login vencido: é o caso de quem acabou de
# baixar o painel, e a tela diz o que fazer em vez de "a fonte não respondeu".
SEM_CREDENCIAL_DA_AWS = "Esta máquina não tem credencial da AWS, ou o login venceu. Faça o login e reinicie o painel (README, em Primeira vez)."
ERROS_DE_CREDENCIAL = (NoCredentialsError, PartialCredentialsError, CredentialRetrievalError, TokenRetrievalError, SSOError, LoginError)
CODIGOS_DE_CREDENCIAL = ("ExpiredToken", "ExpiredTokenException", "UnrecognizedClientException", "InvalidClientTokenId", "InvalidSignatureException")


class FalhaDeLeitura(Exception):
    """A fonte respondeu, mas não com o que a consulta precisa. A mensagem vai à tela."""


# ── Tempo ─────────────────────────────────────────────────────────────────


def inicio_do_dia(dia: date) -> datetime:
    return datetime.combine(dia, time(), tzinfo=FUSO)


def no_dia(dia: date, agora: datetime) -> tuple[datetime, datetime]:
    """O dia escolhido na tela, de 0h a 24h em Brasília, ou até agora se for hoje. Com
    a hora escolhida, `dia` é o começo dela (um `datetime`), e a janela é essa hora."""
    if isinstance(dia, datetime):
        return dia, min(dia + timedelta(hours=1), agora)
    return inicio_do_dia(dia), min(inicio_do_dia(dia + timedelta(days=1)), agora)


def o_dia(dia: date) -> date:
    """O dia de um `dia` que pode ser o começo de uma hora."""
    return dia.astimezone(FUSO).date() if isinstance(dia, datetime) else dia


def _instante(texto: str) -> datetime:
    """ "2026-10-25 15:25:19.991", em UTC, como o Logs Insights devolve."""
    return datetime.strptime(texto[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC).astimezone(FUSO)


def _inteiro(linha: dict[str, str], campo: str) -> int:
    valor = linha.get(campo)
    return int(float(valor)) if valor not in (None, "") else 0


def _real(linha: dict[str, str], campo: str) -> float:
    valor = linha.get(campo)
    return float(valor) if valor not in (None, "") else 0.0


# ── GitHub ────────────────────────────────────────────────────────────────


class _SemAutorizacaoNoDesvio(urllib.request.HTTPRedirectHandler):
    """O log de uma execução mora noutro endereço (armazenamento do GitHub), que
    recusa o cabeçalho de autorização da API: ele não segue no desvio."""

    def redirect_request(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> urllib.request.Request | None:
        novo = super().redirect_request(req, fp, code, msg, headers, newurl)
        if novo is not None:
            novo.remove_header("Authorization")
        return novo


class GitHub:
    def __init__(self, repositorio: str = REPOSITORIO) -> None:
        self._repositorio = repositorio
        self._token: str | None = None
        self._trava_da_chave = threading.Lock()
        self._abrir = urllib.request.build_opener(_SemAutorizacaoNoDesvio)
        # No máximo 3 pedidos ao mesmo tempo: mais que isso dispara o limite secundário do GitHub.
        self._vagas = threading.BoundedSemaphore(3)

    def _chave(self) -> str:
        # Com trava: duas leituras ao mesmo tempo não podem ver a chave pela metade (vazia).
        with self._trava_da_chave:
            if not self._token:
                token = os.environ.get("GITHUB_TOKEN") or ""
                if not token:
                    try:
                        token = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True, timeout=10).stdout.strip()
                    except (OSError, subprocess.SubprocessError):
                        token = ""
                if not token:
                    raise FalhaDeLeitura("Sem acesso ao GitHub: falta o GITHUB_TOKEN, e o gh desta máquina não tem login.")
                self._token = token
            return self._token

    def _pedir(self, caminho: str, parametros: dict[str, Any] | None = None) -> bytes:
        endereco = f"https://api.github.com/repos/{self._repositorio}/{caminho}"
        if parametros:
            endereco += "?" + urllib.parse.urlencode(parametros)
        for tentativa in range(3):
            pedido = urllib.request.Request(endereco, headers={"Authorization": f"Bearer {self._chave()}", "Accept": "application/vnd.github+json"})
            try:
                with self._vagas, self._abrir.open(pedido, timeout=30) as resposta:
                    return resposta.read()  # type: ignore[no-any-return]
            except urllib.error.HTTPError as erro:
                # 403 e 429 com limite de uso: espera o que o GitHub pedir e tenta de novo.
                if erro.code not in (403, 429) or tentativa == 2:
                    registro.warning("GitHub respondeu %s em %s", erro.code, caminho.split("?")[0])
                    raise
                relogio.sleep(min(float(erro.headers.get("Retry-After") or 2 ** (tentativa + 1)), 20))
        raise AssertionError("inalcançável")

    def json(self, caminho: str, parametros: dict[str, Any] | None = None) -> Any:
        import json

        return json.loads(self._pedir(caminho, parametros))

    def texto(self, caminho: str) -> str:
        return self._pedir(caminho).decode("utf-8", "replace")

    def execucoes(self, rotina: str, desde: date) -> list[dict[str, Any]]:
        """As execuções de uma rotina desde o dia, da mais nova para a mais velha.

        A primeira página diz quantas são; as outras vão juntas (cada página de
        100 leva uns 3 segundos). O GitHub entrega no máximo 1000 por filtro."""

        def pagina(numero: int) -> Any:
            return self.json(f"actions/workflows/{rotina}/runs", {"per_page": 100, "page": numero, "created": f">={desde.isoformat()}"})

        primeira = pagina(1)
        todas: list[dict[str, Any]] = primeira.get("workflow_runs", [])
        paginas = min(-(-primeira.get("total_count", 0) // 100), 10)
        if paginas > 1 and todas:
            with ThreadPoolExecutor(max_workers=3) as grupo:
                for parte in grupo.map(pagina, range(2, paginas + 1)):
                    todas += parte.get("workflow_runs", [])
        return todas


# ── A fonte ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class _LinhasDaConferencia:
    """O que o log de um job da conferência diária disse, para um ambiente."""

    concluido_em: datetime | None
    passou: bool
    valida_ate: datetime | None
    renovada_em: datetime | None
    container_novo_no_ar: bool


LINHA_DE_STATUS = re.compile(r"^(\S+)Z \[(prod|release)\] status atual: .*expiraEm=(\S+)")
LINHA_DE_RENOVACAO = re.compile(r"^(\S+)Z \[(prod|release)\] token renovado, gravado no Secrets Manager")
LINHA_DO_CONTAINER = re.compile(r"^(\S+)Z \[(prod|release)\] container novo no ar")


def _hora_do_github(texto: str) -> datetime:
    return datetime.strptime(texto[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=UTC).astimezone(FUSO)


class FonteReal:
    nome = "real"

    def __init__(self, cache: CacheEmDisco, agora: Callable[[], datetime] | None = None, github: GitHub | None = None) -> None:
        self._agora = agora or (lambda: datetime.now(FUSO))
        self._cache = cache
        self._github = github or GitHub()
        configuracao = Config(retries={"max_attempts": 3, "mode": "standard"}, max_pool_connections=20)
        sessao = boto3.Session(region_name=REGIAO)
        self._logs = sessao.client("logs", config=configuracao)
        self._metricas = sessao.client("cloudwatch", config=configuracao)
        self._trava = threading.Lock()
        self._trava_das_conferencias = threading.Lock()
        self._conferencias_lidas: tuple[float, dict[Ambiente, list[_LinhasDaConferencia]]] | None = None
        self._dimensoes: dict[Ambiente, list[dict[str, str]]] = {}
        self._bedrock: tuple[float, dict[date, GastoDeIA]] | None = None

    # ── Leitura com estado ────────────────────────────────────────────────

    def _ler[T](self, fonte: Fonte, gerar: Callable[[datetime], T | None]) -> Leitura[T]:
        momento = self._agora()
        try:
            valor = gerar(momento)
        except FalhaDeLeitura as erro:
            return Leitura(None, Estado.INDISPONIVEL, fonte, momento, str(erro))
        except ClientError as erro:
            codigo = erro.response.get("Error", {}).get("Code", "")
            registro.warning("leitura recusada: %s (%s)", fonte.nome, codigo)
            negado = "AccessDenied" in codigo or "Unauthorized" in codigo
            motivo = "Falta permissão de leitura nesta fonte (pedido ao Ícaro)." if negado else "A AWS recusou a consulta agora."
            if codigo in CODIGOS_DE_CREDENCIAL:
                motivo = SEM_CREDENCIAL_DA_AWS
            return Leitura(None, Estado.INDISPONIVEL, fonte, momento, motivo)
        except ERROS_DE_CREDENCIAL as erro:
            registro.warning("leitura sem credencial da AWS: %s (%s)", fonte.nome, type(erro).__name__)
            return Leitura(None, Estado.INDISPONIVEL, fonte, momento, SEM_CREDENCIAL_DA_AWS)
        except (BotoCoreError, OSError, TimeoutError) as erro:
            registro.warning("leitura falhou: %s (%s)", fonte.nome, type(erro).__name__)
            return Leitura(None, Estado.INDISPONIVEL, fonte, momento, "A fonte não respondeu.")
        except Exception:
            # Resposta num formato que o painel não esperava: o quadro avisa, a tela segue.
            registro.exception("leitura com resposta inesperada: %s", fonte.nome)
            return Leitura(None, Estado.INDISPONIVEL, fonte, momento, "A resposta da fonte veio num formato que o painel não conhece.")
        if valor is None:
            return Leitura(None, Estado.VAZIO, fonte, momento)
        return Leitura(valor, Estado.OK, fonte, momento)

    # ── Logs Insights ─────────────────────────────────────────────────────

    def _consultar(self, ambientes: Iterable[Ambiente], inicio: datetime, fim: datetime, consulta: str, limite: int = 1000) -> list[dict[str, str]]:
        grupos = [fontes.GRUPO_DE_LOGS[a] for a in ambientes]
        inicio = max(inicio, self._agora() - timedelta(days=fontes.DIAS_DO_REGISTRO))
        if fim <= inicio:
            return []
        qid = self._logs.start_query(logGroupNames=grupos, startTime=int(inicio.timestamp()), endTime=int(fim.timestamp()), queryString=consulta, limit=limite)[
            "queryId"
        ]
        prazo = relogio.monotonic() + ESPERA_DA_CONSULTA
        espera = 0.5
        while relogio.monotonic() < prazo:
            resposta = self._logs.get_query_results(queryId=qid)
            if resposta["status"] == "Complete":
                return [{c["field"]: c["value"] for c in linha if c["field"] != "@ptr"} for linha in resposta["results"]]
            if resposta["status"] in ("Failed", "Cancelled", "Timeout"):
                raise FalhaDeLeitura("A consulta aos logs falhou.")
            relogio.sleep(espera)
            espera = min(espera * 1.5, 3.0)
        try:
            self._logs.stop_query(queryId=qid)
        except ClientError:
            pass
        raise FalhaDeLeitura("A consulta aos logs passou de 60 segundos.")

    def _uma(self, ambientes: Iterable[Ambiente], inicio: datetime, fim: datetime, consulta: str) -> dict[str, str]:
        linhas = self._consultar(ambientes, inicio, fim, consulta)
        return linhas[0] if linhas else {}

    # ── Métricas ──────────────────────────────────────────────────────────

    def _serie(
        self, namespace: str, metrica: str, dimensoes: list[dict[str, str]], estatistica: str, periodo: int, inicio: datetime, fim: datetime
    ) -> list[tuple[datetime, float]]:
        resposta = self._metricas.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": "m",
                    "MetricStat": {"Metric": {"Namespace": namespace, "MetricName": metrica, "Dimensions": dimensoes}, "Period": periodo, "Stat": estatistica},
                }
            ],
            StartTime=inicio,
            EndTime=fim,
            ScanBy="TimestampAscending",
        )
        resultado = resposta["MetricDataResults"][0]
        return [(t.astimezone(FUSO), float(v)) for t, v in zip(resultado["Timestamps"], resultado["Values"], strict=True)]

    def _dimensoes_do_balanceador(self, ambiente: Ambiente) -> list[dict[str, str]]:
        """TargetGroup e LoadBalancer pela lista de métricas: a descrição do
        balanceador é negada a esta credencial (levantamento de 26/10)."""
        with self._trava:
            if ambiente not in self._dimensoes:
                prefixo = f"targetgroup/{fontes.TARGET_GROUP[ambiente]}/"
                metricas = self._metricas.list_metrics(Namespace="AWS/ApplicationELB", MetricName="HealthyHostCount")["Metrics"]
                for m in metricas:
                    nomes = {d["Name"]: d["Value"] for d in m["Dimensions"]}
                    if nomes.get("TargetGroup", "").startswith(prefixo) and "LoadBalancer" in nomes and len(nomes) == 2:
                        self._dimensoes[ambiente] = [
                            {"Name": "TargetGroup", "Value": nomes["TargetGroup"]},
                            {"Name": "LoadBalancer", "Value": nomes["LoadBalancer"]},
                        ]
                        break
                else:
                    raise FalhaDeLeitura("O balanceador deste ambiente não aparece nas métricas.")
            return self._dimensoes[ambiente]

    def _servico(self, ambiente: Ambiente) -> list[dict[str, str]]:
        return [{"Name": "ClusterName", "Value": CLUSTER}, {"Name": "ServiceName", "Value": fontes.SERVICO_ECS[ambiente]}]

    def _ultimo(self, serie: list[tuple[datetime, float]]) -> float | None:
        return serie[-1][1] if serie else None

    # ── Agora ─────────────────────────────────────────────────────────────

    def saude_servico(self, ambiente: Ambiente) -> Leitura[SaudeServico]:
        def gerar(agora: datetime) -> SaudeServico:
            saudaveis = self._ultimo(
                self._serie(
                    "AWS/ApplicationELB", "HealthyHostCount", self._dimensoes_do_balanceador(ambiente), "Minimum", 60, agora - timedelta(minutes=10), agora
                )
            )
            if saudaveis is None:
                raise FalhaDeLeitura("O balanceador não mandou a contagem nos últimos 10 minutos.")
            desejados = self._ultimo(
                self._serie("ECS/ContainerInsights", "DesiredTaskCount", self._servico(ambiente), "Maximum", 60, agora - timedelta(minutes=10), agora)
            )
            return SaudeServico(int(saudaveis), int(desejados) if desejados is not None else 1)

        return self._ler(fontes.fonte_saude_servico(ambiente), gerar)

    def implantacoes_em_curso(self, ambiente: Ambiente) -> Leitura[int]:
        def gerar(agora: datetime) -> int:
            valor = self._ultimo(
                self._serie("ECS/ContainerInsights", "DeploymentCount", self._servico(ambiente), "Maximum", 60, agora - timedelta(minutes=10), agora)
            )
            if valor is None:
                raise FalhaDeLeitura("O ECS não mandou a contagem de implantações nos últimos 10 minutos.")
            return int(valor)

        return self._ler(fontes.fonte_implantacoes(ambiente), gerar)

    def ultimo_reinicio(self, ambiente: Ambiente) -> Leitura[datetime]:
        def gerar(agora: datetime) -> datetime | None:
            linha = self._uma(
                [ambiente], agora - timedelta(days=30), agora, "filter @message like /Application startup complete/ | stats max(@timestamp) as ultima"
            )
            return _instante(linha["ultima"]) if linha.get("ultima") else None

        return self._ler(fontes.fonte_ultimo_reinicio(ambiente), gerar)

    def resumo_do_dia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[ResumoDoDia]:
        def gerar(agora: datetime) -> ResumoDoDia:
            linha = self._uma(
                [ambiente],
                *no_dia(dia or agora.date(), agora),
                'filter evento in ["atendimento_criado", "atendimento_finalizado", "verde_chamada", "pergunta_enviada", "atendimento_sem_checkpoint"]'
                ' | stats sum(evento = "atendimento_criado") as comecaram, sum(evento = "atendimento_finalizado") as terminaram,'
                ' sum(evento = "verde_chamada") as consultas, sum(evento = "verde_chamada" and resultado = "sucesso") as aceitas,'
                ' sum(evento = "pergunta_enviada") as perguntas, sum(evento = "atendimento_sem_checkpoint") as sem_checkpoint',
            )
            campos = ("comecaram", "terminaram", "consultas", "aceitas", "perguntas", "sem_checkpoint")
            return ResumoDoDia(*(_inteiro(linha, c) for c in campos))

        return self._ler(fontes.fonte_resumo_do_dia(ambiente, dia), gerar)

    # ── GitHub: conferência diária, rotinas, renovações ───────────────────

    def _linhas_da_conferencia(self, job: dict[str, Any], ambiente: Ambiente) -> _LinhasDaConferencia:
        """O que um job terminado disse. Job terminado não muda: fica guardado sem prazo."""
        chave = f"real:conferencia:{job['id']}"
        guardado = self._cache.ler(chave, self._agora())
        if isinstance(guardado, _LinhasDaConferencia):
            return guardado
        valida_ate = renovada_em = None
        container = False
        nome = NOME_NA_CONFERENCIA[ambiente]
        try:
            texto = self._github.texto(f"actions/jobs/{job['id']}/logs")
        except urllib.error.HTTPError as erro:
            # O GitHub apaga o log com o tempo (410) ou não o tem (404): a execução
            # conta, sem as linhas. Outro erro sobe e vira "não deu para ler".
            if erro.code not in (404, 410):
                raise
            texto = ""
        # Só três linhas interessam; o resto do log nunca sai desta função.
        for linha in texto.splitlines():
            if (achou := LINHA_DE_STATUS.match(linha)) and achou.group(2) == nome:
                # "expiraEm=None": o token não dizia a validade naquele dia.
                try:
                    valida_ate = datetime.fromisoformat(achou.group(3)).astimezone(FUSO)
                except ValueError:
                    valida_ate = None
            elif (achou := LINHA_DE_RENOVACAO.match(linha)) and achou.group(2) == nome:
                renovada_em = _hora_do_github(achou.group(1))
            elif (achou := LINHA_DO_CONTAINER.match(linha)) and achou.group(2) == nome:
                container = True
        concluido = _hora_do_github(job["completed_at"]) if job.get("completed_at") else None
        resultado = _LinhasDaConferencia(concluido, job.get("conclusion") == "success", valida_ate, renovada_em, container)
        if job.get("status") == "completed":
            self._cache.gravar(chave, resultado, None)
        return resultado

    def _conferencias(self, ambiente: Ambiente) -> list[_LinhasDaConferencia]:
        """As conferências diárias desde 19/09 para um ambiente, da mais nova para a mais velha.

        A credencial dos dois ambientes e as renovações saem da mesma varredura,
        feita uma vez a cada 5 minutos: quem chega durante a varredura espera por
        ela, em vez de repetir os pedidos ao GitHub."""
        with self._trava_das_conferencias:
            if self._conferencias_lidas is None or relogio.monotonic() - self._conferencias_lidas[0] > 300:
                self._conferencias_lidas = (relogio.monotonic(), self._varrer_conferencias())
            return self._conferencias_lidas[1][ambiente]

    def _varrer_conferencias(self) -> dict[Ambiente, list[_LinhasDaConferencia]]:
        execucoes = [e for e in self._github.execucoes("verificar-token-verde.yml", INICIO_DAS_ROTINAS) if e.get("status") == "completed"]

        def jobs(execucao: dict[str, Any]) -> list[dict[str, Any]]:
            # Execução terminada não muda: a lista de jobs fica guardada sem prazo.
            chave = f"real:jobs:{execucao['id']}"
            guardados = self._cache.ler(chave, self._agora())
            if isinstance(guardados, list):
                return guardados
            lista: list[dict[str, Any]] = self._github.json(f"actions/runs/{execucao['id']}/jobs").get("jobs", [])
            self._cache.gravar(chave, lista, None)
            return lista

        with ThreadPoolExecutor(max_workers=3) as grupo:
            todos = list(grupo.map(jobs, execucoes))
            resultado: dict[Ambiente, list[_LinhasDaConferencia]] = {}
            for ambiente in Ambiente:
                nome = NOME_NA_CONFERENCIA[ambiente]
                do_ambiente = [next((j for j in lista if f"({nome}," in j.get("name", "")), None) for lista in todos]
                resultado[ambiente] = list(grupo.map(lambda job, a=ambiente: self._linhas_da_conferencia(job, a), [j for j in do_ambiente if j]))
        return resultado

    def credencial(self, ambiente: Ambiente) -> Leitura[Credencial]:
        def gerar(agora: datetime) -> Credencial:
            conferencias = self._conferencias(ambiente)
            com_validade = next((c for c in conferencias if c.valida_ate is not None), None)
            if com_validade is None or com_validade.valida_ate is None:
                raise FalhaDeLeitura("Nenhuma conferência diária desde 19/09 imprimiu a validade deste ambiente.")
            emitida = next((c.renovada_em for c in conferencias if c.renovada_em is not None), None)
            linha = self._uma(
                [ambiente], agora - timedelta(days=30), agora, 'filter evento = "verde_chamada" and resultado = "sucesso" | stats max(@timestamp) as ultima'
            )
            ultima = conferencias[0] if conferencias else None
            return Credencial(
                emitida_em=emitida,
                valida_ate=com_validade.valida_ate,
                ultima_aceita=_instante(linha["ultima"]) if linha.get("ultima") else None,
                ultima_conferencia=ultima.concluido_em if ultima else None,
                conferencia_passou=ultima.passou if ultima else None,
            )

        return self._ler(fontes.fonte_credencial(ambiente), gerar)

    def rotinas(self) -> Leitura[list[Rotina]]:
        def gerar(_: datetime) -> list[Rotina]:
            # As quatro rotinas vão juntas: em fila, a tela esperava a soma delas.
            with ThreadPoolExecutor(max_workers=len(ROTINAS)) as grupo:
                todas = list(grupo.map(lambda arquivo: self._github.execucoes(arquivo, INICIO_DAS_ROTINAS), ROTINAS))
            resultado = []
            for (_arquivo, nome), da_rotina in zip(ROTINAS.items(), todas, strict=True):
                execucoes = [e for e in da_rotina if e.get("status") == "completed"]
                passaram = sum(e.get("conclusion") == "success" for e in execucoes)
                falharam = sum(e.get("conclusion") == "failure" for e in execucoes)
                canceladas = sum(e.get("conclusion") == "cancelled" for e in execucoes)
                falhas = [e for e in execucoes if e.get("conclusion") == "failure"]
                falhando_desde = None
                # Da mais nova para trás: enquanto falha, recua o começo da sequência.
                for e in execucoes:
                    if e.get("conclusion") == "failure":
                        falhando_desde = _hora_do_github(e["created_at"])
                    elif e.get("conclusion") == "success":
                        break
                ultima_falha = _hora_do_github(falhas[0]["created_at"]) if falhas else None
                resultado.append(Rotina(nome, INICIO_DAS_ROTINAS, passaram, falharam, falhando_desde, canceladas=canceladas, ultima_falha=ultima_falha))
            return resultado

        return self._ler(fontes.fonte_rotinas(), gerar)

    def renovacoes(self) -> Leitura[list[Renovacao]]:
        def gerar(_: datetime) -> list[Renovacao]:
            renovacoes = [
                Renovacao(ambiente, c.renovada_em, c.container_novo_no_ar)
                for ambiente in Ambiente
                for c in self._conferencias(ambiente)
                if c.renovada_em is not None
            ]
            return sorted(renovacoes, key=lambda r: r.momento)

        return self._ler(fontes.fonte_renovacoes(), gerar)

    # ── Verde ─────────────────────────────────────────────────────────────

    def _verde_por_dia(self, ambiente: Ambiente, agora: datetime, quantos: int) -> list[DiaDoVerde]:
        hoje = agora.date()
        dias = [hoje - timedelta(days=n) for n in range(quantos - 1, -1, -1)]
        linhas = self._consultar(
            [ambiente],
            inicio_do_dia(dias[0]),
            agora,
            'filter evento = "verde_chamada" | stats sum(resultado = "sucesso") as aceitas, sum(status = 401 or status = 403) as recusadas,'
            # O resto, aberto: processo que não existe (400, 404, 422) e consulta que não voltou (sem status).
            ' sum(tipoErro = "nao_encontrado") as nao_achou, sum(resultado = "erro") as sem_resposta,'
            " count(*) as total by datefloor(@timestamp - 3h, 1d) as dia",
        )
        por_dia = {date.fromisoformat(linha["dia"][:10]): linha for linha in linhas if linha.get("dia")}
        resultado = []
        for dia in dias:
            linha = por_dia.get(dia, {})
            aceitas, recusadas, total = _inteiro(linha, "aceitas"), _inteiro(linha, "recusadas"), _inteiro(linha, "total")
            outras = max(total - aceitas - recusadas, 0)
            resultado.append(DiaDoVerde(dia, aceitas, recusadas, outras, _inteiro(linha, "nao_achou"), _inteiro(linha, "sem_resposta")))
        return resultado

    def verde_por_dia(self, ambiente: Ambiente) -> Leitura[list[DiaDoVerde]]:
        return self._ler(fontes.fonte_verde_por_dia(ambiente), lambda agora: self._verde_por_dia(ambiente, agora, fontes.DIAS_DO_GRAFICO_DO_VERDE))

    def _resultado_do_verde(self, ambientes: list[Ambiente], inicio: datetime, fim: datetime) -> ResultadoDoVerde:
        # RG sem pessoa: o Verde responde 200 com dados vazios, e a consulta sai
        # como sucesso (src/maria/integracoes/verde.py:267). A busca que não achou
        # a pessoa só aparece no encerramento, com o motivo rg_nao_encontrado.
        linha = self._uma(
            ambientes,
            inicio,
            fim,
            'filter evento in ["verde_chamada", "atendimento_finalizado"]'
            ' | stats sum(evento = "verde_chamada" and resultado = "sucesso") as aceitas,'
            ' sum(evento = "verde_chamada" and (status = 401 or status = 403)) as recusadas,'
            ' sum(evento = "verde_chamada" and tipoErro = "auth_ou_infra") as infra,'
            ' sum(motivoHandoff = "rg_nao_encontrado") as nao_achou',
        )
        recusadas = _inteiro(linha, "recusadas")
        # As recusas da credencial também saem como auth_ou_infra: o erro do Verde é o resto.
        return ResultadoDoVerde(_inteiro(linha, "aceitas"), recusadas, max(_inteiro(linha, "infra") - recusadas, 0), _inteiro(linha, "nao_achou"))

    def resultado_do_verde(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[ResultadoDoVerde]:
        def gerar(agora: datetime) -> ResultadoDoVerde:
            inicio, fim = no_dia(dia, agora) if dia else (agora - timedelta(days=7), agora)
            return self._resultado_do_verde([ambiente], inicio, fim)

        return self._ler(fontes.fonte_resultado_do_verde(ambiente, dia), gerar)

    def duracao_do_verde(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DuracaoDoVerde]]:
        def gerar(agora: datetime) -> list[DuracaoDoVerde] | None:
            linhas = self._consultar(
                [ambiente],
                *(no_dia(dia, agora) if dia else (agora - timedelta(days=7), agora)),
                'filter evento = "verde_chamada" and ispresent(duracaoMs) | stats count(*) as n, avg(duracaoMs) as media, max(duracaoMs) as maximo by chamada | sort n desc',
            )
            duracoes = [
                DuracaoDoVerde(linha.get("chamada", "?"), _inteiro(linha, "n"), _real(linha, "media") / 1000, _real(linha, "maximo") / 1000) for linha in linhas
            ]
            return duracoes or None

        return self._ler(fontes.fonte_duracao_do_verde(ambiente, dia), gerar)

    def incidentes_de_credencial(self) -> Leitura[list[IncidenteDeCredencial]]:
        def gerar(agora: datetime) -> list[IncidenteDeCredencial]:
            # Os dois ambientes vão juntos: em fila, a tela esperava a soma deles.
            with ThreadPoolExecutor(max_workers=len(Ambiente)) as grupo:
                por_ambiente = list(grupo.map(lambda ambiente: self._incidentes(ambiente, agora), Ambiente))
            return sorted((i for lista in por_ambiente for i in lista), key=lambda i: i.inicio)

        return self._ler(fontes.fonte_incidentes(), gerar)

    def _incidentes(self, ambiente: Ambiente, agora: datetime) -> list[IncidenteDeCredencial]:
        """Blocos de recusa: horas com recusa, até a primeira hora com consulta aceita."""
        linhas = self._consultar(
            [ambiente],
            agora - timedelta(days=30),
            agora,
            'filter evento = "verde_chamada" | stats sum(status = 401 or status = 403) as recusadas, sum(resultado = "sucesso") as aceitas by bin(1h) as hora',
            limite=10000,
        )
        horas = sorted((_instante(linha["hora"]), _inteiro(linha, "recusadas"), _inteiro(linha, "aceitas")) for linha in linhas if linha.get("hora"))
        blocos: list[tuple[datetime, datetime]] = []
        inicio = ultima_recusa = None
        for hora, recusadas, aceitas in horas:
            if recusadas and inicio is None:
                inicio = hora
            if recusadas:
                ultima_recusa = hora
            if inicio is not None and ultima_recusa is not None and aceitas and not recusadas:
                blocos.append((inicio, ultima_recusa))
                inicio = ultima_recusa = None
        if inicio is not None and ultima_recusa is not None:
            blocos.append((inicio, ultima_recusa))

        def detalhar(bloco: tuple[datetime, datetime]) -> IncidenteDeCredencial | None:
            comeco, fim_das_recusas = bloco
            # Os horários exatos, já que as horas acima são cheias.
            exato = self._uma(
                [ambiente],
                comeco,
                fim_das_recusas + timedelta(hours=1),
                'filter evento = "verde_chamada" and (status = 401 or status = 403) | stats min(@timestamp) as ini, max(@timestamp) as fim, count(*) as n',
            )
            if _inteiro(exato, "n") < RECUSAS_PARA_INCIDENTE or not exato.get("ini"):
                return None
            ultima = _instante(exato["fim"])
            volta = self._uma([ambiente], ultima, agora, 'filter evento = "verde_chamada" and resultado = "sucesso" | stats min(@timestamp) as volta')
            return IncidenteDeCredencial(
                ambiente, _instante(exato["ini"]), _instante(volta["volta"]) if volta.get("volta") else None, _inteiro(exato, "n"), None
            )

        if not blocos:
            return []
        # Cada bloco tem as suas duas consultas, em fila; os blocos vão juntos.
        with ThreadPoolExecutor(max_workers=min(len(blocos), 4)) as grupo:
            return [i for i in grupo.map(detalhar, blocos) if i is not None]

    # ── Sistema ───────────────────────────────────────────────────────────

    def tempo_de_resposta(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[TempoDeResposta]:
        def gerar(agora: datetime) -> TempoDeResposta | None:
            # Só as rotas de atendimento: a checagem de saúde e a varredura de robôs
            # respondem em 1 milissegundo e esconderiam a demora de quem conversa.
            linha = self._uma(
                [ambiente],
                *(no_dia(dia, agora) if dia else (agora - timedelta(hours=24), agora)),
                'filter msg in ["incoming request", "request completed"]'
                " | stats earliest(req.url) as caminho, max(responseTime) as ms by reqId, hostname, pid"
                " | filter caminho like /^\\/atendimentos/ and ispresent(ms)"
                " | stats count(*) as n, pct(ms, 50) as metade, pct(ms, 90) as nove, max(ms) as maxima",
            )
            if not _inteiro(linha, "n"):
                return None
            return TempoDeResposta(_inteiro(linha, "n"), _real(linha, "metade") / 1000, _real(linha, "nove") / 1000, _real(linha, "maxima") / 1000)

        return self._ler(fontes.fonte_tempo_de_resposta(ambiente, dia), gerar)

    def respostas_com_erro(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[RespostasComErro]:
        def gerar(agora: datetime) -> RespostasComErro:
            # Liga a linha de entrada (caminho) à de saída (código) pela mesma requisição.
            # O identificador e o endereço de quem pediu nunca saem da consulta.
            linhas = self._consultar(
                [ambiente],
                *(no_dia(dia, agora) if dia else (agora - timedelta(hours=24), agora)),
                'filter msg in ["incoming request", "request completed"]'
                " | stats earliest(req.url) as caminho, max(res.statusCode) as codigo by reqId, hostname, pid"
                " | filter codigo >= 400"
                " | stats count(*) as n by codigo >= 500 as do_servidor, caminho like /^\\/(atendimentos|webhook)/ as da_api",
            )
            de_gente = de_robo = de_servidor = 0
            for linha in linhas:
                n = _inteiro(linha, "n")
                if linha.get("do_servidor") == "1":
                    de_servidor += n
                elif linha.get("da_api") == "1":
                    de_gente += n
                else:
                    de_robo += n
            return RespostasComErro(de_gente, de_robo, de_servidor)

        return self._ler(fontes.fonte_respostas_com_erro(ambiente, dia), gerar)

    # ── Inteligência artificial (Bedrock) ─────────────────────────────────

    def _bedrock_por_dia(self) -> dict[date, GastoDeIA]:
        """Tokens por dia de Brasília, nos últimos 400 dias, numa chamada só.

        A métrica guarda o dado de 1 hora por 455 dias. Uma chamada traz o ano
        inteiro (3 métricas), e o resultado vale 1 minuto na memória: as dezenas
        de dias que a tela financeira pede saem dela, e não de uma chamada cada."""
        with self._trava:
            if self._bedrock is not None and relogio.monotonic() - self._bedrock[0] < 60:
                return self._bedrock[1]
        agora = self._agora()
        inicio = inicio_do_dia(agora.date() - timedelta(days=400))
        consultas = [
            ("lido", fontes.MODELO_DE_CHAT, "InputTokenCount"),
            ("escrito", fontes.MODELO_DE_CHAT, "OutputTokenCount"),
            ("busca", fontes.MODELO_DE_EMBEDDING, "InputTokenCount"),
        ]
        resposta = self._metricas.get_metric_data(
            MetricDataQueries=[
                {
                    "Id": nome,
                    "MetricStat": {
                        "Metric": {"Namespace": "AWS/Bedrock", "MetricName": metrica, "Dimensions": [{"Name": "ModelId", "Value": modelo}]},
                        "Period": 86400,
                        "Stat": "Sum",
                    },
                }
                for nome, modelo, metrica in consultas
            ],
            StartTime=inicio,
            EndTime=agora,
        )
        por_dia: dict[date, dict[str, int]] = {}
        for serie in resposta["MetricDataResults"]:
            for instante, valor in zip(serie["Timestamps"], serie["Values"], strict=True):
                por_dia.setdefault(instante.astimezone(FUSO).date(), {})[serie["Id"]] = int(valor)
        dias = {dia: GastoDeIA(dia, v.get("lido", 0), v.get("escrito", 0), v.get("busca", 0)) for dia, v in por_dia.items()}
        with self._trava:
            self._bedrock = (relogio.monotonic(), dias)
        return dias

    def tokens_por_dia(self) -> Leitura[list[TokensDoDia]]:
        def gerar(agora: datetime) -> list[TokensDoDia]:
            hoje = agora.date()
            dimensoes = [{"Name": "ModelId", "Value": fontes.MODELO_DE_CHAT}]
            inicio = inicio_do_dia(hoje - timedelta(days=fontes.DIAS_DO_CUSTO - 1))
            chamadas = {t.date(): int(v) for t, v in self._serie("AWS/Bedrock", "Invocations", dimensoes, "Sum", 86400, inicio, agora)}
            gastos = self._bedrock_por_dia()
            dias = [hoje - timedelta(days=n) for n in range(fontes.DIAS_DO_CUSTO - 1, -1, -1)]
            vazio = GastoDeIA(hoje, 0, 0, 0)
            return [TokensDoDia(d, gastos.get(d, vazio).lido, gastos.get(d, vazio).escrito, chamadas.get(d, 0)) for d in dias]

        return self._ler(fontes.fonte_tokens_por_dia(), gerar)

    def gasto_do_dia(self, dia: date) -> Leitura[GastoDeIA]:
        # Dia sem ponto na métrica é dia sem gasto: a AWS não grava zero.
        return self._ler(fontes.fonte_gasto_de_ia(), lambda _: self._bedrock_por_dia().get(dia, GastoDeIA(dia, 0, 0, 0)))

    def gasto_do_mes(self, mes: date) -> Leitura[GastoDeIA]:
        def gerar(_: datetime) -> GastoDeIA:
            primeiro = mes.replace(day=1)
            dias = [g for d, g in self._bedrock_por_dia().items() if (d.year, d.month) == (primeiro.year, primeiro.month)]
            return GastoDeIA(primeiro, sum(g.lido for g in dias), sum(g.escrito for g in dias), sum(g.busca for g in dias))

        return self._ler(fontes.fonte_gasto_de_ia(), gerar)

    def gasto_por_assunto(self, ambiente: Ambiente, dia: date) -> Leitura[list[GastoDoAssunto]]:
        def gerar(agora: datetime) -> list[GastoDoAssunto]:
            fim = min(inicio_do_dia(dia + timedelta(days=1)), agora)
            eventos = ", ".join(f'"{e}"' for e in ("atendimento_finalizado", *EVENTOS_DO_ORQUESTRADOR))
            linhas = self._consultar(
                [ambiente],
                inicio_do_dia(dia),
                fim,
                f"filter evento in [{eventos}]"
                " | stats count(*) as n, sum(tokensGastos.input) as lido, sum(tokensGastos.output) as escrito,"
                " sum(tokensGastosTotal) as so_total by evento, fluxoId",
            )
            total: dict[Assunto, list[int]] = {}
            for linha in linhas:
                if linha.get("evento") == "atendimento_finalizado":
                    assunto = ASSUNTO_DO_FLUXO.get(linha.get("fluxoId", ""), Assunto.OUTROS)
                    soma = total.setdefault(assunto, [0, 0, 0, 0])
                    soma[0] += _inteiro(linha, "n")
                    soma[1] += _inteiro(linha, "lido")
                    soma[2] += _inteiro(linha, "escrito")
                else:
                    soma = total.setdefault(Assunto.TRIAGEM, [0, 0, 0, 0])
                    # Triagem que terminou: identificou, redirecionou ou não entendeu.
                    if linha.get("evento") != "orquestrador_pergunta_enviada":
                        soma[0] += _inteiro(linha, "n")
                    soma[3] += _inteiro(linha, "so_total")
            return [GastoDoAssunto(a, *total[a]) for a in Assunto if a in total]

        return self._ler(fontes.fonte_gasto_por_assunto(ambiente), gerar)

    def tokens_registrados(self, ambiente: Ambiente) -> Leitura[list[TokensRegistrados]]:
        def gerar(agora: datetime) -> list[TokensRegistrados] | None:
            primeiro = agora.date() - timedelta(days=fontes.DIAS_DO_REGISTRO - 1)
            eventos = ", ".join(f'"{e}"' for e in EVENTOS_DO_ORQUESTRADOR)
            linhas = self._consultar(
                [ambiente],
                inicio_do_dia(primeiro),
                agora,
                f'filter (evento = "atendimento_finalizado" and ispresent(tokensGastos.input)) or (evento in [{eventos}] and ispresent(tokensGastosTotal))'
                " | stats sum(tokensGastos.input) as lido, sum(tokensGastos.output) as escrito, sum(tokensGastosTotal) as so_total"
                " by datefloor(@timestamp - 3h, 1d) as dia",
            )
            dias = [
                TokensRegistrados(date.fromisoformat(linha["dia"][:10]), _inteiro(linha, "lido"), _inteiro(linha, "escrito"), _inteiro(linha, "so_total"))
                for linha in linhas
                if linha.get("dia")
            ]
            return sorted(dias, key=lambda d: d.dia) or None

        return self._ler(fontes.fonte_tokens_registrados(ambiente), gerar)

    # ── Atendimento ───────────────────────────────────────────────────────

    def _janela(self, origem: Origem, agora: datetime, dia: date | None = None) -> tuple[datetime, datetime]:
        """O trecho da origem; com o dia escolhido, só a parte do trecho naquele dia."""
        if origem is Origem.PRODUCAO_TS:
            inicio, fim = INICIO_DO_TYPESCRIPT, CORTE_DE_VERSAO
        elif origem is Origem.PRODUCAO_PY:
            inicio, fim = CORTE_DE_VERSAO, agora
        else:
            inicio, fim = agora - timedelta(days=7), agora
        if dia is None:
            return inicio, fim
        comeco, final = no_dia(dia, agora)
        return max(inicio, comeco), min(fim, final)

    def resumo_do_periodo(self, origem: Origem, dia: date | None = None) -> Leitura[ResumoDoPeriodo]:
        def gerar(agora: datetime) -> ResumoDoPeriodo:
            inicio, fim = self._janela(origem, agora, dia)
            inicio = max(inicio, agora - timedelta(days=fontes.DIAS_DO_REGISTRO))
            fim = max(fim, inicio)
            linha = self._uma(
                [AMBIENTE_DA_ORIGEM[origem]],
                inicio,
                fim,
                'filter evento in ["atendimento_criado", "atendimento_finalizado", "pergunta_enviada", "ttl_confirmacao_solicitada"]'
                ' | stats sum(evento = "atendimento_criado") as comecaram, sum(evento = "atendimento_finalizado") as terminaram,'
                ' sum(evento = "pergunta_enviada") as perguntas, sum(evento = "ttl_confirmacao_solicitada") as paradas',
            )
            return ResumoDoPeriodo(inicio, fim, *(_inteiro(linha, c) for c in ("comecaram", "terminaram", "perguntas", "paradas")))

        return self._ler(fontes.fonte_resumo_do_periodo(origem, dia), gerar)

    def nao_encontrado(self, origem: Origem, dia: date | None = None) -> Leitura[list[TrechoDeNaoEncontrado]]:
        def gerar(agora: datetime) -> list[TrechoDeNaoEncontrado]:
            if origem is Origem.PRODUCAO_TS:
                trechos = [
                    ("Antes do incidente, 16 a 22/10", INICIO_DO_TYPESCRIPT, INICIO_DO_INCIDENTE),
                    ("Durante o incidente, 22 e 23/10", INICIO_DO_INCIDENTE, CORTE_DE_VERSAO),
                ]
            elif origem is Origem.PRODUCAO_PY:
                trechos = [("Desde a troca de versão", CORTE_DE_VERSAO, agora)]
            else:
                trechos = [("Últimos 7 dias", agora - timedelta(days=7), agora)]
            if dia is not None:
                # Só a parte de cada trecho que cai no dia escolhido.
                comeco, final = no_dia(dia, agora)
                quando = f"{dia:%d/%m}, das {dia.hour}h às {dia.hour + 1}h" if isinstance(dia, datetime) else f"{dia:%d/%m}"
                trechos = [(f"{rotulo}, em {quando}", max(i, comeco), min(f, final)) for rotulo, i, f in trechos if min(f, final) > max(i, comeco)]
            ambiente = AMBIENTE_DA_ORIGEM[origem]
            resultado = []
            for rotulo, inicio, fim in trechos:
                linha = self._uma(
                    [ambiente],
                    inicio,
                    fim,
                    'filter evento = "atendimento_finalizado" | stats count(*) as encerramentos, sum(motivoHandoff = "rg_nao_encontrado") as nao_encontrado',
                )
                credencial = self._resultado_do_verde([ambiente], inicio, fim)
                resultado.append(TrechoDeNaoEncontrado(rotulo, _inteiro(linha, "encerramentos"), _inteiro(linha, "nao_encontrado"), credencial))
            return resultado

        return self._ler(fontes.fonte_nao_encontrado(origem), gerar)

    def orquestrador(self, origem: Origem, dia: date | None = None) -> Leitura[ResumoDoOrquestrador]:
        def gerar(agora: datetime) -> ResumoDoOrquestrador | None:
            inicio, fim = self._janela(origem, agora, dia)
            if origem is not Origem.RELEASE and dia is None:
                inicio = max(inicio, agora - timedelta(days=7))
            eventos = ", ".join(f'"{e}"' for e in EVENTOS_DO_ORQUESTRADOR)
            linhas = self._consultar([AMBIENTE_DA_ORIGEM[origem]], inicio, fim, f"filter evento in [{eventos}] | stats count(*) as n by evento")
            n = {linha.get("evento"): _inteiro(linha, "n") for linha in linhas}
            resumo = ResumoDoOrquestrador(*(n.get(e, 0) for e in EVENTOS_DO_ORQUESTRADOR))
            return resumo if any((resumo.identificou, resumo.era_da_tykhe, resumo.nao_entendeu, resumo.perguntou_de_novo)) else None

        return self._ler(fontes.fonte_orquestrador(), gerar)

    # ── Relatório do dia ──────────────────────────────────────────────────

    def sistema_no_dia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[SistemaNoDia]:
        def gerar(agora: datetime) -> SistemaNoDia:
            inicio, fim = no_dia(dia or agora.date(), agora)
            dimensoes = self._dimensoes_do_balanceador(ambiente)
            minutos = self._serie("AWS/ApplicationELB", "HealthyHostCount", dimensoes, "Minimum", 60, inicio, fim)
            # A soma num período só: o dia inteiro, ou a hora escolhida.
            periodo = 3600 if isinstance(dia, datetime) else 86400
            erros = self._serie("AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", dimensoes, "Sum", periodo, inicio, fim)
            subidas = self._consultar(
                [ambiente], inicio, fim, "filter @message like /Application startup complete/ | fields @timestamp | sort @timestamp asc | limit 50"
            )
            reinicios = [_instante(linha["@timestamp"]) for linha in subidas if linha.get("@timestamp")]

            def do_dia(rotina: str) -> list[dict[str, Any]]:
                # O GitHub filtra "a partir do dia"; a janela escolhida pode ter execuções depois dela.
                return [e for e in self._github.execucoes(rotina, inicio.date()) if inicio <= _hora_do_github(e["created_at"]) < fim]

            execucoes = do_dia(SUBIDAS_DO[ambiente])
            testes = do_dia("ci.yml")
            return SistemaNoDia(
                minutos_fora_do_ar=sum(1 for _, v in minutos if v < 1),
                reinicios=reinicios,
                erros_de_servidor=int(sum(v for _, v in erros)),
                subidas=sum(e.get("conclusion") == "success" for e in execucoes),
                testes_com_falha=sum(e.get("conclusion") == "failure" for e in testes),
            )

        return self._ler(fontes.fonte_sistema_no_dia(ambiente, dia), gerar)

    # ── Coluna da direita das telas ───────────────────────────────────────

    def atendimentos_por_hora(self, ambiente: Ambiente, dia: date) -> Leitura[list[ContagemPorHora]]:
        def gerar(agora: datetime) -> list[ContagemPorHora]:
            inicio = inicio_do_dia(o_dia(dia))
            fim = min(inicio + timedelta(days=1), agora)
            linhas = self._consultar(
                [ambiente],
                inicio,
                fim,
                'filter evento in ["atendimento_criado", "atendimento_finalizado"]'
                ' | stats sum(evento = "atendimento_criado") as comecaram, sum(evento = "atendimento_finalizado") as terminaram by bin(1h) as hora',
            )
            por_hora = {_instante(linha["hora"]): linha for linha in linhas if linha.get("hora")}
            horas = []
            hora = inicio
            while hora < fim:
                linha = por_hora.get(hora, {})
                horas.append(ContagemPorHora(hora, _inteiro(linha, "comecaram"), _inteiro(linha, "terminaram")))
                hora += timedelta(hours=1)
            return horas

        return self._ler(fontes.fonte_atendimentos_por_hora(ambiente), gerar)

    def atendimentos_por_dia(self, ambiente: Ambiente) -> Leitura[list[ContagemPorDia]]:
        def gerar(agora: datetime) -> list[ContagemPorDia]:
            hoje = agora.date()
            dias = [hoje - timedelta(days=n) for n in range(fontes.DIAS_DO_REGISTRO - 1, -1, -1)]
            linhas = self._consultar(
                [ambiente],
                inicio_do_dia(dias[0]),
                agora,
                'filter evento in ["atendimento_criado", "atendimento_finalizado"]'
                ' | stats sum(evento = "atendimento_criado") as comecaram, sum(evento = "atendimento_finalizado") as terminaram'
                " by datefloor(@timestamp - 3h, 1d) as dia",
            )
            por_dia = {date.fromisoformat(linha["dia"][:10]): linha for linha in linhas if linha.get("dia")}
            return [ContagemPorDia(d, _inteiro(por_dia.get(d, {}), "comecaram"), _inteiro(por_dia.get(d, {}), "terminaram")) for d in dias]

        return self._ler(fontes.fonte_atendimentos_por_dia(ambiente), gerar)

    def _desfechos(self, ambiente: Ambiente, inicio: datetime, fim: datetime) -> list[Desfecho]:
        linhas = self._consultar([ambiente], inicio, fim, 'filter evento = "atendimento_finalizado" | stats count(*) as n by motivoHandoff | sort n desc')
        return [Desfecho(linha.get("motivoHandoff", ""), _inteiro(linha, "n")) for linha in linhas]

    def desfechos(self, origem: Origem, dia: date | None = None) -> Leitura[list[Desfecho]]:
        def gerar(agora: datetime) -> list[Desfecho] | None:
            inicio, fim = self._janela(origem, agora, dia)
            return self._desfechos(AMBIENTE_DA_ORIGEM[origem], inicio, fim) or None

        return self._ler(fontes.fonte_desfechos(AMBIENTE_DA_ORIGEM[origem]), gerar)

    def desfechos_do_dia(self, ambiente: Ambiente, dia: date) -> Leitura[list[Desfecho]]:
        def gerar(agora: datetime) -> list[Desfecho]:
            return self._desfechos(ambiente, *no_dia(dia, agora))

        return self._ler(fontes.fonte_desfechos(ambiente), gerar)

    def origem_nao_atendida(self, origem: Origem, dia: date | None = None) -> Leitura[OrigemNaoAtendida]:
        def gerar(agora: datetime) -> OrigemNaoAtendida | None:
            inicio, fim = self._janela(origem, agora, dia)
            # Agrupa por conversa só para contar: o identificador nunca sai da consulta.
            linha = self._uma(
                [AMBIENTE_DA_ORIGEM[origem]],
                inicio,
                fim,
                'filter (evento = "verde_chamada" and chamada = "processo") or evento = "atendimento_finalizado"'
                ' | stats sum(evento = "verde_chamada" and resultado = "sucesso") as achou,'
                ' sum(evento = "verde_chamada" and tipoErro = "nao_encontrado") as nao_achou,'
                ' sum(evento = "verde_chamada" and resultado != "sucesso" and tipoErro != "nao_encontrado") as falhou,'
                ' sum(motivoHandoff = "origem_processo_nao_suportada") as origem, sum(evento = "atendimento_finalizado") as terminou by chatId'
                " | stats sum(terminou) as finalizados, sum(origem > 0) as total, sum(origem > 0 and achou > 0) as outra_origem,"
                " sum(origem > 0 and achou = 0 and nao_achou > 0) as nao_encontrado,"
                " sum(origem > 0 and achou = 0 and nao_achou = 0 and falhou > 0) as consulta_falhou",
            )
            if not _inteiro(linha, "finalizados"):
                return None
            campos = ("finalizados", "total", "outra_origem", "nao_encontrado", "consulta_falhou")
            return OrigemNaoAtendida(*(_inteiro(linha, c) for c in campos))

        return self._ler(fontes.fonte_origem_nao_atendida(AMBIENTE_DA_ORIGEM[origem]), gerar)

    def requisicoes_por_hora(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[RequisicoesPorHora]]:
        # Com a hora escolhida, o gráfico ainda mostra o dia inteiro, com a hora em destaque.
        dia = o_dia(dia) if dia is not None else None

        def gerar(agora: datetime) -> list[RequisicoesPorHora]:
            dimensoes = self._dimensoes_do_balanceador(ambiente)
            if dia is None:
                inicio, fim = agora.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23), agora
            else:
                inicio, fim = no_dia(dia, agora)
            pedidos = dict(self._serie("AWS/ApplicationELB", "RequestCount", dimensoes, "Sum", 3600, inicio, fim))
            erros = dict(self._serie("AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", dimensoes, "Sum", 3600, inicio, fim))
            horas = [h for h in (inicio + timedelta(hours=n) for n in range(24)) if h < fim]
            return [RequisicoesPorHora(h, int(pedidos.get(h, 0)), int(erros.get(h, 0))) for h in horas]

        return self._ler(fontes.fonte_requisicoes_por_hora(ambiente, dia), gerar)

    def recursos_do_servico(self, ambiente: Ambiente) -> Leitura[RecursosDoServico]:
        def gerar(agora: datetime) -> RecursosDoServico:
            servico = self._servico(ambiente)
            series = {
                nome: self._serie("ECS/ContainerInsights", nome, servico, "Average", 300, agora - timedelta(hours=24), agora)
                for nome in ("CpuUtilized", "CpuReserved", "MemoryUtilized", "MemoryReserved")
            }
            if not all(series.values()):
                raise FalhaDeLeitura("O ECS não mandou CPU e memória nas últimas 24 horas.")

            def fracao(usado: str, reservado: str) -> tuple[float, float]:
                reserva = series[reservado][-1][1] or 1.0
                return series[usado][-1][1] / reserva, max(v for _, v in series[usado]) / reserva

            cpu, memoria = fracao("CpuUtilized", "CpuReserved"), fracao("MemoryUtilized", "MemoryReserved")
            return RecursosDoServico(cpu[0], cpu[1], memoria[0], memoria[1])

        return self._ler(fontes.fonte_recursos_do_servico(ambiente), gerar)

    def horarios_da_conferencia(self) -> Leitura[list[HorarioDaConferencia]]:
        def gerar(agora: datetime) -> list[HorarioDaConferencia]:
            execucoes = self._github.execucoes("verificar-token-verde.yml", agora.date() - timedelta(days=30))
            agendadas = [e for e in execucoes if e.get("event") == "schedule" and e.get("status") == "completed"]
            horarios = [
                HorarioDaConferencia(
                    _hora_do_github(e.get("run_started_at") or e["created_at"]).date(),
                    _hora_do_github(e.get("run_started_at") or e["created_at"]),
                    e.get("conclusion") == "success",
                )
                for e in agendadas
            ]
            return sorted(horarios, key=lambda h: h.comecou)

        return self._ler(fontes.fonte_horarios_da_conferencia(), gerar)

    def verde_do_mes(self, ambiente: Ambiente) -> Leitura[list[DiaDoVerde]]:
        return self._ler(fontes.fonte_verde_do_mes(ambiente), lambda agora: self._verde_por_dia(ambiente, agora, 30))

    # ── Observatório da IA ────────────────────────────────────────────────

    def erros_da_ia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[ErroDaIA]]:
        def gerar(agora: datetime) -> list[ErroDaIA]:
            linhas = self._consultar(
                [ambiente],
                *(no_dia(dia, agora) if dia else (agora - timedelta(days=30), agora)),
                "filter level >= 50 and msg like /^\\[(classificar|desambiguar|extrair|reescrever|sumarizar)\\] falha/"
                " | parse msg /^\\[(?<funcao>[a-z]+)\\]/ | stats count(*) as n by funcao",
            )
            n = {linha.get("funcao"): _inteiro(linha, "n") for linha in linhas}
            return [ErroDaIA(f, n.get(f, 0)) for f in FUNCOES_DE_IA]

        return self._ler(fontes.fonte_erros_da_ia(ambiente, dia), gerar)

    def uso_da_ia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[UsoDaIA]:
        def gerar(agora: datetime) -> UsoDaIA | None:
            linha = self._uma(
                [ambiente],
                *(no_dia(dia, agora) if dia else (agora - timedelta(days=7), agora)),
                'filter evento = "pergunta_enviada" | stats count(*) as perguntas, sum(viaIA = 1) as ia',
            )
            if not _inteiro(linha, "perguntas"):
                return None
            return UsoDaIA(_inteiro(linha, "perguntas"), _inteiro(linha, "ia"))

        return self._ler(fontes.fonte_uso_da_ia(ambiente, dia), gerar)

    def saude_do_modelo(self) -> Leitura[list[DiaDoModelo]]:
        def gerar(agora: datetime) -> list[DiaDoModelo]:
            dias = [agora.date() - timedelta(days=n) for n in range(13, -1, -1)]
            dimensoes = [{"Name": "ModelId", "Value": fontes.MODELO_DE_CHAT}]
            consultas = {
                "chamadas": ("Invocations", "Sum"),
                "pedido": ("InvocationClientErrors", "Sum"),
                "servico": ("InvocationServerErrors", "Sum"),
                "limitadas": ("InvocationThrottles", "Sum"),
                "demora": ("InvocationLatency", "Average"),
                "escritos": ("OutputTokenCount", "Sum"),
            }
            resposta = self._metricas.get_metric_data(
                MetricDataQueries=[
                    {
                        "Id": nome,
                        "MetricStat": {
                            "Metric": {"Namespace": "AWS/Bedrock", "MetricName": metrica, "Dimensions": dimensoes},
                            "Period": 86400,
                            "Stat": estatistica,
                        },
                    }
                    for nome, (metrica, estatistica) in consultas.items()
                ],
                StartTime=inicio_do_dia(dias[0]),
                EndTime=agora,
            )
            valores: dict[str, dict[date, float]] = {
                serie["Id"]: {t.astimezone(FUSO).date(): float(v) for t, v in zip(serie["Timestamps"], serie["Values"], strict=True)}
                for serie in resposta["MetricDataResults"]
            }

            def v(nome: str, dia: date) -> float:
                return valores.get(nome, {}).get(dia, 0.0)

            return [
                DiaDoModelo(
                    dia,
                    int(v("chamadas", dia)),
                    int(v("pedido", dia)),
                    int(v("servico", dia)),
                    int(v("limitadas", dia)),
                    v("demora", dia) / 1000,
                    v("escritos", dia) / v("chamadas", dia) if v("chamadas", dia) else 0.0,
                )
                for dia in dias
            ]

        return self._ler(fontes.fonte_saude_do_modelo(), gerar)

    def mudancas_na_ia(self) -> Leitura[list[MudancaNaIA]]:
        def gerar(_: datetime) -> list[MudancaNaIA] | None:
            commits = self._github.json("commits", {"path": "src/maria/ia", "sha": "develop", "per_page": 30})
            mudancas = [
                MudancaNaIA(_hora_do_github(c["commit"]["committer"]["date"]), c["commit"]["message"].split("\n")[0][:160], c["sha"][:7]) for c in commits
            ]
            return mudancas or None

        return self._ler(fontes.fonte_mudancas_na_ia(), gerar)

    # ── Fluxos ────────────────────────────────────────────────────────────
    # As consultas por conversa juntam os eventos pelo chatId só para contar:
    # o identificador nunca sai da consulta.

    def _janela_dos_fluxos(self, dia: date | None, agora: datetime) -> tuple[datetime, datetime]:
        return no_dia(dia, agora) if dia else (agora - timedelta(days=fontes.DIAS_DOS_FLUXOS), agora)

    def _por_conversa(self, ambiente: Ambiente, dia: date | None, agora: datetime, eventos: str, somas: str, depois: str) -> list[dict[str, str]]:
        """Junta os eventos de cada conversa que começou na janela e devolve o que
        `depois` conta. Lê até 3 horas além do fim da janela, para uma conversa que
        começou nela e terminou logo depois não parecer parada."""
        inicio, fim = self._janela_dos_fluxos(dia, agora)
        return self._consultar(
            [ambiente],
            inicio,
            min(fim + timedelta(hours=3), agora),
            f"filter evento in [{eventos}]"
            f' | stats sum(evento = "atendimento_criado") as criou, min(@timestamp) as ini, earliest(fluxoId) as fluxo, {somas} by chatId'
            f" | filter criou > 0 and ini >= {int(inicio.timestamp() * 1000)} and ini < {int(fim.timestamp() * 1000)}"
            f" | {depois}",
            limite=10000,
        )

    def conversas_por_fluxo(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[ConversasDoFluxo]]:
        def gerar(agora: datetime) -> list[ConversasDoFluxo] | None:
            linhas = self._por_conversa(
                ambiente,
                dia,
                agora,
                '"atendimento_criado", "atendimento_finalizado", "atendimento_expirado", "resposta_recebida"',
                'sum(evento = "atendimento_finalizado") as fim, sum(evento = "atendimento_finalizado" and destino = "atendimento_humano") as humano,'
                ' sum(evento = "atendimento_expirado") as expirou, sum(evento = "resposta_recebida") as respostas',
                "stats count(*) as conversas by fluxo, respostas, fim > 0 as terminou, humano > 0 as encaminhou, expirou > 0 as expirada",
            )
            resultado = []
            for linha in linhas:
                if _inteiro(linha, "encaminhou"):
                    fim_da_conversa = FimDaConversa.ENCAMINHOU
                elif _inteiro(linha, "terminou"):
                    fim_da_conversa = FimDaConversa.CONCLUIU
                elif _inteiro(linha, "expirada"):
                    fim_da_conversa = FimDaConversa.EXPIROU
                else:
                    fim_da_conversa = FimDaConversa.PAROU
                resultado.append(ConversasDoFluxo(linha.get("fluxo", ""), _inteiro(linha, "respostas"), fim_da_conversa, _inteiro(linha, "conversas")))
            return resultado or None

        return self._ler(fontes.fonte_conversas_por_fluxo(ambiente, dia), gerar)

    def duracao_das_conversas(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DuracaoDasConversas]]:
        def gerar(agora: datetime) -> list[DuracaoDasConversas] | None:
            linhas = self._por_conversa(
                ambiente,
                dia,
                agora,
                '"atendimento_criado", "atendimento_finalizado"',
                'sum(evento = "atendimento_finalizado") as fim, max(@timestamp) as ultimo',
                "filter fim > 0 | fields (ultimo - ini) / 60000 as minutos"
                " | stats count(*) as conversas by fluxo, minutos < 2 as ate2, minutos < 5 as ate5, minutos < 15 as ate15, minutos < 60 as ate60",
            )
            resultado = []
            for linha in linhas:
                faixa = next((f for f in ("ate2", "ate5", "ate15", "ate60") if _inteiro(linha, f)), "mais")
                resultado.append(DuracaoDasConversas(linha.get("fluxo", ""), faixa, _inteiro(linha, "conversas")))
            return resultado or None

        return self._ler(fontes.fonte_duracao_das_conversas(ambiente, dia), gerar)

    def desfechos_por_fluxo(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DesfechoDoFluxo]]:
        def gerar(agora: datetime) -> list[DesfechoDoFluxo] | None:
            linhas = self._consultar(
                [ambiente],
                *self._janela_dos_fluxos(dia, agora),
                'filter evento = "atendimento_finalizado" | stats count(*) as n by fluxoId, motivoHandoff, destino',
            )
            desfechos = [
                DesfechoDoFluxo(linha.get("fluxoId", ""), linha.get("motivoHandoff", ""), linha.get("destino", ""), _inteiro(linha, "n")) for linha in linhas
            ]
            return desfechos or None

        return self._ler(fontes.fonte_desfechos_por_fluxo(ambiente, dia), gerar)

    def triagem(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[RodadaDaTriagem]]:
        def gerar(agora: datetime) -> list[RodadaDaTriagem] | None:
            saidas = {
                "orquestrador_fluxo_identificado": SaidaDaTriagem.IDENTIFICOU,
                "orquestrador_redirecionado": SaidaDaTriagem.REDIRECIONOU,
                "orquestrador_finalizado_sem_fluxo": SaidaDaTriagem.SEM_FLUXO,
                "orquestrador_pergunta_enviada": SaidaDaTriagem.PERGUNTOU,
                "orquestrador_inconsistencia": SaidaDaTriagem.INCONSISTENCIA,
            }
            eventos = ", ".join(f'"{e}"' for e in saidas)
            linhas = self._consultar(
                [ambiente],
                *self._janela_dos_fluxos(dia, agora),
                f"filter evento in [{eventos}] | stats count(*) as n by evento, flowId, tipoCaso, destino",
            )
            rodadas = []
            for linha in linhas:
                saida = saidas.get(linha.get("evento", ""))
                if saida is None:
                    continue
                # O alvo: o fluxo identificado, ou o tipo de caso devolvido à Tykhe, ou o destino.
                alvo = linha.get("flowId") or linha.get("tipoCaso") or linha.get("destino") or ""
                rodadas.append(RodadaDaTriagem(saida, alvo, _inteiro(linha, "n")))
            return rodadas or None

        return self._ler(fontes.fonte_triagem(ambiente, dia), gerar)

    def fluxos_por_dia(self, ambiente: Ambiente) -> Leitura[list[FluxoNoDia]]:
        def gerar(agora: datetime) -> list[FluxoNoDia] | None:
            primeiro = agora.date() - timedelta(days=fontes.DIAS_DO_REGISTRO - 1)
            linhas = self._consultar(
                [ambiente],
                inicio_do_dia(primeiro),
                agora,
                'filter evento in ["atendimento_criado", "atendimento_finalizado"]'
                ' | stats sum(evento = "atendimento_criado") as comecaram, sum(evento = "atendimento_finalizado") as terminaram,'
                ' sum(evento = "atendimento_finalizado" and destino = "atendimento_humano") as encaminhadas'
                " by datefloor(@timestamp - 3h, 1d) as dia, fluxoId",
            )
            dias = [
                FluxoNoDia(
                    date.fromisoformat(linha["dia"][:10]),
                    linha.get("fluxoId", ""),
                    _inteiro(linha, "comecaram"),
                    _inteiro(linha, "terminaram"),
                    _inteiro(linha, "encaminhadas"),
                )
                for linha in linhas
                if linha.get("dia")
            ]
            return sorted(dias, key=lambda d: (d.dia, d.fluxo)) or None

        return self._ler(fontes.fonte_fluxos_por_dia(ambiente), gerar)

    def problemas_por_dia(self, ambiente: Ambiente) -> Leitura[list[ProblemaNoDia]]:
        def gerar(agora: datetime) -> list[ProblemaNoDia] | None:
            primeiro = agora.date() - timedelta(days=fontes.DIAS_DO_REGISTRO - 1)
            eventos = ", ".join(f'"{e}"' for e in PROBLEMAS_POR_EVENTO)
            linhas = self._consultar(
                [ambiente],
                inicio_do_dia(primeiro),
                agora,
                f'filter (evento = "atendimento_finalizado" and motivoHandoff = "falha_infra_verde") or evento in [{eventos}]'
                ' or (evento = "whatsapp_status_entrega" and status = "failed")'
                " | stats count(*) as n by datefloor(@timestamp - 3h, 1d) as dia, evento, fluxoId",
            )
            problemas = [
                ProblemaNoDia(
                    date.fromisoformat(linha["dia"][:10]),
                    "falha_infra_verde" if linha.get("evento") == "atendimento_finalizado" else linha.get("evento", ""),
                    linha.get("fluxoId", ""),
                    _inteiro(linha, "n"),
                )
                for linha in linhas
                if linha.get("dia")
            ]
            return sorted(problemas, key=lambda p: (p.dia, p.problema)) or None

        return self._ler(fontes.fonte_problemas_por_dia(ambiente), gerar)

    def encaminhamentos_por_dia(self, ambiente: Ambiente) -> Leitura[list[EncaminhamentoNoDia]]:
        # A triagem que manda direto para pessoa, antes de um fluxo, entra com um motivo próprio.
        da_triagem = {"orquestrador_finalizado_sem_fluxo": "triagem_sem_fluxo", "orquestrador_inconsistencia": "triagem_inconsistente"}

        def gerar(agora: datetime) -> list[EncaminhamentoNoDia] | None:
            primeiro = agora.date() - timedelta(days=fontes.DIAS_DO_REGISTRO - 1)
            eventos = ", ".join(f'"{e}"' for e in da_triagem)
            linhas = self._consultar(
                [ambiente],
                inicio_do_dia(primeiro),
                agora,
                f'filter evento = "atendimento_finalizado" or (evento in [{eventos}] and destino = "atendimento_humano")'
                " | stats count(*) as n by datefloor(@timestamp - 3h, 1d) as dia, evento, fluxoId, destino, motivoHandoff",
            )
            resultado = []
            for linha in linhas:
                if not linha.get("dia"):
                    continue
                evento = linha.get("evento", "")
                motivo = da_triagem.get(evento) or linha.get("motivoHandoff", "")
                resultado.append(
                    EncaminhamentoNoDia(
                        date.fromisoformat(linha["dia"][:10]),
                        "" if evento in da_triagem else linha.get("fluxoId", ""),
                        destino_do_log(linha.get("destino", "")),
                        motivo,
                        _inteiro(linha, "n"),
                    )
                )
            return sorted(resultado, key=lambda e: (e.dia, e.fluxo, e.motivo)) or None

        return self._ler(fontes.fonte_encaminhamentos(ambiente), gerar)

    def envios_do_whatsapp(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[EnvioDoWhatsapp]]:
        def gerar(agora: datetime) -> list[EnvioDoWhatsapp] | None:
            eventos = ", ".join(f'"{e}"' for e in ("whatsapp_envio_ok", "whatsapp_envio_falhou", "whatsapp_envio_erro", "whatsapp_bridge_erro"))
            linhas = self._consultar(
                [ambiente],
                *self._janela_dos_fluxos(dia, agora),
                f'filter evento in [{eventos}] or (evento = "whatsapp_status_entrega" and status = "failed")'
                " | stats count(*) as n by evento, status, erroCodigo",
            )
            envios = [
                # O aviso de entrega tem o código do WhatsApp; o envio recusado, o status HTTP.
                EnvioDoWhatsapp(
                    linha.get("evento", ""),
                    linha.get("erroCodigo") or ("" if linha.get("evento") == "whatsapp_status_entrega" else linha.get("status", "")),
                    _inteiro(linha, "n"),
                )
                for linha in linhas
            ]
            return envios or None

        return self._ler(fontes.fonte_envios_do_whatsapp(ambiente, dia), gerar)
