"""Caso de uso: importar edital (PDF), modelo (IFC, opcional) e lições aprendidas.

Tudo é lido em memória. No modo efêmero, nada é gravado em disco (RF-092).
Sem IFC, o projeto entra no modo "revisar edital" (RF-198): o contratante
revisa o edital antes de publicá-lo.
"""

import uuid
from collections.abc import Sequence
from dataclasses import replace

from editalcheck.application.consumo import em_projeto
from editalcheck.application.errors import EntradaInvalidaError
from editalcheck.application.observability import agora, etapa, logger
from editalcheck.application.ports import (
    AuditLog,
    EditalReader,
    IfcModelReader,
    ProjectRepository,
    TopicClassifier,
)
from editalcheck.application.use_cases.importar_licoes import ImportarLicoes, validar_arquivos
from editalcheck.domain import marcos, topics, versao_ifc
from editalcheck.domain.findings import SCHEMAS_SUPORTADOS
from editalcheck.domain.models import ModeloResumo, Projeto, Topico

ARQUIVO_EDITAL = "edital.pdf"
ARQUIVO_MODELO = "modelo.ifc"


class ImportarDocumentos:
    def __init__(
        self,
        edital_reader: EditalReader,
        ifc_reader: IfcModelReader,
        repositorio: ProjectRepository,
        classificador: TopicClassifier,
        classificador_reserva: TopicClassifier,
        importar_licoes: ImportarLicoes,
        auditoria: AuditLog,
    ) -> None:
        self._edital = edital_reader
        self._ifc = ifc_reader
        self._repo = repositorio
        self._classificador = classificador
        self._reserva = classificador_reserva
        self._licoes = importar_licoes
        self._auditoria = auditoria

    def executar(
        self,
        pdf: bytes,
        nome_pdf: str,
        ifc: bytes | None = None,
        nome_ifc: str | None = None,
        licoes: Sequence[tuple[bytes, str]] = (),
        schema_sem_modelo: str | None = None,
    ) -> Projeto:
        if not pdf.startswith(b"%PDF"):
            raise EntradaInvalidaError("O edital precisa ser um arquivo PDF.")
        if ifc is not None and b"ISO-10303-21" not in ifc[:200]:
            raise EntradaInvalidaError("O modelo precisa ser um arquivo IFC (STEP, ISO 10303-21).")
        validar_arquivos(licoes)

        # 128 bits: o id do projeto é o que dá acesso aos documentos dele.
        projeto_id = uuid.uuid4().hex
        with em_projeto(projeto_id):
            return self._importar(
                projeto_id, pdf, nome_pdf, ifc, nome_ifc, licoes, schema_sem_modelo
            )

    def _importar(
        self,
        projeto_id: str,
        pdf: bytes,
        nome_pdf: str,
        ifc: bytes | None,
        nome_ifc: str | None,
        licoes: Sequence[tuple[bytes, str]],
        schema_sem_modelo: str | None,
    ) -> Projeto:
        avisos: list[str] = []
        with etapa("importar.pdf", projeto=projeto_id) as extra:
            try:
                edital = self._edital.read(pdf, nome_pdf)
            except ValueError as erro:
                raise EntradaInvalidaError(str(erro)) from erro
            extra["paginas"] = len(edital.paginas)

        modelo = self._modelo(projeto_id, edital, ifc, nome_ifc, schema_sem_modelo, avisos)
        segmentados = topics.segmentar(edital)
        classificados, aviso = self._classificar(segmentados)
        classificados = topics.propagar_relevancia(classificados)
        if aviso:
            avisos.append(aviso)

        projeto = Projeto(
            id=projeto_id,
            criado_em=agora(),
            edital=edital,
            modelo=modelo,
            topicos=tuple(classificados),
            marcos=tuple(marcos.detectar(edital)),
        )
        self._repo.save(projeto)
        self._repo.write_file(projeto_id, ARQUIVO_EDITAL, pdf)
        if ifc is not None:
            self._repo.write_file(projeto_id, ARQUIVO_MODELO, ifc)
        if licoes:
            resultado = self._licoes.adicionar(projeto, licoes)
            avisos.extend(resultado.avisos)
        projeto.avisos = tuple(avisos)
        self._repo.save(projeto)
        self._auditoria.record(
            "projeto.importar",
            projeto=projeto_id,
            paginas=len(edital.paginas),
            bytes_edital=len(pdf),
            bytes_modelo=len(ifc) if ifc else 0,
            sem_modelo=modelo.sem_arquivo,
            documentos_licoes=len(licoes),
        )
        return projeto

    def _modelo(
        self,
        projeto_id: str,
        edital,
        ifc: bytes | None,
        nome_ifc: str | None,
        schema_sem_modelo: str | None,
        avisos: list[str],
    ) -> ModeloResumo:
        if ifc is None:
            exigida = versao_ifc.exigida(edital)
            schema = schema_sem_modelo or (exigida[0] if exigida else "IFC4")
            if schema not in versao_ifc.VERSOES_IDS:
                raise EntradaInvalidaError(
                    f"Versão IFC inválida: {schema} (use {', '.join(versao_ifc.VERSOES_IDS)})."
                )
            avisos.append(
                "Sem modelo IFC: só o edital será revisado. As análises de conformidade, "
                "cobertura e saúde do modelo não rodam."
            )
            return ModeloResumo.vazio(schema)
        with etapa("importar.ifc", projeto=projeto_id) as extra:
            try:
                modelo = self._ifc.load(ifc, nome_ifc or ARQUIVO_MODELO)
            except ValueError as erro:
                raise EntradaInvalidaError(str(erro)) from erro
            extra["schema"] = modelo.schema
            extra["elementos"] = modelo.total_elementos
        if modelo.schema.upper() not in SCHEMAS_SUPORTADOS:
            avisos.append(
                f"Schema {modelo.schema} não é suportado oficialmente (use IFC2X3, IFC4 ou IFC4X3)."
            )
        if modelo.total_elementos == 0:
            avisos.append("O modelo IFC não tem elementos construtivos.")
        return replace(modelo, arquivo=nome_ifc or modelo.arquivo)

    def _classificar(self, topicos_segmentados: list[Topico]) -> tuple[list[Topico], str | None]:
        with etapa("topicos.classificar", total=len(topicos_segmentados)):
            try:
                return self._classificador.classify(topicos_segmentados), None
            except Exception as erro:  # RNF-02: falha do LLM não derruba o fluxo
                logger.warning("Classificação de tópicos pelo LLM falhou: %s", erro)
                aviso = "LLM indisponível para nomear os tópicos: usando regras determinísticas."
                return self._reserva.classify(topicos_segmentados), aviso
