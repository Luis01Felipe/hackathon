"""Caso de uso: montar o relatório (JSON), o HTML e o BCF a partir das análises."""

from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from editalcheck.application.observability import agora, etapa, logger
from editalcheck.application.ports import (
    BcfWriter,
    ProjectRepository,
    RecommendationWriter,
    ReportWriter,
)
from editalcheck.domain import findings, indicators
from editalcheck.domain.models import (
    Apontamento,
    Cobertura,
    ItemChecklist,
    Projeto,
    Relatorio,
    ResultadoChecklist,
    ResultadoEspecificacao,
)
from editalcheck.domain.vocabulary import filtrar_referencias

MAX_PARALELO = 4


@dataclass(frozen=True)
class ResultadosAnalises:
    resultados_ids: tuple[ResultadoEspecificacao, ...] = ()
    cobertura: Cobertura | None = None
    checklist: tuple[ResultadoChecklist, ...] = ()
    apontamentos: tuple[Apontamento, ...] = ()


class GerarRelatorio:
    def __init__(
        self,
        repositorio: ProjectRepository,
        recomendador: RecommendationWriter,
        recomendador_reserva: RecommendationWriter,
        escritor_html: ReportWriter,
        escritor_bcf: BcfWriter,
        itens_checklist: Sequence[ItemChecklist],
        modo_ia: str,
        limite_recomendacoes_ia: int = 30,
        paralelismo: int = MAX_PARALELO,
    ) -> None:
        self._paralelismo = max(1, paralelismo)
        self._repo = repositorio
        self._recomendador = recomendador
        self._reserva = recomendador_reserva
        self._html = escritor_html
        self._bcf = escritor_bcf
        self._itens = tuple(itens_checklist)
        self._modo_ia = modo_ia
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
        alvo = list(apontamentos[: self._limite])
        with (
            etapa("recomendacoes", total=len(alvo)),
            ThreadPoolExecutor(self._paralelismo) as executor,
        ):
            resultados = list(executor.map(self._recomendar, alvo))
        avisos: list[str] = []
        if any(not ok for _, ok in resultados):
            avisos.append("LLM indisponível para parte das recomendações: usados textos padrão.")
        return [a for a, _ in resultados] + list(apontamentos[self._limite :]), avisos

    def montar(
        self,
        verificacao_id: str,
        projeto: Projeto,
        analises: ResultadosAnalises,
        avisos: Sequence[str],
        duracoes: dict[str, float],
    ) -> Relatorio:
        requisitos = projeto.eir.requisitos if projeto.eir else ()
        numerados = findings.numerar(analises.apontamentos)
        recomendados, avisos_rec = self.recomendar(numerados)
        estados = indicators.estado_elementos(analises.resultados_ids)
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
        )

    def publicar(self, relatorio: Relatorio, caminho_ifc: str) -> Relatorio:
        avisos = list(relatorio.avisos)
        bcf: bytes | None = None
        with etapa("relatorio.bcf", verificacao=relatorio.verificacao_id):
            try:
                bcf = self._bcf.write(relatorio, caminho_ifc)
            except Exception as erro:  # o relatório sai mesmo sem BCF
                logger.warning("Falha ao gerar o BCF: %s", erro)
                avisos.append("Não foi possível gerar o BCF nesta verificação.")
        relatorio = replace(relatorio, avisos=tuple(avisos))
        with etapa("relatorio.html", verificacao=relatorio.verificacao_id):
            html = self._html.write_html(relatorio)
        self._repo.save_relatorio(relatorio, html, bcf)
        return relatorio
