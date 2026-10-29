"""O gráfico do Verde nos últimos 8 dias: os resultados das consultas por dia (RESULTADOS_DO_VERDE).

Fica fora da tela para poder ser testado sem registrar a página de novo. A marca
do corte de versão só vale para produção.
"""

from __future__ import annotations

from datetime import datetime, time

import plotly.graph_objects as go

from painel.componentes import graficos
from painel.dados.modelo import FUSO, RESULTADOS_DO_VERDE, Ambiente, DiaDoVerde


def figura_do_verde(dias_do_verde: list[DiaDoVerde], ambiente: Ambiente, tema: str | None) -> go.Figure:
    c = graficos.cores(tema)
    meio_dia = [datetime.combine(d.dia, time(12), tzinfo=FUSO) for d in dias_do_verde]
    figura = go.Figure()
    for campo, nome, tom, _ in RESULTADOS_DO_VERDE:
        figura.add_bar(
            x=meio_dia,
            y=[getattr(d, campo) for d in dias_do_verde],
            name=nome,
            marker_color=c[tom],
            width=0.72 * 86_400_000,
            hovertemplate=f"%{{x|%d/%m}}: %{{y}}, {nome.lower()}<extra></extra>",
        )

    def cor_do_dia(d: DiaDoVerde) -> str:
        if d.total and d.recusadas > 0.3 * d.total:
            return c["ruim"]
        return c["atencao"] if d.recusadas else c["suave"]

    figura.update_layout(
        **graficos.layout_base(tema),
        barmode="stack",
        barcornerradius=3,
        height=200,
        xaxis={
            "tickvals": meio_dia,
            "ticktext": [f"<span style='color:{cor_do_dia(d)}'>{d.dia.day}</span>" for d in dias_do_verde],
            "showgrid": False,
            "fixedrange": True,
        },
        yaxis={"visible": False, "fixedrange": True},
    )
    # O corte de 23/10, 12:31 é da produção; o release já rodava Python desde 21/10.
    if ambiente is not Ambiente.PRODUCAO:
        return figura
    inicio = datetime.combine(dias_do_verde[0].dia, time(), tzinfo=FUSO)
    fim = datetime.combine(dias_do_verde[-1].dia, time(23, 59), tzinfo=FUSO)
    return graficos.marcar_corte_de_versao(figura, inicio, fim, c["suave"])
