# EditalCheck — verificador bidirecional Edital × IFC

> Hackathon Open BIM + IA · Sinaenco · 22–23/11/2026. Nome do produto provisório.

O EditalCheck transforma as exigências de um edital, escritas em linguagem natural, num **contrato de dados** operacional: os **requisitos de informação (RI)** e o **IDS**. Depois, verifica o modelo IFC contra esse contrato e o edital contra boas práticas. O objetivo é chegar a um **consenso** entre contratante e contratado antes que o problema chegue à obra.

Entradas: **edital em PDF**, **modelo IFC** (opcional) e **lições aprendidas** em TXT ou PDF (opcional, ciclo PDCA).

1. **O IFC cumpre o edital?** O sistema extrai os RI do edital e das lições aprendidas. Uma pessoa revisa e aprova. O sistema gera o **IDS** por código, para o contrato inteiro ou para um marco de entrega, e valida o IFC.
2. **O edital está bom?** O sistema aponta termos vagos, requisitos não verificáveis, itens mínimos ausentes, contradições, texto repetido e lições aprendidas que o edital não explicita.
3. **O edital cobre o modelo?** O sistema mede quanto do modelo o edital especifica e sugere requisitos com Psets oficiais para as lacunas.

Cada apontamento diz **onde está o problema** (no **edital**, o contratante corrige; no **modelo**, o contratado corrige), **o que** está errado, **onde** (página e/ou GlobalId com coordenada XYZ), **como agir** e **por que**. Cada parte registra a decisão (aceito, rejeitado, em discussão, dispensado). Os apontamentos do modelo aparecem num **visualizador 3D** e num **BCF**. Os do edital saem num **edital anotado em PDF** e numa **matriz de esclarecimentos**.

**Edital na tela (só leitura).** O edital em PDF aparece em dois momentos:

- **Antes de gerar os RI:** o PDF mostra os tópicos selecionados grifados e, tracejados, os relevantes para BIM que ficaram de fora. Dá para marcar ou desmarcar ali mesmo e voltar.
- **Nos resultados (aba "Edital com os ajustes"):** o PDF fica à esquerda, com um grifo por apontamento, e os ajustes à direita. Clicar num ajuste leva ao trecho e abre o detalhe; clicar num grifo abre o ajuste. O relatório HTML tem um link "Ver no edital" em cada apontamento.

O **PDF com as sugestões** traz o mesmo conteúdo para uso sem o sistema: sumário com links para cada trecho, grifos com notas, etiquetas na margem que voltam ao sumário, links para buildingSMART e bSDD e um índice lateral (bookmarks) separado em "Corrigir no edital" e "Corrigir no modelo".

> Sem IFC, o sistema revisa só o edital. Esse é o uso do contratante antes de publicar a licitação.

**Tese:** a IA interpreta o texto. Tudo o que precisa ser exato (IDS, validação, BCF, métricas) é código determinístico sobre padrões abertos. Toda citação da IA é conferida literalmente contra o texto do PDF.

## Padrões Open BIM usados

| Padrão / serviço | Uso |
|---|---|
| **IFC** (IFC2X3, IFC4, IFC4X3) | Entrada do modelo, classes, Psets, GlobalIds e saúde do modelo |
| **IDS 1.0** | Contrato de dados gerado dos requisitos de informação (RI) aprovados, com `purpose` e `milestone`, validado contra o XSD oficial e usado na verificação |
| **BCF 2.1** | Um tópico por apontamento do modelo, com um viewpoint por elemento (seleção, destaque em vermelho e câmera enquadrando o elemento), uma visão geral e um comentário ligado a cada viewpoint |
| **bSDD** | URIs de propriedades e busca de termos (API REST pública) |
| **Psets oficiais** | Vocabulário controlado dos requisitos e das sugestões de lacuna |
| **IDM** (ISO 29481-1:2025) | Mapa de processo: atores, marcos de entrega e trocas de informação ([docs/idm.md](docs/idm.md)) |
| **ISO 19650** | Inspiração da checklist do edital e dos termos de requisitos de informação |

## Arquitetura

Arquitetura hexagonal. O domínio não importa FastAPI, IfcOpenShell nem SDK de LLM.

```
entrypoints/   FastAPI (api/) e CLI Typer (cli.py)
application/   casos de uso + portas (typing.Protocol) + salvaguardas + medição de consumo
domain/        entidades e regras puras: evidência (S2), tópicos, termos vagos, cobertura,
               severidade, origem, checklist, apontamentos, lições aprendidas, marcos,
               versão IFC, texto repetido, indicadores e custo
adapters/      PyMuPDF (leitura e edital anotado) · IfcOpenShell (modelo e geometria) ·
               ifctester (IDS) · bcf-client (BCF) · Gemini · regras offline · bSDD (httpx) ·
               Jinja2 · openpyxl · memória (modo efêmero) · arquivos · auditoria JSONL
```

