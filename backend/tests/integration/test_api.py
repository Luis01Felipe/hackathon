"""Fluxo completo pela API HTTP (contrato em docs/api.md)."""

from io import BytesIO

from fastapi.testclient import TestClient
from openpyxl import load_workbook

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
    eir = cliente.post(f"/api/projetos/{pid}/ir", json={"topicos": selecionados}).json()
    assert len(eir["requisitos"]) == 5
    assert (
        cliente.get(f"/api/projetos/{pid}/ir").json()
        == cliente.get(f"/api/projetos/{pid}/ir").json()
    )
    assert all(r["item_checagem"] and r["verificacao"] for r in eir["requisitos"])

    primeiro = eir["requisitos"][0]["id"]
    editado = cliente.patch(
        f"/api/projetos/{pid}/ir/requisitos/{primeiro}",
        json={
            "acao": "editar",
            "campos": {
                "descricao": "Portas com resistência ao fogo",
                "ambientes": ["Sala de baterias", " sala de baterias ", "Hall"],
                "item_checagem": "INCE",
            },
        },
    ).json()
    assert editado["status"] == "editado"
    assert editado["ambientes"] == ["Sala de baterias", "Hall"]
    assert editado["item_checagem"] == "INCE"
    rejeitado = cliente.patch(
        f"/api/projetos/{pid}/ir/requisitos/{eir['requisitos'][1]['id']}",
        json={"acao": "rejeitar"},
    )
    assert rejeitado.json()["status"] == "rejeitado"
    cliente.post(f"/api/projetos/{pid}/ir/aprovar-todos", json={"somente_verificaveis": True})

    planilha = cliente.get(f"/api/projetos/{pid}/ir.xlsx")
    assert planilha.status_code == 200 and planilha.content[:2] == b"PK"
    assert cliente.get(f"/api/projetos/{pid}/ir.xlsx").status_code == 200
    _confere_planilha_ir(planilha.content, primeiro)

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
        f"/api/projetos/{pid}/ir/requisitos",
        json={"verificacao_id": vid, "apontamento_id": lacuna["id"]},
    )
    assert novos.status_code == 201 and novos.json()[0]["sugerido_por_lacuna"]


COLUNAS_TEMPLATE = [
    "ID",
    "Escopo",
    "Categorias",
    "Item de checagem",
    "Descrição",
    "Pág.",
    "Trecho literal do edital",
    "Verificação",
    "Verificável por IDS",
    "Motivo / observação",
    "Classe IFC",
    "PredefinedType",
    "Faceta IDS",
    "Pset.Propriedade ou atributo",
    "Tipo de dado",
    "Restrição",
    "Cardinalidade",
    "Origem do vocabulário",
    "Aplica a todas do escopo",
    "Status",
]


def _confere_planilha_ir(conteudo: bytes, editado_id: str) -> None:
    """A planilha segue o template de IR: abas, 20 colunas na ordem e matriz por ambiente."""
    planilha = load_workbook(BytesIO(conteudo))
    assert planilha.sheetnames == [
        "Resumo",
        "Requisitos",
        "Matriz",
        "Categorias",
        "Itens de checagem",
        "Aceitação e qualidade",
    ]
    requisitos = planilha["Requisitos"]
    cabecalho = [c.value for c in requisitos[1]]
    assert cabecalho[:20] == COLUNAS_TEMPLATE
    linha = next(r for r in requisitos.iter_rows(min_row=2, values_only=True) if r[0] == editado_id)
    assert linha[1].startswith("5.1 — ")
    assert linha[2] == "Sala de baterias; Hall"
    assert linha[3] == "INCE · Proteção contra incêndio e rotas de fuga"
    assert linha[18] == "não"

    matriz = planilha["Matriz"]
    ambientes = {r[0]: r for r in matriz.iter_rows(min_row=2, values_only=True)}
    coluna_ince = [c.value for c in matriz[1]].index(
        "INCE · Proteção contra incêndio e rotas de fuga"
    )
    assert ambientes["Hall"][coluna_ince].startswith("Tem · ")
    assert len(list(planilha["Itens de checagem"].iter_rows(min_row=2))) == 12


