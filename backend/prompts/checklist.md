<!-- versao: 2026-11-22.1 -->
Avalie se o edital abaixo define cada item mínimo de requisitos de informação (checklist inspirada no conteúdo esperado de requisitos de informação na ISO 19650).

Para cada item da checklist, responda:
- "presente": o edital define o item com critério objetivo;
- "parcial": o edital cita o tema, mas sem critério objetivo;
- "ausente": o edital não trata do item.

As respostas "presente" e "parcial" EXIGEM "evidencia" com a página e uma frase copiada literalmente do edital. Sem evidência literal, a resposta será tratada como "ausente".

## Checklist
{% for i in itens -%}
- {{ i.id }}: {{ i.item }}{% if i.descricao %} — {{ i.descricao }}{% endif %}
{% endfor %}
## Texto do edital (tópicos relevantes)
{{ texto }}
