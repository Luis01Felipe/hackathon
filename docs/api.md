# Contrato da API HTTP do EditalCheck (v2)

Base: `/api`. Todas as respostas são JSON em UTF-8, salvo downloads.
Os nomes dos campos seguem as entidades de `backend/src/editalcheck/domain/models.py`.
Enums são serializados pelo valor em minúsculas (ex.: `"aprovado"`, `"nao_conformidade"`).

Erros: `{"detail": "mensagem em português"}` com status 400, 404, 409, 413 ou 422.

**Nomenclatura.** A interface usa **requisitos de informação (RI)**. As rotas usam o prefixo `/ri`.
As rotas antigas com `/eir` continuam aceitas, fora da documentação OpenAPI, para compatibilidade.
No código, a entidade continua se chamando `Eir`.

**Dados.** No modo `efemero` (padrão), projetos, arquivos e relatórios ficam só em memória.
Eles somem com `DELETE /api/projetos/{id}`, após `ttl_min` minutos sem uso ou quando o processo reinicia.
Depois disso, as rotas do projeto respondem `404`.

## Configuração

### `GET /api/config`

```json
{ "versao": "0.1.0", "modo_ia": "gemini", "modelo_llm": "gemini-4-hydrogen", "bsdd_ativo": true,
  "demo_disponivel": true, "demo_com_licoes": true, "limite_upload_mb": 200,
  "modo_dados": "efemero", "ttl_min": 120, "disponivel_ate": "25/11/2026",
  "aviso_ia": "Trechos do edital e das lições aprendidas são enviados à API paga do Google Gemini...",
  "documentos_contexto": ["referencia-ri.pdf"], "versoes_ifc": ["IFC2X3", "IFC4", "IFC4X3_ADD2"] }
```

- `modo_ia`: `"gemini"` com chave configurada; `"offline"` quando o sistema usa só regras.
- `aviso_ia`: texto do aviso mostrado antes da primeira chamada à IA (`null` sem IA).
- `documentos_contexto`: documentos de referência carregados de `backend/resources/contexto/`.

## Projetos

### `POST /api/projetos` (multipart/form-data)

| Campo | Obrigatório | Conteúdo |
|---|---|---|
| `edital` | sim | PDF com texto |
| `modelo` | não | IFC. Sem ele, o projeto entra no modo "revisar edital" |
| `licoes` | não | Um ou mais arquivos `.txt`, `.md` ou `.pdf` de lições aprendidas (até 10) |
| `versao_ifc` | não | Sem modelo: `IFC2X3`, `IFC4` ou `IFC4X3_ADD2`. Padrão: versão citada no edital, ou `IFC4` |

Resposta `201` com `ProjetoResumo`:

```json
{
  "id": "a1b2c3d4", "criado_em": "2026-11-23T10:00:00", "edital_arquivo": "edital.pdf",
  "modelo_arquivo": "modelo.ifc", "schema_ifc": "IFC4", "paginas": 5, "total_elementos": 133,
  "classes": [{"nome": "IfcDoor", "contagem": 16, "especificavel": true}],
  "topicos_total": 18, "requisitos_total": 0, "ids_gerado": false, "avisos": ["..."],
  "modo_ia": "offline", "sem_modelo": false,
  "licoes": [LicaoAprendida], "documentos_licoes": ["licoes_aprendidas.txt"],
  "marcos": [MarcoEntrega], "ids_marco_id": null, "ids_versao_ifc": null
}
```

Erros: `422` para PDF sem texto, IFC ilegível ou lição em formato não aceito; `413` acima do limite.

`LicaoAprendida`:

```json
{ "id": "LIC-01", "titulo": "Salas de baterias e de nobreak não podem ter janelas",
  "regra": "Salas de baterias e de nobreak não podem ter janelas nem iluminação natural.",
  "evidencia": {"pagina": 1, "trecho": "Salas de baterias e de nobreak não podem ter janelas...", "fonte": "licoes"},
  "documento": "licoes_aprendidas.txt", "contexto": "", "termos_elemento": ["baterias"],
  "ifc_class": null, "extraida_por": "regras" }
```

`MarcoEntrega`: `{"id": "MAR-01", "nome": "Anteprojeto", "descricao": "", "evidencia": Evidencia | null}`.
Os marcos citados no edital são detectados na importação.

### `POST /api/projetos/demo?com_licoes=true`

Cria um projeto com `data/demo/edital.pdf`, `data/demo/modelo.ifc` e, se `com_licoes`, `data/demo/licoes_aprendidas.txt`.

