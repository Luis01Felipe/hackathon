"""Schemas Pydantic da saída estruturada do LLM (salvaguarda S1)."""

from typing import Literal

from pydantic import BaseModel, Field


class EvidenciaLLM(BaseModel):
    pagina: int = Field(description="Número da página indicado pelo marcador [p. N]")
    trecho: str = Field(description="Cópia literal de uma frase do edital, sem reticências")


class RestricaoLLM(BaseModel):
    tipo: Literal["valor", "enumeracao", "padrao", "intervalo"]
    valores: list[str] = Field(default_factory=list)
    minimo: float | None = None
    maximo: float | None = None


class RequisitoLLM(BaseModel):
    descricao: str = Field(description="Requisito em uma frase, no imperativo")
    evidencia: EvidenciaLLM
    verificavel_por_ids: bool
    motivo_nao_verificavel: str | None = None
    ifc_class: str | None = Field(default=None, description="Classe IFC, ex.: IfcDoor")
    predefined_type: str | None = None
    faceta: Literal["property", "attribute", "classification", "material", "partOf"] | None = None
    pset: str | None = Field(
        default=None, description="Pset (property) ou sistema (classification)"
    )
    propriedade: str | None = Field(default=None, description="Propriedade ou atributo")
    tipo_dado: str | None = Field(default=None, description="Tipo IFC do valor, ex.: IfcLabel")
    restricao: RestricaoLLM | None = None
    cardinalidade: Literal["required", "optional", "prohibited"] = "required"


class ExtracaoLLM(BaseModel):
    requisitos: list[RequisitoLLM]


class TopicoClassificadoLLM(BaseModel):
    id: str
    titulo: str
    resumo: str
    relevante_bim: bool


class ClassificacaoTopicosLLM(BaseModel):
    topicos: list[TopicoClassificadoLLM]


class AmbiguidadeLLM(BaseModel):
    indice: int
    ambiguo: bool
    justificativa: str
    redacao_sugerida: str = ""


class AmbiguidadesLLM(BaseModel):
    itens: list[AmbiguidadeLLM]


class ItemChecklistLLM(BaseModel):
    item_id: str
    status: Literal["presente", "parcial", "ausente"]
    evidencia: EvidenciaLLM | None = None
    justificativa: str


class ChecklistLLM(BaseModel):
    itens: list[ItemChecklistLLM]


class ContradicaoLLM(BaseModel):
    evidencia_a: EvidenciaLLM
    evidencia_b: EvidenciaLLM
    explicacao: str


class ContradicoesLLM(BaseModel):
    contradicoes: list[ContradicaoLLM]


class RecomendacaoLLM(BaseModel):
    como_agir: str = Field(description="Até 3 frases, no imperativo")
    por_que: str = Field(description="Até 3 frases, citando só referências da lista")
    referencias: list[str] = Field(
        default_factory=list, description="Rótulos copiados exatamente da lista fornecida"
    )
