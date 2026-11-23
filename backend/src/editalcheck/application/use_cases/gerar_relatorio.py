"""Casos de uso do relatório: montar (JSON), publicar (HTML e BCF), registrar
decisões humanas e exportar o edital anotado e a matriz de esclarecimentos."""

from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from threading import Lock

from editalcheck.application.consumo import ExecutorComContexto, MedidorConsumo
from editalcheck.application.errors import EntradaInvalidaError, NaoEncontradoError
from editalcheck.application.observability import agora, etapa, logger
from editalcheck.application.ports import (
    AuditLog,
    BcfWriter,
    ClarificationExporter,
    EditalAnnotator,
    ElementGeometry,
    ProjectRepository,
    RecommendationWriter,
    ReportWriter,
)
from editalcheck.application.use_cases.gerar_ids import versao_padrao
from editalcheck.application.use_cases.importar_documentos import ARQUIVO_EDITAL
from editalcheck.domain import findings, indicators
from editalcheck.domain.models import (
    Apontamento,
    Cobertura,
    DecisaoApontamento,
    ItemChecklist,
    ModeloResumo,
    Projeto,
    ReferenciaTempoManual,
    Relatorio,
    ResultadoChecklist,
    ResultadoEspecificacao,
    Severidade,
    StatusDecisao,
    VerificacaoLicao,
)
from editalcheck.domain.vocabulary import filtrar_referencias

MAX_PARALELO = 4
ARQUIVO_HTML = "relatorio.html"
ARQUIVO_BCF = "resultado.bcf"
SEVERIDADES_COM_IA = frozenset({Severidade.ALTA, Severidade.MEDIA})
MAX_PDFS_EM_CACHE = 8


@dataclass(frozen=True)
class ResultadosAnalises:
    resultados_ids: tuple[ResultadoEspecificacao, ...] = ()
    cobertura: Cobertura | None = None
    checklist: tuple[ResultadoChecklist, ...] = ()
    apontamentos: tuple[Apontamento, ...] = ()
    verificacoes_licoes: tuple[VerificacaoLicao, ...] = ()


@dataclass(frozen=True)
class PrecosLlm:
    entrada_usd_mtok: float | None = None
    saida_usd_mtok: float | None = None
    fonte: str = ""


