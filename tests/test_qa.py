"""A tela QA (visor-maria#10): o que cada rodada de QA imprime vira rodada e defeito.

Os textos de exemplo copiam o formato real: o log do job `ponta_a_ponta`
(maria-langgraph-pp, scripts/qa/fluxos_ponta_a_ponta.py) e os comentários "QA da
staging" dos PRs #499 (resumo do roteiro) e #496 (tabela de rodadas), de 16/11.
"""

from datetime import datetime

from painel.dados.modelo import FUSO, DefeitoDoQA, RodadaDoQA
from painel.dados.real import ler_comentario_da_staging, ler_log_do_ponta_a_ponta, marcar_resolvidos

LOG_QUE_PASSOU = """2026-11-16T18:10:01.1Z ### QA de ponta a ponta: grupo `normal` (Verde, IA e e-mail simulados)
2026-11-16T18:10:01.2Z | Pessoa presa com processo, até o fim (concluído) | OK | 6 passos |
2026-11-16T18:10:01.3Z **14 de 14 cenários OK.**
2026-11-16T18:10:30.1Z **1 de 1 cenários OK.**
"""

LOG_QUE_FALHOU = """2026-11-16T18:10:01.2Z | Pessoa presa com processo, até o fim (concluído) | OK | 6 passos |
2026-11-16T18:10:01.3Z | Violência doméstica: CPF com a conta errada não vai ao Verde (#497) | **FALHOU** | passo 5 («12345678900»): a resposta não tem «Esse CPF não está certo». |
2026-11-16T18:10:01.4Z **13 de 14 cenários OK.**
"""

PR_499 = """## QA da staging (16/11/2026 11:42, commit 6266722)

**20 de 20 OK.** Custo de IA: US$ 0.0052. Conversas `qa-staging-*-20261116-114127`.

- ✅ publicação do release é do commit atual da staging
"""

COM_FALHA = """## QA da staging (17/11/2026 10:00, commit abc1234)

**19 de 20 OK.** Custo de IA: US$ 0,0123. Conversas `qa-staging-*`.

- ✅ /health
- ❌ encerrar pelo número (o assunto 2 continuou em aberto)
"""

PR_496 = """## QA da staging depois do merge (16/11/2026, commit `82b7888`)

| Rodada | Resultado | Custo de IA |
|---|---|---|
| 1ª (09:50) | **11 de 18** | US$ 0,0105 |
| 2ª (09:51) | **18 de 18** | ~US$ 0,01 |

**O que falhou na 1ª rodada, e por quê:** a triagem por IA devolveu só dois assuntos.
"""

HORA = datetime(2026, 11, 16, 12, 52, tzinfo=FUSO)


def test_o_log_que_passou_soma_os_dois_grupos() -> None:
    assert ler_log_do_ponta_a_ponta(LOG_QUE_PASSOU) == (15, 15, [])


def test_o_log_que_falhou_traz_o_cenario_e_o_detalhe() -> None:
    passaram, total, falhas = ler_log_do_ponta_a_ponta(LOG_QUE_FALHOU)
    assert (passaram, total) == (13, 14)
    [(cenario, detalhe)] = falhas
    assert cenario.startswith("Violência doméstica: CPF com a conta errada")
    assert detalhe.startswith("passo 5")


def test_o_resumo_do_roteiro_vira_uma_rodada_com_o_custo() -> None:
    rodadas, defeitos = ler_comentario_da_staging(PR_499, HORA, 499)
    assert rodadas == [RodadaDoQA(HORA, "staging", 499, "6266722", 20, 20, 0.0052)]
    assert defeitos == []


def test_o_custo_com_virgula_e_a_conferencia_que_falhou() -> None:
    rodadas, defeitos = ler_comentario_da_staging(COM_FALHA, HORA, 510)
    assert rodadas[0].custo == 0.0123 and not rodadas[0].passou
    assert [(d.cenario, d.detalhe, d.commit) for d in defeitos] == [("encerrar pelo número", "o assunto 2 continuou em aberto", "abc1234")]


def test_a_tabela_de_rodadas_vira_duas_rodadas_e_um_defeito() -> None:
    rodadas, defeitos = ler_comentario_da_staging(PR_496, HORA, 496)
    assert [(r.quando.hour, r.quando.minute, r.passaram, r.total, r.custo) for r in rodadas] == [(9, 50, 11, 18, 0.0105), (9, 51, 18, 18, 0.01)]
    [defeito] = defeitos
    assert defeito.cenario == "1ª rodada: 7 conferências de 18 falharam"
    assert "triagem" in defeito.detalhe and defeito.commit == "82b7888"


def test_comentario_sem_resumo_nao_vira_rodada() -> None:
    assert ler_comentario_da_staging("## QA da staging\n\nAinda rodando.", HORA, 1) == ([], [])


def test_o_defeito_do_ponta_a_ponta_resolve_no_mesmo_pr_e_o_da_staging_em_qualquer_um() -> None:
    def h(hora: int) -> datetime:
        return datetime(2026, 11, 16, hora, tzinfo=FUSO)

    rodadas = [
        RodadaDoQA(h(10), "ponta_a_ponta", 1, "a", 13, 14, 0),
        RodadaDoQA(h(11), "ponta_a_ponta", 2, "b", 14, 14, 0),  # outro PR: não resolve o do PR 1
        RodadaDoQA(h(12), "ponta_a_ponta", 1, "c", 14, 14, 0),
        RodadaDoQA(h(10), "staging", 7, "d", 19, 20, 0.01),
        RodadaDoQA(h(13), "staging", 8, "e", 20, 20, 0.01),
    ]
    defeitos = [DefeitoDoQA(h(10), "ponta_a_ponta", "x", "", 1, "a"), DefeitoDoQA(h(10), "staging", "y", "", 7, "d")]
    resolvidos = marcar_resolvidos(rodadas, defeitos)
    assert [d.resolvido_em for d in resolvidos] == [h(12), h(13)]


def test_sem_rodada_seguinte_que_passe_o_defeito_fica_aberto() -> None:
    quando = datetime(2026, 11, 16, 10, tzinfo=FUSO)
    defeito = DefeitoDoQA(quando, "staging", "y", "", 7, "d")
    assert marcar_resolvidos([RodadaDoQA(quando, "staging", 7, "d", 19, 20, 0.01)], [defeito])[0].resolvido_em is None