def test_atras_de_proxy_com_prefixo_removido(container: Container) -> None:
    """Traefik com StripPrefix: o app recebe /api/... e o servidor informa o root_path."""
    cliente = TestClient(criar_app(container), root_path="/editalcheck")
    assert cliente.get("/api/config").status_code == 200
    assert cliente.get("/openapi.json").json()["servers"] == [{"url": "/editalcheck"}]
    assert "/editalcheck/openapi.json" in cliente.get("/docs").text


def test_erros_em_portugues(container: Container) -> None:
    cliente = TestClient(criar_app(container))
    resposta = cliente.get("/api/projetos/inexistente/topicos")
    assert resposta.status_code == 404
    assert resposta.json()["detail"].startswith("Projeto não encontrado")
    assert cliente.get("/api/projetos/..%2F..%2Fetc/topicos").status_code == 404
    demo = cliente.post("/api/projetos/demo").json()
    assert cliente.post(f"/api/projetos/{demo['id']}/ids").status_code == 409


def test_tipo_de_verificacao_decide_se_entra_no_ids(container: Container, arquivos_demo) -> None:
    cliente = TestClient(criar_app(container))
    edital, modelo = arquivos_demo
    pid = cliente.post(
        "/api/projetos",
        files={
            "edital": ("edital.pdf", edital, "application/pdf"),
            "modelo": ("modelo.ifc", modelo, "application/x-step"),
        },
    ).json()["id"]
    topicos = cliente.get(f"/api/projetos/{pid}/topicos").json()
    selecionados = [t["id"] for t in topicos if t["numero"] == "5.1"]
    eir = cliente.post(f"/api/projetos/{pid}/ir", json={"topicos": selecionados}).json()
    verificavel = next(r for r in eir["requisitos"] if r["verificavel_por_ids"])
    url = f"/api/projetos/{pid}/ir/requisitos/{verificavel['id']}"

    manual = cliente.patch(url, json={"acao": "editar", "campos": {"verificacao": "manual"}}).json()
    assert manual["verificacao"] == "manual" and manual["verificavel_por_ids"] is False

    parcial = cliente.patch(
        url, json={"acao": "editar", "campos": {"verificacao": "ids_script"}}
    ).json()
    assert parcial["verificacao"] == "ids_script" and parcial["verificavel_por_ids"] is True

    invalido = cliente.patch(url, json={"acao": "editar", "campos": {"item_checagem": "XPTO"}})
    assert invalido.status_code in (400, 422)


def test_nomes_de_arquivo_fora_do_latin1_nao_derrubam_os_downloads(
    container: Container, arquivos_demo
) -> None:
    """Edital "Vol. II — Linha 6" derrubava /edital.pdf com UnicodeEncodeError no cabeçalho."""
    cliente = TestClient(criar_app(container))
    edital, modelo = arquivos_demo
    pid = cliente.post(
        "/api/projetos",
        files={
            "edital": ("Edital Vol. II — Linha 6 “Laranja”.pdf", edital, "application/pdf"),
            "modelo": ("Modelo — estação ✓.ifc", modelo, "application/x-step"),
        },
    ).json()["id"]

    pdf = cliente.get(f"/api/projetos/{pid}/edital.pdf")
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    disposicao = pdf.headers["content-disposition"]
    assert disposicao.startswith("inline; filename=")
    assert "filename*=UTF-8''Edital%20Vol.%20II%20%E2%80%94%20Linha%206" in disposicao

    ifc = cliente.get(f"/api/projetos/{pid}/modelo.ifc")
    assert ifc.status_code == 200
    assert "%E2%9C%93.ifc" in ifc.headers["content-disposition"]
