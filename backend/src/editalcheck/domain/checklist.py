"""Checklist de itens mínimos do edital (RF-44).

As respostas "presente" e "parcial" exigem um trecho com página conferido
pela salvaguarda S2. Sem trecho conferido, o item vale como "ausente".
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from editalcheck.domain.evidence import conferir_evidencia, normalizar, remover_acentos
from editalcheck.domain.models import (
    Edital,
    Evidencia,
    ItemChecklist,
    ResultadoChecklist,
    StatusChecklist,
)
from editalcheck.domain.vagueness import dividir_sentencas


@dataclass(frozen=True)
class RegraChecklist:
    """Regras determinísticas do modo sem LLM para um item."""

    item_id: str
    padroes_presente: tuple[str, ...] = ()  # regex que indicam o item completo
    palavras_chave: tuple[str, ...] = ()  # indicam o item de forma parcial


def aplicar_salvaguarda(
    resultados: Sequence[ResultadoChecklist],
    edital: Edital,
    paginas_permitidas: Iterable[int] | None = None,
) -> list[ResultadoChecklist]:
    paginas = list(paginas_permitidas) if paginas_permitidas is not None else None
    conferidos: list[ResultadoChecklist] = []
    for resultado in resultados:
        if resultado.status == StatusChecklist.AUSENTE:
            conferidos.append(replace(resultado, evidencia=None))
            continue
        evidencia = (
            conferir_evidencia(resultado.evidencia, edital, paginas)
            if resultado.evidencia
            else None
        )
        if evidencia is None:
            conferidos.append(
                replace(
                    resultado,
                    status=StatusChecklist.AUSENTE,
                    evidencia=None,
                    justificativa="Sem trecho do edital conferido (salvaguarda S2). "
                    + resultado.justificativa,
                )
            )
            continue
        conferidos.append(replace(resultado, evidencia=evidencia))
    return conferidos


def completar(
    resultados: Sequence[ResultadoChecklist], itens: Sequence[ItemChecklist]
) -> list[ResultadoChecklist]:
    """Garante um resultado por item, na ordem da checklist."""
    por_id = {r.item_id: r for r in resultados}
    completos: list[ResultadoChecklist] = []
    for item in itens:
        resultado = por_id.get(item.id)
        if resultado is None:
            resultado = ResultadoChecklist(
                item_id=item.id,
                status=StatusChecklist.AUSENTE,
                justificativa="Item não avaliado.",
            )
        completos.append(resultado)
    return completos


def _primeira_sentenca(edital: Edital, padrao: re.Pattern[str]) -> Evidencia | None:
    for pagina in edital.paginas:
        for sentenca in dividir_sentencas(pagina.texto):
            if padrao.search(remover_acentos(normalizar(sentenca))):
                return Evidencia(pagina=pagina.numero, trecho=sentenca)
    return None


def avaliar_por_regras(
    edital: Edital, itens: Sequence[ItemChecklist], regras: Sequence[RegraChecklist]
) -> list[ResultadoChecklist]:
    """Fallback determinístico: padrões fortes → presente; palavra-chave → parcial."""
    por_item = {r.item_id: r for r in regras}
    resultados: list[ResultadoChecklist] = []
    for item in itens:
        regra = por_item.get(item.id, RegraChecklist(item.id, (), item.palavras_chave))
        evidencia = None
        for padrao in regra.padroes_presente:
            evidencia = _primeira_sentenca(edital, re.compile(padrao, re.IGNORECASE))
            if evidencia:
                break
        if evidencia:
            resultados.append(
                ResultadoChecklist(
                    item_id=item.id,
                    status=StatusChecklist.PRESENTE,
                    evidencia=evidencia,
                    justificativa="Padrão objetivo encontrado no edital (regra determinística).",
                    avaliado_por="regras",
                )
            )
            continue
        for palavra in regra.palavras_chave:
            chave = remover_acentos(normalizar(palavra))
            evidencia = _primeira_sentenca(edital, re.compile(rf"(?<!\w){re.escape(chave)}"))
            if evidencia:
                break
        if evidencia:
            resultados.append(
                ResultadoChecklist(
                    item_id=item.id,
                    status=StatusChecklist.PARCIAL,
                    evidencia=evidencia,
                    justificativa="Tema citado, mas sem critério objetivo identificado por regra.",
                    avaliado_por="regras",
                )
            )
            continue
        resultados.append(
            ResultadoChecklist(
                item_id=item.id,
                status=StatusChecklist.AUSENTE,
                justificativa="Nenhuma menção encontrada no edital.",
                avaliado_por="regras",
            )
        )
    return resultados
