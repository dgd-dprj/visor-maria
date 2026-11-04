"""O quadro "Exige atenção" e os incidentes abertos."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from painel.atencao import incidentes_abertos, itens_de_atencao
from painel.dados import fontes
from painel.dados.modelo import FUSO, Ambiente, Credencial, DiaDoVerde, Estado, Fonte, Leitura, Rotina

AGORA = datetime(2026, 10, 23, 15, 12, tzinfo=FUSO)


def _ok[T](valor: T, fonte: Fonte) -> Leitura[T]:
    return Leitura(valor, Estado.OK, fonte, AGORA)


def _credenciais(producao: datetime, release: datetime) -> dict[Ambiente, Leitura[Credencial]]:
    return {
        Ambiente.PRODUCAO: _ok(Credencial(None, producao, AGORA, None, None), fontes.fonte_credencial(Ambiente.PRODUCAO)),
        Ambiente.RELEASE: _ok(Credencial(None, release, None, None, None), fontes.fonte_credencial(Ambiente.RELEASE)),
    }


def _verde_do_release(recusadas_por_dia: int) -> dict[Ambiente, Leitura[list[DiaDoVerde]]]:
    dias = [DiaDoVerde(AGORA.date() - timedelta(days=n), 0, recusadas_por_dia, 0) for n in range(7, -1, -1)]
    return {Ambiente.RELEASE: _ok(dias, fontes.fonte_verde_por_dia(Ambiente.RELEASE))}


def _rotinas(falhando_desde: datetime | None) -> Leitura[list[Rotina]]:
    rotina = Rotina("Conferência diária da credencial", date(2026, 9, 19), 1, 30, falhando_desde)
    return _ok([rotina], fontes.fonte_rotinas())


def test_credencial_vencida_e_incidente_e_item_parado() -> None:
    credenciais = _credenciais(datetime(2026, 11, 1, 9, 28, tzinfo=FUSO), datetime(2026, 10, 4, 11, 57, tzinfo=FUSO))
    itens = itens_de_atencao(credenciais, _verde_do_release(4), _rotinas(None), AGORA)

    parados = [i for i in itens if i.nivel == "parado"]
    assert parados[0].titulo == "O release está sem acesso ao Verde há 19 dias"
    assert parados[0].descricao == "A credencial venceu em 04/10. As 28 consultas da semana foram todas recusadas."
    assert [i.ambiente for i in incidentes_abertos(credenciais, AGORA)] == [Ambiente.RELEASE]


def test_credencial_que_vence_em_ate_dez_dias_pede_atencao() -> None:
    credenciais = _credenciais(datetime(2026, 11, 1, 9, 28, tzinfo=FUSO), datetime(2026, 12, 1, tzinfo=FUSO))
    itens = itens_de_atencao(credenciais, {}, _rotinas(None), AGORA)
    assert [(i.nivel, i.titulo) for i in itens] == [("atencao", "A credencial de produção vence em 9 dias")]


def test_rotina_falhando_e_item_parado_e_vem_antes_da_atencao() -> None:
    credenciais = _credenciais(datetime(2026, 11, 1, 9, 28, tzinfo=FUSO), datetime(2026, 12, 1, tzinfo=FUSO))
    itens = itens_de_atencao(credenciais, {}, _rotinas(datetime(2026, 9, 23, 6, tzinfo=FUSO)), AGORA)
    assert [i.nivel for i in itens] == ["parado", "atencao"]
    assert itens[0].titulo == "Conferência diária da credencial falhando há 30 dias"
    assert itens[0].descricao == "1 com sucesso e 30 com falha desde 19/09."


def test_sem_nada_vencendo_nada_pede_atencao() -> None:
    longe = datetime(2027, 1, 1, tzinfo=FUSO)
    assert itens_de_atencao(_credenciais(longe, longe), {}, _rotinas(None), AGORA) == []
    assert incidentes_abertos(_credenciais(longe, longe), AGORA) == []


def test_leitura_que_falhou_nao_vira_item() -> None:
    falhou: Leitura[Credencial] = Leitura(None, Estado.INDISPONIVEL, fontes.fonte_credencial(Ambiente.RELEASE), AGORA, "sem resposta")
    assert itens_de_atencao({Ambiente.RELEASE: falhou}, {}, _rotinas(None), AGORA) == []
