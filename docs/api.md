# Contrato da API HTTP do EditalCheck

Base: `/api`. Todas as respostas são JSON em UTF-8, salvo downloads.
Os nomes dos campos seguem as entidades de `backend/src/editalcheck/domain/models.py`.
Enums são serializados pelo valor em minúsculas (ex.: `"aprovado"`, `"nao_conformidade"`).

Erros: `{"detail": "mensagem em português"}` com status 400, 404, 409, 413 ou 422.

## Configuração

### `GET /api/config`

```json
{ "versao": "0.1.0", "modo_ia": "gemini", "modelo_llm": "gemini-4-hydrogen", "bsdd_ativo": true,
  "demo_disponivel": true, "limite_upload_mb": 200 }
```

`modo_ia` é `"gemini"` quando há chave configurada e `"offline"` quando o sistema usa só regras.

## Projetos

### `POST /api/projetos` (multipart/form-data)

Campos: `edital` (PDF) e `modelo` (IFC). Resposta `201` com `ProjetoResumo`:

```json
{
  "id": "a1b2c3d4", "criado_em": "2026-11-22T15:00:00", "edital_arquivo": "edital.pdf",
  "modelo_arquivo": "modelo.ifc", "schema_ifc": "IFC4", "paginas": 8, "total_elementos": 140,
  "classes": [{"nome": "IfcDoor", "contagem": 12, "especificavel": true}],
  "topicos_total": 14, "requisitos_total": 0, "ids_gerado": false,
  "avisos": ["..."], "modo_ia": "offline"
}
```

Erros: `422` para PDF sem texto (escaneado) ou IFC ilegível; `413` acima do limite.

### `POST /api/projetos/demo`

Cria um projeto com `data/demo/edital.pdf` e `data/demo/modelo.ifc`. Resposta igual à anterior.

### `GET /api/projetos/{id}` → `ProjetoResumo`

### `GET /api/projetos/{id}/topicos` → `Topico[]`

```json
[{ "id": "TOP-05", "numero": "4", "titulo": "DA MODELAGEM DA INFORMAÇÃO (BIM)", "nivel": 1,
   "pagina_inicio": 2, "pagina_fim": 2, "texto": "[p. 2]\n4 DA MODELAGEM DA INFORMAÇÃO (BIM)",
   "relevante_bim": true, "resumo": null, "pai_id": null, "agrupador": true },
 { "id": "TOP-06", "numero": "4.1", "titulo": "Formato e entrega do modelo", "nivel": 2,
   "pagina_inicio": 2, "pagina_fim": 2, "texto": "[p. 2]\n4.1 Formato e entrega do modelo\n4.1.1 ...",
   "relevante_bim": true, "resumo": "Exige IFC 4 e três marcos de entrega.",
   "pai_id": "TOP-05", "agrupador": false }]
```

- Os tópicos vêm na ordem do edital e formam uma árvore pelo `pai_id`.
- `nivel` é a profundidade na árvore (1 = raiz). Dentro de um anexo ("ANEXO I – ..."), a numeração reinicia e os títulos ficam um nível abaixo do anexo.
- `agrupador: true` indica uma seção sem texto próprio, que só agrupa subtópicos (ex.: "4" quando o texto começa em "4.1"). Ela pode ser implícita ("Seção 4") quando o edital não tem o título da seção.
- Ao gerar o EIR, um agrupador enviado em `topicos` é trocado pelos subtópicos dele.

## EIR

`Requisito`:

```json
{
  "id": "REQ-001", "topico_id": "TOP-05", "descricao": "Portas devem informar a resistência ao fogo",
  "evidencia": {"pagina": 4, "trecho": "Todas as portas deverão conter ..."},
  "verificavel_por_ids": true, "motivo_nao_verificavel": null,
  "ifc_class": "IfcDoor", "predefined_type": null, "faceta": "property",
  "pset": "Pset_DoorCommon", "propriedade": "FireRating", "tipo_dado": "IfcLabel",
  "restricao": {"tipo": "intervalo", "valores": [], "minimo": 0.16, "maximo": 0.18} ,
  "cardinalidade": "required", "origem_vocabulario": "pset_oficial",
  "bsdd_uri": "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/prop/FireRating",
  "status": "proposto", "sugerido_por_lacuna": false, "clausula": "5.1.1",
  "gerado_por": "llm", "avisos": []
}
```

- `faceta`: `property | attribute | classification | material | partOf | null`.
- `restricao.tipo`: `valor | enumeracao | padrao | intervalo`; `restricao` pode ser `null`.
- `status`: `proposto | aprovado | editado | rejeitado`.
- `origem_vocabulario`: `pset_oficial | bsdd | customizado | null`.

`EirResposta`:

```json
{ "versao": 1, "data": "2026-11-22T15:10:00", "topicos_selecionados": ["TOP-05"],
  "aprovado_por": null, "requisitos": [Requisito], "avisos": ["..."], "descartados": 1 }
```

### `POST /api/projetos/{id}/eir`

Corpo: `{"topicos": ["TOP-05", "TOP-06"]}`. Gera o EIR (síncrono). Resposta `EirResposta`.

### `GET /api/projetos/{id}/eir` → `EirResposta` (404 se ainda não gerado)

### `PATCH /api/projetos/{id}/eir/requisitos/{req_id}`

Corpo:

```json
{ "acao": "aprovar" }
{ "acao": "rejeitar" }
{ "acao": "reabrir" }
{ "acao": "editar", "campos": { "descricao": "...", "ifc_class": "IfcDoor", "predefined_type": null,
  "faceta": "property", "pset": "Pset_DoorCommon", "propriedade": "FireRating",
  "tipo_dado": "IfcLabel", "restricao": null, "cardinalidade": "required",
  "verificavel_por_ids": true, "motivo_nao_verificavel": null } }
```

