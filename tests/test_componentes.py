"""Formatos e a marca do corte de versão."""

from __future__ import annotations

from datetime import datetime, timedelta

import plotly.graph_objects as go

from painel.componentes.formato import data_e_hora, dia_por_extenso, ha_quanto, hora_da_leitura, numero
from painel.componentes.graficos import CORTE_DE_VERSAO, marcar_corte_de_versao
from painel.dados.modelo import FUSO

AGORA = datetime(2026, 10, 26, 15, 0, tzinfo=FUSO)


def test_numero_usa_ponto_de_milhar() -> None:
    assert numero(1831240) == "1.831.240"


def test_hora_da_leitura_diz_o_dia_quando_nao_e_hoje() -> None:
    assert hora_da_leitura(AGORA - timedelta(seconds=30), AGORA) == "lido às 14:59"
    assert hora_da_leitura(AGORA - timedelta(days=1), AGORA) == "lido em 25/10 às 15:00"


def test_data_e_ha_quanto() -> None:
    assert data_e_hora(CORTE_DE_VERSAO) == "23/10 às 12:31"
    assert ha_quanto(CORTE_DE_VERSAO, AGORA) == "há 3 dias"
    assert ha_quanto(AGORA - timedelta(minutes=1), AGORA) == "há 1 minuto"


def test_dia_por_extenso_sem_hifen() -> None:
    assert dia_por_extenso(CORTE_DE_VERSAO) == "Sexta, 23 de outubro"


def test_serie_que_cruza_o_corte_ganha_a_marca() -> None:
    figura = marcar_corte_de_versao(go.Figure(), CORTE_DE_VERSAO - timedelta(days=1), AGORA)
    assert len(figura.layout.shapes) == 1
    assert figura.layout.annotations[0].text == "Versão Python a partir daqui"


def test_o_grafico_do_verde_so_marca_o_corte_na_producao() -> None:
    from painel.componentes.grafico_do_verde import figura_do_verde
    from painel.dados.modelo import Ambiente
    from painel.dados.simulado import FonteSimulada

    fonte = FonteSimulada(agora=lambda: AGORA)
    dias_producao, dias_release = fonte.verde_por_dia(Ambiente.PRODUCAO).valor, fonte.verde_por_dia(Ambiente.RELEASE).valor
    assert dias_producao is not None and dias_release is not None
    producao = figura_do_verde(dias_producao, Ambiente.PRODUCAO, None)
    release = figura_do_verde(dias_release, Ambiente.RELEASE, None)
    assert len(producao.layout.shapes) == 1
    assert not release.layout.shapes


def test_serie_que_nao_cruza_o_corte_fica_sem_marca() -> None:
    figura = marcar_corte_de_versao(go.Figure(), AGORA - timedelta(hours=24), AGORA)
    assert not figura.layout.shapes
