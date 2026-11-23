# Especificação técnica — Verificador bidirecional Edital × IFC

> **Hackathon Open BIM + IA** · Sinaenco · 22–23/11/2026
> Versão 1.0 · 22/11/2026
> Nome provisório do produto: **EditalCheck** (o time define o nome final)
> Status: aprovada para desenvolvimento. Decisões em aberto na seção 17.

> **Documento histórico.** Esta é a especificação escrita antes da implementação. O comportamento atual
> está no [README](../README.md) e no [contrato da API](api.md). Partes daqui foram mudadas na
> [v2](especificacao-tecnica-v2.md) e no código (ex.: o LLM é o Gemini e as rotas usam `/ir`).

---

## Sumário

1. Resumo executivo
2. Problema e contexto
3. Objetivos, metas e não objetivos
4. Personas e fluxo de uso
5. Visão geral da solução
6. Requisitos funcionais
7. Requisitos não funcionais
8. Arquitetura (hexagonal)
9. Modelo de domínio
10. Pipeline de IA e salvaguardas contra alucinação
11. Mapeamento para os padrões Open BIM
12. API HTTP
13. Interface e visualização 3D
14. Estratégia de avaliação e métricas
15. Plano de execução até o pitch
16. Roteiro do pitch e da demo
17. Decisões em aberto
18. Riscos e mitigação
19. Escalabilidade e roadmap pós-hackathon
20. Definição de pronto

---

## 1. Resumo executivo

O **EditalCheck** recebe um **edital em PDF** e um **modelo IFC**. Ele verifica os dois documentos nos dois sentidos:

1. **O IFC cumpre o edital?** O sistema extrai os requisitos do edital e gera um **EIR** estruturado. O projetista revisa e aprova o EIR. O sistema converte o EIR aprovado em **IDS** e valida o IFC.
2. **O edital está bom?** O sistema aponta ambiguidades, requisitos não verificáveis e itens mínimos ausentes.
3. **O edital cobre o modelo?** O sistema mede quanto do modelo o edital realmente especifica e sugere requisitos para as lacunas.

O resultado é um **relatório de apontamentos**. Cada apontamento diz **o que** está errado, **onde**, **como agir**, **por que** e **quem deve agir**. As não conformidades também aparecem num **visualizador 3D web** e num arquivo **BCF**.

**Tese do projeto:** a IA interpreta o texto. Tudo o que precisa ser exato (IDS, validação, BCF, métricas) é feito por código determinístico sobre padrões abertos. Toda afirmação da IA precisa apontar para uma evidência que o sistema confere.

---

## 2. Problema e contexto

### 2.1 Como é hoje

- Editais de obras públicas pedem "projeto em BIM", mas raramente dizem **quais informações** o modelo deve conter.
- O edital é escrito em linguagem comum. Alguém precisa traduzir o texto em requisitos verificáveis (EIR → IDS). A ISO 19650 atribui essa tarefa ao gestor da informação. A banca citou essa tradução como **gargalo no Brasil**.
- A verificação do modelo contra o edital é manual, lenta e depende de quem revisa.
- Falhas do **próprio edital** (cláusulas vagas, lacunas) só aparecem na obra, quando corrigir custa caro.

### 2.2 Contexto legal

A Lei 14.133/2021 (art. 19, §3º) prevê o uso preferencial do BIM em licitações de obras e serviços de engenharia, quando adequado ao objeto. A lei não define **o que** o edital deve exigir do modelo. Confirme a redação vigente antes de citar no pitch.

### 2.3 Estado da arte (para o pitch)

- Pesquisas de 2026 mostram que LLMs geram IDS de forma instável. Também mostram que um IDS **estruturalmente válido** pode representar mal o requisito e deixar a verificação passar pelo motivo errado.
- **Diferencial do EditalCheck:** o LLM nunca escreve XML. A geração do IDS é determinística. Cada requisito é rastreável até o trecho do edital. O projetista aprova antes de qualquer validação.

---

## 3. Objetivos, metas e não objetivos

### 3.1 Objetivos

| # | Objetivo | Critério da banca atendido |
|---|---|---|
| O1 | Verificar o IFC contra os requisitos do edital via IDS | Relevância Open BIM, qualidade da solução |
| O2 | Avaliar a qualidade do edital (ambiguidade, lacunas, itens ausentes) | Inovação e impacto |
| O3 | Medir a cobertura do edital sobre o modelo | Inovação, métrica para o pitch |
| O4 | Gerar apontamentos acionáveis com justificativa e referência | Usabilidade, impacto |
| O5 | Mostrar os conflitos em 3D e exportar BCF | Apresentação, Open BIM |
| O6 | Manter rastreabilidade total: edital ↔ EIR ↔ IDS ↔ elemento IFC | Qualidade da solução, confiança |

### 3.2 Metas mensuráveis (medir até 23/11/2026, 13h)

| Meta | Alvo |
|---|---|
| IDS gerados que carregam sem erro no ifctester | 100% (garantido por construção) |
| Citações da IA conferidas literalmente contra o texto do edital | 100% (o que não confere é descartado) |
| Recall da extração de requisitos no gabarito da demo | ≥ 80% |
| Precisão da extração de requisitos no gabarito da demo | ≥ 80% |
| Tempo do pipeline completo na demo (edital + IFC de exemplo) | ≤ 3 min |
| Tempo manual equivalente (cronometrado pelo time) | Medir; não estimar |

Os alvos de recall e precisão são metas do time, não resultados. Reporte no pitch o valor **medido**.

### 3.3 Não objetivos (fora do escopo do hackathon)

- Verificar requisitos **geométricos** (folgas, distâncias, áreas mínimas) e de desempenho.
- Fazer clash detection.
- Treinar ou ajustar modelos de IA. Usamos LLM pronto via API.
- Fazer OCR de editais escaneados.
- Ter multiusuário, autenticação ou persistência em banco.
- Integrar com produtos existentes do Construtivo. Isso pode ferir a regra "criado durante o hackathon".

---

## 4. Personas e fluxo de uso

### 4.1 Personas

