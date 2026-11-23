"""Versões de IFC citadas no edital e confronto com o schema do modelo."""

import re

from editalcheck.domain.evidence import normalizar
from editalcheck.domain.models import Edital, Evidencia
from editalcheck.domain.vagueness import dividir_sentencas

_VERSAO = re.compile(r"\bifc\s*[- ]?\s*(2\s*x\s*3|4\s*x\s*3|4\.3|4)(?:\s*add\s*2)?\b")
VERSOES_IDS = ("IFC2X3", "IFC4", "IFC4X3_ADD2")


def canonica(schema: str) -> str:
    """Nome da versão no IDS 1.0 a partir do schema do arquivo IFC."""
    schema = schema.upper().replace(" ", "")
    if schema.startswith("IFC4X3") or schema.startswith("IFC4.3"):
        return "IFC4X3_ADD2"
    if schema.startswith("IFC2X3"):
        return "IFC2X3"
    return "IFC4"


def citadas(edital: Edital) -> dict[str, Evidencia]:
    """Versões de IFC citadas no edital, com a primeira frase de cada uma."""
    versoes: dict[str, Evidencia] = {}
    for pagina in edital.paginas:
        for sentenca in dividir_sentencas(pagina.texto):
            for encontrada in _VERSAO.finditer(normalizar(sentenca)):
                bruta = encontrada.group(1).replace(" ", "").replace(".", "x")
                versao = canonica(f"IFC{bruta}")
                versoes.setdefault(versao, Evidencia(pagina=pagina.numero, trecho=sentenca))
    return versoes


def exigida(edital: Edital) -> tuple[str, Evidencia] | None:
    """A versão exigida, quando o edital cita uma única versão de IFC."""
    versoes = citadas(edital)
    if len(versoes) != 1:
        return None
    return next(iter(versoes.items()))
