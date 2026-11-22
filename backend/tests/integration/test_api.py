"""Fluxo completo pela API HTTP (contrato em docs/api.md)."""

from fastapi.testclient import TestClient

from editalcheck.bootstrap import Container
from editalcheck.entrypoints.api.main import criar_app


def test_fluxo_completo_pela_api(container: Container, arquivos_demo) -> None:
    cliente = TestClient(criar_app(container))
    assert cliente.get("/api/config").json()["modo_ia"] == "offline"

    edital, modelo = arquivos_demo
    resposta = cliente.post(
        "/api/projetos",
        files={
            "edital": ("edital.pdf", edital, "application/pdf"),
            "modelo": ("modelo.ifc", modelo, "application/x-step"),
        },
    )
    assert resposta.status_code == 201, resposta.text
    projeto = resposta.json()
    assert projeto["schema_ifc"] == "IFC4" and projeto["paginas"] == 5
    pid = projeto["id"]

    topicos = cliente.get(f"/api/projetos/{pid}/topicos").json()
    selecionados = [t["id"] for t in topicos if t["numero"] in ("5.1", "5.5")]
    eir = cliente.post(f"/api/projetos/{pid}/eir", json={"topicos": selecionados}).json()
    assert len(eir["requisitos"]) == 5

    primeiro = eir["requisitos"][0]["id"]
    editado = cliente.patch(
        f"/api/projetos/{pid}/eir/requisitos/{primeiro}",
        json={"acao": "editar", "campos": {"descricao": "Portas com resistência ao fogo"}},
    ).json()
    assert editado["status"] == "editado"
    rejeitado = cliente.patch(
        f"/api/projetos/{pid}/eir/requisitos/{eir['requisitos'][1]['id']}",
        json={"acao": "rejeitar"},
    )
    assert rejeitado.json()["status"] == "rejeitado"
    cliente.post(f"/api/projetos/{pid}/eir/aprovar-todos", json={"somente_verificaveis": True})

    planilha = cliente.get(f"/api/projetos/{pid}/eir.xlsx")
    assert planilha.status_code == 200 and planilha.content[:2] == b"PK"

    ids = cliente.post(f"/api/projetos/{pid}/ids").json()
    assert ids["valido"] and ids["especificacoes"] == 4
    assert cliente.get(f"/api/projetos/{pid}/ids.xml").text.count("<specification ") == 4

    verificacao = cliente.post(f"/api/projetos/{pid}/verificacoes")
    assert verificacao.status_code == 202
    vid = verificacao.json()["id"]
    estado = cliente.get(f"/api/verificacoes/{vid}").json()  # TestClient roda a tarefa ao responder
    assert estado["status"] == "concluida", estado

    relatorio = cliente.get(f"/api/verificacoes/{vid}/relatorio").json()
    nao_conformidade = next(a for a in relatorio["apontamentos"] if a["tipo"] == "nao_conformidade")
    assert all(e["step_id"] for e in nao_conformidade["elementos"])
    assert {e["estado"] for e in relatorio["estado_elementos"]} == {"conforme", "nao_conforme"}
    assert cliente.get(f"/api/verificacoes/{vid}/relatorio.html").text.startswith("<!doctype html>")
    assert cliente.get(f"/api/verificacoes/{vid}/resultado.bcf").content[:2] == b"PK"
    assert cliente.get(f"/api/projetos/{pid}/modelo.ifc").content.startswith(b"ISO-10303-21")

    lacuna = next(a for a in relatorio["apontamentos"] if a["tipo"] == "lacuna_cobertura")
    novos = cliente.post(
        f"/api/projetos/{pid}/eir/requisitos",
        json={"verificacao_id": vid, "apontamento_id": lacuna["id"]},
    )
    assert novos.status_code == 201 and novos.json()[0]["sugerido_por_lacuna"]


def test_erros_em_portugues(container: Container) -> None:
    cliente = TestClient(criar_app(container))
    resposta = cliente.get("/api/projetos/inexistente/topicos")
    assert resposta.status_code == 404 and resposta.json()["detail"] == "Projeto não encontrado."
    assert cliente.get("/api/projetos/..%2F..%2Fetc/topicos").status_code == 404
    demo = cliente.post("/api/projetos/demo").json()
    assert cliente.post(f"/api/projetos/{demo['id']}/ids").status_code == 409
