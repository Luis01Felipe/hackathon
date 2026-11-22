"""Cobertura do edital sobre o modelo (análise C, sem LLM — RF-41).

cobertura = classes do modelo com ≥ 1 requisito aprovado
            / classes especificáveis presentes no modelo
"""

from collections.abc import Sequence

from editalcheck.domain.models import (
    ClasseModelo,
    Cobertura,
    CoberturaClasse,
    PropriedadeOficial,
    PropriedadeSugerida,
    Requisito,
)

PRIORIDADE_PROPRIEDADES: tuple[str, ...] = (
    "FireRating",
    "IsExternal",
    "LoadBearing",
    "ThermalTransmittance",
    "AcousticRating",
    "FireExit",
    "HandicapAccessible",
    "NumberOfRiser",
    "RiserHeight",
    "TreadLength",
    "OccupancyType",
    "GrossPlannedArea",
    "Reference",
    "Status",
)


def _classes_atendidas(classe: ClasseModelo) -> set[str]:
    return {classe.nome.lower(), *(s.lower() for s in classe.supertipos)}


def calcular(classes: Sequence[ClasseModelo], requisitos: Sequence[Requisito]) -> Cobertura:
    especificaveis = sorted(
        (c for c in classes if c.especificavel), key=lambda c: (-c.contagem, c.nome)
    )
    aprovados = [r for r in requisitos if r.aprovado and r.ifc_class]
    linhas: list[CoberturaClasse] = []
    for classe in especificaveis:
        nomes = _classes_atendidas(classe)
        ids = tuple(r.id for r in aprovados if r.ifc_class and r.ifc_class.lower() in nomes)
        linhas.append(
            CoberturaClasse(
                classe=classe.nome, contagem=classe.contagem, coberta=bool(ids), requisitos=ids
            )
        )
    if not linhas:
        return Cobertura(percentual=None, classes=())
    cobertas = sum(1 for linha in linhas if linha.coberta)
    return Cobertura(percentual=round(100 * cobertas / len(linhas), 1), classes=tuple(linhas))


def sugerir_propriedades(
    classe: str, oficiais: Sequence[PropriedadeOficial], limite: int = 3
) -> list[PropriedadeSugerida]:
    """Escolhe até ``limite`` propriedades dos Psets oficiais para a classe.

    Prefere o Pset "<Classe>Common" e as propriedades da lista de prioridade.
    """
    if not oficiais:
        return []
    comum = f"pset_{classe[3:].lower()}common" if classe.lower().startswith("ifc") else ""

    def chave(prop: PropriedadeOficial) -> tuple[int, int, str]:
        pset_comum = 0 if prop.pset.lower() == comum else 1
        if pset_comum and prop.pset.lower().endswith("common"):
            pset_comum = 0
        try:
            prioridade = PRIORIDADE_PROPRIEDADES.index(prop.nome)
        except ValueError:
            prioridade = len(PRIORIDADE_PROPRIEDADES)
        return (pset_comum, prioridade, prop.nome)

    escolhidas: list[PropriedadeSugerida] = []
    for prop in sorted(oficiais, key=chave):
        if len(escolhidas) >= limite:
            break
        escolhidas.append(
            PropriedadeSugerida(pset=prop.pset, nome=prop.nome, tipo_dado=prop.tipo_dado)
        )
    return escolhidas
