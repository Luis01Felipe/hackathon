"""Adaptadores das portas de IA sobre o ``StructuredLlm`` (provedor agnóstico).

O LLM só interpreta texto e devolve JSON validado. Todas as salvaguardas
(S2 a S5) são aplicadas depois, por código determinístico, nos casos de uso.
"""

from collections.abc import Sequence
from dataclasses import replace

from editalcheck.adapters.llm.schemas import (
    AmbiguidadesLLM,
    ChecklistLLM,
    ClassificacaoTopicosLLM,
    ContradicoesLLM,
    EvidenciaLLM,
    ExtracaoLLM,
    LicoesLLM,
    RecomendacaoLLM,
    RequisitoLLM,
    VerificacoesLicoesLLM,
)
from editalcheck.adapters.llm.structured import StructuredLlm
from editalcheck.application.ports import ReferenceContext
from editalcheck.domain import licoes as licoes_domain
from editalcheck.domain.models import (
    AmbiguidadeConfirmada,
    Apontamento,
    Cardinalidade,
    ContextoVocabulario,
    Contradicao,
    Edital,
    Evidencia,
    FonteEvidencia,
    ItemChecagem,
    ItemChecklist,
    LicaoAprendida,
    Recomendacao,
    Referencia,
    Requisito,
    Restricao,
    ResultadoChecklist,
    StatusChecklist,
    TipoFaceta,
    TipoRestricao,
    TipoVerificacao,
    Topico,
    TrechoVago,
    VerificacaoLicao,
)

LIMITE_PROPRIEDADES_POR_CLASSE = 40
LIMITE_TEXTO_CHECKLIST = 60_000
LOTE_AMBIGUIDADES = 20
LIMITE_TEXTO_LICOES = 40_000
LOTE_LICOES = 15


def _evidencia(
    evidencia: EvidenciaLLM | None, fonte: FonteEvidencia = FonteEvidencia.EDITAL
) -> Evidencia | None:
    if evidencia is None:
        return None
    return Evidencia(pagina=evidencia.pagina, trecho=evidencia.trecho, fonte=fonte)


def _texto_com_paginas(documento: Edital, limite: int) -> str:
    return "\n".join(f"[p. {p.numero}]\n{p.texto}" for p in documento.paginas)[:limite]


def _vocabulario(contexto: ContextoVocabulario) -> str:
    linhas: list[str] = []
    for classe, propriedades in contexto.propriedades_por_classe:
        itens: list[str] = []
        for chave in propriedades[:LIMITE_PROPRIEDADES_POR_CLASSE]:
            pset, _, nome = chave.partition(".")
            oficial = contexto.propriedade_oficial(pset, nome)
            tipo = oficial.tipo_dado if oficial and oficial.tipo_dado else "?"
            itens.append(f"{chave}: {tipo}")
        linhas.append(f"- {classe}: " + ", ".join(itens))
    return "\n".join(linhas) or "(nenhuma)"


def requisito_do_llm(item: RequisitoLLM, topico_id: str) -> Requisito:
    restricao = None
    if item.restricao is not None:
        restricao = Restricao(
            tipo=TipoRestricao(item.restricao.tipo),
            valores=tuple(item.restricao.valores),
            minimo=item.restricao.minimo,
            maximo=item.restricao.maximo,
        )
    return Requisito(
        id="TMP",
        topico_id=topico_id,
        descricao=item.descricao.strip(),
        evidencia=Evidencia(pagina=item.evidencia.pagina, trecho=item.evidencia.trecho),
        verificavel_por_ids=item.verificavel_por_ids,
        motivo_nao_verificavel=item.motivo_nao_verificavel,
        ifc_class=item.ifc_class,
        predefined_type=item.predefined_type,
        faceta=TipoFaceta(item.faceta) if item.faceta else None,
        pset=item.pset,
        propriedade=item.propriedade,
        tipo_dado=item.tipo_dado,
        restricao=restricao,
        cardinalidade=Cardinalidade(item.cardinalidade),
        gerado_por="llm",
        ambientes=tuple(a.strip() for a in item.ambientes if a.strip()),
        item_checagem=ItemChecagem(item.item_checagem) if item.item_checagem else None,
        verificacao=TipoVerificacao(item.verificacao) if item.verificacao else None,
    )


class LlmTopicClassifier:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def classify(self, topicos: Sequence[Topico]) -> list[Topico]:
        if not topicos:
            return []
        resposta = self._llm.gerar("topicos", ClassificacaoTopicosLLM, topicos=topicos)
        por_id = {t.id: t for t in resposta.topicos}
        classificados: list[Topico] = []
        for topico in topicos:
            item = por_id.get(topico.id)
            if item is None:
                classificados.append(topico)
                continue
            classificados.append(
                replace(
                    topico,
                    titulo=item.titulo.strip() or topico.titulo,
                    resumo=item.resumo.strip(),
                    relevante_bim=item.relevante_bim,
                )
            )
        return classificados


class LlmRequirementExtractor:
    def __init__(self, llm: StructuredLlm, referencias: ReferenceContext | None = None) -> None:
        self._llm = llm
        self._referencias = referencias

    def extract(self, topico: Topico, contexto: ContextoVocabulario) -> list[Requisito]:
        referencias = self._referencias.select(topico.texto) if self._referencias else []
        resposta = self._llm.gerar(
            "extracao_requisitos",
            ExtracaoLLM,
            topico=topico,
            schema_ifc=contexto.schema,
            classes=contexto.classes_modelo,
            vocabulario=_vocabulario(contexto),
            termos_bsdd=contexto.termos_bsdd,
            ambientes_modelo=contexto.ambientes_modelo,
            referencias=referencias,
        )
        return [requisito_do_llm(item, topico.id) for item in resposta.requisitos]


