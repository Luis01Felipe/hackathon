# Limites e licenças

## Limites

- Verifica só informação alfanumérica do modelo (IDS). Requisitos geométricos, de desempenho, prazo e custo saem como **verificação manual**. A única checagem geométrica é simples: elementos proibidos por uma lição (ex.: janelas) cuja caixa envolvente toca o ambiente citado.
- No modo efêmero, um reinício do servidor apaga os projetos em andamento. O usuário pode baixar o relatório JSON antes.
- O tempo manual equivalente ainda não foi medido. O painel mostra "não medido" até o time preencher `backend/resources/referencia_tempo_manual.yaml`.
- Não faz OCR: PDFs escaneados são recusados com aviso.
- A segmentação de tópicos reconhece títulos numerados de nível 1 e 2 ("5 TÍTULO", "5.1 Título", "5 – TÍTULO") e anexos ("ANEXO I – ..."). Títulos sem número, como "CLÁUSULA PRIMEIRA" e "CAPÍTULO II", ainda não são reconhecidos.
- O extrator por regras cobre o vocabulário de `backend/resources/vocabulario_pt.yaml`. Editais reais exigem o LLM.
- A checklist e o léxico de termos vagos são autoria do time, inspirados na ISO 19650. Eles não substituem a análise jurídica do edital.
- Os adaptadores de IA têm testes com cliente simulado, que usam os prompts reais. O Gemini (`gemini-4-hydrogen`) já respondeu em execuções reais da demo.
- **Acesso:** não há login. O acesso a um projeto depende do id dele (128 bits, inviável de adivinhar por tentativa), que só o navegador de quem enviou os arquivos conhece. Autenticação e limite de requisições por usuário, se forem necessários, ficam a cargo do proxy (Traefik).
- Os uploads têm limite por arquivo (`LIMITE_UPLOAD_MB`), por soma e por quantidade de lições. A leitura de PDF e IFC roda no próprio processo, sem isolamento de recursos. Arquivos de origem desconhecida devem passar antes por um antivírus.

## Licenças

- Backend: IfcOpenShell e ifctester (LGPL-3.0), **bcf-client (GPL-3.0)**, **PyMuPDF (AGPL-3.0 ou licença comercial da Artifex)**, FastAPI (MIT), Pydantic (MIT), google-genai (Apache-2.0). Na prática, o backend precisa ser distribuído sob AGPL-3.0, ou é preciso trocar o leitor de PDF e o escritor de BCF. Os adaptadores `EditalReader` e `BcfWriter` isolam essas trocas. A licença do repositório é uma decisão do time.
- Frontend: `@thatopen/components` 3.6.0 e `@thatopen/fragments` 3.6.1 (MIT), three.js (MIT), web-ifc (MPL-2.0), `pdfjs-dist` 6.5.438 (Mozilla pdf.js, Apache-2.0, build "legacy" para navegadores mais antigos). Nenhum pacote AGPL no frontend (RNF-09).

---

[← Índice da documentação](README.md) · [README do projeto](../README.md)
