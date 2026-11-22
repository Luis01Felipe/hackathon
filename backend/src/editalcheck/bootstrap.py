"""Raiz de composição: liga portas a adaptadores conforme a configuração."""

import logging
from dataclasses import dataclass

from editalcheck.adapters.bcf.bcf_writer import BcfClientWriter
from editalcheck.adapters.bsdd.http_client import BsddHttpClient
from editalcheck.adapters.export.xlsx_writer import XlsxEirExporter
from editalcheck.adapters.ids.ifctester_builder import IfcTesterIdsBuilder
from editalcheck.adapters.ids.ifctester_validator import IfcTesterValidator
from editalcheck.adapters.ifc.ifcopenshell_model import IfcOpenShellModelReader
from editalcheck.adapters.pdf.pymupdf_reader import PyMuPdfEditalReader
from editalcheck.adapters.report.html_writer import JinjaHtmlReportWriter
from editalcheck.adapters.resources import (
    carregar_checklist,
    carregar_termos_vagos,
    carregar_vocabulario,
)
from editalcheck.adapters.rules.analyzer import (
    RulesEditalAnalyzer,
    RulesTopicClassifier,
    TemplateRecommendationWriter,
)
from editalcheck.adapters.rules.extractor import RulesRequirementExtractor
from editalcheck.adapters.storage.fs_repository import FsProjectRepository
from editalcheck.application.use_cases.executar_verificacao import ExecutarVerificacao
from editalcheck.application.use_cases.gerar_eir import GerarEir, ValidadorRequisitos
from editalcheck.application.use_cases.gerar_ids import GerarIds
from editalcheck.application.use_cases.gerar_relatorio import GerarRelatorio
from editalcheck.application.use_cases.importar_documentos import ImportarDocumentos
from editalcheck.application.use_cases.revisar_eir import RevisarEir
from editalcheck.config import Settings
from editalcheck.domain.severity import ConfigSeveridade


@dataclass
class Container:
    settings: Settings
    repositorio: FsProjectRepository
    importar: ImportarDocumentos
    gerar_eir: GerarEir
    revisar_eir: RevisarEir
    gerar_ids: GerarIds
    verificar: ExecutarVerificacao
    exportador_eir: XlsxEirExporter


def configurar_logs(nivel: str) -> None:
    logging.basicConfig(level=nivel, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    for ruidoso in ("httpx", "httpx2", "httpcore", "google_genai", "urllib3"):
        logging.getLogger(ruidoso).setLevel(logging.WARNING)


def construir(settings: Settings) -> Container:
    recursos = settings.pasta_recursos
    termos_vagos = carregar_termos_vagos(recursos / "termos_vagos.yaml")
    itens_checklist, regras_checklist = carregar_checklist(recursos / "checklist_eir_minimo.yaml")
    vocabulario = carregar_vocabulario(recursos / "vocabulario_pt.yaml")

    repositorio = FsProjectRepository(settings.pasta_dados)
    ifc_reader = IfcOpenShellModelReader()
    dicionario = (
        BsddHttpClient(settings.pasta_cache / "bsdd", timeout_s=settings.bsdd_timeout_s)
        if settings.bsdd_ativo
        else None
    )

    extrator_regras = RulesRequirementExtractor(vocabulario)
    analisador_regras = RulesEditalAnalyzer(regras_checklist)
    classificador_regras = RulesTopicClassifier()
    recomendador_regras = TemplateRecommendationWriter()

    extrator, analisador, classificador, recomendador = (
        extrator_regras,
        analisador_regras,
        classificador_regras,
        recomendador_regras,
    )
    if settings.llm_ativo and settings.gemini_api_key:
        from editalcheck.adapters.llm.adapters import (
            LlmEditalAnalyzer,
            LlmRecommendationWriter,
            LlmRequirementExtractor,
            LlmTopicClassifier,
        )
        from editalcheck.adapters.llm.gemini_client import GeminiJsonClient
        from editalcheck.adapters.llm.structured import PromptLoader, StructuredLlm

        cliente = GeminiJsonClient(
            settings.gemini_api_key, settings.gemini_model, timeout_s=settings.llm_timeout_s
        )
        llm = StructuredLlm(
            cliente, PromptLoader(settings.pasta_prompts), settings.pasta_cache / "llm"
        )
        extrator = LlmRequirementExtractor(llm)
        analisador = LlmEditalAnalyzer(llm)
        classificador = LlmTopicClassifier(llm)
        recomendador = LlmRecommendationWriter(llm)

    validador = ValidadorRequisitos(ifc_reader, dicionario)
    gerar_ids = GerarIds(repositorio, IfcTesterIdsBuilder())
    gerar_relatorio = GerarRelatorio(
        repositorio,
        recomendador,
        recomendador_regras,
        JinjaHtmlReportWriter(),
        BcfClientWriter(),
        itens_checklist,
        settings.modo_ia,
        paralelismo=settings.llm_paralelismo,
    )
    return Container(
        settings=settings,
        repositorio=repositorio,
        importar=ImportarDocumentos(
            PyMuPdfEditalReader(), ifc_reader, repositorio, classificador, classificador_regras
        ),
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
        ),
        exportador_eir=XlsxEirExporter(),
    )
