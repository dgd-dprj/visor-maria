"""Regras que montam texto e números a partir dos dados: renovação, linha do
tempo, frase do dia e custo."""

from __future__ import annotations

from datetime import date, datetime

from painel import frase_do_dia, linha_do_tempo
from painel.dados import fontes
from painel.dados.modelo import (
    FUSO,
    Ambiente,
    Credencial,
    DiaDoVerde,
    Estado,
    Fonte,
    IncidenteDeCredencial,
    Leitura,
    Renovacao,
    ResumoDoDia,
    ValidadeConferida,
)
from painel.precos import custo
from painel.renovacao import prever_renovacao


def _h(dia: int, mes: int, hora: int, minuto: int) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, tzinfo=FUSO)


# ── Renovação ─────────────────────────────────────────────────────────────


def test_a_renovacao_de_producao_caiu_no_domingo_e_nao_no_sabado() -> None:
    """O caso real: vence em 01/11, 09:28. Na sexta, 23/10, a previsão é o domingo, 25/10."""
    previsao = prever_renovacao(_h(1, 11, 9, 28), _h(23, 10, 15, 12))
    assert previsao.dias == (date(2026, 10, 25),)
    assert previsao.dias[0].weekday() == 6  # domingo


def test_limiar_dentro_da_faixa_de_atraso_da_dois_dias() -> None:
    previsao = prever_renovacao(_h(30, 11, 13, 0), _h(1, 11, 10, 0))
    assert previsao.dias == (date(2026, 11, 23), date(2026, 11, 24))


def test_limiar_depois_da_faixa_de_atraso_fica_para_o_dia_seguinte() -> None:
    previsao = prever_renovacao(_h(30, 11, 18, 0), _h(1, 11, 10, 0))
    assert previsao.dias == (date(2026, 11, 24),)


def test_vencida_ha_mais_de_cinco_dias_esta_fora_do_prazo() -> None:
    assert prever_renovacao(_h(4, 10, 11, 57), _h(23, 10, 15, 0)).fora_do_prazo


def test_ja_dentro_dos_sete_dias_renova_hoje() -> None:
    assert prever_renovacao(_h(1, 11, 9, 28), _h(27, 10, 8, 0)).dias == (date(2026, 10, 27),)


# ── Linha do tempo ────────────────────────────────────────────────────────


def test_linha_do_tempo_sai_dos_dados_e_em_ordem() -> None:
    agora = _h(26, 10, 12, 0)
    eventos = linha_do_tempo.montar(
        {Ambiente.PRODUCAO: Credencial(_h(25, 10, 12, 26), _h(24, 11, 12, 26), None, None, None)},
        [IncidenteDeCredencial(Ambiente.PRODUCAO, _h(22, 10, 13, 27), _h(23, 10, 12, 34), 283, 75)],
        [Renovacao(Ambiente.PRODUCAO, _h(22, 10, 13, 27), container_novo_no_ar=False)],
        agora,
    )
    assert [e.tipo for e in eventos] == ["recusou", "renovada", "resolvido", "gerada", "a vencer"]
    assert eventos[0].texto == "Produção começa a levar recusa: 283 consultas negadas em 23 horas."
    assert "não subiu" in eventos[1].texto


def test_incidente_aberto_diz_e_contando() -> None:
    agora = _h(23, 10, 15, 0)
    eventos = linha_do_tempo.montar({}, [IncidenteDeCredencial(Ambiente.RELEASE, _h(4, 10, 11, 57), None, 27, None)], [], agora)
    assert eventos[0].texto.endswith("em 19 dias, e contando.")


# ── Frase do dia ──────────────────────────────────────────────────────────


def _ok[T](valor: T, fonte: Fonte) -> Leitura[T]:
    return Leitura(valor, Estado.OK, fonte, _h(26, 10, 12, 0))


def test_frase_do_dia_junta_atendimentos_verde_e_credencial() -> None:
    agora = _h(26, 10, 12, 0)
    resumo = _ok(ResumoDoDia(31, 21, 49, 43, 166, 4), fontes.fonte_resumo_do_dia(Ambiente.PRODUCAO))
    verde = _ok([DiaDoVerde(agora.date(), 43, 0, 6)], fontes.fonte_verde_por_dia(Ambiente.PRODUCAO))
    credenciais = {
        Ambiente.PRODUCAO: _ok(Credencial(None, _h(24, 11, 12, 26), None, None, None), fontes.fonte_credencial(Ambiente.PRODUCAO)),
        Ambiente.RELEASE: _ok(Credencial(None, _h(4, 10, 11, 57), None, None, None), fontes.fonte_credencial(Ambiente.RELEASE)),
    }
    frase = frase_do_dia.montar(resumo, verde, credenciais, agora)
    assert frase == (
        "Em produção, 31 pessoas começaram um atendimento hoje, e 21 terminaram. "
        "A troca de versão cortou 4 conversas no meio. "
        "O Verde aceitou a credencial em todas as 49 consultas. "
        "O release segue sem credencial, há 22 dias."
    )


