"""Regras e cores de gráfico que valem para todas as telas.

Produção trocou de versão em 23/10, às 12:31 (Brasília): TypeScript antes,
Python depois. Toda série que cruza esse horário leva uma marca vertical nele,
porque alguns números mudam de sentido no corte (antes dele, "RG não encontrado"
inclui as recusas de credencial do incidente de 22 e 23/10).

As cores dos gráficos repetem as de painel.css: o Plotly não lê variáveis CSS,
então o gráfico é refeito quando o tema muda. Mudou uma, mude a outra.
"""

from __future__ import annotations

from datetime import datetime

import plotly.graph_objects as go

from painel.dados.modelo import FUSO

CORTE_DE_VERSAO = datetime(2026, 10, 23, 12, 31, tzinfo=FUSO)
TEXTO_DO_CORTE = "Versão Python a partir daqui"

CORES = {
    "escuro": {
        "texto": "#e8ece9",
        "suave": "#8b9590",
        "grade": "#1f2925",
        "bom": "#3ddc84",
        "ruim": "#ff6b5e",
        "atencao": "#f5b731",
        "outro": "#56615c",
        "azul": "#3bbfd8",
        "rosa": "#e05a8f",
    },
    "claro": {
        "texto": "#131a17",
        "suave": "#5b665f",
        "grade": "#e1e6e3",
        "bom": "#1f9d5c",
        "ruim": "#d6453a",
        "atencao": "#b7791f",
        "outro": "#a9b3ad",
        "azul": "#1b8aa3",
        "rosa": "#c23b72",
    },
    "noturno": {
        "texto": "#e6d9c3",
        "suave": "#9a8f7c",
        "grade": "#2a241c",
        "bom": "#7cc48f",
        "ruim": "#e0786a",
        "atencao": "#e0b45a",
        "outro": "#5c5446",
        "azul": "#7fb3c2",
        "rosa": "#d68aa3",
    },
}
TEMA_PADRAO = "escuro"


def cores(tema: str | None) -> dict[str, str]:
    return CORES.get(tema or TEMA_PADRAO, CORES[TEMA_PADRAO])


def cruza_o_corte(inicio: datetime, fim: datetime) -> bool:
    return inicio <= CORTE_DE_VERSAO <= fim


def marcar_corte_de_versao(figura: go.Figure, inicio: datetime, fim: datetime, cor: str = "#8b9590") -> go.Figure:
    if cruza_o_corte(inicio, fim):
        figura.add_vline(x=CORTE_DE_VERSAO, line_dash="dot", line_width=1, line_color=cor)
        figura.add_annotation(
            x=CORTE_DE_VERSAO,
            y=1,
            yref="paper",
            text=TEXTO_DO_CORTE,
            showarrow=False,
            xanchor="left",
            yanchor="bottom",
            font={"size": 11, "color": cor},
        )
    return figura


def layout_base(tema: str | None) -> dict[str, object]:
    c = cores(tema)
    return {
        "paper_bgcolor": "rgba(0,0,0,0)",
        "plot_bgcolor": "rgba(0,0,0,0)",
        "font": {"family": "Archivo, system-ui, sans-serif", "color": c["suave"], "size": 12},
        "margin": {"l": 0, "r": 0, "t": 22, "b": 0},
        "showlegend": False,
        "hoverlabel": {"font": {"family": "Archivo, system-ui, sans-serif"}},
    }
