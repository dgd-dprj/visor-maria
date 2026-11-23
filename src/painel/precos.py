"""Preços por milhão de tokens, cada um com a fonte e se já foi confirmado.

A conta do custo só usa preço daqui, e a tela mostra a fonte ao lado. Quando a
fatura da AWS estiver legível (leitura de custo, pedido ao Ícaro), ela substitui
esta conta: o preço de tabela vira só conferência.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from painel.dados.fontes import MODELO_DE_CHAT, MODELO_DE_EMBEDDING
from painel.dados.modelo import GastoDeIA, GastoDoAssunto

# O perfil "us." é endpoint regional: 10% acima do global, para o Haiku 4.5 e
# os modelos seguintes (documentação da Anthropic, "Global versus regional endpoints").
ACRESCIMO_REGIONAL = 1.10


@dataclass(frozen=True)
class Preco:
    nome: str
    entrada: float
    saida: float
    fonte: str
    confirmado: bool


PRECOS = {
    MODELO_DE_CHAT: Preco(
        nome="Claude Haiku 4.5, perfil regional (us)",
        entrada=1.00 * ACRESCIMO_REGIONAL,
        saida=5.00 * ACRESCIMO_REGIONAL,
        fonte=(
            "US$ 1 e US$ 5 da tabela da Anthropic, mais 10% do endpoint regional (documentação da Anthropic, "
            "consultada em 26/10). O preço do Bedrock em si falta conferir na fatura."
        ),
        confirmado=False,
    ),
    MODELO_DE_EMBEDDING: Preco(
        nome="Titan Text Embeddings v2",
        entrada=0.02,
        saida=0.0,
        fonte="US$ 0,02 por milhão de tokens, de memória: a página de preços da AWS não trouxe o valor em 26/10.",
        confirmado=False,
    ),
}


def custo(modelo: str, entrada: int, saida: int) -> float:
    preco = PRECOS[modelo]
    return (entrada * preco.entrada + saida * preco.saida) / 1_000_000


class Parcela(StrEnum):
    """De onde vem o gasto, nos nomes que a tela financeira mostra."""

    LIDO = "lido"
    ESCRITO = "escrito"
    BUSCA = "busca"


NOME_DA_PARCELA = {
    Parcela.LIDO: "Inteligência artificial: texto lido",
    Parcela.ESCRITO: "Inteligência artificial: texto escrito",
    Parcela.BUSCA: "Busca por semelhança",
}

# "Servidores e rede" é a quarta parcela, e fica reservada: só a fatura diz
# quanto custa (pendência com o Ícaro). Não entra em nenhuma soma daqui.
NOME_DOS_SERVIDORES = "Servidores e rede"


def parcelas(gasto: GastoDeIA) -> dict[Parcela, float]:
    chat, embedding = PRECOS[MODELO_DE_CHAT], PRECOS[MODELO_DE_EMBEDDING]
    return {
        Parcela.LIDO: gasto.lido * chat.entrada / 1_000_000,
        Parcela.ESCRITO: gasto.escrito * chat.saida / 1_000_000,
        Parcela.BUSCA: gasto.busca * embedding.entrada / 1_000_000,
    }


def total(gasto: GastoDeIA) -> float:
    return sum(parcelas(gasto).values())


def custo_do_assunto(assunto: GastoDoAssunto) -> float:
    """Só o que veio dividido. O que veio só como total fica fora: não dá para
    pôr preço sem saber quanto foi lido e quanto foi escrito (#340 na Maria)."""
    return custo(MODELO_DE_CHAT, assunto.lido, assunto.escrito)