Salvaguardas contra alucinação (todas por código):

| # | Salvaguarda | Onde |
|---|---|---|
| S1 | Saída do LLM valida no schema Pydantic; até 2 reparos | `adapters/llm/structured.py` |
| S2 | Trecho citado existe na página (normaliza espaços, hifenização, caixa) | `domain/evidence.py` |
| S3 | Classe IFC existe no schema do modelo | `application/use_cases/gerar_eir.py` |
| S4 | Propriedade é Pset oficial, bSDD ou marcada como customizada | `domain/vocabulary.py` |
| S5 | Recomendações só citam referências da lista fechada | `domain/vocabulary.py` |
| S6 | IDS gerado valida no XSD do IDS 1.0 e recarrega no ifctester | `adapters/ids/ifctester_builder.py` |
| G1 | Lições aprendidas e documentos de referência só **acrescentam** apontamentos | `application/use_cases/executar_verificacao.py` |
| G2 | Rejeitar ou dispensar um apontamento exige justificativa; o dispensado continua no relatório | `domain/models.py` (`DecisaoApontamento`) |
| G3 | Textos de usuário vão ao LLM entre delimitadores, como dado; o prompt manda ignorar instruções neles | `prompts/sistema.md` |

## Tratamento de dados (LGPD)

- **Modo efêmero (padrão).** Edital, IFC, lições, RI, IDS, relatórios e BCF ficam só na memória do servidor. Nada é gravado em disco. Os dados somem quando o usuário clica em **Encerrar e apagar dados**, após 120 minutos sem uso (`EDITALCHECK_TTL_MIN`) ou quando o processo reinicia.
- **Sem cache do LLM em disco** no modo efêmero: as respostas trazem trechos do edital.
- **Log de auditoria sem conteúdo** (`var/auditoria/auditoria.jsonl`): data, etapa, ID aleatório do projeto, tamanhos e status. Nunca guarda texto de documento.
- **Aviso antes da IA.** A interface informa que trechos são enviados à API paga do Google Gemini, que não usa esses dados para treinar modelos.
- **Validação humana no meio do fluxo:** nenhum requisito vira IDS sem aprovação de uma pessoa.
- O modo `persistente` grava em `var/` e serve só para desenvolvimento.

**Modo offline:** sem chave do Gemini, ou se o LLM falhar, o sistema usa regras determinísticas (extrator por vocabulário, léxico de termos vagos, checklist por padrões). A demo nunca fica sem resposta (RNF-02).

## Como rodar

