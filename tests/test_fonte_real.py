"""A fonte real sem rede: o que ela faz com as respostas do CloudWatch e do GitHub."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from painel.dados.cache import CacheEmDisco
from painel.dados.modelo import FUSO, Ambiente, Assunto, Estado
from painel.dados.real import FonteReal

AGORA = datetime(2026, 10, 26, 15, 0, tzinfo=FUSO)


class GitHubFalso:
    def __init__(self, log: str) -> None:
        self.log = log
        self.logs_baixados = 0

    def texto(self, _caminho: str) -> str:
        self.logs_baixados += 1
        return self.log


@pytest.fixture
def fonte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FonteReal:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "falso")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "falso")
    return FonteReal(CacheEmDisco(tmp_path), agora=lambda: AGORA, github=GitHubFalso(""))  # type: ignore[arg-type]


LOG = """2026-10-25T15:24:31.0Z \x1b[36;1mprint(f"[{ambiente}] status atual: expirado={expirado} revogado={revogado} expiraEm={expira_em}")\x1b[0m
2026-10-25T15:24:35.9Z [prod] status atual: expirado=False revogado=False expiraEm=2026-11-01T09:28:00.000-03:00
2026-10-25T15:26:10.0Z [prod] token renovado, gravado no Secrets Manager — forçando redeploy do ECS
2026-10-25T15:27:23.0Z [prod] container novo no ar (maria-langgraph-pp/api, 1 tarefa(s)) — token renovado em uso
2026-10-25T15:24:35.9Z [release] status atual: expirado=False revogado=False expiraEm=2026-11-23T10:34:18.160-03:00"""


def _job(id_: int = 1) -> dict[str, Any]:
    return {"id": id_, "status": "completed", "conclusion": "success", "completed_at": "2026-10-25T15:28:00Z"}


def test_le_so_as_linhas_do_ambiente_e_ignora_o_codigo_ecoado(fonte: FonteReal) -> None:
    fonte._github = GitHubFalso(LOG)  # type: ignore[assignment]
    linhas = fonte._linhas_da_conferencia(_job(), Ambiente.PRODUCAO)
    assert linhas.valida_ate == datetime(2026, 11, 1, 9, 28, tzinfo=FUSO)
    assert linhas.renovada_em == datetime(2026, 10, 25, 12, 26, 10, tzinfo=FUSO)
    assert linhas.container_novo_no_ar and linhas.passou
    release = fonte._linhas_da_conferencia(_job(2), Ambiente.RELEASE)
    assert release.renovada_em is None and release.valida_ate == datetime(2026, 11, 23, 10, 34, 18, 160000, tzinfo=FUSO)


def test_validade_none_no_log_nao_quebra(fonte: FonteReal) -> None:
    fonte._github = GitHubFalso("2026-10-01T15:00:00.0Z [prod] status atual: expirado=True revogado=False expiraEm=None")  # type: ignore[assignment]
    assert fonte._linhas_da_conferencia(_job(), Ambiente.PRODUCAO).valida_ate is None


def test_job_terminado_e_baixado_uma_vez_so(fonte: FonteReal) -> None:
    github = GitHubFalso(LOG)
    fonte._github = github  # type: ignore[assignment]
    fonte._linhas_da_conferencia(_job(7), Ambiente.PRODUCAO)
    fonte._linhas_da_conferencia(_job(7), Ambiente.PRODUCAO)
    assert github.logs_baixados == 1


def test_incidente_vai_da_primeira_recusa_ate_a_primeira_aceita(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    horas = [
        {"hora": "2026-10-22 15:00:00.000", "recusadas": "0", "aceitas": "9"},
        {"hora": "2026-10-22 16:00:00.000", "recusadas": "40", "aceitas": "2"},
        {"hora": "2026-10-23 10:00:00.000", "recusadas": "30", "aceitas": "0"},
        {"hora": "2026-10-23 15:00:00.000", "recusadas": "0", "aceitas": "5"},
        # Uma recusa solta não é incidente.
        {"hora": "2026-10-25 12:00:00.000", "recusadas": "1", "aceitas": "0"},
        {"hora": "2026-10-25 13:00:00.000", "recusadas": "0", "aceitas": "3"},
    ]
    respostas = iter(
        [
            {"ini": "2026-10-22 16:27:00.000", "fim": "2026-10-23 10:59:00.000", "n": "70"},
            {"volta": "2026-10-23 15:34:00.000"},
            {"ini": "2026-10-25 12:10:00.000", "fim": "2026-10-25 12:10:00.000", "n": "1"},
        ]
    )
    monkeypatch.setattr(fonte, "_consultar", lambda *a, **k: horas)
    monkeypatch.setattr(fonte, "_uma", lambda *a, **k: next(respostas))
    incidentes = fonte._incidentes(Ambiente.PRODUCAO, AGORA)
    assert len(incidentes) == 1
    assert incidentes[0].inicio == datetime(2026, 10, 22, 13, 27, tzinfo=FUSO)
    assert incidentes[0].fim == datetime(2026, 10, 23, 12, 34, tzinfo=FUSO)
    assert incidentes[0].recusadas == 70


def test_assuntos_pelo_codigo_do_fluxo_e_a_triagem_pelo_total(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    linhas = [
        {"evento": "atendimento_finalizado", "fluxoId": "3df874f2-675a-4c43-9ec7-480f7c702f50", "n": "74", "lido": "63007", "escrito": "2310"},
        {"evento": "atendimento_finalizado", "fluxoId": "fluxo-novo", "n": "2", "lido": "100", "escrito": "5"},
        {"evento": "orquestrador_redirecionado", "n": "3", "so_total": "5000"},
        {"evento": "orquestrador_pergunta_enviada", "n": "4", "so_total": "2000"},
    ]
    monkeypatch.setattr(fonte, "_consultar", lambda *a, **k: linhas)
    leitura = fonte.gasto_por_assunto(Ambiente.RELEASE, date(2026, 10, 26))
    assert leitura.estado is Estado.OK and leitura.valor is not None
    por = {g.assunto: g for g in leitura.valor}
    assert por[Assunto.PESSOA_PRESA].atendimentos == 74 and por[Assunto.PESSOA_PRESA].lido == 63007
    assert por[Assunto.OUTROS].atendimentos == 2
    # A pergunta de desambiguação gasta, mas não é uma triagem terminada.
    assert por[Assunto.TRIAGEM].atendimentos == 3 and por[Assunto.TRIAGEM].so_total == 7000


def test_permissao_negada_vira_texto_sem_nome_tecnico(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    from botocore.exceptions import ClientError

    def negar(*_: Any, **__: Any) -> Any:
        raise ClientError({"Error": {"Code": "AccessDeniedException", "Message": "arn:aws:iam::1:user/x"}}, "StartQuery")

    monkeypatch.setattr(fonte, "_consultar", negar)
    leitura = fonte.gasto_por_assunto(Ambiente.PRODUCAO, date(2026, 10, 26))
    assert leitura.estado is Estado.INDISPONIVEL
    assert leitura.motivo == "Falta permissão de leitura nesta fonte (pedido ao Ícaro)."


def test_sem_credencial_a_tela_diz_o_que_fazer(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    from botocore.exceptions import ClientError, NoCredentialsError

    from painel.dados.real import SEM_CREDENCIAL_DA_AWS

    def sem_credencial(*_: Any, **__: Any) -> Any:
        raise NoCredentialsError()

    monkeypatch.setattr(fonte, "_consultar", sem_credencial)
    leitura = fonte.tempo_de_resposta(Ambiente.PRODUCAO, None)
    assert leitura.estado is Estado.INDISPONIVEL and leitura.motivo == SEM_CREDENCIAL_DA_AWS

    def login_vencido(*_: Any, **__: Any) -> Any:
        raise ClientError({"Error": {"Code": "ExpiredTokenException", "Message": ""}}, "StartQuery")

    monkeypatch.setattr(fonte, "_consultar", login_vencido)
    assert fonte.tempo_de_resposta(Ambiente.PRODUCAO, None).motivo == SEM_CREDENCIAL_DA_AWS


def test_a_faixa_sem_aws_so_aparece_sem_credencial(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from painel import dados

    vazio = tmp_path / "aws"
    vazio.write_text("")
    for nome in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setenv("AWS_CONFIG_FILE", str(vazio))
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(vazio))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("PAINEL_FONTE", "real")
    dados.sem_credencial_da_aws.cache_clear()
    try:
        assert dados.sem_credencial_da_aws()
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "falso")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "falso")
        dados.sem_credencial_da_aws.cache_clear()
        assert not dados.sem_credencial_da_aws()
        monkeypatch.setenv("PAINEL_FONTE", "simulado")
        monkeypatch.delenv("AWS_ACCESS_KEY_ID")
        dados.sem_credencial_da_aws.cache_clear()
        assert not dados.sem_credencial_da_aws()
    finally:
        dados.sem_credencial_da_aws.cache_clear()
