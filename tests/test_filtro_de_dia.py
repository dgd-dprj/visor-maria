"""O filtro de dia: o clique num dia de um gráfico refaz a tela naquele dia.

As regras de texto valem também para a tela filtrada, nos três cenários; o
clique escolhe o dia, o mesmo dia de novo tira o filtro; e o dia que já passou
fica guardado no cache sem prazo.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextvars import copy_context
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import dash
import plotly.graph_objects as go
import pytest
from dash._callback_context import context_value
from dash._utils import AttributeDict

from painel import lateral
from painel.componentes import filtro_de_dia
from painel.componentes.menu import TELAS
from painel.dados.cache import CacheEmDisco, FonteComCache
from painel.dados.consultas import fim_do_dia
from painel.dados.modelo import FUSO, Ambiente, Estado, Origem
from painel.dados.simulado import FonteSimulada
from tests.test_cache import Contadora
from tests.test_regras_de_texto import _classes, _componentes, _props, _sem_hifen, _textos

# A tela financeira tem o filtro de período dela, que já filtra pelo clique.
COM_FILTRO_DE_DIA = [nome for nome, _, _ in TELAS if nome != "Relatório da Aplicação"]
HOJE = datetime.now(FUSO).date()
ONTEM = HOJE - timedelta(days=1)


def _tela_no_dia(nome: str, dia: date) -> Any:
    pagina = next(p for p in dash.page_registry.values() if p["name"] == nome)
    return pagina["layout"](dia=dia.isoformat())


# ── O dia escolhido ───────────────────────────────────────────────────────


def test_o_dia_vale_dentro_dos_30_dias_de_registro() -> None:
    agora = datetime(2026, 10, 26, 15, 0, tzinfo=FUSO)
    assert filtro_de_dia.ler("2026-10-22", agora) == date(2026, 10, 22)
    assert filtro_de_dia.ler("2026-10-22 12:00", agora) == date(2026, 10, 22)
    assert filtro_de_dia.ler("2026-09-27", agora) == date(2026, 9, 27)
    # Antes do registro, no futuro ou sem sentido: a tela volta à janela padrão.
    assert filtro_de_dia.ler("2026-09-26", agora) is None
    assert filtro_de_dia.ler("2026-10-27", agora) is None
    assert filtro_de_dia.ler("ontem", agora) is None
    assert filtro_de_dia.ler(None, agora) is None


GRAFICO_DO_VERDE = {"tipo": filtro_de_dia.GRAFICO, "tela": "agora", "nome": "verde", "por": "dia", "series": "aceitas|recusadas|outras"}
GRAFICO_DE_DIA = {"tipo": filtro_de_dia.GRAFICO, "tela": "dia", "nome": "dias", "por": "dia", "series": ""}
GRAFICO_DE_HORA = {"tipo": filtro_de_dia.GRAFICO, "tela": "agora", "nome": "horas", "por": "hora", "series": ""}
GRAFICO_DE_MOTIVO = {"tipo": filtro_de_dia.GRAFICO, "tela": "dia", "nome": "desfechos", "por": "categoria", "series": ""}
LEGENDA_RECUSOU = {"tipo": filtro_de_dia.LEGENDA, "tela": "agora", "serie": "recusadas"}
LIMPAR = {"tipo": filtro_de_dia.LIMPAR, "tela": "agora"}
AGORA = datetime.now(FUSO)
Filtro = filtro_de_dia.Filtro


def _no_dia(x: str, curva: int = 0, **extra: Any) -> dict[str, Any]:
    return {"points": [{"x": x, "y": 40, "curveNumber": curva, **extra}]}


def _clique(atual: Filtro, gatilho: dict[str, Any], valor: Any) -> Filtro | None:
    return filtro_de_dia.proximo(atual, gatilho, valor, AGORA)


def test_o_clique_num_dia_escolhe_o_dia_e_de_novo_tira() -> None:
    clique = _no_dia(f"{ONTEM.isoformat()} 12:00")
    assert _clique(Filtro(), GRAFICO_DE_DIA, clique) == Filtro(ONTEM)
    assert _clique(Filtro(ONTEM), GRAFICO_DE_DIA, clique) == Filtro()


def test_o_segmento_do_verde_escolhe_o_dia_e_o_resultado() -> None:
    recusou = _no_dia(f"{ONTEM.isoformat()} 12:00", curva=1)
    assert _clique(Filtro(), GRAFICO_DO_VERDE, recusou) == Filtro(ONTEM, None, "recusadas")
    # O mesmo segmento de novo desfaz tudo; outro resultado no mesmo dia troca o resultado.
    assert _clique(Filtro(ONTEM, None, "recusadas"), GRAFICO_DO_VERDE, recusou) == Filtro()
    assert _clique(Filtro(ONTEM, None, "recusadas"), GRAFICO_DO_VERDE, _no_dia(f"{ONTEM.isoformat()} 12:00", curva=0)) == Filtro(ONTEM, None, "aceitas")


def test_a_legenda_escolhe_so_o_resultado() -> None:
    assert _clique(Filtro(ONTEM), LEGENDA_RECUSOU, 1) == Filtro(ONTEM, None, "recusadas")
    assert _clique(Filtro(ONTEM, None, "recusadas"), LEGENDA_RECUSOU, 2) == Filtro(ONTEM)


def test_o_clique_numa_hora_escolhe_o_dia_e_a_hora() -> None:
    hora = datetime.combine(ONTEM, datetime.min.time(), tzinfo=FUSO).replace(hour=14)
    clique = _no_dia("14", customdata=hora.isoformat())
    assert _clique(Filtro(), GRAFICO_DE_HORA, clique) == Filtro(ONTEM, 14)
    assert _clique(Filtro(ONTEM, 14), GRAFICO_DE_HORA, clique) == Filtro(ONTEM)
    # O x de data e hora (requisições por hora) vale também.
    assert _clique(Filtro(), GRAFICO_DE_HORA, _no_dia(f"{ONTEM.isoformat()} 14:00")) == Filtro(ONTEM, 14)
    assert Filtro(ONTEM, 14).quando == hora


def test_o_clique_num_motivo_escolhe_o_motivo() -> None:
    clique = {"points": [{"x": 12, "y": "RG não encontrado", "customdata": ["16%", "rg_nao_encontrado"]}]}
    escolha = _clique(Filtro(ONTEM), GRAFICO_DE_MOTIVO, clique)
    assert escolha == Filtro(ONTEM, None, "motivo:rg_nao_encontrado") and escolha.motivo == "rg_nao_encontrado"
    assert _clique(escolha, GRAFICO_DE_MOTIVO, clique) == Filtro(ONTEM)


def test_tirar_o_filtro_desfaz_tudo() -> None:
    assert _clique(Filtro(ONTEM, 14, "recusadas"), LIMPAR, 1) == Filtro()


@pytest.mark.parametrize(
    ("gatilho", "valor"),
    [
        # Gráfico, legenda ou botão que acabou de entrar na tela, sem clique.
        (GRAFICO_DE_DIA, None),
        (LEGENDA_RECUSOU, 0),
        (LIMPAR, 0),
        # Clique fora de um ponto que escolhe algo.
        (GRAFICO_DE_DIA, {"points": [{"x": "Pessoa presa, por RG"}]}),
        (GRAFICO_DE_HORA, _no_dia("14")),
        (GRAFICO_DE_MOTIVO, {"points": [{"x": 12, "customdata": "16%"}]}),
    ],
)
def test_o_que_nao_e_clique_nao_muda_nada(gatilho: dict[str, Any], valor: Any) -> None:
    assert _clique(Filtro(), gatilho, valor) is None


def test_o_callback_guarda_o_filtro_no_armazem() -> None:
    prop_id = json.dumps(GRAFICO_DE_DIA, sort_keys=True, separators=(",", ":")) + ".clickData"

    def rodar() -> list[Any]:
        context_value.set(AttributeDict(triggered_inputs=[{"prop_id": prop_id, "value": _no_dia(ONTEM.isoformat())}]))
        return filtro_de_dia.escolher([], [], [], [None])

    assert copy_context().run(rodar) == [{"dia": ONTEM.isoformat(), "hora": None, "serie": None}]
    assert filtro_de_dia.filtro({"dia": ONTEM.isoformat(), "hora": 14, "serie": "recusadas"}) == Filtro(ONTEM, 14, "recusadas")


def test_o_que_foi_escolhido_fica_em_destaque_no_grafico() -> None:
    dias = [ONTEM - timedelta(days=1), ONTEM, HOJE]
    figura = go.Figure([go.Bar(x=dias, y=[1, 2, 3]), go.Bar(x=dias, y=[3, 2, 1])])
    filtro_de_dia.destacar(figura, Filtro(ONTEM, None, "recusadas"), None, ("aceitas", "recusadas"))
    apagado = filtro_de_dia.APAGADO
    assert list(figura.data[0].marker.opacity) == [apagado, apagado, apagado]
    assert list(figura.data[1].marker.opacity) == [apagado, 1.0, apagado]
    assert len(figura.layout.shapes) == 1
    horas = [datetime.combine(ONTEM, datetime.min.time(), tzinfo=FUSO).replace(hour=h) for h in (13, 14, 15)]
    figura = go.Figure(go.Bar(x=[13, 14, 15], y=[1, 2, 3], customdata=[h.isoformat() for h in horas]))
    filtro_de_dia.destacar_hora(figura, Filtro(ONTEM, 14))
    assert list(figura.data[0].marker.opacity) == [apagado, 1.0, apagado]


# ── As telas no dia escolhido ─────────────────────────────────────────────


@pytest.mark.parametrize("nome", COM_FILTRO_DE_DIA)
def test_toda_tela_tem_um_grafico_de_dia_clicavel(nome: str, layout_da_tela: Callable[[str], Any]) -> None:
    graficos = [c for c in _componentes(layout_da_tela(nome)) if isinstance(_props(c).get("id"), dict) and _props(c)["id"]["tipo"] == filtro_de_dia.GRAFICO]
    assert graficos, f"{nome}: nenhum gráfico de dia para clicar"


@pytest.mark.parametrize("nome", COM_FILTRO_DE_DIA)
def test_a_tela_filtrada_diz_o_dia_e_segue_as_regras(nome: str, cenario: str) -> None:
    tela = _tela_no_dia(nome, ONTEM)
    textos = list(_textos(tela))
    _sem_hifen(textos)
    assert not [t for t in textos if "sem dados" in t.lower()]
    assert any(t.startswith("Filtrado") for t in textos), f"{nome}: a faixa não diz o dia escolhido"
    blocos = [c for c in _componentes(tela) if {"indicador", "quadro"} & _classes(c)]
    for bloco in blocos:
        notas = [c for c in _componentes(bloco) if "fonte-curta" in _classes(c)]
        assert notas, f"{nome}: bloco sem fonte: {_props(bloco).get('className')}"
        if "reservado" not in _classes(bloco):
            assert "lido " in "".join(_textos(notas[0])), f"{nome}: fonte sem hora"


@pytest.mark.parametrize("nome", COM_FILTRO_DE_DIA)
def test_vazio_e_falha_na_tela_filtrada_tem_texto_proprio(nome: str, cenario: str) -> None:
    if cenario == "normal":
        return
    classe = "texto-vazio" if cenario == "vazio" else "texto-aviso"
    indicadores = [c for c in _componentes(_tela_no_dia(nome, ONTEM)) if "indicador" in _classes(c) and "reservado" not in _classes(c)]
    for ind in indicadores:
        avisos = [c for c in _componentes(ind) if classe in _classes(c)]
        assert avisos and "".join(_textos(avisos[0])).strip(), f"{nome}: indicador sem texto de {cenario}"


def test_a_fonte_diz_o_dia_em_vez_da_janela() -> None:
    fonte = FonteSimulada()
    assert "últimas 24 horas" in fonte.tempo_de_resposta(Ambiente.PRODUCAO).fonte.nome
    assert f"em {ONTEM:%d/%m/%Y}" in fonte.tempo_de_resposta(Ambiente.PRODUCAO, ONTEM).fonte.nome


# ── A tela com a hora e a categoria escolhidas ───────────────────────────

ESCOLHAS = [Filtro(ONTEM, 14), Filtro(ONTEM, None, "recusadas"), Filtro(ONTEM, None, "motivo:rg_nao_encontrado"), Filtro(None, None, "recusadas")]
NOMES_DAS_ESCOLHAS = ["hora", "resultado no dia", "motivo no dia", "resultado sem dia"]


def _da_tela(nome: str) -> dict[str, Any]:
    """As funções de uma tela: o Dash carrega as telas sem registrá-las em sys.modules."""
    return next(p for p in dash.page_registry.values() if p["name"] == nome)["layout"].__globals__


def _montagens(escolha: Filtro) -> dict[str, Any]:
    agora, dia, atendimento, sistema, ia, credencial = (
        _da_tela(n) for n in ("Agora", "Relatório do dia", "Atendimento", "Sistema", "Observatório da IA", "Credencial do Verde")
    )
    return {
        "Agora": agora["indicadores"](agora["ler_agora"](escolha.quando), escolha),
        "Agora, o Verde": agora["conteudo_do_verde"](FonteSimulada().verde_por_dia(Ambiente.PRODUCAO), Ambiente.PRODUCAO, None, AGORA, escolha),
        "Relatório do dia": dia["blocos"](dia["ler_dia"](escolha.quando), escolha),
        "Atendimento": atendimento["blocos"](Origem.PRODUCAO_PY, escolha),
        "Sistema": sistema["blocos"](Ambiente.PRODUCAO, escolha.quando),
        "Credencial do Verde": credencial["blocos"](credencial["ler_credencial"](), escolha.dia),
        "Observatório da IA": ia["_corpo"](ia["ler_ia"](Ambiente.PRODUCAO, escolha.quando), None),
        "Agora, de hora em hora": list(agora["_sinais"](None, escolha)),
        "Agora, o caminho do atendimento": agora["caminho_do_atendimento"](agora["ler_agora"](escolha.quando)),
        "Mais sinais, Credencial": lateral.da_credencial(None, escolha),
        "Mais sinais, Atendimento": lateral.do_atendimento(Origem.PRODUCAO_PY, None, escolha),
        "Mais sinais, Sistema": lateral.do_sistema(Ambiente.PRODUCAO, None, escolha),
        "Mais sinais, Relatório do dia": lateral.do_dia(None, escolha),
    }


@pytest.mark.parametrize("ambiente", list(Ambiente))
def test_toda_etapa_do_caminho_tem_um_estado(ambiente: Ambiente, cenario: str) -> None:
    agora = _da_tela("Agora")
    etapas = agora["etapas"](agora["ler_agora"](None, ambiente))
    assert len(etapas) == 11
    estados = {texto for (texto, _), _ in map(agora["_estado_da_etapa"], etapas)}
    assert estados <= {"Funciona", "Com problema", "Não funciona", "Sem uso", "Sem leitura"}


def test_a_leitura_que_falhou_nao_parece_funcionar() -> None:
    agora = _da_tela("Agora")
    dados = agora["ler_agora"](None)
    falhou = FonteSimulada().verde_por_dia(Ambiente.PRODUCAO)
    falhou = type(falhou)(None, Estado.INDISPONIVEL, falhou.fonte, falhou.lido_em, "o CloudWatch não respondeu")
    etapa = next(e for e in agora["etapas"](dados) if e.nome == "O Verde responde")._replace(leituras=[falhou])
    (texto, tom), detalhe = agora["_estado_da_etapa"](etapa)
    assert (texto, tom) == ("Sem leitura", "neutro") and "faltou ler" in detalhe


@pytest.mark.parametrize("escolha", ESCOLHAS, ids=NOMES_DAS_ESCOLHAS)
def test_cada_escolha_segue_as_regras_em_toda_tela(escolha: Filtro, cenario: str) -> None:
    for nome, montado in _montagens(escolha).items():
        textos = list(_textos(montado))
        _sem_hifen(textos)
        assert not [t for t in textos if "sem dados" in t.lower()], nome
        for bloco in (c for c in _componentes(montado) if {"indicador", "quadro"} & _classes(c)):
            notas = [c for c in _componentes(bloco) if "fonte-curta" in _classes(c)]
            assert notas, f"{nome}: bloco sem fonte"
            if "reservado" not in _classes(bloco):
                assert "lido " in "".join(_textos(notas[0])), f"{nome}: fonte sem hora"


def test_os_numeros_seguem_o_que_foi_escolhido() -> None:
    def texto(escolha: Filtro, nome: str) -> str:
        return " ".join(_textos(_montagens(escolha)[nome]))

    assert "Consultas ao Verde: Credencial recusada" in texto(Filtro(ONTEM, None, "recusadas"), "Agora")
    assert "Terminaram: RG não encontrado" in texto(Filtro(ONTEM, None, "motivo:rg_nao_encontrado"), "Atendimento")
    assert "Terminaram: RG não encontrado" in texto(Filtro(ONTEM, None, "motivo:rg_nao_encontrado"), "Relatório do dia")
    assert "das 14h às 15h" in texto(Filtro(ONTEM, 14), "Relatório do dia")
    # O Verde é contado por dia: com a hora escolhida, a frase diz que o número é do dia inteiro.
    assert "No dia inteiro, o Verde" in texto(Filtro(ONTEM, 14), "Relatório do dia")
    assert "das 14h às 15h" in texto(Filtro(ONTEM, 14), "Agora")


def test_a_hora_escolhida_le_so_a_hora() -> None:
    fonte = FonteSimulada()
    hora = datetime.combine(ONTEM, datetime.min.time(), tzinfo=FUSO).replace(hour=14)
    no_dia, na_hora = fonte.resumo_do_dia(Ambiente.PRODUCAO, ONTEM).valor, fonte.resumo_do_dia(Ambiente.PRODUCAO, hora).valor
    assert no_dia is not None and na_hora is not None and na_hora.comecaram < no_dia.comecaram
    assert "das 14h às 15h" in fonte.tempo_de_resposta(Ambiente.PRODUCAO, hora).fonte.nome


def test_toda_tela_tem_uma_faixa_e_um_armazem_do_filtro(layout_da_tela: Callable[[str], Any]) -> None:
    for nome in COM_FILTRO_DE_DIA:
        ids = [_props(c).get("id") for c in _componentes(layout_da_tela(nome))]
        tipos = {i["tipo"] for i in ids if isinstance(i, dict)}
        assert {filtro_de_dia.ARMAZEM, filtro_de_dia.FAIXA, filtro_de_dia.GRAFICO} <= tipos, nome


# ── O cache do dia escolhido ──────────────────────────────────────────────


def test_dia_escolhido_que_ja_passou_fica_guardado_sem_prazo(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    leituras = {"n": 0}

    def resumo_do_dia(ambiente: Ambiente, dia: date | None = None) -> Any:
        leituras["n"] += 1
        return FonteSimulada(agora=lambda: contadora.agora).resumo_do_dia(ambiente, dia)

    contadora.resumo_do_dia = resumo_do_dia  # type: ignore[attr-defined]
    fonte = FonteComCache(contadora, CacheEmDisco(tmp_path), agora=lambda: contadora.agora, por_tras=lambda rodar: rodar())  # type: ignore[arg-type]
    fonte.resumo_do_dia(Ambiente.PRODUCAO, date(2026, 10, 22))
    contadora.agora += timedelta(days=3)
    fonte.resumo_do_dia(Ambiente.PRODUCAO, date(2026, 10, 22))
    assert leituras["n"] == 1
    assert fim_do_dia(date(2026, 10, 22)) < contadora.agora


def test_sem_dia_a_chave_e_a_mesma_de_quem_nao_passou_o_dia(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    leituras = {"n": 0}

    def resumo_do_dia(ambiente: Ambiente, dia: date | None = None) -> Any:
        leituras["n"] += 1
        return FonteSimulada(agora=lambda: contadora.agora).resumo_do_dia(ambiente, dia)

    contadora.resumo_do_dia = resumo_do_dia  # type: ignore[attr-defined]
    fonte = FonteComCache(contadora, CacheEmDisco(tmp_path), agora=lambda: contadora.agora)  # type: ignore[arg-type]
    fonte.resumo_do_dia(Ambiente.PRODUCAO)
    fonte.resumo_do_dia(Ambiente.PRODUCAO, None)
    assert leituras["n"] == 1
