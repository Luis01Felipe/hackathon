"""Portas da aplicação (contratos implementados pelos adaptadores)."""

from collections.abc import Sequence
from typing import Protocol

from editalcheck.domain.models import (
    AmbiguidadeConfirmada,
    Apontamento,
    ContextoVocabulario,
    Contradicao,
    Edital,
    Eir,
    ItemChecklist,
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
)


class EditalReader(Protocol):
    def read(self, pdf_path: str) -> Edital: ...


class IfcModelReader(Protocol):
    def load(self, ifc_path: str) -> ModeloResumo: ...

    def official_properties(self, schema: str, ifc_class: str) -> list[PropriedadeOficial]: ...

    def canonical_class(self, schema: str, ifc_class: str) -> str | None:
        """Nome canônico da declaração no schema (ex.: "IFCDOOR" → "IfcDoor") ou None."""
        ...

    def is_entity(self, schema: str, ifc_class: str) -> bool:
        """True se o nome é uma entidade (classe) do schema, e não um tipo de dado."""
        ...


class TopicClassifier(Protocol):
    """RF-11: nomeia/resume tópicos e marca os relevantes para BIM."""

    def classify(self, topicos: Sequence[Topico]) -> list[Topico]: ...


class RequirementExtractor(Protocol):
    def extract(self, topico: Topico, contexto: ContextoVocabulario) -> list[Requisito]: ...


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
    def build(self, eir: Eir, schema: str, titulo: str) -> bytes: ...

    def check(self, ids_xml: bytes) -> list[str]:
        """S6: recarrega o IDS e devolve a lista de erros (vazia se válido)."""
        ...


class IfcValidator(Protocol):
    def validate(self, ids_xml: bytes, ifc_path: str) -> list[ResultadoEspecificacao]: ...


class RecommendationWriter(Protocol):
    def write(
        self, apontamento: Apontamento, referencias: Sequence[Referencia]
    ) -> Recomendacao: ...


class ReportWriter(Protocol):
    def write_html(self, relatorio: Relatorio) -> str: ...


class BcfWriter(Protocol):
    def write(self, relatorio: Relatorio, ifc_path: str) -> bytes: ...


class EirExporter(Protocol):
    def to_xlsx(self, eir: Eir, projeto: Projeto) -> bytes: ...


class ProjectRepository(Protocol):
    def save(self, projeto: Projeto) -> None: ...

    def get(self, projeto_id: str) -> Projeto | None: ...

    def file_path(self, projeto_id: str, nome: str) -> str: ...

    def write_file(self, projeto_id: str, nome: str, conteudo: bytes) -> str: ...

    def read_file(self, projeto_id: str, nome: str) -> bytes | None: ...

    def save_verificacao(self, verificacao: Verificacao) -> None: ...

    def get_verificacao(self, verificacao_id: str) -> Verificacao | None: ...

    def save_relatorio(self, relatorio: Relatorio, html: str, bcf: bytes | None) -> None: ...

    def get_relatorio(self, verificacao_id: str) -> Relatorio | None: ...

    def relatorio_file(self, verificacao_id: str, nome: str) -> str | None: ...