| Persona | O que quer | Como usa |
|---|---|---|
| **Gestor do contratante** (quem escreve o edital) | Edital claro, completo e verificável | Lê os apontamentos do edital e a cobertura |
| **Projetista / BIM manager** | Saber o que corrigir no modelo e por quê | Aprova o EIR, vê os conflitos em 3D, importa o BCF |
| **Fiscal / gestão da obra** | Visão rápida da conformidade | Painel-resumo e visualizador 3D |

### 4.2 Fluxo principal (assistente em 6 passos)

```
[1 Upload] → [2 Tópicos] → [3 Revisão do EIR] → [4 IDS] → [5 Verificação] → [6 Resultados]
 PDF + IFC    seleciona      projetista aprova    gerado     3 análises       relatório,
                                                  e baixado  em paralelo      3D e BCF
```

1. **Upload:** o usuário envia o edital (PDF com texto) e o IFC.
2. **Tópicos:** o sistema separa o edital em tópicos com número de página. O usuário marca os que quer verificar.
3. **Revisão do EIR:** o sistema propõe os requisitos dos tópicos marcados. Cada um mostra o trecho original. O projetista aceita, edita ou rejeita. O EIR pode ser exportado para planilha.
4. **IDS:** o sistema gera o IDS a partir do EIR aprovado. O arquivo pode ser baixado.
5. **Verificação:** o sistema roda três análises: IFC × IDS, qualidade do edital e cobertura.
6. **Resultados:** painel com indicadores, lista de apontamentos, visualizador 3D, relatório HTML e BCF.

**Ciclo fechado:** um apontamento de lacuna tem o botão "Adicionar ao EIR". O requisito sugerido volta para o passo 3.

---

## 5. Visão geral da solução

### 5.1 As três análises

| Análise | Pergunta | Natureza | Saída |
|---|---|---|---|
| **A. Conformidade** | O IFC cumpre o edital? | Determinística (IDS + ifctester) | Não conformidades por elemento |
| **B. Qualidade do edital** | O edital é claro e completo? | Híbrida (regras + LLM com evidência) | Ambiguidades, não verificáveis, itens ausentes |
| **C. Cobertura** | O edital especifica o que existe no modelo? | Determinística (IFC + templates de Pset) | % de cobertura e lacunas por classe |

Além disso, o sistema faz uma **verificação básica de saúde do modelo**, determinística e barata:
- schema do IFC;
- proporção de `IfcBuildingElementProxy`;
- elementos sem pavimento;
- GlobalIds duplicados;
- ausência de `IfcSpace`.

Esses problemas viram apontamentos do tipo "qualidade do modelo".

### 5.2 Princípios de projeto

1. **IA interpreta; código garante.** O LLM só produz JSON validado por schema. IDS, validação, BCF e métricas são determinísticos.
2. **Evidência ou nada.** Toda citação do edital é conferida literalmente contra o texto extraído. Citação que não confere é descartada.
3. **Referências fechadas.** O LLM só cita referências fornecidas a ele: cláusulas do edital, Psets oficiais, termos do bSDD consultados e itens da checklist. Fora disso, o apontamento sai como "referência a confirmar".
4. **Humano no circuito.** Nenhum requisito vira IDS sem aprovação. Recomendações geradas por IA saem marcadas para revisão.
5. **Rastreabilidade ponta a ponta.** O mesmo ID liga trecho do edital → requisito → especificação IDS → resultado → BCF → elemento 3D.
6. **Honestidade sobre limites.** O que não é verificável aparece explicitamente como "verificação manual".

---

## 6. Requisitos funcionais

### 6.1 Ingestão

| ID | Requisito | Prioridade |
|---|---|---|
| RF-01 | Aceitar edital em PDF com texto selecionável | Must |
| RF-02 | Extrair o texto **por página**, com a numeração preservada | Must |
| RF-03 | Detectar PDF sem texto (escaneado) e avisar o usuário | Must |
| RF-04 | Aceitar IFC2X3 e IFC4 e informar o schema detectado | Must |
| RF-05 | Aceitar IFC4X3 | Could |

### 6.2 Tópicos

| ID | Requisito | Prioridade |
|---|---|---|
| RF-10 | Segmentar o edital em tópicos pela numeração e pelos títulos (regra determinística) | Must |
| RF-11 | Usar o LLM só para nomear e resumir tópicos, e para marcar os relevantes para BIM | Should |
| RF-12 | Permitir que o usuário selecione os tópicos a verificar | Must |

### 6.3 EIR

| ID | Requisito | Prioridade |
|---|---|---|
| RF-20 | Gerar requisitos estruturados por tópico (schema da seção 9) | Must |
| RF-21 | Conferir literalmente o trecho de origem de cada requisito; descartar o que não confere | Must |
| RF-22 | Validar classes IFC contra o schema do modelo | Must |
| RF-23 | Marcar cada propriedade como "Pset oficial", "bSDD" ou "Pset customizado" | Must |
| RF-24 | Classificar cada requisito como verificável ou não por IDS, com motivo | Must |
| RF-25 | Permitir aceitar, editar e rejeitar cada requisito | Must |
| RF-26 | Sugerir URI do bSDD para classificação e propriedade | Should |
| RF-27 | Exportar o EIR para planilha (XLSX ou CSV) | Should |

### 6.4 IDS

| ID | Requisito | Prioridade |
|---|---|---|
| RF-30 | Gerar o IDS só a partir dos requisitos aprovados e verificáveis | Must |
| RF-31 | Usar o nome da especificação IDS com o ID do requisito (ex.: `REQ-012 · ...`) | Must |
| RF-32 | Carregar o IDS gerado de volta no ifctester como teste de integridade | Must |
| RF-33 | Permitir baixar o IDS | Must |

### 6.5 Análises

