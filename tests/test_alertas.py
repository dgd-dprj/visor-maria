"""O quadro Alertas da Agora e a leitura dos alarmes de infra/alertas (issue #2)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from painel.dados.cache import CacheEmDisco
from painel.dados.fontes import fonte_alarmes
from painel.dados.modelo import FUSO, Alarme, Ambiente, Estado, EstadoDoAlarme, Leitura, TipoDeAlarme, alarme_do_nome
from painel.dados.real import FonteReal
from painel.dados.simulado import FonteSimulada
from painel.pages.agora import SEM_ALERTAS, alertas

AGORA = datetime(2026, 11, 3, 15, 0, tzinfo=FUSO)


def _textos(no: Any) -> str:
    return json.dumps(no.to_plotly_json(), default=lambda c: c.to_plotly_json(), ensure_ascii=False)


@pytest.mark.parametrize(
    ("nome", "esperado"),
    [
        ("visor-maria-producao-cpu-alta", (Ambiente.PRODUCAO, TipoDeAlarme.CPU_ALTA)),
        ("visor-maria-release-erros-5xx", (Ambiente.RELEASE, TipoDeAlarme.ERROS_5XX)),
        ("visor-maria-producao-verde-recusou", (Ambiente.PRODUCAO, TipoDeAlarme.VERDE_RECUSOU)),
        # Alarme de outro dono na conta, ambiente ou tipo que o Visor não conhece.
        ("maria-langgraph-pp-cpu", None),
        ("visor-maria-homologacao-cpu-alta", None),
        ("visor-maria-producao-disco-cheio", None),
    ],
)
def test_o_nome_do_alarme_diz_o_ambiente_e_o_tipo(nome: str, esperado: tuple[Ambiente, TipoDeAlarme] | None) -> None:
    assert alarme_do_nome(nome) == esperado


class _Paginador:
    def __init__(self, metricas: "_MetricasFalsas", nome: str) -> None:
        self._metricas = metricas
        self._nome = nome

    def paginate(self, **parametros: Any) -> list[dict[str, Any]]:
        if self._nome == "describe_alarms":
            return [{"MetricAlarms": self._metricas.alarmes}]
        nome = parametros["AlarmName"]
        self._metricas.historicos_pedidos.append(nome)
        itens = [{"HistoryData": json.dumps({"newState": {"stateValue": e}})} for e in self._metricas.historico.get(nome, [])]
        # Duas páginas: um disparo na segunda página também precisa contar.
        return [{"AlarmHistoryItems": itens[:2]}, {"AlarmHistoryItems": itens[2:]}]


class _MetricasFalsas:
    """O que a AWS devolve: os alarmes com o prefixo e o histórico de cada um."""

    def __init__(self, alarmes: list[dict[str, Any]], historico: dict[str, list[str]]) -> None:
        self.alarmes = alarmes
        self.historico = historico
        self.historicos_pedidos: list[str] = []

    def get_paginator(self, nome: str) -> _Paginador:
        assert nome in ("describe_alarms", "describe_alarm_history")
        return _Paginador(self, nome)


@pytest.fixture
def fonte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FonteReal:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "falso")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "falso")
    return FonteReal(CacheEmDisco(tmp_path), agora=lambda: AGORA)


def _descrito(nome: str, estado: str) -> dict[str, Any]:
    return {"AlarmName": nome, "StateValue": estado, "StateTransitionedTimestamp": datetime(2026, 11, 3, 14, 35, tzinfo=FUSO)}


def test_a_fonte_real_conta_os_disparos_da_semana_e_ignora_alarme_de_fora(fonte: FonteReal) -> None:
    metricas = _MetricasFalsas(
        [
            _descrito("visor-maria-producao-latencia-p99", "ALARM"),
            _descrito("visor-maria-producao-cpu-alta", "OK"),
            _descrito("visor-maria-alarme-antigo", "ALARM"),
        ],
        # Cada disparo é uma ida para ALARM; a volta para OK não conta.
        {"visor-maria-producao-latencia-p99": ["ALARM", "OK", "ALARM", "OK", "ALARM"]},
    )
    fonte._metricas = metricas
    leitura = fonte.alarmes()
    assert leitura.estado is Estado.OK and leitura.valor is not None
    por_tipo = {a.tipo: a for a in leitura.valor}
    assert set(por_tipo) == {TipoDeAlarme.LATENCIA_P99, TipoDeAlarme.CPU_ALTA}
    assert por_tipo[TipoDeAlarme.LATENCIA_P99].estado is EstadoDoAlarme.DISPARADO
    assert por_tipo[TipoDeAlarme.LATENCIA_P99].disparos_na_semana == 3
    assert por_tipo[TipoDeAlarme.CPU_ALTA].disparos_na_semana == 0
    # O histórico é pedido por alarme do Visor, nunca o da conta inteira.
    assert "visor-maria-alarme-antigo" not in metricas.historicos_pedidos


def test_sem_alarmes_na_aws_a_leitura_e_vazia(fonte: FonteReal) -> None:
    fonte._metricas = _MetricasFalsas([], {})
    assert fonte.alarmes().estado is Estado.VAZIO


def _agora_com(leitura: Leitura[list[Alarme]]) -> Any:
    # O quadro só lê a hora e os alarmes das leituras da Agora.
    return SimpleNamespace(agora=AGORA, alarmes=leitura)


def test_o_quadro_mostra_o_estado_os_disparos_e_o_verde_so_em_producao() -> None:
    leitura = FonteSimulada("normal", agora=lambda: AGORA).alarmes()
    texto = _textos(alertas(_agora_com(leitura)))
    assert "Disparado" in texto and "Normal" in texto
    assert "31 disparos em 7 dias" in texto
    assert "1 disparado agora" in texto
    # O alerta do Verde existe só em produção: no release, a célula diz que não há vigia.
    assert texto.count("não vigiado aqui") == 1


def test_antes_do_apply_o_quadro_diz_quem_cria_os_alertas() -> None:
    vazio = Leitura[list[Alarme]](None, Estado.VAZIO, fonte_alarmes(), AGORA)
    assert SEM_ALERTAS in _textos(alertas(_agora_com(vazio)))


def test_sem_permissao_o_quadro_diz_o_motivo() -> None:
    falha = Leitura[list[Alarme]](None, Estado.INDISPONIVEL, fonte_alarmes(), AGORA, "Falta permissão de leitura nesta fonte (pedido ao Ícaro).")
    texto = _textos(alertas(_agora_com(falha)))
    assert "Falta permissão de leitura" in texto and SEM_ALERTAS not in texto
