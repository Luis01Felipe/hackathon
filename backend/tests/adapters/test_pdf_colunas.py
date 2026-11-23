"""Folhas com duas páginas impressas lado a lado: leitura e grifo por coluna."""

import pymupdf

from editalcheck.adapters.pdf.localizador import PyMuPdfLocalizador
from editalcheck.adapters.pdf.pymupdf_reader import paginas_do_pdf
from editalcheck.domain import topics
from editalcheck.domain.models import Edital

LARGURA, ALTURA = 842.0, 595.0
ESQUERDA = (
    "4. ESTACOES",
    "4.1. ARQUITETURA",
    "As estacoes devem ter acessos amplos e bem sinalizados.",
    "Os mezaninos devem comportar o fluxo de pico previsto.",
)
DIREITA = (
    "As plataformas devem ter piso tatil em toda a extensao.",
    "4.2. BICICLETARIO",
    "Prever bicicletario coberto com vagas para cem bicicletas.",
)


def _pdf_duplo() -> bytes:
    documento = pymupdf.open()
    folha = documento.new_page(width=LARGURA, height=ALTURA)
    for coluna, linhas in enumerate((ESQUERDA, DIREITA)):
        for indice, linha in enumerate(linhas):
            folha.insert_text((40 + coluna * LARGURA / 2, 80 + indice * 14), linha, fontsize=9)
    return documento.tobytes()


def _pdf_simples() -> bytes:
    documento = pymupdf.open()
    folha = documento.new_page(width=ALTURA, height=LARGURA)
    for indice, linha in enumerate((*ESQUERDA, *DIREITA)):
        folha.insert_text((40, 80 + indice * 14), linha, fontsize=9)
    return documento.tobytes()


def _linhas(texto: str) -> list[str]:
    return [linha.strip() for linha in texto.splitlines() if linha.strip()]


def test_leitor_le_a_folha_dupla_coluna_por_coluna() -> None:
    [pagina] = paginas_do_pdf(_pdf_duplo())
    assert _linhas(pagina.texto) == [*ESQUERDA, *DIREITA]


def test_pagina_de_uma_coluna_segue_inalterada() -> None:
    [pagina] = paginas_do_pdf(_pdf_simples())
    assert _linhas(pagina.texto) == [*ESQUERDA, *DIREITA]


def test_faixa_do_topico_segue_as_colunas_e_para_no_proximo_titulo() -> None:
    pdf = _pdf_duplo()
    segmentados = topics.segmentar(Edital("e.pdf", paginas_do_pdf(pdf)))
    por_numero = {t.numero: t for t in segmentados}
    assert [t.numero for t in segmentados] == ["4", "4.1", "4.2"]

    faixas = PyMuPdfLocalizador().topicos(pdf, segmentados)
    arquitetura = faixas[por_numero["4.1"].id]
    assert len(arquitetura) == 2
    esquerda, direita = arquitetura
    assert esquerda.x1 < 0.5 < direita.x0  # uma faixa em cada metade, sem cruzar o meio
    [bicicletario] = faixas[por_numero["4.2"].id]
    assert bicicletario.x0 > 0.5
    assert direita.y1 <= bicicletario.y0 + 0.01  # 4.1 termina onde 4.2 começa
