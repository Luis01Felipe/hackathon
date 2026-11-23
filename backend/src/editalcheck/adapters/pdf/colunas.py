"""Ordem de leitura de páginas com duas páginas impressas lado a lado (PyMuPDF).

Alguns editais são distribuídos com duas páginas impressas em cada folha do PDF.
Com ``sort=True`` o PyMuPDF ordena o texto por altura na folha inteira e mistura
as duas metades linha a linha ("4.1. ARQUITETURA" colado ao texto da outra
página). Aqui a folha vira duas colunas, lidas da esquerda para a direita.

A folha só é tratada como dupla quando está deitada, há texto dos dois lados do
meio e nenhuma linha cruza o meio. Páginas de uma coluna seguem como antes.
"""

import pymupdf

_FOLGA_MEIO = 2.0  # pontos: tolerância para linhas que encostam no meio


def _linhas(pagina: pymupdf.Page) -> list[pymupdf.Rect]:
    dados = pagina.get_text("dict")
    return [
        pymupdf.Rect(linha["bbox"])
        for bloco in dados["blocks"]
        if bloco.get("type") == 0
        for linha in bloco["lines"]
        if any(span["text"].strip() for span in linha["spans"])
    ]


def colunas(pagina: pymupdf.Page) -> tuple[pymupdf.Rect, ...]:
    """Regiões da página na ordem de leitura: as duas metades ou a página inteira."""
    folha = pagina.rect
    if pagina.rotation or folha.width <= folha.height:
        return (folha,)
    meio = (folha.x0 + folha.x1) / 2
    linhas = _linhas(pagina)
    esquerda = any(r.x1 <= meio + _FOLGA_MEIO for r in linhas)
    direita = any(r.x0 >= meio - _FOLGA_MEIO for r in linhas)
    cruza = any(r.x0 < meio - _FOLGA_MEIO and r.x1 > meio + _FOLGA_MEIO for r in linhas)
    if not (esquerda and direita) or cruza:
        return (folha,)
    return (
        pymupdf.Rect(folha.x0, folha.y0, meio, folha.y1),
        pymupdf.Rect(meio, folha.y0, folha.x1, folha.y1),
    )


def indice_da_coluna(regioes: tuple[pymupdf.Rect, ...], retangulo: pymupdf.Rect) -> int:
    """Coluna em que o retângulo começa (pelo centro horizontal)."""
    centro = (retangulo.x0 + retangulo.x1) / 2
    for indice, regiao in enumerate(regioes):
        if centro < regiao.x1:
            return indice
    return len(regioes) - 1


def texto_em_ordem(pagina: pymupdf.Page) -> str:
    """Texto da página, coluna por coluna."""
    regioes = colunas(pagina)
    if len(regioes) == 1:
        return pagina.get_text("text", sort=True)
    return "\n".join(pagina.get_text("text", clip=regiao, sort=True) for regiao in regioes)
