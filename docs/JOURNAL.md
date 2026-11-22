# Diário de decisões — EditalCheck

Registro da jornada do time. Vira o slide de progresso do pitch.

## 22/11/2026

### Decisões

- **Provedor de LLM (D1):** Google Gemini, modelo `gemini-4-hydrogen`, pelo SDK `google-genai`, com saída JSON validada por schema Pydantic. A porta é agnóstica: um novo provedor exige só um novo `JsonCompletion` (RNF-05).
- **Modo offline:** sem chave, ou se o LLM falhar, o sistema troca para regras determinísticas e avisa na tela (RNF-02). Isso deixa a demo à prova de rede e dá uma linha de base para comparar com o LLM.
- **Dados da demo (D3):** edital e IFC **sintéticos**, gerados por código. Motivos: licença limpa, erros planejados e nenhum dado de cliente. O gabarito foi escrito a partir do texto do edital.
- **Frontend (D2):** Vite + TypeScript sem framework de UI + `@thatopen/components` 3.6.0 (MIT). O FastAPI serve o build em `/`.
- **IDS:** especificações com `minOccurs=0`. Uma classe ausente do modelo não vira não conformidade; a análise de cobertura trata a ausência.
- **Severidade de contradição:** fora da matriz da seção 9.5. Adotamos "média".
- **S3 simplificada:** classe IFC inexistente marca o requisito como não verificável, sem nova chamada de reparo ao LLM.
- **Página corrigida em S2:** se o trecho existe em outra página do mesmo tópico, a evidência é aceita com a página certa.
- **BCF:** um tópico por apontamento (não por elemento), com todos os GlobalIds selecionados e a câmera no centro dos elementos.
- **Ciclo fechado:** a lacuna de cobertura vira até 3 requisitos sugeridos (Psets oficiais), marcados `sugerido_por_lacuna`.

### Tentativas que falharam e como resolvemos

- `ifctester.ids.from_string(validate=True)` rejeitava IDS válido com restrição numérica (`base="xs:double"`): o ElementTree perde o prefixo `xs`. Passamos a validar o texto direto no XSD com `xmlschema` e só depois carregar no ifctester (S6).
- O texto extraído do PDF vinha com ligaduras tipográficas ("ﬁ"). O leitor agora expande as ligaduras.
- A checklist em YAML quebrou com "ex.: IFC 4" sem aspas (dois-pontos). Todos os textos foram para aspas.
- No Windows, o registro pode servir `.js` como `text/plain` e quebrar o worker do 3D. A API registra os tipos MIME antes de servir o frontend.
- A heurística de relevância BIM deixava de fora tópicos como "Escadas". Passamos a reconhecer nomes IFC em CamelCase (ex.: `NumberOfRiser`).

### Medições

- Pipeline completo pela CLI, modo offline: menos de 1 s (meta ≤ 3 min).
- Métricas contra o gabarito sintético: recall 100% (19/19), precisão 100% (19/19), citações 100%, IDS válido, checklist 10/10, ambiguidades 10/10.
- **Limite:** os números são otimistas porque o edital sintético e as regras são do mesmo time. É preciso medir de novo com edital público real e com o Gemini.

### Primeira execução com o Gemini e refinos (tarde)

- **Bug encontrado no log real:** a extração do EIR pelo Gemini falhava em todos os tópicos (`got multiple values for argument 'schema'`). O sistema caía nas regras sem que a tela deixasse isso evidente. Causa: a variável de template `schema` colidia com o parâmetro `schema` de `StructuredLlm.gerar`. Correção: parâmetros só posicionais e variável renomeada para `schema_ifc`. Um teste com os prompts reais e cliente simulado passou a cobrir os quatro adaptadores de IA.
- **Defeito achado pelo novo teste:** o vocabulário enviado ao LLM não trazia o tipo de dado das propriedades, embora o prompt anunciasse "Pset.Propriedade: tipo".
- **Tópicos em árvore:** a seção "4 DA MODELAGEM" era descartada por não ter texto próprio, e os itens 4.1–4.3 apareciam como filhos da seção 3 na tela. Agora:
  - todo tópico tem `pai_id`;
  - seções sem texto viram agrupadores;
  - subtópico sem título de seção cria a seção implícita;
  - "ANEXO I – ..." reinicia a numeração;
  - a tela de tópicos ganhou seleção em cascata, estado parcial e recolher/expandir.
- **Desempenho com LLM:** a verificação levou 114 s. As três consultas da análise B rodavam em sequência (53 s) e as 30 recomendações rodavam com 4 em paralelo (61 s). Agora a análise B roda em paralelo, e o paralelismo é configurável (`LLM_PARALELISMO`, padrão 6). Resultado medido: a verificação caiu para 60 s (análise B: 15 s; recomendações: 45 s), e o pipeline completo com o Gemini ficou em 110 s.
- **S2 rígida demais com quebra de linha:** o Gemini citou "W/(m²·K)", mas o PDF tem "W/" e "(m²·K)" em linhas diferentes. A S2 descartou um requisito correto (janelas, `ThermalTransmittance`). A conferência agora tenta de novo ignorando só os espaços; os caracteres continuam precisando ser idênticos. Com isso, o recall do Gemini no gabarito subiu de 94,7% para 100% (19/19).
- **BCF sem viewpoint por elemento (retorno do teste do time):** cada tópico tinha um único viewpoint, com todos os elementos selecionados e a câmera num ponto médio fixo. Para 5 portas espalhadas em 40 m, nenhuma ficava enquadrada. Agora cada tópico traz:
  - uma visão geral, quando o apontamento tem mais de um elemento;
  - um viewpoint por elemento, com só aquele elemento selecionado e pintado de vermelho, e a câmera enquadrando a caixa envolvente dele, calculada pelo IfcOpenShell;
  - um comentário por viewpoint, com nome, classe, GlobalId e motivo da falha;
  - o primeiro viewpoint com o nome `viewpoint.bcfv`, o padrão do BCF 2.0, para ferramentas mais antigas;
  - prioridade, índice e rótulos no tópico.

  Ainda não há imagens (snapshots) nos viewpoints.

### Pendências para o dia 23/11/2026

- [x] Colocar a chave do Gemini no `.env` e rodar `uv run editalcheck demo` com o LLM.
- [ ] Testar com um edital público real e um IFC público.
- [ ] Validar o IFC da demo no Validation Service da buildingSMART.
- [ ] Cronometrar o tempo manual equivalente (1 tópico).
- [ ] Definir nome do time e do produto (D4) e a licença do repositório.
- [ ] Gravar o vídeo de reserva da demo.
