"""Renova a credencial do Verde quando falta 1 dia para ela vencer (issue #14).

Este é o único código do Visor que lê e escreve o segredo `VERDE_JWT_TOKEN`; o
resto do painel continua sem tocar nele. Por isso roda como comando próprio
(`python -m painel.renovador`), uma vez por dia, e nunca dentro do servidor web.

Regras do Verde: `POST /autenticacao/token/refresh` com `Authorization: Bearer`
e `X-Client-ID`; renova token ativo ou vencido há no máximo 5 dias; token
revogado nunca renova; o token antigo morre na hora; o novo vale 30 dias.

O que protege o token (o novo é a única cópia depois do refresh):

- trava por ambiente, criada de forma atômica, contra duas execuções ao mesmo tempo;
- a gravação do segredo tenta de novo antes de desistir;
- o token nunca entra em log, mensagem de erro, tela ou disco. Os registros
  levam só ambiente, data e resultado.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Protocol

registro = logging.getLogger("painel.renovador")

DIAS_ANTES = 1
DIAS_DE_GRACA = 5
PRAZO_DO_VERDE_S = 20
TENTATIVAS_DA_GRAVACAO = 5
TRAVA_VELHA = timedelta(minutes=15)

REGIAO = "sa-east-1"
CLUSTER = "maria-langgraph-pp-sp"
SERVICOS = {"prod": "api-prod-sp", "release": "api-release-sp"}


class Resultado(Enum):
    NAO_PRECISA = "nao_precisa"
    SIMULADA = "simulada"
    RENOVADA = "renovada"
    OCUPADA = "ocupada"
    REVOGADA = "revogada"
    FORA_DO_PRAZO = "fora_do_prazo"
    RECUSADA = "recusada"
    SEM_TOKEN_NA_RESPOSTA = "sem_token_na_resposta"
    GRAVACAO_FALHOU = "gravacao_falhou"
    REDEPLOY_FALHOU = "redeploy_falhou"


# Resultados em que algo precisa de gente: o comando sai com erro.
PEDEM_ATENCAO = {
    Resultado.REVOGADA,
    Resultado.FORA_DO_PRAZO,
    Resultado.RECUSADA,
    Resultado.SEM_TOKEN_NA_RESPOSTA,
    Resultado.GRAVACAO_FALHOU,
    Resultado.REDEPLOY_FALHOU,
}


class Segredos(Protocol):
    def ler(self, nome: str) -> dict[str, str]: ...
    def gravar(self, nome: str, valor: dict[str, str]) -> None: ...
    def pegar_trava(self, nome: str, agora: datetime) -> bool: ...
    def soltar_trava(self, nome: str) -> None: ...


class Verde(Protocol):
    def renovar(self, api_url: str, token: str, client_id: str) -> tuple[int, Any]: ...


class Servico(Protocol):
    def redeploy(self, cluster: str, servico: str) -> None: ...


class RenovacaoInterrompida(Exception):
    """Mensagem segura para o log: nunca leva token nem client id."""


def validade_do_token(token: str) -> datetime | None:
    """O `exp` do JWT. Só decide *se* renova; quem confere a assinatura é o Verde."""
    try:
        carga = token.split(".")[1]
        carga += "=" * (-len(carga) % 4)
        exp = json.loads(base64.urlsafe_b64decode(carga)).get("exp")
        return datetime.fromtimestamp(float(exp), UTC) if exp is not None else None
    except (IndexError, ValueError, TypeError, OSError):
        return None


def decidir(valida_ate: datetime, agora: datetime) -> Resultado | None:
    """None quando é para renovar agora."""
    if agora >= valida_ate + timedelta(days=DIAS_DE_GRACA):
        return Resultado.FORA_DO_PRAZO
    if valida_ate - agora > timedelta(days=DIAS_ANTES):
        return Resultado.NAO_PRECISA
    return None


def _token_novo(corpo: Any) -> str | None:
    if isinstance(corpo, dict):
        achado = corpo.get("token")
        if achado is None and isinstance(corpo.get("dados"), dict):
            achado = corpo["dados"].get("token")
        if isinstance(achado, str) and achado:
            return achado
    return None


@dataclass(frozen=True)
class Relato:
    ambiente: str
    resultado: Resultado
    em: datetime


def renovar_ambiente(
    ambiente: str,
    *,
    segredos: Segredos,
    verde: Verde,
    servico: Servico,
    agora: datetime,
    simular: bool = False,
    esperar: Callable[[float], None] = time.sleep,
) -> Relato:
    nome = f"maria-langgraph-pp-{ambiente}/app"

    def relato(resultado: Resultado) -> Relato:
        return Relato(ambiente, resultado, agora)

    segredo = segredos.ler(nome)
    valida_ate = validade_do_token(segredo.get("VERDE_JWT_TOKEN", ""))
    if valida_ate is None:
        raise RenovacaoInterrompida(f"[{ambiente}] o token do segredo não tem validade legível")
    parar = decidir(valida_ate, agora)
    if parar is not None:
        return relato(parar)
    if simular:
        return relato(Resultado.SIMULADA)

    if not segredos.pegar_trava(f"visor-maria/trava-renovacao-{ambiente}", agora):
        return relato(Resultado.OCUPADA)
    try:
        # Relê sob a trava: outra execução pode ter renovado entre a primeira leitura e a trava.
        segredo = segredos.ler(nome)
        valida_ate = validade_do_token(segredo.get("VERDE_JWT_TOKEN", ""))
        if valida_ate is None or decidir(valida_ate, agora) is not None:
            return relato(Resultado.NAO_PRECISA)

        codigo, corpo = verde.renovar(segredo["VERDE_API_URL"], segredo["VERDE_JWT_TOKEN"], segredo["VERDE_CLIENT_ID"])
        if codigo != 200:
            return relato(Resultado.REVOGADA if _revogado(corpo) else Resultado.RECUSADA)
        novo = _token_novo(corpo)
        if novo is None:
            return relato(Resultado.SEM_TOKEN_NA_RESPOSTA)

        segredo["VERDE_JWT_TOKEN"] = novo
        if not _gravar_com_tentativas(segredos, nome, segredo, esperar):
            return relato(Resultado.GRAVACAO_FALHOU)
        try:
            servico.redeploy(CLUSTER, SERVICOS[ambiente])
        except Exception as erro:  # noqa: BLE001 - só o tipo vai para o log
            registro.error("[%s] token renovado e gravado, mas o redeploy falhou (%s)", ambiente, type(erro).__name__)
            return relato(Resultado.REDEPLOY_FALHOU)
        return relato(Resultado.RENOVADA)
    finally:
        segredos.soltar_trava(f"visor-maria/trava-renovacao-{ambiente}")


def _revogado(corpo: Any) -> bool:
    return isinstance(corpo, (dict, str)) and "revog" in json.dumps(corpo).lower()


def _gravar_com_tentativas(segredos: Segredos, nome: str, valor: dict[str, str], esperar: Callable[[float], None]) -> bool:
    for tentativa in range(TENTATIVAS_DA_GRAVACAO):
        try:
            segredos.gravar(nome, valor)
            return True
        except Exception as erro:  # noqa: BLE001 - só o tipo vai para o log
            registro.error("gravação do segredo falhou (%s), tentativa %d", type(erro).__name__, tentativa + 1)
            esperar(2**tentativa)
    return False


# ── Implementações reais ──────────────────────────────────────────────────


class _SemDesvio(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_: Any, **__: Any) -> None:  # o token não segue para outro endereço
        return None


class VerdeHttp:
    def renovar(self, api_url: str, token: str, client_id: str) -> tuple[int, Any]:
        pedido = urllib.request.Request(
            f"{api_url.rstrip('/')}/autenticacao/token/refresh",
            method="POST",
            headers={"accept": "application/json", "authorization": f"Bearer {token}", "x-client-id": client_id},
        )
        try:
            with urllib.request.build_opener(_SemDesvio).open(pedido, timeout=PRAZO_DO_VERDE_S) as resposta:
                return resposta.status, _json(resposta.read())
        except urllib.error.HTTPError as erro:
            return erro.code, _json(erro.read())
        except (urllib.error.URLError, TimeoutError, OSError) as erro:
            raise RenovacaoInterrompida(f"POST token/refresh sem resposta do Verde ({type(erro).__name__})") from erro


def _json(corpo: bytes) -> Any:
    try:
        return json.loads(corpo)
    except ValueError:
        return None


class SegredosAws:
    def __init__(self, cliente: Any) -> None:
        self._c = cliente

    def ler(self, nome: str) -> dict[str, str]:
        return dict(json.loads(self._c.get_secret_value(SecretId=nome)["SecretString"]))

    def gravar(self, nome: str, valor: dict[str, str]) -> None:
        self._c.put_secret_value(SecretId=nome, SecretString=json.dumps(valor))

    def pegar_trava(self, nome: str, agora: datetime) -> bool:
        for _ in range(2):
            try:
                self._c.create_secret(Name=nome, SecretString=agora.isoformat())
                return True
            except self._c.exceptions.ResourceExistsException:
                criada = self._c.describe_secret(SecretId=nome).get("CreatedDate")
                if criada is None or agora - criada < TRAVA_VELHA:
                    return False
                self.soltar_trava(nome)  # trava de uma execução que morreu no meio
        return False

    def soltar_trava(self, nome: str) -> None:
        self._c.delete_secret(SecretId=nome, ForceDeleteWithoutRecovery=True)


class ServicoEcs:
    def __init__(self, cliente: Any) -> None:
        self._c = cliente

    def redeploy(self, cluster: str, servico: str) -> None:
        self._c.update_service(cluster=cluster, service=servico, forceNewDeployment=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="painel.renovador", description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--simular", action="store_true", help="decide e registra, sem chamar o Verde nem gravar nada")
    parser.add_argument("--ambiente", choices=sorted(SERVICOS), action="append", help="padrão: todos")
    args = parser.parse_args(argv)

    import boto3  # só aqui: os testes não precisam da AWS

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    segredos = SegredosAws(boto3.client("secretsmanager", region_name=REGIAO))
    servico = ServicoEcs(boto3.client("ecs", region_name=REGIAO))
    precisa_de_gente = False
    for ambiente in args.ambiente or sorted(SERVICOS):
        try:
            relato = renovar_ambiente(ambiente, segredos=segredos, verde=VerdeHttp(), servico=servico, agora=datetime.now(UTC), simular=args.simular)
        except RenovacaoInterrompida as erro:
            registro.error("%s", erro)
            precisa_de_gente = True
            continue
        registro.info("renovacao_verde ambiente=%s resultado=%s em=%s", relato.ambiente, relato.resultado.value, relato.em.isoformat())
        precisa_de_gente = precisa_de_gente or relato.resultado in PEDEM_ATENCAO
    return 1 if precisa_de_gente else 0


if __name__ == "__main__":
    sys.exit(main())
