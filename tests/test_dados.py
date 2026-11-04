"""A camada de dados: forma das leituras, só agregados, nada de banco."""

from __future__ import annotations

import dataclasses
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from painel.dados import fontes, modelo
from painel.dados.modelo import Ambiente, Estado, Leitura, Origem
from painel.dados.simulado import FonteSimulada

RAIZ = Path(__file__).parents[1] / "src" / "painel"
POR_AMBIENTE = (
    "saude_servico",
    "implantacoes_em_curso",
    "ultimo_reinicio",
    "resumo_do_dia",
    "credencial",
    "verde_por_dia",
    "tempo_de_resposta",
    "duracao_do_verde",
    "resultado_do_verde",
    "respostas_com_erro",
    "sistema_no_dia",
)
POR_ORIGEM = ("resumo_do_periodo", "nao_encontrado")
SEM_ARGUMENTO = ("rotinas", "renovacoes", "incidentes_de_credencial", "tokens_por_dia")
DIA = date(2026, 10, 25)


def _todas(fonte: FonteSimulada) -> list[Leitura[object]]:
    leituras = [getattr(fonte, c)(a) for c in POR_AMBIENTE for a in Ambiente]
    leituras += [getattr(fonte, c)(o) for c in POR_ORIGEM for o in Origem]
    leituras += [getattr(fonte, c)() for c in SEM_ARGUMENTO]
    leituras += [fonte.gasto_do_dia(DIA), fonte.gasto_do_mes(DIA.replace(day=1))]
    leituras += [fonte.gasto_por_assunto(a, DIA) for a in Ambiente]
    return [*leituras, fonte.orquestrador(Origem.RELEASE)]


@pytest.mark.parametrize("nome_cenario", ["normal", "vazio", "falha"])
def test_toda_leitura_traz_fonte_hora_e_estado(nome_cenario: str) -> None:
    esperado = {"normal": Estado.OK, "vazio": Estado.VAZIO, "falha": Estado.INDISPONIVEL}[nome_cenario]
    for leitura in _todas(FonteSimulada(nome_cenario)):
        assert isinstance(leitura, Leitura)
        assert leitura.estado is esperado
        assert leitura.lido_em.tzinfo is not None
        f = leitura.fonte
        assert f.curto and f.nome and f.identificador and f.atraso
        assert (leitura.valor is None) == (esperado is not Estado.OK)
        assert (leitura.motivo is not None) == (esperado is Estado.INDISPONIVEL)


def test_producao_nao_tem_orquestrador() -> None:
    fonte = FonteSimulada()
    assert fonte.orquestrador(Origem.PRODUCAO_PY).estado is Estado.VAZIO
    assert fonte.orquestrador(Origem.RELEASE).estado is Estado.OK


def test_cada_ambiente_le_o_seu_grupo_de_logs() -> None:
    fonte = FonteSimulada()
    producao = fonte.resumo_do_dia(Ambiente.PRODUCAO).fonte.identificador
    release = fonte.resumo_do_dia(Ambiente.RELEASE).fonte.identificador
    assert producao.startswith("/ecs/maria-langgraph-pp/api,")
    assert release.startswith("/ecs/maria-langgraph-pp-release/api,")


def test_o_grafico_do_verde_tem_oito_dias_terminando_hoje() -> None:
    momento = datetime(2026, 10, 26, 14, 5, tzinfo=modelo.FUSO)
    dias = FonteSimulada(agora=lambda: momento).verde_por_dia(Ambiente.PRODUCAO).valor
    assert dias is not None and len(dias) == fontes.DIAS_DO_GRAFICO_DO_VERDE
    assert dias[-1].dia == momento.date()


def test_o_mesmo_momento_da_o_mesmo_numero() -> None:
    momento = datetime(2026, 10, 26, 14, 5, tzinfo=modelo.FUSO)
    a = FonteSimulada(agora=lambda: momento).verde_por_dia(Ambiente.PRODUCAO).valor
    b = FonteSimulada(agora=lambda: momento).verde_por_dia(Ambiente.PRODUCAO).valor
    assert a == b


def test_nenhum_tipo_carrega_dado_de_conversa() -> None:
    proibidos = re.compile(r"chat|telefone|ip|texto|relato|cpf|rg", re.IGNORECASE)
    for objeto in vars(modelo).values():
        if dataclasses.is_dataclass(objeto) and objeto is not modelo.Fonte:
            campos = [c.name for c in dataclasses.fields(objeto)]
            assert not [c for c in campos if proibidos.fullmatch(c) or "chat" in c.lower()], objeto


def test_nada_le_o_banco_antes_da_309() -> None:
    proibidos = re.compile(r"psycopg|sqlalchemy|asyncpg|DATABASE_URL|PGPASSWORD")
    achados = [str(p) for p in RAIZ.rglob("*.py") if proibidos.search(p.read_text(encoding="utf-8"))]
    assert not achados


def test_cenario_desconhecido_falha_logo() -> None:
    with pytest.raises(ValueError):
        FonteSimulada("otimista")
