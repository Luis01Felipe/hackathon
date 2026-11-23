"""Portas da aplicação (contratos implementados pelos adaptadores)."""

from collections.abc import Sequence
from typing import Protocol

from editalcheck.domain.models import (
    AmbiguidadeConfirmada,
    Apontamento,
    CaixaEnvolvente,
    ContextoVocabulario,
    Contradicao,
    DecisaoApontamento,
    Edital,
    Eir,
    ItemChecklist,
    LicaoAprendida,
    ModeloResumo,
    Projeto,
    PropriedadeOficial,
    Recomendacao,
    Referencia,
    Relatorio,
    Requisito,
    ResultadoChecklist,
    ResultadoEspecificacao,
    TermoDicionario,
    Topico,
    TrechoVago,
    Verificacao,
    VerificacaoLicao,
)


class EditalReader(Protocol):
    """Lê um documento (PDF ou texto) em memória e devolve o texto por página."""

    def read(self, conteudo: bytes, nome: str) -> Edital: ...


class IfcModelReader(Protocol):
    def load(self, conteudo: bytes, nome: str) -> ModeloResumo: ...

    def official_properties(self, schema: str, ifc_class: str) -> list[PropriedadeOficial]: ...

    def canonical_class(self, schema: str, ifc_class: str) -> str | None:
        """Nome canônico da declaração no schema (ex.: "IFCDOOR" → "IfcDoor") ou None."""
        ...

    def is_entity(self, schema: str, ifc_class: str) -> bool:
        """True se o nome é uma entidade (classe) do schema, e não um tipo de dado."""
        ...


class ElementGeometry(Protocol):
    def boxes(self, conteudo_ifc: bytes, global_ids: Sequence[str]) -> dict[str, CaixaEnvolvente]:
        """Caixa envolvente de cada elemento em coordenadas do projeto (metros)."""
        ...


class TopicClassifier(Protocol):
    """RF-11: nomeia/resume tópicos e marca os relevantes para BIM."""

    def classify(self, topicos: Sequence[Topico]) -> list[Topico]: ...


class RequirementExtractor(Protocol):
    def extract(self, topico: Topico, contexto: ContextoVocabulario) -> list[Requisito]: ...


class LessonExtractor(Protocol):
    """Lê as lições aprendidas de um documento (texto por página)."""

    def extract(self, documento: Edital) -> list[LicaoAprendida]: ...


class LessonChecker(Protocol):
    """Procura cada lição no edital (a evidência é conferida depois, por código)."""

    def check(
        self, licoes: Sequence[LicaoAprendida], edital: Edital, topicos: Sequence[Topico]
    ) -> list[VerificacaoLicao]: ...


class ReferenceContext(Protocol):
    """Documentos de referência autorizados, enviados ao LLM só como dado (G3)."""

    def select(self, texto: str) -> list[tuple[str, str]]:
        """Trechos (documento, texto) mais relevantes para o texto, dentro do orçamento."""
        ...


class EditalAnalyzer(Protocol):
    def confirm_vagueness(
        self, candidatos: Sequence[TrechoVago]
    ) -> list[AmbiguidadeConfirmada]: ...

    def evaluate_checklist(
        self, edital: Edital, topicos: Sequence[Topico], itens: Sequence[ItemChecklist]
    ) -> list[ResultadoChecklist]: ...

    def find_contradictions(self, topicos: Sequence[Topico]) -> list[Contradicao]: ...


class DictionaryLookup(Protocol):
    def search(self, termo: str, ifc_class: str | None = None) -> list[TermoDicionario]: ...


class IdsBuilder(Protocol):
    def build(
        self,
        eir: Eir,
        versao_ifc: str,
        titulo: str,
        marco: str | None = None,
        requisitos: Sequence[Requisito] | None = None,
    ) -> bytes: ...

    def check(self, ids_xml: bytes) -> list[str]:
        """S6: recarrega o IDS e devolve a lista de erros (vazia se válido)."""
        ...


class IfcValidator(Protocol):
    def validate(self, ids_xml: bytes, conteudo_ifc: bytes) -> list[ResultadoEspecificacao]: ...


class RecommendationWriter(Protocol):
    def write(
        self, apontamento: Apontamento, referencias: Sequence[Referencia]
    ) -> Recomendacao: ...


class ReportWriter(Protocol):
    def write_html(self, relatorio: Relatorio) -> str: ...


class BcfWriter(Protocol):
    def write(self, relatorio: Relatorio, modelo: ModeloResumo) -> bytes: ...


class EirExporter(Protocol):
    def to_xlsx(self, eir: Eir, projeto: Projeto) -> bytes: ...


class EditalAnnotator(Protocol):
    """Cópia do edital com destaque e nota em cada trecho apontado (RF-151)."""

    def annotate(
        self,
        pdf: bytes,
        apontamentos: Sequence[Apontamento],
        decisoes: Sequence[DecisaoApontamento],
    ) -> bytes: ...


class ClarificationExporter(Protocol):
    """Matriz de esclarecimentos do edital (RF-152)."""

    def to_xlsx(self, relatorio: Relatorio) -> bytes: ...


class AuditLog(Protocol):
    """Log de auditoria SEM conteúdo de documento (RNF-12)."""

    def record(self, evento: str, **campos: object) -> None: ...


class ProjectRepository(Protocol):
    def save(self, projeto: Projeto) -> None: ...

    def get(self, projeto_id: str) -> Projeto | None: ...

    def delete(self, projeto_id: str) -> bool: ...

    def write_file(self, projeto_id: str, nome: str, conteudo: bytes) -> None: ...

    def read_file(self, projeto_id: str, nome: str) -> bytes | None: ...

    def save_verificacao(self, verificacao: Verificacao) -> None: ...

    def get_verificacao(self, verificacao_id: str) -> Verificacao | None: ...

    def save_relatorio(self, relatorio: Relatorio) -> None: ...

    def get_relatorio(self, verificacao_id: str) -> Relatorio | None: ...

    def write_relatorio_file(self, verificacao_id: str, nome: str, conteudo: bytes) -> None: ...

    def read_relatorio_file(self, verificacao_id: str, nome: str) -> bytes | None: ...
