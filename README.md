# EditalCheck — verificador bidirecional Edital × IFC

> Hackathon Open BIM + IA · Sinaenco · 22–23/11/2026. Nome do produto provisório.

O EditalCheck recebe um **edital em PDF** e um **modelo IFC** e verifica um contra o outro:

1. **O IFC cumpre o edital?** O sistema extrai os requisitos do edital num **EIR**. O projetista revisa e aprova. O sistema gera o **IDS** por código e valida o IFC.
2. **O edital está bom?** O sistema aponta termos vagos, requisitos não verificáveis, itens mínimos ausentes e contradições.
3. **O edital cobre o modelo?** O sistema mede quanto do modelo o edital especifica e sugere requisitos com Psets oficiais para as lacunas.

Cada apontamento diz **o que** está errado, **onde** (página do edital e/ou GlobalId), **como agir**, **por que** e **quem age**. As não conformidades aparecem num **visualizador 3D** e num arquivo **BCF**.

**Tese:** a IA interpreta o texto. Tudo o que precisa ser exato (IDS, validação, BCF, métricas) é código determinístico sobre padrões abertos. Toda citação da IA é conferida literalmente contra o texto do PDF.

## Padrões Open BIM usados

| Padrão / serviço | Uso |
|---|---|
| **IFC** (IFC2X3, IFC4, IFC4X3) | Entrada do modelo, classes, Psets, GlobalIds e saúde do modelo |
| **IDS 1.0** | Contrato de dados gerado do EIR aprovado, validado contra o XSD oficial e usado na verificação |
| **BCF 2.1** | Um tópico por apontamento do modelo, com um viewpoint por elemento (seleção, destaque em vermelho e câmera enquadrando o elemento), uma visão geral e um comentário ligado a cada viewpoint |
| **bSDD** | URIs de propriedades e busca de termos (API REST pública) |
| **Psets oficiais** | Vocabulário controlado dos requisitos e das sugestões de lacuna |

## Arquitetura

Arquitetura hexagonal. O domínio não importa FastAPI, IfcOpenShell nem SDK de LLM.

```
entrypoints/   FastAPI (api/) e CLI Typer (cli.py)
application/   casos de uso + portas (typing.Protocol) + salvaguardas
domain/        entidades e regras puras: evidência (S2), tópicos, termos vagos,
               cobertura, severidade, checklist, apontamentos, indicadores
adapters/      PyMuPDF · IfcOpenShell · ifctester (IDS) · bcf-client (BCF) ·
               Gemini · regras offline · bSDD (httpx) · Jinja2 · openpyxl · arquivos
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

3. (Opcional) Configure o Gemini. Copie `.env.example` para `.env` e preencha `GEMINI_API_KEY`. Com o Gemini, `LLM_PARALELISMO` (padrão 6) define quantas chamadas rodam ao mesmo tempo. Reduza esse valor se a cota do seu plano recusar requisições.

4. Suba a aplicação e abra http://127.0.0.1:8000:

```powershell
cd backend; uv run editalcheck servidor
```

Clique em **Usar dados de exemplo** para rodar a demo.

### CLI (sem interface)

```powershell
cd backend; uv run editalcheck demo
```

Outros comandos: `topicos <pdf>`, `modelo <ifc>`, `pipeline --edital <pdf> --modelo <ifc> [--topicos 5.1,5.2] [--gabarito <json>]` e `gerar-demo`.

### Testes

```powershell
cd backend; uv run pytest
```

Desenvolvimento do frontend com recarga automática: rode `npm run dev` em `frontend/`. O Vite redireciona `/api` para `127.0.0.1:8000`.

## API

Contrato em [docs/api.md](docs/api.md). Documentação OpenAPI em `/docs` com o servidor no ar.

## Dados da demo

Os arquivos de `data/demo/` são **sintéticos**, gerados por código (`uv run editalcheck gerar-demo`):

- `edital.pdf`: edital fictício de uma escola, com 5 páginas. Mistura cláusulas verificáveis, termos vagos, itens mínimos ausentes e uma contradição (IFC 4 × IFC 2x3).
- `modelo.ifc`: escola de 2 pavimentos em IFC4, com 133 elementos e 18 ambientes. Tem erros planejados: 5 portas sem `FireRating`, 4 janelas sem `ThermalTransmittance`, 2 ambientes sem `LongName`, 1 escada com espelho de 0,19 m, 4 objetos genéricos e 1 elemento sem pavimento. O IFC passa na validação de schema do IfcOpenShell.
- `gabarito.json`: requisitos, trechos vagos e checklist esperados, anotados pelo time.

Nenhum dado de cliente, contrato ou projeto do Construtivo é usado.

## Métricas medidas (seção 14.3)

Medidas em 22/11/2026 com `uv run editalcheck demo`, sobre os dados sintéticos (edital de 5 páginas e IFC de 151 elementos):

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

- Verifica só informação alfanumérica do modelo (IDS). Requisitos geométricos, de desempenho, prazo e custo saem como **verificação manual**.
- Não faz OCR: PDFs escaneados são recusados com aviso.
- A segmentação de tópicos reconhece títulos numerados de nível 1 e 2 ("5 TÍTULO", "5.1 Título", "5 – TÍTULO") e anexos ("ANEXO I – ..."). Títulos sem número, como "CLÁUSULA PRIMEIRA" e "CAPÍTULO II", ainda não são reconhecidos.
- O extrator por regras cobre o vocabulário de `backend/resources/vocabulario_pt.yaml`. Editais reais exigem o LLM.
- A checklist e o léxico de termos vagos são autoria do time, inspirados na ISO 19650. Eles não substituem a análise jurídica do edital.
- Os adaptadores de IA têm testes com cliente simulado, que usam os prompts reais. O Gemini (`gemini-4-hydrogen`) já respondeu em execuções reais da demo.

## Licenças

- Backend: IfcOpenShell e ifctester (LGPL-3.0), **bcf-client (GPL-3.0)**, **PyMuPDF (AGPL-3.0 ou licença comercial da Artifex)**, FastAPI (MIT), Pydantic (MIT), google-genai (Apache-2.0). Na prática, o backend precisa ser distribuído sob AGPL-3.0, ou é preciso trocar o leitor de PDF e o escritor de BCF. Os adaptadores `EditalReader` e `BcfWriter` isolam essas trocas. A licença do repositório é uma decisão do time.
- Frontend: `@thatopen/components` 3.6.0 e `@thatopen/fragments` 3.6.1 (MIT), three.js (MIT), web-ifc (MPL-2.0). Nenhum pacote AGPL no frontend (RNF-09).

## Documentos

- [Especificação técnica](docs/especificacao-tecnica.md)
- [Contrato da API](docs/api.md)
- [Diário de decisões (JOURNAL)](docs/JOURNAL.md)