Em `editar`, só os campos enviados mudam e o status vira `editado`. Resposta: `Requisito`.

### `POST /api/projetos/{id}/eir/aprovar-todos`

Corpo: `{"somente_verificaveis": true}`. Aprova todos os requisitos `proposto`. Resposta `EirResposta`.

### `POST /api/projetos/{id}/eir/requisitos` (ciclo fechado)

Corpo: `{"verificacao_id": "v1x2", "apontamento_id": "APT-007"}`.
Cria requisitos a partir das propriedades sugeridas de um apontamento `lacuna_cobertura`.
Resposta: `Requisito[]` com `sugerido_por_lacuna: true` e `status: "proposto"`.

### `GET /api/projetos/{id}/eir.xlsx` → planilha do EIR

## IDS

### `POST /api/projetos/{id}/ids`

```json
{ "especificacoes": 6, "valido": true, "erros": [], "requisitos_incluidos": ["REQ-001"],
  "url": "/api/projetos/a1b2c3d4/ids.xml" }
```

`409` quando não há requisito aprovado e verificável.

### `GET /api/projetos/{id}/ids.xml` → arquivo IDS 1.0

## Verificação

### `POST /api/projetos/{id}/verificacoes` → `202` com `Verificacao`

```json
{ "id": "v1x2", "projeto_id": "a1b2c3d4", "status": "executando",
  "progresso": {"conformidade": "executando", "qualidade_edital": "pendente",
                "cobertura": "concluida", "saude_modelo": "concluida", "relatorio": "pendente"},
  "iniciado_em": "...", "concluido_em": null, "erro": null, "avisos": [] }
```

- `status`: `pendente | executando | concluida | falhou`.
- Cada análise em `progresso`: `pendente | executando | concluida | falhou | ignorada`.

### `GET /api/verificacoes/{vid}` → `Verificacao` (consultar a cada 1 s até `concluida` ou `falhou`)

### `GET /api/verificacoes/{vid}/relatorio` → `Relatorio`

```json
{
  "verificacao_id": "v1x2", "projeto_id": "a1b2c3d4", "gerado_em": "...",
  "edital_arquivo": "edital.pdf", "modelo_arquivo": "modelo.ifc", "schema_ifc": "IFC4",
  "modo_ia": "offline",
  "indicadores": {
    "conformidade_percentual": 62.5, "especificacoes_total": 8, "especificacoes_aprovadas": 5,
    "elementos_verificados": 60, "elementos_nao_conformes": 14,
    "cobertura_percentual": 50.0, "classes_especificaveis": 10, "classes_cobertas": 5,
    "checklist_presentes": 5, "checklist_parciais": 1, "checklist_total": 10,
    "requisitos_aprovados": 9, "requisitos_nao_verificaveis": 2,
    "apontamentos_por_severidade": {"alta": 4, "media": 6, "baixa": 3},
    "apontamentos_por_destinatario": {"projetista": 6, "contratante": 7},
    "apontamentos_por_tipo": {"nao_conformidade": 3}
  },
  "apontamentos": [{
    "id": "APT-001", "tipo": "nao_conformidade", "severidade": "alta",
    "destinatario": "projetista", "titulo": "...", "analise": "A",
    "evidencias_edital": [{"pagina": 4, "trecho": "..."}],
    "elementos": [{"global_id": "2O2Fr$t4X7Zf8NOew3FLOH", "step_id": 123, "classe": "IfcDoor",
                   "nome": "Porta P01"}],
    "requisito_id": "REQ-001", "como_agir": "...", "por_que": "...",
    "referencias": [{"tipo": "clausula_edital", "rotulo": "Edital, item 5.1.1, p. 4", "uri": null}],
    "gerado_por_ia": false, "referencia_a_confirmar": false, "classe_ifc": "IfcDoor",
    "propriedades_sugeridas": [{"pset": "Pset_DoorCommon", "nome": "FireRating", "tipo_dado": "IfcLabel"}],
    "detalhe": "..."
  }],
  "resultados_ids": [{ "nome_especificacao": "REQ-001 · ...", "requisito_id": "REQ-001", "status": false,
                       "aplicaveis": 12, "aprovados": 8, "falhas": [{"global_id": "...", "step_id": 1,
                       "classe": "IfcDoor", "nome": "P01", "motivo": "..."}], "elementos_aprovados": ["..."] }],
  "cobertura": {"percentual": 50.0, "classes": [{"classe": "IfcDoor", "contagem": 12, "coberta": true,
                                                  "requisitos": ["REQ-001"]}]},
  "checklist": [{"item_id": "CHK-01", "status": "presente", "evidencia": {"pagina": 3, "trecho": "..."},
                 "justificativa": "...", "avaliado_por": "regras"}],
  "itens_checklist": [{"id": "CHK-01", "item": "Formato e versão do IFC de entrega", "critico": true,
                       "descricao": "...", "palavras_chave": ["IFC"]}],
  "requisitos": [Requisito],
  "estado_elementos": [{"global_id": "...", "step_id": 123, "estado": "nao_conforme"}],
  "avisos": ["..."], "duracoes_s": {"conformidade": 0.8}
}
```

`estado_elementos.estado`: `conforme | nao_conforme`. Elementos ausentes da lista não têm requisito (cinza no 3D).

### `GET /api/verificacoes/{vid}/relatorio.html` → relatório HTML em português

### `GET /api/verificacoes/{vid}/resultado.bcf` → BCF 2.1 (zip) das não conformidades

### `GET /api/projetos/{id}/modelo.ifc` → IFC original para o visualizador 3D
