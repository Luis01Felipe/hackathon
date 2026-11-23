# Especificação técnica v2 — Atualização do EditalCheck após a banca

> **Hackathon Open BIM + IA** · Sinaenco · 22–23/11/2026
> Versão 2.0 · 22/11/2026
> Base: [especificação v1.0](especificacao-tecnica.md) e código da `main` (commit `d11a9e8`)
> Fontes: transcrições "importante.mp3" (59:06) e "importante 2.mp3" (17:10), gravadas na apresentação do protótipo à banca organizadora
> Status: **implementada em 23/11/2026** (seção 17). Decisões do time na seção 13.

---

## Sumário

1. Objetivo deste documento
2. Resumo das mudanças
3. Feedback da banca, rastreável
4. Posicionamento, escopo e nomenclatura
5. Requisitos funcionais novos e alterados
6. Requisitos não funcionais novos e alterados
7. Mudanças no modelo de domínio
8. Portas e adaptadores (arquitetura hexagonal)
9. API HTTP
10. Interface e relatório
11. Testes e critérios de aceite
12. Plano de execução e priorização
13. Decisões em aberto e pontos a confirmar
14. Riscos novos
15. Mensagens para o pitch
16. Fora do escopo e roadmap
17. Status da implementação

---

## 1. Objetivo deste documento

Este documento define o que muda no EditalCheck depois do debate com a banca organizadora.
A especificação v1.0 continua valendo. Este documento só descreve o que é novo, alterado ou corrigido.

**Como ler as fontes:**
- **T1** é a transcrição "importante.mp3". **T2** é a transcrição "importante 2.mp3".
- Os tempos seguem o formato da transcrição (ex.: T1 0:29:20).
- A transcrição automática troca siglas e nomes. Exemplos: "AER", "AIR" e "IR" aparecem no lugar de EIR, PIR e AIR. "Cloud" é Claude. "BSTD" é bSDD.
- Os rótulos de locutor não identificam pessoas. Este documento atribui as falas à "banca" ou ao "time" pelo contexto, sem nomes.
- Tudo o que não foi possível confirmar está marcado como **[confirmar]**.

---

## 2. Resumo das mudanças

| # | Mudança | Motivo (feedback) | Prioridade |
|---|---|---|---|
| M1 | Alinhar o tratamento de dados ao que foi dito à banca: modo efêmero, sem arquivo do usuário em disco | FB-04 | **Must** |
| M2 | Origem da inconsistência bem visível: **edital** (contratante) × **modelo** (contratado), com cor e seção próprias | FB-13 | **Must** |
| M3 | Escopo e nomenclatura explícitos: "contrato de dados da contratação", EIR, marcos e glossário | FB-15, FB-24, FB-25 | **Must** |
| M4 | **Quarta entrada:** documento de lições aprendidas (ciclo PDCA) | FB-07, FB-18 | **Must** |
| M5 | Salvaguardas contra abuso: contexto e lições só acrescentam; dispensa exige justificativa visível | FB-12 | **Must** |
| M6 | BCF com coordenada XYZ, propriedades e motivo em cada viewpoint | FB-09, FB-20 | **Must** |
| M7 | Referência explícita ao IDM (ISO 29481) e mapa de processo do fluxo | FB-23 | **Must** |
| M8 | Consumo de IA medido (tokens, tempo, custo) e comparativo com o trabalho manual medido | FB-27 | **Must** |
| M9 | Menos ruído: agrupar apontamentos de baixa severidade e separar a "verificação manual" | FB-05, FB-06 | **Should** |
| M10 | Edital anotado em PDF e matriz de esclarecimentos com decisão aceita / rejeitada | FB-10, FB-20, FB-21 | **Should** |
| M11 | Marcos de entrega: requisitos por marco e IDS por marco ou do contrato inteiro | FB-15, FB-25 | **Should** |
| M12 | Escolha da versão IFC do IDS e confronto com a versão exigida no edital | FB-22 | **Should** |
| M13 | Pacotes de contexto: exemplos nos prompts, NBR 15965, EIR de referência e contexto da empresa | FB-14, FB-26 | **Should** |
| M14 | Visualizador: enquadrar, isolar e mostrar a coordenada do elemento | FB-08 | **Should** |
| M15 | Perfil de uso (contratante, contratado líder, contratado, verificador) | FB-16 | **Should** |
| M16 | Modo "revisar edital" sem IFC | FB-07, FB-21 | **Should** |
| M17 | Comparar a verificação atual com a anterior (resolvidos, novos, persistentes) | FB-11, FB-12 | **Could** |
| M18 | Detectar texto repetido ou sobrescrito no edital | FB-17 | **Could** |
| M19 | Desempenho: menos chamadas ao LLM e paralelismo por tópico | FB-02 | **Could** |
| M20 | Linguagem para não engenheiros (glossário, leitura jurídica) | FB-28 | **Could** |

**Must** é obrigatório antes do pitch. **Should** é desejável. **Could** entra se sobrar tempo ou vai para o roadmap.

---

## 3. Feedback da banca, rastreável

Cada item tem um ID (FB-xx). As seções seguintes citam esses IDs.

