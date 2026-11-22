"""Adaptadores: IDS (S6 e validação) e camada estruturada do LLM (S1, cache)."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from editalcheck.adapters.ids.ifctester_builder import IdsInvalidoError, IfcTesterIdsBuilder
from editalcheck.adapters.ids.ifctester_validator import IfcTesterValidator, traduzir_motivo
from editalcheck.adapters.llm.structured import (
    LlmIndisponivelError,
    PromptLoader,
    StructuredLlm,
    Uso,
)
from editalcheck.config import RAIZ_BACKEND, RAIZ_REPO
from editalcheck.domain.models import (
    Eir,
    Evidencia,
    Requisito,
    Restricao,
    StatusRequisito,
    TipoFaceta,
    TipoRestricao,
)

MODELO = RAIZ_REPO / "data" / "demo" / "modelo.ifc"


def _requisito(id_: str, **campos) -> Requisito:
    base = dict(
        id=id_,
        topico_id="TOP-01",
        descricao="teste",
        evidencia=Evidencia(3, "Todas as portas deverão conter a propriedade FireRating."),
        verificavel_por_ids=True,
        ifc_class="IfcDoor",
        faceta=TipoFaceta.PROPRIEDADE,
        pset="Pset_DoorCommon",
        propriedade="FireRating",
        tipo_dado="IfcLabel",
        status=StatusRequisito.APROVADO,
    )
    base.update(campos)
    return Requisito(**base)


def _eir(*requisitos: Requisito) -> Eir:
    return Eir(
        versao=1,
        data="2026-11-22T10:00:00",
        topicos_selecionados=("TOP-01",),
        requisitos=requisitos,
    )


def test_ids_gerado_e_valido_e_so_inclui_aprovados_verificaveis() -> None:
    construtor = IfcTesterIdsBuilder()
    eir = _eir(
        _requisito("REQ-001"),
        _requisito(
            "REQ-002",
            ifc_class="IfcStair",
            pset="Pset_StairCommon",
            propriedade="RiserHeight",
            tipo_dado="IfcPositiveLengthMeasure",
            restricao=Restricao(TipoRestricao.INTERVALO, minimo=0.16, maximo=0.18),
        ),
        _requisito(
            "REQ-003",
            faceta=TipoFaceta.ATRIBUTO,
            ifc_class="IfcSpace",
            pset=None,
            propriedade="LongName",
            tipo_dado=None,
        ),
        _requisito("REQ-004", status=StatusRequisito.REJEITADO),
        _requisito("REQ-005", verificavel_por_ids=False),
    )
    xml = construtor.build(eir, "IFC4", "Teste")
    assert construtor.check(xml) == []
    texto = xml.decode()
    assert 'identifier="REQ-001"' in texto and 'identifier="REQ-002"' in texto
    assert "REQ-004" not in texto and "REQ-005" not in texto
    assert "Edital, p. 3" in texto


def test_s6_detecta_ids_invalido() -> None:
    construtor = IfcTesterIdsBuilder()
    xml = construtor.build(_eir(_requisito("REQ-001")), "IFC4", "Teste")
    assert construtor.check(xml.replace(b'cardinality="required"', b'cardinality="sempre"'))


def test_eir_sem_requisito_para_ids() -> None:
    with pytest.raises(IdsInvalidoError):
        IfcTesterIdsBuilder().build(
            _eir(_requisito("REQ-001", verificavel_por_ids=False)), "IFC4", "Teste"
        )


def test_validacao_encontra_as_portas_sem_firerating() -> None:
    xml = IfcTesterIdsBuilder().build(_eir(_requisito("REQ-001")), "IFC4", "Teste")
    resultado = IfcTesterValidator().validate(xml, str(MODELO))[0]
    assert resultado.requisito_id == "REQ-001"
    assert resultado.aplicaveis == 16
    assert sorted(f.nome for f in resultado.falhas) == [
        "Porta P03",
        "Porta P07",
        "Porta P10",
        "Porta P13",
        "Porta P16",
    ]
    assert resultado.falhas[0].motivo == "O Pset não contém a propriedade exigida"


def test_traducao_de_motivos() -> None:
    assert traduzir_motivo('The property value "0.19" does not match the requirements') == (
        'O valor "0.19" não atende à restrição'
    )
    assert traduzir_motivo("motivo desconhecido") == "motivo desconhecido"


# ------------------------------------------------------------------ LLM estruturado


class _Saida(BaseModel):
    valor: int


class _ClienteFalso:
    modelo = "falso-1"

    def __init__(self, respostas: list[str]) -> None:
        self.respostas = respostas
        self.chamadas: list[str] = []

    def complete(self, *, sistema: str, prompt: str, schema: type[BaseModel]) -> tuple[str, Uso]:
        self.chamadas.append(prompt)
        if not self.respostas:
            raise RuntimeError("sem rede")
        return self.respostas.pop(0), Uso(10, 5)


@pytest.fixture()
def prompts(tmp_path: Path) -> PromptLoader:
    (tmp_path / "sistema.md").write_text("<!-- versao: 1 -->\nSistema.", encoding="utf-8")
    (tmp_path / "teste.md").write_text("<!-- versao: 7 -->\nValor de {{ x }}.", encoding="utf-8")
    return PromptLoader(tmp_path)


def test_s1_repara_resposta_fora_do_schema_e_usa_cache(
    prompts: PromptLoader, tmp_path: Path
) -> None:
    cliente = _ClienteFalso(['{"valor": "abc"}', '```json\n{"valor": 3}\n```'])
    llm = StructuredLlm(cliente, prompts, tmp_path / "cache")
    assert llm.gerar("teste", _Saida, x=1).valor == 3
    assert len(cliente.chamadas) == 2 and "Correção necessária" in cliente.chamadas[1]
    assert llm.gerar("teste", _Saida, x=1).valor == 3  # cache: nenhuma chamada nova
    assert len(cliente.chamadas) == 2


def test_s1_desiste_apos_dois_reparos(prompts: PromptLoader, tmp_path: Path) -> None:
    cliente = _ClienteFalso(['{"x": 1}'] * 3)
    with pytest.raises(LlmIndisponivelError):
        StructuredLlm(cliente, prompts, tmp_path / "cache").gerar("teste", _Saida, x=2)
    assert len(cliente.chamadas) == 3


def test_falha_de_rede_vira_llm_indisponivel(prompts: PromptLoader, tmp_path: Path) -> None:
    with pytest.raises(LlmIndisponivelError):
        StructuredLlm(_ClienteFalso([]), prompts, tmp_path / "cache").gerar("teste", _Saida, x=3)


def test_prompts_versionados_renderizam() -> None:
    loader = PromptLoader(RAIZ_BACKEND / "prompts")
    for nome in (
        "sistema",
        "topicos",
        "extracao_requisitos",
        "ambiguidade",
        "checklist",
        "contradicoes",
        "recomendacao",
    ):
        prompt = loader.carregar(nome)
        assert prompt.versao != "0", nome