class GerarRelatorio:
    def __init__(
        self,
        repositorio: ProjectRepository,
        recomendador: RecommendationWriter,
        recomendador_reserva: RecommendationWriter,
        escritor_html: ReportWriter,
        escritor_bcf: BcfWriter,
        geometria: ElementGeometry,
        itens_checklist: Sequence[ItemChecklist],
        modo_ia: str,
        medidor: MedidorConsumo,
        precos: PrecosLlm,
        tempo_manual: ReferenciaTempoManual,
        documentos_contexto: Sequence[str] = (),
        limite_recomendacoes_ia: int = 30,
        paralelismo: int = MAX_PARALELO,
    ) -> None:
        self._paralelismo = max(1, paralelismo)
        self._repo = repositorio
        self._recomendador = recomendador
        self._reserva = recomendador_reserva
        self._html = escritor_html
        self._bcf = escritor_bcf
        self._geometria = geometria
        self._itens = tuple(itens_checklist)
        self._modo_ia = modo_ia
        self._medidor = medidor
        self._precos = precos
        self._tempo_manual = tempo_manual
        self._contexto = tuple(documentos_contexto)
        self._limite = limite_recomendacoes_ia

    def _recomendar(self, apontamento: Apontamento) -> tuple[Apontamento, bool]:
        try:
            recomendacao = self._recomendador.write(apontamento, apontamento.referencias)
        except Exception as erro:  # RNF-02: fallback por template
            logger.warning("Recomendação pelo LLM falhou em %s: %s", apontamento.id, erro)
            return apontamento, False
        if not recomendacao.gerado_por_ia:
            return apontamento, True
        referencias, removida = filtrar_referencias(
            recomendacao.referencias, apontamento.referencias
        )
        return (
            replace(
                apontamento,
                como_agir=recomendacao.como_agir or apontamento.como_agir,
                por_que=recomendacao.por_que or apontamento.por_que,
                referencias=referencias or apontamento.referencias,
                gerado_por_ia=True,
                referencia_a_confirmar=apontamento.referencia_a_confirmar or removida,
            ),
            True,
        )

    def recomendar(
        self, apontamentos: Sequence[Apontamento]
    ) -> tuple[list[Apontamento], list[str]]:
        """RF-163: o LLM só reescreve severidade alta e média. A baixa usa o texto padrão."""
        alvo_ids = {
            a.id
            for a in apontamentos
            if a.severidade in SEVERIDADES_COM_IA and not a.verificacao_manual
        }
        alvo = [a for a in apontamentos if a.id in alvo_ids][: self._limite]
        with (
            etapa("recomendacoes", total=len(alvo)),
            ExecutorComContexto(self._paralelismo) as executor,
        ):
            resultados = list(executor.map(self._recomendar, alvo))
        avisos: list[str] = []
        if any(not ok for _, ok in resultados):
            avisos.append("LLM indisponível para parte das recomendações: usados textos padrão.")
        reescritos = {a.id: a for a, _ in resultados}
        return [reescritos.get(a.id, a) for a in apontamentos], avisos

    def _caixas(self, conteudo_ifc: bytes | None, analises: ResultadosAnalises) -> dict:
        if not conteudo_ifc:
            return {}
        guids = [g for a in analises.apontamentos for g in a.elementos]
        guids += [f.global_id for r in analises.resultados_ids for f in r.falhas]
        try:
            with etapa("relatorio.geometria", elementos=len(set(guids))):
                return self._geometria.boxes(conteudo_ifc, guids)
        except Exception as erro:  # a coordenada é um extra: o relatório sai sem ela
            logger.warning("Falha ao calcular a geometria dos elementos: %s", erro)
            return {}

    def montar(
        self,
        verificacao_id: str,
        projeto: Projeto,
        analises: ResultadosAnalises,
        avisos: Sequence[str],
        duracoes: dict[str, float],
        conteudo_ifc: bytes | None = None,
    ) -> Relatorio:
        requisitos = projeto.eir.requisitos if projeto.eir else ()
        numerados = findings.numerar(analises.apontamentos)
        recomendados, avisos_rec = self.recomendar(numerados)
        estados = indicators.estado_elementos(analises.resultados_ids)
        consumo = self._medidor.consumo(projeto.id)
        marco = projeto.marco(projeto.ids_marco_id)
        return Relatorio(
            verificacao_id=verificacao_id,
            projeto_id=projeto.id,
            gerado_em=agora(),
            edital_arquivo=projeto.edital.arquivo,
            modelo_arquivo=projeto.modelo.arquivo,
            schema_ifc=projeto.modelo.schema,
            modo_ia=self._modo_ia,
            indicadores=indicators.calcular(
                analises.resultados_ids,
                analises.cobertura,
                analises.checklist,
                requisitos,
                recomendados,
                analises.verificacoes_licoes,
            ),
            apontamentos=tuple(recomendados),
            resultados_ids=analises.resultados_ids,
            cobertura=analises.cobertura,
            checklist=analises.checklist,
            itens_checklist=self._itens,
            requisitos=requisitos,
            estado_elementos=estados,
            avisos=tuple(dict.fromkeys([*avisos, *avisos_rec])),
            duracoes_s=duracoes,
            escopo=marco.nome if marco else "Contrato inteiro",
            versao_ifc_ids=projeto.ids_versao_ifc or versao_padrao(projeto),
            sem_modelo=projeto.modelo.sem_arquivo,
            licoes=projeto.licoes,
            verificacoes_licoes=analises.verificacoes_licoes,
            caixas=self._caixas(conteudo_ifc, analises),
            consumo=consumo,
            custo=indicators.calcular_custo(
                consumo,
                self._precos.entrada_usd_mtok,
                self._precos.saida_usd_mtok,
                self._precos.fonte,
            ),
            tempo_manual=self._tempo_manual,
            contexto_usado=self._contexto if self._modo_ia != "offline" else (),
        )

    def publicar(self, relatorio: Relatorio, modelo: ModeloResumo) -> Relatorio:
        avisos = list(relatorio.avisos)
        bcf: bytes | None = None
        if not relatorio.sem_modelo:
            with etapa("relatorio.bcf", verificacao=relatorio.verificacao_id):
                try:
                    bcf = self._bcf.write(relatorio, modelo)
                except Exception as erro:  # o relatório sai mesmo sem BCF
                    logger.warning("Falha ao gerar o BCF: %s", erro)
                    avisos.append("Não foi possível gerar o BCF nesta verificação.")
        relatorio = replace(relatorio, avisos=tuple(avisos))
        self._repo.save_relatorio(relatorio)
        self._escrever_html(relatorio)
        if bcf is not None:
            self._repo.write_relatorio_file(relatorio.verificacao_id, ARQUIVO_BCF, bcf)
        return relatorio

    def _escrever_html(self, relatorio: Relatorio) -> None:
        with etapa("relatorio.html", verificacao=relatorio.verificacao_id):
            html = self._html.write_html(relatorio)
        self._repo.write_relatorio_file(
            relatorio.verificacao_id, ARQUIVO_HTML, html.encode("utf-8")
        )

    def reescrever_html(self, relatorio: Relatorio) -> None:
        self._repo.save_relatorio(relatorio)
        self._escrever_html(relatorio)


