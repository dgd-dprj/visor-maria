"""O dia em uma frase, montada a partir dos números do dia.

Cada pedaço da frase sai de uma leitura; se a leitura faltou, o pedaço some, e
a frase diz o que não deu para ler. Nunca é texto escrito à mão.
"""

from __future__ import annotations

from datetime import datetime

from painel.atencao import incidentes_abertos
from painel.componentes.formato import contagem, data_curta, ha_quanto, lista, numero
from painel.dados.modelo import Ambiente, Credencial, DiaDoVerde, Estado, Leitura, ResumoDoDia

NA_FRASE = {Ambiente.PRODUCAO: "A produção", Ambiente.RELEASE: "O release"}


def montar(
    resumo: Leitura[ResumoDoDia],
    verde: Leitura[list[DiaDoVerde]],
    credenciais: dict[Ambiente, Leitura[Credencial]],
    agora: datetime,
    quando: str = "hoje",
    verde_do_dia_inteiro: bool = False,
) -> str:
    """`quando` é "hoje" ou o que foi escolhido ("em 22/10", "em 22/10, das 14h às 15h").
    O último dia do `verde` é o desse dia; com uma hora escolhida, o Verde é o do dia
    inteiro (ele é contado por dia), e a frase diz isso. A credencial é sempre a de agora."""
    partes: list[str] = []
    faltaram: list[str] = []

    if resumo.estado is Estado.OK and resumo.valor is not None:
        r = resumo.valor
        if r.comecaram:
            partes.append(
                f"Em produção, {contagem(r.comecaram, 'pessoa começou', 'pessoas começaram')} um atendimento {quando}, "
                f"e {numero(r.terminaram)} {'terminou' if r.terminaram == 1 else 'terminaram'}."
            )
        else:
            partes.append(f"Em produção, ninguém começou um atendimento {quando}{' ainda' if quando == 'hoje' else ''}.")
        if r.sem_checkpoint:
            partes.append(f"A troca de versão cortou {contagem(r.sem_checkpoint, 'conversa', 'conversas')} no meio.")
    else:
        faltaram.append("os atendimentos")

    if verde.estado is Estado.OK and verde.valor:
        hoje = verde.valor[-1]
        no_dia = "No dia inteiro, o Verde" if verde_do_dia_inteiro else "O Verde"
        if not hoje.total:
            partes.append("Ninguém consultou o Verde no dia inteiro." if verde_do_dia_inteiro else f"Ninguém consultou o Verde {quando}.")
        elif hoje.recusadas:
            partes.append(f"{no_dia} recusou a credencial em {numero(hoje.recusadas)} de {numero(hoje.total)} consultas.")
        else:
            partes.append(f"{no_dia} aceitou a credencial em todas as {numero(hoje.total)} consultas.")
    else:
        faltaram.append("o Verde")

    lidas = {a: c for a, c in credenciais.items() if c.estado is Estado.OK and c.valor is not None}
    abertos = incidentes_abertos(lidas, agora)
    for incidente in abertos:
        partes.append(f"{NA_FRASE[incidente.ambiente]} segue sem credencial, {ha_quanto(incidente.desde, agora)}.")
    if not abertos and Ambiente.PRODUCAO in lidas:
        valor = lidas[Ambiente.PRODUCAO].valor
        assert valor is not None
        partes.append(f"A credencial de produção vale até {data_curta(valor.valida_ate)}.")
    if len(lidas) < len(credenciais):
        faltaram.append("a credencial")

    if faltaram:
        partes.append(f"Não deu para ler {lista(faltaram)}.")
    return " ".join(partes)
