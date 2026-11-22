# EditalCheck — imagem de produção (frontend + API em um único contêiner).
#
# Estágio 1: compila o frontend (Vite + TypeScript) com o caminho base do proxy.
# Estágio 2: instala o backend (Python 3.12 + uv) e serve API + frontend na porta 8000.

########################### 1) FRONTEND
FROM node:22-bookworm-slim AS frontend

# Caminho público do app atrás do Traefik (ex.: atena.construtivo.com/editalcheck/).
ARG BASE_PATH=/editalcheck/

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
COPY frontend/scripts ./scripts
RUN npm ci --no-audit --no-fund

COPY frontend/ ./
RUN node scripts/copy-assets.mjs \
    && npx tsc --noEmit \
    && npx vite build --base="${BASE_PATH}"

########################### 2) BACKEND + APP
FROM python:3.12-slim-bookworm AS app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    TZ=America/Sao_Paulo

# libgomp1: usada pelo onnxruntime (dependência do PyMuPDF 2.x); tzdata: fuso de São Paulo.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.32

WORKDIR /app/backend
# Dependências primeiro (camada em cache enquanto o uv.lock não mudar).
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

WORKDIR /app
COPY data/demo ./data/demo
COPY --from=frontend /build/frontend/dist ./frontend/dist

# Usuário sem privilégios. As pastas var/ e .cache/ recebem volumes do host.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin editalcheck \
    && mkdir -p /app/var /app/.cache \
    && chown -R editalcheck:editalcheck /app/var /app/.cache

ENV PATH="/opt/venv/bin:${PATH}" \
    EDITALCHECK_DATA_DIR=/app/var \
    EDITALCHECK_CACHE_DIR=/app/.cache

USER editalcheck
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/config', timeout=4)"

CMD ["editalcheck", "servidor", "--host", "0.0.0.0", "--porta", "8000"]
