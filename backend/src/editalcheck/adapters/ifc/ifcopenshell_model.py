"""Leitura do modelo IFC com IfcOpenShell: resumo, saúde e Psets oficiais."""

from collections import Counter
from functools import lru_cache

import ifcopenshell
import ifcopenshell.ifcopenshell_wrapper as wrapper
import ifcopenshell.util.element as util_element
import ifcopenshell.util.pset as util_pset

from editalcheck.adapters.ifc.abrir import IfcInvalidoError, abrir_ifc
from editalcheck.domain.models import (
    ClasseModelo,
    ElementoModelo,
    ModeloResumo,
    PropriedadeOficial,
    SaudeModelo,
)

CLASSES_EXCLUIDAS = ("IfcFeatureElement", "IfcVirtualElement")
PROXY = "IfcBuildingElementProxy"
PSETS_IGNORADOS = frozenset(
    {
        "Pset_EnvironmentalImpactIndicators",
        "Pset_EnvironmentalImpactValues",
        "Pset_Condition",
        "Pset_ManufacturerOccurrence",
        "Pset_PrecastConcreteElementFabrication",
        "Pset_PrecastConcreteElementGeneral",
        "Pset_ConcreteElementGeneral",
    }
)

__all__ = ["IfcInvalidoError", "IfcOpenShellModelReader"]


def _schema_base(schema: str) -> str:
    schema = schema.upper()
    if schema.startswith("IFC4X3"):
        return "IFC4X3"
    if schema.startswith("IFC2X3"):
        return "IFC2X3"
    return "IFC4"


def _schema_wrapper(schema: str) -> str:
    base = _schema_base(schema)
    return "IFC4X3_ADD2" if base == "IFC4X3" else base


@lru_cache(maxsize=8)
def _declaracoes(schema: str) -> wrapper.schema_definition:
    return wrapper.schema_by_name(_schema_wrapper(schema))


@lru_cache(maxsize=8)
def _templates(schema: str) -> util_pset.PsetQto:
    return util_pset.get_template(_schema_base(schema))


def _supertipos(schema: str, classe: str) -> tuple[str, ...]:
    try:
        declaracao = _declaracoes(schema).declaration_by_name(classe)
    except (RuntimeError, IndexError):
        return ()
    nomes: list[str] = []
    atual = declaracao.supertype() if hasattr(declaracao, "supertype") else None
    while atual is not None:
        nomes.append(atual.name())
        atual = atual.supertype()
    return tuple(nomes)


def _pavimento(elemento: ifcopenshell.entity_instance) -> str | None:
    atual = util_element.get_container(elemento)
    if atual is None:
        agregado = util_element.get_aggregate(elemento)
        atual = util_element.get_container(agregado) if agregado else None
        if atual is None and agregado is not None and agregado.is_a("IfcSpatialElement"):
            atual = agregado
    visitados = 0
    while atual is not None and not atual.is_a("IfcBuildingStorey") and visitados < 10:
        atual = util_element.get_aggregate(atual)
        visitados += 1
    if atual is None:
        return None
    return atual.Name or atual.GlobalId


def _elementos(arquivo: ifcopenshell.file) -> list[ifcopenshell.entity_instance]:
    excluidos: set[int] = set()
    for classe in CLASSES_EXCLUIDAS:
        try:
            excluidos.update(e.id() for e in arquivo.by_type(classe))
        except RuntimeError:
            continue
    elementos = [e for e in arquivo.by_type("IfcElement") if e.id() not in excluidos]
    return elementos + list(arquivo.by_type("IfcSpace"))


class IfcOpenShellModelReader:
    def load(self, conteudo: bytes, nome: str) -> ModeloResumo:
        arquivo = abrir_ifc(conteudo)
        schema = arquivo.schema_identifier
        elementos = _elementos(arquivo)
        contagem = Counter(e.is_a() for e in elementos)
        classes = tuple(
            ClasseModelo(
                nome=nome,
                contagem=total,
                especificavel=nome != PROXY,
                supertipos=_supertipos(schema, nome),
            )
            for nome, total in sorted(contagem.items(), key=lambda item: (-item[1], item[0]))
        )
        resumo_elementos = tuple(
            ElementoModelo(
                global_id=e.GlobalId,
                step_id=e.id(),
                classe=e.is_a(),
                nome=e.Name,
                pavimento=_pavimento(e),
                nome_longo=getattr(e, "LongName", None),
            )
            for e in elementos
        )
        return ModeloResumo(
            arquivo=nome,
            schema=schema,
            classes=classes,
            elementos=resumo_elementos,
            saude=self._saude(arquivo, schema, resumo_elementos),
        )

    def _saude(
        self, arquivo: ifcopenshell.file, schema: str, elementos: tuple[ElementoModelo, ...]
    ) -> SaudeModelo:
        fisicos = [e for e in elementos if e.classe != "IfcSpace"]
        guids = Counter(e.GlobalId for e in arquivo.by_type("IfcRoot"))
        return SaudeModelo(
            schema=schema,
            total_elementos=len(fisicos),
            proxies=sum(1 for e in fisicos if e.classe == PROXY),
            sem_pavimento=tuple(e.global_id for e in fisicos if e.pavimento is None),
            guids_duplicados=tuple(sorted(g for g, n in guids.items() if n > 1)),
            espacos=sum(1 for e in elementos if e.classe == "IfcSpace"),
        )

    def canonical_class(self, schema: str, ifc_class: str) -> str | None:
        if not ifc_class:
            return None
        try:
            declaracao = _declaracoes(schema).declaration_by_name(ifc_class.strip())
        except (RuntimeError, IndexError):
            return None
        return declaracao.name()

    def is_entity(self, schema: str, ifc_class: str) -> bool:
        try:
            declaracao = _declaracoes(schema).declaration_by_name(ifc_class.strip())
        except (RuntimeError, IndexError):
            return False
        return isinstance(declaracao, wrapper.entity)

    def official_properties(self, schema: str, ifc_class: str) -> list[PropriedadeOficial]:
        try:
            psets = _templates(schema).get_applicable(ifc_class, pset_only=True)
        except Exception:  # classe inexistente no schema
            return []
        propriedades: list[PropriedadeOficial] = []
        for pset in psets:
            if pset.Name in PSETS_IGNORADOS:
                continue
            for prop in pset.HasPropertyTemplates or ():
                if not prop.is_a("IfcSimplePropertyTemplate"):
                    continue
                enumeracao = getattr(prop, "Enumerators", None)
                valores = (
                    tuple(str(v.wrappedValue) for v in enumeracao.EnumerationValues)
                    if enumeracao
                    else ()
                )
                propriedades.append(
                    PropriedadeOficial(
                        pset=pset.Name,
                        nome=prop.Name,
                        tipo_dado=prop.PrimaryMeasureType or None,
                        descricao=(prop.Description or "").strip().split("\n")[0][:160],
                        valores_enumerados=valores,
                    )
                )
        return propriedades