class LlmLessonExtractor:
    """Lê as lições aprendidas de um documento (PDF ou texto) com o LLM."""

    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def extract(self, documento: Edital) -> list[LicaoAprendida]:
        texto = _texto_com_paginas(documento, LIMITE_TEXTO_LICOES)
        resposta = self._llm.gerar("licoes", LicoesLLM, documento=documento.arquivo, texto=texto)
        licoes: list[LicaoAprendida] = []
        for indice, item in enumerate(resposta.licoes, start=1):
            evidencia = _evidencia(item.evidencia, FonteEvidencia.LICOES)
            if evidencia is None:
                continue
            termos = tuple(t.strip() for t in item.termos_elemento if t.strip())
            licoes.append(
                LicaoAprendida(
                    id=f"LIC-{indice:02d}",
                    titulo=item.titulo.strip(),
                    regra=item.regra.strip(),
                    evidencia=evidencia,
                    documento=documento.arquivo,
                    contexto=item.contexto.strip(),
                    termos_elemento=termos or licoes_domain.termos_de_ambiente(item.regra),
                    ifc_class=item.ifc_class,
                    extraida_por="llm",
                )
            )
        return licoes


class LlmLessonChecker:
    """Procura cada lição no edital. A evidência é conferida depois (S2)."""

    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def check(
        self, licoes: Sequence[LicaoAprendida], edital: Edital, topicos: Sequence[Topico]
    ) -> list[VerificacaoLicao]:
        texto = "\n\n".join(t.texto for t in topicos)[:LIMITE_TEXTO_CHECKLIST]
        resultados: list[VerificacaoLicao] = []
        for inicio in range(0, len(licoes), LOTE_LICOES):
            lote = list(licoes[inicio : inicio + LOTE_LICOES])
            resposta = self._llm.gerar(
                "licao_no_edital", VerificacoesLicoesLLM, licoes=lote, texto=texto
            )
            por_indice = {item.indice: item for item in resposta.itens}
            for indice, licao in enumerate(lote):
                item = por_indice.get(indice)
                if item is None:
                    continue
                resultados.append(
                    VerificacaoLicao(
                        licao_id=licao.id,
                        explicita=item.explicita,
                        evidencia=_evidencia(item.evidencia),
                        trecho_relacionado=_evidencia(item.trecho_relacionado),
                        justificativa=item.justificativa.strip(),
                        redacao_sugerida=item.redacao_sugerida.strip(),
                        avaliado_por="llm",
                    )
                )
        return resultados


class LlmEditalAnalyzer:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def confirm_vagueness(self, candidatos: Sequence[TrechoVago]) -> list[AmbiguidadeConfirmada]:
        confirmadas: list[AmbiguidadeConfirmada] = []
        for inicio in range(0, len(candidatos), LOTE_AMBIGUIDADES):
            lote = list(candidatos[inicio : inicio + LOTE_AMBIGUIDADES])
            resposta = self._llm.gerar("ambiguidade", AmbiguidadesLLM, candidatos=lote)
            por_indice = {item.indice: item for item in resposta.itens}
            for indice, candidato in enumerate(lote):
                item = por_indice.get(indice)
                if item is None:
                    continue
                confirmadas.append(
                    AmbiguidadeConfirmada(
                        trecho=candidato,
                        ambiguo=item.ambiguo,
                        justificativa=item.justificativa,
                        redacao_sugerida=item.redacao_sugerida,
                        confirmado_por="llm",
                    )
                )
        return confirmadas

    def evaluate_checklist(
        self, edital: Edital, topicos: Sequence[Topico], itens: Sequence[ItemChecklist]
    ) -> list[ResultadoChecklist]:
        texto = "\n\n".join(t.texto for t in topicos)[:LIMITE_TEXTO_CHECKLIST]
        resposta = self._llm.gerar("checklist", ChecklistLLM, texto=texto, itens=itens)
        return [
            ResultadoChecklist(
                item_id=item.item_id,
                status=StatusChecklist(item.status),
                evidencia=_evidencia(item.evidencia),
                justificativa=item.justificativa,
                avaliado_por="llm",
            )
            for item in resposta.itens
        ]

    def find_contradictions(self, topicos: Sequence[Topico]) -> list[Contradicao]:
        texto = "\n\n".join(t.texto for t in topicos)[:LIMITE_TEXTO_CHECKLIST]
        resposta = self._llm.gerar("contradicoes", ContradicoesLLM, texto=texto)
        return [
            Contradicao(
                evidencia_a=Evidencia(c.evidencia_a.pagina, c.evidencia_a.trecho),
                evidencia_b=Evidencia(c.evidencia_b.pagina, c.evidencia_b.trecho),
                explicacao=c.explicacao,
            )
            for c in resposta.contradicoes
        ]


class LlmRecommendationWriter:
    def __init__(self, llm: StructuredLlm) -> None:
        self._llm = llm

    def write(self, apontamento: Apontamento, referencias: Sequence[Referencia]) -> Recomendacao:
        resposta = self._llm.gerar(
            "recomendacao", RecomendacaoLLM, apontamento=apontamento, referencias=referencias
        )
        citadas = tuple(Referencia(tipo="citada", rotulo=r) for r in resposta.referencias)
        return Recomendacao(
            como_agir=resposta.como_agir.strip(),
            por_que=resposta.por_que.strip(),
            referencias=citadas,
            gerado_por_ia=True,
        )
