<!-- versao: 2026-11-22.2 -->
Extraia os requisitos de informação do modelo BIM contidos no tópico do edital abaixo. Gere um EIR estruturado.

## Como mapear cada requisito
- Um requisito por exigência verificável. Se uma frase exige duas propriedades, gere dois requisitos.
- "ifc_class": use uma classe da lista "Classes no modelo" quando a frase falar desse tipo de elemento (porta → IfcDoor, parede → IfcWall, janela → IfcWindow, ambiente/sala → IfcSpace, escada → IfcStair, laje → IfcSlab, extintor/hidrante → IfcFireSuppressionTerminal). Se a classe não estiver na lista mas existir no schema {{ schema_ifc }}, pode usá-la.
- "faceta":
  - "property": a frase exige uma propriedade. Preencha "pset", "propriedade" e "tipo_dado" com o vocabulário oficial listado abaixo sempre que possível.
  - "attribute": exige um atributo IFC (Name, Description, LongName, ObjectType, Tag). Preencha "propriedade" com o nome do atributo.
  - "classification": exige classificação. Preencha "pset" com o nome do sistema citado no edital.
  - "material": exige material associado.
  - "partOf": exige relação (ex.: elemento contido em pavimento). "pset" = entidade (ex.: IfcBuildingStorey); "propriedade" = relação (ex.: IFCRELCONTAINEDINSPATIALSTRUCTURE).
- "restricao" só quando o edital der valor: "valor" (um valor exato), "enumeracao" (lista fechada), "padrao" (regex) ou "intervalo" (mínimo/máximo em unidades SI: metros, W/(m²K)). Converta cm e mm para metros.
- "cardinalidade": "required" para "deverá/deve/obrigatório"; "optional" para "quando houver/se aplicável"; "prohibited" para "não deverá".
- "verificavel_por_ids" = false quando a exigência não é informação do modelo (prazo, custo, desempenho em obra, geometria, folgas, aprovação de projeto, "conforme normas vigentes" sem critério). Explique em "motivo_nao_verificavel". Mesmo assim, registre o requisito.
- "evidencia.trecho": copie literalmente a frase do edital que gera o requisito.
- Não gere requisitos para frases que não exigem nada do modelo.

## Classes no modelo ({{ schema_ifc }})
{% for c in classes -%}
- {{ c.nome }} ({{ c.contagem }} elementos)
{% endfor %}
## Vocabulário oficial (Pset.Propriedade: tipo) por classe
{{ vocabulario }}

## Termos do bSDD consultados
{% for t in termos_bsdd -%}
- {{ t.nome }} ({{ t.tipo }}): {{ t.uri }}
{% else -%}
(nenhum)
{% endfor %}
## Tópico {{ topico.numero }} — {{ topico.titulo }}
{{ topico.texto }}
