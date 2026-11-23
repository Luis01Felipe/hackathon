"""Regras das restrições de valor que vão para o IDS.

Uma restrição por padrão (regex) é executada pelo validador do IDS contra cada valor do
modelo. Um padrão com quantificadores aninhados, como ``(a+)+``, pode levar tempo
exponencial (ReDoS) e travar a verificação. Esta checagem barra os casos comuns.
"""

import re

TAMANHO_MAXIMO_PADRAO = 200

# Grupo que contém um quantificador e é quantificado de novo: (a+)+, (\d*)*, (x{1,3})+...
_QUANTIFICADOR_ANINHADO = re.compile(r"\((?:[^()\\]|\\.)*[+*}](?:[^()\\]|\\.)*\)\s*[+*{]")


def problema_no_padrao(padrao: str) -> str | None:
    """Motivo para recusar o padrão, ou None se ele pode ir para o IDS."""
    if len(padrao) > TAMANHO_MAXIMO_PADRAO:
        return f"o padrão passa de {TAMANHO_MAXIMO_PADRAO} caracteres."
    try:
        re.compile(padrao)
    except re.error:
        return "o padrão não é uma expressão regular válida."
    if _QUANTIFICADOR_ANINHADO.search(padrao):
        return "o padrão tem quantificadores aninhados, que podem travar a validação."
    return None
