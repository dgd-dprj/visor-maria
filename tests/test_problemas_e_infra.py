"""Problemas e defeitos (Atendimento) e a tela Infra: da linha de log à tela.

A regra que mais importa aqui: nenhuma ocorrência identifica a conversa. O `chatId`
volta da consulta só para saber o que aconteceu depois, e não sai da fonte.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from painel.componentes import problemas
from painel.componentes.filtro_de_dia import OCORRENCIA, Filtro, nome_da_serie
from painel.dados.cache import CacheEmDisco
from painel.dados.modelo import (
    FUSO,
    TIPOS_DE_OCORRENCIA,
    Ambiente,
    EstadoDaParte,
    HoraDaInfra,
    Ocorrencia,
    Origem,
    estado_da_parte,
)
from painel.dados.real import FonteReal, _com_o_depois, _Depois, _do_evento, _do_pedido, _etapa_da_rota

AGORA = datetime(2026, 11, 10, 12, 0, tzinfo=FUSO)
CONVERSA = "conversa-inventada-1"


@pytest.fixture
def fonte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FonteReal:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "falso")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "falso")
    return FonteReal(CacheEmDisco(tmp_path), agora=lambda: AGORA)


# ── Da linha à ocorrência ─────────────────────────────────────────────────


def test_a_rota_com_o_chat_id_no_caminho_nao_mostra_o_chat_id() -> None:
    etapa, conversa = _etapa_da_rota("GET", f"/atendimentos/{CONVERSA}?x=1")
    assert etapa == "GET /atendimentos/:chatId"
    assert conversa == CONVERSA
    assert _etapa_da_rota("POST", "/atendimentos/respostas") == ("POST /atendimentos/respostas", "")


def test_pedido_com_500_e_erro_da_maria_com_o_tipo_da_excecao() -> None:
    linha = {
        "ini": "1794255319653",
        "fim": "1794255319900",
        "caminho": "/atendimentos/respostas",
        "metodo": "POST",
        "codigo": "500",
        "ms": "247",
        "tipo_erro": "TypeError",
        "conversa": CONVERSA,
        "fluxo": "3df874f2-675a-4c43-9ec7-480f7c702f50",
        "reqId": "a1b2",
    }
    resultado = _do_pedido(linha)
    assert resultado is not None
    ocorrencia, conversa, referencia = resultado
    assert (ocorrencia.tipo, ocorrencia.codigo, ocorrencia.pedido) == ("erro_da_maria", "500 TypeError", "a1b2")
    assert conversa == CONVERSA and referencia > ocorrencia.hora


def test_pedido_que_passou_de_30_s_e_resposta_cortada_mesmo_com_200() -> None:
    resultado = _do_pedido({"ini": "2026-11-09 20:15:19.000", "caminho": "/atendimentos/respostas", "metodo": "POST", "codigo": "200", "ms": "90160"})
    assert resultado is not None
    assert (resultado[0].tipo, resultado[0].codigo) == ("resposta_cortada", "200 depois de 90 s")


def test_verde_sem_resposta_traz_a_tentativa_e_a_demora() -> None:
    linha = {
        "@timestamp": "2026-11-09 20:16:49.000",
        "evento": "verde_chamada",
        "chamada": "apenado",
        "resultado": "erro",
        "tipo_erro": "TimeoutError",
        "duracaoMs": "30002",
        "tentativa": "3",
        "chatId": CONVERSA,
    }
    resultado = _do_evento(linha)
    assert resultado is not None
    o = resultado[0]
    assert (o.tipo, o.etapa, o.codigo, o.tentativa) == ("verde", "Verde: apenado", "TimeoutError", "3 de 3")
    assert o.demora == pytest.approx(30.002)


def test_linha_que_nao_e_problema_conhecido_fica_de_fora() -> None:
    assert _do_evento({"@timestamp": "2026-11-09 20:16:49.000", "funcao": "outra"}) is None


def test_nenhuma_ocorrencia_tem_campo_que_identifique_a_conversa() -> None:
    campos = {c.name for c in dataclasses.fields(Ocorrencia)}
    assert not campos & {"chatId", "conversa", "telefone", "texto", "mensagem", "relato"}


# ── O que aconteceu depois ────────────────────────────────────────────────


def _ocorrencia(hora: datetime) -> Ocorrencia:
    return Ocorrencia(hora, "verde", "Verde: apenado", "TimeoutError", 30.0, "", "sem_conversa")


def test_o_depois_encerrou_seguiu_parou_e_ja_encerrada() -> None:
    hora = AGORA - timedelta(hours=2)
    encerrou = _com_o_depois(_ocorrencia(hora), CONVERSA, _Depois(terminou=hora, motivo="falha_infra_verde"), hora, AGORA)
    assert (encerrou.depois, encerrou.motivo) == ("encerrou", "falha_infra_verde")
    seguiu = _com_o_depois(_ocorrencia(hora), CONVERSA, _Depois(ultima_resposta=hora + timedelta(minutes=1)), hora, AGORA)
    assert seguiu.depois == "seguiu"
    assert _com_o_depois(_ocorrencia(hora), CONVERSA, None, hora, AGORA).depois == "parou"
    assert _com_o_depois(_ocorrencia(AGORA - timedelta(minutes=5)), CONVERSA, None, AGORA - timedelta(minutes=5), AGORA).depois == "recente"
    antes = _com_o_depois(_ocorrencia(hora), CONVERSA, _Depois(terminou=hora - timedelta(hours=1), motivo="rg_nao_encontrado"), hora, AGORA)
    assert antes.depois == "ja_encerrada"
    assert _com_o_depois(_ocorrencia(hora), "", None, hora, AGORA).depois == "sem_conversa"


def test_a_fonte_real_liga_o_depois_sem_devolver_o_chat_id(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    pedidos = [{"ini": "2026-11-09 20:15:19.000", "fim": "2026-11-09 20:16:49.000", "caminho": "/atendimentos/respostas", "metodo": "POST",
                "codigo": "200", "ms": "90160", "conversa": CONVERSA, "reqId": "r1"}]  # fmt: skip
    eventos = [{"@timestamp": "2026-11-09 20:15:49.000", "evento": "verde_chamada", "chamada": "apenado", "resultado": "erro",
                "tipo_erro": "TimeoutError", "duracaoMs": "30000", "tentativa": "1", "chatId": CONVERSA}]  # fmt: skip
    depois = [{"chatId": CONVERSA, "evento": "atendimento_finalizado", "ultima": "2026-11-09 20:16:49.000", "motivo": "falha_infra_verde"}]
    consultas: list[str] = []

    # As duas primeiras consultas rodam juntas: a resposta sai pelo conteúdo, e não pela ordem.
    def consultar(_ambientes: Any, _inicio: Any, _fim: Any, consulta: str, limite: int = 1000) -> list[dict[str, str]]:
        consultas.append(consulta)
        if "chatId in [" in consulta:
            return depois
        return pedidos if "incoming request" in consulta else eventos

    monkeypatch.setattr(fonte, "_consultar", consultar)
    leitura = fonte.ocorrencias(Origem.PRODUCAO_PY)
    assert leitura.valor is not None
    assert leitura.valor.conversas == 1
    assert {o.depois for o in leitura.valor.ocorrencias} == {"encerrou"}
    assert any(CONVERSA in c for c in consultas if "chatId in [" in c)
    assert CONVERSA not in repr(leitura)


# ── Os filtros e o pico ───────────────────────────────────────────────────


def test_filtrar_pelo_tipo_do_clique_e_pelos_filtros_do_quadro() -> None:
    base = _ocorrencia(AGORA)
    lista = [base, dataclasses.replace(base, tipo="recusa", codigo="409", fluxo="x"), dataclasses.replace(base, depois="encerrou")]
    assert len(problemas.filtrar(lista, problemas.Escolhas(), Filtro())) == 3
    assert len(problemas.filtrar(lista, problemas.Escolhas(), Filtro(serie=f"{OCORRENCIA}recusa"))) == 1
    assert len(problemas.filtrar(lista, problemas.Escolhas(fluxo=problemas.SEM_FLUXO), Filtro())) == 2
    assert len(problemas.filtrar(lista, problemas.Escolhas(codigo="409"), Filtro())) == 1
    assert len(problemas.filtrar(lista, problemas.Escolhas(depois="encerrou"), Filtro())) == 1


def test_hora_de_pico_e_a_hora_com_mais_ocorrencias() -> None:
    lista = [_ocorrencia(AGORA.replace(hour=h)) for h in (9, 16, 16, 16, 9)]
    assert problemas.hora_de_pico(lista) == (16, 3)
    assert problemas.hora_de_pico([]) is None


def test_todo_tipo_tem_nome_na_faixa_do_filtro() -> None:
    for tipo, (nome, _, _) in TIPOS_DE_OCORRENCIA.items():
        assert nome_da_serie(f"{OCORRENCIA}{tipo}") == nome


def test_a_consulta_do_log_usa_o_pedido_quando_tem() -> None:
    com_pedido = dataclasses.replace(_ocorrencia(AGORA), pedido="r1")
    assert 'reqId = "r1"' in problemas.consulta_do_log(com_pedido, Ambiente.PRODUCAO)
    assert "verde_chamada" in problemas.consulta_do_log(_ocorrencia(AGORA), Ambiente.PRODUCAO)


# ── Infra ─────────────────────────────────────────────────────────────────


def _hora(**campos: Any) -> HoraDaInfra:
    padrao: dict[str, Any] = dict(
        hora=AGORA, pedidos=100, erros_5xx=0, erros_4xx=0, p99=2.0, saudaveis=1.0, desejados=1.0, cpu=2.0, memoria=22.0, reinicios=0,
        banco_cpu=7.0, banco_conexoes=10.0, banco_memoria_livre=9.5e8, saida_erros=0, ia_recusas=0, email_erros=0, verde_falhas=0, respostas_cortadas=0,
    )  # fmt: skip
    return HoraDaInfra(**{**padrao, **campos})


def test_os_limites_de_cada_parte() -> None:
    assert all(estado_da_parte(p, _hora()) is EstadoDaParte.BOM for p in ("entrada", "tempo", "containers", "banco", "saida", "verde", "ia", "email"))
    assert estado_da_parte("entrada", _hora(erros_5xx=1)) is EstadoDaParte.ATENCAO
    assert estado_da_parte("entrada", _hora(erros_5xx=6)) is EstadoDaParte.RUIM
    assert estado_da_parte("entrada", _hora(pedidos=0)) is EstadoDaParte.SEM_USO
    assert estado_da_parte("tempo", _hora(p99=12.0)) is EstadoDaParte.ATENCAO
    assert estado_da_parte("tempo", _hora(p99=29.0, respostas_cortadas=1)) is EstadoDaParte.RUIM
    assert estado_da_parte("containers", _hora(saudaveis=0.0)) is EstadoDaParte.RUIM
    assert estado_da_parte("containers", _hora(reinicios=1)) is EstadoDaParte.ATENCAO
    assert estado_da_parte("banco", _hora(banco_cpu=85.0)) is EstadoDaParte.RUIM
    assert estado_da_parte("verde", _hora(verde_falhas=14)) is EstadoDaParte.RUIM
    assert estado_da_parte("email", _hora(email_erros=1)) is EstadoDaParte.RUIM


def test_horas_seguidas_com_problema_viram_um_trecho_so() -> None:
    from painel.pages import infra

    horas = [
        _hora(hora=AGORA.replace(hour=15), verde_falhas=6),
        _hora(hora=AGORA.replace(hour=16), verde_falhas=8, erros_5xx=6),
        _hora(hora=AGORA.replace(hour=17)),
        _hora(hora=AGORA.replace(hour=19), email_erros=1),
    ]
    trechos = infra._instabilidades(horas)
    assert [(t[0].hour, t[1].hour) for t in trechos] == [(19, 20), (15, 17)]
    assert trechos[1][2]["verde"] == 14 and trechos[1][2]["entrada"] == 6


def test_a_fonte_real_da_infra_junta_metricas_e_logs(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    hora = AGORA.replace(hour=11)
    metricas: dict[str, dict[datetime, float]] = {n: {} for n in ("pedidos", "taxa5", "taxa4", "p99", "saudaveis", "desejados", "cpu", "memoria", "banco_cpu", "banco_conexoes",
                                "banco_memoria", "nat_portas", "nat_perdidos", "ia_pedido", "ia_servico", "ia_limitadas", "email_erros", "email_limitadas")}  # fmt: skip
    metricas["pedidos"][hora] = 200.0
    metricas["taxa5"][hora] = 3.0
    monkeypatch.setattr(fonte, "_varias_series", lambda *a, **k: metricas)
    monkeypatch.setattr(fonte, "_dimensoes_do_balanceador", lambda _a: [])
    monkeypatch.setattr(fonte, "_consultar", lambda *a, **k: [{"hora": "2026-11-10 14:00:00.000", "verde": "4", "cortadas": "2", "subidas": "1"}])
    horas = fonte._horas_da_infra(Ambiente.PRODUCAO, hora, hora + timedelta(hours=1))
    assert len(horas) == 1
    h = horas[0]
    assert (h.pedidos, h.erros_5xx, h.verde_falhas, h.respostas_cortadas, h.reinicios) == (200, 6, 4, 2, 1)


def test_os_graves_aparecem_um_a_um_mesmo_com_um_tipo_escolhido() -> None:
    from painel.dados.fontes import fonte_ocorrencias
    from painel.dados.modelo import Estado, Leitura, OcorrenciasDoPeriodo

    base = _ocorrencia(AGORA)
    lista = [
        dataclasses.replace(base, tipo="erro_da_maria", codigo="500 TypeError", etapa="POST /atendimentos/respostas"),
        dataclasses.replace(base, tipo="resposta_cortada", codigo="200 depois de 90 s", demora=90.2, depois="encerrou", motivo="falha_infra_verde"),
        base,
    ]
    leitura = Leitura(OcorrenciasDoPeriodo(AGORA - timedelta(days=1), AGORA, lista, 2), Estado.OK, fonte_ocorrencias(Origem.PRODUCAO_PY), AGORA)
    texto = str(problemas.conteudo(leitura, Ambiente.PRODUCAO, Filtro(serie=f"{OCORRENCIA}verde"), problemas.Escolhas(), None, AGORA))
    for tipo in problemas.GRAVES:
        assert TIPOS_DE_OCORRENCIA[tipo][0] in texto
    assert "500 TypeError" in texto and "Falha ao consultar o Verde" in texto
