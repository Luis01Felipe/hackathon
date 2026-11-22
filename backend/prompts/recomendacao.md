<!-- versao: 2026-11-22.1 -->
Escreva a recomendação de um apontamento de verificação de edital × modelo IFC.

- "como_agir": até 3 frases, no imperativo, dirigidas a quem deve agir ({{ apontamento.destinatario.value }}). Se o destinatário for o contratante, sugira nova redação da cláusula.
- "por_que": até 3 frases. Justifique citando SÓ referências da lista fechada abaixo.
- "referencias": copie exatamente os rótulos usados da lista fechada. Não cite nada fora dela.

## Apontamento
- Tipo: {{ apontamento.tipo.value }}
- Severidade: {{ apontamento.severidade.value }}
- Título: {{ apontamento.titulo }}
{% if apontamento.requisito_id %}- Requisito: {{ apontamento.requisito_id }}
{% endif %}{% if apontamento.classe_ifc %}- Classe IFC: {{ apontamento.classe_ifc }}
{% endif %}{% if apontamento.elementos %}- Elementos afetados: {{ apontamento.elementos | length }}
{% endif %}{% if apontamento.detalhe %}- Detalhe: {{ apontamento.detalhe }}
{% endif %}{% for e in apontamento.evidencias_edital -%}
- Trecho do edital (p. {{ e.pagina }}): "{{ e.trecho }}"
{% endfor %}
## Lista fechada de referências
{% for r in referencias -%}
- {{ r.rotulo }}
{% else -%}
(vazia — escreva sem referências)
{% endfor %}
