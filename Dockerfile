# Visor Maria (Dash + Plotly). Mesmo padrão do Dockerfile da maria-langgraph-pp:
# Python 3.12, uv fixado por versão, dependências antes do código.
FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /usr/local/bin/uv

FROM base AS deps
COPY pyproject.toml uv.lock .python-version README.md ./
RUN uv sync --frozen --no-dev --no-install-project

FROM deps AS build
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

FROM python:3.12-slim AS runner
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    PAINEL_FONTE=real
COPY --from=build /app/.venv ./.venv
# Com pasta própria: o gunicorn 26 grava o socket do servidor de controle em $HOME.
RUN useradd --system --create-home painel
USER painel
EXPOSE 8050
# O painel não guarda estado no processo: mais de um worker é seguro.
# Prazo de 120 s: a primeira abertura de uma tela, com o cache vazio, faz as consultas
# reais de uma vez (alguns segundos cada, até 8 juntas).
CMD ["gunicorn", "painel.app:server", "--bind", "0.0.0.0:8050", "--workers", "2", "--timeout", "120"]
