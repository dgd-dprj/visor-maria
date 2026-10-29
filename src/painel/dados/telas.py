"""O que cada tela lê numa rodada, lido uma vez só.

Na fonte real, cada leitura é uma consulta paga (Logs Insights cobra pelo que
varre). Juntar aqui o que a tela precisa evita que dois quadros façam a mesma
consulta. Fica fora de `pages/` porque o Dash carrega as telas sem registrá-las
em `sys.modules`, o que quebra dataclasses declaradas lá.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any

from painel import gasto
from painel.dados import obter_fonte
from painel.dados.fontes import DIAS_DO_REGISTRO
from painel.dados.modelo import (
    AMBIENTE_DA_ORIGEM,
    FUSO,
    Ambiente,
    Assunto,
    ContagemPorDia,
    ConversasDoFluxo,
    CpuELatencia,
    Credencial,
    Desfecho,
    DesfechoDoFluxo,
    DiaDoModelo,
    DiaDoVerde,
    DuracaoDasConversas,
    DuracaoDoVerde,
    EncaminhamentoNoDia,
    EnvioDoWhatsapp,
    ErroDaIA,
    FluxoNoDia,
    GastoDeIA,
    GastoDoAssunto,
    IncidenteDeCredencial,
    Leitura,
    MudancaNaIA,
    Origem,
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
    SaudeServico,
    SistemaNoDia,
    TempoDeResposta,
    TokensDoDia,
    TokensRegistrados,
    TrechoDeNaoEncontrado,
    UsoDaIA,
    juntar,
)
from painel.periodo import Escolha, Periodo

# Na fonte real, cada leitura é uma consulta de alguns segundos: em fila, uma
# tela fria levaria um minuto. As leituras de uma tela vão juntas, até 8 por vez,
# abaixo do limite de consultas simultâneas do Logs Insights da conta (30, divididas
# entre todo mundo que roda o painel).
_LEITURAS = ThreadPoolExecutor(max_workers=8, thread_name_prefix="leitura")


def ler_ja[T](chamada: Callable[[], T]) -> Future[T]:
    return _LEITURAS.submit(chamada)


# A coluna da direita é montada junto com o corpo da tela, e não depois dele. Fica
# num conjunto à parte: uma montagem espera as suas leituras, e no mesmo conjunto
# das leituras as duas poderiam ficar esperando uma pela outra.
_MONTAGENS = ThreadPoolExecutor(max_workers=8, thread_name_prefix="montagem")


def montar_ja[T](chamada: Callable[[], T]) -> Future[T]:
    return _MONTAGENS.submit(chamada)


# Ao abrir uma tela, os dias que já passaram no gráfico dela são lidos por trás:
# o clique num dia encontra a leitura pronta, em vez de esperar a consulta. Dia
# fechado fica guardado sem prazo, então cada um é lido uma vez só. Dois por vez,
# para não disputar o Logs Insights com a tela aberta.
_PREPARO = ThreadPoolExecutor(max_workers=2, thread_name_prefix="preparo")
_preparados: set[tuple[Any, ...]] = set()
_trava_do_preparo = threading.Lock()


def preparar(consulta: str, *argumentos: Any) -> None:
    """Lê por trás, uma vez por processo, uma consulta de um dia que já passou."""
    fonte = obter_fonte()
    chave = (fonte.nome, consulta, *argumentos)
    with _trava_do_preparo:
        if chave in _preparados:
            return
        _preparados.add(chave)
    _PREPARO.submit(getattr(fonte, consulta), *argumentos)


def dias_passados(quantos: int, agora: datetime) -> list[date]:
    """Os dias antes de hoje num gráfico de `quantos` dias, do mais novo ao mais velho."""
    hoje = agora.astimezone(FUSO).date()
    return [hoje - timedelta(days=n) for n in range(1, quantos)]


@dataclass(frozen=True)
class LeiturasDaAgora:
    agora: datetime
    # O dia escolhido num gráfico da tela (ou o começo da hora escolhida); None é hoje.
    dia: date | None
    resumo: Leitura[ResumoDoDia]
    credenciais: dict[Ambiente, Leitura[Credencial]]
    verde: dict[Ambiente, Leitura[list[DiaDoVerde]]]
    rotinas: Leitura[list[Rotina]]
    saude: dict[Ambiente, Leitura[SaudeServico]]
    implantacoes: dict[Ambiente, Leitura[int]]
    reinicio: dict[Ambiente, Leitura[datetime]]
    # O ambiente do filtro da tela, e o que só ele mostra.
    ambiente: Ambiente = Ambiente.PRODUCAO
    tempo: Leitura[TempoDeResposta] | None = None
    erros: Leitura[RespostasComErro] | None = None
    pedidos: Leitura[list[RequisicoesPorHora]] | None = None
    fluxos: Leitura[list[ConversasDoFluxo]] | None = None
    desfechos: Leitura[list[Desfecho]] | None = None
    sistema: Leitura[SistemaNoDia] | None = None
    incidentes: Leitura[list[IncidenteDeCredencial]] | None = None
    renovacoes: Leitura[list[Renovacao]] | None = None
    # O caminho do atendimento: a triagem, as funções de IA e o envio pelo WhatsApp, no dia.
    triagem: Leitura[list[RodadaDaTriagem]] | None = None
    erros_da_ia: Leitura[list[ErroDaIA]] | None = None
    envios: Leitura[list[EnvioDoWhatsapp]] | None = None

    def todas(self) -> list[Leitura[Any]]:
        leituras: list[Leitura[Any]] = [self.resumo, self.rotinas]
        for por_ambiente in (self.credenciais, self.verde, self.saude, self.implantacoes, self.reinicio):
            leituras += por_ambiente.values()
        extras = (
            self.tempo,
            self.erros,
            self.pedidos,
            self.fluxos,
            self.desfechos,
            self.sistema,
            self.incidentes,
            self.renovacoes,
            self.triagem,
            self.erros_da_ia,
            self.envios,
        )
        return leituras + [x for x in extras if x is not None]


@dataclass(frozen=True)
class LeiturasDaCredencial:
    agora: datetime
    credenciais: dict[Ambiente, Leitura[Credencial]]
    incidentes: Leitura[list[IncidenteDeCredencial]]
    renovacoes: Leitura[list[Renovacao]]

    def todas(self) -> list[Leitura[Any]]:
        return [*self.credenciais.values(), self.incidentes, self.renovacoes]


def ler_credencial() -> LeiturasDaCredencial:
    fonte = obter_fonte()
    credenciais = {a: ler_ja(partial(fonte.credencial, a)) for a in Ambiente}
    incidentes, renovacoes = ler_ja(fonte.incidentes_de_credencial), ler_ja(fonte.renovacoes)
    return LeiturasDaCredencial(
        agora=datetime.now(FUSO),
        credenciais={a: f.result() for a, f in credenciais.items()},
        incidentes=incidentes.result(),
        renovacoes=renovacoes.result(),
    )


@dataclass(frozen=True)
class LeiturasDoSistema:
    agora: datetime
    dia: date | None
    tempo: Leitura[TempoDeResposta]
    duracao_do_verde: Leitura[list[DuracaoDoVerde]]
    resultado_do_verde: Leitura[ResultadoDoVerde]
    erros: Leitura[RespostasComErro]
    tokens: Leitura[list[TokensDoDia]]
    rotinas: Leitura[list[Rotina]]
    # Cada parte da arquitetura: os containers, o balanceador, o banco, o modelo, o WhatsApp e o gasto do dia.
    ambiente: Ambiente = Ambiente.PRODUCAO
    saude: Leitura[SaudeServico] | None = None
    recursos: Leitura[RecursosDoServico] | None = None
    pedidos: Leitura[list[RequisicoesPorHora]] | None = None
    modelo: Leitura[list[DiaDoModelo]] | None = None
    erros_da_ia: Leitura[list[ErroDaIA]] | None = None
    envios: Leitura[list[EnvioDoWhatsapp]] | None = None
    credencial: Leitura[Credencial] | None = None
    resumo: Leitura[ResumoDoDia] | None = None
    gasto: Leitura[GastoDeIA] | None = None
    # A CPU e a latência p99 dos dois ambientes, hora a hora (o que o Grafana mostrava).
    cpu_e_latencia: Leitura[list[CpuELatencia]] | None = None

    def todas(self) -> list[Leitura[Any]]:
        leituras: list[Leitura[Any]] = [self.tempo, self.duracao_do_verde, self.resultado_do_verde, self.erros, self.tokens, self.rotinas]
        extras = (
            self.saude,
            self.recursos,
            self.pedidos,
            self.modelo,
            self.erros_da_ia,
            self.envios,
            self.credencial,
            self.resumo,
            self.gasto,
            self.cpu_e_latencia,
        )
        return leituras + [x for x in extras if x is not None]


def ler_sistema(ambiente: Ambiente, dia: date | None = None) -> LeiturasDoSistema:
    fonte = obter_fonte()
    tempo, duracao = ler_ja(partial(fonte.tempo_de_resposta, ambiente, dia)), ler_ja(partial(fonte.duracao_do_verde, ambiente, dia))
    resultado, erros = ler_ja(partial(fonte.resultado_do_verde, ambiente, dia)), ler_ja(partial(fonte.respostas_com_erro, ambiente, dia))
    tokens, rotinas = ler_ja(fonte.tokens_por_dia), ler_ja(fonte.rotinas)
    # O dia da leitura (com a hora escolhida, o dia dela), ou hoje: o gasto é contado por dia.
    no_dia = (dia.astimezone(FUSO).date() if isinstance(dia, datetime) else dia) or datetime.now(FUSO).date()
    saude, recursos = ler_ja(partial(fonte.saude_servico, ambiente)), ler_ja(partial(fonte.recursos_do_servico, ambiente))
    pedidos, modelo = ler_ja(partial(fonte.requisicoes_por_hora, ambiente, dia)), ler_ja(fonte.saude_do_modelo)
    erros_da_ia, envios = ler_ja(partial(fonte.erros_da_ia, ambiente, dia or no_dia)), ler_ja(partial(fonte.envios_do_whatsapp, ambiente, dia or no_dia))
    credencial, resumo = ler_ja(partial(fonte.credencial, ambiente)), ler_ja(partial(fonte.resumo_do_dia, ambiente, dia))
    gasto_do_dia = ler_ja(partial(fonte.gasto_do_dia, no_dia))
    # Com a hora escolhida, o gráfico mostra o dia inteiro, com a hora em destaque.
    cpu_e_latencia = ler_ja(partial(fonte.cpu_e_latencia, no_dia if dia is not None else None))
    return LeiturasDoSistema(
        agora=datetime.now(FUSO),
        dia=dia,
        tempo=tempo.result(),
        duracao_do_verde=duracao.result(),
        resultado_do_verde=resultado.result(),
        erros=erros.result(),
        tokens=tokens.result(),
        rotinas=rotinas.result(),
        ambiente=ambiente,
        saude=saude.result(),
        recursos=recursos.result(),
        pedidos=pedidos.result(),
        modelo=modelo.result(),
        erros_da_ia=erros_da_ia.result(),
        envios=envios.result(),
        credencial=credencial.result(),
        resumo=resumo.result(),
        gasto=gasto_do_dia.result(),
        cpu_e_latencia=cpu_e_latencia.result(),
    )


@dataclass(frozen=True)
class LeiturasDoAtendimento:
    agora: datetime
    origem: Origem
    dia: date | None
    resumo: Leitura[ResumoDoPeriodo]
    nao_encontrado: Leitura[list[TrechoDeNaoEncontrado]]
    orquestrador: Leitura[ResumoDoOrquestrador]
    # O gráfico em que se escolhe o dia: o ambiente da origem, dia a dia.
    por_dia: Leitura[list[ContagemPorDia]]
    # Como terminaram, para o filtro por motivo.
    desfechos: Leitura[list[Desfecho]]

    def todas(self) -> list[Leitura[Any]]:
        return [self.por_dia, self.resumo, self.nao_encontrado, self.orquestrador, self.desfechos]


def ler_atendimento(origem: Origem, dia: date | None = None) -> LeiturasDoAtendimento:
    fonte = obter_fonte()
    resumo, nao_encontrado = ler_ja(partial(fonte.resumo_do_periodo, origem, dia)), ler_ja(partial(fonte.nao_encontrado, origem, dia))
    orquestrador = ler_ja(partial(fonte.orquestrador, origem, dia))
    por_dia = ler_ja(partial(fonte.atendimentos_por_dia, AMBIENTE_DA_ORIGEM[origem]))
    desfechos = ler_ja(partial(fonte.desfechos, origem, dia))
    return LeiturasDoAtendimento(
        agora=datetime.now(FUSO),
        origem=origem,
        dia=dia,
        resumo=resumo.result(),
        nao_encontrado=nao_encontrado.result(),
        orquestrador=orquestrador.result(),
        por_dia=por_dia.result(),
        desfechos=desfechos.result(),
    )


@dataclass(frozen=True)
class LeiturasDoDia:
    agora: datetime
    # O dia do relatório: o escolhido no gráfico, ou hoje.
    dia: date
    # O que foi escolhido: o dia, ou o começo da hora escolhida no gráfico hora a hora.
    quando: date
    escolhido: bool
    resumo: dict[Ambiente, Leitura[ResumoDoDia]]
    verde: dict[Ambiente, Leitura[list[DiaDoVerde]]]
    credenciais: dict[Ambiente, Leitura[Credencial]]
    sistema: dict[Ambiente, Leitura[SistemaNoDia]]
    rotinas: Leitura[list[Rotina]]
    incidentes: Leitura[list[IncidenteDeCredencial]]
    por_dia: Leitura[list[ContagemPorDia]]
    # Como terminaram no dia, para o filtro por motivo.
    desfechos: Leitura[list[Desfecho]]

    def todas(self) -> list[Leitura[Any]]:
        leituras: list[Leitura[Any]] = [self.por_dia, self.rotinas, self.incidentes, self.desfechos]
        for por_ambiente in (self.resumo, self.verde, self.credenciais, self.sistema):
            leituras += por_ambiente.values()
        return leituras


def _ate_o_dia(leitura: Leitura[list[DiaDoVerde]], dia: date) -> Leitura[list[DiaDoVerde]]:
    """Os dias do Verde até o escolhido: o último da lista passa a ser ele."""
    if leitura.valor is None:
        return leitura
    return replace(leitura, valor=[d for d in leitura.valor if d.dia <= dia])


def ler_dia(dia: date | None = None) -> LeiturasDoDia:
    fonte = obter_fonte()
    resumo = {a: ler_ja(partial(fonte.resumo_do_dia, a, dia)) for a in Ambiente}
    verde = {a: ler_ja(partial(fonte.verde_por_dia, a)) for a in Ambiente}
    credenciais = {a: ler_ja(partial(fonte.credencial, a)) for a in Ambiente}
    sistema = {a: ler_ja(partial(fonte.sistema_no_dia, a, dia)) for a in Ambiente}
    rotinas, incidentes = ler_ja(fonte.rotinas), ler_ja(fonte.incidentes_de_credencial)
    por_dia = ler_ja(partial(fonte.atendimentos_por_dia, Ambiente.PRODUCAO))
    agora = datetime.now(FUSO)
    quando = dia or agora.date()
    desfechos = ler_ja(partial(fonte.desfechos_do_dia, Ambiente.PRODUCAO, quando))
    do_relatorio = quando.astimezone(FUSO).date() if isinstance(quando, datetime) else quando
    return LeiturasDoDia(
        agora=agora,
        dia=do_relatorio,
        quando=quando,
        escolhido=dia is not None,
        resumo={a: f.result() for a, f in resumo.items()},
        verde={a: _ate_o_dia(f.result(), do_relatorio) for a, f in verde.items()},
        credenciais={a: f.result() for a, f in credenciais.items()},
        sistema={a: f.result() for a, f in sistema.items()},
        rotinas=rotinas.result(),
        incidentes=incidentes.result(),
        por_dia=por_dia.result(),
        desfechos=desfechos.result(),
    )


@dataclass(frozen=True)
class LeiturasDaAplicacao:
    """O gasto lido dia a dia e mês a mês, cada dia uma vez só.

    `dias` tem todo dia que algum quadro usa: o período escolhido, os trechos de
    comparação e o mês da âncora. `assuntos` é None quando o período começa antes
    do que o registro da aplicação guarda (30 dias)."""

    agora: datetime
    periodo: Periodo
    ambiente: Ambiente
    dias: dict[date, Leitura[GastoDeIA]]
    # Os 11 meses fechados antes do mês da âncora (o da âncora sai dos dias).
    meses: list[Leitura[GastoDeIA]]
    assuntos: Leitura[list[GastoDoAssunto]] | None
    # O que as conversas da Maria registraram, nos dois ambientes: a medição é da conta inteira.
    registrados: dict[Ambiente, Leitura[list[TokensRegistrados]]]
    # Como os atendimentos do ambiente terminaram, nos 30 dias que o registro guarda.
    encaminhamentos: Leitura[list[EncaminhamentoNoDia]]

    def gasto(self, primeiro: date, ultimo: date) -> Leitura[GastoDeIA]:
        trecho = gasto.Trecho(primeiro, ultimo)
        return juntar([self.dias[d] for d in trecho.dias], lambda valores: gasto.somar(primeiro, valores))

    def dias_do_mes(self) -> Leitura[list[GastoDeIA]]:
        trecho = gasto.trechos(self.periodo.ultimo_dia).mes
        return juntar([self.dias[d] for d in trecho.dias], list)

    def doze_meses(self) -> Leitura[list[GastoDeIA]]:
        # O mês da âncora vai só até ela, como os títulos dizem ("outubro, até 25/10"):
        # a soma dos dias, e não o mês inteiro, que passaria da data escolhida.
        t = gasto.trechos(self.periodo.ultimo_dia).mes
        return juntar([*self.meses, self.gasto(t.primeiro, t.ultimo)], list)

    def dias_do_registro(self) -> list[date]:
        """Os 30 dias até hoje: os que o registro da aplicação guarda."""
        hoje = self.agora.astimezone(FUSO).date()
        return [hoje - timedelta(days=n) for n in range(DIAS_DO_REGISTRO - 1, -1, -1)]

    def todas(self) -> list[Leitura[Any]]:
        leituras: list[Leitura[Any]] = [*self.dias.values(), *self.meses, *self.registrados.values(), self.encaminhamentos]
        return [*leituras, self.assuntos] if self.assuntos is not None else leituras


MESES_DO_GRAFICO = 12


def _somar_assuntos(dias: list[list[GastoDoAssunto]]) -> list[GastoDoAssunto]:
    total: dict[Assunto, GastoDoAssunto] = {}
    for dia in dias:
        for a in dia:
            antes = total.get(a.assunto, GastoDoAssunto(a.assunto, 0, 0, 0, 0))
            total[a.assunto] = GastoDoAssunto(
                a.assunto, antes.atendimentos + a.atendimentos, antes.lido + a.lido, antes.escrito + a.escrito, antes.so_total + a.so_total
            )
    return [total[a] for a in Assunto if a in total]


def ler_aplicacao(periodo: Periodo, ambiente: Ambiente) -> LeiturasDaAplicacao:
    fonte = obter_fonte()
    ancora = periodo.ultimo_dia
    t = gasto.trechos(ancora)
    precisa: set[date] = set(periodo.dias)
    # O período anterior do mesmo tamanho, com quem o escolhido se compara.
    anterior = gasto.anterior_ao_periodo(periodo.primeiro_dia, periodo.ultimo_dia, periodo.escolha is Escolha.MES)
    for trecho in (t.dia, t.dia_anterior, t.semana, t.semana_anterior, t.mes, t.mes_anterior, anterior):
        precisa.update(trecho.dias)
    # Os 30 dias do quadro "Quanto do gasto é da Maria".
    hoje = periodo.agora.astimezone(FUSO).date()
    precisa.update(hoje - timedelta(days=n) for n in range(DIAS_DO_REGISTRO))
    registrados = {a: ler_ja(partial(fonte.tokens_registrados, a)) for a in Ambiente}
    encaminhamentos = ler_ja(partial(fonte.encaminhamentos_por_dia, ambiente))
    meses = [gasto.mes_anterior(ancora)]
    while len(meses) < MESES_DO_GRAFICO - 1:
        meses.insert(0, gasto.mes_anterior(meses[0]))
    por_assunto = None
    if periodo.primeiro_dia > hoje - timedelta(days=DIAS_DO_REGISTRO):
        por_assunto = [ler_ja(partial(fonte.gasto_por_assunto, ambiente, d)) for d in periodo.dias]
    dias = {d: ler_ja(partial(fonte.gasto_do_dia, d)) for d in sorted(precisa)}
    por_mes = [ler_ja(partial(fonte.gasto_do_mes, m)) for m in meses]
    return LeiturasDaAplicacao(
        agora=periodo.agora,
        periodo=periodo,
        ambiente=ambiente,
        dias={d: f.result() for d, f in dias.items()},
        meses=[f.result() for f in por_mes],
        assuntos=juntar([f.result() for f in por_assunto], _somar_assuntos) if por_assunto is not None else None,
        registrados={a: f.result() for a, f in registrados.items()},
        encaminhamentos=encaminhamentos.result(),
    )


def ler_agora(dia: date | None = None, ambiente: Ambiente = Ambiente.PRODUCAO) -> LeiturasDaAgora:
    """`dia` é o dia ou o começo da hora escolhidos num gráfico; `ambiente`, o do filtro da tela."""
    fonte = obter_fonte()
    agora = datetime.now(FUSO)
    # Os quadros "de hoje" (fluxos, como terminaram) leem o dia escolhido, ou hoje.
    no_dia = dia or agora.date()
    resumo, rotinas = ler_ja(partial(fonte.resumo_do_dia, ambiente, dia)), ler_ja(fonte.rotinas)
    credenciais = {a: ler_ja(partial(fonte.credencial, a)) for a in Ambiente}
    verde = {a: ler_ja(partial(fonte.verde_por_dia, a)) for a in Ambiente}
    saude = {a: ler_ja(partial(fonte.saude_servico, a)) for a in Ambiente}
    implantacoes = {a: ler_ja(partial(fonte.implantacoes_em_curso, a)) for a in Ambiente}
    reinicio = {a: ler_ja(partial(fonte.ultimo_reinicio, a)) for a in Ambiente}
    tempo, erros = ler_ja(partial(fonte.tempo_de_resposta, ambiente, dia)), ler_ja(partial(fonte.respostas_com_erro, ambiente, dia))
    pedidos = ler_ja(partial(fonte.requisicoes_por_hora, ambiente, dia))
    fluxos, desfechos = ler_ja(partial(fonte.conversas_por_fluxo, ambiente, no_dia)), ler_ja(partial(fonte.desfechos_do_dia, ambiente, no_dia))
    sistema = ler_ja(partial(fonte.sistema_no_dia, ambiente, dia))
    incidentes, renovacoes = ler_ja(fonte.incidentes_de_credencial), ler_ja(fonte.renovacoes)
    triagem, erros_da_ia = ler_ja(partial(fonte.triagem, ambiente, no_dia)), ler_ja(partial(fonte.erros_da_ia, ambiente, no_dia))
    envios = ler_ja(partial(fonte.envios_do_whatsapp, ambiente, no_dia))
    return LeiturasDaAgora(
        agora=agora,
        dia=dia,
        resumo=resumo.result(),
        credenciais={a: f.result() for a, f in credenciais.items()},
        verde={a: f.result() for a, f in verde.items()},
        rotinas=rotinas.result(),
        saude={a: f.result() for a, f in saude.items()},
        implantacoes={a: f.result() for a, f in implantacoes.items()},
        reinicio={a: f.result() for a, f in reinicio.items()},
        ambiente=ambiente,
        tempo=tempo.result(),
        erros=erros.result(),
        pedidos=pedidos.result(),
        fluxos=fluxos.result(),
        desfechos=desfechos.result(),
        sistema=sistema.result(),
        incidentes=incidentes.result(),
        renovacoes=renovacoes.result(),
        triagem=triagem.result(),
        erros_da_ia=erros_da_ia.result(),
        envios=envios.result(),
    )


@dataclass(frozen=True)
class LeiturasDaIA:
    agora: datetime
    ambiente: Ambiente
    dia: date | None
    erros: Leitura[list[ErroDaIA]]
    uso: Leitura[UsoDaIA]
    modelo: Leitura[list[DiaDoModelo]]
    mudancas: Leitura[list[MudancaNaIA]]

    def todas(self) -> list[Leitura[Any]]:
        return [self.erros, self.uso, self.modelo, self.mudancas]


def ler_ia(ambiente: Ambiente, dia: date | None = None) -> LeiturasDaIA:
    fonte = obter_fonte()
    erros, uso = ler_ja(partial(fonte.erros_da_ia, ambiente, dia)), ler_ja(partial(fonte.uso_da_ia, ambiente, dia))
    modelo, mudancas = ler_ja(fonte.saude_do_modelo), ler_ja(fonte.mudancas_na_ia)
    return LeiturasDaIA(datetime.now(FUSO), ambiente, dia, erros.result(), uso.result(), modelo.result(), mudancas.result())


@dataclass(frozen=True)
class LeiturasDosFluxos:
    """A tela Fluxos: os detalhes na janela (7 dias, ou o dia ou a hora escolhidos)
    e o histórico e os problemas em 30 dias, dia a dia."""

    agora: datetime
    ambiente: Ambiente
    # O dia, o começo da hora escolhida, ou None (os últimos 7 dias).
    dia: date | None
    conversas: Leitura[list[ConversasDoFluxo]]
    desfechos: Leitura[list[DesfechoDoFluxo]]
    triagem: Leitura[list[RodadaDaTriagem]]
    duracao: Leitura[list[DuracaoDasConversas]]
    envios: Leitura[list[EnvioDoWhatsapp]]
    por_dia: Leitura[list[FluxoNoDia]]
    problemas: Leitura[list[ProblemaNoDia]]
    # Para onde os atendimentos foram, dia a dia: quanto a Maria resolve sozinha.
    encaminhamentos: Leitura[list[EncaminhamentoNoDia]] | None = None

    def todas(self) -> list[Leitura[Any]]:
        leituras: list[Leitura[Any]] = [self.conversas, self.desfechos, self.triagem, self.duracao, self.envios, self.por_dia, self.problemas]
        return [*leituras, self.encaminhamentos] if self.encaminhamentos is not None else leituras


def ler_fluxos(ambiente: Ambiente, dia: date | None = None) -> LeiturasDosFluxos:
    fonte = obter_fonte()
    conversas, desfechos = ler_ja(partial(fonte.conversas_por_fluxo, ambiente, dia)), ler_ja(partial(fonte.desfechos_por_fluxo, ambiente, dia))
    triagem, duracao = ler_ja(partial(fonte.triagem, ambiente, dia)), ler_ja(partial(fonte.duracao_das_conversas, ambiente, dia))
    envios = ler_ja(partial(fonte.envios_do_whatsapp, ambiente, dia))
    por_dia, problemas = ler_ja(partial(fonte.fluxos_por_dia, ambiente)), ler_ja(partial(fonte.problemas_por_dia, ambiente))
    encaminhamentos = ler_ja(partial(fonte.encaminhamentos_por_dia, ambiente))
    return LeiturasDosFluxos(
        agora=datetime.now(FUSO),
        ambiente=ambiente,
        dia=dia,
        conversas=conversas.result(),
        desfechos=desfechos.result(),
        triagem=triagem.result(),
        duracao=duracao.result(),
        envios=envios.result(),
        por_dia=por_dia.result(),
        problemas=problemas.result(),
        encaminhamentos=encaminhamentos.result(),
    )
