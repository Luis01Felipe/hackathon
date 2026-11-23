"""API HTTP do EditalCheck (FastAPI). Contrato em docs/api.md."""

import logging
import mimetypes
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from editalcheck import __version__
from editalcheck.application.errors import (
    ConflitoError,
    EditalCheckError,
    EntradaInvalidaError,
    NaoEncontradoError,
)
from editalcheck.application.use_cases.gerar_ids import ARQUIVO_IDS
from editalcheck.application.use_cases.gerar_relatorio import ARQUIVO_BCF, ARQUIVO_HTML
from editalcheck.application.use_cases.importar_documentos import ARQUIVO_EDITAL, ARQUIVO_MODELO
from editalcheck.application.use_cases.importar_licoes import MAX_DOCUMENTOS
from editalcheck.bootstrap import Container, configurar_logs, construir
from editalcheck.config import carregar
from editalcheck.domain.versao_ifc import VERSOES_IDS
from editalcheck.entrypoints.api import dto

logger = logging.getLogger("editalcheck.api")
TAMANHO_BLOCO = 1024 * 1024
MB = 1024 * 1024
# Edital e modelo podem chegar no limite de cada arquivo; as lições somam pouco.
FOLGA_LICOES_MB = 50
STATUS_ERRO = {NaoEncontradoError: 404, ConflitoError: 409, EntradaInvalidaError: 422}
TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ARQUIVO_LICOES_DEMO = "licoes_aprendidas.txt"
AVISO_IA = (
    "Trechos do edital e das lições aprendidas são enviados à API paga do Google Gemini para "
    "interpretação. Na API paga, o Google não usa esses dados para treinar modelos. Nada fica "
    "gravado no servidor do EditalCheck."
)


