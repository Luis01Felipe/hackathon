"""DTOs Pydantic de entrada e conversão das entidades para JSON (contrato em docs/api.md)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, TypeAdapter

from editalcheck.domain.models import (
    Eir,
    ModeloResumo,
    Projeto,
    Relatorio,
    Requisito,
    Topico,
    Verificacao,
)

_REQUISITO = TypeAdapter(Requisito)
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

    def elemento(guid: str) -> dict[str, Any]:
        item = por_guid.get(guid)
        if item is None:
            return {"global_id": guid, "step_id": None, "classe": None, "nome": None}
        return {
            "global_id": guid,
            "step_id": item.step_id,
            "classe": item.classe,
            "nome": item.nome,
        }

    dados = _RELATORIO.dump_python(rel, mode="json")
    for apontamento in dados["apontamentos"]:
        apontamento["elementos"] = [elemento(g) for g in apontamento["elementos"]]
    dados["estado_elementos"] = [
        {**elemento(guid), "estado": estado} for guid, estado in dados["estado_elementos"].items()
    ]
    return dados