| ID | Fonte | O que foi dito (resumo) | Decisão nesta versão |
|---|---|---|---|
| FB-01 | T1 0:00:01 | A validação humana no meio do percurso é obrigatória, por causa da LGPD | Manter a aprovação do EIR. Acrescentar a decisão humana sobre os apontamentos do edital (RF-150) |
| FB-02 | T1 0:00:43–0:02:23; 0:35:35–0:36:51 | A verificação é lenta por causa das muitas chamadas ao LLM. A banca disse que velocidade não é requisito, mas pode ganhar ponto | Reduzir chamadas e paralelizar por tópico (RF-190). Escala horizontal vai para o roadmap |
| FB-03 | T1 0:02:28 | Não há tela de login; um produto precisaria | Fora do escopo do hackathon (seção 16) |
| FB-04 | T1 0:03:07–0:04:54; 0:16:24–0:20:44 | O time afirmou que nada fica no servidor: o arquivo vai para a RAM, segue para a IA e some no fim. Só um log de auditoria sem conteúdo seria aceitável. O servidor sai do ar na quarta-feira | **O código atual não faz isso.** Ver M1 e a seção 5.1 |
| FB-05 | T1 0:05:10; 0:06:38 | O relatório da demo teve 24 apontamentos de severidade alta, 33 média e 269 baixa. "Olha o tamanho desse negócio" | Agrupar e recolher a severidade baixa (RF-160) |
| FB-06 | T1 0:05:53–0:06:33 | O resultado precisa fazer sentido para a engenharia. Mais contexto aumenta a chance de alucinação | Amostra revisada por pessoa de BIM (seção 11.3). Orçamento de contexto por chamada (RNF-16) |
| FB-07 | T1 0:06:56–0:07:40 | Usos: analista na fase de projeto; contratante que vai lançar um novo edital revisa as bases e as lições aprendidas e retroalimenta | Lições aprendidas (M4) e modo sem IFC (M16) |
| FB-08 | T1 0:08:45–0:09:56 | Ao clicar num elemento grande, o zoom quase não muda | Enquadrar, isolar e mostrar XYZ (RF-180) |
| FB-09 | T1 0:09:21–0:09:34 | O apontamento e a coordenada XYZ precisam estar no BCF final. As propriedades aparecem na tela, mas não vão para a exportação | BCF com XYZ e propriedades (RF-170) |
| FB-10 | T1 0:11:13–0:12:03 | Gerar um documento revisado que o contratante possa aceitar ou não | Edital anotado e matriz de esclarecimentos (RF-150 a RF-153) |
| FB-11 | T1 0:13:00–0:15:48 | A maturidade BIM do mercado é baixa. A ferramenta pode servir de repositório de boas práticas e sempre apontar para a buildingSMART. Comparar revisões é útil | Manter os links da buildingSMART. Comparação de verificações (M17) |
| FB-12 | T1 0:25:50–0:28:35 | Ajustar a IA com as "decisões da empresa" torna o sistema abusável: um usuário pode mascarar problemas. O certo é revisar o edital e verificar de novo. A ferramenta deve rodar a cada revisão | Salvaguardas G1–G4 (seção 5.3) |
| FB-13 | T1 0:29:20–0:31:10 | O relatório deve mostrar, de forma bem visível e com cor, se a inconsistência está no edital ou no IFC | M2 (RF-120) |
| FB-14 | T1 0:37:15–0:39:30 | A banca perguntou como o prompt separa os tópicos. Sugeriu dar exemplos, outra área e uma norma brasileira como referência | Exemplos nos prompts e pacotes de contexto (RF-140) |
| FB-15 | T1 0:40:56–0:46:08; 0:53:11–0:57:09 | O EIR está ligado à troca de informação entre processos e marcos de entrega (ISO 19650). Um termo de referência traz requisitos do projeto. O IDS final precisa ser compatível com a entrega. A banca admitiu que usou o termo em dois contextos no material entregue. Um IDS do contrato inteiro é válido e já é usado no mercado, mas o uso deve ficar claro | Seção 4 e marcos de entrega (RF-130) |
| FB-16 | T1 0:46:12–0:49:05 | Quem usa (contratante, contratado líder, subcontratado) muda tudo | Perfil de uso (RF-121) |
| FB-17 | T1 0:47:00–0:48:38 | O time descreveu três análises do edital: cruzamento com o modelo, ambiguidade e texto repetido. A banca pediu para não usar a palavra "validadores", que já nomeia um grupo do evento | Usar "análises". Detectar texto repetido (RF-200) |
| FB-18 | T1 0:49:41–0:50:50; 0:57:54–0:59:01; T2 0:02:11–0:02:36 | Caso real: o edital pedia iluminação natural "quando possível". Foi instalada em salas de baterias, onde não devia. A lição aprendida deve entrar antes de gerar o IDS e deve estar explícita no edital. A banca citou também análise de geometria | M4 (RF-100 a RF-106). Geometria vai para o roadmap |
| FB-19 | T1 0:52:09–0:52:29 | O time não reinventou a roda: usa IDS | Manter. Mensagem do pitch |
| FB-20 | T1 0:52:37–0:52:53 | Comentários no edital e no modelo | Edital anotado (RF-151) e BCF (RF-170) |
| FB-21 | T1 0:53:34–0:57:43 | O objetivo é chegar a um consenso entre as partes. Apresentar o problema e defender a simplificação adotada | Registro de decisões (RF-150). Seção 15 |
| FB-22 | T2 0:01:20–0:01:44 | O IDS saiu em IFC4X3 ADD2. Dá para escolher a versão? | RF-131 |
| FB-23 | T2 0:05:09–0:05:20; 0:10:43–0:11:02 | Falta o IDM. Ele está "espalhado". Citar a ISO 29481 de forma explícita e usá-la como contexto | M7 (RF-110 a RF-112) |
| FB-24 | T2 0:07:15–0:08:11 | O ponto fraco hoje é o uso e a nomenclatura. Se usar o termo, explique | Seção 4 |
| FB-25 | T2 0:08:42–0:10:30 | Hoje o EIR cobre o projeto inteiro. No futuro, haverá vários EIR por entrega no mesmo projeto. Deve dar para validar só uma parte ou o todo. Em licitação, a questão já está respondida | RF-130 |
| FB-26 | T2 0:11:15–0:14:09 | Usar o sistema de classificação brasileiro (ABNT NBR 15965). A ISO 19650 tem adoção nacional. O nível de informação necessária vem de uma norma CEN. O EIR de referência da banca foi feito por pessoas, sem IA, e serve de contexto | RF-140 a RF-143 |
| FB-27 | T2 0:14:09–0:15:42 | Comparar o custo da IA com as horas de trabalho humano. O time citou cerca de 39 mil tokens num documento | RF-195 a RF-197 |
| FB-28 | T2 0:15:49–0:16:03 | A ferramenta também será usada por advogados | RF-210 |
| FB-29 | T2 0:16:20–0:16:38 | A ferramenta tem potencial comercial | Roadmap (seção 16) |
| FB-30 | T2 0:12:23–0:12:47 | A plataforma fica no servidor do Construtivo, com URL para a banca, até quarta-feira | RNF-18 |

---

## 4. Posicionamento, escopo e nomenclatura

### 4.1 Frase de posicionamento

> O EditalCheck transforma as exigências de um edital, escritas em linguagem natural, num **contrato de dados** operacional (EIR e IDS). Em seguida, ele verifica o modelo IFC contra esse contrato e o edital contra boas práticas. O objetivo é chegar a um **consenso** entre contratante e contratado antes que o problema chegue à obra.

Use esta frase na tela inicial, no relatório, no README e no pitch.

### 4.2 Escopo declarado

| Item | Definição |
|---|---|
| Fase | Contratação (licitação) e entregas do contrato |
| Unidade de verificação | O contrato inteiro **ou** um marco de entrega (RF-130) |
| Quem emite o EIR | O contratante (parte que contrata) |
| Quem responde ao EIR | O contratado (projetista ou contratado líder) |
| O que **não** é | Verificação de projeto em fase interna, sem edital, ou de operação do ativo (AIR) |

### 4.3 Nomenclatura

A banca apontou a nomenclatura como o ponto fraco (FB-24). Regras:

1. **Decisão do time (D7):** o termo da interface passa a ser **"requisitos de informação (RI)"**, mais genérico que EIR.
2. Texto padrão: "**Requisitos de informação (RI)**: o que o contratante exige que o modelo contenha em cada entrega deste contrato. Aqui eles são extraídos do edital e das lições aprendidas."
3. O IDS informa o escopo no campo `milestone`: "Contrato inteiro" ou o nome do marco.
4. Não chame as três análises de "validadores" (FB-17). Use "Análise A — Conformidade", "Análise B — Qualidade do edital" e "Análise C — Cobertura".
5. No código, a entidade continua se chamando `Eir`, e as rotas `/eir` seguem aceitas como alias de `/ri`. A troca interna fica para depois do hackathon, para não arriscar a demo.

### 4.4 Glossário (exibido na interface e no relatório)

| Termo | Definição curta | Referência |
|---|---|---|
| **OIR / PIR / AIR / EIR** | Requisitos de informação da organização, do projeto, do ativo e para troca | ISO 19650-1:2018; no Brasil, ABNT NBR ISO 19650-1:2022 (errata de 2024) |
| **Marco de entrega** | Momento em que o contratado entrega informação ao contratante | ISO 19650-2:2018; ABNT NBR ISO 19650-2:2022 |
| **IDM** | Método para descrever processos, atores e trocas de informação | ISO 29481-1:2025 (3ª edição, metodologia e formato) |
| **IDS** | Arquivo que define, de forma verificável por máquina, a informação exigida no modelo | buildingSMART, IDS 1.0 |
| **IFC** | Formato aberto do modelo BIM | ISO 16739 [confirmar versão] |
| **BCF** | Formato aberto para comunicar problemas ligados a elementos do modelo | buildingSMART, BCF 2.1 |
| **bSDD** | Dicionário de dados aberto da buildingSMART | buildingSMART |
| **Pset** | Conjunto de propriedades de um elemento IFC | IFC |
| **Nível de informação necessária** | Quanta informação cada entrega exige | ISO 7817-1:2024, que substituiu a EN 17412-1:2020 (CEN) |
| **Sistema de classificação** | Tabelas para classificar elementos e informações da construção | ABNT NBR 15965, série em partes (ex.: Parte 1:2011, Parte 7:2015); a lista completa de partes vigentes não foi confirmada |

> Não reproduza texto de norma ISO, CEN ou ABNT no repositório. As definições acima são do time. As versões foram conferidas em catálogos públicos (ISO, CBIC, distribuidores) em 22/11/2026; confirme a vigência no catálogo oficial antes de citar em contrato.

### 4.5 IDM explícito (FB-23)

O fluxo do EditalCheck já segue a lógica do IDM, mas isso não está declarado. Torne explícito:

- **Mapa de processo** (figura em `docs/idm.md` e no slide): atores, atividades e trocas.

