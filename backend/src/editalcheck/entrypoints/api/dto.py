"""DTOs Pydantic de entrada e conversão das entidades para JSON (contrato em docs/api.md)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from editalcheck.domain.models import (
    ConsumoEtapa,
    Eir,
    LicaoAprendida,
    MarcoEntrega,
    ModeloResumo,
    Projeto,
    RegiaoPdf,
    Relatorio,
    Requisito,
    Topico,
    Verificacao,
)

_REQUISITO = TypeAdapter(Requisito)
_LICAO = TypeAdapter(LicaoAprendida)
_MARCO = TypeAdapter(MarcoEntrega)
_CONSUMO = TypeAdapter(ConsumoEtapa)
_TOPICO = TypeAdapter(Topico)
_RELATORIO = TypeAdapter(Relatorio)
_VERIFICACAO = TypeAdapter(Verificacao)


class CriarEirRequest(BaseModel):
    topicos: list[str] = Field(min_length=1)


class PatchRequisitoRequest(BaseModel):
    acao: Literal["aprovar", "rejeitar", "reabrir", "editar"]
    campos: dict[str, Any] | None = None


class AprovarTodosRequest(BaseModel):
    somente_verificaveis: bool = True


class AdicionarLacunaRequest(BaseModel):
    verificacao_id: str
    apontamento_id: str


class GerarIdsRequest(BaseModel):
    marco_id: str | None = None
    versao_ifc: Literal["IFC2X3", "IFC4", "IFC4X3_ADD2"] | None = None


class MarcoRequest(BaseModel):
    id: str | None = Field(default=None, max_length=20)
    nome: str = Field(min_length=1, max_length=80)
    descricao: str = Field(default="", max_length=300)


class DefinirMarcosRequest(BaseModel):
    marcos: list[MarcoRequest] = Field(max_length=20)


class DecisaoRequest(BaseModel):
    status: Literal["pendente", "aceito", "rejeitado", "em_discussao", "dispensado"]
    comentario: str = Field(default="", max_length=1000)
    autor: str = Field(default="", max_length=120)


def regiao(r: RegiaoPdf) -> dict[str, Any]:
    return {"pagina": r.pagina, "x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1}


def licoes(projeto: Projeto) -> list[dict[str, Any]]:
    return [_LICAO.dump_python(licao, mode="json") for licao in projeto.licoes]


def marcos(projeto: Projeto) -> list[dict[str, Any]]:
    return [_MARCO.dump_python(marco, mode="json") for marco in projeto.marcos]


def consumo(itens: tuple[ConsumoEtapa, ...]) -> list[dict[str, Any]]:
    return [_CONSUMO.dump_python(item, mode="json") for item in itens]


def projeto_resumo(projeto: Projeto, modo_ia: str) -> dict[str, Any]:
    modelo = projeto.modelo
    return {
        "id": projeto.id,
        "criado_em": projeto.criado_em,
        "edital_arquivo": projeto.edital.arquivo,
        "modelo_arquivo": modelo.arquivo,
        "schema_ifc": modelo.schema,
        "paginas": len(projeto.edital.paginas),
        "total_elementos": modelo.total_elementos,
        "classes": [
            {"nome": c.nome, "contagem": c.contagem, "especificavel": c.especificavel}
            for c in modelo.classes
        ],
        "topicos_total": len(projeto.topicos),
        "requisitos_total": len(projeto.eir.requisitos) if projeto.eir else 0,
        "ids_gerado": projeto.ids_gerado,
        "avisos": list(projeto.avisos),
        "modo_ia": modo_ia,
        "sem_modelo": modelo.sem_arquivo,
        "licoes": licoes(projeto),
        "documentos_licoes": [d.arquivo for d in projeto.documentos_licoes],
        "marcos": marcos(projeto),
        "ids_marco_id": projeto.ids_marco_id,
        "ids_versao_ifc": projeto.ids_versao_ifc,
    }


def topicos(projeto: Projeto) -> list[dict[str, Any]]:
    return [_TOPICO.dump_python(t, mode="json") for t in projeto.topicos]


def requisito(req: Requisito) -> dict[str, Any]:
    return _REQUISITO.dump_python(req, mode="json")


def eir_resposta(eir: Eir, avisos: tuple[str, ...] = (), descartados: int = 0) -> dict[str, Any]:
    return {
        "versao": eir.versao,
        "data": eir.data,
        "topicos_selecionados": list(eir.topicos_selecionados),
        "aprovado_por": eir.aprovado_por,
        "requisitos": [requisito(r) for r in eir.requisitos],
        "avisos": list(avisos),
        "descartados": descartados,
    }


def verificacao(v: Verificacao) -> dict[str, Any]:
    return _VERIFICACAO.dump_python(v, mode="json")


def relatorio(rel: Relatorio, modelo: ModeloResumo) -> dict[str, Any]:
    por_guid = {e.global_id: e for e in modelo.elementos}
    caixas = rel.caixas

    def elemento(guid: str) -> dict[str, Any]:
        item = por_guid.get(guid)
        caixa = caixas.get(guid)
        posicao = (
            {
                "centro": list(caixa.centro),
                "minimo": list(caixa.minimo),
                "maximo": list(caixa.maximo),
            }
            if caixa
            else None
        )
        if item is None:
            return {
                "global_id": guid,
                "step_id": None,
                "classe": None,
                "nome": None,
                "nome_longo": None,
                "pavimento": None,
                "posicao": posicao,
            }
        return {
            "global_id": guid,
            "step_id": item.step_id,
            "classe": item.classe,
            "nome": item.nome,
            "nome_longo": item.nome_longo,
            "pavimento": item.pavimento,
            "posicao": posicao,
        }

    dados = _RELATORIO.dump_python(rel, mode="json")
    dados.pop("caixas", None)
    for bruto, apontamento in zip(rel.apontamentos, dados["apontamentos"], strict=True):
        apontamento["elementos"] = [elemento(g) for g in apontamento["elementos"]]
        apontamento["origem"] = bruto.origem.value
        apontamento["verificacao_manual"] = bruto.verificacao_manual
    dados["estado_elementos"] = [
        {**elemento(guid), "estado": estado} for guid, estado in dados["estado_elementos"].items()
    ]
    return dados
