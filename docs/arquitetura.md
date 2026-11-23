# Arquitetura

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

---

[← Índice da documentação](README.md) · [README do projeto](../README.md)
