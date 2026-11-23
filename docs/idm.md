# Mapa de processo do EditalCheck (IDM)

> Referência: ISO 29481-1:2025 — *Building information models — Information delivery manual — Part 1: Methodology and format* (3ª edição, publicada em 11/2025, conforme o catálogo da ISO consultado em 22/11/2026). Confirme a vigência antes de citar em contrato.
> Este documento é de autoria do time. Ele aplica a lógica do IDM ao fluxo do EditalCheck e não reproduz o texto da norma.

## Por que um mapa IDM

A banca apontou que o IDM estava "espalhado" no projeto. O IDM organiza três perguntas:

1. **Quem** troca informação (atores)?
2. **Quando** a troca acontece (processo e marcos)?
3. **O que** precisa ser entregue em cada troca (requisitos de troca)?

No EditalCheck, as respostas são estas:

| Pergunta do IDM | Resposta no EditalCheck |
|---|---|
| Atores | Contratante (publica o edital), contratado líder e contratados (entregam o modelo), verificador independente |
| Processo e marcos | Fases do edital: estudo preliminar, anteprojeto, projeto básico, projeto executivo, como construído. O sistema detecta os marcos citados no edital |
| Requisitos de troca | Os **requisitos de informação (IR)** de cada marco. O **IDS** é a forma verificável por máquina desses requisitos |

## Mapa de processo

```
 Contratante                    EditalCheck                         Revisor humano
 ───────────                    ───────────                         ──────────────
 Edital (PDF) ─────────┐
 Lições aprendidas ────┼──► Lê, segmenta e extrai ──► IR propostos ──► aprova, edita, rejeita
 (TXT/PDF, ciclo PDCA) │    (citações conferidas)      por marco          e associa a marcos
                       │                                                       │
                       │                                                       ▼
                       │                              IDS por marco ◄──── IR aprovados
                       │                              (purpose + milestone)
 Contratado            │                                     │
 ──────────            │                                     ▼
 Modelo IFC ───────────┴──────────────────────────► Análises A, B, C, lições e saúde
 (por marco)                                                 │
                                                             ▼
                       ┌───────────────── Relatório por origem ─────────────────┐
                       ▼                                                          ▼
       EDITAL: contratante corrige                                MODELO: contratado corrige
       edital anotado (PDF), matriz de                           BCF com coordenada XYZ,
       esclarecimentos (XLSX)                                    viewpoint por elemento
                       │                                                          │
                       └────────────► Decisões registradas (consenso) ◄──────────┘
                                      aceito, rejeitado, em discussão, dispensado
                                                     │
                                                     ▼
                                    Nova revisão do edital ou do modelo
                                    e nova verificação (ciclo PDCA)
```

## Trocas de informação

| ID | Troca | De → Para | Conteúdo | Formato |
|---|---|---|---|---|
| T1 | Requisitos da contratação | Contratante → Contratado | Edital e IR aprovados | PDF, XLSX, IDS |
| T2 | Entrega do modelo | Contratado → Contratante | Modelo do marco | IFC |
| T3 | Apontamentos do modelo | Verificador → Contratado | Não conformidades e qualidade do modelo | BCF 2.1, relatório HTML |
| T4 | Apontamentos do edital | Verificador → Contratante | Ambiguidades, lacunas, contradições, lições ausentes | Edital anotado (PDF), matriz de esclarecimentos (XLSX) |
| T5 | Registro de consenso | Contratante ↔ Contratado | Decisão sobre cada apontamento, com justificativa | Relatório HTML e JSON |
| T6 | Lições aprendidas | Obras anteriores → Contratante | Regras para o próximo edital | TXT ou PDF |

## Como o mapa aparece no produto

- O IDS gerado traz `milestone` (o marco ou "Contrato inteiro") e `purpose` (contrato de dados da contratação).
- Cada especificação do IDS cita o requisito, o marco e o trecho do edital.
- O relatório mostra o escopo verificado (contrato ou marco) e separa o que o contratante corrige do que o contratado corrige.

## Escopo e limites

- O EditalCheck trata a fase de **contratação e entregas do contrato**. Ele não cobre requisitos de operação do ativo (AIR).
- Um IDS do contrato inteiro é válido e já é usado no mercado. O IDS por marco atende a quem prefere verificar cada entrega.
- O nome final do conjunto de requisitos ficou "requisitos de informação (IR, de Information Requirements)", mais genérico que EIR, por decisão do time. A sigla segue o inglês, como as demais da ISO 19650.
