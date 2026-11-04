"""O cache é requisito: toda consulta declara janela e validade, janela fechada
fica guardada sem prazo, e a falha nunca é guardada."""

from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from painel.dados.cache import VENCIDA_AINDA_SERVE, CacheEmDisco, FonteComCache
from painel.dados.consultas import CONSULTAS, fim_do_dia, fim_do_mes
from painel.dados.fontes import FonteDeDados
from painel.dados.modelo import FUSO, Estado, Leitura
from painel.dados.simulado import FonteSimulada


def _consultas_do_contrato() -> set[str]:
    return {nome for nome in vars(FonteDeDados) if not nome.startswith("_") and nome != "nome"}


def test_toda_consulta_do_contrato_declara_janela_e_validade() -> None:
    faltando = _consultas_do_contrato() - set(CONSULTAS)
    assert not faltando, f"consultas sem janela e validade em dados/consultas.py: {sorted(faltando)}"
    sobrando = set(CONSULTAS) - _consultas_do_contrato()
    assert not sobrando, f"declaradas mas fora do FonteDeDados: {sorted(sobrando)}"
    for nome, consulta in CONSULTAS.items():
        assert consulta.janela.strip() and consulta.validade > timedelta(0), nome


def test_o_cache_recusa_consulta_nao_declarada(tmp_path: Path) -> None:
    fonte = FonteComCache(FonteSimulada(), CacheEmDisco(tmp_path))
    with pytest.raises(AttributeError, match="janela e validade"):
        fonte.consulta_inventada  # noqa: B018


class Contadora:
    """Uma fonte que conta quantas vezes foi consultada, com a hora que quisermos."""

    nome = "contadora"

    def __init__(self, agora: datetime, estado: Estado = Estado.OK) -> None:
        self.agora = agora
        self.estado = estado
        self.chamadas = 0

    def gasto_do_dia(self, dia: date) -> Leitura[Any]:
        self.chamadas += 1
        fonte = FonteSimulada().gasto_do_dia(dia).fonte
        valor = None if self.estado is Estado.INDISPONIVEL else self.chamadas
        return Leitura(valor, self.estado, fonte, self.agora, "falhou" if self.estado is Estado.INDISPONIVEL else None)


def _com_cache(contadora: Contadora, pasta: Path) -> Any:
    # A leitura "por trás" roda na hora, para o teste ver a contagem.
    return FonteComCache(contadora, CacheEmDisco(pasta), agora=lambda: contadora.agora, por_tras=lambda rodar: rodar())  # type: ignore[arg-type]


def test_dia_fechado_e_lido_uma_vez_so(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    fonte = _com_cache(contadora, tmp_path)
    ontem = date(2026, 10, 25)
    primeira = fonte.gasto_do_dia(ontem)
    contadora.agora += timedelta(days=40)
    segunda = fonte.gasto_do_dia(ontem)
    assert contadora.chamadas == 1
    # "lido às" continua sendo a hora em que o dado saiu da fonte.
    assert segunda.lido_em == primeira.lido_em


def test_dia_em_curso_vence_na_validade(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    fonte = _com_cache(contadora, tmp_path)
    hoje = date(2026, 10, 26)
    fonte.gasto_do_dia(hoje)
    contadora.agora += timedelta(seconds=30)
    fonte.gasto_do_dia(hoje)
    assert contadora.chamadas == 1
    contadora.agora += CONSULTAS["gasto_do_dia"].validade
    # Vencida há pouco: a tela recebe a leitura guardada, e a nova é lida por trás.
    assert fonte.gasto_do_dia(hoje).valor == 1
    assert contadora.chamadas == 2
    assert fonte.gasto_do_dia(hoje).valor == 2


def test_vencida_ha_muito_tempo_a_tela_espera_a_nova(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    fonte = _com_cache(contadora, tmp_path)
    hoje = date(2026, 10, 26)
    fonte.gasto_do_dia(hoje)
    contadora.agora += CONSULTAS["gasto_do_dia"].validade + VENCIDA_AINDA_SERVE
    assert fonte.gasto_do_dia(hoje).valor == 2


def test_a_mesma_consulta_ao_mesmo_tempo_e_lida_uma_vez(tmp_path: Path) -> None:
    """Duas telas pedem a mesma leitura juntas: a segunda espera a primeira."""
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    comecou, solta = threading.Event(), threading.Event()
    lenta = contadora.gasto_do_dia

    def gasto_do_dia(dia: date) -> Leitura[Any]:
        comecou.set()
        solta.wait(5)
        return lenta(dia)

    contadora.gasto_do_dia = gasto_do_dia  # type: ignore[method-assign]
    fonte = _com_cache(contadora, tmp_path)
    with ThreadPoolExecutor(max_workers=2) as grupo:
        primeira = grupo.submit(fonte.gasto_do_dia, date(2026, 10, 25))
        comecou.wait(5)
        segunda = grupo.submit(fonte.gasto_do_dia, date(2026, 10, 25))
        solta.set()
        assert primeira.result(5).valor == segunda.result(5).valor == 1
    assert contadora.chamadas == 1


def test_leitura_feita_antes_de_a_janela_fechar_ainda_vence(tmp_path: Path) -> None:
    """Lida às 23:59, a leitura de hoje vale a validade, e não para sempre."""
    contadora = Contadora(datetime(2026, 10, 26, 23, 59, tzinfo=FUSO))
    fonte = _com_cache(contadora, tmp_path)
    fonte.gasto_do_dia(date(2026, 10, 26))
    contadora.agora = fim_do_dia(date(2026, 10, 26)) + timedelta(minutes=1)
    fonte.gasto_do_dia(date(2026, 10, 26))
    fonte.gasto_do_dia(date(2026, 10, 26))
    assert contadora.chamadas == 2


def test_falha_nao_e_guardada(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO), Estado.INDISPONIVEL)
    fonte = _com_cache(contadora, tmp_path)
    fonte.gasto_do_dia(date(2026, 10, 25))
    fonte.gasto_do_dia(date(2026, 10, 25))
    assert contadora.chamadas == 2


def test_dois_processos_dividem_o_mesmo_cache(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    _com_cache(contadora, tmp_path).gasto_do_dia(date(2026, 10, 25))
    _com_cache(contadora, tmp_path).gasto_do_dia(date(2026, 10, 25))
    assert contadora.chamadas == 1


def test_fontes_diferentes_nao_dividem_leitura(tmp_path: Path) -> None:
    cache = CacheEmDisco(tmp_path)
    normal = FonteComCache(FonteSimulada("normal"), cache).gasto_do_dia(date(2026, 10, 25))
    vazio = FonteComCache(FonteSimulada("vazio"), cache).gasto_do_dia(date(2026, 10, 25))
    assert normal.estado is Estado.OK and vazio.estado is Estado.VAZIO


def test_arquivo_estragado_conta_como_ausente(tmp_path: Path) -> None:
    contadora = Contadora(datetime(2026, 10, 26, 15, 0, tzinfo=FUSO))
    _com_cache(contadora, tmp_path).gasto_do_dia(date(2026, 10, 25))
    for arquivo in tmp_path.iterdir():
        arquivo.write_bytes(b"pela metade")
    _com_cache(contadora, tmp_path).gasto_do_dia(date(2026, 10, 25))
    assert contadora.chamadas == 2


def test_fim_do_mes_vira_o_ano() -> None:
    assert fim_do_mes(date(2026, 12, 1)) == datetime(2027, 1, 1, 1, 0, tzinfo=FUSO)
    assert fim_do_mes(date(2026, 2, 1)) == datetime(2026, 3, 1, 1, 0, tzinfo=FUSO)