| ID | Requisito | Prioridade |
|---|---|---|
| RF-40 | Validar o IFC contra o IDS (análise A) | Must |
| RF-41 | Calcular a cobertura do edital por classe IFC (análise C) | Must |
| RF-42 | Detectar termos vagos por léxico (análise B, parte determinística) | Must |
| RF-43 | Confirmar ambiguidades com LLM e sugerir redação mensurável | Should |
| RF-44 | Avaliar a checklist de itens mínimos do edital com evidência obrigatória | Should |
| RF-45 | Detectar contradições entre cláusulas | Could |
| RF-46 | Rodar a verificação de saúde do modelo | Should |

### 6.6 Apontamentos e saídas

| ID | Requisito | Prioridade |
|---|---|---|
| RF-50 | Gerar apontamentos no formato da seção 9.4 | Must |
| RF-51 | Calcular a severidade por regra determinística (seção 9.5) | Must |
| RF-52 | Gerar "como agir" e "por que" com referências da lista fechada | Must |
| RF-53 | Gerar relatório HTML em português | Must |
| RF-54 | Exportar o relatório em JSON | Must |
| RF-55 | Exportar as não conformidades em BCF | Must |
| RF-56 | Visualizar o modelo em 3D, com os elementos em conflito destacados | Must |
| RF-57 | Ao clicar num elemento, mostrar requisito, trecho e página do edital | Must |
| RF-58 | Exibir painel com indicadores (seção 13.3) | Should |
| RF-59 | Botão "Adicionar ao EIR" em apontamentos de lacuna (ciclo fechado) | Should |

**Must** é obrigatório para a demo. **Should** é desejável. **Could** entra se sobrar tempo.

---

## 7. Requisitos não funcionais

| ID | Requisito |
|---|---|
| RNF-01 | **Desempenho:** a demo completa roda em até 3 min com o edital e o IFC de exemplo |
| RNF-02 | **Robustez:** falha do LLM ou do bSDD não derruba o fluxo; o sistema degrada e avisa |
| RNF-03 | **Reprodutibilidade:** temperatura 0, prompts versionados em arquivo e cache das respostas do LLM por hash da entrada |
| RNF-04 | **Rastreabilidade:** todo apontamento tem evidência verificável (página/trecho e/ou GlobalId) |
| RNF-05 | **Portabilidade de IA:** trocar de provedor de LLM exige só um novo adaptador |
| RNF-06 | **Segurança:** chaves só em `.env`, fora do Git; uploads com limite de tamanho; nenhum dado de cliente |
| RNF-07 | **Observabilidade:** logs estruturados por etapa, com duração e contagem de tokens |
| RNF-08 | **Qualidade de código:** PEP 8, type hints modernos, early returns, testes das regras de domínio |
| RNF-09 | **Licenças:** só dependências abertas ou licenciadas; nenhum pacote AGPL no frontend |
| RNF-10 | **Idioma:** interface e relatórios em português do Brasil |

---

## 8. Arquitetura (hexagonal)

### 8.1 Visão geral

```
                    ┌────────────────────── Entrypoints ──────────────────────┐
                    │  FastAPI (HTTP)        CLI (Typer, para testes e demo)  │
                    └──────────────┬──────────────────────────┬───────────────┘
                                   │                          │
                    ┌──────────────▼──────── Application ─────▼───────────────┐
                    │ Casos de uso: ImportarDocumentos, SegmentarTopicos,      │
                    │ GerarEir, RevisarEir, GerarIds, ExecutarVerificacao,     │
                    │ GerarRelatorio                                           │
                    │ Portas (typing.Protocol)                                 │
                    └──────────────┬───────────────────────────────────────────┘
                                   │
                    ┌──────────────▼──────────── Domain ──────────────────────┐
                    │ Entidades: Edital, Topico, Requisito, Eir, Apontamento   │
                    │ Serviços puros: cobertura, severidade, léxico de termos  │
                    │ vagos, conferência de citação, checklist                 │
                    │ (sem IfcOpenShell, sem FastAPI, sem SDK de LLM)          │
                    └──────────────────────────────────────────────────────────┘
                                   ▲
                    ┌──────────────┴─────────── Adapters ─────────────────────┐
                    │ PyMuPDF · LLM (Claude/OpenAI) · IfcOpenShell · ifctester │
                    │ bSDD HTTP · Jinja2 (HTML) · BCF · FileSystem storage     │
                    └──────────────────────────────────────────────────────────┘
```

### 8.2 Estrutura do repositório

```
editalcheck/
├── backend/
│   ├── pyproject.toml
│   ├── src/editalcheck/
│   │   ├── domain/
│   │   │   ├── models.py            # dataclasses imutáveis do domínio
│   │   │   ├── coverage.py          # cálculo de cobertura (puro)
│   │   │   ├── severity.py          # matriz de severidade (pura)
│   │   │   ├── vagueness.py         # detecção por léxico (pura)
│   │   │   ├── evidence.py          # conferência literal de citações (pura)
│   │   │   └── checklist.py         # avaliação da checklist (pura)
│   │   ├── application/
│   │   │   ├── ports.py             # Protocols
│   │   │   └── use_cases/
│   │   │       ├── importar_documentos.py
│   │   │       ├── segmentar_topicos.py
│   │   │       ├── gerar_eir.py
│   │   │       ├── revisar_eir.py
│   │   │       ├── gerar_ids.py
│   │   │       ├── executar_verificacao.py
│   │   │       └── gerar_relatorio.py
│   │   ├── adapters/
│   │   │   ├── pdf/pymupdf_reader.py
│   │   │   ├── llm/anthropic_client.py     # ou openai_client.py
│   │   │   ├── llm/schemas.py              # Pydantic para saída estruturada
│   │   │   ├── ifc/ifcopenshell_model.py
│   │   │   ├── ids/ifctester_builder.py
│   │   │   ├── ids/ifctester_validator.py
│   │   │   ├── bsdd/http_client.py
│   │   │   ├── report/html_writer.py       # Jinja2
│   │   │   ├── bcf/ifctester_bcf.py
│   │   │   └── storage/fs_repository.py
│   │   └── entrypoints/
│   │       ├── api/main.py                 # FastAPI
│   │       ├── api/dto.py                  # Pydantic de entrada e saída
│   │       └── cli.py                      # Typer
│   ├── prompts/                     # prompts versionados (.md)
│   ├── resources/
│   │   ├── checklist_eir_minimo.yaml
│   │   └── termos_vagos.yaml
│   └── tests/
│       ├── domain/                  # testes unitários das regras puras
│       └── integration/             # pipeline com dados da demo
├── frontend/                        # Vite + TypeScript + @thatopen/components
├── data/demo/                       # edital.pdf, modelo.ifc, gabarito.json (públicos)
├── docs/
│   ├── especificacao-tecnica.md     # este documento
│   └── JOURNAL.md                   # diário de decisões (vira slide)
├── .env.example
└── README.md
```