Pré-requisitos: Python 3.12 com [uv](https://docs.astral.sh/uv/) e Node.js 20 ou superior.

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

### CLI (sem interface)

```powershell
cd backend; uv run editalcheck demo
```

Outros comandos: `topicos <pdf>`, `modelo <ifc>`, `pipeline --edital <pdf> --modelo <ifc> [--licoes <txt|pdf>] [--topicos 5.1,5.2] [--gabarito <json>]` e `gerar-demo`. O `pipeline` grava em `--saida` o relatório (JSON e HTML), o BCF, o IDS, a planilha dos RI, o edital anotado e a matriz de esclarecimentos.

### Testes

```powershell
cd backend; uv run pytest
```

Desenvolvimento do frontend com recarga automática: rode `npm run dev` em `frontend/`. O Vite redireciona `/api` para `127.0.0.1:8000`.

## Deploy no servidor (Docker + Traefik)

O deploy segue o padrão dos serviços da Atena:
- O `docker-compose.yml` monta o repositório em `/workspace` e roda o backend direto do código (`python -m editalcheck.entrypoints.cli servidor`).
- A imagem (`py3_12-ifcopenshell.Dockerfile`) guarda só o ambiente: Python 3.12, as dependências travadas no `uv.lock` e o frontend compilado.
- O Traefik da rede `proxy` publica o app em **https://atena.construtivo.com/editalcheck/**.

Como o roteamento funciona:
- O roteador aceita `Host(APP_DOMAIN) && PathPrefix(/editalcheck)`, remove o prefixo (`stripprefix`) e repassa à porta 8000.
- O frontend é compilado com `--base=/editalcheck/`. Assets, wasm, worker e chamadas à API ficam sob o prefixo.
- `EDITALCHECK_ROOT_PATH=/editalcheck` faz o `/docs` da API funcionar atrás do proxy.

Primeira instalação, no servidor:

1. Clone o repositório na pasta do projeto e entre nele.

```bash
cd /mnt/dados/atena/projects/hackathon
git clone https://github.com/Luis01Felipe/hackathon.git
cd hackathon
```

2. Crie o arquivo de variáveis e preencha a `GEMINI_API_KEY`.

```bash
cp .env.deploy.example .env.deploy && nano .env.deploy
```

3. Suba o contêiner.

```bash
docker compose up -d --build
```

Para atualizar depois de um merge:

```bash
git pull && docker compose up -d --build --force-recreate
```

O `--force-recreate` reinicia o app com o backend novo, que vem do volume. O build só refaz o frontend ou as dependências quando eles mudam.

Dicas:
- **Logs:** `docker compose logs -f app`.
- **Status:** `docker compose ps` mostra `healthy` quando `/api/config` responde.
- **Dados:** o compose usa o modo efêmero. Projetos, arquivos e relatórios ficam só na memória do contêiner. No disco ficam apenas o log de auditoria sem conteúdo (`var/auditoria/`) e o cache do bSDD (`.cache/bsdd/`, dados públicos). Um reinício do contêiner apaga os projetos em andamento.
- **Ambiente de demonstração (opcional):** `EDITALCHECK_DISPONIVEL_ATE` (DD/MM/AAAA) mostra uma data de desligamento na faixa do topo. Vazio, a faixa mostra só o aviso de que os dados ficam em memória.
- **Uma réplica:** no modo efêmero, cada projeto vive na memória de um processo. Mantenha uma réplica ou a sessão fixa do Traefik (já configurada).
- **Domínio:** o padrão é `atena.construtivo.com`. Para usar outro, defina `APP_DOMAIN` no ambiente ou num `.env` ao lado do compose.
- **Outro prefixo:** troque `/editalcheck` nas labels, em `BASE_PATH` e em `EDITALCHECK_ROOT_PATH`.

## API

Contrato em [docs/api.md](docs/api.md). Documentação OpenAPI em `/docs` com o servidor no ar.

## Dados da demo

Os arquivos de `data/demo/` são **sintéticos**. O edital e o IFC são gerados por código (`uv run editalcheck gerar-demo`); as lições foram escritas pelo time:

- `edital.pdf`: edital fictício de uma escola, com 5 páginas. Mistura cláusulas verificáveis, termos vagos, itens mínimos ausentes e uma contradição (IFC 4 × IFC 2x3).
- `modelo.ifc`: escola de 2 pavimentos em IFC4, com 133 elementos e 18 ambientes. Tem erros planejados: 5 portas sem `FireRating`, 4 janelas sem `ThermalTransmittance`, 2 ambientes sem `LongName`, 1 escada com espelho de 0,19 m, 4 objetos genéricos e 1 elemento sem pavimento. O IFC passa na validação de schema do IfcOpenShell.
- `licoes_aprendidas.txt`: 4 lições de obras escolares fictícias. Uma já está explícita no edital (portas com FireRating); três não estão (sala de baterias sem janelas, lajes com LoadBearing, acesso à casa de bombas).
- No IFC, a sala S106 se chama "Sala de baterias" e tem duas janelas. Isso reproduz o caso relatado pela banca.
- `gabarito.json`: requisitos, trechos vagos e checklist esperados, anotados pelo time.

Nenhum dado de cliente, contrato ou projeto do Construtivo é usado.

## Métricas medidas (seção 14.3)

Medidas em 22/11/2026 com `uv run editalcheck demo`, sobre os dados sintéticos (edital de 5 páginas e IFC de 151 elementos). Em 23/11/2026, depois da v2 e com as lições aprendidas, o modo offline foi medido de novo: recall 100% (19/19), precisão 100% (19/19), checklist 10/10, ambiguidade 10/10 e pipeline em menos de 1 s. Os requisitos vindos de lições ficam fora da métrica, porque o gabarito cobre só o edital. A coluna do Gemini não foi medida de novo após a v2.

| Métrica | Modo offline (regras) | Gemini (`gemini-4-hydrogen`) | Amostra |
|---|---|---|---|
| Recall de extração | 100% (19/19) | 100% (19/19) | 19 requisitos do gabarito |
| Precisão de extração | 100% (19/19) | 95% (19/20) | requisitos extraídos |
| Citações conferidas (S2) | 100% (19/19) | 100% (20/20) | trechos citados |
| IDS válido (S6) | sim (8 especificações) | sim (8 especificações) | — |
| Acerto da checklist | 100% (10/10) | 80% (8/10) | 10 itens |
| Precisão / recall de ambiguidade | 100% / 100% | 100% / 90% | 10 trechos vagos |
| Tempo do pipeline (CLI) | menos de 1 s | 110 s sem cache; 33 s com cache parcial | — |

O "extra" do Gemini é a cláusula 6.1.1 ("a fiscalização verificará o modelo..."), registrada como requisito não verificável; o gabarito não a conta como requisito. Na checklist, o Gemini julgou o CHK-02 como "parcial" e o CHK-10 como "ausente"; o gabarito do time diz o contrário. São divergências de julgamento, que o time deve revisar.

> **Atenção:** estes números **não** representam editais reais. O edital sintético e as regras offline foram escritos pelo mesmo time, então o resultado é otimista por construção. Meça de novo com um edital público real antes de citar números no pitch. O tempo manual equivalente ainda precisa ser cronometrado pelo time.

## Limites

- Verifica só informação alfanumérica do modelo (IDS). Requisitos geométricos, de desempenho, prazo e custo saem como **verificação manual**. A única checagem geométrica é simples: elementos proibidos por uma lição (ex.: janelas) cuja caixa envolvente toca o ambiente citado.
- No modo efêmero, um reinício do servidor apaga os projetos em andamento. O usuário pode baixar o relatório JSON antes.
- O tempo manual equivalente ainda não foi medido. O painel mostra "não medido" até o time preencher `backend/resources/referencia_tempo_manual.yaml`.
- Não faz OCR: PDFs escaneados são recusados com aviso.
- A segmentação de tópicos reconhece títulos numerados de nível 1 e 2 ("5 TÍTULO", "5.1 Título", "5 – TÍTULO") e anexos ("ANEXO I – ..."). Títulos sem número, como "CLÁUSULA PRIMEIRA" e "CAPÍTULO II", ainda não são reconhecidos.
- O extrator por regras cobre o vocabulário de `backend/resources/vocabulario_pt.yaml`. Editais reais exigem o LLM.
- A checklist e o léxico de termos vagos são autoria do time, inspirados na ISO 19650. Eles não substituem a análise jurídica do edital.
- Os adaptadores de IA têm testes com cliente simulado, que usam os prompts reais. O Gemini (`gemini-4-hydrogen`) já respondeu em execuções reais da demo.

## Licenças

- Backend: IfcOpenShell e ifctester (LGPL-3.0), **bcf-client (GPL-3.0)**, **PyMuPDF (AGPL-3.0 ou licença comercial da Artifex)**, FastAPI (MIT), Pydantic (MIT), google-genai (Apache-2.0). Na prática, o backend precisa ser distribuído sob AGPL-3.0, ou é preciso trocar o leitor de PDF e o escritor de BCF. Os adaptadores `EditalReader` e `BcfWriter` isolam essas trocas. A licença do repositório é uma decisão do time.
- Frontend: `@thatopen/components` 3.6.0 e `@thatopen/fragments` 3.6.1 (MIT), three.js (MIT), web-ifc (MPL-2.0), `pdfjs-dist` 6.5.438 (Mozilla pdf.js, Apache-2.0, build "legacy" para navegadores mais antigos). Nenhum pacote AGPL no frontend (RNF-09).

## Documentos

- [Especificação técnica](docs/especificacao-tecnica.md)
- [Especificação técnica v2 — atualização após a banca](docs/especificacao-tecnica-v2.md)
- [Mapa de processo (IDM)](docs/idm.md)
- [Contrato da API](docs/api.md)
- [Diário de decisões (JOURNAL)](docs/JOURNAL.md)

## Trabalhos relacionados

Pesquisas recentes sobre IA e IDS (preprints de 2026; confira a versão publicada antes de citar):

- Ishigaki-IDS-Bench, arXiv:2605.22079 — benchmark de geração de IDS 1.0 por LLMs a partir de documentos práticos. Conclui que os modelos ainda erram o XML e o vocabulário IFC com frequência. <https://arxiv.org/abs/2605.22079>
- Ishigaki-IDS, arXiv:2606.08545 — modelo aberto para rascunhar IDS, treinado com recompensas de um verificador de IDS. <https://arxiv.org/abs/2606.08545>
- Hosseini et al., *Natural-language-to-IFC mapping for IDS authoring* (capítulo, Taylor & Francis) — fluxo em etapas com termos IFC sugeridos e confirmação de especialista. Aponta que IDS estruturalmente válidos podem representar mal o requisito. <https://www.taylorfrancis.com/chapters/oa-edit/10.1201/9781042025374-23/natural-language-ifc-mapping-ids-authoring-hosseini-gourabpasi-jalaei-khodabakhshi>

O EditalCheck segue a mesma conclusão: o LLM não escreve XML; o IDS é gerado por código a partir de requisitos aprovados por uma pessoa.