```
Contratante ──(edital + lições aprendidas)──► EditalCheck ──(EIR proposto)──► Revisor humano
     ▲                                                                          │ aprova
     │ apontamentos do edital                                                   ▼
     └──────────── relatório / edital anotado ◄── Análises A, B, C ◄── IDS (contrato de dados)
                                                     ▲
Contratado ──(modelo IFC por marco)──────────────────┘ ──► BCF ──► Contratado corrige
```

- **Requisito de troca (ER):** cada EIR por marco é um requisito de troca do mapa. O IDS é a forma verificável dele.
- **Rastreio:** cada especificação do IDS cita o marco e o ID do requisito de troca na descrição (RF-111).

---

## 5. Requisitos funcionais novos e alterados

A numeração continua a da v1.0. Os novos requisitos começam em RF-100.

### 5.1 Tratamento de dados e LGPD (M1)

**Situação atual (verificada no código):**
- `FsProjectRepository` grava `edital.pdf`, `modelo.ifc`, `projeto.json`, `relatorio.json`, `relatorio.html` e `resultado.bcf` em `var/`.
- `StructuredLlm` grava as respostas do LLM em `.cache/`. Essas respostas contêm trechos do edital.
- O README do deploy diz que `var/` e `.cache/` "sobrevivem a novos builds".

**Conflito:** à banca, o time disse que nada é persistido (T1 0:03:23–0:03:43 e 0:16:35–0:18:40). Corrija o código **ou** a fala antes do pitch. Esta especificação adota a correção do código.

| ID | Requisito | Prioridade |
|---|---|---|
| RF-090 | Criar o modo de dados `efemero` e torná-lo o padrão no deploy (`EDITALCHECK_MODO_DADOS=efemero`). O modo `persistente` continua para desenvolvimento e demo local | Must |
| RF-091 | No modo efêmero, guardar projeto, verificação e relatório só em memória, com prazo de expiração (TTL, ver D9) | Must |
| RF-092 | No modo efêmero, não gravar PDF nem IFC em disco persistente. Se uma biblioteca exigir caminho de arquivo, usar diretório temporário em memória (`/dev/shm`) e apagá-lo no `finally` | Must |
| RF-093 | No modo efêmero, desligar o cache de respostas do LLM em disco. O cache do bSDD pode continuar, porque guarda só dados públicos | Must |
| RF-094 | Botão "Encerrar e apagar dados" e rota `DELETE /api/projetos/{id}`. A tela confirma a remoção | Must |
| RF-095 | Antes da primeira chamada à IA, mostrar aviso: "Trechos do edital e das lições aprendidas serão enviados ao provedor de IA (Google Gemini)". O usuário confirma uma vez por sessão | Must |
| RF-096 | Registrar um log de auditoria **sem conteúdo**: data e hora, ID de sessão aleatório, etapa, modelo, tokens de entrada e saída, duração e tamanho dos arquivos | Should |
| RF-097 | No modo efêmero, o visualizador carrega o IFC do arquivo que já está no navegador. Não há download de volta pelo servidor | Should |
| RF-098 | Exibir faixa fixa: "Ambiente de demonstração. Disponível até DD/MM/AAAA. Não envie dados de clientes" (data por variável de ambiente) | Must |

**Retenção pelo provedor de IA:** o time disse que a API paga não usa os dados para treino e que o provedor guarda os dados por 24 a 48 horas. Isso **não** foi conferido. Confirme nos termos vigentes da API Gemini antes de repetir no pitch (D12). Quem decide sobre o tratamento de dados pessoais é o jurídico do Construtivo, conforme a política SI-Política_Geral_de_Seguranca_da_Informacao.

### 5.2 Origem da inconsistência e perfil de uso (M2, M15)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-120 | Todo apontamento tem `origem`: **EDITAL** ou **MODELO**. A origem é derivada do tipo, por regra determinística (tabela abaixo) | Must |
| RF-120a | Na lista, no detalhe, no relatório HTML e no 3D, a origem aparece como selo com cor e ícone. Edital: cor A. Modelo: cor B. A cor nunca é o único sinal (acessibilidade): o selo também traz o texto | Must |
| RF-120b | O relatório HTML ganha duas seções: "**Corrigir no edital** — contratante age" e "**Corrigir no modelo** — contratado age". O cabeçalho mostra a contagem de cada uma | Must |
| RF-121 | Seletor "Estou usando como": contratante, contratado líder, contratado ou verificador independente. O perfil muda a ordem das seções, o filtro inicial e o texto de "quem age". Não muda o conteúdo | Should |

| Tipo de apontamento | Origem | Quem age |
|---|---|---|
| `NAO_CONFORMIDADE` | MODELO | Contratado |
| `QUALIDADE_MODELO` | MODELO | Contratado |
| `AMBIGUIDADE` | EDITAL | Contratante |
| `ITEM_AUSENTE` | EDITAL | Contratante |
| `CONTRADICAO` | EDITAL | Contratante |
| `NAO_VERIFICAVEL` | EDITAL | Contratante |
| `LACUNA_COBERTURA` | EDITAL | Contratante |
| `LICAO_NAO_EXPLICITA` (novo) | EDITAL | Contratante |
| `DUPLICIDADE` (novo) | EDITAL | Contratante |

> Rótulos dos destinatários na interface: "Contratante (edital)" e "Contratado / projetista (modelo)". Os valores do enum continuam `contratante` e `projetista`, para não quebrar a API.

### 5.3 Lições aprendidas e salvaguardas contra abuso (M4, M5)

**Caso de referência (FB-18):** o edital pedia iluminação ou ventilação natural "em todas as salas, quando possível". A contratada instalou essas aberturas em salas de baterias, onde não deviam existir. A lição aprendida diz: "sala de baterias não tem abertura para o exterior". A ferramenta deve:
1. apontar ao contratante que o edital não explicita essa exceção; e
2. quando possível, verificar o modelo.

#### 5.3.1 Entrada

| ID | Requisito | Prioridade |
|---|---|---|
| RF-100 | Aceitar um documento de lições aprendidas como quarta entrada, opcional, no upload | Must |
| RF-101 | **Decisão do time:** o campo "Informações adicionais" virou "Lições aprendidas" e aceita **TXT e PDF** (também `.md`). Sem LLM, cada item com regra (marcador, numeração ou parágrafo com "deve", "não pode" etc.) vira uma lição | Must |
| RF-102 | Com LLM, a IA extrai as lições (título, regra, ambiente afetado, classe IFC). Cada lição cita um trecho literal do documento, conferido pela S2. Se nada conferir, o sistema usa as regras | Must |
| RF-103 | Mostrar as lições na revisão do EIR, em bloco próprio, com origem e autor | Must |

#### 5.3.2 Processamento

| ID | Requisito | Prioridade |
|---|---|---|
| RF-104 | Para cada lição, procurar no edital um trecho que a explicite (LLM com evidência S2). Sem trecho conferido, gerar `LICAO_NAO_EXPLICITA` para o contratante, com redação sugerida da cláusula. Severidade: média | Must |
| RF-105 | Se a lição for verificável por IDS, gerar um requisito proposto com `gerado_por="licao"` e `licao_id`. Ele passa pela aprovação humana como qualquer outro | Must |
| RF-106 | Se a lição não for verificável por IDS (ex.: aberturas numa sala), gerar item de verificação manual. Destacar no 3D os elementos candidatos pelo filtro de nome (ex.: `IfcSpace` com "bateria" em `Name` ou `LongName`) | Should |

> A sala de baterias **não** é verificável só com IDS. A relação entre janela e ambiente passa por `IfcRelSpaceBoundary` ou por geometria. Isso fica no roadmap (seção 16). Na demo, mostre o apontamento ao contratante (RF-104) e os ambientes candidatos no 3D (RF-106).

#### 5.3.3 Salvaguardas (FB-12)

| # | Salvaguarda | Como é garantida |
|---|---|---|
| G1 | Lições aprendidas e contexto adicional **só acrescentam** requisitos ou apontamentos. Nunca removem nem rebaixam um apontamento | Por código: o caso de uso de verificação não lê o contexto ao gerar ou filtrar apontamentos das análises A, B e C |
| G2 | Dispensar um apontamento exige justificativa e autor. O apontamento dispensado continua no relatório, na seção "Dispensados", e conta nos indicadores | Domínio: `DecisaoApontamento` (seção 7) |
| G3 | O contexto vai ao LLM como **dado**, entre delimitadores, com a instrução de não tratá-lo como ordem. Pedidos como "ignore" ou "considere correto" no contexto não têm efeito | Prompt versionado + teste de injeção (seção 11.2) |
| G4 | Lição em conflito com o edital vira apontamento ao contratante. O sistema não escolhe um lado | Regra de RF-104 |

