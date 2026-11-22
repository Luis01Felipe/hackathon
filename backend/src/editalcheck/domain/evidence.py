"""Conferência literal de citações do edital (salvaguarda S2).

Toda citação produzida pela IA precisa existir no texto extraído da página.
A comparação usa texto normalizado: espaços, hifenização de fim de linha,
aspas/travessões tipográficos e caixa.
"""

import re
import unicodedata
from collections.abc import Iterable

from editalcheck.domain.models import Edital, Evidencia, Pagina

_HIFENIZACAO = re.compile(r"(\w)-[ \t]*\r?\n[ \t]*(\w)")
_ESPACOS = re.compile(r"\s+")
_MARCADOR_PAGINA = re.compile(r"\[p\.\s*\d+\]", re.IGNORECASE)
_RETICENCIAS = re.compile(r"\s*(?:\.\.\.|…|\[\.\.\.\]|\(\.\.\.\))\s*")
_CLAUSULA = re.compile(r"^(\d{1,2}(?:\.\d{1,2})+|\d{1,2}\.)\s+\S")
_TRADUCAO = str.maketrans(
    {
        "“": '"',
        "”": '"',
        "„": '"',
        "‘": "'",
        "’": "'",
        "–": "-",
        "—": "-",
        "‐": "-",
        " ": " ",
        "­": "",
    }
)
_TAMANHO_MINIMO_SEGMENTO = 12


def desifenizar(texto: str) -> str:
    """Junta palavras quebradas com hífen no fim da linha ("resis-\\ntência")."""
    return _HIFENIZACAO.sub(r"\1\2", texto)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKC", texto)
    texto = desifenizar(texto)
    texto = texto.translate(_TRADUCAO)
    texto = _MARCADOR_PAGINA.sub(" ", texto)
    texto = _ESPACOS.sub(" ", texto)
    return texto.strip().casefold()


def remover_acentos(texto: str) -> str:
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def compactar_espacos(texto: str) -> str:
    return _ESPACOS.sub(" ", desifenizar(texto)).strip()


def _segmentos_em_ordem(segmentos: list[str], texto: str) -> bool:
    posicao = 0
    for segmento in segmentos:
        if len(segmento) < _TAMANHO_MINIMO_SEGMENTO and len(segmentos) > 1:
            return False
        indice = texto.find(segmento, posicao)
        if indice < 0:
            return False
        posicao = indice + len(segmento)
    return True


def trecho_confere(trecho: str, texto_pagina: str) -> bool:
    """True se o trecho existe literalmente (após normalização) no texto.

    Aceita reticências no trecho: cada segmento precisa aparecer, na ordem.
    Se não achar, compara de novo sem nenhum espaço: a quebra de linha do PDF
    pode inserir ou tirar espaços (ex.: "W/\\n(m²·K)" × "W/(m²·K)"). Os
    caracteres continuam precisando ser idênticos e na mesma ordem.
    """
    segmentos = [s.strip() for s in _RETICENCIAS.split(normalizar(trecho)) if s.strip()]
    if not segmentos:
        return False
    texto = normalizar(texto_pagina)
    if _segmentos_em_ordem(segmentos, texto):
        return True
    compactos = [_ESPACOS.sub("", s) for s in segmentos]
    return _segmentos_em_ordem(compactos, _ESPACOS.sub("", texto))


def conferir_evidencia(
    evidencia: Evidencia,
    edital: Edital,
    paginas_permitidas: Iterable[int] | None = None,
) -> Evidencia | None:
    """Confere a evidência na página indicada; corrige a página se o trecho
    estiver em outra página permitida. Retorna None se o trecho não existe."""
    if len(normalizar(evidencia.trecho)) < _TAMANHO_MINIMO_SEGMENTO:
        return None
    pagina = edital.pagina(evidencia.pagina)
    if pagina and trecho_confere(evidencia.trecho, pagina.texto):
        return evidencia
    candidatas = set(paginas_permitidas) if paginas_permitidas is not None else None
    for outra in edital.paginas:
        if candidatas is not None and outra.numero not in candidatas:
            continue
        if outra.numero == evidencia.pagina:
            continue
        if trecho_confere(evidencia.trecho, outra.texto):
            return Evidencia(pagina=outra.numero, trecho=evidencia.trecho)
    return None


def clausula_do_trecho(texto_pagina: str, trecho: str) -> str | None:
    """Número da cláusula (ex.: "5.1.1") que contém o trecho, se houver."""
    alvo = normalizar(trecho)[:40]
    if not alvo:
        return None
    acumulado = ""
    marcos: list[tuple[int, str | None]] = []
    clausula_atual: str | None = None
    for linha in desifenizar(texto_pagina).splitlines():
        normalizada = normalizar(linha)
        if not normalizada:
            continue
        encontrada = _CLAUSULA.match(linha.strip())
        if encontrada:
            clausula_atual = encontrada.group(1).rstrip(".")
        marcos.append((len(acumulado), clausula_atual))
        acumulado += normalizada + " "
    indice = acumulado.find(alvo)
    if indice < 0:
        return None
    clausula: str | None = None
    for offset, numero in marcos:
        if offset > indice:
            break
        clausula = numero
    return clausula


def rotulo_clausula(evidencia: Evidencia, clausula: str | None) -> str:
    if clausula:
        return f"Edital, item {clausula}, p. {evidencia.pagina}"
    return f"Edital, p. {evidencia.pagina}"


def paginas_de(paginas: Iterable[Pagina]) -> list[int]:
    return [p.numero for p in paginas]
