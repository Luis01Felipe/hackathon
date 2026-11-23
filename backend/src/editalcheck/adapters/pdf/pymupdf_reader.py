"""Leitura do edital em PDF com PyMuPDF, texto por página (RF-01, RF-02, RF-03)."""

import logging

import pymupdf

from editalcheck.domain.models import Edital, Pagina

logger = logging.getLogger("editalcheck.pdf")
CARACTERES_MINIMOS_POR_PAGINA = 40
LIGADURAS = str.maketrans(
    {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st", "­": ""}
)


class PdfSemTextoError(ValueError):
    """O PDF não tem texto selecionável (provavelmente escaneado)."""


def paginas_do_pdf(conteudo: bytes) -> tuple[Pagina, ...]:
    """Texto por página de um PDF em memória (nada é gravado em disco)."""
    paginas: list[Pagina] = []
    try:
        with pymupdf.open(stream=conteudo, filetype="pdf") as documento:
            for indice, pagina in enumerate(documento, start=1):
                texto = pagina.get_text("text", sort=True).translate(LIGADURAS)
                paginas.append(Pagina(numero=indice, texto=texto))
    except (pymupdf.FileDataError, RuntimeError, ValueError) as erro:
        logger.warning("PDF ilegível: %s", erro)
        raise ValueError(
            "Não foi possível ler o PDF. Confira se o arquivo não está corrompido nem protegido por senha."
        ) from erro
    return tuple(paginas)


class PyMuPdfEditalReader:
    def read(self, conteudo: bytes, nome: str) -> Edital:
        paginas = paginas_do_pdf(conteudo)
        edital = Edital(arquivo=nome, paginas=paginas)
        if not paginas:
            raise PdfSemTextoError("O PDF não tem páginas.")
        media = edital.total_caracteres / len(paginas)
        if media < CARACTERES_MINIMOS_POR_PAGINA:
            raise PdfSemTextoError(
                "O PDF parece escaneado: não há texto selecionável suficiente. "
                "Envie um edital com texto (OCR está fora do escopo)."
            )
        return edital


class TextoOuPdfReader:
    """Lê documentos de apoio (lições aprendidas) em PDF ou texto simples (.txt, .md)."""

    def read(self, conteudo: bytes, nome: str) -> Edital:
        if conteudo.startswith(b"%PDF"):
            paginas = paginas_do_pdf(conteudo)
        else:
            paginas = _paginas_do_texto(conteudo)
        documento = Edital(arquivo=nome, paginas=paginas)
        if documento.total_caracteres < CARACTERES_MINIMOS_POR_PAGINA:
            raise PdfSemTextoError(
                f"O arquivo {nome} não tem texto legível. Envie um .txt ou um PDF com texto."
            )
        return documento


def _paginas_do_texto(conteudo: bytes) -> tuple[Pagina, ...]:
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            texto = conteudo.decode(codificacao)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = conteudo.decode("latin-1")
    if "\x00" in texto:
        raise PdfSemTextoError("O arquivo não é texto simples. Envie um .txt ou um PDF.")
    partes = texto.replace("\r\n", "\n").split("\f")
    return tuple(Pagina(numero=i, texto=parte) for i, parte in enumerate(partes, start=1))