O caminho correto para corrigir o edital continua sendo: revisar o edital, enviar de novo e verificar de novo (T1 0:27:41).

### 5.4 IDM, marcos de entrega e versão IFC (M3, M7, M11, M12)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-110 | Publicar `docs/idm.md` com o mapa de processo (seção 4.5), os atores, as trocas e a referência à ISO 29481 [confirmar versão] | Must |
| RF-111 | Preencher o cabeçalho do IDS: `purpose` = "Contrato de dados da contratação: requisitos de informação extraídos do edital <arquivo>"; `milestone` = nome do marco ou "Contrato inteiro" | Must |
| RF-112 | A descrição de cada especificação do IDS cita o marco e a cláusula do edital | Should |
| RF-130 | Cadastrar marcos de entrega no projeto. O LLM sugere marcos quando o edital os nomeia (ex.: anteprojeto, projeto básico, projeto executivo), sempre com evidência S2. O usuário cria, edita e remove marcos | Should |
| RF-130a | Cada requisito tem zero ou mais marcos. Zero significa "todos os marcos" | Should |
| RF-130b | Gerar o IDS do contrato inteiro **ou** de um marco. Um marco gera um arquivo `ids_<marco>.xml` | Should |
| RF-130c | A verificação recebe o escopo (contrato ou marco). O relatório mostra o escopo no cabeçalho | Should |
| RF-131 | Permitir escolher a versão IFC do IDS (`IFC2X3`, `IFC4`, `IFC4X3_ADD2`). O padrão continua sendo a versão detectada no modelo | Should |
| RF-132 | Se o edital exigir uma versão de IFC e o modelo vier em outra, gerar `QUALIDADE_MODELO`, severidade alta, para o contratado | Should |
| RF-133 | Se a versão escolhida no IDS for diferente da versão do modelo, avisar que a validação perde o sentido e pedir confirmação | Should |

### 5.5 Contexto, exemplos e classificação brasileira (M13)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-140 | Incluir 1 ou 2 exemplos curtos (few-shot) nos prompts de tópicos e de extração, no estilo de edital brasileiro. Os exemplos são do time e ficam versionados em `backend/prompts/` | Should |
| RF-141 | Campo "Informações adicionais" no upload: texto livre do usuário com o contexto da empresa, limitado a 4.000 caracteres. Aplicar G1 e G3. O relatório mostra o contexto usado | Should |
| RF-142 | Pacotes de contexto em `backend/resources/contexto/`. Cada pacote declara nome, fonte, licença e trechos. O sistema envia ao LLM só os trechos relevantes ao tópico, por pontuação de palavras-chave, dentro de um orçamento de tokens (RNF-16) | Could |
| RF-143 | Faceta de classificação com o sistema ABNT NBR 15965 no EIR e no IDS. Buscar a classe no bSDD se o dicionário estiver publicado lá [confirmar, D13]. Se não estiver, marcar a origem como `customizado` | Could |

**Pacotes previstos:**

| Pacote | Conteúdo | Condição |
|---|---|---|
| EIR de referência da banca | Modelo de EIR baseado na ISO 19650, feito por pessoas | Só com autorização escrita do autor e licença registrada (D8) |
| Classificação NBR 15965 | Códigos e títulos das tabelas | Só se a licença da ABNT permitir; senão, usar o bSDD |
| Conceitos IDM | Texto autoral do time sobre atores, trocas e marcos | Sem reproduzir a norma |
| Contexto da empresa | Texto do RF-141 | Efêmero; não versionado |

### 5.6 Decisões, edital anotado e esclarecimentos (M10)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-150 | Cada apontamento recebe uma decisão: `aceito`, `rejeitado`, `em_discussao` ou `dispensado`. A decisão tem comentário, autor (texto livre) e data. `rejeitado` e `dispensado` exigem comentário (G2) | Should |
| RF-151 | Gerar `edital_anotado.pdf`: cópia do edital com um destaque e uma nota em cada trecho citado por apontamento de origem EDITAL. A nota traz ID, tipo, problema, redação sugerida e decisão. Usar `Page.search_for` e `Page.add_highlight_annot` do PyMuPDF. Se o trecho não for achado, pôr a nota no topo da página | Should |
| RF-152 | Gerar `esclarecimentos.xlsx`, a matriz de esclarecimentos: item, página, trecho, problema, pergunta sugerida, redação sugerida, decisão e resposta | Should |
| RF-153 | A pergunta sugerida serve de base para um pedido de esclarecimento ao edital. O relatório avisa: "Minuta gerada por IA. Valide com o jurídico antes de protocolar" | Should |

> O pedido de esclarecimento e a impugnação de edital têm prazos e forma definidos na Lei 14.133/2021 (art. 164, [confirmar redação vigente]). A decisão de protocolar é do jurídico, não da ferramenta.

### 5.7 Volume e qualidade dos apontamentos (M9)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-160 | Agrupar ambiguidades pelo par (termo, tópico). Um apontamento traz várias evidências | Should |
| RF-161 | Tirar os requisitos não verificáveis por IDS da lista de apontamentos. Eles vão para a aba "Verificação manual", com contagem própria | Should |
| RF-162 | Por padrão, a lista mostra severidade alta e média. A baixa fica recolhida, com contagem visível ("+ N de severidade baixa") | Should |
| RF-163 | Recomendações por LLM só para severidade alta e média. A baixa usa o texto padrão por tipo | Should |
| RF-164 | Medir, na demo, o total de apontamentos visíveis antes e depois desta seção. Registrar no `JOURNAL.md` | Should |

### 5.8 BCF (M6)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-170 | O comentário de cada viewpoint por elemento traz: nome, classe, GlobalId, pavimento, coordenada XYZ do centro da caixa envolvente (m, sistema do projeto), caixa mínima e máxima, propriedade exigida, valor encontrado, cláusula e página do edital e "como agir" | Must |
| RF-171 | A descrição do tópico resume o apontamento e lista os GlobalIds | Must |
| RF-172 | Os rótulos (`Labels`) do tópico trazem a origem ("Modelo") e o tipo | Should |
| RF-173 | Se o IFC tiver `IfcMapConversion`, incluir também a coordenada no sistema georreferenciado | Could |
| RF-174 | Snapshot PNG por viewpoint, capturado pelo visualizador no navegador e enviado ao backend para entrar no BCF | Could |
| RF-175 | Teste: abrir o BCF gerado numa ferramenta BIM que leia BCF 2.1 e conferir câmera, seleção e comentário | Must |

> O BCF 2.1 não tem um campo de coordenada no tópico. A coordenada vai no texto do comentário e na câmera do viewpoint. Isso atende ao pedido sem sair do padrão.

### 5.9 Visualizador 3D (M14)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-180 | Ao selecionar elemento ou apontamento, enquadrar a caixa envolvente com margem e deixar os demais elementos translúcidos | Should |
| RF-181 | Botão "Isolar": esconde tudo que não pertence ao apontamento. Botão "Mostrar tudo" desfaz | Should |
| RF-182 | O painel de detalhe mostra a coordenada XYZ e as propriedades do elemento, iguais às do BCF (RF-170) | Should |

### 5.10 Comparação entre verificações (M17)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-185 | O usuário envia o `relatorio.json` de uma verificação anterior. O sistema compara com a atual e classifica cada apontamento como resolvido, novo ou persistente | Could |
| RF-186 | A chave de comparação é determinística: tipo + requisito (ou cláusula) + classe IFC. Para não conformidades, comparar também o conjunto de GlobalIds e contar os elementos corrigidos | Could |
| RF-187 | O histórico fica com o usuário (arquivo baixado), não no servidor. Isso mantém o modo efêmero | Could |

