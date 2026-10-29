"""As contas novas das telas: o dia contra a semana (Relatório do dia), o tempo
de resposta dia a dia (Sistema) e os problemas do dia com o que aconteceu com a
conversa."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from painel import lateral
from painel.componentes.filtro_de_dia import Filtro
from painel.dados.modelo import FUSO, Ambiente, CpuELatencia, Destino, EncaminhamentoNoDia, Estado, Fonte, Leitura, ProblemaNoDia, TempoDeResposta
from tests.test_filtro_de_dia import _da_tela
from tests.test_regras_de_texto import _textos

DIA = date(2026, 10, 28)
FONTE = Fonte("logs de produção", "teste", "teste", "na hora")
LIDO = datetime(2026, 10, 28, 15, tzinfo=FUSO)


def _encerrados(dia: date, maria: int, humano: int, falha: int = 0) -> list[EncaminhamentoNoDia]:
    linhas = [
        EncaminhamentoNoDia(dia, "f", Destino.IA, "", maria),
        EncaminhamentoNoDia(dia, "f", Destino.HUMANO, "rg_nao_encontrado", humano - falha),
    ]
    if falha:
        linhas.append(EncaminhamentoNoDia(dia, "f", Destino.HUMANO, "falha_infra_verde", falha))
    return linhas


def test_o_dia_contra_a_semana_diz_para_que_lado_mudou() -> None:
    # Na semana, metade resolvida pela Maria; no dia, um quarto, com duas falhas técnicas.
    semana = [e for n in range(1, 8) for e in _encerrados(DIA - timedelta(days=n), 10, 10)]
    textos = " ".join(_textos(lateral._contra_a_semana([*semana, *_encerrados(DIA, 5, 15, falha=2)], DIA, DIA + timedelta(days=1))))
    assert "25%" in textos and "50%" in textos
    assert "25 pontos a menos" in textos and "25 pontos a mais" in textos
    assert "A média é a dos 7 dias antes" in textos


def test_hoje_avisa_que_as_contagens_vao_crescer() -> None:
    textos = " ".join(_textos(lateral._contra_a_semana(_encerrados(DIA, 1, 1), DIA, DIA)))
    assert "ainda está em curso" in textos and "dia em curso" in textos


def test_os_dias_juntos_guardam_o_dia_e_deixam_o_vazio_de_fora() -> None:
    tempo = TempoDeResposta(10, 1.0, 4.0, 9.0)
    leituras = {
        DIA - timedelta(days=1): Leitura(tempo, Estado.OK, FONTE, LIDO),
        DIA: Leitura(None, Estado.VAZIO, FONTE, LIDO),
    }
    junta = lateral._dia_a_dia(leituras)
    assert junta.estado is Estado.OK and junta.valor == [(DIA - timedelta(days=1), tempo)]
    leituras[DIA] = Leitura(None, Estado.INDISPONIVEL, FONTE, LIDO, "o CloudWatch não respondeu")
    assert lateral._dia_a_dia(leituras).estado is Estado.INDISPONIVEL


def test_cada_problema_do_dia_diz_o_que_aconteceu_com_a_conversa() -> None:
    problemas = [
        ProblemaNoDia(DIA, "falha_infra_verde", "f", 2),
        ProblemaNoDia(DIA, "whatsapp_status_entrega", "", 1),
        ProblemaNoDia(DIA - timedelta(days=1), "atendimento_expirado", "f", 9),
    ]
    encerrados = [EncaminhamentoNoDia(DIA, "f", Destino.HUMANO, "falha_cadastro", 3)]
    textos = " ".join(_textos(lateral._problemas_do_dia(problemas, encerrados, DIA)))
    assert "A conversa foi para atendimento humano." in textos and "A resposta não chegou à pessoa." in textos
    assert "Falha ao cadastrar" in textos and "expirou" not in textos


def _horas(p99s: list[float | None], cpu: float = 0.5) -> list[CpuELatencia]:
    inicio = datetime(2026, 10, 29, 0, tzinfo=FUSO)
    return [CpuELatencia(inicio + timedelta(hours=n), a, cpu, p) for a in Ambiente for n, p in enumerate(p99s)]


def test_o_resumo_conta_as_horas_acima_do_limite_do_alerta() -> None:
    sistema = _da_tela("Sistema")
    linhas = _horas([0.4, 29.1, 9.9, None])
    assert sistema["_resumo_do_p99"](linhas, Ambiente.PRODUCAO) == "Produção: acima de 3 s em 2 horas; o pior às 01h, 29,1 s."
    assert sistema["_resumo_do_p99"](_horas([0.4, 1.0]), Ambiente.RELEASE) == "Release: sempre abaixo de 3 s."
    assert sistema["_resumo_da_cpu"](linhas, Ambiente.PRODUCAO) == "Produção: até 0,5%, longe do limite do alerta (80%)."


def test_a_linha_do_limite_so_aparece_perto_dele() -> None:
    # CPU de 0,5% contra o limite de 80%: sem linha; p99 de 29 s contra 3 s: com.
    sistema = _da_tela("Sistema")

    def linhas_do_limite(campo: str, limite: float, horas: list[CpuELatencia]) -> int:
        figura = sistema["_por_ambiente"](horas, campo, None, Filtro(), limite, "", campo, ".1f")
        return sum(forma.type == "line" for forma in figura.layout.shapes)

    assert linhas_do_limite("cpu", 80.0, _horas([0.4, 29.1])) == 0
    assert linhas_do_limite("p99", 3.0, _horas([0.4, 29.1])) == 1
    assert linhas_do_limite("p99", 3.0, _horas([0.4, 0.6])) == 0