### `GET /api/projetos/{id}` → `ProjetoResumo`

### `DELETE /api/projetos/{id}` → `204`

Apaga o projeto, os arquivos e as verificações. `404` se já não existir.

### `GET /api/projetos/{id}/topicos` → `Topico[]`

```json
[{ "id": "TOP-06", "numero": "4.1", "titulo": "Formato e entrega do modelo", "nivel": 2,
   "pagina_inicio": 2, "pagina_fim": 2, "texto": "[p. 2]\n4.1 Formato e entrega do modelo\n4.1.1 ...",
   "relevante_bim": true, "resumo": "Exige IFC 4 e três marcos de entrega.",
   "pai_id": "TOP-05", "agrupador": false }]
```

- Os tópicos formam uma árvore pelo `pai_id`. `agrupador: true` indica seção sem texto próprio.
- Ao gerar os RI, um agrupador enviado em `topicos` é trocado pelos subtópicos dele.

### `GET /api/projetos/{id}/modelo.ifc` → IFC enviado (`404` sem modelo)

### `GET /api/projetos/{id}/edital.pdf` → edital original, para o visualizador (`Content-Disposition: inline`)

### `GET /api/projetos/{id}/topicos/regioes`

Faixa de cada tópico no PDF, do título até o início do tópico seguinte (sem cabeçalho e rodapé):

```json
{ "TOP-06": [{"pagina": 2, "x0": 0.0908, "y0": 0.2308, "x1": 0.9094, "y1": 0.3714}] }
```

Coordenadas em **frações da página** (0 a 1, origem no canto superior esquerdo), independentes da escala de desenho.

### `GET /api/projetos/{id}/consumo` → `ConsumoEtapa[]`

```json
[{ "etapa": "Requisitos de informação", "chamadas": 12, "chamadas_cache": 0,
   "tokens_entrada": 25100, "tokens_saida": 9800, "duracao_s": 41.2 }]
```

Tokens informados pelo provedor de IA, somados por etapa, desde a importação do projeto.

## Lições aprendidas e marcos

### `POST /api/projetos/{id}/licoes` (multipart, campo `licoes`, um ou mais arquivos)

Lê os documentos e substitui as lições de documentos com o mesmo nome. Resposta:

```json
{ "licoes": [LicaoAprendida], "avisos": ["..."], "descartadas": 0 }
```

`descartadas`: lições cujo trecho citado pela IA não existe no documento (salvaguarda S2).

### `GET /api/projetos/{id}/licoes` → `LicaoAprendida[]`

### `GET /api/projetos/{id}/marcos` → `MarcoEntrega[]`

### `PUT /api/projetos/{id}/marcos`

Corpo: `{"marcos": [{"id": "MAR-01", "nome": "Anteprojeto"}, {"nome": "Projeto executivo"}]}`.
Substitui a lista (até 20). Marco sem `id` recebe um novo. Marcos removidos saem dos requisitos.

## Requisitos de informação (RI)

`Requisito`:

```json
{
  "id": "REQ-001", "topico_id": "TOP-05", "descricao": "IfcDoor deve ter a propriedade Pset_DoorCommon.FireRating",
  "evidencia": {"pagina": 3, "trecho": "Todas as portas deverão conter ...", "fonte": "edital"},
  "verificavel_por_ids": true, "motivo_nao_verificavel": null,
  "ifc_class": "IfcDoor", "predefined_type": null, "faceta": "property",
  "pset": "Pset_DoorCommon", "propriedade": "FireRating", "tipo_dado": "IfcLabel",
  "restricao": null, "cardinalidade": "required", "origem_vocabulario": "pset_oficial",
  "bsdd_uri": "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating",
  "status": "proposto", "sugerido_por_lacuna": false, "clausula": "5.1.1",
  "gerado_por": "llm", "avisos": [], "marcos": [], "licao_id": null
}
```

- `faceta`: `property | attribute | classification | material | partOf | null`.
- `status`: `proposto | aprovado | editado | rejeitado`.
- `gerado_por`: `llm | regras | usuario | lacuna | licao`. Requisitos de lição têm `licao_id`, evidência com `fonte: "licoes"` e um aviso: a regra não está no edital.
- `marcos`: IDs de marcos em que o requisito vale. Lista vazia = todos os marcos.

`EirResposta`:

```json
{ "versao": 1, "data": "2026-11-23T10:10:00", "topicos_selecionados": ["TOP-05"],
  "aprovado_por": null, "requisitos": [Requisito], "avisos": ["..."], "descartados": 1 }
```

