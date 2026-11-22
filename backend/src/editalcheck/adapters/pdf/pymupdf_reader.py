"""Leitura do edital em PDF com PyMuPDF, texto por página (RF-01, RF-02, RF-03)."""

from pathlib import Path

import pymupdf

from editalcheck.domain.models import Edital, Pagina

CARACTERES_MINIMOS_POR_PAGINA = 40
LIGADURAS = str.maketrans(
    {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st", "­": ""}
)


class PdfSemTextoError(ValueError):
    """O PDF não tem texto selecionável (provavelmente escaneado)."""


class PyMuPdfEditalReader:
    def read(self, pdf_path: str) -> Edital:
        paginas: list[Pagina] = []
        with pymupdf.open(pdf_path) as documento:
            for indice, pagina in enumerate(documento, start=1):
                texto = pagina.get_text("text", sort=True).translate(LIGADURAS)
                paginas.append(Pagina(numero=indice, texto=texto))
        edital = Edital(arquivo=Path(pdf_path).name, paginas=tuple(paginas))
        if not paginas:
            raise PdfSemTextoError("O PDF não tem páginas.")
        media = edital.total_caracteres / len(paginas)
        if media < CARACTERES_MINIMOS_POR_PAGINA:
            raise PdfSemTextoError(
                "O PDF parece escaneado: não há texto selecionável suficiente. "
                "Envie um edital com texto (OCR está fora do escopo)."
            )
        return edital