> Isto compara **apontamentos** entre revisões. A comparação **geométrica** entre revisões do IFC (ex.: o tubo mudou de posição) fica no roadmap.

### 5.11 Desempenho (M19)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-190 | Extrair requisitos por tópico em paralelo, limitado por `LLM_PARALELISMO` | Could |
| RF-191 | Agrupar recomendações em lotes (ex.: 5 apontamentos por chamada), com saída validada por schema | Could |
| RF-192 | Mostrar o progresso por tópico com estimativa de tempo restante | Could |

### 5.12 Consumo de IA e comparativo de custo (M8)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-195 | Registrar por etapa: chamadas, tokens de entrada, tokens de saída, chamadas servidas pelo cache e duração. Usar os metadados de uso devolvidos pela API do Gemini | Must |
| RF-196 | Calcular o custo estimado com preços **configurados** (`LLM_PRECO_ENTRADA_USD_MTOK`, `LLM_PRECO_SAIDA_USD_MTOK`, `LLM_PRECO_FONTE_DATA`). Sem preço configurado, mostrar só os tokens. Nunca usar preço fixo no código | Must |
| RF-197 | Painel "Custo e tempo" no relatório: tokens, custo estimado, tempo do pipeline e tempo manual **medido** pelo time, com a fonte e o tamanho da amostra | Must |

> O tempo manual não pode ser estimado no código. A pessoa de BIM cronometra a tarefa em pelo menos um tópico, e o resultado vai para `backend/resources/referencia_tempo_manual.yaml`, com data, pessoa (papel, não nome) e método. A banca sugeriu "meses e semanas" só para entender um termo de referência (T2 0:15:32). Isso é opinião, não medição.

### 5.13 Modo "Revisar edital" sem IFC (M16)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-198 | O IFC passa a ser opcional no upload. Sem IFC, o sistema roda tópicos, EIR, análise B e lições aprendidas | Should |
| RF-199 | Sem IFC, a classe IFC do requisito é validada contra o schema escolhido pelo usuário (RF-131). As análises A e C aparecem como "não executadas: sem modelo" | Should |

### 5.14 Texto repetido no edital (M18)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-200 | Detectar sentenças muito parecidas em cláusulas diferentes, por similaridade de n-gramas de palavras (determinística; limite configurável, ponto de partida 0,8) | Could |
| RF-201 | Sentenças iguais geram `DUPLICIDADE`, severidade baixa: "texto repetido; risco de divergência em revisões futuras" | Could |
| RF-202 | Sentenças parecidas com valores diferentes viram candidatas a `CONTRADICAO` e seguem para a confirmação do LLM já existente | Could |

### 5.15 Linguagem acessível (M20)

| ID | Requisito | Prioridade |
|---|---|---|
| RF-210 | Glossário (seção 4.4) acessível por dica (tooltip) em toda sigla da interface e como anexo do relatório | Could |
| RF-211 | A seção "Corrigir no edital" usa linguagem sem jargão BIM. Siglas aparecem sempre com a explicação ao lado | Could |

---

## 6. Requisitos não funcionais novos e alterados

| ID | Requisito |
|---|---|
| RNF-06 (alterado) | **Segurança:** além do que já vale, o modo efêmero é o padrão no deploy, e os logs não trazem conteúdo de documento |
| RNF-11 | **Privacidade:** no modo efêmero, nenhum arquivo do usuário nem resposta do LLM é gravado em disco persistente. Os dados expiram pelo TTL e são apagados quando o processo encerra |
| RNF-12 | **Auditoria sem conteúdo:** o log de auditoria guarda só metadados (RF-096) |
| RNF-13 | **Transparência da IA:** o usuário sabe, antes do envio, que dados vão ao provedor de IA (RF-095) |
| RNF-14 | **Custo mensurável:** todo pipeline registra tokens e duração por etapa (RF-195) |
| RNF-15 | **Acessibilidade:** origem e severidade nunca são indicadas só por cor |
| RNF-16 | **Contexto limitado:** cada chamada ao LLM tem orçamento de tokens de contexto adicional (ponto de partida: 2.000 tokens). O excedente é cortado pela menor pontuação |
| RNF-17 | **Licença de conteúdo:** nenhum texto de norma ISO, CEN ou ABNT, nem material da banca, entra no repositório sem licença registrada |
| RNF-18 | **Ambiente de demonstração:** a data de desligamento fica numa variável (`EDITALCHECK_DISPONIVEL_ATE`) e aparece na interface |
| RNF-19 | **Escala:** o modo efêmero com memória local exige uma única réplica, ou sessão fixa no proxy. Registrar essa limitação no README |

---

## 7. Mudanças no modelo de domínio

Todas as mudanças ficam em `domain/models.py`. O domínio continua sem FastAPI, IfcOpenShell e SDK de LLM.

```python
from dataclasses import dataclass
from enum import StrEnum


class FonteEvidencia(StrEnum):
    EDITAL = "edital"
    LICOES = "licoes"


@dataclass(frozen=True)
class Evidencia:
    pagina: int
    trecho: str
    fonte: FonteEvidencia = FonteEvidencia.EDITAL  # novo; padrão mantém compatibilidade


class OrigemInconsistencia(StrEnum):
    EDITAL = "edital"
    MODELO = "modelo"


class TipoApontamento(StrEnum):
    # ... tipos atuais ...
    LICAO_NAO_EXPLICITA = "licao_nao_explicita"
    DUPLICIDADE = "duplicidade"


class StatusDecisao(StrEnum):
    PENDENTE = "pendente"
    ACEITO = "aceito"
    REJEITADO = "rejeitado"
    EM_DISCUSSAO = "em_discussao"
    DISPENSADO = "dispensado"


@dataclass(frozen=True)
class DecisaoApontamento:
    apontamento_id: str
    status: StatusDecisao
    comentario: str
    autor: str
    data: str  # ISO 8601

    def __post_init__(self) -> None:
        exige_comentario = self.status in (StatusDecisao.REJEITADO, StatusDecisao.DISPENSADO)
        if exige_comentario and not self.comentario.strip():
            raise ValueError("Rejeitar ou dispensar um apontamento exige justificativa.")


@dataclass(frozen=True)
class LicaoAprendida:
    id: str  # LIC-001
    titulo: str
    regra: str
    evidencia: Evidencia  # fonte=LICOES
    contexto: str = ""
    ifc_class: str | None = None
    filtro_nome: str | None = None  # ex.: "bateria", aplicado a Name/LongName
    pset: str | None = None
    propriedade: str | None = None
    restricao: "Restricao | None" = None
    cardinalidade: "Cardinalidade" = Cardinalidade.OBRIGATORIA
    origem: str = ""  # obra ou projeto de onde veio
    autor: str | None = None
    data: str | None = None


@dataclass(frozen=True)
class MarcoEntrega:
    id: str  # MAR-01
    nome: str  # ex.: "Projeto básico"
    descricao: str = ""
    evidencia: Evidencia | None = None


@dataclass(frozen=True)
class EscopoVerificacao:
    marco_id: str | None = None  # None = contrato inteiro
    versao_ifc_ids: str | None = None  # None = versão detectada no modelo


@dataclass(frozen=True)
class ConsumoEtapa:
    etapa: str
    chamadas: int
    chamadas_cache: int
    tokens_entrada: int
    tokens_saida: int
    duracao_s: float
```

**Campos novos em entidades existentes:**

| Entidade | Campo | Tipo | Observação |
|---|---|---|---|
| `Requisito` | `marcos` | `tuple[str, ...] = ()` | Vazio = todos os marcos |
| `Requisito` | `licao_id` | `str \| None = None` | Preenchido quando `gerado_por="licao"` |
| `Apontamento` | `origem` | `OrigemInconsistencia` | Derivado do tipo por `domain/severity.py::origem(tipo)` |
| `Apontamento` | `evidencias_edital` | (mantido) | Pode conter evidências com `fonte=LICOES` |
| `Projeto` | `licoes`, `marcos`, `contexto_adicional` | tuplas e `str` | `contexto_adicional` nunca é usado para filtrar apontamentos (G1) |
| `Projeto` | `modelo` | `ModeloResumo \| None` | `None` no modo "revisar edital" (RF-198) |
| `Relatorio` | `escopo`, `decisoes`, `consumo`, `contexto_usado` | novos | `consumo` alimenta o painel de custo |
| `Indicadores` | `apontamentos_por_origem`, `dispensados`, `verificacao_manual` | novos | Os dispensados continuam no total |

