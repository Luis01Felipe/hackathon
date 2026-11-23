# Dados da demonstração e métricas

## Dados da demonstração

Os arquivos de `data/demo/` são **sintéticos**. O edital e o IFC são gerados por código (`uv run editalcheck gerar-demo`); as lições foram escritas pelo time:

- `edital.pdf`: edital fictício de uma escola, com 5 páginas. Mistura cláusulas verificáveis, termos vagos, itens mínimos ausentes e uma contradição (IFC 4 × IFC 2x3).
- `modelo.ifc`: escola de 2 pavimentos em IFC4, com 133 elementos e 18 ambientes. Tem erros planejados: 5 portas sem `FireRating`, 4 janelas sem `ThermalTransmittance`, 2 ambientes sem `LongName`, 1 escada com espelho de 0,19 m, 4 objetos genéricos e 1 elemento sem pavimento. O IFC passa na validação de schema do IfcOpenShell.
- `licoes_aprendidas.txt`: 4 lições de obras escolares fictícias. Uma já está explícita no edital (portas com FireRating); três não estão (sala de baterias sem janelas, lajes com LoadBearing, acesso à casa de bombas).
- No IFC, a sala S106 se chama "Sala de baterias" e tem duas janelas. Isso reproduz o caso relatado pela banca.
- `gabarito.json`: requisitos, trechos vagos e checklist esperados, anotados pelo time.

Nenhum dado de cliente, contrato ou projeto do Construtivo é usado.

## Métricas medidas (seção 14.3 da especificação)

Medidas em 22/11/2026 com `uv run editalcheck demo`, sobre os dados sintéticos (edital de 5 páginas e IFC de 151 elementos, 18 deles ambientes). Em 23/11/2026, depois da v2 e com as lições aprendidas, o modo offline foi medido de novo: recall 100% (19/19), precisão 100% (19/19), checklist 10/10, ambiguidade 10/10 e pipeline em menos de 1 s. Os requisitos vindos de lições ficam fora da métrica, porque o gabarito cobre só o edital. A coluna do Gemini não foi medida de novo após a v2.

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

---

[← Índice da documentação](README.md) · [README do projeto](../README.md)