def test_frase_do_dia_diz_o_que_nao_deu_para_ler() -> None:
    agora = _h(26, 10, 12, 0)
    falhou: Leitura[ResumoDoDia] = Leitura(None, Estado.INDISPONIVEL, fontes.fonte_resumo_do_dia(Ambiente.PRODUCAO), agora, "sem resposta")
    verde: Leitura[list[DiaDoVerde]] = Leitura(None, Estado.INDISPONIVEL, fontes.fonte_verde_por_dia(Ambiente.PRODUCAO), agora, "sem resposta")
    frase = frase_do_dia.montar(falhou, verde, {}, agora)
    assert frase == "Não deu para ler os atendimentos e o Verde."


# ── Custo ─────────────────────────────────────────────────────────────────


def test_o_custo_dos_30_dias_bate_com_o_levantamento() -> None:
    """1.831.240 de entrada a US$ 1,10 e 67.004 de saída a US$ 5,50: cerca de US$ 2,38."""
    assert round(custo(fontes.MODELO_DE_CHAT, 1_831_240, 67_004), 2) == 2.38


def test_um_dia_sem_tokens_nao_custa_nada() -> None:
    assert custo(fontes.MODELO_DE_CHAT, 0, 0) == 0


def test_o_vencimento_de_cada_evento_sai_da_conferencia() -> None:
    agora = _h(26, 10, 18, 0)
    conferidas = (
        ValidadeConferida(_h(24, 10, 12, 13), _h(1, 11, 9, 28)),
        # A conferência que renovou termina depois da renovação, com a validade antiga.
        ValidadeConferida(_h(25, 10, 12, 28), _h(1, 11, 9, 28)),
        ValidadeConferida(_h(26, 10, 15, 4), _h(25, 11, 12, 24)),
    )
    credencial = Credencial(_h(25, 10, 12, 27), _h(25, 11, 12, 24), None, None, None, conferidas)
    eventos = linha_do_tempo.montar(
        {Ambiente.PRODUCAO: credencial},
        [IncidenteDeCredencial(Ambiente.PRODUCAO, _h(24, 10, 20, 0), _h(24, 10, 21, 0), 12, 4)],
        [Renovacao(Ambiente.PRODUCAO, _h(25, 10, 12, 27), container_novo_no_ar=True)],
        agora,
    )
    por_tipo = {e.tipo: e.vencimento for e in eventos}
    # A conferência de 25/10 leu a validade antes de renovar: a nova sai na de 26/10.
    assert por_tipo["renovada"] == _h(25, 11, 12, 24)
    assert por_tipo["gerada"] == por_tipo["a vencer"] == _h(25, 11, 12, 24)
    assert por_tipo["recusou"] is None and por_tipo["resolvido"] is None


def test_a_causa_do_incidente_cruza_renovacao_e_validade() -> None:
    conferidas = (ValidadeConferida(_h(20, 10, 13, 11), _h(1, 11, 9, 28)), ValidadeConferida(_h(2, 11, 14, 0), _h(1, 11, 9, 28)))
    credenciais = {Ambiente.PRODUCAO: Credencial(None, _h(1, 11, 9, 28), None, None, None, conferidas)}
    renovacoes = [Renovacao(Ambiente.PRODUCAO, _h(22, 10, 13, 27), container_novo_no_ar=False)]

    def causa(ambiente: Ambiente, inicio: datetime) -> str:
        return linha_do_tempo.causa(IncidenteDeCredencial(ambiente, inicio, None, 30, None), credenciais, renovacoes)

    assert causa(Ambiente.PRODUCAO, _h(22, 10, 13, 28)) == "container"
    assert causa(Ambiente.PRODUCAO, _h(20, 10, 16, 29)) == "no prazo"
    assert causa(Ambiente.PRODUCAO, _h(2, 11, 15, 0)) == "vencida"
    assert causa(Ambiente.RELEASE, _h(22, 10, 14, 8)) == "sem validade"
