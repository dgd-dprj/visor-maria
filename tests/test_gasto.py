"""O filtro de dia e as contas da tela financeira."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from typing import Any

from painel import gasto, periodo
from painel.dados.modelo import FUSO, Assunto, GastoDeIA, GastoDoAssunto
from painel.periodo import Escolha
from painel.precos import Parcela, custo_do_assunto, parcelas, total
from tests.test_regras_de_texto import _componentes, _props, _textos

AGORA = datetime(2026, 10, 26, 15, 40, tzinfo=FUSO)

# ── Período ───────────────────────────────────────────────────────────────


def test_hoje_vai_de_0h_ate_agora() -> None:
    p = periodo.montar("hoje", None, AGORA)
    assert (p.primeiro_dia, p.ultimo_dia) == (date(2026, 10, 26), date(2026, 10, 26))
    assert periodo.descrever(p) == "26/10, de 0h às 15:40"


def test_sete_e_trinta_dias_terminam_hoje() -> None:
    sete = periodo.montar("7dias", None, AGORA)
    assert sete.primeiro_dia == date(2026, 10, 20) and len(sete.dias) == 7
    assert periodo.descrever(sete) == "20/10 a 26/10, hoje até 15:40"
    assert len(periodo.montar("30dias", None, AGORA).dias) == 30


def test_data_especifica_e_um_dia_inteiro() -> None:
    p = periodo.montar("data", "2026-10-25", AGORA)
    assert p.escolha is Escolha.DATA and p.dias == [date(2026, 10, 25)]
    assert periodo.descrever(p) == "25/10, dia inteiro"
    assert periodo.descrever(periodo.montar("data", "2025-12-01", AGORA)) == "01/12/2025, dia inteiro"


def test_data_invalida_futura_ou_longe_demais_vira_hoje() -> None:
    for texto in (None, "", "ontem", "2026-10-27", "2024-01-01"):
        assert periodo.montar("data", texto, AGORA).ultimo_dia == date(2026, 10, 26), texto
    assert periodo.montar("semana", None, AGORA).escolha is Escolha.HOJE


def test_a_lista_de_datas_cobre_um_ano_sem_hifen() -> None:
    opcoes = periodo.opcoes_de_data(AGORA)
    assert opcoes[0] == {"label": "26/10/2026, segunda", "value": "2026-10-26"}
    assert len(opcoes) == periodo.DIAS_PARA_TRAS + 1
    assert not [o for o in opcoes if "-" in o["label"]]


# ── Trechos e variação ────────────────────────────────────────────────────


def test_trechos_de_comparacao() -> None:
    t = gasto.trechos(date(2026, 10, 26))
    assert t.dia_anterior.primeiro == date(2026, 10, 25)
    assert (t.semana.primeiro, t.semana_anterior.primeiro, t.semana_anterior.ultimo) == (date(2026, 10, 20), date(2026, 10, 13), date(2026, 10, 19))
    assert (t.mes.primeiro, t.mes_anterior.primeiro, t.mes_anterior.ultimo) == (date(2026, 10, 1), date(2026, 9, 1), date(2026, 9, 26))


def test_mes_anterior_mais_curto_para_no_ultimo_dia() -> None:
    t = gasto.trechos(date(2026, 3, 31))
    assert (t.mes_anterior.primeiro, t.mes_anterior.ultimo) == (date(2026, 2, 1), date(2026, 2, 28))
    assert gasto.trechos(date(2026, 1, 15)).mes_anterior.primeiro == date(2025, 12, 1)


def test_variacao_em_palavras_sem_sinal() -> None:
    assert gasto.variacao(1.12, 1.0, "no dia 25/10") == "12% a mais que no dia 25/10"
    assert gasto.variacao(0.5, 1.0, "no dia 25/10") == "50% a menos que no dia 25/10"
    assert gasto.variacao(1.001, 1.0, "no dia 25/10") == "igual ao gasto no dia 25/10"
    assert gasto.variacao(1.0, 0.0, "no dia 25/10") == "nenhum gasto no dia 25/10"
    assert gasto.variacao(0.0, 0.0, "no dia 25/10") == "também nenhum gasto no dia 25/10"


# ── Preço ─────────────────────────────────────────────────────────────────


def test_parcelas_somam_o_total() -> None:
    g = GastoDeIA(date(2026, 10, 25), 1_000_000, 100_000, 1_000_000)
    p = parcelas(g)
    assert round(p[Parcela.LIDO], 4) == 1.10 and round(p[Parcela.ESCRITO], 4) == 0.55 and round(p[Parcela.BUSCA], 4) == 0.02
    assert total(g) == sum(p.values())


def test_triagem_so_com_total_nao_ganha_preco() -> None:
    """Sem saber quanto foi lido e quanto foi escrito, não há preço (#340 na Maria)."""
    assert custo_do_assunto(GastoDoAssunto(Assunto.TRIAGEM, 4, 0, 0, so_total=4_000)) == 0


def test_somar_dias() -> None:
    dias = [GastoDeIA(date(2026, 10, d), 10, 2, 5) for d in (24, 25, 26)]
    assert gasto.somar(date(2026, 10, 24), dias) == GastoDeIA(date(2026, 10, 24), 30, 6, 15)


# ── A tela ────────────────────────────────────────────────────────────────


def _texto(layout: Any) -> str:
    return " ".join(_textos(layout))


def test_a_faixa_de_simulado_esta_na_moldura() -> None:
    import painel.app

    assert "Dados simulados:" in _texto(painel.app.app.layout)


def test_tela_financeira_sem_nome_tecnico_nos_rotulos(layout_da_tela: Callable[[str], Any]) -> None:
    """Para quem lê de finanças: os nomes técnicos só aparecem em "De onde vem cada número"."""
    layout = layout_da_tela("Relatório da Aplicação")
    textos = list(_textos(layout))
    # A lista do pé fica de fora: ela é o lugar dos nomes técnicos.
    lista = next(c for c in _componentes(layout) if "lista-de-fontes" in str(_props(c).get("className") or ""))
    for t in _textos(lista):
        textos.remove(t)
    textos_lidos = " ".join(textos)
    for tecnico in ("token de entrada", "tokens de entrada", "Bedrock", "embedding", "Haiku", "orquestrador", "Logs Insights", "CloudWatch"):
        assert tecnico not in textos_lidos, tecnico


def test_tela_financeira_mostra_o_que_falta_e_os_avisos(layout_da_tela: Callable[[str], Any]) -> None:
    texto = _texto(layout_da_tela("Relatório da Aplicação"))
    for esperado in ("Servidores e rede", "Espera a fatura", "#230", "#340", "O que ainda não dá para medir", "Gasto de hoje, até"):
        assert esperado in texto, esperado


def test_o_mes_da_data_escolhida_vai_so_ate_ela() -> None:
    """Numa data passada do mês corrente, a barra do mês bate com "Gasto em outubro, até 25/10"."""
    from painel.dados.modelo import Ambiente
    from painel.dados.telas import ler_aplicacao

    agora = datetime.now(FUSO)
    ontem = agora.date().replace(day=max(agora.day - 1, 1))
    dados = ler_aplicacao(periodo.montar("data", ontem.isoformat(), agora), Ambiente.PRODUCAO)
    meses = dados.doze_meses().valor
    ate_a_data = dados.gasto(ontem.replace(day=1), ontem).valor
    assert meses is not None and ate_a_data is not None
    assert len(meses) == 12 and meses[-1] == ate_a_data


def test_dinheiro_com_mais_casas_para_o_valor_por_atendimento() -> None:
    from painel.componentes.formato import dinheiro

    assert dinheiro(0.00071, casas=4) == "US$ 0,0007"
    assert dinheiro(0.00001, casas=4) == "menos de US$ 0,0001"
    assert dinheiro(0.004) == "menos de US$ 0,01"


def test_mes_inteiro_ou_ate_hoje() -> None:
    setembro = periodo.montar("mes", None, AGORA, "2026-09")
    assert (setembro.primeiro_dia, setembro.ultimo_dia) == (date(2026, 9, 1), date(2026, 9, 30))
    assert periodo.descrever(setembro) == "setembro de 2026, mês inteiro"
    outubro = periodo.montar("mes", None, AGORA, "2026-10")
    assert outubro.ultimo_dia == date(2026, 10, 26)
    assert periodo.descrever(outubro) == "outubro de 2026, hoje até 15:40"
    assert periodo.opcoes_de_mes(AGORA)[0] == {"label": "outubro de 2026", "value": "2026-10"}
    assert len(periodo.opcoes_de_mes(AGORA)) == 12


def test_clique_no_grafico_muda_o_filtro() -> None:
    import dash
    import pytest
    from dash._callback_context import context_value
    from dash._utils import AttributeDict

    pagina = next(p for p in dash.page_registry.values() if p["name"] == "Relatório da Aplicação")
    modulo = __import__(pagina["module"], fromlist=["escolher_no_grafico"])

    def clicar(id_: str, clique: Any) -> Any:
        context_value.set(AttributeDict(triggered_inputs=[{"prop_id": f"{id_}.clickData", "value": clique}]))
        escritos = modulo.lateral.ID_DOS_ESCRITOS
        return modulo.escolher_no_grafico(
            clique if id_ == modulo.ID_DOS_DIAS else None, clique if id_ == modulo.ID_DOS_MESES else None, clique if id_ == escritos else None
        )

    dia = {"points": [{"x": "2026-10-22 12:00", "customdata": "texto"}]}
    assert clicar(modulo.ID_DOS_DIAS, dia)[:2] == ("data", "2026-10-22")
    # O texto escrito por chamada, na coluna da direita, também escolhe a data.
    assert clicar(modulo.lateral.ID_DOS_ESCRITOS, {"points": [{"x": "2026-10-20"}]})[:2] == ("data", "2026-10-20")
    mes = {"points": [{"x": "2026-09", "customdata": "texto"}]}
    resposta = clicar(modulo.ID_DOS_MESES, mes)
    assert resposta[0] == "mes" and resposta[2] == "2026-09"
    with pytest.raises(dash.exceptions.PreventUpdate):
        clicar(modulo.ID_DOS_DIAS, None)


def test_titulo_de_commit_sem_hifen_nem_emoji() -> None:
    from painel.componentes.formato import sem_hifen

    assert sem_hifen(":bug: fix: Perfil AWS inexistente — não impede a API") == "fix: Perfil AWS inexistente, não impede a API"
    assert sem_hifen("refactor: pessoa-presa e cross-check") == "refactor: pessoa presa e cross check"


def test_toda_tela_tem_a_coluna_da_direita(layout_da_tela: Callable[[str], Any]) -> None:
    from painel.componentes.menu import TELAS

    for nome, _, _ in TELAS:
        layout = layout_da_tela(nome)
        if nome == "Agora":
            # A Agora usa a largura toda (28/10): os gráficos de hora em hora pedem espaço.
            assert "tela-larga" in str(_props(layout).get("className") or ""), nome
            continue
        colunas = [c for c in _componentes(layout) if "tela-lateral" in str(_props(c).get("className") or "")]
        assert colunas, nome
        assert "Mais sinais" in " ".join(_textos(colunas[0])), nome


# ── O período escolhido muda os números ───────────────────────────────────


def test_o_periodo_se_compara_com_o_anterior_do_mesmo_tamanho() -> None:
    sete = gasto.anterior_ao_periodo(date(2026, 10, 23), date(2026, 10, 29), mes=False)
    assert (sete.primeiro, sete.ultimo) == (date(2026, 10, 16), date(2026, 10, 22))
    trinta = gasto.anterior_ao_periodo(date(2026, 9, 30), date(2026, 10, 29), mes=False)
    assert len(trinta.dias) == 30 and trinta.ultimo == date(2026, 9, 29)
    # O mês em curso: o mesmo trecho do anterior. O mês fechado: o anterior inteiro.
    em_curso = gasto.anterior_ao_periodo(date(2026, 10, 1), date(2026, 10, 29), mes=True)
    assert (em_curso.primeiro, em_curso.ultimo) == (date(2026, 9, 1), date(2026, 9, 29))
    fechado = gasto.anterior_ao_periodo(date(2026, 9, 1), date(2026, 9, 30), mes=True)
    assert (fechado.primeiro, fechado.ultimo) == (date(2026, 8, 1), date(2026, 8, 31))


def test_cada_periodo_mostra_numeros_proprios() -> None:
    """O defeito de 29/10: em 7 dias, 30 dias e mês, os três números saíam iguais aos de hoje."""
    import dash

    pagina = next(p for p in dash.page_registry.values() if p["name"] == "Relatório da Aplicação")
    tela = pagina["layout"].__globals__

    def indicadores(escolha: str) -> str:
        dados = tela["_ler"](escolha, None, None, None)
        return " ".join(_textos(tela["_indicadores"](dados)))

    textos = {e: indicadores(e) for e in ("hoje", "7dias", "30dias", "mes")}
    assert len(set(textos.values())) == 4, "dois períodos mostram os mesmos números"
    assert "Gasto de hoje" in textos["hoje"]
    for escolha in ("7dias", "30dias", "mes"):
        assert "Média por dia no período" in textos[escolha] and "Dia mais caro do período" in textos[escolha]
    assert "Gasto em 7 dias" in textos["7dias"] and "nos 7 dias antes" in textos["7dias"]
    assert "Gasto em 30 dias" in textos["30dias"] and "nos 30 dias antes" in textos["30dias"]


# ── Quanto do gasto é da Maria ────────────────────────────────────────────


def test_o_gasto_se_divide_entre_a_maria_e_o_que_veio_de_fora() -> None:
    from painel.dados.modelo import TokensRegistrados

    dia = date(2026, 10, 27)
    # O caso real de 27/10: a conta mediu 5,9 milhões de tokens lidos; a Maria registrou 101 mil.
    medido = GastoDeIA(dia, 5_949_632, 147_960, 109_232)
    dividido = gasto.dividir(medido, [TokensRegistrados(dia, 99_315, 3_605, 0), TokensRegistrados(dia, 0, 0, 1_837)])
    assert dividido.fora > 50 * dividido.maria
    assert round(dividido.maria + dividido.fora + dividido.busca, 6) == round(total(medido), 6)
    # Um dia comum (16/10): tudo o que a conta mediu veio das conversas da Maria.
    comum = gasto.dividir(GastoDeIA(dia, 68_425, 2_491, 0), [TokensRegistrados(dia, 68_425, 2_491, 0)])
    assert comum.fora == 0 and comum.maria > 0
    # A contagem da Maria que passa do medido (issue #230) não faz a parte dela passar do total.
    a_mais = gasto.dividir(GastoDeIA(dia, 100, 10, 0), [TokensRegistrados(dia, 0, 0, 1_000)])
    assert a_mais.fora == 0 and round(a_mais.maria, 9) == round(total(GastoDeIA(dia, 100, 10, 0)), 9)