### `POST /api/projetos/{id}/ri`

Corpo: `{"topicos": ["TOP-05", "TOP-06"]}`. Gera os RI dos tópicos e das lições aprendidas (síncrono).

### `GET /api/projetos/{id}/ri` → `EirResposta` (`404` se ainda não gerados)

### `PATCH /api/projetos/{id}/ri/requisitos/{req_id}`

```json
{ "acao": "aprovar" }
{ "acao": "rejeitar" }
{ "acao": "reabrir" }
{ "acao": "editar", "campos": { "ifc_class": "IfcDoor", "marcos": ["MAR-03"] } }
```

Campos editáveis: `descricao`, `ifc_class`, `predefined_type`, `faceta`, `pset`, `propriedade`, `tipo_dado`, `restricao`, `cardinalidade`, `verificavel_por_ids`, `motivo_nao_verificavel` e `marcos`.
Em `editar`, só os campos enviados mudam e o status vira `editado`.

### `POST /api/projetos/{id}/ri/aprovar-todos`

Corpo: `{"somente_verificaveis": true}`.

### `POST /api/projetos/{id}/ri/requisitos` (ciclo fechado)

Corpo: `{"verificacao_id": "v1x2", "apontamento_id": "APT-007"}`. Cria requisitos a partir de um apontamento `lacuna_cobertura`.

### `GET /api/projetos/{id}/ri.xlsx` → planilha dos RI

## IDS

### `POST /api/projetos/{id}/ids`

Corpo (opcional): `{"marco_id": "MAR-03", "versao_ifc": "IFC4"}`. Sem corpo: contrato inteiro na versão do modelo.

```json
{ "especificacoes": 6, "valido": true, "erros": [], "avisos": [],
  "requisitos_incluidos": ["REQ-008"], "escopo": "Projeto executivo", "marco_id": "MAR-03",
  "versao_ifc": "IFC4", "url": "/api/projetos/a1b2c3d4/ids.xml" }
```

- O cabeçalho do IDS traz `purpose` (contrato de dados da contratação) e `milestone` (marco ou "Contrato inteiro").
- `avisos` alerta quando a versão do IDS difere da versão do modelo.
- `409` quando não há requisito aprovado e verificável no escopo; `422` para marco ou versão inválidos.

### `GET /api/projetos/{id}/ids.xml` → arquivo IDS 1.0 do último escopo gerado

## Verificação

### `POST /api/projetos/{id}/verificacoes` → `202` com `Verificacao`

```json
{ "id": "v1x2", "projeto_id": "a1b2c3d4", "status": "executando",
  "progresso": {"conformidade": "executando", "qualidade_edital": "pendente", "licoes": "pendente",
                "cobertura": "concluida", "saude_modelo": "concluida", "relatorio": "pendente"},
  "iniciado_em": "...", "concluido_em": null, "erro": null, "avisos": [] }
```

- Cada análise: `pendente | executando | concluida | falhou | ignorada`.
- Sem modelo, `conformidade`, `cobertura` e `saude_modelo` vêm como `ignorada`. Sem lições, `licoes` também.

### `GET /api/verificacoes/{vid}` → `Verificacao` (consultar a cada 1 s até `concluida` ou `falhou`)

### `GET /api/verificacoes/{vid}/relatorio` → `Relatorio`

Campos principais (além dos da v1: `indicadores`, `apontamentos`, `resultados_ids`, `cobertura`, `checklist`, `itens_checklist`, `requisitos`, `estado_elementos`, `avisos`, `duracoes_s`):