### 8.3 Stack

| Camada | Tecnologia | Motivo |
|---|---|---|
| Linguagem | Python 3.12 | Ecossistema IfcOpenShell |
| API | FastAPI | Tipagem, OpenAPI automático, tarefas em segundo plano |
| CLI | Typer | Rodar o pipeline sem interface (marco das 18h) |
| PDF | PyMuPDF | Texto por página, rápido |
| IFC | IfcOpenShell | Leitura, Psets, templates de Pset oficiais |
| IDS | ifctester | Criação, validação e reporters JSON, HTML e BCF |
| BCF | Reporter `Bcf` do ifctester (+ módulo BCF do IfcOpenShell, se necessário) | Evita implementar BCF do zero |
| bSDD | HTTP para `api.bsdd.buildingsmart.org` (`httpx`) | API REST pública |
| LLM | Claude ou OpenAI, com saída estruturada | Decisão em aberto (seção 17) |
| Validação de dados | Pydantic v2 (só nos adaptadores e entrypoints) | Domínio sem dependência de framework |
| Relatório | Jinja2 → HTML | Simples e bonito |
| Frontend | Vite + TypeScript + `@thatopen/components` v3 | MIT, IFC no navegador, Highlighter, BCFTopics |

> **Regra:** antes de usar qualquer API de biblioteca, confira a documentação oficial da versão instalada. Os trechos de código deste documento são ilustrativos.

### 8.4 Portas (contratos)

```python
from typing import Protocol

class EditalReader(Protocol):
    def read(self, pdf_path: str) -> "Edital": ...

class IfcModelReader(Protocol):
    def load(self, ifc_path: str) -> "ModeloResumo": ...
    def official_properties(self, ifc_class: str) -> list["PropriedadeOficial"]: ...

class RequirementExtractor(Protocol):
    def extract(self, topico: "Topico", contexto: "ContextoVocabulario") -> list["Requisito"]: ...

class EditalAnalyzer(Protocol):
    def confirm_vagueness(self, candidatos: list["TrechoVago"]) -> list["Apontamento"]: ...
    def evaluate_checklist(self, edital: "Edital", itens: list["ItemChecklist"]) -> list["ResultadoChecklist"]: ...

class DictionaryLookup(Protocol):
    def search(self, termo: str, ifc_class: str | None = None) -> list["TermoDicionario"]: ...

class IdsBuilder(Protocol):
    def build(self, eir: "Eir") -> bytes: ...

class IfcValidator(Protocol):
    def validate(self, ids_xml: bytes, ifc_path: str) -> list["ResultadoEspecificacao"]: ...

class RecommendationWriter(Protocol):
    def write(self, apontamento: "Apontamento", referencias: list["Referencia"]) -> "Recomendacao": ...

class ReportWriter(Protocol):
    def write_html(self, relatorio: "Relatorio") -> str: ...

class BcfWriter(Protocol):
    def write(self, resultados: list["ResultadoEspecificacao"]) -> bytes: ...

class ProjectRepository(Protocol):
    def save(self, projeto: "Projeto") -> None: ...
    def get(self, projeto_id: str) -> "Projeto | None": ...
```

### 8.5 Execução das análises

- `ExecutarVerificacao` dispara as análises A, B e C de forma **independente**. A falha de uma não impede as outras.
- Na API, a verificação roda como tarefa em segundo plano. O frontend consulta o status.
- O cache do LLM fica em disco, com a chave `hash(prompt_version + modelo + entrada)`. Repetir a demo é instantâneo e não gasta tokens.

---

## 9. Modelo de domínio

### 9.1 Entidades principais

```python
from dataclasses import dataclass, field
from enum import StrEnum

class StatusRequisito(StrEnum):
    PROPOSTO = "proposto"
    APROVADO = "aprovado"
    EDITADO = "editado"
    REJEITADO = "rejeitado"

class TipoFaceta(StrEnum):          # espelha as facetas do IDS
    PROPRIEDADE = "property"
    ATRIBUTO = "attribute"
    CLASSIFICACAO = "classification"
    MATERIAL = "material"
    PARTE_DE = "partOf"

class OrigemVocabulario(StrEnum):
    PSET_OFICIAL = "pset_oficial"
    BSDD = "bsdd"
    CUSTOMIZADO = "customizado"

@dataclass(frozen=True)
class Evidencia:
    pagina: int
    trecho: str                       # conferido literalmente contra o texto da página

@dataclass(frozen=True)
class Restricao:
    tipo: str                         # "valor" | "enumeracao" | "padrao" | "intervalo"
    valores: tuple[str, ...] = ()
    minimo: float | None = None
    maximo: float | None = None

@dataclass(frozen=True)
class Requisito:
    id: str                           # REQ-001
    topico_id: str
    descricao: str
    evidencia: Evidencia
    verificavel_por_ids: bool
    motivo_nao_verificavel: str | None
    ifc_class: str | None             # ex.: IfcDoor
    predefined_type: str | None
    faceta: TipoFaceta | None
    pset: str | None                  # ex.: Pset_DoorCommon
    propriedade: str | None           # ex.: FireRating
    tipo_dado: str | None             # ex.: IfcLabel
    restricao: Restricao | None
    cardinalidade: str = "required"   # required | optional | prohibited
    origem_vocabulario: OrigemVocabulario | None = None
    bsdd_uri: str | None = None
    status: StatusRequisito = StatusRequisito.PROPOSTO
    sugerido_por_lacuna: bool = False
```