_REQUEST_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_CAMINHOS_DOCS = ("/docs", "/redoc")
# O app usa wasm (web-ifc), workers (pdf.js e Fragments) e atributos style; nada de script inline.
CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; "
    "connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; "
    "frame-ancestors 'self'"
)
CABECALHOS_SEGURANCA = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class CabecalhosMiddleware:
    """Request id em toda resposta (para correlacionar com o log) e cabeçalhos de segurança.

    ASGI puro, e não ``BaseHTTPMiddleware``: não interfere nas tarefas em segundo plano.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        recebido = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = recebido if _REQUEST_ID.match(recebido) else uuid.uuid4().hex[:16]
        scope.setdefault("state", {})["request_id"] = request_id
        documentacao = scope["path"].startswith(_CAMINHOS_DOCS)

        async def enviar(mensagem: Message) -> None:
            if mensagem["type"] == "http.response.start":
                cabecalhos = MutableHeaders(scope=mensagem)
                cabecalhos["X-Request-ID"] = request_id
                for nome, valor in CABECALHOS_SEGURANCA.items():
                    cabecalhos.setdefault(nome, valor)
                html = cabecalhos.get("content-type", "").startswith("text/html")
                if html and not documentacao:
                    cabecalhos.setdefault("Content-Security-Policy", CSP)
            await send(mensagem)

        await self.app(scope, receive, enviar)


class _Orcamento:
    """Bytes que ainda cabem na requisição (soma de todos os arquivos enviados)."""

    def __init__(self, total_mb: int) -> None:
        self.total_mb = total_mb
        self.restante = total_mb * MB


async def _ler_limitado(arquivo: UploadFile, limite_mb: int, orcamento: _Orcamento) -> bytes:
    limite = limite_mb * MB
    partes: list[bytes] = []
    total = 0
    while bloco := await arquivo.read(TAMANHO_BLOCO):
        total += len(bloco)
        orcamento.restante -= len(bloco)
        if total > limite:
            raise HTTPException(413, f"Arquivo acima do limite de {limite_mb} MB.")
        if orcamento.restante < 0:
            raise HTTPException(413, f"Os arquivos somam mais de {orcamento.total_mb} MB.")
        partes.append(bloco)
    return b"".join(partes)


def content_disposition(modo: str, nome: str) -> str:
    """Cabeçalho Content-Disposition seguro para qualquer nome de arquivo (RFC 6266 e 5987).

    Cabeçalhos HTTP só aceitam latin-1: nomes com "—", emoji ou aspas derrubavam a rota
    com UnicodeEncodeError. Vai um nome ASCII de reserva e o nome real em ``filename*``.
    """
    limpo = re.sub(r'[\x00-\x1f\x7f"\\]', "_", nome).strip() or "arquivo"
    ascii_ = unicodedata.normalize("NFKD", limpo).encode("ascii", "ignore").decode("ascii")
    reserva = re.sub(r"[^A-Za-z0-9._ ()-]", "_", ascii_).strip() or "arquivo"
    return f"{modo}; filename=\"{reserva}\"; filename*=UTF-8''{quote(limpo, safe='')}"


def _anexo(conteudo: bytes, tipo: str, nome: str) -> Response:
    return Response(
        conteudo,
        media_type=tipo,
        headers={"Content-Disposition": content_disposition("attachment", nome)},
    )


def criar_app(container: Container | None = None) -> FastAPI:
    if container is None:
        settings = carregar()
        configurar_logs(settings.nivel_log)
        container = construir(settings)
    c = container
    docs = c.settings.docs_ativos
    app = FastAPI(
        title="EditalCheck API",
        version=__version__,
        description="Verificador bidirecional Edital × IFC (IFC, IDS, BCF, bSDD).",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.add_middleware(CabecalhosMiddleware)

    @app.exception_handler(EditalCheckError)
    async def _erro_negocio(_: Request, erro: EditalCheckError) -> JSONResponse:
        status = next((s for tipo, s in STATUS_ERRO.items() if isinstance(erro, tipo)), 400)
        return JSONResponse({"detail": str(erro)}, status_code=status)

    @app.exception_handler(Exception)
    async def _erro_inesperado(request: Request, erro: Exception) -> JSONResponse:
        """Erro não previsto: JSON com um código para o suporte; o detalhe fica só no log."""
        codigo = getattr(request.state, "request_id", None) or uuid.uuid4().hex[:16]
        logger.error(
            "Erro inesperado [%s] %s %s", codigo, request.method, request.url.path, exc_info=erro
        )
        return JSONResponse(
            {"detail": f"Erro interno do servidor. Código para o suporte: {codigo}."},
            status_code=500,
            headers={"X-Request-ID": codigo},
        )

    def projeto_ou_404(projeto_id: str):
        projeto = c.repositorio.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado (pode ter expirado ou sido apagado).")
        return projeto

    # ------------------------------------------------------------------ configuração

    @app.get("/api/saude")
    def saude() -> dict[str, str]:
        """Usado pelo healthcheck do contêiner: o processo responde."""
        return {"status": "ok", "versao": __version__}

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        s = c.settings
        demo = s.pasta_demo
        return {
            "versao": __version__,
            "modo_ia": s.modo_ia,
            "modelo_llm": s.gemini_model if s.llm_ativo else None,
            "bsdd_ativo": s.bsdd_ativo,
            "demo_disponivel": (demo / "edital.pdf").exists() and (demo / "modelo.ifc").exists(),
            "demo_com_licoes": (demo / ARQUIVO_LICOES_DEMO).exists(),
            "limite_upload_mb": s.limite_upload_mb,
            "modo_dados": s.modo_dados,
            "ttl_min": s.ttl_min if s.modo_dados == "efemero" else None,
            "disponivel_ate": s.disponivel_ate,
            "aviso_ia": AVISO_IA if s.llm_ativo else None,
            "documentos_contexto": list(c.documentos_contexto),
            "versoes_ifc": list(VERSOES_IDS),
        }

    # ------------------------------------------------------------------ projetos

    @app.post("/api/projetos", status_code=201)
    async def criar_projeto(
        edital: UploadFile = File(...),
        modelo: UploadFile | None = File(None),
        licoes: list[UploadFile] | None = File(None),
        versao_ifc: str | None = Form(None),
    ) -> dict[str, Any]:
        limite = c.settings.limite_upload_mb
        if licoes and len(licoes) > MAX_DOCUMENTOS:
            raise EntradaInvalidaError(
                f"Envie até {MAX_DOCUMENTOS} documentos de lições aprendidas."
            )
        orcamento = _Orcamento(2 * limite + FOLGA_LICOES_MB)
        pdf = await _ler_limitado(edital, limite, orcamento)
        ifc = await _ler_limitado(modelo, limite, orcamento) if modelo and modelo.filename else None
        documentos = [
            (
                await _ler_limitado(arquivo, limite, orcamento),
                Path(arquivo.filename or "licoes.txt").name,
            )
            for arquivo in licoes or []
            if arquivo.filename
        ]
        # Ler PDF e IFC e chamar o LLM bloqueia: roda numa thread para não travar o servidor.
        projeto = await run_in_threadpool(
            c.importar.executar,
            pdf,
            Path(edital.filename or "edital.pdf").name,
            ifc,
            Path(modelo.filename).name if modelo and modelo.filename else None,
            documentos,
            versao_ifc or None,
        )
        return dto.projeto_resumo(projeto, c.settings.modo_ia)

    @app.post("/api/projetos/demo", status_code=201)
    def criar_projeto_demo(com_licoes: bool = True) -> dict[str, Any]:
        pasta = c.settings.pasta_demo
        pdf, ifc, licoes = pasta / "edital.pdf", pasta / "modelo.ifc", pasta / ARQUIVO_LICOES_DEMO
        if not pdf.exists() or not ifc.exists():
            raise NaoEncontradoError("Dados de demonstração não encontrados em data/demo.")
        documentos = [(licoes.read_bytes(), licoes.name)] if com_licoes and licoes.exists() else []
        projeto = c.importar.executar(
            pdf.read_bytes(), pdf.name, ifc.read_bytes(), ifc.name, documentos
        )
        return dto.projeto_resumo(projeto, c.settings.modo_ia)

    @app.get("/api/projetos/{projeto_id}")
    def obter_projeto(projeto_id: str) -> dict[str, Any]:
        return dto.projeto_resumo(projeto_ou_404(projeto_id), c.settings.modo_ia)

    @app.delete("/api/projetos/{projeto_id}", status_code=204)
    def apagar_projeto(projeto_id: str) -> Response:
        c.excluir.executar(projeto_id)
        return Response(status_code=204)

    @app.get("/api/projetos/{projeto_id}/topicos")
    def listar_topicos(projeto_id: str) -> list[dict[str, Any]]:
        return dto.topicos(projeto_ou_404(projeto_id))

    @app.get("/api/projetos/{projeto_id}/modelo.ifc")
    def baixar_modelo(projeto_id: str) -> Response:
        projeto = projeto_ou_404(projeto_id)
        conteudo = c.repositorio.read_file(projeto.id, ARQUIVO_MODELO)
        if conteudo is None:
            raise NaoEncontradoError("Este projeto não tem modelo IFC.")
        return _anexo(conteudo, "application/x-step", projeto.modelo.arquivo or ARQUIVO_MODELO)

    @app.get("/api/projetos/{projeto_id}/edital.pdf")
    def ver_edital(projeto_id: str) -> Response:
        projeto = projeto_ou_404(projeto_id)
        conteudo = c.repositorio.read_file(projeto.id, ARQUIVO_EDITAL)
        if conteudo is None:
            raise NaoEncontradoError("O edital deste projeto não está disponível.")
        return Response(
            conteudo,
            media_type="application/pdf",
            headers={"Content-Disposition": content_disposition("inline", projeto.edital.arquivo)},
        )

    @app.get("/api/projetos/{projeto_id}/topicos/regioes")
    def regioes_topicos(projeto_id: str) -> dict[str, list[dict[str, Any]]]:
        return {
            topico_id: [dto.regiao(r) for r in regioes]
            for topico_id, regioes in c.localizar.topicos(projeto_id).items()
        }

    @app.get("/api/projetos/{projeto_id}/consumo")
    def consumo(projeto_id: str) -> list[dict[str, Any]]:
        projeto_ou_404(projeto_id)
        return dto.consumo(c.medidor.consumo(projeto_id))

    # ------------------------------------------------------------------ lições e marcos

    @app.post("/api/projetos/{projeto_id}/licoes")
    async def enviar_licoes(
        projeto_id: str, licoes: list[UploadFile] = File(...)
    ) -> dict[str, Any]:
        limite = c.settings.limite_upload_mb
        if len(licoes) > MAX_DOCUMENTOS:
            raise EntradaInvalidaError(
                f"Envie até {MAX_DOCUMENTOS} documentos de lições aprendidas."
            )
        orcamento = _Orcamento(limite + FOLGA_LICOES_MB)
        documentos = [
            (
                await _ler_limitado(arquivo, limite, orcamento),
                Path(arquivo.filename or "licoes.txt").name,
            )
            for arquivo in licoes
        ]
        resultado = await run_in_threadpool(c.importar_licoes.executar, projeto_id, documentos)
        projeto = projeto_ou_404(projeto_id)
        return {
            "licoes": dto.licoes(projeto),
            "avisos": list(resultado.avisos),
            "descartadas": resultado.descartadas,
        }

    @app.get("/api/projetos/{projeto_id}/licoes")
    def listar_licoes(projeto_id: str) -> list[dict[str, Any]]:
        return dto.licoes(projeto_ou_404(projeto_id))

    @app.get("/api/projetos/{projeto_id}/marcos")
    def listar_marcos(projeto_id: str) -> list[dict[str, Any]]:
        return dto.marcos(projeto_ou_404(projeto_id))

    @app.put("/api/projetos/{projeto_id}/marcos")
    def definir_marcos(projeto_id: str, corpo: dto.DefinirMarcosRequest) -> list[dict[str, Any]]:
        c.revisar_eir.definir_marcos(projeto_id, [m.model_dump() for m in corpo.marcos])
        return dto.marcos(projeto_ou_404(projeto_id))

    # ------------------------------------------------------------------ requisitos de informação

    @app.post("/api/projetos/{projeto_id}/ir")
    def gerar_ir(projeto_id: str, corpo: dto.CriarEirRequest) -> dict[str, Any]:
        resultado = c.gerar_eir.executar(projeto_id, corpo.topicos)
        return dto.eir_resposta(resultado.eir, resultado.avisos, resultado.descartados)

    @app.get("/api/projetos/{projeto_id}/ir")
    def obter_ir(projeto_id: str) -> dict[str, Any]:
        projeto = projeto_ou_404(projeto_id)
        if projeto.eir is None:
            raise NaoEncontradoError("Os requisitos de informação (IR) ainda não foram gerados.")
        return dto.eir_resposta(projeto.eir)

    @app.patch("/api/projetos/{projeto_id}/ir/requisitos/{requisito_id}")
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
                campos = corpo.campos.model_dump(exclude_unset=True)
                requisito = revisar.editar(projeto_id, requisito_id, campos)
        return dto.requisito(requisito)

    @app.post("/api/projetos/{projeto_id}/ir/aprovar-todos")
    def aprovar_todos(projeto_id: str, corpo: dto.AprovarTodosRequest) -> dict[str, Any]:
        return dto.eir_resposta(c.revisar_eir.aprovar_todos(projeto_id, corpo.somente_verificaveis))

    @app.post("/api/projetos/{projeto_id}/ir/requisitos", status_code=201)
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

    @app.get("/api/projetos/{projeto_id}/ir.xlsx")
    def exportar_ir(projeto_id: str) -> Response:
        projeto = projeto_ou_404(projeto_id)
        if projeto.eir is None:
            raise NaoEncontradoError("Os requisitos de informação (IR) ainda não foram gerados.")
        conteudo = c.exportador_eir.to_xlsx(projeto.eir, projeto)
        return _anexo(conteudo, TIPO_XLSX, f"requisitos-informacao-ir-{projeto.id}.xlsx")

    # ------------------------------------------------------------------ IDS

    @app.post("/api/projetos/{projeto_id}/ids")
    def gerar_ids(projeto_id: str, corpo: dto.GerarIdsRequest | None = None) -> dict[str, Any]:
        corpo = corpo or dto.GerarIdsRequest()
        resultado = c.gerar_ids.executar(projeto_id, corpo.marco_id, corpo.versao_ifc)
        return {
            "especificacoes": resultado.especificacoes,
            "valido": resultado.valido,
            "erros": list(resultado.erros),
            "avisos": list(resultado.avisos),
            "requisitos_incluidos": list(resultado.requisitos_incluidos),
            "escopo": resultado.escopo,
            "marco_id": resultado.marco_id,
            "versao_ifc": resultado.versao_ifc,
            "url": f"/api/projetos/{projeto_id}/ids.xml" if resultado.valido else None,
        }

    @app.get("/api/projetos/{projeto_id}/ids.xml")
    def baixar_ids(projeto_id: str) -> Response:
        projeto = projeto_ou_404(projeto_id)
        conteudo = c.repositorio.read_file(projeto.id, ARQUIVO_IDS)
        if conteudo is None:
            raise NaoEncontradoError("O IDS ainda não foi gerado.")
        escopo = projeto.ids_marco_id or "contrato"
        return _anexo(conteudo, "application/xml", f"editalcheck-{projeto.id}-{escopo}.ids")

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

    def arquivo_relatorio(verificacao_id: str, nome: str) -> bytes:
        conteudo = c.repositorio.read_relatorio_file(verificacao_id, nome)
        if conteudo is None:
            raise NaoEncontradoError("Arquivo não encontrado para esta verificação.")
        return conteudo

    @app.get("/api/verificacoes/{verificacao_id}/relatorio")
    def obter_relatorio(verificacao_id: str) -> dict[str, Any]:
        relatorio = relatorio_ou_404(verificacao_id)
        projeto = projeto_ou_404(relatorio.projeto_id)
        return dto.relatorio(relatorio, projeto.modelo)

    @app.get("/api/verificacoes/{verificacao_id}/relatorio.html")
    def relatorio_html(verificacao_id: str) -> Response:
        relatorio_ou_404(verificacao_id)
        return Response(
            arquivo_relatorio(verificacao_id, ARQUIVO_HTML), media_type="text/html; charset=utf-8"
        )

    @app.get("/api/verificacoes/{verificacao_id}/resultado.bcf")
    def resultado_bcf(verificacao_id: str) -> Response:
        conteudo = c.repositorio.read_relatorio_file(verificacao_id, ARQUIVO_BCF)
        if conteudo is None:
            raise NaoEncontradoError("BCF não encontrado para esta verificação.")
        return _anexo(conteudo, "application/octet-stream", f"editalcheck-{verificacao_id}.bcf")

    @app.patch("/api/verificacoes/{verificacao_id}/apontamentos/{apontamento_id}")
    def decidir(
        verificacao_id: str, apontamento_id: str, corpo: dto.DecisaoRequest
    ) -> dict[str, Any]:
        decisao = c.decidir.executar(
            verificacao_id, apontamento_id, corpo.status, corpo.comentario, corpo.autor
        )
        return {
            "apontamento_id": decisao.apontamento_id,
            "status": decisao.status.value,
            "comentario": decisao.comentario,
            "autor": decisao.autor,
            "data": decisao.data,
        }

    @app.get("/api/verificacoes/{verificacao_id}/regioes")
    def regioes_apontamentos(verificacao_id: str) -> list[dict[str, Any]]:
        return [
            {
                "apontamento_id": local.apontamento_id,
                "localizado": local.localizado,
                "paginas": list(local.paginas),
                "regioes": [dto.regiao(r) for r in local.regioes],
            }
            for local in c.localizar.apontamentos(verificacao_id)
        ]

    @app.get("/api/verificacoes/{verificacao_id}/edital-anotado.pdf")
    def edital_anotado(verificacao_id: str) -> Response:
        return _anexo(
            c.exportar_edital.anotado(verificacao_id),
            "application/pdf",
            f"edital-anotado-{verificacao_id}.pdf",
        )

    @app.get("/api/verificacoes/{verificacao_id}/esclarecimentos.xlsx")
    def esclarecimentos(verificacao_id: str) -> Response:
        return _anexo(
            c.exportar_edital.matriz(verificacao_id),
            TIPO_XLSX,
            f"esclarecimentos-{verificacao_id}.xlsx",
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
