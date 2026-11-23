# Deploy em produção

A imagem `py3_12-ifcopenshell.Dockerfile` é autocontida. Ela traz Python 3.12 com as dependências travadas no `uv.lock`, o código do backend, os prompts, os recursos, os dados de demonstração e o frontend compilado. O contêiner não precisa do repositório montado.

O repositório traz só o [`docker-compose.local.yml`](../docker-compose.local.yml), para rodar na máquina. O compose de produção (proxy, domínio e volumes) fica no servidor, fora do Git.

## Gerar a imagem

```bash
docker build -f py3_12-ifcopenshell.Dockerfile --build-arg BASE_PATH=/editalcheck/ -t editalcheck .
```

`BASE_PATH` é o caminho público do app. Use `/` quando o app ficar na raiz do domínio.

## Atrás de um proxy reverso com prefixo

Exemplo: o app em `https://seu-dominio/editalcheck/`.

1. Gere a imagem com `BASE_PATH=/editalcheck/`. Assets, wasm, worker e chamadas à API ficam sob o prefixo.
2. Configure o proxy para remover o prefixo (no Traefik, `stripprefix`) e repassar à porta 8000.
3. Defina `EDITALCHECK_ROOT_PATH=/editalcheck`. Assim o `/docs` funciona atrás do proxy, se estiver ligado.
4. Defina `FORWARDED_ALLOW_IPS` com o IP do proxy (ou `*`, se só o proxy alcança o contêiner). O uvicorn passa a confiar nos cabeçalhos `X-Forwarded-*` dele.
5. Use uma réplica só ou sessão fixa (*sticky session*) no proxy. No modo efêmero, cada projeto vive na memória de um processo.

## Variáveis de ambiente de produção

| Variável | Valor recomendado | Para quê |
|---|---|---|
| `GEMINI_API_KEY` | chave do Google AI Studio | Liga a IA. Sem chave, o app usa regras determinísticas |
| `EDITALCHECK_MODO_DADOS` | `efemero` | Arquivos e relatórios só na memória |
| `EDITALCHECK_DOCS` | `false` | Desliga `/docs`, `/redoc` e `/openapi.json` |
| `EDITALCHECK_ROOT_PATH` | o prefixo do proxy | `/docs` atrás do proxy |
| `FORWARDED_ALLOW_IPS` | IP do proxy | Confia nos `X-Forwarded-*` do proxy |
| `EDITALCHECK_TTL_MIN` | `120` | Minutos sem uso até um projeto sair da memória |
| `LIMITE_UPLOAD_MB` | `200` | Tamanho máximo de cada arquivo |
| `LLM_TIMEOUT_S` | `300` | Tempo máximo de cada chamada ao LLM |
| `LLM_PARALELISMO` | `6` | Chamadas simultâneas ao LLM. Reduza se a cota recusar |
| `EDITALCHECK_DISPONIVEL_ATE` | DD/MM/AAAA ou vazio | Data de desligamento na faixa do topo (ambiente de demonstração) |
| `LLM_PRECO_ENTRADA_USD_MTOK`, `LLM_PRECO_SAIDA_USD_MTOK`, `LLM_PRECO_FONTE` | preços oficiais do modelo | Custo em dólares no painel "Custo e tempo" |

A lista completa, com comentários, está no [`.env.example`](../.env.example).

## Segurança do contêiner

A imagem já roda com o usuário `app` (uid 1000). No compose do servidor, complete o endurecimento:

```yaml
services:
  app:
    image: editalcheck
    read_only: true                    # sistema de arquivos só leitura
    tmpfs:
      - /tmp:size=1g,mode=1777         # uploads grandes passam por /tmp (em memória)
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    volumes:
      - auditoria:/app/var/auditoria   # log de auditoria, sem conteúdo do usuário
      - bsdd:/app/.cache/bsdd          # cache do bSDD (dados públicos)
    deploy:
      resources:
        limits: {cpus: "4", memory: 6g}
    logging:
      driver: json-file
      options: {max-size: "10m", max-file: "5"}
volumes:
  auditoria:
  bsdd:
```

O healthcheck da imagem consulta `/api/saude`. Cada resposta traz um `X-Request-ID`, que também aparece no log.

## Atualizar

```bash
git pull && docker compose build && docker compose up -d
```

## Operação

- **Logs:** `docker compose logs -f app`.
- **Status:** `docker compose ps` mostra `healthy` quando `/api/saude` responde.
- **Auditoria:** `docker compose exec app tail /app/var/auditoria/auditoria.jsonl`.
- **Dados:** no modo efêmero, um reinício do contêiner apaga os projetos em andamento.
- **Documentos de referência:** para usar documentos de contexto do LLM, copie-os para `backend/resources/contexto/` antes do build. Veja o [LEIA-ME da pasta](../backend/resources/contexto/LEIA-ME.md).

---

[← Índice da documentação](README.md) · [README do projeto](../README.md)