**Regras puras novas (com testes de domínio):**
- `severity.origem(tipo) -> OrigemInconsistencia`: tabela da seção 5.2.
- `findings.de_licoes(licoes, evidencias_encontradas) -> list[Apontamento]`.
- `findings.agrupar_ambiguidades(apontamentos) -> list[Apontamento]` (RF-160).
- `comparison.comparar(anterior, atual) -> ComparacaoVerificacoes` (RF-185, novo módulo `domain/comparison.py`).
- `duplicates.sentencas_parecidas(topicos, limite) -> list[ParSentencas]` (RF-200, novo módulo `domain/duplicates.py`).

---

## 8. Portas e adaptadores (arquitetura hexagonal)

### 8.1 Portas novas ou alteradas (`application/ports.py`)

```python
from typing import Protocol


class LessonsReader(Protocol):
    def read(self, conteudo: bytes, nome_arquivo: str) -> list[LicaoAprendida]: ...


class LessonChecker(Protocol):
    """Procura no edital um trecho que explicite a lição (evidência conferida por S2)."""

    def find_evidence(self, licao: LicaoAprendida, edital: Edital) -> Evidencia | None: ...


class EditalAnnotator(Protocol):
    def annotate(self, edital_pdf: bytes, apontamentos: list[Apontamento]) -> bytes: ...


class ClarificationWriter(Protocol):
    def write(self, apontamentos: list[Apontamento], decisoes: list[DecisaoApontamento]) -> bytes: ...


class AuditLog(Protocol):
    def record(self, evento: "EventoAuditoria") -> None: ...


class UsageMeter(Protocol):
    def snapshot(self) -> list[ConsumoEtapa]: ...


class ProjectRepository(Protocol):  # alterada
    def save(self, projeto: Projeto) -> None: ...
    def get(self, projeto_id: str) -> Projeto | None: ...
    def delete(self, projeto_id: str) -> None: ...  # nova (RF-094)
```

`IdsBuilder.build` passa a receber `EscopoVerificacao` e o marco. `BcfWriter` passa a receber as propriedades e a evidência de cada falha.

### 8.2 Adaptadores

| Adaptador | Arquivo | Observação |
|---|---|---|
| `MemoryProjectRepository` | `adapters/storage/memory_repository.py` | Dicionário com trava, TTL, limite de projetos e limpeza periódica. Guarda os bytes do PDF e o `ifcopenshell.file` carregado |
| Arquivos temporários em memória | `adapters/storage/tmp_files.py` | `tempfile.TemporaryDirectory(dir="/dev/shm")` com remoção garantida. Usado só quando a biblioteca exige caminho |
| `XlsxLessonsReader` | `adapters/lessons/xlsx_reader.py` | openpyxl; valida colunas obrigatórias |
| `LlmLessonsReader` | `adapters/llm/adapters.py` | Para PDF e DOCX; prompt `licoes.md`; S1 e S2 |
| `LlmLessonChecker` | `adapters/llm/adapters.py` | Prompt `licao_no_edital.md`; S2 obrigatória |
| `PyMuPdfAnnotator` | `adapters/pdf/annotator.py` | `pymupdf.open(stream=..., filetype="pdf")`, `search_for`, `add_highlight_annot`. Saída em bytes |
| `XlsxClarificationWriter` | `adapters/export/xlsx_writer.py` | Nova aba ou novo arquivo |
| `JsonLinesAuditLog` | `adapters/audit/jsonl_log.py` | Só metadados. Arquivo fora do Git |
| `GeminiUsageMeter` | `adapters/llm/gemini_client.py` | Lê os metadados de uso da resposta. Conferir o nome do campo na documentação do `google-genai` instalado |
| `StructuredLlm` (alterado) | `adapters/llm/structured.py` | Cache em disco só no modo persistente (RF-093) |
| `BcfWriter` (alterado) | `adapters/bcf/bcf_writer.py` | Comentário com XYZ e propriedades (RF-170). Opcional: `VisualizationInfoBitmap` para snapshots (RF-174) |

### 8.3 Composição (`bootstrap.py`)

- `EDITALCHECK_MODO_DADOS=efemero` liga `MemoryProjectRepository` e desliga o cache do LLM.
- `EDITALCHECK_MODO_DADOS=persistente` mantém `FsProjectRepository` e o cache atual.
- No `docker-compose.yml`, defina `efemero`. Remova o volume de `var/` do serviço ou deixe-o só para o log de auditoria.

> **Regra da v1.0 mantida:** antes de usar qualquer API de biblioteca, confira a documentação oficial da versão instalada. Já conferido neste ambiente: `ifctester.ids.Ids` aceita `purpose` e `milestone`; `pymupdf.Page` tem `search_for` e `add_highlight_annot`; `ifcopenshell.file.from_string` existe (IfcOpenShell 0.9.0.post1, PyMuPDF 2.1).

---

## 9. API HTTP

### 9.1 Rotas novas

| Método | Rota | Descrição |
|---|---|---|
| `DELETE` | `/api/projetos/{id}` | Apaga o projeto e suas verificações (RF-094) |
| `POST` | `/api/projetos/{id}/licoes` | Envia o documento de lições aprendidas |
| `GET` | `/api/projetos/{id}/licoes` | Lista as lições lidas |
| `GET` | `/api/projetos/{id}/marcos` | Lista os marcos |
| `PUT` | `/api/projetos/{id}/marcos` | Substitui a lista de marcos |
| `PATCH` | `/api/verificacoes/{vid}/apontamentos/{apt_id}` | Registra a decisão (RF-150) |
| `GET` | `/api/verificacoes/{vid}/edital-anotado.pdf` | Edital anotado (RF-151) |
| `GET` | `/api/verificacoes/{vid}/esclarecimentos.xlsx` | Matriz de esclarecimentos (RF-152) |
| `POST` | `/api/verificacoes/{vid}/comparacao` | Recebe o `relatorio.json` anterior e devolve a comparação (RF-185) |
| `GET` | `/api/verificacoes/{vid}/consumo` | Tokens, duração e custo estimado por etapa (RF-195) |

### 9.2 Rotas alteradas

| Rota | Mudança |
|---|---|
| `POST /api/projetos` | `modelo` opcional (RF-198); novos campos opcionais `licoes` (arquivo) e `contexto_adicional` (texto) |
| `POST /api/projetos/{id}/ids` | Corpo: `{ "marco_id": str \| null, "versao_ifc": str \| null }` |
| `POST /api/projetos/{id}/verificacoes` | Corpo: o mesmo escopo do IDS |
| `GET /api/config` | Novos campos: `modo_dados`, `disponivel_ate`, `ttl_min` e `aviso_ia` |
| `GET /api/verificacoes/{vid}/relatorio` | Novos campos: `origem` por apontamento, `decisoes`, `escopo`, `consumo` e `contexto_usado` |

Atualize `docs/api.md` junto com o código.

---

## 10. Interface e relatório

### 10.1 Assistente

```
[1 Upload] → [2 Tópicos] → [3 Revisão do EIR] → [4 IDS] → [5 Verificação] → [6 Resultados]
 PDF          marca          + lições           contrato   escopo:           por origem,
 + IFC (opc.) tópicos        + marcos           ou marco   contrato/marco    decisões, custo
 + lições                    + glossário        versão IFC
 + contexto
```

| Tela | Mudanças |
|---|---|
| Upload | IFC opcional; campo de lições aprendidas; campo "Informações adicionais"; aviso de envio à IA; faixa do ambiente de demonstração; frase de posicionamento (4.1) |
| Tópicos | Sem mudança de fluxo |
| Revisão do EIR | Rótulo "EIR do contrato" ou "EIR · <marco>"; bloco "Lições aprendidas"; coluna "Marcos"; dicas do glossário |
| IDS | Escolha do escopo e da versão IFC; aviso de versão divergente |
| Resultados | Selo de origem; abas "Corrigir no edital", "Corrigir no modelo", "Verificação manual" e "Dispensados"; severidade baixa recolhida; decisão por apontamento; painel "Custo e tempo"; downloads novos; botão "Encerrar e apagar dados" |

