# Desenvolvimento

## Rodar com Docker

O jeito mais rápido. Precisa só do Docker.

```bash
docker compose -f docker-compose.local.yml up --build
```

Abra http://localhost:8000. Para usar o Gemini, copie `.env.example` para `.env` e preencha `GEMINI_API_KEY` antes de subir.

## Rodar sem Docker

Pré-requisitos: Python 3.12 com [uv](https://docs.astral.sh/uv/) e Node.js 20.19+ ou 22.12+ (exigência do Vite 7).

1. Instale o backend:

```powershell
cd backend; uv sync
```

2. Instale e compile o frontend:

```powershell
cd frontend; npm install; npm run build
```

3. (Opcional) Configure o Gemini. Copie `.env.example` para `.env` e preencha `GEMINI_API_KEY`. Com o Gemini, `LLM_PARALELISMO` (padrão 6) define quantas chamadas rodam ao mesmo tempo. Reduza esse valor se a cota do seu plano recusar requisições. Para o painel "Custo e tempo" mostrar dólares, preencha `LLM_PRECO_ENTRADA_USD_MTOK`, `LLM_PRECO_SAIDA_USD_MTOK` e `LLM_PRECO_FONTE` com os preços oficiais do modelo.

4. Suba a aplicação e abra http://127.0.0.1:8000:

```powershell
cd backend; uv run editalcheck servidor
```

Clique em **Usar dados de exemplo (com lições)** para rodar a demo. Ela inclui o caso da sala de baterias: o edital exige iluminação natural em todos os ambientes, a lição aprendida proíbe janelas nessa sala, e o modelo já tem duas janelas lá.

## CLI (sem interface)

```powershell
cd backend; uv run editalcheck demo
```

Outros comandos: `topicos <pdf>`, `modelo <ifc>`, `pipeline --edital <pdf> --modelo <ifc> [--licoes <txt|md|pdf>] [--topicos 5.1,5.2] [--gabarito <json>]` e `gerar-demo`. O `pipeline` grava em `--saida` o relatório (JSON e HTML), o BCF, o IDS, a planilha dos IR, o edital anotado e a matriz de esclarecimentos.

## Testes

```powershell
cd backend; uv run ruff check src tests; uv run pytest
```

O CI (`.github/workflows/ci.yml`) roda o lint e os testes do backend, o build do frontend (com checagem de tipos) e o build da imagem Docker a cada push e pull request.

Desenvolvimento do frontend com recarga automática: rode `npm run dev` em `frontend/`. O Vite redireciona `/api` para `127.0.0.1:8000`.

Teste de ponta a ponta do visualizador 3D (precisa do Playwright e do servidor no ar): `node scripts/e2e-ida-e-volta.mjs` em `frontend/`.

## API

Contrato em [Contrato da API](api.md). Documentação OpenAPI em `/docs` com o servidor no ar.

---

[← Índice da documentação](README.md) · [README do projeto](../README.md)
