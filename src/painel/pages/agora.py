"""Tela Agora: está funcionando?

O filtro de ambiente, no topo, vale para a tela toda: os números, o Verde, os
fluxos, como terminaram, o que aconteceu e os gráficos de hora em hora. Só "Os
dois ambientes" fica sem filtro, de propósito: é a tabela que compara os dois.

Tudo se refaz a cada minuto pelo relógio da moldura (`relogio`, em app.py). Cada
fonte é lida uma vez por rodada (`ler_agora`, em dados/telas.py): na fonte real,
cada leitura é uma consulta paga. Os gráficos têm callback próprio, para o tema
não refazer a tela inteira. Todo gráfico filtra a tela (componentes/filtro_de_dia.py).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any, NamedTuple

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, dcc, html

from painel import lateral
from painel.atencao import PRAZO_DE_AVISO_DIAS, ItemDeAtencao, incidentes_abertos, itens_de_atencao
from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import (
    Tom,
    Valor,
    celula_de_leitura,
    indicador,
    lista_de_fontes,
    nota_de_fonte,
    ponto,
    quadro,
    selo,
    texto_de_falha,
)
from painel.componentes.cabecalho import acao_em_breve, cabecalho, filtro_de_ambiente
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import (
    contagem,
    data_curta,
    data_e_hora_curta,
    dia_por_extenso,
    dias,
    ha_quanto,
    lista,
    numero,
    por_extenso,
    segundos,
)
from painel.componentes.grafico_do_verde import figura_do_verde
from painel.dados import obter_fonte
from painel.dados.fontes import DIAS_DO_GRAFICO_DO_VERDE
from painel.dados.modelo import (
    FUSO,
    NOME_DO_AMBIENTE,
    RESULTADOS_DO_VERDE,
    Ambiente,
    ConversasDoFluxo,
    Credencial,
    DiaDoVerde,
    Estado,
    FimDaConversa,
    Leitura,
    SaidaDaTriagem,
    SaudeServico,
    nome_do_desfecho,
    nome_do_fluxo,
)
from painel.dados.telas import LeiturasDaAgora, dias_passados, ler_agora, ler_ja, montar_ja, preparar

dash.register_page(__name__, path="/", name="Agora", order=0, title="Agora · Visor Maria")


# ── Indicadores ───────────────────────────────────────────────────────────


def _quando(dados: LeiturasDaAgora) -> str:
    """ "hoje", ou o que foi escolhido num gráfico: "em 22/10", "em 22/10, das 14h às 15h"."""
    return "hoje" if dados.dia is None or dados.dia == dados.agora.date() else f"em {filtro_de_dia.rotulo(dados.dia)}"


def _janela(dados: LeiturasDaAgora, padrao: str) -> str:
    """A janela das leituras que andam com o relógio ("nas últimas 24 horas") ou o que foi escolhido."""
    return padrao if dados.dia is None else f"em {filtro_de_dia.rotulo(dados.dia)}"


def _do_ambiente(dados: LeiturasDaAgora) -> str:
    return "de produção" if dados.ambiente is Ambiente.PRODUCAO else "do release"


def _dia_do_verde(dados: LeiturasDaAgora, dia: date) -> DiaDoVerde | None:
    leitura = dados.verde[dados.ambiente]
    return next((d for d in leitura.valor or [] if d.dia == dia), None) if leitura.estado is Estado.OK else None


def _do_fluxo(dados: LeiturasDaAgora, fluxo: str) -> Counter[FimDaConversa]:
    """As conversas de um fluxo no dia, por como terminaram."""
    fins = Counter[FimDaConversa]()
    for c in (dados.fluxos.valor if dados.fluxos else None) or []:
        if c.fluxo == fluxo:
            fins[c.fim] += c.conversas
    return fins


def indicadores(dados: LeiturasDaAgora, escolha: Filtro = Filtro()) -> list[html.Section]:
    agora, resumo, credencial = dados.agora, dados.resumo, dados.credenciais[dados.ambiente]
    quando = _quando(dados)
    # Um dia que já passou é lido inteiro; hoje, de 0h até agora.
    passado = quando != "hoje"
    resultado = escolha.resultado_do_verde
    no_verde = _dia_do_verde(dados, escolha.dia or agora.date()) if resultado else None

    def comecaram() -> Valor:
        assert resumo.valor is not None
        return Valor(numero(resumo.valor.comecaram), legenda="dia inteiro" if passado else "desde 0h")

    def terminaram() -> Valor:
        assert resumo.valor is not None
        em_aberto = resumo.valor.comecaram - resumo.valor.terminaram
        return Valor(numero(resumo.valor.terminaram), legenda=f"{numero(em_aberto)} {'sem terminar no dia' if passado else 'ainda em aberto'}")

    # Com um fluxo escolhido em "Fluxos hoje", começaram e terminaram são só dele.
    if escolha.fluxo is not None and dados.fluxos is not None:
        fins, nome = _do_fluxo(dados, escolha.fluxo), nome_do_fluxo(escolha.fluxo)

        def comecaram_no_fluxo() -> Valor:
            return Valor(numero(sum(fins.values())), legenda=f"no fluxo {nome}")

        def terminaram_no_fluxo() -> Valor:
            terminou = fins[FimDaConversa.CONCLUIU] + fins[FimDaConversa.ENCAMINHOU]
            return Valor(numero(terminou), legenda=f"{numero(fins[FimDaConversa.ENCAMINHOU])} encaminhadas; {numero(fins[FimDaConversa.PAROU])} pararam")

        quadro_dos_que_comecaram = indicador(f"Começaram: {nome}", "conversa", [dados.fluxos], comecaram_no_fluxo, f"Nenhuma conversa {quando}.", agora)
        quadro_dos_que_terminaram = indicador(f"Terminaram: {nome}", "certo", [dados.fluxos], terminaram_no_fluxo, f"Nenhuma conversa {quando}.", agora)
    else:
        quadro_dos_que_comecaram = indicador(f"Começaram {quando}", "conversa", [resumo], comecaram, f"Ninguém começou um atendimento {quando}.", agora)
        quadro_dos_que_terminaram = indicador("Terminaram", "certo", [resumo], terminaram, f"Nenhum atendimento terminou {quando}.", agora)
        # Com um motivo escolhido em "Como terminaram", terminaram conta só ele.
        if dados.desfechos is not None:
            quadro_dos_que_terminaram = (
                filtro_de_dia.terminaram_no_motivo(dados.desfechos, escolha.motivo, f"Nenhum atendimento terminou {quando}.", agora)
                or quadro_dos_que_terminaram
            )

    def consultas() -> Valor:
        assert resumo.valor is not None
        r = resumo.valor
        tom: Tom = "bom" if r.aceitas_verde >= 0.8 * r.consultas_verde else "atencao"
        return Valor(numero(r.consultas_verde), legenda=f"{numero(r.aceitas_verde)} aceitas {'no dia' if passado else 'desde 0h'}", tom_da_legenda=tom)

    def consultas_do_resultado() -> Valor:
        # O resultado escolhido no gráfico do Verde, no dia inteiro (o gráfico é por dia).
        assert no_verde is not None and resultado is not None
        tom: Tom = "ruim" if resultado == "recusadas" and no_verde.recusadas else "neutro"
        return Valor(numero(getattr(no_verde, resultado)), tom, legenda=f"de {numero(no_verde.total)} consultas em {data_curta(no_verde.dia)}, dia inteiro")

    if no_verde is not None and resultado is not None:
        quadro_das_consultas = indicador(
            f"Consultas ao Verde: {filtro_de_dia.nome_da_serie(resultado)}",
            "busca",
            [dados.verde[dados.ambiente]],
            consultas_do_resultado,
            "Ninguém consultou o Verde no dia.",
            agora,
        )
    else:
        quadro_das_consultas = indicador("Consultas ao Verde", "busca", [resumo], consultas, f"Ninguém consultou o Verde {quando}.", agora)

    def validade() -> Valor:
        assert credencial.valor is not None
        valida_ate = credencial.valor.valida_ate
        if valida_ate <= agora:
            return Valor("Vencida", "ruim", legenda=f"desde {data_e_hora_curta(valida_ate)}")
        faltam = (valida_ate.date() - agora.date()).days
        tom: Tom = "atencao" if faltam <= PRAZO_DE_AVISO_DIAS else "bom"
        quantos, _, unidade = dias(faltam).partition(" ")
        return Valor(quantos, tom, unidade=unidade, legenda=f"vence em {data_e_hora_curta(valida_ate)}")

    def incidentes() -> Valor:
        abertos = incidentes_abertos(dados.credenciais, agora)
        if not abertos:
            return Valor("0", legenda="nenhum aberto", tom_da_legenda="bom")
        primeiro = abertos[0]
        de = "de produção" if primeiro.ambiente is Ambiente.PRODUCAO else "do release"
        return Valor(numero(len(abertos)), "ruim", legenda=f"credencial {de}, {ha_quanto(primeiro.desde, agora)}")

    return [
        quadro_dos_que_comecaram,
        quadro_dos_que_terminaram,
        quadro_das_consultas,
        indicador(f"Credencial {_do_ambiente(dados)}", "relogio", [credencial], validade, "A conferência diária não trouxe a validade.", agora),
        indicador(
            "Incidentes abertos",
            "alerta",
            list(dados.credenciais.values()),
            incidentes,
            "A conferência diária não trouxe as credenciais.",
            agora,
        ),
        *_indicadores_do_servico(dados),
    ]


def _indicadores_do_servico(dados: LeiturasDaAgora) -> list[html.Section]:
    """Tempo de resposta, erros de servidor e requisições, do ambiente do filtro."""
    agora = dados.agora
    tempo, erros, pedidos = dados.tempo, dados.erros, dados.pedidos
    if tempo is None or erros is None or pedidos is None:
        return []
    janela = _janela(dados, "nas últimas 24 horas")

    def resposta() -> Valor:
        assert tempo.valor is not None
        t = tempo.valor
        tom: Tom = "ruim" if t.nove_em_dez_ate > 10 else "atencao" if t.nove_em_dez_ate > 5 else "bom"
        return Valor(
            segundos(t.metade_ate),
            unidade=" s",
            legenda=f"metade das respostas em até isso; nove em dez em até {segundos(t.nove_em_dez_ate)} s",
            tom_da_legenda=tom,
        )

    def com_erro() -> Valor:
        assert erros.valor is not None
        e = erros.valor
        return Valor(
            numero(e.de_servidor),
            "ruim" if e.de_servidor else "bom",
            legenda=f"{janela}; {numero(e.de_gente)} recusadas a pessoas e {numero(e.de_robo)} a robôs",
        )

    def requisicoes() -> Valor:
        assert pedidos.valor is not None
        horas = pedidos.valor
        if dados.dia is not None:
            pico = max(horas, key=lambda h: h.requisicoes)
            return Valor(numero(sum(h.requisicoes for h in horas)), legenda=f"no dia; a hora mais cheia foi a das {pico.hora:%H}h")
        # A hora corrente acabou de começar: a última hora inteira diz mais.
        completas = horas[:-1] or horas
        ultima = completas[-1]
        media = sum(h.requisicoes for h in completas) / len(completas)
        fim = ultima.hora + timedelta(hours=1)
        return Valor(numero(ultima.requisicoes), legenda=f"das {ultima.hora:%H}h às {fim:%H}h; a média é {numero(round(media))} por hora")

    return [
        indicador("Tempo de resposta", "relogio", [tempo], resposta, f"Nenhum atendimento respondido {janela}.", agora),
        indicador("Erros de servidor", "servidor", [erros], com_erro, f"Nenhuma resposta com erro {janela}.", agora),
        indicador(
            "Requisições no dia" if dados.dia is not None else "Requisições na última hora",
            "atividade",
            [pedidos],
            requisicoes,
            f"O balanceador não contou requisição {janela}.",
            agora,
        ),
    ]


# ── Exige atenção ─────────────────────────────────────────────────────────

SELO: dict[str, tuple[str, Tom]] = {"parado": ("Parado", "ruim"), "atencao": ("Atenção", "atencao")}


def _linha_de_atencao(item: ItemDeAtencao) -> html.Li:
    texto, tom = SELO[item.nivel]
    caminhos = {p["name"]: p["relative_path"] for p in dash.page_registry.values()}
    if item.tela in caminhos:
        acao: Any = dcc.Link(item.acao, href=caminhos[item.tela], className="atencao-acao")
    else:
        acao = html.Span(item.acao, className="atencao-acao atencao-acao-desativada", title="Tela em breve")
    return html.Li(
        [
            selo(texto, tom),
            html.Div([html.P(item.titulo, className="atencao-titulo"), html.P(item.descricao, className="atencao-descricao")]),
            acao,
        ],
        className="atencao-linha",
    )


def exige_atencao(dados: LeiturasDaAgora) -> html.Section:
    leituras: list[Leitura[Any]] = [*dados.credenciais.values(), *dados.verde.values(), dados.rotinas]
    itens = itens_de_atencao(dados.credenciais, dados.verde, dados.rotinas, dados.agora)
    linhas: list[Any] = [_linha_de_atencao(item) for item in itens]
    # Se uma fonte faltou, o quadro diz qual, em vez de parecer tranquilo.
    faltaram = list(dict.fromkeys(leitura.fonte.curto for leitura in leituras if leitura.estado is not Estado.OK))
    if faltaram:
        linhas.append(
            html.Li(
                html.P(f"Faltou ler: {lista(faltaram)}. Este quadro pode estar incompleto.", className="texto-aviso"),
                className="atencao-linha",
            )
        )
    elif not linhas:
        linhas = [html.Li(html.P("Nada pede atenção agora.", className="texto-vazio"), className="atencao-linha")]
    quantos = len(itens)
    lateral = f"{por_extenso(quantos)} {'item aberto' if quantos <= 1 else 'itens abertos'}"
    return quadro("Exige atenção", html.Ul(linhas, className="atencao-lista"), leituras, dados.agora, lateral=lateral)


# ── O que aconteceu no dia ────────────────────────────────────────────────


def _no_dia(momento: datetime, dia: date) -> bool:
    return momento.astimezone(FUSO).date() == dia


def acontecimentos(dados: LeiturasDaAgora) -> html.Section:
    """O dia do ambiente do filtro, em linhas com hora: reinícios, credencial que
    passou a recusar ou voltou, renovações; e, no topo, quedas, subidas e erros."""
    dia = filtro_de_dia.dia_de(dados.dia) or dados.agora.date()
    quando = _quando(dados)
    leituras: list[Leitura[Any]] = [x for x in (dados.sistema, dados.incidentes, dados.renovacoes) if x is not None]
    linhas: list[tuple[datetime, str, Tom]] = []
    sistema = dados.sistema.valor if dados.sistema is not None and dados.sistema.estado is Estado.OK else None
    if sistema is not None:
        linhas += [(r, "A Maria reiniciou", "atencao") for r in sistema.reinicios if _no_dia(r, dia)]
    for i in (dados.incidentes.valor if dados.incidentes is not None else None) or []:
        if i.ambiente is not dados.ambiente:
            continue
        if _no_dia(i.inicio, dia):
            linhas.append((i.inicio, f"A credencial começou a ser recusada ({contagem(i.recusadas, 'recusa', 'recusas')})", "ruim"))
        if i.fim is not None and _no_dia(i.fim, dia):
            linhas.append((i.fim, "A credencial voltou a ser aceita", "bom"))
    for r in (dados.renovacoes.valor if dados.renovacoes is not None else None) or []:
        if r.ambiente is dados.ambiente and _no_dia(r.momento, dia):
            linhas.append(
                (
                    r.momento,
                    "A conferência diária renovou a credencial" + ("" if r.container_novo_no_ar else ", mas o container novo não subiu"),
                    "bom" if r.container_novo_no_ar else "atencao",
                )
            )
    linhas.sort(key=lambda linha: linha[0])

    contas: list[Any] = []
    if sistema is not None:
        contas = [
            ponto(f"{numero(sistema.minutos_fora_do_ar)} min fora do ar", "ruim" if sistema.minutos_fora_do_ar else "bom"),
            ponto(contagem(sistema.subidas, "versão nova no ar", "versões novas no ar"), "neutro"),
            ponto(contagem(sistema.erros_de_servidor, "erro de servidor", "erros de servidor"), "ruim" if sistema.erros_de_servidor else "bom"),
        ]
    corpo: list[Any] = [html.Div(contas, className="acontecimentos-contas")] if contas else []
    if linhas:
        corpo.append(
            html.Ul(
                [
                    html.Li([html.Span(f"{m.astimezone(FUSO):%H:%M}", className="mono"), ponto(texto, tom)], className="acontecimento")
                    for m, texto, tom in linhas
                ],
                className="acontecimentos",
            )
        )
    else:
        corpo.append(html.P(f"Nenhum reinício e nenhuma troca de credencial {quando}.", className="texto-vazio"))
    falhou = next((x for x in leituras if x.estado is Estado.INDISPONIVEL), None)
    if falhou is not None:
        corpo.append(texto_de_falha(falhou))
    return quadro(f"O que aconteceu {quando}", corpo, leituras, dados.agora, lateral=NOME_DO_AMBIENTE[dados.ambiente].lower())


# ── O caminho do atendimento ──────────────────────────────────────────────

# O estado de cada etapa: funciona, com problema, parada, ou sem uso no ambiente ou na janela.
EstadoDaEtapa = tuple[str, Tom]
FUNCIONA: EstadoDaEtapa = ("Funciona", "bom")
COM_PROBLEMA: EstadoDaEtapa = ("Com problema", "atencao")
PARADO: EstadoDaEtapa = ("Não funciona", "ruim")
SEM_USO: EstadoDaEtapa = ("Sem uso", "neutro")
SEM_LEITURA: EstadoDaEtapa = ("Sem leitura", "neutro")
# Motivos de encaminhamento que vêm de um sistema que falhou no meio do atendimento.
FALHAS_NO_ATENDIMENTO = ("falha_infra_verde", "falha_cadastro", "falha_encaminhamento", "sem_orgao_disponivel")
ENVIO_FALHOU = ("whatsapp_envio_falhou", "whatsapp_envio_erro", "whatsapp_bridge_erro", "whatsapp_status_entrega")


class Etapa(NamedTuple):
    """Uma etapa do caminho: o que ela faz, as leituras que dizem como está, e onde ver mais.
    A primeira leitura é a principal: vazia, a etapa não teve uso, e diz `vazio`."""

    nome: str
    faz: str
    leituras: list[Leitura[Any]]
    avaliar: Callable[[], tuple[EstadoDaEtapa, str]]
    tela: tuple[str, str]
    vazio: str


def _recebe(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    saude, erros, sistema = dados.saude[dados.ambiente].valor, dados.erros, dados.sistema
    assert saude is not None
    de_servidor = erros.valor.de_servidor if erros is not None and erros.valor is not None else 0
    fora = sistema.valor.minutos_fora_do_ar if sistema is not None and sistema.valor is not None else 0
    detalhe = f"{saude.hosts_saudaveis} de {saude.hosts_desejados} containers no ar; {contagem(de_servidor, 'erro de servidor', 'erros de servidor')}; {numero(fora)} min fora do ar"
    if saude.hosts_saudaveis == 0:
        return PARADO, detalhe
    if saude.hosts_saudaveis < saude.hosts_desejados or de_servidor or fora:
        return COM_PROBLEMA, detalhe
    return FUNCIONA, detalhe


def _responde_rapido(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    assert dados.tempo is not None and dados.tempo.valor is not None
    t = dados.tempo.valor
    detalhe = f"metade das respostas em até {segundos(t.metade_ate)} s, nove em dez em até {segundos(t.nove_em_dez_ate)} s"
    if t.nove_em_dez_ate > 10:
        return PARADO, detalhe + "; a pessoa espera demais"
    return (COM_PROBLEMA if t.nove_em_dez_ate > 5 else FUNCIONA), detalhe


def _triagem(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    rodadas = (dados.triagem.valor if dados.triagem is not None else None) or []
    if not rodadas:
        return SEM_USO, "a triagem por escrita livre não rodou neste ambiente na janela"
    por_saida = Counter[SaidaDaTriagem]()
    for r in rodadas:
        por_saida[r.saida] += r.vezes
    decididas = sum(por_saida.values()) - por_saida[SaidaDaTriagem.PERGUNTOU]
    achou = por_saida[SaidaDaTriagem.IDENTIFICOU] + por_saida[SaidaDaTriagem.REDIRECIONOU]
    sem_fluxo, contradisse = por_saida[SaidaDaTriagem.SEM_FLUXO], por_saida[SaidaDaTriagem.INCONSISTENCIA]
    detalhe = f"achou o assunto em {numero(achou)} de {numero(decididas)}; {numero(sem_fluxo)} sem fluxo; {numero(contradisse)} contradições"
    if contradisse or (decididas and sem_fluxo / decididas > 0.3):
        return COM_PROBLEMA, detalhe
    return FUNCIONA, detalhe


def _fluxos_andam(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    fins = Counter[FimDaConversa]()
    for c in (dados.fluxos.valor if dados.fluxos is not None else None) or []:
        fins[c.fim] += c.conversas
    total = sum(fins.values())
    if not total:
        return SEM_USO, "nenhuma conversa começou num fluxo na janela"
    pararam = fins[FimDaConversa.PAROU] + fins[FimDaConversa.EXPIROU]
    detalhe = (
        f"{numero(total)} conversas: {numero(fins[FimDaConversa.CONCLUIU])} concluídas, {numero(fins[FimDaConversa.ENCAMINHOU])} encaminhadas, "
        f"{numero(pararam)} pararam ou estão em andamento"
    )
    return (COM_PROBLEMA if pararam / total > 0.5 else FUNCIONA), detalhe


def _credencial_vale(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    credencial = dados.credenciais[dados.ambiente].valor
    assert credencial is not None
    abertos = [i for i in incidentes_abertos(dados.credenciais, dados.agora) if i.ambiente is dados.ambiente]
    if credencial.valida_ate <= dados.agora:
        return PARADO, f"venceu em {data_e_hora_curta(credencial.valida_ate)}; o Verde recusa as consultas"
    if abertos:
        return PARADO, f"o Verde está recusando a credencial, {ha_quanto(abertos[0].desde, dados.agora)}"
    faltam = (credencial.valida_ate.date() - dados.agora.date()).days
    detalhe = f"vale até {data_e_hora_curta(credencial.valida_ate)}, faltam {dias(faltam)}"
    return (COM_PROBLEMA if faltam <= PRAZO_DE_AVISO_DIAS else FUNCIONA), detalhe


def _verde_responde_hoje(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    dia = _dia_do_verde(dados, filtro_de_dia.dia_de(dados.dia) or dados.agora.date())
    if dia is None or not dia.total:
        return SEM_USO, "ninguém consultou o Verde no dia"
    falhou = dia.erro_do_verde + dia.sem_resposta
    detalhe = (
        f"{numero(dia.aceitas)} de {numero(dia.total)} consultas responderam; {numero(dia.recusadas)} recusas da credencial, "
        f"{numero(falhou)} com erro do Verde ou sem resposta, {numero(dia.nao_achou)} com processo inexistente"
    )
    if dia.recusadas and not dia.aceitas:
        return PARADO, detalhe
    if dia.recusadas or falhou > 0.1 * dia.total:
        return COM_PROBLEMA, detalhe
    return FUNCIONA, detalhe


def _ia_responde(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    erros = (dados.erros_da_ia.valor if dados.erros_da_ia is not None else None) or []
    falhas = {e.funcao: e.falhas for e in erros if e.falhas}
    if not falhas:
        return FUNCIONA, "nenhuma falha das funções de inteligência artificial no dia"
    total = sum(falhas.values())
    quais = lista([f"{f} ({numero(n)})" for f, n in sorted(falhas.items(), key=lambda par: -par[1])])
    return COM_PROBLEMA, f"{contagem(total, 'falha', 'falhas')} no dia: {quais}"


def _falhas_no_meio(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    desfechos = (dados.desfechos.valor if dados.desfechos is not None else None) or []
    terminaram = sum(d.atendimentos for d in desfechos)
    falhas = {d.motivo: d.atendimentos for d in desfechos if d.motivo in FALHAS_NO_ATENDIMENTO and d.atendimentos}
    if not terminaram:
        return SEM_USO, "nenhum atendimento terminou na janela"
    if not falhas:
        return FUNCIONA, f"nenhum dos {numero(terminaram)} atendimentos foi para pessoa por falha de sistema"
    quais = lista([f"{nome_do_desfecho(m)} ({numero(n)})" for m, n in sorted(falhas.items(), key=lambda par: -par[1])])
    total = sum(falhas.values())
    return (PARADO if total > 0.3 * terminaram else COM_PROBLEMA), f"{numero(total)} de {numero(terminaram)} foram para pessoa por falha: {quais}"


def _whatsapp(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    envios = (dados.envios.valor if dados.envios is not None else None) or []
    if not envios:
        return SEM_USO, "a Maria não mandou direto pelo WhatsApp na janela; neste caso quem entrega é a Tykhe"
    ok = sum(e.vezes for e in envios if e.evento == "whatsapp_envio_ok")
    falhou = sum(e.vezes for e in envios if e.evento in ENVIO_FALHOU)
    detalhe = f"{numero(ok)} mensagens enviadas; {numero(falhou)} recusadas, com erro ou sem chegar à pessoa"
    if falhou and not ok:
        return PARADO, detalhe
    return (COM_PROBLEMA if falhou else FUNCIONA), detalhe


def _troca_de_versao(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    resumo, em_curso = dados.resumo.valor, dados.implantacoes[dados.ambiente].valor or 0
    assert resumo is not None
    detalhe = f"{contagem(resumo.sem_checkpoint, 'conversa cortada', 'conversas cortadas')} na troca de versão; {contagem(em_curso, 'implantação', 'implantações')} em curso"
    if em_curso > 1:
        return COM_PROBLEMA, detalhe + "; a atualização pode ter travado"
    return (COM_PROBLEMA if resumo.sem_checkpoint else FUNCIONA), detalhe


def _rotinas(dados: LeiturasDaAgora) -> tuple[EstadoDaEtapa, str]:
    rotinas = dados.rotinas.valor
    assert rotinas is not None
    falhando = [r for r in rotinas if r.falhando_desde is not None]
    if not falhando:
        return FUNCIONA, f"as {len(rotinas)} rotinas automáticas passaram na última vez, com a conferência diária da credencial"
    quais = lista([f"{r.nome}, {ha_quanto(r.falhando_desde, dados.agora)}" for r in falhando if r.falhando_desde is not None])
    return PARADO, f"falhando: {quais}"


def etapas(dados: LeiturasDaAgora) -> list[Etapa]:
    """O caminho de uma mensagem, na ordem: chega, é triada, segue um fluxo, consulta o
    Verde, usa a inteligência artificial, termina ou vai para pessoa, e a resposta volta."""
    a = dados.ambiente
    opcionais: dict[str, list[Leitura[Any]]] = {
        "tempo": [dados.tempo] if dados.tempo is not None else [],
        "triagem": [dados.triagem] if dados.triagem is not None else [],
        "fluxos": [dados.fluxos] if dados.fluxos is not None else [],
        "ia": [dados.erros_da_ia] if dados.erros_da_ia is not None else [],
        "desfechos": [dados.desfechos] if dados.desfechos is not None else [],
        "envios": [dados.envios] if dados.envios is not None else [],
    }
    recebe: list[Leitura[Any]] = [dados.saude[a], *(x for x in (dados.erros, dados.sistema) if x is not None)]
    sistema, fluxos = ("Sistema", "/sistema"), ("Fluxos", "/fluxos")
    return [
        Etapa("A Maria recebe a mensagem", "o serviço no ar, atrás do balanceador", recebe, partial(_recebe, dados), sistema, "o balanceador não respondeu"),
        Etapa(
            "Responde a tempo",
            "quanto a pessoa espera por cada resposta",
            opcionais["tempo"],
            partial(_responde_rapido, dados),
            sistema,
            "nenhuma resposta na janela",
        ),
        Etapa(
            "A triagem acha o assunto",
            "a escrita livre que leva ao fluxo certo",
            opcionais["triagem"],
            partial(_triagem, dados),
            fluxos,
            "a triagem por escrita livre não rodou neste ambiente na janela",
        ),
        Etapa(
            "O fluxo anda até o fim",
            "as perguntas de cada fluxo",
            opcionais["fluxos"],
            partial(_fluxos_andam, dados),
            fluxos,
            "nenhuma conversa começou num fluxo na janela",
        ),
        Etapa(
            "A credencial do Verde vale",
            "a chave que a Maria usa para consultar",
            [dados.credenciais[a]],
            partial(_credencial_vale, dados),
            ("Credencial", "/credencial"),
            "a conferência diária não trouxe a validade",
        ),
        Etapa(
            "O Verde responde",
            "a consulta da pessoa e do processo",
            [dados.verde[a]],
            partial(_verde_responde_hoje, dados),
            ("Credencial", "/credencial"),
            "ninguém consultou o Verde nos últimos dias",
        ),
        Etapa(
            "A inteligência artificial funciona",
            "classificar, extrair e reescrever as respostas",
            opcionais["ia"],
            partial(_ia_responde, dados),
            ("Observatório da IA", "/ia"),
            "nenhuma função de inteligência artificial rodou na janela",
        ),
        Etapa(
            "Cadastro e envio ao órgão",
            "os sistemas que a Maria chama para concluir",
            opcionais["desfechos"],
            partial(_falhas_no_meio, dados),
            ("Relatório da Aplicação", "/aplicacao"),
            "nenhum atendimento terminou na janela",
        ),
        Etapa(
            "A resposta chega pelo WhatsApp",
            "o envio direto, quando a Maria manda",
            opcionais["envios"],
            partial(_whatsapp, dados),
            fluxos,
            "a Maria não mandou direto pelo WhatsApp na janela; neste caso quem entrega é a Tykhe",
        ),
        Etapa(
            "A troca de versão não corta conversa",
            "a atualização da Maria no ar",
            [dados.resumo, dados.implantacoes[a]],
            partial(_troca_de_versao, dados),
            sistema,
            "nenhum atendimento na janela",
        ),
        Etapa(
            "As rotinas automáticas passam",
            "testes e a conferência diária",
            [dados.rotinas],
            partial(_rotinas, dados),
            sistema,
            "o GitHub não trouxe as rotinas",
        ),
    ]


def _estado_da_etapa(etapa: Etapa) -> tuple[EstadoDaEtapa, str]:
    falha = next((x for x in etapa.leituras if x.estado is Estado.INDISPONIVEL), None)
    if falha is not None:
        return SEM_LEITURA, f"faltou ler {falha.fonte.curto}; não dá para dizer se funciona"
    if not etapa.leituras:
        return SEM_LEITURA, "esta leitura não entrou nesta rodada"
    # Leitura vazia (nada na janela) não é falha: a etapa não teve uso.
    if etapa.leituras[0].estado is Estado.VAZIO or etapa.leituras[0].valor is None:
        return SEM_USO, etapa.vazio
    return etapa.avaliar()


def caminho_do_atendimento(dados: LeiturasDaAgora) -> html.Section:
    """De ponta a ponta, o que funciona e o que não funciona no atendimento, no ambiente do filtro."""
    linhas, contas = [], Counter[str]()
    todas = etapas(dados)
    for etapa in todas:
        (texto, tom), detalhe = _estado_da_etapa(etapa)
        contas[tom] += 1
        nome_da_tela, caminho = etapa.tela
        linhas.append(
            html.Tr(
                [
                    html.Th([html.P(etapa.nome, className="etapa-nome"), html.P(etapa.faz, className="etapa-faz")], scope="row", className="com-explicacao"),
                    html.Td(ponto(texto, tom)),
                    html.Td(detalhe, className="etapa-detalhe"),
                    html.Td(dcc.Link(f"Ver em {nome_da_tela}", href=caminho, className="atencao-acao")),
                ],
                className=f"etapa etapa-{tom}",
            )
        )
    tabela = html.Table(
        [html.Thead(html.Tr([html.Th("Etapa"), html.Th("Estado"), html.Th("O que os números dizem"), html.Th("")])), html.Tbody(linhas)],
        className="tabela tabela-do-caminho",
    )
    ruins, atencao = contas["ruim"], contas["atencao"]
    funcionam = contas["bom"]
    tom_do_resumo: Tom
    if ruins:
        resumo, tom_do_resumo = f"{contagem(ruins, 'etapa não funciona', 'etapas não funcionam')}", "ruim"
    elif atencao:
        resumo, tom_do_resumo = f"{contagem(atencao, 'etapa com problema', 'etapas com problema')}", "atencao"
    else:
        resumo, tom_do_resumo = "tudo o que rodou funciona", "bom"
    lateral = [selo(resumo, tom_do_resumo), html.Span(f" {funcionam} de {len(todas)} funcionam; {NOME_DO_AMBIENTE[dados.ambiente].lower()}, {_quando(dados)}")]
    # Sem repetir a mesma leitura no pé (a mesma fonte entra em mais de uma etapa).
    leituras: list[Leitura[Any]] = list({id(x): x for etapa in todas for x in etapa.leituras}.values())
    return quadro("O caminho do atendimento: o que funciona e o que não", tabela, leituras, dados.agora, lateral=lateral)


# ── Os dois ambientes ─────────────────────────────────────────────────────


def _no_ar(saude: SaudeServico) -> html.Div:
    if saude.hosts_saudaveis == 0:
        return ponto("Fora do ar", "ruim")
    if saude.hosts_saudaveis < saude.hosts_desejados:
        return ponto("Em parte", "atencao", f"{saude.hosts_saudaveis} de {saude.hosts_desejados} containers")
    return ponto("No ar", "bom")


def _verde_responde(dias_do_verde: list[DiaDoVerde]) -> html.Div:
    hoje = dias_do_verde[-1]
    semana = dias_do_verde[-7:]
    if hoje.total:
        if hoje.recusadas == 0:
            return ponto("Sim", "bom", f"{numero(hoje.aceitas)} de {numero(hoje.total)} aceitas hoje")
        if hoje.aceitas == 0:
            return ponto("Recusando", "ruim", f"{contagem(hoje.recusadas, 'recusada', 'recusadas')} hoje, nenhuma aceita")
        return ponto("Com recusas", "atencao", f"{numero(hoje.recusadas)} de {numero(hoje.total)} recusadas hoje")
    aceitas = sum(d.aceitas for d in semana)
    recusadas = sum(d.recusadas for d in semana)
    if recusadas and not aceitas:
        return ponto("Recusando", "ruim", f"{numero(recusadas)} em 7 dias, nenhuma aceita")
    if not aceitas:
        return ponto("Sem consulta", "neutro", "ninguém consultou em 7 dias")
    return ponto("Sem consulta hoje", "neutro", f"{numero(aceitas)} aceitas em 7 dias")


def _credencial(agora: datetime) -> Any:
    def montar(credencial: Credencial) -> html.Div:
        if credencial.valida_ate <= agora:
            return ponto(f"Venceu em {data_curta(credencial.valida_ate)}", "ruim")
        faltam = (credencial.valida_ate.date() - agora.date()).days
        if faltam <= PRAZO_DE_AVISO_DIAS:
            return ponto(f"Vence em {dias(faltam)}", "atencao")
        return ponto(f"Vale até {data_curta(credencial.valida_ate)}", "bom")

    return montar


def _travou(em_curso: int) -> html.Div:
    if em_curso <= 1:
        return ponto("Não", "bom")
    return ponto("Talvez", "atencao", f"{em_curso} implantações ao mesmo tempo")


def _reinicio(momento: datetime) -> html.P:
    return html.P(data_e_hora_curta(momento), className="mono")


def dois_ambientes(dados: LeiturasDaAgora) -> html.Section:
    linhas = (
        ("A Maria está no ar", dados.saude, _no_ar, "sem leitura do balanceador"),
        ("O Verde responde", dados.verde, _verde_responde, "ninguém consultou em 8 dias"),
        ("A credencial", dados.credenciais, _credencial(dados.agora), "conferência sem resultado"),
        ("A atualização travou", dados.implantacoes, _travou, "sem leitura do ECS"),
        ("Reiniciou em", dados.reinicio, _reinicio, "nenhuma subida em 30 dias"),
    )
    corpo_da_tabela = [
        html.Tr(
            [
                html.Th(pergunta, scope="row"),
                *(html.Td(celula_de_leitura(leituras[a], montar, vazio)) for a in Ambiente),
            ]
        )
        for pergunta, leituras, montar, vazio in linhas
    ]
    tabela = html.Table(
        [
            html.Thead(html.Tr([html.Th("Pergunta"), *(html.Th(NOME_DO_AMBIENTE[a]) for a in Ambiente)])),
            html.Tbody(corpo_da_tabela),
        ],
        className="tabela",
    )
    usadas: list[Leitura[Any]] = [leitura for _, porta, _, _ in linhas for leitura in porta.values()]
    return quadro("Os dois ambientes", tabela, usadas, dados.agora, lateral="sem filtro, de propósito")


# ── O Verde nos últimos 8 dias ────────────────────────────────────────────


def _resumo_do_verde(dias_do_verde: list[DiaDoVerde]) -> html.Div:
    total = sum(d.total for d in dias_do_verde)
    aceitas = sum(d.aceitas for d in dias_do_verde)
    recusadas = sum(d.recusadas for d in dias_do_verde)
    com_recusa = [data_curta(d.dia) for d in dias_do_verde if d.recusadas]
    if recusadas and len(com_recusa) > 3:
        explicacao = f"As {numero(recusadas)} recusas estão espalhadas em {len(com_recusa)} dos {len(dias_do_verde)} dias."
    elif recusadas:
        explicacao = f"As {numero(recusadas)} recusas estão em {dias(len(com_recusa))}: {lista(com_recusa)}."
    else:
        explicacao = "Nenhuma recusa da credencial no período."
    nao_achou = sum(d.nao_achou for d in dias_do_verde)
    falhou = sum(d.erro_do_verde + d.sem_resposta for d in dias_do_verde)
    resto = []
    if nao_achou:
        resto.append(f"{numero(nao_achou)} não acharam o processo, o que não é falha")
    if falhou:
        resto.append(f"{numero(falhou)} tiveram erro do Verde ou ficaram sem resposta")
    return html.Div(
        [
            html.P([html.Strong(numero(aceitas)), f" de {numero(total)} responderam"], className="verde-total"),
            html.P(explicacao + (f" Das outras, {lista(resto)}." if resto else ""), className="verde-explicacao"),
        ],
        className="verde-resumo",
    )


LEGENDA_DO_VERDE = [(campo, tom, nome) for campo, nome, tom, _ in RESULTADOS_DO_VERDE]


def _o_que_cada_cor_quer_dizer() -> html.Div:
    """Embaixo do gráfico: o que é cada resultado de uma consulta ao Verde."""
    return html.Div(
        [
            html.P("O que cada cor quer dizer", className="rotulo-pequeno"),
            html.Dl(
                [
                    peca
                    for _, nome, tom, explicacao in RESULTADOS_DO_VERDE
                    for peca in (html.Dt([html.Span(className=f"legenda-cor tom-{tom}"), nome]), html.Dd(explicacao))
                ],
                className="significados",
            ),
        ],
        className="miolo",
    )


def conteudo_do_verde(leitura: Leitura[list[DiaDoVerde]], ambiente: Ambiente, tema: str | None, agora: datetime, escolha: Filtro = Filtro()) -> list[Any]:
    """O miolo do quadro do Verde, com a fonte no pé. O topo, com o filtro, não se refaz.
    O clique num segmento escolhe o dia e o resultado; na legenda, só o resultado
    (componentes/filtro_de_dia.py)."""
    if leitura.estado is Estado.INDISPONIVEL:
        miolo: list[Any] = [texto_de_falha(leitura)]
    elif leitura.estado is Estado.VAZIO or not leitura.valor or not any(d.total for d in leitura.valor):
        miolo = [html.P("Ninguém consultou o Verde nos últimos 8 dias.", className="texto-vazio")]
    else:
        series = filtro_de_dia.SERIES_DO_VERDE
        figura = filtro_de_dia.destacar(figura_do_verde(leitura.valor, ambiente, tema), escolha, tema, series)
        figura.update_layout(height=260)
        # Na largura inteira: o gráfico e o resumo à esquerda, a legenda e o que cada cor quer dizer à direita.
        miolo = [
            html.Div(
                [
                    html.Div([filtro_de_dia.grafico("agora", "verde", figura, series=series), _resumo_do_verde(leitura.valor)], className="verde-grafico"),
                    html.Div(
                        [filtro_de_dia.legenda("agora", LEGENDA_DO_VERDE, escolha.resultado_do_verde), _o_que_cada_cor_quer_dizer()],
                        className="verde-significados",
                    ),
                ],
                className="verde-em-largura",
            )
        ]
    return [html.Div(miolo, className="quadro-corpo"), html.Footer(nota_de_fonte([leitura], agora), className="quadro-pe")]


def quadro_do_verde(dados: LeiturasDaAgora, escolha: Filtro = Filtro()) -> html.Section:
    """O ambiente é o do filtro no topo da tela."""
    return html.Section(
        [
            html.Header(
                [html.H2("O Verde nos últimos 8 dias"), html.Div("clique num dia ou numa cor", className="quadro-lateral")],
                className="quadro-topo",
            ),
            html.Div(conteudo_do_verde(dados.verde[dados.ambiente], dados.ambiente, None, dados.agora, escolha), id="agora-verde"),
        ],
        className="quadro",
    )


# ── Fluxos e como terminaram ──────────────────────────────────────────────

# Como a conversa terminou: o rótulo e o tom de cada fim, como na tela Fluxos.
FINS = {
    FimDaConversa.CONCLUIU: ("concluiu na Maria", "bom"),
    FimDaConversa.ENCAMINHOU: ("encaminhada a atendimento humano", "azul"),
    FimDaConversa.PAROU: ("parou no meio", "atencao"),
    FimDaConversa.EXPIROU: ("expirou", "ruim"),
}


def _fluxos(conversas: list[ConversasDoFluxo], tema: str | None, escolha: Filtro) -> list[Any]:
    """Cada fluxo numa barra, dividida por como as conversas terminaram. O clique filtra a tela pelo fluxo."""
    c = graficos.cores(tema)
    por_fluxo: dict[str, Counter[FimDaConversa]] = {}
    for conversa in conversas:
        por_fluxo.setdefault(conversa.fluxo, Counter())[conversa.fim] += conversa.conversas
    total = sum(sum(v.values()) for v in por_fluxo.values())
    if not total:
        return [html.P("Nenhuma conversa começou num fluxo.", className="texto-vazio")]
    ordem = sorted(por_fluxo, key=lambda f: sum(por_fluxo[f].values()))
    figura = go.Figure()
    for fim, (rotulo, tom) in FINS.items():
        figura.add_bar(
            x=[por_fluxo[f][fim] for f in ordem],
            y=[nome_do_fluxo(f) for f in ordem],
            orientation="h",
            name=rotulo,
            marker={"color": c[tom], "opacity": [1.0 if escolha.fluxo in (None, f) else filtro_de_dia.APAGADO for f in ordem]},
            customdata=[[rotulo, f"{filtro_de_dia.FLUXO}{f}"] for f in ordem],
            hovertemplate="%{y}: %{x} %{customdata[0]}<extra></extra>",
        )
    figura.update_layout(**graficos.layout_base(tema), barmode="stack", height=max(200, 70 + 40 * len(ordem)), separators=",.")
    figura.update_layout(margin={"l": 0, "r": 8, "t": 8, "b": 0})
    figura.update_xaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero")
    figura.update_yaxes(showgrid=False, fixedrange=True, automargin=True)
    encaminhadas = sum(v[FimDaConversa.ENCAMINHOU] for v in por_fluxo.values())
    mais = ordem[-1]
    resumo = (
        f"{nome_do_fluxo(mais)} recebe {round(sum(por_fluxo[mais].values()) / total * 100)}% das {numero(total)} conversas; "
        f"{numero(encaminhadas)} foram encaminhadas a atendimento humano."
    )
    legenda = html.Div([html.Span([html.Span(className=f"legenda-cor tom-{tom}"), rotulo]) for rotulo, tom in FINS.values()], className="legenda")
    return [
        filtro_de_dia.grafico("agora", "fluxos", figura, por="categoria"),
        legenda,
        html.P([resumo, " ", dcc.Link("Ver tudo na tela Fluxos", href="/fluxos")], className="lateral-resumo"),
    ]


# ── Montagem ──────────────────────────────────────────────────────────────


ID_DO_AMBIENTE = "agora-ambiente"
FILTRADO = (
    "Os atendimentos, o caminho do atendimento, os fluxos, como terminaram, o tempo de resposta, os erros, o que aconteceu e os gráficos de hora em hora "
    "mostram o que foi escolhido."
)
DE_AGORA = "A credencial, os incidentes, os dois ambientes, o que exige atenção e CPU e memória continuam sendo de agora."
filtro_de_dia.registrar("agora", FILTRADO, DE_AGORA)

Sinais = tuple[html.Section, html.Section, html.Section, html.Section, html.Section]


def _ambiente(valor: str | None) -> Ambiente:
    return Ambiente(valor or Ambiente.PRODUCAO.value)


def _sinais(tema: str | None, escolha: Filtro, ambiente: Ambiente = Ambiente.PRODUCAO) -> Sinais:
    """Os quadros com gráfico, que dependem do tema: atendimentos e requisições por
    hora, na largura inteira da tela; CPU e memória; os fluxos; como terminaram."""
    fonte, agora = obter_fonte(), datetime.now(FUSO)
    dia = escolha.dia or agora.date()
    quando = escolha.quando or dia
    horas = ler_ja(partial(fonte.atendimentos_por_hora, ambiente, dia))
    antes = ler_ja(partial(fonte.atendimentos_por_hora, ambiente, dia - timedelta(days=7)))
    pedidos = ler_ja(partial(fonte.requisicoes_por_hora, ambiente, escolha.dia))
    recursos = {a: ler_ja(partial(fonte.recursos_do_servico, a)) for a in Ambiente}
    fluxos = ler_ja(partial(fonte.conversas_por_fluxo, ambiente, quando))
    desfechos = ler_ja(partial(fonte.desfechos_do_dia, ambiente, quando))
    no_dia = "hoje" if escolha.dia in (None, agora.date()) else f"em {data_curta(escolha.dia)}"
    na_janela = "hoje" if escolha.quando in (None, agora.date()) else f"em {filtro_de_dia.rotulo(quando)}"
    nome = NOME_DO_AMBIENTE[ambiente].lower()
    leitura_de_antes = antes.result()
    comparar = leitura_de_antes.valor if leitura_de_antes.estado is Estado.OK else None
    return (
        lateral.bloco(
            f"Atendimentos por hora, {no_dia}",
            horas.result(),
            lambda v: lateral.barras_por_hora(v, tema, comparar, tela="agora", escolha=escolha, largo=True),
            f"Ninguém começou um atendimento {no_dia}.",
            agora,
            lateral=f"{nome}, com o mesmo dia da semana anterior; clique numa hora",
            extras=[leitura_de_antes],
        ),
        lateral.bloco(
            "Requisições por hora",
            pedidos.result(),
            lambda v: lateral.barras_de_requisicoes(v, tema, "agora", escolha, largo=True),
            "O balanceador não contou requisição nas últimas 24 horas." if escolha.dia is None else f"O balanceador não contou requisição {no_dia}.",
            agora,
            lateral=f"{nome}, com a varredura de robôs; clique numa hora",
        ),
        lateral.quadro_de_recursos({a: f.result() for a, f in recursos.items()}, agora),
        lateral.bloco(
            f"Fluxos {na_janela}",
            fluxos.result(),
            lambda v: _fluxos(v, tema, escolha),
            f"Nenhuma conversa começou num fluxo {na_janela}.",
            agora,
            lateral=f"{nome}; clique num fluxo",
        ),
        lateral.bloco(
            f"Como terminaram {na_janela}",
            desfechos.result(),
            lambda v: lateral.barras_de_desfechos(v, tema, "agora", escolha),
            f"Nenhum atendimento terminou {na_janela}.",
            agora,
            lateral=f"{nome}; clique num motivo",
        ),
    )


def _tela(escolha: Filtro, sinais: Sinais) -> html.Div:
    dados = ler_agora(escolha.quando)
    horas, pedidos, recursos, fluxos, desfechos = sinais
    return html.Div(
        [
            cabecalho(
                "Agora",
                f"Está funcionando? {dia_por_extenso(dados.agora)}",
                [html.Span("Ambiente", className="rotulo-filtro"), filtro_de_ambiente(ID_DO_AMBIENTE), acao_em_breve("Relatório do dia", "arquivo")],
            ),
            filtro_de_dia.armazem("agora", escolha),
            filtro_de_dia.faixa("agora", escolha),
            html.Div(indicadores(dados, escolha), id="agora-indicadores", className="grade-indicadores grade-quatro"),
            # De ponta a ponta: cada etapa do atendimento, se funciona ou não, e onde ver mais.
            html.Div(caminho_do_atendimento(dados), id="agora-caminho"),
            # O que pede atenção agora, ao lado do que já aconteceu no dia.
            html.Div([html.Div(exige_atencao(dados), id="agora-atencao"), html.Div(acontecimentos(dados), id="agora-acontecimentos")], className="grade-dupla"),
            # Dois quadros de altura parecida lado a lado, para não sobrar buraco.
            html.Div([html.Div(dois_ambientes(dados), id="agora-ambientes"), html.Div(recursos, id="agora-recursos")], className="grade-dois-tercos"),
            quadro_do_verde(dados, escolha),
            html.Div([html.Div(fluxos, id="agora-fluxos"), html.Div(desfechos, id="agora-desfechos")], className="grade-dupla"),
            # Os dois gráficos de hora em hora, na largura inteira: são os que pedem mais espaço.
            html.Div(horas, id="agora-horas"),
            html.Div(pedidos, id="agora-requisicoes"),
            html.Div(lista_de_fontes(dados.todas(), dados.agora), id="agora-fontes"),
        ],
        # Sem a coluna da direita: a Agora usa a largura toda.
        className="tela tela-larga",
    )


@callback(
    Output("agora-indicadores", "children"),
    Output("agora-caminho", "children"),
    Output("agora-atencao", "children"),
    Output("agora-acontecimentos", "children"),
    Output("agora-ambientes", "children"),
    Output("agora-fontes", "children"),
    Input("relogio", "n_intervals"),
    Input(ID_DO_AMBIENTE, "value"),
    filtro_de_dia.entrada("agora"),
    prevent_initial_call=True,
)
def atualizar(_: int, ambiente: str | None, guardado: Any) -> tuple[Any, ...]:
    escolha = filtro_de_dia.filtro(guardado)
    dados = ler_agora(escolha.quando, _ambiente(ambiente))
    return (
        indicadores(dados, escolha),
        caminho_do_atendimento(dados),
        exige_atencao(dados),
        acontecimentos(dados),
        dois_ambientes(dados),
        lista_de_fontes(dados.todas(), dados.agora),
    )


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador.
@callback(
    Output("agora-verde", "children"),
    Input("relogio", "n_intervals"),
    Input(ID_DO_AMBIENTE, "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada("agora"),
)
def atualizar_o_verde(_: int | None, ambiente: str | None, tema: str | None, guardado: Any) -> list[Any]:
    escolhido = _ambiente(ambiente)
    leitura = obter_fonte().verde_por_dia(escolhido)
    return conteudo_do_verde(leitura, escolhido, tema, leitura.lido_em, filtro_de_dia.filtro(guardado))


# Os quadros com gráfico: a cada minuto, com o tema guardado, o ambiente e o filtro.
@callback(
    Output("agora-horas", "children"),
    Output("agora-requisicoes", "children"),
    Output("agora-recursos", "children"),
    Output("agora-fluxos", "children"),
    Output("agora-desfechos", "children"),
    Input("relogio", "n_intervals"),
    Input(ID_DO_AMBIENTE, "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada("agora"),
)
def atualizar_os_sinais(_: int | None, ambiente: str | None, tema: str | None, guardado: Any) -> Sinais:
    return _sinais(tema, filtro_de_dia.filtro(guardado), _ambiente(ambiente))


def layout(dia: str | None = None, **_: str) -> html.Div:
    agora = datetime.now(FUSO)
    escolha = Filtro(filtro_de_dia.ler(dia, agora))
    # Os dias do gráfico do Verde, lidos por trás: o clique num deles já encontra a leitura.
    for passado in dias_passados(DIAS_DO_GRAFICO_DO_VERDE, agora):
        for consulta in (
            "resumo_do_dia",
            "atendimentos_por_hora",
            "requisicoes_por_hora",
            "tempo_de_resposta",
            "respostas_com_erro",
            "conversas_por_fluxo",
            "desfechos_do_dia",
            "sistema_no_dia",
            "triagem",
            "erros_da_ia",
            "envios_do_whatsapp",
        ):
            preparar(consulta, Ambiente.PRODUCAO, passado)
    sinais = montar_ja(partial(_sinais, None, escolha))
    return _tela(escolha, sinais.result())
