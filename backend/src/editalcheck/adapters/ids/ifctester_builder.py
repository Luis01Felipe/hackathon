"""Geração determinística do IDS 1.0 a partir dos requisitos de informação (RI) aprovados.

O LLM nunca escreve XML: cada requisito aprovado vira uma especificação IDS
por código, com o ID do requisito no nome e no identifier.
"""

from collections.abc import Sequence
from datetime import date

from ifctester import ids

from editalcheck.domain.models import (
    Eir,
    Requisito,
    Restricao,
    TipoFaceta,
    TipoRestricao,
)
from editalcheck.domain.versao_ifc import canonica

RELACOES_PARTOF = {
    "IFCRELAGGREGATES",
    "IFCRELASSIGNSTOGROUP",
    "IFCRELCONTAINEDINSPATIALSTRUCTURE",
    "IFCRELNESTS",
    "IFCRELVOIDSELEMENT IFCRELFILLSELEMENT",
}
TIPOS_NUMERICOS = ("MEASURE", "IFCINTEGER", "IFCREAL", "IFCNUMERICMEASURE", "IFCCOUNTMEASURE")


class IdsInvalidoError(ValueError):
    pass


def versao_ids(schema: str) -> str:
    """Versão do IDS 1.0 (IFC2X3, IFC4 ou IFC4X3_ADD2) para um schema ou versão."""
    return canonica(schema)


def _base_xsd(tipo_dado: str | None) -> str:
    if not tipo_dado:
        return "string"
    tipo = tipo_dado.upper()
    if tipo == "IFCBOOLEAN" or tipo == "IFCLOGICAL":
        return "boolean"
    if tipo in ("IFCINTEGER", "IFCCOUNTMEASURE"):
        return "integer"
    if any(marca in tipo for marca in TIPOS_NUMERICOS):
        return "double"
    return "string"


def _valor_simples(valor: str, base: str) -> str:
    if base == "boolean":
        return "true" if valor.strip().lower() in ("true", "verdadeiro", "sim", "1") else "false"
    if base in ("double", "integer"):
        return valor.strip().replace(",", ".")
    return valor


def _numero(valor: float, base: str) -> float | int:
    return int(valor) if base == "integer" and float(valor).is_integer() else float(valor)


def valor_ids(restricao: Restricao | None, tipo_dado: str | None) -> str | ids.Restriction | None:
    if restricao is None:
        return None
    base = _base_xsd(tipo_dado)
    match restricao.tipo:
        case TipoRestricao.VALOR if restricao.valores:
            return _valor_simples(restricao.valores[0], base)
        case TipoRestricao.ENUMERACAO if restricao.valores:
            valores = [_valor_simples(v, base) for v in restricao.valores]
            return ids.Restriction(options={"enumeration": valores}, base=base)
        case TipoRestricao.PADRAO if restricao.valores:
            return ids.Restriction(options={"pattern": restricao.valores[0]}, base="string")
        case TipoRestricao.INTERVALO:
            base_numerica = base if base in ("double", "integer") else "double"
            opcoes: dict[str, float | int] = {}
            if restricao.minimo is not None:
                opcoes["minInclusive"] = _numero(restricao.minimo, base_numerica)
            if restricao.maximo is not None:
                opcoes["maxInclusive"] = _numero(restricao.maximo, base_numerica)
            return ids.Restriction(options=opcoes, base=base_numerica) if opcoes else None
    return None


def _requisito_ids(requisito: Requisito):
    cardinalidade = requisito.cardinalidade.value
    valor = valor_ids(requisito.restricao, requisito.tipo_dado)
    match requisito.faceta:
        case TipoFaceta.PROPRIEDADE:
            return ids.Property(
                propertySet=requisito.pset,
                baseName=requisito.propriedade,
                value=valor,
                dataType=requisito.tipo_dado.upper() if requisito.tipo_dado else None,
                uri=requisito.bsdd_uri,
                cardinality=cardinalidade,
            )
        case TipoFaceta.ATRIBUTO:
            return ids.Attribute(name=requisito.propriedade, value=valor, cardinality=cardinalidade)
        case TipoFaceta.CLASSIFICACAO:
            return ids.Classification(
                system=requisito.pset or None, value=valor, cardinality=cardinalidade
            )
        case TipoFaceta.MATERIAL:
            return ids.Material(value=valor, cardinality=cardinalidade)
        case TipoFaceta.PARTE_DE:
            relacao = (requisito.propriedade or "").upper() or None
            if relacao and relacao not in RELACOES_PARTOF:
                raise IdsInvalidoError(f"{requisito.id}: relação partOf inválida ({relacao}).")
            return ids.PartOf(
                name=(requisito.pset or "IFCBUILDINGSTOREY").upper(),
                relation=relacao,
                cardinality=cardinalidade,
            )
    raise IdsInvalidoError(f"{requisito.id}: faceta não suportada ({requisito.faceta}).")


