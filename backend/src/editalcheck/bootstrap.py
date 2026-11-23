"""Raiz de composição: liga portas a adaptadores conforme a configuração."""

import logging
from dataclasses import dataclass

from editalcheck.adapters.audit.jsonl_log import AuditLogNulo, JsonLinesAuditLog
from editalcheck.adapters.bcf.bcf_writer import BcfClientWriter
from editalcheck.adapters.bsdd.http_client import BsddHttpClient
from editalcheck.adapters.contexto.referencias import ContextoReferencia
from editalcheck.adapters.export.xlsx_writer import XlsxClarificationExporter, XlsxEirExporter
from editalcheck.adapters.ids.ifctester_builder import IfcTesterIdsBuilder
from editalcheck.adapters.ids.ifctester_validator import IfcTesterValidator
from editalcheck.adapters.ifc import abrir
from editalcheck.adapters.ifc.geometria import IfcOpenShellGeometry
from editalcheck.adapters.ifc.ifcopenshell_model import IfcOpenShellModelReader
from editalcheck.adapters.pdf.annotator import PyMuPdfEditalAnnotator
from editalcheck.adapters.pdf.localizador import PyMuPdfLocalizador
from editalcheck.adapters.pdf.pymupdf_reader import PyMuPdfEditalReader, TextoOuPdfReader
from editalcheck.adapters.report.html_writer import JinjaHtmlReportWriter
from editalcheck.adapters.resources import (
    carregar_checklist,
    carregar_tempo_manual,
    carregar_termos_vagos,
    carregar_vocabulario,
)
from editalcheck.adapters.rules.analyzer import (
    RulesEditalAnalyzer,
    RulesTopicClassifier,
    TemplateRecommendationWriter,
)
from editalcheck.adapters.rules.extractor import RulesRequirementExtractor
from editalcheck.adapters.rules.licoes import RulesLessonChecker, RulesLessonExtractor
from editalcheck.adapters.storage.fs_repository import FsProjectRepository
from editalcheck.adapters.storage.memory_repository import MemoryProjectRepository
from editalcheck.application.consumo import MedidorConsumo
from editalcheck.application.ports import AuditLog, ProjectRepository
from editalcheck.application.use_cases.excluir_projeto import ExcluirProjeto
from editalcheck.application.use_cases.executar_verificacao import ExecutarVerificacao
from editalcheck.application.use_cases.gerar_eir import GerarEir, ValidadorRequisitos
from editalcheck.application.use_cases.gerar_ids import GerarIds
from editalcheck.application.use_cases.gerar_relatorio import (
    DecidirApontamento,
    ExportarEdital,
    GerarRelatorio,
    PrecosLlm,
)
from editalcheck.application.use_cases.importar_documentos import (
    ARQUIVO_MODELO,
    ImportarDocumentos,
)
from editalcheck.application.use_cases.importar_licoes import ImportarLicoes
from editalcheck.application.use_cases.localizar_no_edital import LocalizarNoEdital
from editalcheck.application.use_cases.revisar_eir import RevisarEir
from editalcheck.config import Settings
from editalcheck.domain.severity import ConfigSeveridade


@dataclass
class Container:
    settings: Settings
    repositorio: ProjectRepository
    medidor: MedidorConsumo
    importar: ImportarDocumentos
    importar_licoes: ImportarLicoes
    gerar_eir: GerarEir
    revisar_eir: RevisarEir
    gerar_ids: GerarIds
    verificar: ExecutarVerificacao
    decidir: DecidirApontamento
    exportar_edital: ExportarEdital
    localizar: LocalizarNoEdital
    excluir: ExcluirProjeto
    exportador_eir: XlsxEirExporter
    documentos_contexto: tuple[str, ...]


