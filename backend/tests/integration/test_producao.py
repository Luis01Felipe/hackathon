"""Garantias de produção: erros previsíveis, segurança HTTP, limites e verificação robusta."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from editalcheck.application.errors import ConflitoError
from editalcheck.application.use_cases.executar_verificacao import PROJETO_REMOVIDO
from editalcheck.bootstrap import Container, construir
from editalcheck.config import carregar
from editalcheck.domain.models import StatusVerificacao
from editalcheck.domain.restricoes import problema_no_padrao
from editalcheck.entrypoints.api.main import CSP, criar_app
from tests.conftest import configuracao_de_teste


def _projeto(container: Container, arquivos_demo) -> str:
    edital, modelo = arquivos_demo
    return container.importar.executar(edital, "edital.pdf", modelo, "modelo.ifc").id


def test_saude_e_cabecalhos_de_seguranca(container: Container) -> None:
    cliente = TestClient(criar_app(container))
    resposta = cliente.get("/api/saude")
    assert resposta.status_code == 200 and resposta.json()["status"] == "ok"
    assert resposta.headers["X-Content-Type-Options"] == "nosniff"
    assert resposta.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert len(resposta.headers["X-Request-ID"]) >= 8
    # Um id válido vindo do proxy é mantido, para correlacionar os logs.
    eco = cliente.get("/api/saude", headers={"X-Request-ID": "abc12345-proxy"})
    assert eco.headers["X-Request-ID"] == "abc12345-proxy"


def test_csp_so_nas_paginas_html(tmp_path: Path) -> None:
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<!doctype html><title>EditalCheck</title>")
    container = construir(
        carregar(
            configuracao_de_teste(tmp_path, EDITALCHECK_FRONTEND_DIR=str(frontend)),
            ler_dotenv=False,
        )
    )
    cliente = TestClient(criar_app(container))
    assert cliente.get("/").headers["Content-Security-Policy"] == CSP
    assert "Content-Security-Policy" not in cliente.get("/api/config").headers


def test_erro_inesperado_vira_json_com_codigo(container: Container, monkeypatch) -> None:
    def quebrar(_: str):
        raise RuntimeError("detalhe interno que não pode vazar")

    monkeypatch.setattr(container.repositorio, "get", quebrar)
    cliente = TestClient(criar_app(container), raise_server_exceptions=False)
    resposta = cliente.get("/api/projetos/qualquer")
    assert resposta.status_code == 500
    detalhe = resposta.json()["detail"]
    assert "Código para o suporte" in detalhe and "detalhe interno" not in detalhe
    assert resposta.headers["X-Request-ID"] in detalhe


def test_documentacao_da_api_pode_ser_desligada(tmp_path: Path) -> None:
    container = construir(
        carregar(configuracao_de_teste(tmp_path, EDITALCHECK_DOCS="false"), ler_dotenv=False)
    )
    cliente = TestClient(criar_app(container))
    assert cliente.get("/docs").status_code == 404
    assert cliente.get("/openapi.json").status_code == 404
    assert cliente.get("/api/saude").status_code == 200


def test_ids_de_projeto_e_verificacao_tem_128_bits(container: Container, arquivos_demo) -> None:
    pid = _projeto(container, arquivos_demo)
    verificacao = container.verificar.iniciar(pid)
    assert len(pid) == 32 and len(verificacao.id) == 32


def test_verificacao_duplicada_no_mesmo_projeto(container: Container, arquivos_demo) -> None:
    pid = _projeto(container, arquivos_demo)
    primeira = container.verificar.iniciar(pid)
    with pytest.raises(ConflitoError):
        container.verificar.iniciar(pid)
    container.verificar.executar(primeira.id)
    # Terminada a primeira, uma nova verificação é aceita.
    assert container.verificar.iniciar(pid).status == StatusVerificacao.PENDENTE


def test_projeto_apagado_durante_a_verificacao(
    container: Container, arquivos_demo, monkeypatch
) -> None:
    pid = _projeto(container, arquivos_demo)
    verificacao = container.verificar.iniciar(pid)
    original = container.verificar._rodar_analises

    def apagar_no_meio(*args, **kwargs):
        container.excluir.executar(pid)
        return original(*args, **kwargs)

    monkeypatch.setattr(container.verificar, "_rodar_analises", apagar_no_meio)
    resultado = container.verificar.executar(verificacao.id)
    assert resultado.status == StatusVerificacao.FALHOU
    assert resultado.erro == PROJETO_REMOVIDO


@pytest.mark.parametrize(
    ("padrao", "aceito"),
    [
        (r"^[A-Z]{2}-\d{3}$", True),
        (r"EI\s?(30|60|90|120)", True),
        (r"(a+)+$", False),
        (r"(\d*)*x", False),
        (r"(", False),
        ("a" * 201, False),
    ],
)
def test_padrao_regex_da_restricao(padrao: str, aceito: bool) -> None:
    assert (problema_no_padrao(padrao) is None) is aceito


def test_edicao_recusa_padrao_perigoso_e_campo_desconhecido(
    container: Container, arquivos_demo
) -> None:
    pid = _projeto(container, arquivos_demo)
    cliente = TestClient(criar_app(container))
    topicos = [t["id"] for t in cliente.get(f"/api/projetos/{pid}/topicos").json()]
    requisito = cliente.post(f"/api/projetos/{pid}/ir", json={"topicos": topicos}).json()[
        "requisitos"
    ][0]["id"]
    url = f"/api/projetos/{pid}/ir/requisitos/{requisito}"
    perigoso = {"restricao": {"tipo": "padrao", "valores": ["(a+)+$"]}}
    resposta = cliente.patch(url, json={"acao": "editar", "campos": perigoso})
    assert resposta.status_code == 422 and "padrão" in resposta.json()["detail"]
    desconhecido = cliente.patch(url, json={"acao": "editar", "campos": {"inexistente": 1}})
    assert desconhecido.status_code == 422


def test_limite_de_documentos_de_licoes(container: Container, arquivos_demo) -> None:
    edital, _ = arquivos_demo
    cliente = TestClient(criar_app(container))
    licoes = [("licoes", (f"l{i}.txt", b"Regra de teste.", "text/plain")) for i in range(11)]
    resposta = cliente.post(
        "/api/projetos", files=[("edital", ("edital.pdf", edital, "application/pdf")), *licoes]
    )
    assert resposta.status_code == 422 and "até 10" in resposta.json()["detail"]
