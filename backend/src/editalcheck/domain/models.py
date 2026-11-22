"""Entidades e objetos de valor do domínio do EditalCheck.

O domínio não importa framework web, IfcOpenShell nem SDK de LLM.
Objetos de valor são imutáveis (frozen). Os agregados Projeto e Verificacao
são mutáveis para simplificar a orquestração dos casos de uso.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class StatusRequisito(StrEnum):
    PROPOSTO = "proposto"
    APROVADO = "aprovado"
    EDITADO = "editado"
    REJEITADO = "rejeitado"


class TipoFaceta(StrEnum):
    """Espelha as facetas de requisito do IDS 1.0."""

    PROPRIEDADE = "property"
    ATRIBUTO = "attribute"
    CLASSIFICACAO = "classification"
    MATERIAL = "material"
    PARTE_DE = "partOf"


class OrigemVocabulario(StrEnum):
    PSET_OFICIAL = "pset_oficial"
    BSDD = "bsdd"
    CUSTOMIZADO = "customizado"


class Cardinalidade(StrEnum):
    OBRIGATORIA = "required"
    OPCIONAL = "optional"
    PROIBIDA = "prohibited"


class TipoRestricao(StrEnum):
    VALOR = "valor"
    ENUMERACAO = "enumeracao"
    PADRAO = "padrao"
    INTERVALO = "intervalo"


class TipoApontamento(StrEnum):
    NAO_CONFORMIDADE = "nao_conformidade"
    AMBIGUIDADE = "ambiguidade"
    NAO_VERIFICAVEL = "nao_verificavel"
    ITEM_AUSENTE = "item_ausente"
    CONTRADICAO = "contradicao"
    LACUNA_COBERTURA = "lacuna_cobertura"
    QUALIDADE_MODELO = "qualidade_modelo"


class Destinatario(StrEnum):
    PROJETISTA = "projetista"
    CONTRATANTE = "contratante"


class Severidade(StrEnum):
    ALTA = "alta"
    MEDIA = "media"
    BAIXA = "baixa"


class StatusChecklist(StrEnum):
    PRESENTE = "presente"
    PARCIAL = "parcial"
    AUSENTE = "ausente"


class EstadoElemento(StrEnum):
    CONFORME = "conforme"
    NAO_CONFORME = "nao_conforme"


# --------------------------------------------------------------------------- edital


@dataclass(frozen=True)
class Pagina:
    numero: int
    texto: str


@dataclass(frozen=True)
class Edital:
    arquivo: str
    paginas: tuple[Pagina, ...]

    def pagina(self, numero: int) -> Pagina | None:
        for pagina in self.paginas:
            if pagina.numero == numero:
                return pagina
        return None

    @property
    def total_caracteres(self) -> int:
        return sum(len(p.texto.strip()) for p in self.paginas)


@dataclass(frozen=True)
class Topico:
    id: str  # TOP-01
    numero: str  # "5.1"
    titulo: str
    nivel: int
    pagina_inicio: int
    pagina_fim: int
    texto: str  # texto com marcadores de página "[p. N]"
    relevante_bim: bool = False
    resumo: str | None = None


@dataclass(frozen=True)
class Evidencia:
    pagina: int
    trecho: str  # conferido literalmente contra o texto da página


# --------------------------------------------------------------------------- requisitos / EIR


@dataclass(frozen=True)
class Restricao:
    tipo: TipoRestricao
    valores: tuple[str, ...] = ()
    minimo: float | None = None
    maximo: float | None = None


@dataclass(frozen=True)
class Requisito:
    id: str  # REQ-001
    topico_id: str
    descricao: str
    evidencia: Evidencia
    verificavel_por_ids: bool
    motivo_nao_verificavel: str | None = None
    ifc_class: str | None = None  # ex.: IfcDoor
    predefined_type: str | None = None
    faceta: TipoFaceta | None = None
    pset: str | None = None  # ex.: Pset_DoorCommon (ou sistema de classificação)
    propriedade: str | None = None  # ex.: FireRating (ou nome do atributo)
    tipo_dado: str | None = None  # ex.: IfcLabel
    restricao: Restricao | None = None
    cardinalidade: Cardinalidade = Cardinalidade.OBRIGATORIA
    origem_vocabulario: OrigemVocabulario | None = None
    bsdd_uri: str | None = None
    status: StatusRequisito = StatusRequisito.PROPOSTO
    sugerido_por_lacuna: bool = False
    clausula: str | None = None  # ex.: "5.1.1"
    gerado_por: str = "llm"  # llm | regras | usuario | lacuna
    avisos: tuple[str, ...] = ()

    @property
    def aprovado(self) -> bool:
        return self.status in (StatusRequisito.APROVADO, StatusRequisito.EDITADO)

    @property
    def entra_no_ids(self) -> bool:
        return self.aprovado and self.verificavel_por_ids


@dataclass(frozen=True)
class Eir:
    versao: int
    data: str  # ISO 8601
    topicos_selecionados: tuple[str, ...]
    requisitos: tuple[Requisito, ...] = ()
    aprovado_por: str | None = None

    def requisito(self, requisito_id: str) -> Requisito | None:
        for requisito in self.requisitos:
            if requisito.id == requisito_id:
                return requisito
        return None

    @property
    def requisitos_para_ids(self) -> tuple[Requisito, ...]:
        return tuple(r for r in self.requisitos if r.entra_no_ids)


# --------------------------------------------------------------------------- modelo IFC


@dataclass(frozen=True)
class ClasseModelo:
    nome: str  # ex.: IfcDoor
    contagem: int
    especificavel: bool
    supertipos: tuple[str, ...] = ()  # ancestrais no schema, do mais próximo ao mais distante


@dataclass(frozen=True)
class ElementoModelo:
    global_id: str
    step_id: int
    classe: str
    nome: str | None = None
    pavimento: str | None = None


@dataclass(frozen=True)
class SaudeModelo:
    schema: str
    total_elementos: int
    proxies: int
    sem_pavimento: tuple[str, ...] = ()  # GlobalIds
    guids_duplicados: tuple[str, ...] = ()
    espacos: int = 0

    @property
    def proporcao_proxies(self) -> float:
        if self.total_elementos == 0:
            return 0.0
        return self.proxies / self.total_elementos


@dataclass(frozen=True)
class ModeloResumo:
    arquivo: str
    schema: str
    classes: tuple[ClasseModelo, ...]
    elementos: tuple[ElementoModelo, ...]
    saude: SaudeModelo

    @property
    def total_elementos(self) -> int:
        return len(self.elementos)

    def classe(self, nome: str) -> ClasseModelo | None:
        for classe in self.classes:
            if classe.nome.lower() == nome.lower():
                return classe
        return None


@dataclass(frozen=True)
class PropriedadeOficial:
    pset: str
    nome: str
    tipo_dado: str | None = None
    descricao: str = ""
    valores_enumerados: tuple[str, ...] = ()


@dataclass(frozen=True)
class TermoDicionario:
    nome: str
    uri: str
    tipo: str  # "classe" | "propriedade"
    dicionario: str = ""
    descricao: str = ""


@dataclass(frozen=True)
class ContextoVocabulario:
    schema: str
    classes_modelo: tuple[ClasseModelo, ...]
    propriedades_oficiais: tuple[PropriedadeOficial, ...] = ()
    propriedades_por_classe: tuple[
        tuple[str, tuple[str, ...]], ...
    ] = ()  # (classe, (Pset.Prop,...))
    termos_bsdd: tuple[TermoDicionario, ...] = ()

    def propriedade_oficial(self, pset: str, nome: str) -> PropriedadeOficial | None:
        for prop in self.propriedades_oficiais:
            if prop.pset.lower() == pset.lower() and prop.nome.lower() == nome.lower():
                return prop
        return None

    def termo_bsdd(self, nome: str) -> TermoDicionario | None:
        for termo in self.termos_bsdd:
            if termo.nome.lower() == nome.lower():
                return termo
        return None


# --------------------------------------------------------------------------- análise B


@dataclass(frozen=True)
class TermoVago:
    termo: str
    categoria: str
    sugestao: str = ""


@dataclass(frozen=True)
class TrechoVago:
    pagina: int
    trecho: str  # sentença onde o termo aparece
    termo: str
    categoria: str
    topico_id: str | None = None
    clausula: str | None = None
    sugestao: str = ""


@dataclass(frozen=True)
class AmbiguidadeConfirmada:
    trecho: TrechoVago
    ambiguo: bool
    justificativa: str = ""
    redacao_sugerida: str = ""
    confirmado_por: str = "regras"  # llm | regras


@dataclass(frozen=True)
class ItemChecklist:
    id: str  # CHK-01
    item: str
    critico: bool
    descricao: str = ""
    palavras_chave: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoChecklist:
    item_id: str
    status: StatusChecklist
    evidencia: Evidencia | None = None
    justificativa: str = ""
    avaliado_por: str = "regras"  # llm | regras


@dataclass(frozen=True)
class Contradicao:
    evidencia_a: Evidencia
    evidencia_b: Evidencia
    explicacao: str


# --------------------------------------------------------------------------- análise A


@dataclass(frozen=True)
class FalhaElemento:
    global_id: str
    step_id: int
    classe: str
    nome: str | None
    motivo: str


@dataclass(frozen=True)
class ResultadoEspecificacao:
    nome_especificacao: str
    requisito_id: str | None
    status: bool
    aplicaveis: int
    aprovados: int
    falhas: tuple[FalhaElemento, ...] = ()
    elementos_aprovados: tuple[str, ...] = ()  # GlobalIds


# --------------------------------------------------------------------------- análise C


@dataclass(frozen=True)
class CoberturaClasse:
    classe: str
    contagem: int
    coberta: bool
    requisitos: tuple[str, ...] = ()


@dataclass(frozen=True)
class Cobertura:
    percentual: float | None
    classes: tuple[CoberturaClasse, ...]

    @property
    def classes_cobertas(self) -> int:
        return sum(1 for c in self.classes if c.coberta)

    @property
    def lacunas(self) -> tuple[CoberturaClasse, ...]:
        return tuple(c for c in self.classes if not c.coberta)


# --------------------------------------------------------------------------- apontamentos


@dataclass(frozen=True)
class Referencia:
    tipo: str  # "clausula_edital" | "pset_oficial" | "bsdd" | "checklist" | "modelo"
    rotulo: str  # ex.: "Edital, item 5.3.2, p. 14"
    uri: str | None = None


@dataclass(frozen=True)
class Recomendacao:
    como_agir: str
    por_que: str
    referencias: tuple[Referencia, ...] = ()
    gerado_por_ia: bool = False
    referencia_a_confirmar: bool = False


@dataclass(frozen=True)
class PropriedadeSugerida:
    pset: str
    nome: str
    tipo_dado: str | None = None


@dataclass(frozen=True)
class Apontamento:
    id: str  # APT-001
    tipo: TipoApontamento
    severidade: Severidade
    destinatario: Destinatario
    titulo: str
    analise: str  # "A" | "B" | "C" | "saude"
    evidencias_edital: tuple[Evidencia, ...] = ()
    elementos: tuple[str, ...] = ()  # GlobalIds
    requisito_id: str | None = None
    como_agir: str = ""
    por_que: str = ""
    referencias: tuple[Referencia, ...] = ()
    gerado_por_ia: bool = False
    referencia_a_confirmar: bool = False
    classe_ifc: str | None = None
    propriedades_sugeridas: tuple[PropriedadeSugerida, ...] = ()
    detalhe: str = ""


@dataclass(frozen=True)
class Indicadores:
    conformidade_percentual: float | None
    especificacoes_total: int
    especificacoes_aprovadas: int
    elementos_verificados: int
    elementos_nao_conformes: int
    cobertura_percentual: float | None
    classes_especificaveis: int
    classes_cobertas: int
    checklist_presentes: int
    checklist_parciais: int
    checklist_total: int
    requisitos_aprovados: int
    requisitos_nao_verificaveis: int
    apontamentos_por_severidade: dict[str, int] = field(default_factory=dict)
    apontamentos_por_destinatario: dict[str, int] = field(default_factory=dict)
    apontamentos_por_tipo: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class Relatorio:
    verificacao_id: str
    projeto_id: str
    gerado_em: str
    edital_arquivo: str
    modelo_arquivo: str
    schema_ifc: str
    modo_ia: str
    indicadores: Indicadores
    apontamentos: tuple[Apontamento, ...]
    resultados_ids: tuple[ResultadoEspecificacao, ...]
    cobertura: Cobertura | None
    checklist: tuple[ResultadoChecklist, ...]
    itens_checklist: tuple[ItemChecklist, ...]
    requisitos: tuple[Requisito, ...]
    estado_elementos: dict[str, EstadoElemento] = field(default_factory=dict)  # GlobalId → estado
    avisos: tuple[str, ...] = ()
    duracoes_s: dict[str, float] = field(default_factory=dict)


# --------------------------------------------------------------------------- agregados


@dataclass
class Projeto:
    id: str
    criado_em: str
    edital: Edital
    modelo: ModeloResumo
    topicos: tuple[Topico, ...] = ()
    eir: Eir | None = None
    ids_gerado: bool = False
    avisos: tuple[str, ...] = ()

    def topico(self, topico_id: str) -> Topico | None:
        for topico in self.topicos:
            if topico.id == topico_id:
                return topico
        return None


class StatusVerificacao(StrEnum):
    PENDENTE = "pendente"
    EXECUTANDO = "executando"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"


@dataclass
class Verificacao:
    id: str
    projeto_id: str
    status: StatusVerificacao = StatusVerificacao.PENDENTE
    progresso: dict[str, str] = field(default_factory=dict)  # análise → status
    iniciado_em: str | None = None
    concluido_em: str | None = None
    erro: str | None = None
    avisos: tuple[str, ...] = ()
