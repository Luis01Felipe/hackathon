"""Pipeline completo com os dados da demo, no modo offline, e métricas do gabarito (seção 14)."""

import time

import pytest

from editalcheck.application.errors import EntradaInvalidaError
from editalcheck.bootstrap import Container
from editalcheck.domain.models import (
    EstadoElemento,
    StatusRequisito,
    StatusVerificacao,
    TipoApontamento,
)
from editalcheck.evaluation import avaliar, carregar_gabarito
from tests.conftest import PASTA_DEMO


def _rodar(container: Container, edital: bytes, modelo: bytes, numeros: list[str]):
    projeto = container.importar.executar(edital, "edital.pdf", modelo, "modelo.ifc")
    topicos = [t.id for t in projeto.topicos if t.numero in numeros]
    resultado_eir = container.gerar_eir.executar(projeto.id, topicos)
    container.revisar_eir.aprovar_todos(projeto.id)
    resultado_ids = container.gerar_ids.executar(projeto.id)
    verificacao = container.verificar.executar(container.verificar.iniciar(projeto.id).id)
    relatorio = container.repositorio.get_relatorio(verificacao.id)
    return projeto, resultado_eir, resultado_ids, verificacao, relatorio


def test_pipeline_demo_ponta_a_ponta(container: Container, arquivos_demo) -> None:
    gabarito = carregar_gabarito(PASTA_DEMO / "gabarito.json")
    inicio = time.perf_counter()
    projeto, resultado_eir, resultado_ids, verificacao, relatorio = _rodar(
        container, *arquivos_demo, gabarito["topicos_demo"]
    )
    duracao = time.perf_counter() - inicio

    assert verificacao.status == StatusVerificacao.CONCLUIDA
    assert set(verificacao.progresso.values()) == {"concluida"}
    assert resultado_ids.valido and resultado_ids.especificacoes == 8
    assert relatorio is not None
    assert duracao < 180  # RNF-01

    falhas = {r.requisito_id: len(r.falhas) for r in relatorio.resultados_ids}
    requisitos = {r.id: r for r in relatorio.requisitos}
    por_mapeamento = {
        f"{requisitos[rid].ifc_class}.{requisitos[rid].propriedade}": n for rid, n in falhas.items()
    }
    for mapeamento, esperado in gabarito["nao_conformidades_planejadas"].items():
        assert por_mapeamento[mapeamento] == esperado, mapeamento

    tipos = {a.tipo for a in relatorio.apontamentos}
    assert {
        TipoApontamento.NAO_CONFORMIDADE,
        TipoApontamento.LACUNA_COBERTURA,
        TipoApontamento.AMBIGUIDADE,
        TipoApontamento.ITEM_AUSENTE,
        TipoApontamento.NAO_VERIFICAVEL,
        TipoApontamento.CONTRADICAO,
        TipoApontamento.QUALIDADE_MODELO,
    } <= tipos
    # RNF-04: todo apontamento tem evidência (trecho do edital e/ou elemento) ou é item ausente
    for a in relatorio.apontamentos:
        assert (
            a.evidencias_edital
            or a.elementos
            or a.tipo
            in (
                TipoApontamento.ITEM_AUSENTE,
                TipoApontamento.QUALIDADE_MODELO,
            )
        ), a.id
        assert a.como_agir and a.por_que, a.id
    assert relatorio.indicadores.conformidade_percentual == 50.0
    assert relatorio.indicadores.cobertura_percentual == pytest.approx(45.5)
    assert EstadoElemento.NAO_CONFORME in relatorio.estado_elementos.values()

    # Saídas publicadas: HTML e BCF
    assert container.repositorio.relatorio_file(verificacao.id, "relatorio.html")
    assert container.repositorio.relatorio_file(verificacao.id, "resultado.bcf")

    # Métricas da seção 14.3 contra o gabarito (modo regras; ver limites no JOURNAL)
    metricas = avaliar(
        gabarito,
        relatorio.requisitos,
        resultado_eir.descartados,
        relatorio,
        resultado_ids.valido,
        duracao,
    )
    assert metricas.citacoes_percentual == 100.0
    assert metricas.ids_valido
    assert metricas.recall is not None and metricas.recall >= 80.0
    assert metricas.precisao is not None and metricas.precisao >= 80.0
    assert metricas.checklist_percentual is not None and metricas.checklist_percentual >= 80.0


def test_ciclo_fechado_lacuna_volta_para_o_eir(container: Container, arquivos_demo) -> None:
    projeto, _, _, verificacao, relatorio = _rodar(container, *arquivos_demo, ["5.1"])
    lacuna = next(a for a in relatorio.apontamentos if a.tipo == TipoApontamento.LACUNA_COBERTURA)
    novos = container.revisar_eir.adicionar_de_lacuna(projeto.id, lacuna)
    assert novos and all(
        r.sugerido_por_lacuna and r.status == StatusRequisito.PROPOSTO for r in novos
    )
    container.revisar_eir.aprovar(projeto.id, novos[0].id)
    resultado = container.gerar_ids.executar(projeto.id)
    assert resultado.valido and novos[0].id in resultado.requisitos_incluidos


def test_edicao_revalida_classe_s3(container: Container, arquivos_demo) -> None:
    projeto = container.importar.executar(*arquivos_demo[:1], "e.pdf", arquivos_demo[1], "m.ifc")
    portas = next(t.id for t in projeto.topicos if t.numero == "5.1")
    eir = container.gerar_eir.executar(projeto.id, [portas]).eir
    editado = container.revisar_eir.editar(
        projeto.id, eir.requisitos[0].id, {"ifc_class": "IfcPortaInventada"}
    )
    assert editado.status == StatusRequisito.EDITADO
    assert not editado.verificavel_por_ids
    assert "S3" in (editado.motivo_nao_verificavel or "")


def test_pdf_invalido_e_rejeitado(container: Container, arquivos_demo) -> None:
    with pytest.raises(EntradaInvalidaError):
        container.importar.executar(b"nao sou pdf", "x.pdf", arquivos_demo[1], "m.ifc")