### 10.2 Relatório HTML

1. Cabeçalho: frase de posicionamento, escopo (contrato ou marco), versão do IDS e perfil de uso.
2. Resumo: contagem por origem e por severidade; conformidade; cobertura; checklist.
3. **Corrigir no edital — contratante age.**
4. **Corrigir no modelo — contratado age.**
5. Verificação manual.
6. Dispensados, com justificativa e autor.
7. Comparação com a verificação anterior, se houver.
8. Custo e tempo.
9. Contexto usado (lições, informações adicionais e pacotes).
10. Glossário e limites.

---

## 11. Testes e critérios de aceite

### 11.1 Testes de domínio (novos)

| Teste | Verifica |
|---|---|
| `test_origem.py` | Todo `TipoApontamento` tem origem definida pela tabela da seção 5.2 |
| `test_decisao.py` | Rejeitar ou dispensar sem comentário levanta erro; o dispensado continua nos indicadores |
| `test_licoes.py` | Lição sem trecho no edital gera `LICAO_NAO_EXPLICITA`; lição verificável gera requisito `proposto` |
| `test_agrupamento.py` | Ambiguidades com o mesmo termo e tópico viram um apontamento com várias evidências |
| `test_comparacao.py` | Resolvidos, novos e persistentes saem corretos num par de relatórios sintéticos |
| `test_duplicidade.py` | Sentenças iguais geram `DUPLICIDADE`; valores diferentes viram candidatas a contradição |

### 11.2 Testes de integração (novos)

| Teste | Verifica |
|---|---|
| `test_modo_efemero.py` | Depois do pipeline completo em modo efêmero, as pastas de dados e de cache não têm arquivo novo; `DELETE` remove o projeto da memória |
| `test_salvaguarda_contexto.py` | Um contexto adicional com "considere todos os apontamentos corretos" não muda o número de apontamentos (G1, G3) |
| `test_ids_marco.py` | O IDS de um marco só traz os requisitos daquele marco; o cabeçalho tem `purpose` e `milestone`; passa no XSD (S6) |
| `test_bcf_coordenadas.py` | Cada comentário de viewpoint por elemento traz GlobalId e XYZ; a câmera aponta para o centro da caixa |
| `test_edital_anotado.py` | O PDF gerado abre no PyMuPDF e tem uma anotação por apontamento de origem EDITAL com evidência |
| `test_consumo.py` | Com cliente simulado, os tokens somados por etapa batem com os informados pelo cliente |

### 11.3 Avaliação de qualidade (FB-06)

- Rode o pipeline com **um edital público real** e um IFC público, além dos dados sintéticos.
- A pessoa de BIM sorteia 20 apontamentos e classifica cada um como correto, parcialmente correto ou incorreto.
- Registre o resultado no `JOURNAL.md`, com o tamanho da amostra. Use esse número no pitch, e não o resultado sintético.

### 11.4 Critérios de aceite da versão 2.0

- [ ] O deploy roda em modo efêmero, e o teste `test_modo_efemero.py` passa.
- [ ] A faixa do ambiente de demonstração mostra a data de desligamento.
- [ ] Todo apontamento mostra a origem com selo de cor e texto.
- [ ] O relatório HTML separa "Corrigir no edital" e "Corrigir no modelo".
- [ ] A lição "sala de baterias" da demo gera um apontamento ao contratante e destaca os ambientes candidatos no 3D.
- [ ] O BCF abre numa ferramenta externa com XYZ e propriedades no comentário.
- [ ] O IDS traz `purpose` e `milestone`.
- [ ] `docs/idm.md` existe e é citado no relatório e no slide.
- [ ] O painel "Custo e tempo" mostra tokens medidos e o tempo manual medido, com fonte.
- [ ] A palavra "validadores" não aparece na interface nem nos slides.

---

## 12. Plano de execução e priorização

### 12.1 Antes do pitch (23/11/2026, até o congelamento do código)

| Ordem | Entrega | Requisitos | Dono sugerido (papéis da v1.0) |
|---|---|---|---|
| 1 | Modo efêmero mínimo: memória + TTL, cache do LLM desligado, `DELETE`, faixa e aviso de IA | RF-090 a RF-095, RF-098 | P2 |
| 2 | Origem visível e duas seções no relatório | RF-120, RF-120a, RF-120b | P3 |
| 3 | Lições aprendidas em planilha + apontamento ao contratante + salvaguardas G1–G4 | RF-100, RF-101, RF-103 a RF-105 | P1 |
| 4 | BCF com XYZ e propriedades | RF-170, RF-171, RF-175 | P2 |
| 5 | Nomenclatura, glossário, `purpose`/`milestone` e `docs/idm.md` | Seção 4, RF-110, RF-111 | P4 + P5 |
| 6 | Consumo de IA e tempo manual medido | RF-195 a RF-197 | P1 + P4 |
| 7 | Severidade baixa recolhida e não verificáveis na aba própria | RF-161, RF-162 | P3 |

**Se o tempo apertar, corte nesta ordem:** 7 → 6 (manter só os tokens no log) → 5 (manter só o texto do glossário no slide). **Nunca corte** os itens 1 e 2. Se o item 1 não ficar pronto, **corrija a fala do pitch**: diga que os arquivos ficam no servidor de demonstração até o desligamento, em quarta-feira.

### 12.2 Depois do pitch (curto prazo)

Marcos de entrega (RF-130), versão IFC (RF-131 a RF-133), edital anotado e esclarecimentos (RF-150 a RF-153), visualizador (RF-180 a RF-182), perfil de uso (RF-121), modo sem IFC (RF-198, RF-199), exemplos nos prompts e contexto adicional (RF-140, RF-141).

### 12.3 Médio prazo

Pacotes de contexto e NBR 15965 (RF-142, RF-143), comparação de verificações (RF-185 a RF-187), duplicidade (RF-200 a RF-202), desempenho (RF-190 a RF-192), snapshots no BCF (RF-174), linguagem acessível (RF-210, RF-211).

---

## 13. Decisões em aberto e pontos a confirmar

| # | Decisão ou ponto | Padrão até haver resposta | Dono |
|---|---|---|---|
| D7 | Termo final | **Decidido:** "requisitos de informação (RI)" | Time |
| D8 | Uso do documento de teste da banca | **Liberado pela banca.** O arquivo ainda não está no repositório. Para usar como contexto, coloque-o em `backend/resources/contexto/`; para usar como demo, em `data/` | Time |
| D9 | TTL do modo efêmero | 120 minutos (`EDITALCHECK_TTL_MIN`) | P2 |
| D10 | Preço por milhão de tokens do modelo Gemini usado | **Em aberto.** Sem preço configurado, o painel mostra só os tokens medidos | P1 |
| D11 | Formato do documento de lições aprendidas | **Decidido:** TXT ou PDF | Time |
| D12 | API Gemini paga e treino de modelos | **Confirmado pelo time:** a API paga não usa os dados para treino. O aviso da interface diz isso | Time |
| D13 | A ABNT NBR 15965 está publicada no bSDD? | **Em aberto.** Enquanto isso, classificações fora do bSDD saem como `customizado` | P2 |
| D14 | Versões vigentes das normas | **Conferidas em catálogos públicos em 22/11/2026:** ISO 29481-1:2025; ISO 19650-1:2018 e ABNT NBR ISO 19650-1:2022; ISO 7817-1:2024 (substituiu a EN 17412-1:2020); NBR 15965 em partes, sem lista completa confirmada | P4 |
| D15 | Data do desligamento do servidor | **Decidido:** não exibir data. `EDITALCHECK_DISPONIVEL_ATE` fica vazio; a variável continua disponível | Time |
| D16 | Artigo sobre geração de IDS com IA citado pelo time | **Pesquisado.** Candidatos: Ishigaki-IDS-Bench (arXiv:2605.22079), Ishigaki-IDS (arXiv:2606.08545) e Hosseini et al., capítulo da Taylor & Francis sobre mapeamento de linguagem natural para IFC na autoria de IDS. O time confirma qual foi lido | Time |

