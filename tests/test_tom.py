"""O tom da IA no Observatório (visor-maria#12): o bloco de dados da #508 e a nota cega da equipe."""

import json
from datetime import datetime

from painel.dados.modelo import FUSO, CasoDoTom
from painel.tom import CASOS_PARA_NOTA, corpo_das_notas, endereco_das_notas, ler_comentario_do_tom, ler_notas, versoes_do_caso

DADOS = {
    "rodado_em": "2026-11-16T20:16:23+00:00",
    "custo_total": 0.192208,
    "relatos": 30,
    "passadas": 2,
    "resumo": {
        "haiku": {"nome": "Haiku", "perguntas": 60, "regras": {"tem_acolhimento": 51}, "palavras_em_media": 25.9, "com_emoji": 0, "custo": 0.08},
        "qwen_tom": {"nome": "Qwen", "perguntas": 60, "regras": {"tem_acolhimento": 59}, "palavras_em_media": 18.8, "com_emoji": 3, "custo": 0.05},
    },
    "amostra": [{"caso": 1, "relato": "Meu irmão foi preso.", "sensivel": True, "haiku": "Onde ele está?", "qwen_tom": "Como posso ajudar?"}],
}
COMENTARIO = "## Tom da desambiguação\n\n<!-- visor:tom-da-ia -->\n```json\n" + json.dumps(DADOS, ensure_ascii=False) + "\n```\n"
QUANDO = datetime(2026, 11, 16, 17, 16, tzinfo=FUSO)


def test_o_bloco_de_dados_vira_o_tom_da_ia() -> None:
    tom = ler_comentario_do_tom(COMENTARIO)
    assert tom.relatos == 30 and tom.custo == 0.192208 and tom.rodado_em.hour == 17
    assert [(v.versao, dict(v.regras)["tem_acolhimento"]) for v in tom.versoes] == [("haiku", 51), ("qwen_tom", 59)]
    [caso] = tom.amostra
    assert caso.sensivel and dict(caso.perguntas) == {"haiku": "Onde ele está?", "qwen_tom": "Como posso ajudar?"}


def test_a_nota_e_cega_e_a_ordem_troca_a_cada_caso() -> None:
    assert versoes_do_caso(1) == ("qwen_tom", "haiku")
    assert versoes_do_caso(2) == ("haiku", "qwen_tom")
    amostra = tuple(CasoDoTom(n, f"relato {n}", False, (("haiku", f"h{n}?"), ("qwen_tom", f"q{n}?"))) for n in CASOS_PARA_NOTA)
    corpo = corpo_das_notas(amostra, QUANDO)
    assert "haiku" not in corpo.lower() and "qwen" not in corpo.lower(), "a issue não diz de que modelo é cada pergunta"
    assert corpo.count("| ? | ? |") == 2 * len(CASOS_PARA_NOTA)


def test_o_endereco_da_issue_cabe_no_limite_do_github() -> None:
    longa = "Você quer saber como está a situação dele na prisão ou como anda o processo na Justiça, com audiência e decisão?"
    amostra = tuple(
        CasoDoTom(n, "Relato inventado de tamanho parecido com os da comparação de verdade.", True, (("haiku", longa), ("qwen_tom", longa)))
        for n in CASOS_PARA_NOTA
    )
    assert len(endereco_das_notas(amostra, QUANDO)) < 7000


def test_as_notas_preenchidas_voltam_com_a_versao_certa() -> None:
    corpo = "| código | relato | pergunta | acolhedor | simples |\n|---|---|---|---|---|\n| c1-1 | r | p | 5 | 4 |\n| c1-2 | (o mesmo) | p | 3 | ? |\n| c2-1 | r | p | 2 | 2 |\n"
    notas = ler_notas(corpo, "equipe", QUANDO)
    assert [(n.caso, n.versao, n.acolhedor, n.simples) for n in notas] == [(1, "qwen_tom", 5, 4), (2, "haiku", 2, 2)]