def especificacao(requisito: Requisito, schema: str, marco: str | None = None) -> ids.Specification:
    if not requisito.ifc_class:
        raise IdsInvalidoError(f"{requisito.id}: requisito sem classe IFC.")
    trecho = " ".join(requisito.evidencia.trecho.split())
    origem = (
        "Sugerido pela análise de cobertura do EditalCheck (cláusula a incluir no edital)."
        if requisito.sugerido_por_lacuna
        else f"Edital, p. {requisito.evidencia.pagina}: {trecho[:200]}"
    )
    spec = ids.Specification(
        name=f"{requisito.id} · {requisito.descricao[:80]}",
        ifcVersion=[versao_ids(schema)],
        identifier=requisito.id,
        description=origem,
        instructions=(
            f"Requisito {requisito.id} dos requisitos de informação (RI) aprovados "
            f"(tópico {requisito.topico_id}). Entrega: {marco or 'contrato inteiro'}."
        ),
        minOccurs=0,
        maxOccurs="unbounded",
    )
    spec.applicability.append(
        ids.Entity(
            name=requisito.ifc_class.upper(),
            predefinedType=requisito.predefined_type.upper() if requisito.predefined_type else None,
        )
    )
    spec.requirements.append(_requisito_ids(requisito))
    return spec


class IfcTesterIdsBuilder:
    def build(
        self,
        eir: Eir,
        versao_ifc: str,
        titulo: str,
        marco: str | None = None,
        requisitos: Sequence[Requisito] | None = None,
    ) -> bytes:
        """Monta o IDS do contrato inteiro (``marco=None``) ou de um marco de entrega."""
        documento = ids.Ids(
            title=titulo,
            version=f"RI v{eir.versao}",
            description="Requisitos de informação (RI) extraídos do edital e aprovados por uma "
            "pessoa (EditalCheck). Cada especificação cita a página e o trecho do edital.",
            date=date.today().isoformat(),
            purpose=(
                "Contrato de dados da contratação: o que o modelo IFC deve conter em cada "
                "entrega, conforme o edital."
            ),
            milestone=marco or "Contrato inteiro",
        )
        alvo = eir.requisitos_para_ids if requisitos is None else requisitos
        for requisito in alvo:
            documento.specifications.append(especificacao(requisito, versao_ifc, marco))
        if not documento.specifications:
            raise IdsInvalidoError("Não há requisito aprovado e verificável por IDS neste escopo.")
        xml = documento.to_string()
        return ('<?xml version="1.0" encoding="UTF-8"?>\n' + xml).encode("utf-8")

    def check(self, ids_xml: bytes) -> list[str]:
        """S6: valida o XML contra o XSD oficial do IDS 1.0 e recarrega no ifctester.

        Valida o texto direto no xmlschema: o ``from_string(validate=True)`` do
        ifctester perde os prefixos de namespace e rejeita restrições válidas
        (ex.: ``base="xs:double"``).
        """
        texto = ids_xml.decode("utf-8")
        corpo = texto.split("?>", 1)[1].lstrip() if texto.startswith("<?xml") else texto
        erros = [str(e.reason or e.message)[:300] for e in ids.get_schema().iter_errors(corpo)]
        if erros:
            return [f"IDS inválido no XSD: {e}" for e in erros[:5]]
        try:
            documento = ids.from_string(texto)
        except Exception as erro:  # xmlschema/ElementTree lançam tipos variados
            return [f"IDS não recarregou no ifctester: {erro}"]
        if not documento.specifications:
            return ["IDS sem especificações."]
        return []