### 9.2 EIR

O `Eir` é a lista de `Requisito` de um projeto, mais metadados: versão, data, tópicos selecionados e autor da aprovação. Só requisitos `APROVADO` ou `EDITADO` com `verificavel_por_ids=True` entram no IDS.

### 9.3 Tipos de apontamento

| Tipo | Análise | Exemplo |
|---|---|---|
| `NAO_CONFORMIDADE` | A | Porta sem `FireRating`, exigida pelo item 5.3.2 |
| `AMBIGUIDADE` | B | "materiais adequados", sem critério mensurável |
| `NAO_VERIFICAVEL` | B | Requisito de prazo ou custo citado como requisito de modelo |
| `ITEM_AUSENTE` | B | O edital não define a versão do IFC de entrega |
| `CONTRADICAO` | B | Duas cláusulas exigem formatos diferentes |
| `LACUNA_COBERTURA` | C | 48 `IfcDoor` no modelo e nenhum requisito sobre portas |
| `QUALIDADE_MODELO` | Saúde | 32% dos elementos são `IfcBuildingElementProxy` |

### 9.4 Estrutura do apontamento

```python
class Destinatario(StrEnum):
    PROJETISTA = "projetista"         # corrige o IFC
    CONTRATANTE = "contratante"       # corrige o edital

class Severidade(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"

@dataclass(frozen=True)
class Referencia:
    tipo: str                         # "clausula_edital" | "pset_oficial" | "bsdd" | "checklist"
    rotulo: str                       # ex.: "Edital, item 5.3.2, p. 14"
    uri: str | None = None

@dataclass(frozen=True)
class Apontamento:
    id: str                           # APT-001
    tipo: str
    severidade: Severidade
    destinatario: Destinatario
    titulo: str
    evidencias_edital: tuple[Evidencia, ...] = ()
    elementos: tuple[str, ...] = ()   # GlobalIds
    requisito_id: str | None = None
    como_agir: str = ""
    por_que: str = ""
    referencias: tuple[Referencia, ...] = ()
    gerado_por_ia: bool = False
    referencia_a_confirmar: bool = False
```

### 9.5 Matriz de severidade (determinística)

| Tipo | Regra | Severidade |
|---|---|---|
| `NAO_CONFORMIDADE` | Requisito `required` não atendido | Alta |
| `NAO_CONFORMIDADE` | Requisito `optional` com valor fora da restrição | Média |
| `LACUNA_COBERTURA` | Classe com ≥ 10 elementos ou ligada à segurança (portas, escadas, equipamentos de incêndio) | Alta |
| `LACUNA_COBERTURA` | Demais classes | Média |
| `ITEM_AUSENTE` | Item marcado como crítico na checklist | Alta |
| `ITEM_AUSENTE` | Demais itens | Média |
| `AMBIGUIDADE` | Em cláusula que gera requisito | Média |
| `AMBIGUIDADE` | Demais casos | Baixa |
| `NAO_VERIFICAVEL` | Qualquer caso | Baixa (informativo) |
| `QUALIDADE_MODELO` | Proxies > 20% ou GlobalId duplicado | Alta |
| `QUALIDADE_MODELO` | Demais casos | Média |

A lista de classes ligadas à segurança e os limites ficam em configuração. O time ajusta durante os testes.

---

## 10. Pipeline de IA e salvaguardas contra alucinação

### 10.1 Etapas

```
PDF ──► texto por página ──► segmentação determinística ──► tópicos
                                                              │ (usuário seleciona)
IFC ──► resumo do modelo (classes, contagens, Psets) ─────────┤
Templates de Pset oficiais + bSDD ──► vocabulário candidato ──┤
                                                              ▼
                                   LLM: extração de requisitos (JSON)
                                                              │
                         ┌──── salvaguardas determinísticas ──┘
                         ▼
   conferência de citação · classe no schema · origem do vocabulário · reparo (máx. 2)
                         │
                         ▼
               EIR proposto ──► revisão humana ──► EIR aprovado ──► IDS (código)
```

### 10.2 Contexto enviado ao LLM na extração

- O texto do tópico, com marcadores de página (`[p. 14]`).
- As classes IFC presentes no modelo e suas contagens.
- Para essas classes, as propriedades dos **Psets oficiais**, obtidas dos templates do IfcOpenShell.
- Os termos do bSDD encontrados para palavras-chave do tópico, quando disponíveis.
- Instrução explícita: usar só esse vocabulário. Termos fora dele são marcados como `customizado`.

> **Cuidado com o viés do modelo:** o vocabulário vem dos templates oficiais para as classes presentes, e não das propriedades que o IFC já tem. Senão, o EIR tenderia a exigir só o que o modelo já cumpre.

### 10.3 Salvaguardas (todas determinísticas)

| # | Salvaguarda | Ação se falhar |
|---|---|---|
| S1 | Resposta valida contra o schema Pydantic | Reparo com a mensagem de erro (máx. 2 tentativas) |
| S2 | `evidencia.trecho` existe na página indicada (texto normalizado: espaços, hifenização, caixa) | Descarta o requisito e registra no log |
| S3 | `ifc_class` existe no schema do modelo | Reparo; senão, marca como não verificável |
| S4 | Propriedade existe no template oficial ou no bSDD consultado | Marca `customizado` e avisa na revisão |
| S5 | Referências citadas pertencem à lista fechada fornecida | Remove a referência e marca `referencia_a_confirmar` |
| S6 | O IDS gerado é recarregado no ifctester sem erro | Bloqueia a etapa e mostra o requisito problemático |

### 10.4 Análise B — qualidade do edital

1. **Léxico de termos vagos** (`termos_vagos.yaml`), aplicado por regra. Exemplos de entrada: "adequado", "conforme normas vigentes", "boa qualidade", "quando necessário", "a critério da fiscalização", "compatível", "padrão de mercado".
2. **Confirmação pelo LLM:** para cada trecho candidato, o LLM diz se é ambíguo no contexto. Se for, sugere uma redação mensurável. A conferência S2 vale para o trecho.
3. **Checklist de itens mínimos** (`checklist_eir_minimo.yaml`), inspirada no conteúdo esperado de requisitos de informação na ISO 19650. Itens iniciais:

