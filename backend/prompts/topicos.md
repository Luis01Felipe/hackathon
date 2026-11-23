<!-- versao: 2026-11-23.1 -->
Abaixo estão os tópicos de um edital, já segmentados por regra (número e título). Para cada tópico:
- mantenha o "id" exatamente igual;
- devolva um "titulo" curto e claro (pode manter o original);
- escreva um "resumo" de até 20 palavras;
- marque "relevante_bim" = true se o tópico traz requisitos sobre o modelo BIM, os dados do modelo, os elementos construtivos ou a entrega de informação. Prazos, pagamentos, habilitação e garantias não são relevantes.

Não crie, junte nem divida tópicos.

Exemplos de decisão (ilustrativos):
- "4 DA MODELAGEM DA INFORMAÇÃO (BIM)", "5.1 Portas", "Formato de entrega do IFC" → relevante_bim = true.
- "3 DOS PRAZOS E DO PAGAMENTO", "2 DAS CONDIÇÕES DE PARTICIPAÇÃO", "Da garantia contratual" → relevante_bim = false.

{% for t in topicos -%}
### {{ t.id }} — {{ t.numero }} {{ t.titulo }} (p. {{ t.pagina_inicio }}–{{ t.pagina_fim }})
{{ t.texto[:500] }}

{% endfor %}
