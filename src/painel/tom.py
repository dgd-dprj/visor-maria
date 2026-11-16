"""A nota humana do tom da IA (maria-langgraph-pp #508, visor-maria#12).

O Visor só lê. Para a Nicole e a acessibilidade darem nota, o botão "Dar notas" abre no GitHub uma issue já
preenchida com uma amostra das perguntas, e o Visor lê as notas dessas issues depois.

A nota é cega: cada pergunta vai com um código (`c3-1`, `c3-2`), sem dizer se é do Haiku ou do Qwen com o tom. A
ordem troca a cada caso (par: o Haiku primeiro; ímpar: o Qwen primeiro), para ninguém aprender o padrão. Só as duas
versões que importam para a decisão entram na nota: a produção de hoje e a proposta da #508.
"""

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime

from painel.componentes.formato import sem_hifen
from painel.dados.modelo import FUSO, VERSOES_DO_TOM, CasoDoTom, NotaDoTom, TomDaIA, VersaoDoTom

BLOCO_DE_DADOS = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def ler_comentario_do_tom(corpo: str) -> TomDaIA:
    """O resultado da comparação, do bloco de dados do comentário da #508 (scripts/avaliacao/tom_desambiguacao.py)."""
    achou = BLOCO_DE_DADOS.search(corpo)
    if achou is None:
        raise ValueError("comentário do tom sem o bloco de dados")
    dados = json.loads(achou.group(1))
    versoes = tuple(
        VersaoDoTom(
            versao,
            int(r["perguntas"]),
            tuple((regra, int(n)) for regra, n in r["regras"].items()),
            float(r["palavras_em_media"]),
            int(r.get("com_emoji", 0)),
            float(r["custo"]),
        )
        for versao, r in dados["resumo"].items()
        if versao in VERSOES_DO_TOM
    )
    amostra = tuple(
        CasoDoTom(int(c["caso"]), str(c["relato"]), bool(c["sensivel"]), tuple((v, str(c[v])) for v in VERSOES_DO_TOM if v in c)) for c in dados["amostra"]
    )
    rodado_em = datetime.fromisoformat(dados["rodado_em"]).astimezone(FUSO)
    return TomDaIA(rodado_em, float(dados["custo_total"]), int(dados["relatos"]), int(dados["passadas"]), versoes, amostra)


REPOSITORIO = "dgd-dprj/maria-langgraph-pp"
TITULO_DAS_NOTAS = "[nota de tom]"
# Os casos da amostra que vão para a nota: os dois temas sensíveis, o plano de saúde, o app, a agenda e outros assuntos.
CASOS_PARA_NOTA = (1, 6, 10, 11, 19, 22, 26, 28)
LINHA_DA_NOTA = re.compile(r"^\|\s*c(\d+)-([12])\s*\|.*\|\s*([1-5])\s*\|\s*([1-5])\s*\|\s*$")


def versoes_do_caso(caso: int) -> tuple[str, str]:
    """As versões dos códigos 1 e 2 de um caso."""
    return ("haiku", "qwen_tom") if caso % 2 == 0 else ("qwen_tom", "haiku")


def corpo_das_notas(amostra: tuple[CasoDoTom, ...], rodado_em: datetime) -> str:
    linhas = [
        f"Notas de tom para a comparação de {rodado_em:%d/%m/%Y} (#508). Os relatos são inventados.",
        "",
        "Para cada pergunta, troque o `?` por uma nota de 1 a 5:",
        "- **acolhedor:** a pessoa se sente bem recebida?",
        "- **simples:** dá para entender de primeira, sem termo difícil?",
        "",
        "Não diga de que modelo acha que cada pergunta é: a nota é cega. Ao terminar, crie a issue.",
        "",
        "| código | relato inventado | pergunta | acolhedor | simples |",
        "|---|---|---|---|---|",
    ]
    por_caso = {c.caso: c for c in amostra}
    for numero in CASOS_PARA_NOTA:
        caso = por_caso.get(numero)
        if caso is None:
            continue
        perguntas = dict(caso.perguntas)
        for posicao, versao in enumerate(versoes_do_caso(numero), start=1):
            pergunta = sem_hifen(perguntas.get(versao, "")).replace("|", "/")
            # O relato vai só na primeira linha do caso: o endereço da issue preenchida tem limite de tamanho.
            relato = sem_hifen(caso.exemplo).replace("|", "/") if posicao == 1 else "(o mesmo)"
            linhas.append(f"| c{numero}-{posicao} | {relato} | {pergunta} | ? | ? |")
    return "\n".join(linhas) + "\n"


def endereco_das_notas(amostra: tuple[CasoDoTom, ...], rodado_em: datetime) -> str:
    parametros = {"title": f"{TITULO_DAS_NOTAS} comparação de {rodado_em:%d/%m}", "body": corpo_das_notas(amostra, rodado_em)}
    return f"https://github.com/{REPOSITORIO}/issues/new?" + urllib.parse.urlencode(parametros, quote_via=urllib.parse.quote)


def ler_notas(corpo: str, por: str, em: datetime) -> list[NotaDoTom]:
    """As notas preenchidas de uma issue. Linha com "?" (sem nota) fica de fora."""
    notas = []
    for linha in corpo.splitlines():
        if achou := LINHA_DA_NOTA.match(linha.strip()):
            caso, posicao = int(achou.group(1)), int(achou.group(2))
            versao = versoes_do_caso(caso)[posicao - 1]
            notas.append(NotaDoTom(caso, versao, int(achou.group(3)), int(achou.group(4)), por, em))
    return notas
