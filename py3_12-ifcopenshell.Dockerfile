# syntax=docker/dockerfile:1
# EditalCheck: imagem de produção autocontida (Python 3.12 + IfcOpenShell + frontend compilado).
#
# Código, prompts, recursos, dados de demonstração e frontend compilado ficam dentro da imagem.
# O contêiner roda com um usuário sem privilégios e não precisa do repositório montado.
# Para atualizar no servidor:
#   git pull && docker compose build && docker compose up -d

########################### 1) FRONTEND
FROM node:22.23.5-bookworm-slim AS frontend

# Caminho público do app atrás do Traefik (ex.: atena.construtivo.com/editalcheck/).
ARG BASE_PATH=/editalcheck/

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts ./scripts
RUN --mount=type=cache,target=/root/.npm npm ci --no-audit --no-fund

COPY frontend/ ./
# O build confere os tipos (tsc) e gera o frontend com o caminho base do proxy.
RUN BASE_PATH="${BASE_PATH}" npm run build

########################### 2) BACKEND
FROM python:3.12.16-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    TZ=America/Sao_Paulo

# libgomp1: usada pelo onnxruntime (dependência do PyMuPDF 2.x); tzdata: fuso de São Paulo.
# Usuário "app" (uid 1000), sem shell e sem privilégios.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --no-create-home --home-dir /tmp --shell /usr/sbin/nologin app

# Dependências primeiro (camada reaproveitada enquanto o uv.lock não muda), depois o código.
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY backend/src ./src
COPY backend/prompts ./prompts
COPY backend/resources ./resources
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

COPY data/demo /app/data/demo
COPY --from=frontend /build/frontend/dist /app/frontend

# Únicas pastas graváveis (volumes no compose): log de auditoria sem conteúdo e cache do bSDD.
RUN mkdir -p /app/var/auditoria /app/.cache/bsdd && chown -R app:app /app/var /app/.cache

ENV PATH="/opt/venv/bin:${PATH}" \
    EDITALCHECK_FRONTEND_DIR=/app/frontend \
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp/.cache

USER app
WORKDIR /app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/saude', timeout=4)"]

CMD ["python", "-m", "editalcheck.entrypoints.cli", "servidor", "--host", "0.0.0.0", "--porta", "8000"]
