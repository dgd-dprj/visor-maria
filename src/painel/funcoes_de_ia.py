"""As funções de inteligência artificial da Maria, como o código de develop as descreve.

Lido de src/maria/ia/*.py em 26/10. "Se falha" repete o que a mensagem de erro de
cada função diz que ela faz quando o modelo não responde. Função nova na Maria
entra aqui; o Observatório da IA mostra esta lista com as falhas medidas.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FuncaoDeIA:
    """Uma função de IA da Maria, como o código de develop a descreve (lido em 26/10)."""

    codigo: str
    nome: str
    faz: str
    onde: str
    se_falha: str


FUNCOES = (
    FuncaoDeIA(
        "classificar",
        "Classificar o relato",
        "Lê o relato livre e escolhe o assunto entre os atendimentos da Maria.",
        "triagem por escrita livre",
        "Trata como não identificado: o caso volta para a Tykhe como outros.",
    ),
    FuncaoDeIA(
        "desambiguar",
        "Perguntar para desempatar",
        "Quando o relato serve a mais de um assunto, escreve uma pergunta curta que ajuda a escolher.",
        "triagem por escrita livre",
        "Usa uma pergunta genérica.",
    ),
    FuncaoDeIA(
        "sumarizar",
        "Resumir o relato",
        "Depois de 3 rodadas de desempate, resume o que a pessoa contou, para não reenviar tudo.",
        "triagem por escrita livre",
        "Mantém o texto inteiro.",
    ),
    FuncaoDeIA(
        "extrair",
        "Tirar dados do relato",
        "Tira do relato sobre pessoa presa o RG, o número do processo, se há processo e o parentesco de quem fala. A instrução diz para nunca inventar.",
        "pessoa presa",
        "Segue sem nada extraído: a pessoa responde às perguntas uma a uma.",
    ),
    FuncaoDeIA(
        "reescrever",
        "Reescrever as perguntas",
        "Reescreve o texto de cada pergunta dos fluxos, sem mudar o que se pergunta.",
        "todos os fluxos",
        "Usa o texto original da pergunta.",
    ),
)
