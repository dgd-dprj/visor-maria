"""Fonte inventada, com a mesma forma da fonte real.

Os números seguem medições reais quando há uma, e a ordem de grandeza delas
quando não há. Medidos (sem dado pessoal, só contagens):

- tokens e chamadas do Bedrock em 30 dias e os de 19 a 25/10 (CloudWatch, 26/10);
- embeddings em 30 dias: 660.059 tokens (CloudWatch, 26/10), cerca de 22 mil por dia;
- validade das credenciais e renovações (logs do verificar-token-verde.yml, 26/10):
  produção renovada no domingo, 25/10, às 12:24; release válida até 23/11, 10:34;
- conferência diária: 6 sucessos e 32 falhas desde 19/09, última falha em 22/10;
- atendimentos, incidentes e orquestrador: levantamento de 23/10;
- incidente de 28/09 a 01/10 (produção): levantamento de 26/10, contado do
  mesmo jeito que os outros (linhas de 401 e atendimentos encerrados na janela).

O resto é inventado: só serve para fechar o desenho. A validade da credencial
nova de produção não aparece no log da renovação, então a daqui é estimada.

O `cenario` força um estado em todas as leituras, para conferir o texto de cada
um: "normal", "vazio" ou "falha".
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import astuple
from datetime import date, datetime, timedelta

from painel.dados import fontes
from painel.dados.modelo import (
    AMBIENTE_DA_ORIGEM,
    FUSO,
    Ambiente,
    Assunto,
    ContagemPorDia,
    ContagemPorHora,
    ConversasDoFluxo,
    CpuELatencia,
    Credencial,
    Desfecho,
    DesfechoDoFluxo,
    Destino,
    DiaDoModelo,
    DiaDoVerde,
    DuracaoDasConversas,
    DuracaoDoVerde,
    EncaminhamentoNoDia,
    EnvioDoWhatsapp,
    ErroDaIA,
    Estado,
    FimDaConversa,
    FluxoNoDia,
    Fonte,
    GastoDeIA,
    GastoDoAssunto,
    HorarioDaConferencia,
    IncidenteDeCredencial,
    Leitura,
    MudancaNaIA,
    Origem,
    OrigemNaoAtendida,
    ProblemaNoDia,
    RecursosDoServico,
    Renovacao,
    RequisicoesPorHora,
    RespostasComErro,
    ResultadoDoVerde,
    ResumoDoDia,
    ResumoDoOrquestrador,
    ResumoDoPeriodo,
    RodadaDaTriagem,
    Rotina,
    SaidaDaTriagem,
    SaudeServico,
    SistemaNoDia,
    TempoDeResposta,
    TokensDoDia,
    TokensRegistrados,
    TrechoDeNaoEncontrado,
    UsoDaIA,
)

MOTIVO_DA_FALHA_SIMULADA = "A fonte não respondeu a esta leitura (falha simulada)."


def _h(dia: int, mes: int, hora: int, minuto: int) -> datetime:
    return datetime(2026, mes, dia, hora, minuto, tzinfo=FUSO)


# Produção passou a rodar a versão Python em 23/10, às 12:30 (container novo).
CORTE_DE_VERSAO = _h(23, 10, 12, 31)
SUBIDA_DA_PRODUCAO = _h(23, 10, 12, 30)
INICIO_DAS_ROTINAS = date(2026, 9, 19)
CONFERENCIA_DE_ONTEM = _h(25, 10, 12, 24)
# Os fluxos da Maria (src/maria/fluxos/__init__.py).
PESSOA_PRESA = "3df874f2-675a-4c43-9ec7-480f7c702f50"
VIOLENCIA_DOMESTICA = "cabb2495-4e12-4f4a-9956-3d20649059bc"
PLANO_DE_SAUDE = "84433c84-4776-4b05-a5a0-af8012d8eced"
# Antes disso, a fonte simulada não conta gasto nenhum.
INICIO_DO_GASTO = date(2026, 8, 1)

CREDENCIAIS = {
    # Estimada: a renovação de 25/10 não imprime a validade nova.
    Ambiente.PRODUCAO: (_h(25, 10, 12, 26), _h(24, 11, 12, 26)),
    # Validade medida no log; a emissão é estimada.
    Ambiente.RELEASE: (_h(23, 10, 10, 34), _h(23, 11, 10, 34)),
}

INCIDENTES = [
    # Anterior à #316 e com o mesmo padrão: 733 recusas, todas de um container
    # só, e o Verde volta a aceitar na primeira linha do container seguinte
    # (01/10, 09:55). Os 221 encerrados saíram como "RG não encontrado".
    IncidenteDeCredencial(Ambiente.PRODUCAO, _h(28, 9, 17, 38), _h(1, 10, 9, 55), 733, 221),
    IncidenteDeCredencial(Ambiente.RELEASE, _h(4, 10, 11, 57), _h(23, 10, 10, 40), 27, None),
    IncidenteDeCredencial(Ambiente.PRODUCAO, _h(20, 10, 16, 29), _h(20, 10, 17, 23), 33, None),
    IncidenteDeCredencial(Ambiente.PRODUCAO, _h(22, 10, 13, 27), _h(23, 10, 12, 34), 283, 75),
]

RENOVACOES = [
    Renovacao(Ambiente.PRODUCAO, _h(22, 10, 13, 27), container_novo_no_ar=False),
    Renovacao(Ambiente.PRODUCAO, _h(25, 10, 12, 26), container_novo_no_ar=True),
]

# CloudWatch, AWS/Bedrock, ModelId do Haiku 4.5, medido em 26/10.
TOKENS_MEDIDOS = {
    date(2026, 10, 19): (108_040, 3_964, 93),
    date(2026, 10, 20): (100_384, 3_650, 94),
    date(2026, 10, 21): (150_358, 5_425, 116),
    date(2026, 10, 22): (324_638, 12_541, 227),
    date(2026, 10, 23): (43_075, 1_549, 39),
    date(2026, 10, 24): (14_961, 552, 14),
    date(2026, 10, 25): (6_407, 235, 6),
}


class FonteSimulada:
    def __init__(self, cenario: str = "normal", agora: Callable[[], datetime] | None = None) -> None:
        if cenario not in ("normal", "vazio", "falha"):
            raise ValueError(f"cenário desconhecido: {cenario!r} (use normal, vazio ou falha)")
        self._cenario = cenario
        self.nome = f"simulado:{cenario}"
        self._agora = agora or (lambda: datetime.now(FUSO))

    def _sorteio(self, *chave: object) -> random.Random:
        # Mesma chave, mesmo número: duas telas abertas ao mesmo tempo concordam.
        return random.Random(":".join(map(str, chave)))

    def _ler[T](self, fonte: Fonte, gerar: Callable[[datetime], T | None]) -> Leitura[T]:
        momento = self._agora()
        if self._cenario == "falha":
            return Leitura(None, Estado.INDISPONIVEL, fonte, momento, MOTIVO_DA_FALHA_SIMULADA)
        valor = None if self._cenario == "vazio" else gerar(momento)
        if valor is None:
            return Leitura(None, Estado.VAZIO, fonte, momento)
        return Leitura(valor, Estado.OK, fonte, momento)

    # ── Agora ─────────────────────────────────────────────────────────────

    def saude_servico(self, ambiente: Ambiente) -> Leitura[SaudeServico]:
        return self._ler(fontes.fonte_saude_servico(ambiente), lambda _: SaudeServico(1, 1))

    def implantacoes_em_curso(self, ambiente: Ambiente) -> Leitura[int]:
        # 1 é o normal: uma versão rodando. Mais de 1 por muito tempo foi o sinal do incidente de 22/10.
        return self._ler(fontes.fonte_implantacoes(ambiente), lambda _: 1)

    def ultimo_reinicio(self, ambiente: Ambiente) -> Leitura[datetime]:
        def gerar(momento: datetime) -> datetime:
            if ambiente is Ambiente.PRODUCAO:
                return SUBIDA_DA_PRODUCAO
            return (momento - timedelta(hours=5, minutes=12)).replace(second=0, microsecond=0)

        return self._ler(fontes.fonte_ultimo_reinicio(ambiente), gerar)

    def _resumo(self, ambiente: Ambiente, dia: date, momento: datetime) -> ResumoDoDia:
        """O dia de um ambiente. O resumo e os atendimentos por dia saem daqui, para baterem."""
        if dia > momento.date():
            return ResumoDoDia(0, 0, 0, 0, 0, 0)
        # Um dia que já passou conta inteiro: das 7h às 19h.
        horas = 12.0 if dia < momento.date() else max(momento.hour - 7, 0) + momento.minute / 60
        sorteio = self._sorteio(ambiente, "resumo", dia)
        ritmo = sorteio.uniform(3.5, 5.0) if ambiente is Ambiente.PRODUCAO else sorteio.uniform(0.3, 0.8)
        comecaram = int(horas * ritmo)
        terminaram = int(comecaram * 0.7)
        consultas = int(comecaram * 1.6)
        return ResumoDoDia(comecaram, terminaram, consultas, int(consultas * 0.88), int(comecaram * 5.6), 0)

    def resumo_do_dia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[ResumoDoDia]:
        def gerar(momento: datetime) -> ResumoDoDia:
            r = self._resumo(ambiente, _o_dia(dia) if dia else momento.date(), momento)
            # A hora escolhida: a fatia dela no dia (das 7h às 19h, um doze avos cada).
            fatia = _fatia_da_hora(dia)
            return ResumoDoDia(*(int(v * fatia) for v in astuple(r)))

        return self._ler(fontes.fonte_resumo_do_dia(ambiente, dia), gerar)

    def credencial(self, ambiente: Ambiente) -> Leitura[Credencial]:
        def gerar(momento: datetime) -> Credencial:
            emitida, validade = CREDENCIAIS[ambiente]
            minutos = 10 if ambiente is Ambiente.PRODUCAO else 140
            ultima_aceita = (momento - timedelta(minutes=minutos)).replace(second=0, microsecond=0)
            return Credencial(emitida, validade, ultima_aceita, CONFERENCIA_DE_ONTEM, True)

        return self._ler(fontes.fonte_credencial(ambiente), gerar)

    def rotinas(self) -> Leitura[list[Rotina]]:
        return self._ler(
            fontes.fonte_rotinas(),
            lambda _: [
                Rotina("Testes a cada mudança", INICIO_DAS_ROTINAS, 126, 1, None),
                Rotina("Subidas no release", INICIO_DAS_ROTINAS, 51, 0, None, canceladas=7),
                Rotina("Subidas em produção", INICIO_DAS_ROTINAS, 2, 0, None),
                Rotina("Conferência diária da credencial", INICIO_DAS_ROTINAS, 6, 32, None, ultima_falha=_h(22, 10, 13, 27)),
            ],
        )

    def renovacoes(self) -> Leitura[list[Renovacao]]:
        return self._ler(fontes.fonte_renovacoes(), lambda _: list(RENOVACOES))

    def verde_por_dia(self, ambiente: Ambiente) -> Leitura[list[DiaDoVerde]]:
        def gerar(momento: datetime) -> list[DiaDoVerde]:
            hoje = momento.date()
            dias = [hoje - timedelta(days=n) for n in range(fontes.DIAS_DO_GRAFICO_DO_VERDE - 1, -1, -1)]
            resultado = []
            for dia in dias:
                sorteio = self._sorteio(ambiente, "verde", dia)
                if ambiente is Ambiente.RELEASE:
                    # Vencida de 04/10 até a credencial nova de 23/10.
                    if dia < date(2026, 10, 23):
                        resultado.append(DiaDoVerde(dia, 0, sorteio.randint(0, 7), 0))
                    else:
                        resultado.append(DiaDoVerde(dia, sorteio.randint(0, 6), 0, sorteio.randint(0, 1)))
                    continue
                fim_de_semana = dia.weekday() >= 5
                total = sorteio.randint(40, 70) if fim_de_semana else sorteio.randint(150, 210)
                if dia == hoje:
                    total = int(total * min(max(momento.hour - 7, 0), 12) / 12)
                recusadas = _recusas_do_incidente(dia, total)
                nao_achou, sem_resposta, erro = _o_resto_do_verde(sorteio, total)
                outras = nao_achou + sem_resposta + erro
                resultado.append(DiaDoVerde(dia, max(total - recusadas - outras, 0), recusadas, outras, nao_achou, sem_resposta))
            return resultado

        return self._ler(fontes.fonte_verde_por_dia(ambiente), gerar)

    # ── Credencial do Verde ───────────────────────────────────────────────

    def incidentes_de_credencial(self) -> Leitura[list[IncidenteDeCredencial]]:
        return self._ler(fontes.fonte_incidentes(), lambda _: list(INCIDENTES))

    # ── Sistema ───────────────────────────────────────────────────────────

    def _parte(self, dia: date | None, *chave: object, de: int = 7) -> float:
        """Sem o dia escolhido, 1 (a janela inteira); com ele, a fatia de um dia de
        uma janela de `de` dias, sorteada para cada dia ter o seu número; com a hora
        escolhida, a fatia dela nesse dia."""
        if dia is None:
            return 1.0
        return self._sorteio("parte", dia, *chave).uniform(0.5, 1.5) / de * _fatia_da_hora(dia)

    def tempo_de_resposta(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[TempoDeResposta]:
        def gerar(_: datetime) -> TempoDeResposta:
            ajuste = self._sorteio("tempo", ambiente, dia).uniform(0.8, 1.2) if dia else 1.0
            if ambiente is Ambiente.PRODUCAO:
                return TempoDeResposta(912, 1.1 * ajuste, 3.3 * ajuste, 5.0 * ajuste)
            return TempoDeResposta(124, 0.9 * ajuste, 2.4 * ajuste, 4.1 * ajuste)

        return self._ler(fontes.fonte_tempo_de_resposta(ambiente, dia), gerar)

    def duracao_do_verde(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DuracaoDoVerde]]:
        def gerar(_: datetime) -> list[DuracaoDoVerde]:
            p = self._parte(dia, "duracao", ambiente)
            if ambiente is Ambiente.PRODUCAO:
                return [DuracaoDoVerde("pessoa", int(1_104 * p), 3.5, 29.3), DuracaoDoVerde("processo", int(127 * p), 10.6, 26.7)]
            return [DuracaoDoVerde("pessoa", int(31 * p), 2.9, 11.2), DuracaoDoVerde("cep", int(9 * p), 0.8, 1.9)]

        return self._ler(fontes.fonte_duracao_do_verde(ambiente, dia), gerar)

    def resultado_do_verde(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[ResultadoDoVerde]:
        def gerar(_: datetime) -> ResultadoDoVerde:
            p = self._parte(dia, "resultado", ambiente)
            if ambiente is Ambiente.PRODUCAO:
                recusadas = 316 if dia is None else _recusas_do_incidente(dia, int(180 * p * 7))
                return ResultadoDoVerde(aceitas=int(948 * p), credencial_recusada=recusadas, erro_do_verde=int(6 * p), nao_encontrado=int(121 * p))
            return ResultadoDoVerde(aceitas=int(12 * p), credencial_recusada=int(27 * p), erro_do_verde=0, nao_encontrado=int(2 * p))

        return self._ler(fontes.fonte_resultado_do_verde(ambiente, dia), gerar)

    def respostas_com_erro(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[RespostasComErro]:
        def gerar(_: datetime) -> RespostasComErro:
            p = self._parte(dia, "erros", ambiente, de=1)
            if ambiente is Ambiente.PRODUCAO:
                return RespostasComErro(de_gente=int(14 * p), de_robo=int(61 * p), de_servidor=0)
            return RespostasComErro(de_gente=int(3 * p), de_robo=int(22 * p), de_servidor=0)

        return self._ler(fontes.fonte_respostas_com_erro(ambiente, dia), gerar)

    def tokens_por_dia(self) -> Leitura[list[TokensDoDia]]:
        def gerar(momento: datetime) -> list[TokensDoDia]:
            hoje = momento.date()
            dias = [hoje - timedelta(days=n) for n in range(fontes.DIAS_DO_CUSTO - 1, -1, -1)]
            return [TokensDoDia(dia, *self._tokens_do_dia(dia, momento)) for dia in dias]

        return self._ler(fontes.fonte_tokens_por_dia(), gerar)

    def _tokens_do_dia(self, dia: date, momento: datetime) -> tuple[int, int, int]:
        """Tokens lidos, escritos e chamadas do modelo de conversa num dia. A
        mesma conta serve à tela Sistema e à financeira, para as duas baterem."""
        if dia > momento.date() or dia < INICIO_DO_GASTO:
            return 0, 0, 0
        if dia in TOKENS_MEDIDOS:
            return TOKENS_MEDIDOS[dia]
        sorteio = self._sorteio("tokens", dia)
        chamadas = sorteio.randint(20, 60) if dia.weekday() < 5 else sorteio.randint(3, 12)
        chamadas = int(chamadas * _parte_do_dia(dia, momento))
        return chamadas * 1_150, chamadas * 42, chamadas

    # ── Relatório da Aplicação ────────────────────────────────────────────

    def _gasto_do_dia(self, dia: date, momento: datetime) -> GastoDeIA:
        lido, escrito, _ = self._tokens_do_dia(dia, momento)
        busca = 0
        if INICIO_DO_GASTO <= dia <= momento.date():
            # A reindexação a cada subida de container: cerca de 22 mil tokens por dia.
            busca = int(self._sorteio("busca", dia).randint(18_000, 26_000) * _parte_do_dia(dia, momento))
        return GastoDeIA(dia, lido, escrito, busca)

    def gasto_do_dia(self, dia: date) -> Leitura[GastoDeIA]:
        return self._ler(fontes.fonte_gasto_de_ia(), lambda momento: self._gasto_do_dia(dia, momento))

    def gasto_do_mes(self, mes: date) -> Leitura[GastoDeIA]:
        def gerar(momento: datetime) -> GastoDeIA:
            primeiro = mes.replace(day=1)
            dias = [primeiro + timedelta(days=n) for n in range(31) if (primeiro + timedelta(days=n)).month == primeiro.month]
            lido = escrito = busca = 0
            for dia in dias:
                g = self._gasto_do_dia(dia, momento)
                lido, escrito, busca = lido + g.lido, escrito + g.escrito, busca + g.busca
            return GastoDeIA(primeiro, lido, escrito, busca)

        return self._ler(fontes.fonte_gasto_de_ia(), gerar)

    def gasto_por_assunto(self, ambiente: Ambiente, dia: date) -> Leitura[list[GastoDoAssunto]]:
        def gerar(momento: datetime) -> list[GastoDoAssunto]:
            if dia > momento.date() or dia < INICIO_DO_GASTO:
                return []
            sorteio = self._sorteio("assunto", ambiente, dia)
            parte = _parte_do_dia(dia, momento)
            util = dia.weekday() < 5

            def atendimentos(minimo: int, maximo: int) -> int:
                return int(sorteio.randint(minimo, maximo) * parte)

            if ambiente is Ambiente.PRODUCAO:
                # Produção não chama a triagem hoje (levantamento de 23/10).
                presa = atendimentos(55, 95) if util else atendimentos(5, 20)
                violencia = atendimentos(0, 2)
                return [
                    GastoDoAssunto(Assunto.PESSOA_PRESA, presa, presa * 560, presa * 20),
                    GastoDoAssunto(Assunto.VIOLENCIA_DOMESTICA, violencia, violencia * 2_800, violencia * 110),
                ]
            presa, violencia, triagens = atendimentos(0, 3), atendimentos(0, 1), atendimentos(1, 6)
            return [
                GastoDoAssunto(Assunto.PESSOA_PRESA, presa, presa * 560, presa * 20),
                GastoDoAssunto(Assunto.VIOLENCIA_DOMESTICA, violencia, violencia * 2_800, violencia * 110),
                GastoDoAssunto(Assunto.TRIAGEM, triagens, 0, 0, triagens * 1_000),
            ]

        return self._ler(fontes.fonte_gasto_por_assunto(ambiente), gerar)

    def tokens_registrados(self, ambiente: Ambiente) -> Leitura[list[TokensRegistrados]]:
        """Produção registra quase tudo o que a conta mede (o resto é a conversa
        abandonada); o release, um pouco de triagem. Os dias medidos de 27 e 28/10,
        em que o gasto veio de fora das conversas, ficam assim também."""

        def gerar(momento: datetime) -> list[TokensRegistrados] | None:
            resultado = []
            for n in range(fontes.DIAS_DO_REGISTRO - 1, -1, -1):
                dia = momento.date() - timedelta(days=n)
                lido, escrito, _ = self._tokens_do_dia(dia, momento)
                if ambiente is Ambiente.PRODUCAO:
                    parte = self._sorteio("registrado", dia).uniform(0.85, 1.0)
                    resultado.append(TokensRegistrados(dia, int(lido * parte), int(escrito * parte), 0))
                else:
                    resultado.append(TokensRegistrados(dia, 0, 0, int(lido * 0.05)))
            return resultado

        return self._ler(fontes.fonte_tokens_registrados(ambiente), gerar)

    # ── Atendimento ───────────────────────────────────────────────────────

    def _trecho(self, origem: Origem, momento: datetime, dia: date) -> tuple[datetime, datetime, float]:
        """A parte do trecho da origem que cai no dia escolhido, e as horas dela."""
        if origem is Origem.PRODUCAO_TS:
            inicio, fim = _h(16, 10, 0, 0), CORTE_DE_VERSAO
        elif origem is Origem.PRODUCAO_PY:
            inicio, fim = CORTE_DE_VERSAO, momento
        else:
            inicio, fim = momento - timedelta(days=7), momento
        # A hora escolhida chega como o começo dela (um datetime); o dia, como date.
        comeco = dia if isinstance(dia, datetime) else datetime.combine(dia, datetime.min.time(), tzinfo=FUSO)
        final = comeco + (timedelta(hours=1) if isinstance(dia, datetime) else timedelta(days=1))
        inicio, fim = max(inicio, comeco), min(fim, final, momento)
        return inicio, max(fim, inicio), max((fim - inicio).total_seconds() / 3600, 0)

    def resumo_do_periodo(self, origem: Origem, dia: date | None = None) -> Leitura[ResumoDoPeriodo]:
        def gerar(momento: datetime) -> ResumoDoPeriodo:
            if dia is not None:
                inicio, fim, horas = self._trecho(origem, momento, dia)
                ritmo = {Origem.PRODUCAO_TS: 3.4, Origem.PRODUCAO_PY: 1.9, Origem.RELEASE: 0.32}[origem]
                comecaram = int(horas * ritmo * self._sorteio("periodo", origem, dia).uniform(0.7, 1.3))
                return ResumoDoPeriodo(inicio, fim, comecaram, int(comecaram * 0.78), int(comecaram * 5.4), 0)
            if origem is Origem.PRODUCAO_TS:
                return ResumoDoPeriodo(_h(16, 10, 0, 0), CORTE_DE_VERSAO, 610, 489, 3_439, 0)
            if origem is Origem.PRODUCAO_PY:
                horas = (momento - CORTE_DE_VERSAO).total_seconds() / 3600
                comecaram = int(horas * 1.9)
                return ResumoDoPeriodo(CORTE_DE_VERSAO, momento, comecaram, int(comecaram * 0.78), int(comecaram * 5.4), 0)
            return ResumoDoPeriodo(momento - timedelta(days=7), momento, 54, 10, 68, 0)

        return self._ler(fontes.fonte_resumo_do_periodo(origem, dia), gerar)

    def nao_encontrado(self, origem: Origem, dia: date | None = None) -> Leitura[list[TrechoDeNaoEncontrado]]:
        def gerar(momento: datetime) -> list[TrechoDeNaoEncontrado]:
            if dia is not None:
                _, _, horas = self._trecho(origem, momento, dia)
                if not horas:
                    return []
                encerramentos = int(horas * 1.9 * 0.78)
                recusadas = _recusas_do_incidente(dia, int(encerramentos * 1.4)) if AMBIENTE_DA_ORIGEM[origem] is Ambiente.PRODUCAO else 0
                nao_achou = encerramentos if recusadas else int(encerramentos * 0.19)
                aceitas = 0 if recusadas else int(encerramentos * 1.4)
                rotulo = f"Em {dia:%d/%m}, das {dia.hour}h às {dia.hour + 1}h" if isinstance(dia, datetime) else f"Em {dia:%d/%m}"
                return [TrechoDeNaoEncontrado(rotulo, encerramentos, nao_achou, ResultadoDoVerde(aceitas, recusadas, 0, nao_achou))]
            if origem is Origem.PRODUCAO_TS:
                return [
                    TrechoDeNaoEncontrado("Antes do incidente, 16 a 22/10", 414, 87, ResultadoDoVerde(912, 33, 4, 97)),
                    TrechoDeNaoEncontrado("Durante o incidente, 22 e 23/10", 75, 75, ResultadoDoVerde(0, 283, 6, 0)),
                ]
            if origem is Origem.PRODUCAO_PY:
                horas = (momento - CORTE_DE_VERSAO).total_seconds() / 3600
                encerramentos = int(horas * 1.9 * 0.78)
                return [
                    TrechoDeNaoEncontrado(
                        "Desde a troca de versão",
                        encerramentos,
                        int(encerramentos * 0.19),
                        ResultadoDoVerde(int(encerramentos * 1.4), 0, 1, int(encerramentos * 0.2)),
                    )
                ]
            return [TrechoDeNaoEncontrado("Últimos 7 dias", 10, 1, ResultadoDoVerde(12, 27, 0, 2))]

        return self._ler(fontes.fonte_nao_encontrado(origem), gerar)

    def orquestrador(self, origem: Origem, dia: date | None = None) -> Leitura[ResumoDoOrquestrador]:
        # Produção não chama o orquestrador hoje (levantamento de 23/10): vazio.
        p = self._parte(dia, "orquestrador")
        return self._ler(
            fontes.fonte_orquestrador(),
            lambda _: ResumoDoOrquestrador(int(59 * p), int(68 * p), int(31 * p), int(28 * p)) if origem is Origem.RELEASE else None,
        )

    # ── Relatório do dia ──────────────────────────────────────────────────

    def sistema_no_dia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[SistemaNoDia]:
        def gerar(momento: datetime) -> SistemaNoDia:
            escolhido = _o_dia(dia) if dia else momento.date()
            if ambiente is Ambiente.PRODUCAO:
                reinicios = [SUBIDA_DA_PRODUCAO] if escolhido == SUBIDA_DA_PRODUCAO.date() else []
            elif escolhido < momento.date():
                reinicio = datetime.combine(escolhido, datetime.min.time(), tzinfo=FUSO) + timedelta(hours=self._sorteio("subida", escolhido).randint(9, 17))
                reinicios = [reinicio] if escolhido.weekday() < 5 else []
            else:
                reinicio = (momento - timedelta(hours=5, minutes=12)).replace(second=0, microsecond=0)
                reinicios = [reinicio] if reinicio.date() == momento.date() else []
            if isinstance(dia, datetime):
                # A hora escolhida: só o que caiu nela.
                reinicios = [r for r in reinicios if dia <= r < dia + timedelta(hours=1)]
            return SistemaNoDia(minutos_fora_do_ar=0, reinicios=reinicios, erros_de_servidor=0, subidas=len(reinicios))

        return self._ler(fontes.fonte_sistema_no_dia(ambiente, dia), gerar)

    # ── Coluna da direita das telas ───────────────────────────────────────

    def atendimentos_por_hora(self, ambiente: Ambiente, dia: date) -> Leitura[list[ContagemPorHora]]:
        dia = _o_dia(dia)

        def gerar(momento: datetime) -> list[ContagemPorHora]:
            horas = []
            for h in range(24):
                hora = datetime.combine(dia, datetime.min.time(), tzinfo=FUSO) + timedelta(hours=h)
                if hora > momento:
                    break
                sorteio = self._sorteio("hora", ambiente, hora)
                pico = 1.0 if 9 <= h <= 15 else 0.4 if 7 <= h <= 19 else 0.05
                base = 12 if ambiente is Ambiente.PRODUCAO and dia.weekday() < 5 else 2
                comecaram = int(sorteio.randint(0, base) * pico)
                horas.append(ContagemPorHora(hora, comecaram, int(comecaram * 0.8)))
            return horas

        return self._ler(fontes.fonte_atendimentos_por_hora(ambiente), gerar)

    def atendimentos_por_dia(self, ambiente: Ambiente) -> Leitura[list[ContagemPorDia]]:
        def gerar(momento: datetime) -> list[ContagemPorDia]:
            dias = [momento.date() - timedelta(days=n) for n in range(fontes.DIAS_DO_REGISTRO - 1, -1, -1)]
            return [ContagemPorDia(d, (r := self._resumo(ambiente, d, momento)).comecaram, r.terminaram) for d in dias]

        return self._ler(fontes.fonte_atendimentos_por_dia(ambiente), gerar)

    def _desfechos(self, *chave: object) -> list[Desfecho]:
        sorteio = self._sorteio("desfechos", *chave)
        return [
            Desfecho("origem_processo_nao_suportada", sorteio.randint(20, 35)),
            Desfecho("sem_numero_processo", sorteio.randint(8, 22)),
            Desfecho("rg_nao_encontrado", sorteio.randint(6, 16)),
            Desfecho("", sorteio.randint(5, 15)),
            Desfecho("falha_infra_verde", sorteio.randint(0, 7)),
            Desfecho("dados_pessoa_nao_atendidos", sorteio.randint(0, 3)),
        ]

    def desfechos(self, origem: Origem, dia: date | None = None) -> Leitura[list[Desfecho]]:
        def gerar(momento: datetime) -> list[Desfecho]:
            if dia is None:
                return self._desfechos(origem)
            return self._desfechos(origem, dia) if self._trecho(origem, momento, dia)[2] else []

        return self._ler(fontes.fonte_desfechos(AMBIENTE_DA_ORIGEM[origem]), gerar)

    def desfechos_do_dia(self, ambiente: Ambiente, dia: date) -> Leitura[list[Desfecho]]:
        def gerar(momento: datetime) -> list[Desfecho]:
            if _o_dia(dia) > momento.date():
                return []
            # A hora escolhida: a fatia dela no dia; os motivos que somem dela saem da lista.
            fatia = _fatia_da_hora(dia) * 3 if isinstance(dia, datetime) else 1.0
            return [Desfecho(d.motivo, int(d.atendimentos * fatia)) for d in self._desfechos(ambiente, dia) if int(d.atendimentos * fatia)]

        return self._ler(fontes.fonte_desfechos(ambiente), gerar)

    def origem_nao_atendida(self, origem: Origem, dia: date | None = None) -> Leitura[OrigemNaoAtendida]:
        # Os números do levantamento de 26/10, nos 30 dias de produção.
        p = self._parte(dia, "origem", origem, de=30)
        o = OrigemNaoAtendida(*(int(n * p) for n in (1_840, 808, 496, 304, 3)))
        return self._ler(fontes.fonte_origem_nao_atendida(AMBIENTE_DA_ORIGEM[origem]), lambda _: o if o.finalizados else None)

    def requisicoes_por_hora(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[RequisicoesPorHora]]:
        # Com a hora escolhida, o gráfico ainda mostra o dia inteiro, com a hora em destaque.
        dia = _o_dia(dia) if dia is not None else None

        def gerar(momento: datetime) -> list[RequisicoesPorHora]:
            if dia is None:
                inicio = momento.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
            else:
                inicio = datetime.combine(dia, datetime.min.time(), tzinfo=FUSO)
            horas = [h for h in (inicio + timedelta(hours=n) for n in range(24)) if h <= momento]
            return [RequisicoesPorHora(h, self._sorteio("req", ambiente, h).randint(20, 260), 0) for h in horas]

        return self._ler(fontes.fonte_requisicoes_por_hora(ambiente, dia), gerar)

    def recursos_do_servico(self, ambiente: Ambiente) -> Leitura[RecursosDoServico]:
        return self._ler(fontes.fonte_recursos_do_servico(ambiente), lambda _: RecursosDoServico(0.08, 0.41, 0.52, 0.61))

    def cpu_e_latencia(self, dia: date | None = None) -> Leitura[list[CpuELatencia]]:
        # Como em produção: CPU abaixo de 1%, e o p99 quase sempre baixo, com uma hora ruim
        # (consulta lenta ao Verde) que passa do limite do alerta.
        dia = _o_dia(dia) if dia is not None else None

        def gerar(momento: datetime) -> list[CpuELatencia]:
            if dia is None:
                inicio = momento.replace(minute=0, second=0, microsecond=0) - timedelta(hours=23)
            else:
                inicio = datetime.combine(dia, datetime.min.time(), tzinfo=FUSO)
            horas = [h for h in (inicio + timedelta(hours=n) for n in range(24)) if h <= momento]
            linhas = []
            for ambiente in Ambiente:
                for h in horas:
                    sorteio = self._sorteio("cpu", ambiente, h)
                    p99 = 9.9 if ambiente is Ambiente.PRODUCAO and h.hour == 14 else sorteio.uniform(0.2, 1.6)
                    linhas.append(CpuELatencia(h, ambiente, round(sorteio.uniform(0.3, 0.9), 2), round(p99, 3)))
            return linhas

        return self._ler(fontes.fonte_cpu_e_latencia(dia), gerar)

    def horarios_da_conferencia(self) -> Leitura[list[HorarioDaConferencia]]:
        def gerar(momento: datetime) -> list[HorarioDaConferencia]:
            dias = [momento.date() - timedelta(days=n) for n in range(29, -1, -1)]
            return [
                HorarioDaConferencia(
                    d,
                    datetime.combine(d, datetime.min.time(), tzinfo=FUSO) + timedelta(minutes=self._sorteio("conf", d).randint(553, 730)),
                    d > date(2026, 10, 22),
                )
                for d in dias
            ]

        return self._ler(fontes.fonte_horarios_da_conferencia(), gerar)

    def verde_do_mes(self, ambiente: Ambiente) -> Leitura[list[DiaDoVerde]]:
        def gerar(momento: datetime) -> list[DiaDoVerde]:
            dias = [momento.date() - timedelta(days=n) for n in range(29, -1, -1)]
            resultado = []
            for dia in dias:
                total = (
                    self._sorteio("verde30", ambiente, dia).randint(40, 70) if dia.weekday() >= 5 else self._sorteio("verde30", ambiente, dia).randint(150, 210)
                )
                if ambiente is Ambiente.RELEASE:
                    total //= 30
                recusadas = _recusas_do_incidente(dia, total) if ambiente is Ambiente.PRODUCAO else 0
                nao_achou, sem_resposta, erro = _o_resto_do_verde(self._sorteio("resto30", ambiente, dia), total)
                outras = nao_achou + sem_resposta + erro
                resultado.append(DiaDoVerde(dia, max(total - recusadas - outras, 0), recusadas, outras, nao_achou, sem_resposta))
            return resultado

        return self._ler(fontes.fonte_verde_do_mes(ambiente), gerar)

    # ── Observatório da IA ────────────────────────────────────────────────

    def erros_da_ia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[ErroDaIA]]:
        # A única falha medida: um "extrair" em 21/10.
        falhou = dia is None or dia == date(2026, 10, 21)
        return self._ler(
            fontes.fonte_erros_da_ia(ambiente, dia),
            lambda _: [ErroDaIA(f, n) for f, n in (("classificar", 0), ("desambiguar", 0), ("extrair", int(falhou)), ("reescrever", 0), ("sumarizar", 0))],
        )

    def uso_da_ia(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[UsoDaIA]:
        perguntas = int(1_620 * self._parte(dia, "uso", ambiente))
        return self._ler(fontes.fonte_uso_da_ia(ambiente, dia), lambda _: UsoDaIA(perguntas, 0) if perguntas else None)

    def saude_do_modelo(self) -> Leitura[list[DiaDoModelo]]:
        def gerar(momento: datetime) -> list[DiaDoModelo]:
            resultado = []
            for n in range(13, -1, -1):
                dia = momento.date() - timedelta(days=n)
                lido, escrito, chamadas = self._tokens_do_dia(dia, momento)
                resultado.append(DiaDoModelo(dia, chamadas, 0, 0, 0, 1.4, escrito / chamadas if chamadas else 0.0))
            return resultado

        return self._ler(fontes.fonte_saude_do_modelo(), gerar)

    def mudancas_na_ia(self) -> Leitura[list[MudancaNaIA]]:
        return self._ler(
            fontes.fonte_mudancas_na_ia(),
            lambda _: [
                MudancaNaIA(_h(19, 10, 16, 2), "migração do módulo ia para Python (simulado)", "0000001"),
                MudancaNaIA(_h(14, 10, 11, 40), "issue #212: lista de parentescos (simulado)", "0000002"),
            ],
        )

    # ── Fluxos ────────────────────────────────────────────────────────────
    # Na ordem de grandeza do levantamento de 28/10: produção só com pessoa presa,
    # cerca de 90 conversas por dia; o release com os três fluxos e a triagem.

    def _fluxos(self, ambiente: Ambiente) -> dict[str, float]:
        """Os fluxos de um ambiente e quantas conversas cada um começa por dia."""
        if ambiente is Ambiente.PRODUCAO:
            return {PESSOA_PRESA: 90.0}
        return {PESSOA_PRESA: 1.6, VIOLENCIA_DOMESTICA: 0.8, PLANO_DE_SAUDE: 1.4}

    def _dias(self, dia: date | None) -> float:
        """Quantos dias a janela tem: 7, um dia, ou a fatia da hora escolhida."""
        return float(fontes.DIAS_DOS_FLUXOS) if dia is None else _fatia_da_hora(dia) * 1.0

    def conversas_por_fluxo(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[ConversasDoFluxo]]:
        def gerar(_: datetime) -> list[ConversasDoFluxo] | None:
            resultado: list[ConversasDoFluxo] = []
            for fluxo, por_dia in self._fluxos(ambiente).items():
                sorteio = self._sorteio("conversas", ambiente, fluxo, dia)
                total = por_dia * self._dias(dia)
                # Param mais na terceira pergunta, a do número do processo: o ponto em que o fluxo trava.
                partes = {
                    FimDaConversa.ENCAMINHOU: (0.70, range(4, 15)),
                    FimDaConversa.CONCLUIU: (0.12, range(8, 13)),
                    FimDaConversa.PAROU: (0.17, (0, 1, 2, 3, 3, 3, 4, 5, 7)),
                    FimDaConversa.EXPIROU: (0.01, (1, 2)),
                }
                for fim, (parte, respostas) in partes.items():
                    contagem: dict[int, int] = {}
                    for _conversa in range(int(total * parte)):
                        r = sorteio.choice(list(respostas))
                        contagem[r] = contagem.get(r, 0) + 1
                    resultado += [ConversasDoFluxo(fluxo, r, fim, n) for r, n in sorted(contagem.items())]
            return resultado or None

        return self._ler(fontes.fonte_conversas_por_fluxo(ambiente, dia), gerar)

    def desfechos_por_fluxo(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DesfechoDoFluxo]]:
        motivos = {
            PESSOA_PRESA: {
                "origem_processo_nao_suportada": 0.39,
                "rg_nao_encontrado": 0.29,
                "sem_numero_processo": 0.14,
                "": 0.13,
                "dados_pessoa_nao_atendidos": 0.04,
                "nome_nao_confirmado": 0.01,
                "falha_infra_verde": 0.01,
            },
            VIOLENCIA_DOMESTICA: {"falha_infra_verde": 0.6, "nao_e_vitima": 0.4},
            PLANO_DE_SAUDE: {"": 0.35, "municipio_nao_identificado": 0.25, "situacao_nao_informada": 0.1, "fora_do_rio": 0.1, "renda_nao_entendida": 0.2},
        }

        def gerar(_: datetime) -> list[DesfechoDoFluxo] | None:
            resultado = []
            for fluxo, por_dia in self._fluxos(ambiente).items():
                terminaram = por_dia * 0.83 * self._dias(dia)
                for motivo, parte in motivos[fluxo].items():
                    n = int(terminaram * parte)
                    if n:
                        resultado.append(DesfechoDoFluxo(fluxo, motivo, "" if not motivo else "atendimento_humano", n))
            return resultado or None

        return self._ler(fontes.fonte_desfechos_por_fluxo(ambiente, dia), gerar)

    def triagem(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[RodadaDaTriagem]]:
        # Produção não chama a triagem por escrita livre: vazio. No release, os 30 dias medidos em 28/10.
        medidos = [
            (SaidaDaTriagem.IDENTIFICOU, PESSOA_PRESA, 51),
            (SaidaDaTriagem.IDENTIFICOU, VIOLENCIA_DOMESTICA, 23),
            (SaidaDaTriagem.REDIRECIONOU, "novo-processo", 22),
            (SaidaDaTriagem.REDIRECIONOU, "saude", 15),
            (SaidaDaTriagem.REDIRECIONOU, "ajuda-app", 9),
            (SaidaDaTriagem.REDIRECIONOU, "andamento-processo", 9),
            (SaidaDaTriagem.REDIRECIONOU, "agendamentos", 7),
            (SaidaDaTriagem.REDIRECIONOU, "sair", 7),
            (SaidaDaTriagem.SEM_FLUXO, "outros", 32),
            (SaidaDaTriagem.PERGUNTOU, "", 28),
            (SaidaDaTriagem.INCONSISTENCIA, "atendimento_humano", 1),
        ]

        def gerar(_: datetime) -> list[RodadaDaTriagem] | None:
            if ambiente is Ambiente.PRODUCAO:
                return None
            escala = self._dias(dia) / 30 * (self._sorteio("triagem", dia).uniform(0.6, 1.4) if dia else 1.0)
            rodadas = [RodadaDaTriagem(saida, alvo, round(n * escala)) for saida, alvo, n in medidos]
            return [r for r in rodadas if r.vezes] or None

        return self._ler(fontes.fonte_triagem(ambiente, dia), gerar)

    def fluxos_por_dia(self, ambiente: Ambiente) -> Leitura[list[FluxoNoDia]]:
        def gerar(momento: datetime) -> list[FluxoNoDia]:
            hoje = momento.date()
            resultado = []
            for n in range(fontes.DIAS_DO_REGISTRO - 1, -1, -1):
                d = hoje - timedelta(days=n)
                for fluxo, por_dia in self._fluxos(ambiente).items():
                    sorteio = self._sorteio("fluxo-dia", ambiente, fluxo, d)
                    semana = 1.0 if d.weekday() < 5 else 0.35
                    comecaram = int(por_dia * semana * sorteio.uniform(0.6, 1.4) * _parte_do_dia(d, momento))
                    terminaram = int(comecaram * 0.83)
                    resultado.append(FluxoNoDia(d, fluxo, comecaram, terminaram, int(terminaram * 0.85)))
            return resultado

        return self._ler(fontes.fonte_fluxos_por_dia(ambiente), gerar)

    def problemas_por_dia(self, ambiente: Ambiente) -> Leitura[list[ProblemaNoDia]]:
        def gerar(momento: datetime) -> list[ProblemaNoDia] | None:
            hoje = momento.date()
            resultado = []
            for n in range(fontes.DIAS_DO_REGISTRO - 1, -1, -1):
                d = hoje - timedelta(days=n)
                sorteio = self._sorteio("problemas", ambiente, d)
                if ambiente is Ambiente.PRODUCAO:
                    vezes = {("falha_infra_verde", PESSOA_PRESA): sorteio.choice((0, 0, 0, 1, 2))}
                    if d == date(2026, 10, 23):
                        # As 5 conversas cortadas na troca de versão (levantamento de 23/10).
                        vezes[("atendimento_sem_checkpoint", PESSOA_PRESA)] = 5
                else:
                    vezes = {
                        ("falha_infra_verde", VIOLENCIA_DOMESTICA): sorteio.choice((0, 0, 0, 1)),
                        ("whatsapp_status_entrega", ""): sorteio.choice((0, 0, 0, 0, 1, 2)),
                        ("whatsapp_envio_falhou", ""): sorteio.choice((0, 0, 0, 0, 0, 1)),
                    }
                resultado += [ProblemaNoDia(d, problema, fluxo, v) for (problema, fluxo), v in vezes.items() if v]
            return resultado or None

        return self._ler(fontes.fonte_problemas_por_dia(ambiente), gerar)

    def encaminhamentos_por_dia(self, ambiente: Ambiente) -> Leitura[list[EncaminhamentoNoDia]]:
        # Por fluxo: a parte que a Maria resolve sozinha, a que expira e os motivos de quem vai para pessoa.
        partes = {
            PESSOA_PRESA: (
                0.12,
                0.03,
                {
                    "origem_processo_nao_suportada": 0.39,
                    "rg_nao_encontrado": 0.29,
                    "sem_numero_processo": 0.14,
                    "": 0.08,
                    "dados_pessoa_nao_atendidos": 0.04,
                    "nome_nao_confirmado": 0.02,
                    "falha_infra_verde": 0.03,
                    "falha_cadastro": 0.01,
                },
            ),
            VIOLENCIA_DOMESTICA: (0.45, 0.05, {"falha_infra_verde": 0.3, "nao_e_vitima": 0.4, "cpf_nao_encontrado": 0.2, "sem_orgao_disponivel": 0.1}),
            PLANO_DE_SAUDE: (
                0.35,
                0.05,
                {"municipio_nao_identificado": 0.3, "situacao_nao_informada": 0.15, "fora_do_rio": 0.15, "renda_nao_entendida": 0.25, "outra_pessoa": 0.15},
            ),
        }

        def gerar(momento: datetime) -> list[EncaminhamentoNoDia] | None:
            hoje = momento.date()
            resultado = []
            for n in range(fontes.DIAS_DO_REGISTRO - 1, -1, -1):
                d = hoje - timedelta(days=n)
                semana = 1.0 if d.weekday() < 5 else 0.35
                for fluxo, por_dia in self._fluxos(ambiente).items():
                    sorteio = self._sorteio("encaminhamentos", ambiente, fluxo, d)
                    terminaram = por_dia * 0.83 * semana * sorteio.uniform(0.6, 1.4) * _parte_do_dia(d, momento)
                    ia, saiu, motivos = partes[fluxo]
                    resultado.append(EncaminhamentoNoDia(d, fluxo, Destino.IA, "", int(terminaram * ia)))
                    resultado.append(EncaminhamentoNoDia(d, fluxo, Destino.SAIU, "", int(terminaram * saiu)))
                    humano = terminaram * (1 - ia - saiu)
                    resultado += [EncaminhamentoNoDia(d, fluxo, Destino.HUMANO, m, int(humano * p * sorteio.uniform(0.7, 1.3))) for m, p in motivos.items()]
                if ambiente is Ambiente.RELEASE:
                    # A triagem que não acha o assunto manda direto para pessoa (levantamento de 28/10: 32 em 30 dias).
                    resultado.append(EncaminhamentoNoDia(d, "", Destino.HUMANO, "triagem_sem_fluxo", self._sorteio("triagem-humano", d).choice((0, 1, 1, 2))))
            return [e for e in resultado if e.atendimentos] or None

        return self._ler(fontes.fonte_encaminhamentos(ambiente), gerar)

    def duracao_das_conversas(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[DuracaoDasConversas]]:
        # As partes medidas em produção nos 7 dias até 28/10.
        partes = {"ate2": 0.24, "ate5": 0.47, "ate15": 0.19, "ate60": 0.06, "mais": 0.04}

        def gerar(_: datetime) -> list[DuracaoDasConversas] | None:
            resultado = []
            for fluxo, por_dia in self._fluxos(ambiente).items():
                terminaram = por_dia * 0.83 * self._dias(dia)
                resultado += [DuracaoDasConversas(fluxo, faixa, int(terminaram * parte)) for faixa, parte in partes.items() if int(terminaram * parte)]
            return resultado or None

        return self._ler(fontes.fonte_duracao_das_conversas(ambiente, dia), gerar)

    def envios_do_whatsapp(self, ambiente: Ambiente, dia: date | None = None) -> Leitura[list[EnvioDoWhatsapp]]:
        # Só o release manda pelo WhatsApp direto; os 30 dias medidos em 28/10.
        medidos = [
            ("whatsapp_envio_ok", "", 10),
            ("whatsapp_status_entrega", "130497", 6),
            ("whatsapp_envio_falhou", "400", 2),
            ("whatsapp_envio_falhou", "401", 1),
        ]

        def gerar(_: datetime) -> list[EnvioDoWhatsapp] | None:
            if ambiente is Ambiente.PRODUCAO:
                return None
            envios = [EnvioDoWhatsapp(evento, codigo, round(n * self._dias(dia) / 30 * 3)) for evento, codigo, n in medidos]
            return [e for e in envios if e.vezes] or None

        return self._ler(fontes.fonte_envios_do_whatsapp(ambiente, dia), gerar)


def _o_resto_do_verde(sorteio: random.Random, total: int) -> tuple[int, int, int]:
    """Processo que não existe, consulta que não voltou e erro do Verde, nas
    partes do levantamento de 28/10 em produção: cerca de 9%, 3% e 2%."""
    return (int(total * sorteio.uniform(0.06, 0.12)), int(total * sorteio.uniform(0.01, 0.05)), int(total * sorteio.uniform(0.0, 0.03)))


def _o_dia(dia: date) -> date:
    """O dia de um `dia` que pode ser o começo da hora escolhida (um `datetime`)."""
    return dia.astimezone(FUSO).date() if isinstance(dia, datetime) else dia


def _fatia_da_hora(dia: date | None) -> float:
    """1 sem a hora escolhida; com ela, a parte do dia que cai nela (das 7h às 19h)."""
    if not isinstance(dia, datetime):
        return 1.0
    return 1 / 12 if 7 <= dia.astimezone(FUSO).hour < 19 else 0.0


def _recusas_do_incidente(dia: date, total: int) -> int:
    """As recusas de produção do levantamento: 33 em 20/10 (54 minutos) e o
    incidente de 22 e 23/10 (23 horas, até 12:34 do dia 23)."""
    dia = _o_dia(dia)
    if dia == date(2026, 10, 20):
        return min(33, total)
    if dia == date(2026, 10, 22):
        return int(total * 0.45)
    if dia == date(2026, 10, 23):
        return int(total * 0.4)
    return 0


def _parte_do_dia(dia: date, momento: datetime) -> float:
    """Hoje só conta até agora: das 7h às 19h, a fração do dia útil que passou."""
    if dia != momento.date():
        return 1.0
    return min(max(momento.hour - 7, 0), 12) / 12
