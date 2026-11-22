"""Origem do vocabulário (S4) e lista fechada de referências (S5)."""

from collections.abc import Sequence

from editalcheck.domain.models import (
    ContextoVocabulario,
    OrigemVocabulario,
    Referencia,
    Requisito,
    TipoFaceta,
)

URI_BSDD_IFC = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"


def uri_bsdd_classe(ifc_class: str) -> str:
    return f"{URI_BSDD_IFC}/class/{ifc_class}"


def uri_bsdd_propriedade(propriedade: str) -> str:
    return f"{URI_BSDD_IFC}/prop/{propriedade}"


def classificar_origem(
    requisito: Requisito, contexto: ContextoVocabulario
) -> tuple[OrigemVocabulario | None, str | None, str | None]:
    """Retorna (origem, uri_bsdd, aviso) para a propriedade do requisito."""
    if requisito.faceta != TipoFaceta.PROPRIEDADE or not requisito.propriedade:
        return None, requisito.bsdd_uri, None
    if requisito.pset:
        oficial = contexto.propriedade_oficial(requisito.pset, requisito.propriedade)
        if oficial:
            uri = requisito.bsdd_uri or uri_bsdd_propriedade(oficial.nome)
            return OrigemVocabulario.PSET_OFICIAL, uri, None
    termo = contexto.termo_bsdd(requisito.propriedade)
    if termo:
        return OrigemVocabulario.BSDD, termo.uri, None
    aviso = (
        f"Propriedade {requisito.pset or '?'}.{requisito.propriedade} não está nos Psets "
        "oficiais nem nos termos do bSDD consultados: marcada como customizada."
    )
    return OrigemVocabulario.CUSTOMIZADO, None, aviso


def filtrar_referencias(
    citadas: Sequence[Referencia], permitidas: Sequence[Referencia]
) -> tuple[tuple[Referencia, ...], bool]:
    """Mantém só referências da lista fechada. Retorna (refs, alguma_removida)."""
    rotulos = {p.rotulo.casefold(): p for p in permitidas}
    uris = {p.uri: p for p in permitidas if p.uri}
    mantidas: list[Referencia] = []
    removida = False
    for ref in citadas:
        encontrada = rotulos.get(ref.rotulo.casefold()) or (uris.get(ref.uri) if ref.uri else None)
        if encontrada is None:
            removida = True
            continue
        if encontrada not in mantidas:
            mantidas.append(encontrada)
    return tuple(mantidas), removida
