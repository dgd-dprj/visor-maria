"""O contrato com os logs da Maria: falha quando um nome de evento ou de campo muda.

O painel e a Maria moram em repositórios diferentes. Sem este teste, uma
renomeação na Maria faz as consultas do painel devolverem zero, sem erro.

Confere o que o painel lê (`painel/dados/contrato.py`) contra:
1. o retrato do código da Maria (`fixtures/maria/contrato_extraido.json`), que o
   CI refaz todo dia a partir de `main` e de `develop` da Maria;
2. os logs de referência da Maria (`fixtures/maria/logs/`), com as lacunas
   declaradas em `FORA_DOS_LOGS_DE_REFERENCIA`.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from painel.dados import contrato, fontes
from painel.dados.modelo import Ambiente, Origem

PASTA = Path(__file__).parent / "fixtures" / "maria"
RETRATO = json.loads((PASTA / "contrato_extraido.json").read_text(encoding="utf-8"))


def _eventos_dos_logs() -> dict[str, set[str]]:
    eventos: dict[str, set[str]] = {}
    for arquivo in sorted((PASTA / "logs").glob("*.ndjson")):
        for linha in arquivo.read_text(encoding="utf-8").splitlines():
            if linha.strip():
                registro = json.loads(linha)
                if "evento" in registro:
                    eventos.setdefault(registro["evento"], set()).update(registro)
    return eventos


LOGS = _eventos_dos_logs()


@pytest.mark.parametrize("evento", sorted(contrato.EVENTOS))
def test_o_codigo_da_maria_registra_o_evento_e_os_campos_que_o_painel_le(evento: str) -> None:
    registrados = RETRATO["eventos"]
    origem = f"maria-langgraph-pp @ {RETRATO['origem']['commit'][:7]}"
    assert evento in registrados, f"{origem} não registra mais o evento {evento!r}: o painel lê esse nome"
    faltam = sorted(contrato.EVENTOS[evento] - set(registrados[evento]))
    assert not faltam, f"{origem} não registra mais {faltam} no evento {evento!r}: o painel lê esses campos"


# A conferência diária roda da branch padrão do maria-langgraph-pp (develop): é lá
# que as linhas importam. Em main, elas chegam no release seguinte.
BRANCH_DA_CONFERENCIA = "develop"


def test_a_conferencia_diaria_ainda_imprime_as_linhas_que_o_painel_procura() -> None:
    if RETRATO["origem"].get("branch") != BRANCH_DA_CONFERENCIA:
        pytest.skip(f"a conferência diária roda de {BRANCH_DA_CONFERENCIA}, e este retrato é de {RETRATO['origem'].get('branch')}")
    faltam = sorted(contrato.LINHAS_DO_WORKFLOW - set(RETRATO["linhas_do_workflow"]))
    assert not faltam, f"verificar-token-verde.yml não imprime mais {faltam}: o painel lê a validade e as renovações por elas"


@pytest.mark.parametrize("evento", sorted(contrato.EVENTOS))
def test_os_logs_de_referencia_mostram_o_que_o_painel_le(evento: str) -> None:
    lacuna = contrato.FORA_DOS_LOGS_DE_REFERENCIA.get(evento, frozenset())
    if "*" in lacuna:
        assert evento not in LOGS, f"os logs de referência passaram a ter {evento!r}: tire-o de FORA_DOS_LOGS_DE_REFERENCIA"
        return
    assert evento in LOGS, f"os logs de referência não têm {evento!r}, e ele não está em FORA_DOS_LOGS_DE_REFERENCIA"
    faltam = sorted(contrato.EVENTOS[evento] - LOGS[evento] - lacuna)
    assert not faltam, f"os logs de referência não têm {faltam} em {evento!r}"
    voltaram = sorted(lacuna & LOGS[evento])
    assert not voltaram, f"os logs de referência passaram a ter {voltaram} em {evento!r}: tire de FORA_DOS_LOGS_DE_REFERENCIA"


def test_as_lacunas_declaradas_sao_de_eventos_do_contrato() -> None:
    for evento, campos in contrato.FORA_DOS_LOGS_DE_REFERENCIA.items():
        assert evento in contrato.EVENTOS
        assert campos == {"*"} or campos <= contrato.EVENTOS[evento]


def _identificadores_das_fontes() -> list[str]:
    produtores = [getattr(fontes, nome) for nome in dir(fontes) if nome.startswith("fonte_")]
    identificadores = []
    for produtor in produtores:
        for argumentos in ((Ambiente.PRODUCAO,), (Origem.PRODUCAO_PY,), ()):
            try:
                identificadores.append(produtor(*argumentos).identificador)
                break
            except (TypeError, KeyError):
                continue
    return identificadores


def test_todo_evento_citado_nas_fontes_esta_no_contrato() -> None:
    """Uma fonte nova que cite um evento fora do contrato não seria conferida contra a Maria."""
    padrao = re.compile(r"\b((?:atendimento|pergunta|resposta|verde|orquestrador|ttl|whatsapp)_[a-z_]+)\b")
    citados = {e for identificador in _identificadores_das_fontes() for e in padrao.findall(identificador)}
    assert citados
    assert not sorted(citados - set(contrato.EVENTOS))
