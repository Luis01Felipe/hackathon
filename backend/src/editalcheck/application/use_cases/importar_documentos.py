"""Caso de uso: importar edital (PDF) e modelo (IFC) e segmentar tópicos."""

import uuid
from dataclasses import replace

from editalcheck.application.errors import EntradaInvalidaError
from editalcheck.application.observability import agora, etapa, logger
from editalcheck.application.ports import (
    EditalReader,
    IfcModelReader,
    ProjectRepository,
    TopicClassifier,
)
from editalcheck.domain import topics
from editalcheck.domain.findings import SCHEMAS_SUPORTADOS
from editalcheck.domain.models import Projeto, Topico


class ImportarDocumentos:
    def __init__(
        self,
        edital_reader: EditalReader,
        ifc_reader: IfcModelReader,
        repositorio: ProjectRepository,
        classificador: TopicClassifier,
        classificador_reserva: TopicClassifier,
    ) -> None:
        self._edital = edital_reader
        self._ifc = ifc_reader
        self._repo = repositorio
        self._classificador = classificador
        self._reserva = classificador_reserva

    def executar(self, pdf: bytes, nome_pdf: str, ifc: bytes, nome_ifc: str) -> Projeto:
        if not pdf.startswith(b"%PDF"):
            raise EntradaInvalidaError("O edital precisa ser um arquivo PDF.")
        if b"ISO-10303-21" not in ifc[:200]:
            raise EntradaInvalidaError("O modelo precisa ser um arquivo IFC (STEP, ISO 10303-21).")

        projeto_id = uuid.uuid4().hex[:10]
        caminho_pdf = self._repo.write_file(projeto_id, "edital.pdf", pdf)
        caminho_ifc = self._repo.write_file(projeto_id, "modelo.ifc", ifc)
        avisos: list[str] = []

        with etapa("importar.pdf", projeto=projeto_id) as extra:
            try:
                edital = replace(self._edital.read(caminho_pdf), arquivo=nome_pdf)
            except ValueError as erro:
                raise EntradaInvalidaError(str(erro)) from erro
            extra["paginas"] = len(edital.paginas)

        with etapa("importar.ifc", projeto=projeto_id) as extra:
            try:
                modelo = replace(self._ifc.load(caminho_ifc), arquivo=nome_ifc)
            except ValueError as erro:
                raise EntradaInvalidaError(str(erro)) from erro
            extra["schema"] = modelo.schema
            extra["elementos"] = modelo.total_elementos

        if modelo.schema.upper() not in SCHEMAS_SUPORTADOS:
            avisos.append(
                f"Schema {modelo.schema} não é suportado oficialmente (use IFC2X3 ou IFC4)."
            )
        if modelo.total_elementos == 0:
            avisos.append("O modelo IFC não tem elementos construtivos.")

        segmentados = topics.segmentar(edital)
        classificados, aviso = self._classificar(segmentados)
        if aviso:
            avisos.append(aviso)

        projeto = Projeto(
            id=projeto_id,
            criado_em=agora(),
            edital=edital,
            modelo=modelo,
            topicos=tuple(classificados),
            avisos=tuple(avisos),
        )
        self._repo.save(projeto)
        return projeto

    def _classificar(self, topicos_segmentados: list[Topico]) -> tuple[list[Topico], str | None]:
        with etapa("topicos.classificar", total=len(topicos_segmentados)):
            try:
                return self._classificador.classify(topicos_segmentados), None
            except Exception as erro:  # RNF-02: falha do LLM não derruba o fluxo
                logger.warning("Classificação de tópicos pelo LLM falhou: %s", erro)
                aviso = "LLM indisponível para nomear os tópicos: usando regras determinísticas."
                return self._reserva.classify(topicos_segmentados), aviso
