<!-- versao: 2026-11-22.1 -->
Cada trecho abaixo, de um edital de obra pública, contém um termo que o léxico marcou como possivelmente vago. Para cada trecho, decida se ele é AMBÍGUO NO CONTEXTO, ou seja, se não traz critério mensurável que permita verificar o cumprimento.

- "ambiguo" = false se a frase já define valor, norma com número, lista fechada ou critério objetivo.
- "justificativa": uma frase.
- "redacao_sugerida": se for ambíguo, proponha uma redação mensurável para a cláusula (até 2 frases). Não invente números de normas: use "[norma a definir]" se precisar.
- Devolva um item por trecho, com o mesmo "indice".

{% for c in candidatos -%}
[{{ loop.index0 }}] (p. {{ c.pagina }}, termo: "{{ c.termo }}") {{ c.trecho }}
{% endfor %}