```json
{
  "escopo": "Contrato inteiro", "versao_ifc_ids": "IFC4", "sem_modelo": false,
  "licoes": [LicaoAprendida],
  "verificacoes_licoes": [{ "licao_id": "LIC-01", "explicita": false, "evidencia": null,
      "trecho_relacionado": {"pagina": 3, "trecho": "5.3.2 As janelas deverão garantir iluminação natural...", "fonte": "edital"},
      "justificativa": "...", "redacao_sugerida": "...", "avaliado_por": "regras" }],
  "decisoes": [{ "apontamento_id": "APT-001", "status": "aceito", "comentario": "", "autor": "Fiscal", "data": "..." }],
  "consumo": [ConsumoEtapa],
  "custo": { "tokens_entrada": 25100, "tokens_saida": 9800, "usd": null,
             "preco_entrada_usd_mtok": null, "preco_saida_usd_mtok": null, "fonte_preco": "" },
  "tempo_manual": { "medido": false, "horas": null, "tarefa": "...", "amostra": "", "metodo": "", "data": "" },
  "contexto_usado": [],
  "indicadores": { "...": "...", "apontamentos_por_origem": {"edital": 26, "modelo": 7},
                   "verificacao_manual": 14, "licoes_total": 4, "licoes_nao_explicitas": 3 },
  "apontamentos": [{
    "id": "APT-006", "tipo": "licao_nao_explicita", "severidade": "alta", "destinatario": "contratante",
    "origem": "edital", "verificacao_manual": false, "licao_id": "LIC-01",
    "titulo": "Lição aprendida ausente do edital: ...", "analise": "licoes",
    "evidencias_edital": [{"pagina": 3, "trecho": "...", "fonte": "edital"},
                          {"pagina": 1, "trecho": "...", "fonte": "licoes"}],
    "elementos": [{ "global_id": "1WhAevr9n0Q9Z_fWQh$CWP", "step_id": 910, "classe": "IfcSpace",
                    "nome": "S106", "nome_longo": "Sala de baterias", "pavimento": "Térreo",
                    "posicao": {"centro": [12.0, 11.0, 0.025], "minimo": [8.1, 8.1, 0.0], "maximo": [15.9, 13.9, 0.05]} }],
    "como_agir": "...", "por_que": "...", "referencias": [], "detalhe": "O modelo já repete o erro: ..."
  }]
}
```

- `tipo`: `nao_conformidade | qualidade_modelo | ambiguidade | nao_verificavel | item_ausente | contradicao | lacuna_cobertura | licao_nao_explicita | duplicidade`.
- `origem`: `modelo` para `nao_conformidade` e `qualidade_modelo`; `edital` para os demais. Regra determinística.
- `verificacao_manual: true` para `nao_verificavel`. Esses itens ficam fora de `apontamentos_por_severidade` e contam em `verificacao_manual`.
- `posicao`: caixa envolvente em metros, no sistema do projeto (`null` se não houver geometria).
- `custo.usd` é `null` quando os preços não estão configurados (`LLM_PRECO_*`).

### `PATCH /api/verificacoes/{vid}/apontamentos/{apt_id}`

Corpo: `{"status": "dispensado", "comentario": "Combinado em reunião.", "autor": "Fiscal"}`.
`status`: `pendente | aceito | rejeitado | em_discussao | dispensado`. `rejeitado` e `dispensado` exigem comentário (`422` sem ele).
A decisão não remove o apontamento. O relatório HTML é regenerado.

### `GET /api/verificacoes/{vid}/relatorio.html` → relatório HTML em português

Seções "Corrigir no edital" e "Corrigir no modelo", verificação manual, dispensados, lições, custo e tempo, glossário.

### `GET /api/verificacoes/{vid}/resultado.bcf` → BCF 2.1 (zip)

Um tópico por apontamento com elementos (modelo e lições). Um viewpoint por elemento. Cada comentário traz nome, classe, GlobalId, pavimento, coordenada XYZ, falha, exigência e trecho de origem. Os rótulos trazem a origem ("Corrigir no modelo" ou "Corrigir no edital").

### `GET /api/verificacoes/{vid}/regioes`

Posição de cada apontamento no PDF do edital, para a aba "Edital com os ajustes":

```json
[{ "apontamento_id": "APT-006", "localizado": true, "paginas": [3],
   "regioes": [{"pagina": 3, "x0": 0.0958, "y0": 0.452, "x1": 0.7612, "y1": 0.4691}] },
 { "apontamento_id": "APT-007", "localizado": false, "paginas": [], "regioes": [] }]
```

- O trecho é localizado palavra por palavra (aceita quebra de linha e hifenização).
- `localizado: false` com `paginas` preenchido: o visualizador vai para a página citada.
- Sem `paginas`: o apontamento pede uma cláusula nova (item ausente, lacuna, lição).

### `GET /api/verificacoes/{vid}/edital-anotado.pdf` → PDF com as sugestões

Páginas iniciais com o sumário de ajustes (links para cada trecho e para as referências), grifo e nota em cada trecho, etiqueta na margem que volta ao sumário e índice (bookmarks) "Corrigir no edital" e "Corrigir no modelo". Os apontamentos do modelo aparecem na cláusula que gerou o requisito.

### `GET /api/verificacoes/{vid}/esclarecimentos.xlsx` → matriz de esclarecimentos (apontamentos do edital, pergunta sugerida e decisão)

A minuta é gerada automaticamente. Valide com o jurídico antes de protocolar.