def configurar_logs(nivel: str) -> None:
    logging.basicConfig(level=nivel, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for ruidoso in ("httpx", "httpx2", "httpcore", "google_genai", "urllib3"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def _repositorio(settings: Settings, medidor: MedidorConsumo) -> ProjectRepository:
    if settings.modo_dados == "persistente":
        return FsProjectRepository(settings.pasta_dados)

    def ao_expirar(projeto_id: str, arquivos: dict[str, bytes]) -> None:
        modelo = arquivos.get(ARQUIVO_MODELO)
        if modelo is not None:
            abrir.esquecer(modelo)
        medidor.esquecer(projeto_id)

    return MemoryProjectRepository(ttl_s=settings.ttl_min * 60, ao_expirar=ao_expirar)


def _auditoria(settings: Settings) -> AuditLog:
    if settings.arquivo_auditoria is None:
        return AuditLogNulo()
    return JsonLinesAuditLog(settings.arquivo_auditoria)


def construir(settings: Settings) -> Container:
    recursos = settings.pasta_recursos
    termos_vagos = carregar_termos_vagos(recursos / "termos_vagos.yaml")
    itens_checklist, regras_checklist = carregar_checklist(recursos / "checklist_eir_minimo.yaml")
    vocabulario = carregar_vocabulario(recursos / "vocabulario_pt.yaml")

    medidor = MedidorConsumo()
    localizador = PyMuPdfLocalizador()
    repositorio = _repositorio(settings, medidor)
    auditoria = _auditoria(settings)
    ifc_reader = IfcOpenShellModelReader()
    dicionario = (
        BsddHttpClient(settings.pasta_cache / "bsdd", timeout_s=settings.bsdd_timeout_s)
        if settings.bsdd_ativo
        else None
    )
    referencias = ContextoReferencia(settings.pasta_contexto) if settings.pasta_contexto else None

    extrator_regras = RulesRequirementExtractor(vocabulario)
    analisador_regras = RulesEditalAnalyzer(regras_checklist)
    classificador_regras = RulesTopicClassifier()
    recomendador_regras = TemplateRecommendationWriter()
    licoes_regras = RulesLessonExtractor()
    verificador_licoes_regras = RulesLessonChecker()

    extrator, analisador, classificador, recomendador = (
        extrator_regras,
        analisador_regras,
        classificador_regras,
        recomendador_regras,
    )
    extrator_licoes, verificador_licoes = licoes_regras, verificador_licoes_regras
    if settings.llm_ativo and settings.gemini_api_key:
        from editalcheck.adapters.llm.adapters import (
            LlmEditalAnalyzer,
            LlmLessonChecker,
            LlmLessonExtractor,
            LlmRecommendationWriter,
            LlmRequirementExtractor,
            LlmTopicClassifier,
        )
        from editalcheck.adapters.llm.gemini_client import GeminiJsonClient
        from editalcheck.adapters.llm.structured import PromptLoader, StructuredLlm

        cliente = GeminiJsonClient(
            settings.gemini_api_key, settings.gemini_model, timeout_s=settings.llm_timeout_s
        )
        # RF-093: no modo efêmero, as respostas do LLM (com trechos do edital) não vão a disco.
        cache_llm = settings.pasta_cache / "llm" if settings.modo_dados == "persistente" else None
        llm = StructuredLlm(cliente, PromptLoader(settings.pasta_prompts), cache_llm, medidor)
        extrator = LlmRequirementExtractor(llm, referencias)
        analisador = LlmEditalAnalyzer(llm)
        classificador = LlmTopicClassifier(llm)
        recomendador = LlmRecommendationWriter(llm)
        extrator_licoes = LlmLessonExtractor(llm)
        verificador_licoes = LlmLessonChecker(llm)

    validador = ValidadorRequisitos(ifc_reader, dicionario)
    gerar_ids = GerarIds(repositorio, IfcTesterIdsBuilder(), auditoria)
    gerar_relatorio = GerarRelatorio(
        repositorio,
        recomendador,
        recomendador_regras,
        JinjaHtmlReportWriter(),
        BcfClientWriter(),
        IfcOpenShellGeometry(),
        itens_checklist,
        settings.modo_ia,
        medidor,
        PrecosLlm(
            settings.preco_entrada_usd_mtok, settings.preco_saida_usd_mtok, settings.fonte_preco
        ),
        carregar_tempo_manual(recursos / "referencia_tempo_manual.yaml"),
        referencias.documentos if referencias else (),
        paralelismo=settings.llm_paralelismo,
    )
    importar_licoes = ImportarLicoes(
        repositorio, TextoOuPdfReader(), extrator_licoes, licoes_regras, auditoria
    )
    return Container(
        settings=settings,
        repositorio=repositorio,
        medidor=medidor,
        importar=ImportarDocumentos(
            PyMuPdfEditalReader(),
            ifc_reader,
            repositorio,
            classificador,
            classificador_regras,
            importar_licoes,
            auditoria,
        ),
        importar_licoes=importar_licoes,
        gerar_eir=GerarEir(
            repositorio,
            validador,
            extrator,
            extrator_regras,
            dicionario,
            vocabulario.classes,
            vocabulario.classes_en,
            paralelismo=settings.llm_paralelismo,
        ),
        revisar_eir=RevisarEir(repositorio, validador, vocabulario.classes),
        gerar_ids=gerar_ids,
        verificar=ExecutarVerificacao(
            repositorio,
            ifc_reader,
            IfcTesterValidator(),
            analisador,
            analisador_regras,
            gerar_ids,
            gerar_relatorio,
            termos_vagos,
            itens_checklist,
            ConfigSeveridade(),
            verificador_licoes,
            verificador_licoes_regras,
            auditoria,
            IfcOpenShellGeometry(),
        ),
        decidir=DecidirApontamento(repositorio, gerar_relatorio, auditoria),
        exportar_edital=ExportarEdital(
            repositorio, PyMuPdfEditalAnnotator(), XlsxClarificationExporter()
        ),
        localizar=LocalizarNoEdital(repositorio, localizador),
        excluir=ExcluirProjeto(repositorio, medidor, auditoria, abrir.esquecer),
        exportador_eir=XlsxEirExporter(),
        documentos_contexto=referencias.documentos if referencias else (),
    )
