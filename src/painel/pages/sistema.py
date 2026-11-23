"""Tela Sistema: por que está assim?

Segue o rascunho: o tempo de resposta, quanto o Verde demora, se o Verde
falhou ou só não achou, cada parte da arquitetura (uso, demora, erros e custo),
as respostas com erro e as entregas e rotinas. O ambiente é filtro, no
cabeçalho, fora da área que se refaz a cada minuto. O gasto de IA dia a dia fica
no Relatório da Aplicação, e as requisições por hora, na Agora: aqui não se repetem.

Duas diferenças do rascunho, por falta de fonte:
- "Prazo para a Tykhe" não tem número: o contrato não define prazo
  (docs/contrato-tykhe.md), e o "10 s sugerido" do rascunho fica como pendência;
- o modelo de conversa e a busca por semelhança são da conta AWS inteira e não
  seguem o filtro de ambiente.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any

import dash
import plotly.graph_objects as go
from dash import Input, Output, callback, html

from painel import lateral
from painel.componentes import filtro_de_dia, graficos
from painel.componentes.blocos import (
    Tom,
    Valor,
    barra_rotulada,
    celula_de_leitura,
    indicador,
    lista_de_fontes,
    quadro,
)
from painel.componentes.cabecalho import cabecalho, filtro_de_ambiente
from painel.componentes.filtro_de_dia import Filtro
from painel.componentes.formato import contagem, data_curta, dinheiro, lista, numero, segundos
from painel.dados.modelo import FUSO, NOME_DO_AMBIENTE, Ambiente, CpuELatencia, DuracaoDoVerde, Estado, Leitura, RespostasComErro, ResultadoDoVerde, Rotina
from painel.dados.telas import LeiturasDoSistema, dias_passados, ler_sistema, montar_ja, preparar
from painel.lateral import coluna, com_lateral
from painel.precos import Parcela, parcelas

dash.register_page(__name__, path="/sistema", name="Sistema", order=3, title="Sistema · Visor Maria")

# TIMEOUT_VERDE_S em maria-langgraph-pp/src/maria/integracoes/verde.py: 30 s por tentativa.
PRAZO_DO_VERDE_S = 30.0
NOME_DA_CHAMADA = {
    "pessoa": "Pessoa presa, por RG",
    "processo": "Número de processo",
    "apenado": "Apenado",
    "cep": "Endereço, pelo CEP",
    "encaminhamento": "Encaminhamento",
    "cadastroPessoa": "Cadastro da pessoa",
}


def _janela(dados: LeiturasDoSistema, padrao: str) -> str:
    """A janela padrão do quadro ("nas últimas 24 horas") ou o dia escolhido num gráfico."""
    return padrao if dados.dia is None else f"em {filtro_de_dia.rotulo(dados.dia)}"


# ── Tempo de resposta ─────────────────────────────────────────────────────


def _indicadores(dados: LeiturasDoSistema) -> list[html.Section]:
    tempo = dados.tempo

    def valor(campo: str) -> Any:
        def montar() -> Valor:
            assert tempo.valor is not None
            return Valor(segundos(getattr(tempo.valor, campo)), unidade="s")

        return montar

    vazio = f"Nenhuma requisição {_janela(dados, 'nas últimas 24 horas')}."
    return [
        indicador("Metade responde até", "relogio", [tempo], valor("metade_ate"), vazio, dados.agora),
        indicador("Nove em dez até", "relogio", [tempo], valor("nove_em_dez_ate"), vazio, dados.agora),
        indicador("A mais lenta", "relogio", [tempo], valor("mais_lenta"), vazio, dados.agora),
        html.Section(
            [
                html.P("Prazo para a Tykhe", className="indicador-rotulo"),
                html.P("Não combinado", className="indicador-valor indicador-valor-texto"),
                html.P("O contrato não define prazo de resposta. O rascunho sugere 10 s.", className="indicador-legenda"),
                html.P(["sem prazo em ", html.Code("docs/contrato-tykhe.md")], className="fonte-curta"),
            ],
            className="indicador reservado",
        ),
    ]


# ── CPU e latência por hora (o que o Grafana mostrava) ────────────────────

# Os limites dos alertas do Grafana (infra/grafana/alerts/saude-operacional.json na
# maria-langgraph-pp, lido em 29/10): CPU acima de 80% por 5 min, p99 acima de 3 s por 15 min.
LIMITE_DA_CPU = 80.0
LIMITE_DO_P99 = 3.0
COR_DO_AMBIENTE: dict[Ambiente, Tom] = {Ambiente.PRODUCAO: "azul", Ambiente.RELEASE: "rosa"}


def _por_ambiente(linhas: list[CpuELatencia], campo: str, tema: str | None, escolha: Filtro, limite: float, sufixo: str, nome: str, casas: str) -> go.Figure:
    """Uma linha por ambiente, hora a hora, com a linha tracejada do limite do alerta."""
    c = graficos.cores(tema)
    figura = go.Figure()
    for ambiente in Ambiente:
        do_ambiente = [x for x in linhas if x.ambiente is ambiente]
        figura.add_scatter(
            x=[x.hora for x in do_ambiente],
            y=[getattr(x, campo) for x in do_ambiente],
            mode="lines+markers",
            line={"color": c[COR_DO_AMBIENTE[ambiente]]},
            # Pontos grandes: o clique numa hora filtra a tela.
            marker={"size": 8},
            name=NOME_DO_AMBIENTE[ambiente].lower(),
            customdata=[x.hora.isoformat() for x in do_ambiente],
            hovertemplate=f"%{{x|%Hh}}, {NOME_DO_AMBIENTE[ambiente].lower()}: {nome} %{{y:{casas}}}{sufixo}<extra></extra>",
        )
    figura.update_layout(**graficos.layout_base(tema), height=220, separators=",.")
    figura.update_xaxes(showgrid=False, fixedrange=True, tickformat="%Hh")
    figura.update_yaxes(showgrid=True, gridcolor=c["grade"], fixedrange=True, rangemode="tozero", ticksuffix=sufixo)
    valores = [v for x in linhas if (v := getattr(x, campo)) is not None]
    # O limite só entra no eixo quando os valores chegam perto dele: CPU de 0,5% contra 80% viraria uma linha reta.
    if max(valores, default=0) >= limite / 2:
        figura.add_hline(y=limite, line={"color": c["ruim"], "dash": "dash", "width": 1})
    escolhida = escolha.quando if isinstance(escolha.quando, datetime) else None
    if escolhida is not None:
        figura.add_vrect(x0=escolhida, x1=escolhida + timedelta(hours=1), fillcolor=c["suave"], opacity=0.18, line_width=0)
    return figura


def _resumo_da_cpu(linhas: list[CpuELatencia], ambiente: Ambiente) -> str:
    cpus = [x.cpu for x in linhas if x.ambiente is ambiente and x.cpu is not None]
    if not cpus:
        return f"{NOME_DO_AMBIENTE[ambiente]}: sem ponto de CPU."
    longe = " longe do" if max(cpus) < LIMITE_DA_CPU / 2 else " perto do" if max(cpus) <= LIMITE_DA_CPU else " acima do"
    return f"{NOME_DO_AMBIENTE[ambiente]}: até {segundos(max(cpus))}%,{longe} limite do alerta ({LIMITE_DA_CPU:.0f}%)."


def _resumo_do_p99(linhas: list[CpuELatencia], ambiente: Ambiente) -> str:
    lentas = [x for x in linhas if x.ambiente is ambiente and x.p99 is not None and x.p99 > LIMITE_DO_P99]
    if not lentas:
        return f"{NOME_DO_AMBIENTE[ambiente]}: sempre abaixo de {LIMITE_DO_P99:.0f} s."
    pior = max(lentas, key=lambda x: x.p99 or 0)
    assert pior.p99 is not None
    return f"{NOME_DO_AMBIENTE[ambiente]}: acima de {LIMITE_DO_P99:.0f} s em {contagem(len(lentas), 'hora', 'horas')}; o pior às {pior.hora:%H}h, {segundos(pior.p99)} s."


def _grafico_por_ambiente(
    dados: LeiturasDoSistema,
    tema: str | None,
    campo: str,
    titulo: str,
    limite: str,
    montar: Callable[[list[CpuELatencia]], go.Figure],
    resumo: Callable[..., str],
) -> html.Section:
    leitura = dados.cpu_e_latencia
    if leitura is None:
        return quadro(titulo, html.P("Esta leitura não entrou nesta rodada.", className="texto-vazio"), [], dados.agora)

    def corpo(linhas: list[CpuELatencia]) -> list[Any]:
        figura = montar(linhas)
        itens = [html.Span([html.Span(className=f"legenda-cor tom-{COR_DO_AMBIENTE[a]}"), NOME_DO_AMBIENTE[a].lower()]) for a in Ambiente]
        if any(forma.type == "line" for forma in figura.layout.shapes):
            itens.append(html.Span([html.Span(className="legenda-cor tom-ruim"), "limite do alerta"]))
        return [
            filtro_de_dia.grafico("sistema", campo, figura, por="hora"),
            html.Div(itens, className="legenda"),
            html.Div([html.P(resumo(linhas, a), className="quadro-explicacao") for a in Ambiente], className="miolo"),
        ]

    vazio = f"O ECS e o balanceador não mandaram ponto {_janela(dados, 'nas últimas 24 horas')}."
    return quadro(titulo, celula_de_leitura(leitura, corpo, vazio), [leitura], dados.agora, lateral=f"produção e release; {limite}; clique numa hora")


def _cpu_e_latencia(dados: LeiturasDoSistema, tema: str | None) -> html.Div:
    """Os dois gráficos que eram do Grafana (painel "Maria — Observabilidade"), com os dois ambientes."""
    quando = dados.dia
    escolha = Filtro(filtro_de_dia.dia_de(quando), quando.astimezone(FUSO).hour if isinstance(quando, datetime) else None)
    cpu = _grafico_por_ambiente(
        dados,
        tema,
        "cpu",
        "CPU do serviço por hora",
        f"alerta acima de {LIMITE_DA_CPU:.0f}%",
        lambda linhas: _por_ambiente(linhas, "cpu", tema, escolha, LIMITE_DA_CPU, "%", "CPU", ".1f"),
        _resumo_da_cpu,
    )
    p99 = _grafico_por_ambiente(
        dados,
        tema,
        "latencia",
        "Latência p99 do balanceador por hora",
        f"alerta acima de {LIMITE_DO_P99:.0f} s",
        lambda linhas: _por_ambiente(linhas, "p99", tema, escolha, LIMITE_DO_P99, " s", "p99", ".2f"),
        _resumo_do_p99,
    )
    return html.Div([cpu, p99], className="grade-dupla")


# ── Quanto o Verde demora ─────────────────────────────────────────────────


def _duracao(duracoes: list[DuracaoDoVerde]) -> list[Any]:
    linhas: list[Any] = [
        barra_rotulada(
            NOME_DA_CHAMADA.get(d.chamada, d.chamada),
            f"média {segundos(d.media)} s, máximo {segundos(d.maximo)} s",
            d.media / PRAZO_DO_VERDE_S,
            "bom" if d.maximo < PRAZO_DO_VERDE_S * 0.8 else "atencao",
            marca=d.maximo / PRAZO_DO_VERDE_S,
        )
        for d in sorted(duracoes, key=lambda d: -d.consultas)
    ]
    escala = html.Div([html.Span(f"{s} s") for s in (0, 10, 20, 30)], className="barra-escala mono")
    return [html.Div(linhas, className="lista-de-barras"), escala]


def _quanto_demora(dados: LeiturasDoSistema) -> html.Section:
    leitura = dados.duracao_do_verde
    corpo = celula_de_leitura(leitura, _duracao, f"Ninguém consultou o Verde {_janela(dados, 'nos últimos 7 dias')}.")
    return quadro("Quanto o Verde demora", html.Div(corpo, className="miolo"), [leitura], dados.agora, lateral=f"prazo de {int(PRAZO_DO_VERDE_S)} s")


# ── O Verde falhou, ou não achou? ─────────────────────────────────────────


def _falhou_ou_nao_achou(resultado: ResultadoDoVerde) -> html.Div:
    # A credencial e as buscas que não acharam a pessoa ficam sempre juntas:
    # em 22/10, o "não achou" subiu porque a credencial foi recusada.
    colunas = (
        ("Recusou a credencial", resultado.credencial_recusada, "problema nosso", "ruim"),
        ("Erro do próprio Verde", resultado.erro_do_verde, "problema do outro lado", "neutro"),
        ("Não achou a pessoa", resultado.nao_encontrado, "não é falha", "neutro"),
    )
    return html.Div(
        [
            html.Div(
                [
                    html.P(rotulo, className=f"coluna-rotulo tom-{tom if valor else 'neutro'}"),
                    html.P(numero(valor), className=f"numero-grande tom-{tom if valor else 'neutro'}"),
                    html.P(legenda, className="indicador-legenda"),
                ]
            )
            for rotulo, valor, legenda, tom in colunas
        ]
        + [html.P(f"{numero(resultado.aceitas)} consultas aceitas no mesmo período.", className="indicador-legenda rodape-do-trio")],
        className="trio",
    )


def _verde_falhou(dados: LeiturasDoSistema) -> html.Section:
    leitura = dados.resultado_do_verde
    corpo = celula_de_leitura(leitura, _falhou_ou_nao_achou, f"Ninguém consultou o Verde {_janela(dados, 'nos últimos 7 dias')}.")
    return quadro("O Verde falhou, ou não achou?", html.Div(corpo, className="miolo"), [leitura], dados.agora, lateral=_janela(dados, "últimos 7 dias"))


# ── Respostas com erro ────────────────────────────────────────────────────


def _erros(erros: RespostasComErro) -> html.Div:
    colunas = (
        ("4xx de gente", erros.de_gente, "neutro"),
        ("4xx de robô", erros.de_robo, "neutro"),
        ("5xx", erros.de_servidor, "ruim"),
    )
    return html.Div(
        [
            html.Div([html.P(rotulo, className="coluna-rotulo"), html.P(numero(valor), className=f"numero-grande tom-{tom if valor else 'neutro'}")])
            for rotulo, valor, tom in colunas
        ],
        className="trio",
    )


def _respostas_com_erro(dados: LeiturasDoSistema) -> html.Section:
    leitura = dados.erros
    explicacao = html.P(
        "Os erros 4xx incluem varredura de robô em caminhos como /.env e phpMyAdmin. Contados juntos, parecem problema e são ruído: "
        "por isso o robô fica numa coluna própria.",
        className="quadro-explicacao",
    )
    corpo = celula_de_leitura(leitura, _erros, f"Nenhuma resposta com erro {_janela(dados, 'nas últimas 24 horas')}.")
    return quadro("Respostas com erro", html.Div([explicacao, corpo], className="miolo"), [leitura], dados.agora, lateral=_janela(dados, "últimas 24 horas"))


# ── Cada parte da arquitetura ─────────────────────────────────────────────

NAO_MEDIDA = "não medida"


def _ok[T](leitura: Leitura[T] | None) -> T | None:
    """O valor de uma leitura que deu certo; nenhum, se faltou ou veio vazia."""
    return leitura.valor if leitura is not None and leitura.estado is Estado.OK else None


def _parte(nome: str, faz: str, uso: str, demora: str, erros: tuple[str, Tom], custo: str) -> html.Tr:
    texto, tom = erros
    return html.Tr(
        [
            html.Th([html.P(nome, className="etapa-nome"), html.P(faz, className="etapa-faz")], scope="row", className="com-explicacao"),
            html.Td(uso, className="etapa-detalhe"),
            html.Td(demora, className="etapa-detalhe"),
            html.Td(texto, className=f"etapa-detalhe tom-{tom}" if tom != "neutro" else "etapa-detalhe"),
            html.Td(custo, className="etapa-detalhe"),
        ]
    )


def _sem_leitura(leitura: Leitura[Any] | None) -> str:
    return "sem leitura" if leitura is None or leitura.estado is Estado.INDISPONIVEL else "nada na janela"


def _linhas_da_arquitetura(dados: LeiturasDoSistema) -> list[html.Tr]:
    janela_24h, janela_7d = _janela(dados, "em 24 horas"), _janela(dados, "em 7 dias")
    no_dia = "hoje" if dados.dia is None else f"em {data_curta(filtro_de_dia.dia_de(dados.dia) or dados.agora.date())}"
    dia = filtro_de_dia.dia_de(dados.dia) or dados.agora.date()
    linhas = []

    # O balanceador: o que chega, e o que volta com erro.
    pedidos, erros = _ok(dados.pedidos), _ok(dados.erros)
    uso = f"{numero(sum(h.requisicoes for h in pedidos))} requisições {janela_24h}" if pedidos else _sem_leitura(dados.pedidos)
    erro: tuple[str, Tom] = (
        (
            f"{contagem(erros.de_servidor, 'erro de servidor', 'erros de servidor')}; {numero(erros.de_robo)} recusas a robôs",
            "ruim" if erros.de_servidor else "bom",
        )
        if erros
        else (_sem_leitura(dados.erros), "neutro")
    )
    linhas.append(_parte("Balanceador", "recebe as mensagens da Tykhe e entrega aos containers", uso, NAO_MEDIDA, erro, "na fatura, a medir"))

    # Os containers da Maria.
    saude, recursos, tempo = _ok(dados.saude), _ok(dados.recursos), _ok(dados.tempo)
    uso = f"{saude.hosts_saudaveis} de {saude.hosts_desejados} containers no ar" if saude else _sem_leitura(dados.saude)
    if recursos:
        uso += f"; CPU até {round(recursos.cpu_maxima * 100)}% e memória até {round(recursos.memoria_maxima * 100)}% em 24 horas"
    demora = f"metade em até {segundos(tempo.metade_ate)} s, nove em dez em até {segundos(tempo.nove_em_dez_ate)} s" if tempo else _sem_leitura(dados.tempo)
    fora = saude.hosts_desejados - saude.hosts_saudaveis if saude else 0
    erro = (contagem(fora, "container fora do ar", "containers fora do ar"), "ruim") if fora else ("todos os containers respondem", "bom")
    nome = f"Maria, {'produção' if dados.ambiente is Ambiente.PRODUCAO else 'release'}"
    linhas.append(_parte(nome, "os containers que rodam a triagem e os fluxos (ECS)", uso, demora, erro, "na fatura, a medir"))

    # O banco que guarda onde cada conversa parou.
    resumo = _ok(dados.resumo)
    uso = f"{numero(resumo.comecaram)} conversas começaram {no_dia}" if resumo else _sem_leitura(dados.resumo)
    erro = (
        (
            contagem(resumo.sem_checkpoint, "conversa cortada na troca de versão", "conversas cortadas na troca de versão"),
            "atencao" if resumo.sem_checkpoint else "bom",
        )
        if resumo
        else (_sem_leitura(dados.resumo), "neutro")
    )
    linhas.append(_parte("Banco das conversas", "guarda onde cada conversa parou, para continuar depois", uso, NAO_MEDIDA, erro, "na fatura, a medir"))

    # O modelo de conversa e a busca por semelhança: o gasto do dia, da conta inteira.
    modelo = next((m for m in _ok(dados.modelo) or [] if m.dia == dia), None)
    gasto = _ok(dados.gasto)
    custo = parcelas(gasto) if gasto else None
    uso = f"{numero(modelo.chamadas)} chamadas {no_dia}, conta inteira" if modelo else _sem_leitura(dados.modelo)
    demora = f"{segundos(modelo.demora_media)} s por chamada, em média" if modelo else NAO_MEDIDA
    recusadas = modelo.erros_do_pedido + modelo.erros_do_servico + modelo.limitadas if modelo else 0
    erro = (contagem(recusadas, "chamada recusada", "chamadas recusadas"), "ruim" if recusadas else "bom") if modelo else (_sem_leitura(dados.modelo), "neutro")
    valor = dinheiro(custo[Parcela.LIDO] + custo[Parcela.ESCRITO]) + f" {no_dia}" if custo else _sem_leitura(dados.gasto)
    linhas.append(_parte("Modelo de conversa", "entende a pessoa e escreve as perguntas (Bedrock)", uso, demora, erro, valor))

    falhas = {e.funcao: e.falhas for e in _ok(dados.erros_da_ia) or [] if e.falhas}
    erro = (
        (f"{contagem(sum(falhas.values()), 'falha', 'falhas')}: {lista([f'{f} ({n})' for f, n in falhas.items()])}", "atencao")
        if falhas
        else ("nenhuma falha " + no_dia, "bom")
    )
    linhas.append(
        _parte(
            "Funções de IA da Maria",
            "classificar, extrair, reescrever, sumarizar e desambiguar",
            "dentro das chamadas ao modelo",
            NAO_MEDIDA,
            erro,
            "no modelo de conversa",
        )
    )
    uso = f"{numero(gasto.busca)} tokens {no_dia}, conta inteira" if gasto else _sem_leitura(dados.gasto)
    valor = dinheiro(custo[Parcela.BUSCA]) + f" {no_dia}" if custo else _sem_leitura(dados.gasto)
    linhas.append(
        _parte("Busca por semelhança", "acha o fluxo certo pelo texto livre (embeddings)", uso, NAO_MEDIDA, ("sem registro de erro próprio", "neutro"), valor)
    )

    # O Verde e a credencial das consultas.
    resultado, duracoes = _ok(dados.resultado_do_verde), _ok(dados.duracao_do_verde)
    if resultado:
        total = resultado.aceitas + resultado.credencial_recusada + resultado.erro_do_verde + resultado.nao_encontrado
        uso = f"{numero(total)} consultas {janela_7d}, {numero(resultado.aceitas)} aceitas"
        problemas = resultado.credencial_recusada + resultado.erro_do_verde
        erro = (
            f"{numero(resultado.credencial_recusada)} recusas da credencial; {numero(resultado.erro_do_verde)} erros do Verde",
            "ruim" if resultado.credencial_recusada else "atencao" if problemas else "bom",
        )
    else:
        uso, erro = _sem_leitura(dados.resultado_do_verde), (_sem_leitura(dados.resultado_do_verde), "neutro")
    if duracoes:
        consultas = sum(d.consultas for d in duracoes) or 1
        media = sum(d.media * d.consultas for d in duracoes) / consultas
        demora = f"{segundos(media)} s em média; a mais lenta, {segundos(max(d.maximo for d in duracoes))} s"
    else:
        demora = _sem_leitura(dados.duracao_do_verde)
    linhas.append(_parte("Verde", "consulta a pessoa, o processo, o endereço e faz o cadastro", uso, demora, erro, "sem custo por consulta"))
    credencial = _ok(dados.credencial)
    if credencial:
        faltam = (credencial.valida_ate.date() - dados.agora.date()).days
        uso = f"vale até {data_curta(credencial.valida_ate)}"
        erro = ("vencida", "ruim") if faltam < 0 else (f"vence em {contagem(faltam, 'dia', 'dias')}", "atencao" if faltam <= 7 else "bom")
    else:
        uso, erro = _sem_leitura(dados.credencial), (_sem_leitura(dados.credencial), "neutro")
    linhas.append(_parte("Credencial do Verde", "a chave das consultas, renovada pela conferência diária", uso, NAO_MEDIDA, erro, "sem custo"))

    # A saída: o WhatsApp, quando a Maria manda direto, e as rotinas do GitHub.
    envios = _ok(dados.envios) or []
    ok = sum(e.vezes for e in envios if e.evento == "whatsapp_envio_ok")
    falharam = sum(e.vezes for e in envios if e.evento != "whatsapp_envio_ok")
    uso = f"{numero(ok)} mensagens enviadas {no_dia}" if envios else f"nenhum envio direto {no_dia}; quem entrega é a Tykhe"
    erro = (contagem(falharam, "mensagem não entregue", "mensagens não entregues"), "atencao" if falharam else "bom") if envios else ("sem uso", "neutro")
    linhas.append(_parte("WhatsApp, envio direto", "manda a resposta à pessoa, no release", uso, NAO_MEDIDA, erro, "fora da AWS"))
    rotinas = _ok(dados.rotinas) or []
    quebradas = [r.nome for r in rotinas if r.falhando_desde is not None]
    erro = (f"falhando: {lista(quebradas)}", "ruim") if quebradas else ("todas passaram na última vez", "bom")
    linhas.append(
        _parte("GitHub", "testes, entregas e a conferência diária da credencial", f"{len(rotinas)} rotinas automáticas", NAO_MEDIDA, erro, "fora da AWS")
    )
    return linhas


def _arquitetura(dados: LeiturasDoSistema) -> html.Section:
    tabela = html.Table(
        [
            html.Thead(html.Tr([html.Th(t) for t in ("Parte", "Uso", "Demora", "Erros", "Custo")])),
            html.Tbody(_linhas_da_arquitetura(dados)),
        ],
        className="tabela tabela-do-caminho",
    )
    explicacao = html.P(
        "Cada peça por onde o atendimento passa, com o que dá para medir dela. O custo de servidores, balanceador e banco está na fatura da AWS, "
        "que o painel ainda não lê (pendência no Relatório da Aplicação); o modelo e a busca por semelhança são da conta inteira e não seguem o filtro.",
        className="quadro-explicacao miolo",
    )
    leituras: list[Leitura[Any]] = [x for x in dados.todas() if x is not dados.tokens]
    return quadro(
        "Cada parte da arquitetura", [explicacao, tabela], leituras, dados.agora, lateral=f"{'produção' if dados.ambiente is Ambiente.PRODUCAO else 'release'}"
    )


# ── Entregas e rotinas ────────────────────────────────────────────────────


def _leitura_da_rotina(rotina: Rotina, agora: Any) -> html.Td:
    if rotina.falhando_desde is not None:
        dias = (agora.date() - rotina.falhando_desde.date()).days
        return html.Td(f"falha todo dia há {contagem(dias, 'dia', 'dias')}", className="tom-ruim")
    if rotina.ultima_falha is not None and agora - rotina.ultima_falha < timedelta(days=7):
        return html.Td(f"voltou a passar; a última falha foi em {data_curta(rotina.ultima_falha)}", className="tom-atencao")
    if rotina.canceladas:
        return html.Td(f"{contagem(rotina.canceladas, 'cancelada', 'canceladas')} pela fila, o que é normal", className="tom-suave")
    return html.Td("saudável", className="tom-suave")


def _rotinas(dados: LeiturasDoSistema) -> html.Section:
    leitura = dados.rotinas

    def tabela(rotinas: list[Rotina]) -> html.Table:
        return html.Table(
            [
                html.Thead(html.Tr([html.Th("Rotina"), html.Th("Passaram", className="numero"), html.Th("Falharam", className="numero"), html.Th("Leitura")])),
                html.Tbody(
                    [
                        html.Tr(
                            [
                                html.Td(r.nome),
                                html.Td(numero(r.passaram), className="numero"),
                                html.Td(numero(r.falharam), className=f"numero {'tom-ruim' if r.falhando_desde else ''}"),
                                _leitura_da_rotina(r, dados.agora),
                            ]
                        )
                        for r in rotinas
                    ]
                ),
            ],
            className="tabela",
        )

    corpo = celula_de_leitura(leitura, tabela, "Nenhuma rotina rodou desde 19/09.")
    return quadro("Entregas e rotinas", corpo, [leitura], dados.agora, lateral="desde 19 de setembro")


# ── Montagem ──────────────────────────────────────────────────────────────


def blocos(ambiente: Ambiente, dia: date | None = None, tema: str | None = None) -> list[Any]:
    dados = ler_sistema(ambiente, dia)
    return [
        html.Div(_indicadores(dados), className="grade-indicadores grade-quatro"),
        _cpu_e_latencia(dados, tema),
        html.Div([_quanto_demora(dados), _verde_falhou(dados)], className="grade-dupla"),
        _arquitetura(dados),
        html.Div([_respostas_com_erro(dados), _rotinas(dados)], className="grade-dupla"),
        lista_de_fontes(dados.todas(), dados.agora),
    ]


FILTRADO = "O tempo de resposta, o Verde, cada parte da arquitetura, as respostas com erro, os erros por hora e a CPU e a latência mostram esse dia."
DE_AGORA = "As rotinas e CPU e memória continuam sendo de agora."
filtro_de_dia.registrar("sistema", FILTRADO, DE_AGORA)


def _tela(dia: date | None) -> html.Div:
    return html.Div(
        [
            cabecalho(
                "Sistema",
                "Por que está assim?",
                [html.Span("Ambiente", className="rotulo-filtro"), filtro_de_ambiente("sistema-ambiente")],
            ),
            filtro_de_dia.armazem("sistema", dia),
            filtro_de_dia.faixa("sistema", dia),
            html.Div(blocos(Ambiente.PRODUCAO, dia), id="sistema-corpo", className="tela-corpo"),
        ],
        className="tela",
    )


# Sem prevent_initial_call: na subida, aplica o tema guardado no navegador aos gráficos.
@callback(
    Output("sistema-corpo", "children"),
    Input("relogio", "n_intervals"),
    Input("sistema-ambiente", "value"),
    Input("tema", "data"),
    filtro_de_dia.entrada("sistema"),
)
def atualizar(_: int | None, ambiente: str | None, tema: str | None, dia: str | None) -> list[Any]:
    return blocos(Ambiente(ambiente or Ambiente.PRODUCAO.value), filtro_de_dia.escolhido(dia), tema)


def layout(dia: str | None = None, **_: str) -> html.Div:
    agora = datetime.now(FUSO)
    escolhido = filtro_de_dia.ler(dia, agora)
    # Os 14 dias do gráfico da IA, lidos por trás: o clique num deles já encontra a leitura.
    for passado in dias_passados(14, agora):
        for consulta in ("tempo_de_resposta", "duracao_do_verde", "resultado_do_verde", "respostas_com_erro", "requisicoes_por_hora"):
            preparar(consulta, Ambiente.PRODUCAO, passado)
        preparar("cpu_e_latencia", passado)
    lado = montar_ja(partial(lateral.do_sistema, Ambiente.PRODUCAO, None, Filtro(escolhido)))
    return com_lateral(_tela(escolhido), coluna("sistema-lateral", lado.result()))


# A coluna da direita: a cada minuto, com o tema guardado e com o filtro da tela.
@callback(
    Output("sistema-lateral", "children"),
    Input("relogio", "n_intervals"),
    Input("tema", "data"),
    Input("sistema-ambiente", "value"),
    filtro_de_dia.entrada("sistema"),
)
def atualizar_a_lateral(_: int | None, tema: str | None, filtro: str | None, dia: str | None) -> list[Any]:
    return lateral.do_sistema(Ambiente(filtro or Ambiente.PRODUCAO.value), tema, filtro_de_dia.filtro(dia))