| ID | Item | Crítico |
|---|---|---|
| CHK-01 | Formato e versão do IFC de entrega | Sim |
| CHK-02 | Nível de informação exigido (LOIN ou equivalente) por fase | Sim |
| CHK-03 | Sistema de classificação adotado | Não |
| CHK-04 | Convenção de nomenclatura de arquivos e elementos | Não |
| CHK-05 | Marcos e frequência de entrega do modelo | Sim |
| CHK-06 | Ambiente comum de dados (CDE) e fluxo de aprovação | Não |
| CHK-07 | Propriedades obrigatórias por tipo de elemento | Sim |
| CHK-08 | Sistema de coordenadas e georreferenciamento | Não |
| CHK-09 | Critérios de aceite e de verificação do modelo | Sim |
| CHK-10 | Responsabilidades (papéis) pela informação | Não |

Para cada item, o LLM responde `presente`, `parcial` ou `ausente`. As respostas `presente` e `parcial` **exigem** um trecho com página, conferido por S2. Sem trecho conferido, o item vale como `ausente`.

> O texto da checklist é autoria do time, **inspirado** na ISO 19650. Não cite números de cláusula da norma sem conferir no documento oficial.

### 10.5 Análise C — cobertura (sem LLM)

```
cobertura = classes do modelo com ≥ 1 requisito aprovado / classes "especificáveis" presentes no modelo
```

- **Classes especificáveis:** subtipos de `IfcElement` e `IfcSpace`, exceto `IfcBuildingElementProxy`. As proxies entram em "qualidade do modelo".
- Para cada classe sem requisito, gere um `LACUNA_COBERTURA` com até 3 propriedades sugeridas do Pset oficial (ex.: `Pset_DoorCommon.FireRating`).
- O texto "como agir" sugere uma cláusula modelo para o edital. Ela entra no EIR com `sugerido_por_lacuna=True`.

### 10.6 Recomendações ("como agir" e "por que")

- **Entrada do LLM:** o apontamento estruturado (tipo, evidências, elementos, requisito) e a lista fechada de referências.
- **Saída:** `como_agir` (até 3 frases, no imperativo) e `por_que` (até 3 frases, citando só referências da lista).
- **Para o destinatário `CONTRATANTE`:** sugestão de nova redação da cláusula.
- **Fallback sem LLM:** templates de texto por tipo de apontamento. A demo nunca fica sem recomendação.

---

## 11. Mapeamento para os padrões Open BIM

| Padrão / serviço | Uso no EditalCheck | Por que importa para a banca |
|---|---|---|
| **IFC** | Entrada do modelo; classes, Psets, GlobalIds; saúde do modelo | Estrutura de dados aberta |
| **IDS 1.0** | Contrato de dados gerado do EIR aprovado; validação | O IDS usado como **especificação**, não só verificação |
| **BCF** | Exportação das não conformidades com elemento e viewpoint; leitura no 3D | Comunicação aberta com qualquer ferramenta BIM |
| **bSDD** | Sugestão de classificações e propriedades com URI | Dicionário aberto e governança fora da aplicação |
| **Psets oficiais** | Vocabulário controlado para requisitos e lacunas | Alinhamento com a buildingSMART |
| **Validation Service da buildingSMART** | Validar o IFC da demo antes da apresentação (uso manual) | Mostra rigor com o modelo de entrada |
| **ISO 19650** | Inspiração para a checklist do edital e para o papel do EIR | Linguagem da gestão da informação |

### 11.1 Do requisito à especificação IDS (ilustrativo)

```python
from ifctester import ids

def to_specification(req: Requisito, ifc_version: str) -> ids.Specification:
    spec = ids.Specification(
        name=f"{req.id} · {req.descricao[:80]}",
        ifcVersion=[ifc_version],
        description=f"Edital, p. {req.evidencia.pagina}: {req.evidencia.trecho[:200]}",
    )
    spec.applicability.append(ids.Entity(name=req.ifc_class.upper()))
    spec.requirements.append(
        ids.Property(
            propertySet=req.pset,
            baseName=req.propriedade,
            dataType=req.tipo_dado.upper() if req.tipo_dado else None,
            cardinality=req.cardinalidade,
        )
    )
    return spec
```

> Confira na documentação do ifctester instalado os nomes exatos dos parâmetros e o uso de `ids.Restriction` para enumerações, padrões e intervalos.

### 11.2 Validação e reporters

- Validação: `ids.validate(ifc_file)`.
- Resultados estruturados: reporter `Json`, convertido em `Apontamento`.
- BCF: reporter `Bcf`.
- HTML do ifctester: anexo técnico. O relatório principal é o nosso, em português.

---

