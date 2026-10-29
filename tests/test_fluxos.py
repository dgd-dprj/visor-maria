"""A tela Fluxos: o que a fonte real faz com as linhas por conversa, o filtro
por fluxo e por problema, e a tela com cada escolha seguindo as regras."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import dash
import pytest

from painel.componentes import filtro_de_dia
from painel.dados.cache import CacheEmDisco
from painel.dados.modelo import (
    FUSO,
    NOME_DO_DESFECHO,
    Ambiente,
    Destino,
    Estado,
    FimDaConversa,
    SaidaDaTriagem,
    TipoDeProblema,
    nome_do_fluxo,
    tipo_do_motivo,
)
from painel.dados.real import FonteReal
from painel.dados.simulado import PESSOA_PRESA, PLANO_DE_SAUDE, FonteSimulada
from tests.test_regras_de_texto import _classes, _componentes, _sem_hifen, _textos

AGORA = datetime(2026, 10, 28, 15, 0, tzinfo=FUSO)
Filtro = filtro_de_dia.Filtro


@pytest.fixture
def fonte(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FonteReal:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "falso")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "falso")
    return FonteReal(CacheEmDisco(tmp_path), agora=lambda: AGORA)


# ── A fonte real ──────────────────────────────────────────────────────────


def test_cada_conversa_cai_num_fim_so(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    linhas = [
        {"fluxo": PESSOA_PRESA, "respostas": "11", "terminou": "1", "encaminhou": "1", "expirada": "0", "conversas": "5"},
        {"fluxo": PESSOA_PRESA, "respostas": "9", "terminou": "1", "expirada": "0", "conversas": "3"},
        {"fluxo": PESSOA_PRESA, "respostas": "3", "terminou": "0", "expirada": "0", "conversas": "7"},
        {"fluxo": PLANO_DE_SAUDE, "respostas": "1", "terminou": "0", "expirada": "1", "conversas": "1"},
    ]
    consultas: list[str] = []

    def consultar(_ambientes: Any, _inicio: datetime, _fim: datetime, consulta: str, **_: Any) -> list[dict[str, str]]:
        consultas.append(consulta)
        return linhas

    monkeypatch.setattr(fonte, "_consultar", consultar)
    leitura = fonte.conversas_por_fluxo(Ambiente.PRODUCAO)
    assert leitura.estado is Estado.OK and leitura.valor is not None
    assert [c.fim for c in leitura.valor] == [FimDaConversa.ENCAMINHOU, FimDaConversa.CONCLUIU, FimDaConversa.PAROU, FimDaConversa.EXPIROU]
    # O identificador da conversa junta os eventos, e a consulta só devolve contagens.
    assert "by chatId" in consultas[0] and "count(*) as conversas by fluxo" in consultas[0]


def test_a_conversa_conta_pela_janela_em_que_comecou(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    janelas: list[tuple[datetime, datetime, str]] = []

    def consultar(_ambientes: Any, inicio: datetime, fim: datetime, consulta: str, **_: Any) -> list[dict[str, str]]:
        janelas.append((inicio, fim, consulta))
        return []

    monkeypatch.setattr(fonte, "_consultar", consultar)
    hora = datetime(2026, 10, 27, 14, tzinfo=FUSO)
    fonte.conversas_por_fluxo(Ambiente.PRODUCAO, hora)
    inicio, fim, consulta = janelas[0]
    # Lê 3 horas além da hora escolhida, para ver como terminaram, mas só conta as que começaram nela.
    assert inicio == hora and fim == hora + timedelta(hours=4)
    assert f"ini >= {int(hora.timestamp() * 1000)}" in consulta and f"ini < {int((hora + timedelta(hours=1)).timestamp() * 1000)}" in consulta


def test_triagem_le_o_alvo_de_cada_saida(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    linhas = [
        {"evento": "orquestrador_fluxo_identificado", "flowId": PESSOA_PRESA, "n": "51"},
        {"evento": "orquestrador_redirecionado", "destino": "tykhe", "tipoCaso": "saude", "n": "15"},
        {"evento": "orquestrador_finalizado_sem_fluxo", "destino": "atendimento_humano", "n": "1"},
        {"evento": "orquestrador_pergunta_enviada", "n": "28"},
    ]
    monkeypatch.setattr(fonte, "_consultar", lambda *a, **k: linhas)
    leitura = fonte.triagem(Ambiente.RELEASE)
    assert leitura.valor is not None
    assert [(r.saida, r.alvo, r.vezes) for r in leitura.valor] == [
        (SaidaDaTriagem.IDENTIFICOU, PESSOA_PRESA, 51),
        (SaidaDaTriagem.REDIRECIONOU, "saude", 15),
        (SaidaDaTriagem.SEM_FLUXO, "atendimento_humano", 1),
        (SaidaDaTriagem.PERGUNTOU, "", 28),
    ]


def test_o_verde_que_falhou_vira_problema_pelo_motivo(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    linhas = [
        {"dia": "2026-10-27 00:00:00.000", "evento": "atendimento_finalizado", "fluxoId": PESSOA_PRESA, "n": "2"},
        {"dia": "2026-10-27 00:00:00.000", "evento": "whatsapp_envio_falhou", "n": "1"},
    ]
    monkeypatch.setattr(fonte, "_consultar", lambda *a, **k: linhas)
    leitura = fonte.problemas_por_dia(Ambiente.RELEASE)
    assert leitura.valor is not None
    assert {(p.problema, p.fluxo, p.vezes) for p in leitura.valor} == {("falha_infra_verde", PESSOA_PRESA, 2), ("whatsapp_envio_falhou", "", 1)}


def test_encaminhamentos_leem_destino_motivo_e_a_triagem(fonte: FonteReal, monkeypatch: pytest.MonkeyPatch) -> None:
    dia = "2026-10-27 00:00:00.000"
    linhas = [
        {
            "dia": dia,
            "evento": "atendimento_finalizado",
            "fluxoId": PESSOA_PRESA,
            "destino": "atendimento_humano",
            "motivoHandoff": "rg_nao_encontrado",
            "n": "4",
        },
        {"dia": dia, "evento": "atendimento_finalizado", "fluxoId": PESSOA_PRESA, "n": "2"},
        {"dia": dia, "evento": "atendimento_finalizado", "fluxoId": PESSOA_PRESA, "destino": "sessao_expirada", "n": "1"},
        {"dia": dia, "evento": "orquestrador_finalizado_sem_fluxo", "fluxoId": PESSOA_PRESA, "destino": "atendimento_humano", "n": "3"},
    ]
    consultas: list[str] = []

    def consultar(_ambientes: Any, _inicio: datetime, _fim: datetime, consulta: str, **_: Any) -> list[dict[str, str]]:
        consultas.append(consulta)
        return linhas

    monkeypatch.setattr(fonte, "_consultar", consultar)
    leitura = fonte.encaminhamentos_por_dia(Ambiente.RELEASE)
    assert leitura.valor is not None
    assert {(e.fluxo, e.destino, e.motivo, e.atendimentos) for e in leitura.valor} == {
        (PESSOA_PRESA, Destino.HUMANO, "rg_nao_encontrado", 4),
        (PESSOA_PRESA, Destino.IA, "", 2),
        (PESSOA_PRESA, Destino.SAIU, "", 1),
        # A triagem fica fora dos fluxos, com motivo próprio.
        ("", Destino.HUMANO, "triagem_sem_fluxo", 3),
    }
    # Só contagens: nenhuma conversa sai da consulta.
    assert "chatId" not in consultas[0]


def test_todo_motivo_conhecido_tem_um_tipo_de_problema() -> None:
    sem_tipo = [m for m in NOME_DO_DESFECHO if m and tipo_do_motivo(m) is TipoDeProblema.SEM_MOTIVO]
    assert not sem_tipo
    assert tipo_do_motivo("falha_infra_verde") is TipoDeProblema.FALHA
    assert tipo_do_motivo("motivo_que_ainda_nao_existe") is TipoDeProblema.SEM_MOTIVO


# ── O simulado ────────────────────────────────────────────────────────────


def test_producao_nao_tem_triagem_e_o_release_tem() -> None:
    fonte = FonteSimulada()
    assert fonte.triagem(Ambiente.PRODUCAO).estado is Estado.VAZIO
    assert fonte.triagem(Ambiente.RELEASE).estado is Estado.OK
    assert {c.fluxo for c in fonte.conversas_por_fluxo(Ambiente.PRODUCAO).valor or []} == {PESSOA_PRESA}


def test_fluxo_novo_aparece_pelo_codigo() -> None:
    assert nome_do_fluxo(PESSOA_PRESA) == "Pessoa presa"
    assert nome_do_fluxo("0123abcd-0000-0000-0000-000000000000") == "Fluxo 0123abcd"


# ── O filtro ──────────────────────────────────────────────────────────────


def test_o_clique_num_fluxo_e_num_problema_escolhe_a_categoria() -> None:
    agora = datetime.now(FUSO)
    grafico = {"tipo": filtro_de_dia.GRAFICO, "tela": "fluxos", "nome": "fluxos", "por": "categoria", "series": ""}
    clique = {"points": [{"x": 30, "y": "Pessoa presa", "customdata": ["parou no meio", f"fluxo:{PESSOA_PRESA}"]}]}
    escolha = filtro_de_dia.proximo(Filtro(), grafico, clique, agora)
    assert escolha is not None and escolha.fluxo == PESSOA_PRESA
    assert filtro_de_dia.proximo(escolha, grafico, clique, agora) == Filtro()
    legenda = {"tipo": filtro_de_dia.LEGENDA, "tela": "fluxos", "serie": "problema:atendimento_expirado"}
    escolha = filtro_de_dia.proximo(Filtro(), legenda, 1, agora)
    assert escolha is not None and escolha.problema == "atendimento_expirado"


ESCOLHAS = [
    Filtro(),
    Filtro(datetime.now(FUSO).date() - timedelta(days=1)),
    Filtro(datetime.now(FUSO).date() - timedelta(days=1), 14),
    Filtro(None, None, f"fluxo:{PESSOA_PRESA}"),
    Filtro(None, None, f"fluxo:{PLANO_DE_SAUDE}"),
    Filtro(None, None, "problema:whatsapp_status_entrega"),
    Filtro(None, None, "motivo:rg_nao_encontrado"),
]


def _da_tela() -> dict[str, Any]:
    return next(p for p in dash.page_registry.values() if p["name"] == "Fluxos")["layout"].__globals__


@pytest.mark.parametrize("ambiente", list(Ambiente))
@pytest.mark.parametrize("escolha", ESCOLHAS, ids=["sem", "dia", "hora", "pessoa presa", "plano de saude", "problema", "motivo"])
def test_a_tela_com_cada_escolha_segue_as_regras(ambiente: Ambiente, escolha: Filtro, cenario: str) -> None:
    from painel import lateral

    tela = _da_tela()
    for montado in (tela["blocos"](ambiente, escolha), lateral.dos_fluxos(ambiente, None, escolha)):
        textos = list(_textos(montado))
        _sem_hifen(textos)
        assert not [t for t in textos if "sem dados" in t.lower()]
        for bloco in (c for c in _componentes(montado) if {"indicador", "quadro"} & _classes(c)):
            notas = [c for c in _componentes(bloco) if "fonte-curta" in _classes(c)]
            assert notas and "lido " in "".join(_textos(notas[0]))


def test_os_quadros_seguem_o_fluxo_escolhido() -> None:
    tela = _da_tela()
    texto = " ".join(_textos(tela["blocos"](Ambiente.RELEASE, Filtro(None, None, f"fluxo:{PLANO_DE_SAUDE}"))))
    assert "Problemas com plano de saúde, nos últimos 7 dias" in texto
    # A triagem e os fluxos mais acessados aparecem; o fluxo escolhido em destaque.
    assert "Como a triagem direcionou" in texto and "Fluxos mais acessados" in texto
