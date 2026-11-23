"""PDF anotado com muitos apontamentos: rápido, pequeno e com cache por decisões."""

import pymupdf

from editalcheck.adapters.export.xlsx_writer import XlsxClarificationExporter
from editalcheck.adapters.pdf.annotator import PyMuPdfEditalAnnotator
from editalcheck.application.use_cases.gerar_relatorio import ExportarEdital
from editalcheck.bootstrap import Container
from editalcheck.domain.models import (
    Apontamento,
    Destinatario,
    Evidencia,
    Referencia,
    Severidade,
    TipoApontamento,
)
from tests.integration.test_v2 import _rodar

PAGINAS = 30
APONTAMENTOS = 300


def _edital() -> bytes:
    documento = pymupdf.open()
    for p in range(PAGINAS):
        documento.new_page().insert_htmlbox(
            pymupdf.Rect(50, 50, 545, 800),
            "".join(
                f"<p>{p + 1}.{i} A contratada deverá apresentar o item {i} da planilha {p} "
                f"no prazo de {i + 5} dias, conforme o cronograma.</p>"
                for i in range(1, 11)
            ),
        )
    documento.subset_fonts()
    return documento.tobytes(garbage=3, deflate=True)


def _apontamento(k: int) -> Apontamento:
    pagina, item = k % PAGINAS, k % 10 + 1
    return Apontamento(
        id=f"APT-{k:04d}",
        tipo=TipoApontamento.AMBIGUIDADE,
        severidade=Severidade.MEDIA,
        destinatario=Destinatario.CONTRATANTE,
        titulo=f"Termo vago <{k}> & cia",
        analise="B",
        evidencias_edital=(
            Evidencia(pagina + 1, f"{pagina + 1}.{item} A contratada deverá apresentar o item"),
        ),
        como_agir="Reescreva a cláusula com critério mensurável.",
        referencias=(
            Referencia("bsdd", "bSDD: FireRating", "https://identifier.buildingsmart.org/x"),
            Referencia("x", "Endereço inseguro", "javascript:alert(1)"),
        ),
    )


def test_muitos_apontamentos_geram_pdf_pequeno_com_links() -> None:
    edital = _edital()
    saida = PyMuPdfEditalAnnotator().annotate(
        edital, [_apontamento(k) for k in range(APONTAMENTOS)], ()
    )
    # Antes, cada bloco do sumário embutia a fonte de novo (centenas de MB com milhares).
    assert len(saida) < len(edital) + 2_000_000
    with pymupdf.open(stream=saida, filetype="pdf") as documento:
        sumario = documento.page_count - PAGINAS
        assert sumario >= 1
        links = [link for i in range(sumario) for link in documento[i].get_links()]
        internos = [link for link in links if link["kind"] == pymupdf.LINK_GOTO]
        uris = {link["uri"] for link in links if link["kind"] == pymupdf.LINK_URI}
        assert len(internos) == APONTAMENTOS
        assert all(link["page"] >= sumario for link in internos)
        assert uris == {"https://identifier.buildingsmart.org/x"}
        assert "Termo vago <0> & cia" in documento[0].get_text()


class _AnotadorContado:
    def __init__(self) -> None:
        self.chamadas = 0

    def annotate(self, pdf, apontamentos, decisoes) -> bytes:
        self.chamadas += 1
        return pdf


def test_edital_anotado_em_cache_ate_mudar_uma_decisao(container: Container) -> None:
    _, verificacao, relatorio = _rodar(container)
    anotador = _AnotadorContado()
    exportar = ExportarEdital(container.repositorio, anotador, XlsxClarificationExporter())
    exportar.anotado(verificacao.id)
    exportar.anotado(verificacao.id)
    assert anotador.chamadas == 1
    container.decidir.executar(verificacao.id, relatorio.apontamentos[0].id, "aceito")
    exportar.anotado(verificacao.id)
    assert anotador.chamadas == 2