---

## 14. Riscos novos

| Risco | Prob. | Impacto | Mitigação |
|---|---|---|---|
| A fala sobre dados no pitch não bate com o servidor | Alta (hoje) | Alto | Entrega 1 da seção 12.1, ou correção da fala |
| Contexto ou lição usada para mascarar problemas | Média | Alto | G1–G4 e teste de injeção |
| Lições aprendidas com dados de cliente | Média | Alto | Modo efêmero; aviso no upload; nenhum exemplo real no repositório |
| Contexto demais aumenta a alucinação | Média | Médio | RNF-16; trechos selecionados por tópico; S2 |
| Reproduzir norma paga no repositório | Baixa | Alto | RNF-17 |
| Modo efêmero perde dados se o contêiner reiniciar no meio da demo | Média | Médio | Botão para baixar o relatório JSON; dados de exemplo sempre disponíveis |
| Memória insuficiente com IFC grande em RAM | Média | Médio | Limite de upload; limite de projetos simultâneos; TTL |
| Minuta de esclarecimento usada sem revisão jurídica | Média | Alto | Aviso fixo (RF-153) |

---

## 15. Mensagens para o pitch

Tiradas do debate com a banca:

1. **Problema:** no projeto, cada parte entende o edital de um jeito. Isso vira disputa. A ferramenta leva ao consenso (FB-21).
2. **Solução em uma frase:** a frase da seção 4.1.
3. **Escopo:** fase de contratação; EIR do contrato ou por marco. Diga o termo e explique na mesma frase (FB-24).
4. **Não reinventamos a roda:** IFC, IDS, BCF e bSDD. O LLM não escreve XML (FB-19).
5. **IDM explícito:** mostre o mapa de processo (FB-23).
6. **PDCA com lições aprendidas:** conte o caso da sala de baterias (FB-18).
7. **Salvaguardas:** a IA não consegue "aprovar" um problema; dispensar exige justificativa (FB-12).
8. **Dados:** só o que estiver implementado e conferido (FB-04, D12).
9. **Custo e tempo:** tokens medidos e tempo manual medido, com amostra (FB-27).
10. **Limites:** geometria, OCR e precisão em editais reais.
11. Use "análises", nunca "validadores" (FB-17).

---

## 16. Fora do escopo e roadmap

| Item | Origem | Observação |
|---|---|---|
| Login, multiusuário e perfis com permissão | FB-03 | Exige `ProjectRepository` com banco e autenticação |
| Produto SaaS ou integração ao visualizador do Construtivo | FB-29, T1 0:02:42 | Respeitar a regra "criado durante o hackathon" na apresentação |
| Verificação geométrica e relacional (ex.: aberturas em sala de baterias, pé-direito) | FB-18 | Novo analisador com `IfcRelSpaceBoundary` e geometria do IfcOpenShell; mesmo formato de apontamento |
| Comparação geométrica entre revisões do IFC | FB-11 | Diferente da comparação de apontamentos (RF-185) |
| Escala horizontal com fila e contêineres | FB-02 | Exige estado compartilhado com TTL (ex.: Redis), por causa do RNF-19 |
| Integração com CDE via OpenCDE (Documents, BCF API) | v1.0 | Mantido |
| BCF 3.0 | — | Avaliar depois de RF-170 |
| Correção assistida do modelo por outra IA a partir do relatório | T1 0:06:49 | O relatório JSON já serve de entrada; definir formato próprio depois |

---

## Anexo A — Como este documento foi produzido

- Fonte: as duas transcrições automáticas citadas no cabeçalho, lidas por completo.
- O código da `main` (commit `d11a9e8`) foi lido para separar o que já existe do que é novo. Exemplos: o armazenamento em `var/`, o cache em `.cache/`, os viewpoints por elemento no BCF e o mapeamento automático da versão IFC (`versao_ids`).
- O campo "Informações adicionais" foi mostrado na demo (T1 0:39:01), mas não está na `main`. Ele foi especificado como novo (RF-141).
- Nenhum número de custo, prazo ou norma foi inventado. O que não pôde ser conferido está marcado como **[confirmar]** ou consta da seção 13.

---

## 17. Status da implementação

Implementado em 23/11/2026, com 81 testes automatizados passando e o fluxo completo conferido no navegador.

| # | Mudança | Status | Onde |
|---|---|---|---|
| M1 | Modo efêmero, sem cache do LLM em disco, apagar dados, faixa de demonstração, aviso de IA, auditoria sem conteúdo | Feito | `adapters/storage/memory_repository.py`, `adapters/audit/`, `main.ts` |
| M2 | Origem visível (EDITAL × MODELO) com cor e texto, seções no relatório, abas na tela | Feito | `domain/models.py` (`Apontamento.origem`), `relatorio.html.j2`, `resultados.ts` |
| M3 | Nomenclatura RI, posicionamento e glossário | Feito | interface, relatório, XLSX, IDS |
| M4 | Lições aprendidas em TXT ou PDF | Feito | `domain/licoes.py`, `importar_licoes.py`, prompts `licoes.md` e `licao_no_edital.md` |
| M5 | Salvaguardas G1 a G4 | Feito | teste `test_licoes_nunca_removem_apontamentos` |
| M6 | BCF com XYZ, pavimento, falha e exigência | Feito | `adapters/bcf/bcf_writer.py` |
| M7 | IDM explícito | Feito | `docs/idm.md`, `purpose` e `milestone` no IDS |
| M8 | Consumo de IA, custo por preço configurado, tempo manual medido | Feito (custo depende de D10; tempo manual depende da medição do time) | `application/consumo.py`, `resources/referencia_tempo_manual.yaml` |
| M9 | Agrupar ambiguidades, verificação manual à parte, baixa recolhida, LLM só para alta e média | Feito | `domain/findings.py`, `gerar_relatorio.py`, `resultados.ts` |
| M10 | Edital anotado e matriz de esclarecimentos com decisões | Feito | `adapters/pdf/annotator.py`, `XlsxClarificationExporter` |
| M11 | Marcos de entrega e IDS por marco | Feito | `domain/marcos.py`, `gerar_ids.py`, telas de RI e IDS |
| M12 | Versão IFC escolhida e versão exigida no edital | Feito | `domain/versao_ifc.py` |
| M13 | Exemplos nos prompts e documentos de referência como contexto | Feito (falta colocar o documento da banca na pasta) | `adapters/contexto/referencias.py` |
| M14 | Visualizador: isolar, mostrar tudo, XYZ no detalhe | Feito | `viewer.ts` |
| M15 | Perfil de uso | Feito | seletor na tela de resultados |
| M16 | Revisar edital sem IFC | Feito | `ModeloResumo.vazio`, `importar_documentos.py` |
| M17 | Comparar verificações | Não feito (roadmap) | — |
| M18 | Texto repetido e valores diferentes | Feito (ignora cabeçalhos e rodapés repetidos) | `domain/duplicidade.py` |
| M19 | Desempenho | Parcial: menos chamadas (recomendação por IA só em alta e média) e paralelismo por tópico. Lotes de recomendação ficaram para depois | `gerar_relatorio.py` |
| M20 | Linguagem acessível | Parcial: glossário na tela e no relatório | `labels.ts`, `html_writer.py` |

| M21 | Visualizador do edital (só leitura): confirmação dos tópicos antes de gerar os RI e aba "Edital com os ajustes" nos resultados, com link "Ver no edital" no relatório HTML | Feito (pedido do time após a v2) | `frontend/src/pdf.ts`, `steps/confirmacao.ts`, `steps/edital.ts`, `adapters/pdf/localizador.py` |
| M22 | PDF com as sugestões: sumário com links, etiquetas que voltam ao sumário, links externos, índice por origem e apontamentos do modelo na cláusula de origem | Feito | `adapters/pdf/annotator.py` |

**Além do planejado:** checagem geométrica simples nas lições. Elementos que a lição proíbe (ex.: janelas) e cuja caixa envolvente toca o ambiente citado entram no apontamento. Na demo, o sistema mostra as janelas J11 e J12 na sala de baterias.
