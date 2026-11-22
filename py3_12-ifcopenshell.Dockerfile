# EditalCheck: ambiente de execução (Python 3.12 + IfcOpenShell + frontend compilado).
#
# Mesmo padrão dos serviços da Atena: a imagem guarda só o ambiente.
# O código do backend entra pelo volume ".:/workspace" do docker-compose.yml.
#   - Mudou o backend: git pull e recrie o contêiner (o build usa o cache).
#   - Mudou o frontend ou as dependências: o build refaz só a camada afetada.

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

########################### 2) PYTHON 3.12 + DEPENDÊNCIAS
FROM python:3.12-slim-bookworm

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

# Dependências do backend, travadas pelo uv.lock (o pacote editalcheck vem do volume).
WORKDIR /opt/editalcheck
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Frontend compilado. Fica fora de /workspace para o volume não escondê-lo.
COPY --from=frontend /build/frontend/dist /opt/editalcheck/frontend

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONPATH=/workspace/backend/src \
    EDITALCHECK_FRONTEND_DIR=/opt/editalcheck/frontend

WORKDIR /workspace
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/config', timeout=4)"

CMD [ "python", "-m", "editalcheck.entrypoints.cli", "servidor", "--host", "0.0.0.0", "--porta", "8000" ]
