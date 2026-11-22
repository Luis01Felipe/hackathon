"""API HTTP do EditalCheck (FastAPI). Contrato em docs/api.md."""

import mimetypes
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from editalcheck import __version__
from editalcheck.application.errors import (
    ConflitoError,
    EditalCheckError,
    EntradaInvalidaError,
    NaoEncontradoError,
)
from editalcheck.bootstrap import Container, configurar_logs, construir
from editalcheck.config import carregar
from editalcheck.entrypoints.api import dto

TAMANHO_BLOCO = 1024 * 1024
STATUS_ERRO = {NaoEncontradoError: 404, ConflitoError: 409, EntradaInvalidaError: 422}
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


async def _ler_limitado(arquivo: UploadFile, limite_mb: int) -> bytes:
    limite = limite_mb * 1024 * 1024
    partes: list[bytes] = []
    total = 0
    while bloco := await arquivo.read(TAMANHO_BLOCO):
        total += len(bloco)
        if total > limite:
            raise HTTPException(413, f"Arquivo acima do limite de {limite_mb} MB.")
        partes.append(bloco)
    return b"".join(partes)


def criar_app(container: Container | None = None) -> FastAPI:
    if container is None:
        settings = carregar()
        configurar_logs(settings.nivel_log)
        container = construir(settings)
    c = container
    app = FastAPI(
        title="EditalCheck API",
        version=__version__,
        description="Verificador bidirecional Edital × IFC (IFC, IDS, BCF, bSDD).",
    )

    @app.exception_handler(EditalCheckError)
    async def _erro_negocio(_: Request, erro: EditalCheckError) -> JSONResponse:
        status = next((s for tipo, s in STATUS_ERRO.items() if isinstance(erro, tipo)), 400)
        return JSONResponse({"detail": str(erro)}, status_code=status)

    def projeto_ou_404(projeto_id: str):
        projeto = c.repositorio.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        return projeto

    # ------------------------------------------------------------------ configuração

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        demo = c.settings.pasta_demo
        return {
            "versao": __version__,
            "modo_ia": c.settings.modo_ia,
            "modelo_llm": c.settings.gemini_model if c.settings.llm_ativo else None,
            "bsdd_ativo": c.settings.bsdd_ativo,
            "demo_disponivel": (demo / "edital.pdf").exists() and (demo / "modelo.ifc").exists(),
            "limite_upload_mb": c.settings.limite_upload_mb,
        }

    # ------------------------------------------------------------------ projetos

    @app.post("/api/projetos", status_code=201)
    async def criar_projeto(
        edital: UploadFile = File(...), modelo: UploadFile = File(...)
    ) -> dict[str, Any]:
        limite = c.settings.limite_upload_mb
        pdf = await _ler_limitado(edital, limite)
        ifc = await _ler_limitado(modelo, limite)
        projeto = c.importar.executar(
            pdf,
            Path(edital.filename or "edital.pdf").name,
            ifc,
            Path(modelo.filename or "modelo.ifc").name,
        )
        return dto.projeto_resumo(projeto, c.settings.modo_ia)

    @app.post("/api/projetos/demo", status_code=201)
    def criar_projeto_demo() -> dict[str, Any]:
        pasta = c.settings.pasta_demo
        pdf, ifc = pasta / "edital.pdf", pasta / "modelo.ifc"
        if not pdf.exists() or not ifc.exists():
            raise NaoEncontradoError("Dados de demonstração não encontrados em data/demo.")
        projeto = c.importar.executar(pdf.read_bytes(), pdf.name, ifc.read_bytes(), ifc.name)
        return dto.projeto_resumo(projeto, c.settings.modo_ia)

    @app.get("/api/projetos/{projeto_id}")
    def obter_projeto(projeto_id: str) -> dict[str, Any]:
        return dto.projeto_resumo(projeto_ou_404(projeto_id), c.settings.modo_ia)

    @app.get("/api/projetos/{projeto_id}/topicos")
    def listar_topicos(projeto_id: str) -> list[dict[str, Any]]:
        return dto.topicos(projeto_ou_404(projeto_id))

    @app.get("/api/projetos/{projeto_id}/modelo.ifc")
    def baixar_modelo(projeto_id: str) -> FileResponse:
        projeto = projeto_ou_404(projeto_id)
        return FileResponse(
            c.repositorio.file_path(projeto.id, "modelo.ifc"),
            media_type="application/x-step",
            filename=projeto.modelo.arquivo,
        )

    # ------------------------------------------------------------------ EIR

    @app.post("/api/projetos/{projeto_id}/eir")
    def gerar_eir(projeto_id: str, corpo: dto.CriarEirRequest) -> dict[str, Any]:
        resultado = c.gerar_eir.executar(projeto_id, corpo.topicos)
        return dto.eir_resposta(resultado.eir, resultado.avisos, resultado.descartados)

    @app.get("/api/projetos/{projeto_id}/eir")
    def obter_eir(projeto_id: str) -> dict[str, Any]:
        projeto = projeto_ou_404(projeto_id)
        if projeto.eir is None:
            raise NaoEncontradoError("O EIR ainda não foi gerado.")
        return dto.eir_resposta(projeto.eir)

    @app.patch("/api/projetos/{projeto_id}/eir/requisitos/{requisito_id}")
    def revisar_requisito(
        projeto_id: str, requisito_id: str, corpo: dto.PatchRequisitoRequest
    ) -> dict[str, Any]:
        revisar = c.revisar_eir
        match corpo.acao:
            case "aprovar":
                requisito = revisar.aprovar(projeto_id, requisito_id)
            case "rejeitar":
                requisito = revisar.rejeitar(projeto_id, requisito_id)
            case "reabrir":
                requisito = revisar.reabrir(projeto_id, requisito_id)
            case _:
                if not corpo.campos:
                    raise EntradaInvalidaError("Informe os campos a editar.")
                requisito = revisar.editar(projeto_id, requisito_id, corpo.campos)
        return dto.requisito(requisito)

    @app.post("/api/projetos/{projeto_id}/eir/aprovar-todos")
    def aprovar_todos(projeto_id: str, corpo: dto.AprovarTodosRequest) -> dict[str, Any]:
        return dto.eir_resposta(c.revisar_eir.aprovar_todos(projeto_id, corpo.somente_verificaveis))

    @app.post("/api/projetos/{projeto_id}/eir/requisitos", status_code=201)
    def adicionar_de_lacuna(
        projeto_id: str, corpo: dto.AdicionarLacunaRequest
    ) -> list[dict[str, Any]]:
        relatorio = c.repositorio.get_relatorio(corpo.verificacao_id)
        if relatorio is None or relatorio.projeto_id != projeto_id:
            raise NaoEncontradoError("Relatório não encontrado para este projeto.")
        apontamento = next(
            (a for a in relatorio.apontamentos if a.id == corpo.apontamento_id), None
        )
        if apontamento is None:
            raise NaoEncontradoError("Apontamento não encontrado.")
        return [
            dto.requisito(r) for r in c.revisar_eir.adicionar_de_lacuna(projeto_id, apontamento)
        ]

    @app.get("/api/projetos/{projeto_id}/eir.xlsx")
    def exportar_eir(projeto_id: str) -> Response:
        projeto = projeto_ou_404(projeto_id)
        if projeto.eir is None:
            raise NaoEncontradoError("O EIR ainda não foi gerado.")
        conteudo = c.exportador_eir.to_xlsx(projeto.eir, projeto)
        return Response(
            conteudo,
            media_type=TIPO_XLSX,
            headers={"Content-Disposition": f'attachment; filename="eir-{projeto.id}.xlsx"'},
        )

    # ------------------------------------------------------------------ IDS

    @app.post("/api/projetos/{projeto_id}/ids")
    def gerar_ids(projeto_id: str) -> dict[str, Any]:
        resultado = c.gerar_ids.executar(projeto_id)
        return {
            "especificacoes": resultado.especificacoes,
            "valido": resultado.valido,
            "erros": list(resultado.erros),
            "requisitos_incluidos": list(resultado.requisitos_incluidos),
            "url": f"/api/projetos/{projeto_id}/ids.xml" if resultado.valido else None,
        }

    @app.get("/api/projetos/{projeto_id}/ids.xml")
    def baixar_ids(projeto_id: str) -> Response:
        projeto = projeto_ou_404(projeto_id)
        conteudo = c.repositorio.read_file(projeto.id, "ids.xml")
        if conteudo is None:
            raise NaoEncontradoError("O IDS ainda não foi gerado.")
        return Response(
            conteudo,
            media_type="application/xml",
            headers={"Content-Disposition": f'attachment; filename="editalcheck-{projeto.id}.ids"'},
        )

    # ------------------------------------------------------------------ verificações

    @app.post("/api/projetos/{projeto_id}/verificacoes", status_code=202)
    def iniciar_verificacao(projeto_id: str, tarefas: BackgroundTasks) -> dict[str, Any]:
        verificacao = c.verificar.iniciar(projeto_id)
        tarefas.add_task(c.verificar.executar, verificacao.id)
        return dto.verificacao(verificacao)

    @app.get("/api/verificacoes/{verificacao_id}")
    def obter_verificacao(verificacao_id: str) -> dict[str, Any]:
        verificacao = c.repositorio.get_verificacao(verificacao_id)
        if verificacao is None:
            raise NaoEncontradoError("Verificação não encontrada.")
        return dto.verificacao(verificacao)

    def relatorio_ou_404(verificacao_id: str):
        relatorio = c.repositorio.get_relatorio(verificacao_id)
        if relatorio is None:
            raise NaoEncontradoError("Relatório não encontrado (a verificação terminou?).")
        return relatorio

    @app.get("/api/verificacoes/{verificacao_id}/relatorio")
    def obter_relatorio(verificacao_id: str) -> dict[str, Any]:
        relatorio = relatorio_ou_404(verificacao_id)
        projeto = projeto_ou_404(relatorio.projeto_id)
        return dto.relatorio(relatorio, projeto.modelo)

    @app.get("/api/verificacoes/{verificacao_id}/relatorio.html")
    def relatorio_html(verificacao_id: str) -> FileResponse:
        relatorio_ou_404(verificacao_id)
        caminho = c.repositorio.relatorio_file(verificacao_id, "relatorio.html")
        if caminho is None:
            raise NaoEncontradoError("Relatório HTML não encontrado.")
        return FileResponse(caminho, media_type="text/html; charset=utf-8")

    @app.get("/api/verificacoes/{verificacao_id}/resultado.bcf")
    def resultado_bcf(verificacao_id: str) -> FileResponse:
        caminho = c.repositorio.relatorio_file(verificacao_id, "resultado.bcf")
        if caminho is None:
            raise NaoEncontradoError("BCF não encontrado para esta verificação.")
        return FileResponse(
            caminho,
            media_type="application/octet-stream",
            filename=f"editalcheck-{verificacao_id}.bcf",
        )

    # ------------------------------------------------------------------ frontend

    frontend = c.settings.pasta_frontend
    # No Windows, o registro pode mapear .js para text/plain e quebrar os workers.
    for tipo, extensao in (
        ("text/javascript", ".js"),
        ("text/javascript", ".mjs"),
        ("application/wasm", ".wasm"),
        ("text/css", ".css"),
        ("image/svg+xml", ".svg"),
    ):
        mimetypes.add_type(tipo, extensao)
    if (frontend / "index.html").exists():
        app.mount("/", StaticFiles(directory=frontend, html=True), name="frontend")
    else:

        @app.get("/")
        def raiz() -> dict[str, str]:
            return {
                "mensagem": "EditalCheck API. Gere o frontend com `npm run build` em frontend/."
            }

    return app