## 12. API HTTP

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/projetos` | Upload de PDF + IFC; retorna `projeto_id`, schema IFC e nº de páginas |
| `GET` | `/api/projetos/{id}/topicos` | Lista os tópicos com página e relevância BIM |
| `POST` | `/api/projetos/{id}/eir` | Gera o EIR para os tópicos selecionados |
| `GET` | `/api/projetos/{id}/eir` | Retorna o EIR atual |
| `PATCH` | `/api/projetos/{id}/eir/requisitos/{req_id}` | Aprova, edita ou rejeita um requisito |
| `GET` | `/api/projetos/{id}/eir.xlsx` | Exporta o EIR |
| `POST` | `/api/projetos/{id}/ids` | Gera o IDS a partir do EIR aprovado |
| `GET` | `/api/projetos/{id}/ids.xml` | Baixa o IDS |
| `POST` | `/api/projetos/{id}/verificacoes` | Dispara as análises A, B e C (assíncrono) |
| `GET` | `/api/verificacoes/{vid}` | Status e progresso por análise |
| `GET` | `/api/verificacoes/{vid}/relatorio` | Relatório JSON (apontamentos e indicadores) |
| `GET` | `/api/verificacoes/{vid}/relatorio.html` | Relatório HTML |
| `GET` | `/api/verificacoes/{vid}/resultado.bcf` | BCF das não conformidades |
| `GET` | `/api/projetos/{id}/modelo.ifc` | IFC para o visualizador |

Cada apontamento no JSON traz `elementos` com `global_id` e o `step_id` (id da entidade no arquivo IFC), para facilitar o destaque no 3D.

---

## 13. Interface e visualização 3D

### 13.1 Telas

1. **Upload:** dois campos de arquivo e validação imediata (PDF com texto? schema IFC?).
2. **Tópicos:** lista com caixas de seleção, página e selo "relevante para BIM".
3. **Revisão do EIR:** tabela de requisitos. Cada linha mostra o trecho do edital, o mapeamento IFC, a origem do vocabulário (oficial / bSDD / customizado) e os botões Aceitar, Editar e Rejeitar. Filtro "não verificáveis".
4. **Resultados:**
   - **Painel** com os indicadores.
   - **Visualizador 3D:** elementos em vermelho (não conforme), verde (conforme) e cinza (sem requisito).
   - **Lista de apontamentos** com filtros por tipo, severidade e destinatário.
   - **Painel de detalhe:** ao clicar num elemento ou apontamento, mostra requisito, trecho, página, "como agir" e "por que".
   - **Downloads:** IDS, BCF, relatório HTML e EIR.

### 13.2 Visualizador

- `@thatopen/components` v3 (MIT). Confira a licença da versão instalada e não use pacotes antigos AGPL.
- Carregar o IFC no navegador e usar o `Highlighter` com estilos por estado.
- Ligar os resultados aos elementos pelo `GlobalId`. Se a API da versão exigir id local, use o `step_id` enviado pelo backend.
- Clicar num apontamento enquadra a câmera nos elementos afetados.
- Use o `BCFTopics` para abrir o BCF gerado, se sobrar tempo. Isso prova a interoperabilidade na própria demo.

**Plano B:** se o 3D atrasar, a demo usa o relatório HTML e abre o BCF numa ferramenta BIM gratuita que leia BCF.

### 13.3 Indicadores do painel

- Conformidade do modelo: % de verificações IDS aprovadas.
- Cobertura do edital: % das classes especificáveis com requisito.
- Itens mínimos presentes na checklist: X de 10.
- Apontamentos por severidade e por destinatário.
- Requisitos não verificáveis por IDS (verificação manual).

---

## 14. Estratégia de avaliação e métricas

### 14.1 Dados da demo

- **Edital:** um edital público real de obra (de preferência uma escola), com texto selecionável. Use só os tópicos com requisitos de projeto.
- **IFC:** um modelo público de exemplo, de licença aberta, compatível com o tipo de obra. A pessoa de BIM ajusta o modelo para ter conformidades **e** não conformidades nos tópicos da demo.
- Valide o IFC no Validation Service da buildingSMART antes da apresentação.
- **Proibido:** dados de clientes, contratos ou projetos do Construtivo.

### 14.2 Gabarito

- A pessoa de BIM anota manualmente os requisitos dos tópicos da demo (`gabarito.json`), **antes** de ver a saída da IA.
- Anote também 10 trechos vagos e o status esperado dos 10 itens da checklist.

### 14.3 Métricas

| Métrica | Como medir |
|---|---|
| Recall de extração | requisitos do gabarito encontrados / total do gabarito |
| Precisão de extração | requisitos corretos / total extraído |
| Citações conferidas | trechos aprovados em S2 / trechos gerados |
| Validade do IDS | IDS recarregado sem erro (esperado: 100%) |
| Acerto da checklist | itens com status igual ao gabarito / 10 |
| Precisão de ambiguidade | ambiguidades confirmadas corretas / ambiguidades apontadas |
| Tempo do pipeline | cronômetro da execução ponta a ponta |
| Tempo manual | cronometrar uma pessoa do time fazendo a mesma tarefa em 1 tópico; extrapolar só com aviso |

Automatize as métricas num script (`tests/integration/test_gabarito.py`). Mostre os números **medidos** no pitch, com o tamanho da amostra.

---

## 15. Plano de execução até o pitch

### 15.1 Papéis

| Papel | Responsabilidade |
|---|---|
| **P1 – IA e domínio** | Prompts, extração do EIR, análise B, recomendações, salvaguardas |
| **P2 – Open BIM e backend** | IfcOpenShell, ifctester, IDS, BCF, cobertura, saúde do modelo, API |
| **P3 – Frontend e 3D** | Assistente, revisão do EIR, visualizador, painel |
| **P4 – BIM e dados** | Edital e IFC da demo, gabarito, checklist, léxico, testes manuais |
| **P5 – Pitch** (pode acumular com P4) | Slides, roteiro, métricas, `JOURNAL.md`, ensaios |

Com 3 pessoas: P1+P5, P2+P4, P3.

### 15.2 Cronograma

| Janela | Entrega | Critério de pronto |
|---|---|---|
| **22/11, até 14h** | Repositório, estrutura hexagonal, `.env`, dados da demo escolhidos | `pytest` roda; edital e IFC no repositório |
| **22/11, até 16h** | Leitura do PDF por página; resumo do IFC; segmentação de tópicos | CLI lista tópicos e classes do modelo |
| **22/11, até 18h** | **Marco 1:** EIR → IDS → validação → JSON pela CLI | IDS gerado valida o IFC da demo |
| **22/11, noite** | Cobertura, léxico de termos vagos, BCF, API FastAPI, visualizador carregando o IFC | Relatório JSON com análises A e C |
| **23/11, até 11h** | Revisão do EIR na interface, destaque 3D, relatório HTML, checklist com LLM | Fluxo completo pela interface |
| **23/11, até 13h** | Gabarito medido, recomendações, painel, bSDD | Métricas da seção 14 calculadas |
| **23/11, 14h** | **Congelamento do código** | Só correção de bugs depois disso |
| **23/11, 14h–17h20** | README, GitHub público, slides, 2 ensaios cronometrados, cache aquecido | Demo roda 3 vezes seguidas sem falha |

### 15.3 Regras de corte de escopo

Se o cronograma atrasar, corte nesta ordem:
1. Contradições entre cláusulas.
2. Leitura de BCF no 3D.
3. bSDD (manter só os Psets oficiais).
4. Checklist com LLM (manter só o léxico).
5. Edição do EIR na interface (manter aceitar e rejeitar).

**Nunca corte:** IDS gerado por código, validação ifctester, cobertura, rastreabilidade e o destaque no 3D ou o plano B.

---

## 16. Roteiro do pitch e da demo (≤ 5 min)

| Tempo | Conteúdo |
|---|---|
| 0:00–0:40 | **Problema:** o edital pede BIM, mas não diz o que exigir; a verificação é manual; os defeitos do edital aparecem na obra |
| 0:40–1:00 | **Solução em uma frase:** "verificamos o edital e o modelo, um contra o outro, com padrões abertos" |
| 1:00–3:00 | **Demo ao vivo:** upload → tópicos → EIR com trecho do edital → aprovação → IDS → 3D com conflitos → clique no elemento mostra a página do edital → painel de cobertura e apontamentos do edital |
| 3:00–3:40 | **Open BIM e confiança:** IFC, IDS, BCF, bSDD e Psets oficiais; "o LLM não escreve XML"; citações conferidas |
| 3:40–4:20 | **Números medidos:** recall, precisão, tempo antes × depois, cobertura; **limites** declarados |
| 4:20–4:45 | **Jornada e equipe:** o que tentamos, o que falhou, quem ajudou |
| 4:45–5:00 | **Próximos passos:** integração com CDEs via OpenCDE, biblioteca de cláusulas modelo |

**Seguro da demo:** cache do LLM aquecido e um vídeo gravado da demo como reserva.

---

## 17. Decisões em aberto

| # | Decisão | Padrão adotado até haver resposta | Dono |
|---|---|---|---|
| D1 | Provedor de LLM (Claude, OpenAI ou Azure OpenAI) | Porta agnóstica; implementar o adaptador do provedor que já tiver chave | Time |
| D2 | Frontend: Vite + TS ou Streamlit | Vite + TypeScript + That Open, servido pelo FastAPI | P3 |
| D3 | Edital e IFC da demo | Edital público de escola + IFC público de exemplo | P4 |
| D4 | Nome do time e do produto | "EditalCheck" (provisório) | Time |
| D5 | Repositório público desde o início ou só no fim | Público desde o início (código aberto pontua mais) | Time |
| D6 | Mencionar produtos do Construtivo no pitch | Não mencionar sem consultar a banca | Luis Felipe |

---

## 18. Riscos e mitigação

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| LLM inventa requisito ou norma | Alta | Alto | Salvaguardas S1–S5; revisão humana; lista fechada de referências |
| Edital escaneado ou mal formatado | Média | Alto | Escolher edital com texto (D3); RF-03 detecta e avisa |
| IDS válido mas semanticamente errado | Média | Alto | Rastreabilidade + aprovação humana + gabarito |
| Visualizador 3D atrasa | Média | Médio | Começar cedo; plano B (HTML + BCF em ferramenta externa) |
| API do LLM lenta ou fora do ar na demo | Média | Alto | Cache em disco; vídeo de reserva |
| Mudança de API entre versões das bibliotecas | Média | Médio | Fixar versões no `pyproject.toml` e no `package.json`; conferir a documentação |
| Escopo grande demais | Alta | Alto | Prioridades Must/Should/Could; regras de corte (15.3); congelamento às 14h |
| IFC sem as propriedades da demo | Média | Médio | P4 prepara o modelo com casos de acerto e erro |
| Licença incompatível (AGPL) | Baixa | Alto | RNF-09; conferir licenças ao instalar |
| Dados sensíveis enviados ao LLM | Baixa | Alto | Só documentos públicos; aviso na interface |

---

## 19. Escalabilidade e roadmap pós-hackathon

A arquitetura hexagonal permite evoluir sem reescrever o domínio:

| Evolução | O que muda | O que não muda |
|---|---|---|
| Fila de processamento (ex.: Celery/RQ) para IFCs grandes | Entrypoint e orquestração | Casos de uso e domínio |
| Banco de dados e multiusuário | Adaptador `ProjectRepository` | Todo o resto |
| Armazenamento de objetos para arquivos | Adaptador de storage | Todo o resto |
| Outro provedor de LLM ou modelo local | Adaptador `RequirementExtractor` | Salvaguardas e domínio |
| Integração com CDE via APIs OpenCDE (Documents, BCF) | Novos adaptadores | Domínio |
| Biblioteca de cláusulas modelo por tipo de obra | Novo recurso + bSDD | Fluxo principal |
| Publicação de um dicionário brasileiro de requisitos no bSDD | Conteúdo | Código |
| Regras geométricas (fora do IDS) | Novo analisador | Formato de apontamento |

**Escala de processamento:**
- A validação é por especificação IDS e pode ser paralelizada.
- O LLM é chamado por tópico, não pelo edital inteiro, o que controla custo e contexto.
- O cache por hash evita chamadas repetidas.

---

## 20. Definição de pronto

**Uma funcionalidade está pronta quando:**
- roda pela interface ou pela CLI com os dados da demo;
- tem teste das regras de domínio que ela usa;
- não tem prints de debug nem variáveis temporárias;
- está registrada no `JOURNAL.md`.

**O projeto está pronto para o pitch quando:**
- [ ] Fluxo completo roda 3 vezes seguidas sem erro
- [ ] IDS, BCF, relatório HTML e EIR baixam corretamente
- [ ] Um elemento em conflito leva ao trecho e à página do edital
- [ ] Indicadores do painel conferem com o relatório
- [ ] Métricas da seção 14 medidas e nos slides
- [ ] Limites declarados nos slides
- [ ] README com problema, arquitetura, padrões Open BIM e como rodar
- [ ] Repositório no GitHub (público, de preferência)
- [ ] Cache aquecido e vídeo de reserva gravado
- [ ] Pitch ensaiado em até 5 min
