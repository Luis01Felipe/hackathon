"""Validação do IFC contra o IDS com o ifctester (análise A — RF-40)."""

import re

from ifctester import ids

from editalcheck.adapters.ifc.abrir import abrir_ifc
from editalcheck.domain.models import FalhaElemento, ResultadoEspecificacao

_TRADUCOES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"^The required property set does not exist$"),
        "O Pset exigido não existe no elemento",
    ),
    (
        re.compile(r"^The property set does not contain the required property$"),
        "O Pset não contém a propriedade exigida",
    ),
    (
        re.compile(
            r"^The property's data type \"(.*)\" does not match the required data type of \"(.*)\"$"
        ),
        r'O tipo de dado "\1" difere do exigido "\2"',
    ),
    (
        re.compile(r"^The property values? \"(.*)\" (?:does|do) not match the requirements$"),
        r'O valor "\1" não atende à restrição',
    ),
    (re.compile(r"^The required attribute did not exist$"), "O atributo exigido não existe"),
    (re.compile(r"^The attribute value \"(.*)\" is empty$"), r'O atributo está vazio ("\1")'),
    (
        re.compile(r"^The attribute value \"(.*)\" does not match the requirement$"),
        r'O valor do atributo "\1" não atende à restrição',
    ),
    (re.compile(r"^The entity has no classification$"), "O elemento não tem classificação"),
    (re.compile(r"^The entity has no material$"), "O elemento não tem material"),
    (re.compile(r"^The entity has no relationship$"), "O elemento não tem a relação exigida"),
)
_ID_REQUISITO = re.compile(r"^(REQ-\d+)")


def traduzir_motivo(motivo: str) -> str:
    for padrao, traducao in _TRADUCOES:
        if padrao.match(motivo):
            return padrao.sub(traducao, motivo)
    return motivo


def _requisito_id(especificacao: ids.Specification) -> str | None:
    if especificacao.identifier:
        return str(especificacao.identifier)
    encontrado = _ID_REQUISITO.match(especificacao.name or "")
    return encontrado.group(1) if encontrado else None


class IfcTesterValidator:
    def validate(self, ids_xml: bytes, conteudo_ifc: bytes) -> list[ResultadoEspecificacao]:
        documento = ids.from_string(ids_xml.decode("utf-8"))
        modelo = abrir_ifc(conteudo_ifc)
        documento.validate(modelo)
        return [self._resultado(spec) for spec in documento.specifications]

    def _resultado(self, especificacao: ids.Specification) -> ResultadoEspecificacao:
        falhas: dict[str, FalhaElemento] = {}
        for faceta in especificacao.requirements:
            for falha in faceta.failures:
                elemento = falha["element"]
                guid = getattr(elemento, "GlobalId", None) or str(elemento.id())
                if guid in falhas:
                    continue
                falhas[guid] = FalhaElemento(
                    global_id=guid,
                    step_id=elemento.id(),
                    classe=elemento.is_a(),
                    nome=getattr(elemento, "Name", None),
                    motivo=traduzir_motivo(str(falha.get("reason", ""))),
                )
        aplicaveis = especificacao.applicable_entities
        aprovados = tuple(
            e.GlobalId
            for e in aplicaveis
            if getattr(e, "GlobalId", None) and e.GlobalId not in falhas
        )
        return ResultadoEspecificacao(
            nome_especificacao=especificacao.name,
            requisito_id=_requisito_id(especificacao),
            status=bool(especificacao.status),
            aplicaveis=len(aplicaveis),
            aprovados=len(aprovados),
            falhas=tuple(falhas.values()),
            elementos_aprovados=aprovados,
        )