class DecidirApontamento:
    """Registra a decisão humana sobre um apontamento (RF-150, salvaguarda G2).

    A decisão nunca apaga o apontamento: um apontamento dispensado continua no
    relatório, com a justificativa e o autor, e continua nos indicadores.
    """

    def __init__(
        self, repositorio: ProjectRepository, relatorio: GerarRelatorio, auditoria: AuditLog
    ) -> None:
        self._repo = repositorio
        self._relatorio = relatorio
        self._auditoria = auditoria

    def executar(
        self,
        verificacao_id: str,
        apontamento_id: str,
        status: str,
        comentario: str = "",
        autor: str = "",
    ) -> DecisaoApontamento:
        relatorio = self._repo.get_relatorio(verificacao_id)
        if relatorio is None:
            raise NaoEncontradoError("Relatório não encontrado.")
        if not any(a.id == apontamento_id for a in relatorio.apontamentos):
            raise NaoEncontradoError(f"Apontamento {apontamento_id} não encontrado.")
        try:
            decisao = DecisaoApontamento(
                apontamento_id=apontamento_id,
                status=StatusDecisao(status),
                comentario=comentario.strip()[:1000],
                autor=autor.strip()[:120],
                data=agora(),
            )
        except ValueError as erro:
            raise EntradaInvalidaError(str(erro)) from erro
        outras = [d for d in relatorio.decisoes if d.apontamento_id != apontamento_id]
        decisoes = outras if decisao.status == StatusDecisao.PENDENTE else [*outras, decisao]
        self._relatorio.reescrever_html(replace(relatorio, decisoes=tuple(decisoes)))
        self._auditoria.record(
            "apontamento.decidir",
            verificacao=verificacao_id,
            apontamento=apontamento_id,
            status=decisao.status.value,
        )
        return decisao


class ExportarEdital:
    """Edital anotado em PDF (RF-151) e matriz de esclarecimentos em XLSX (RF-152)."""

    def __init__(
        self,
        repositorio: ProjectRepository,
        anotador: EditalAnnotator,
        esclarecimentos: ClarificationExporter,
    ) -> None:
        self._repo = repositorio
        self._anotador = anotador
        self._esclarecimentos = esclarecimentos
        # O PDF anotado só muda quando as decisões mudam: cache por verificação e decisões.
        self._cache: OrderedDict[tuple, bytes] = OrderedDict()
        self._trava = Lock()

    def _relatorio(self, verificacao_id: str) -> Relatorio:
        relatorio = self._repo.get_relatorio(verificacao_id)
        if relatorio is None:
            raise NaoEncontradoError("Relatório não encontrado.")
        return relatorio

    def anotado(self, verificacao_id: str) -> bytes:
        relatorio = self._relatorio(verificacao_id)
        chave = (verificacao_id, relatorio.decisoes)
        with self._trava:
            if chave in self._cache:
                return self._cache[chave]
        pdf = self._repo.read_file(relatorio.projeto_id, ARQUIVO_EDITAL)
        if pdf is None:
            raise NaoEncontradoError("O edital deste projeto não está mais disponível.")
        with etapa(
            "relatorio.edital_anotado",
            verificacao=verificacao_id,
            apontamentos=len(relatorio.apontamentos),
        ):
            conteudo = self._anotador.annotate(pdf, relatorio.apontamentos, relatorio.decisoes)
        with self._trava:
            self._cache[chave] = conteudo
            while len(self._cache) > MAX_PDFS_EM_CACHE:
                self._cache.popitem(last=False)
        return conteudo

    def matriz(self, verificacao_id: str) -> bytes:
        return self._esclarecimentos.to_xlsx(self._relatorio(verificacao_id))
