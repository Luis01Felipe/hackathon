"""Analisador do edital por regras (modo sem LLM): ambiguidade, checklist e contradição."""

import re
from collections.abc import Sequence
from dataclasses import replace

from editalcheck.domain import checklist as checklist_domain
from editalcheck.domain.checklist import RegraChecklist
from editalcheck.domain.evidence import normalizar, remover_acentos
from editalcheck.domain.models import (
    AmbiguidadeConfirmada,
    Apontamento,
    Contradicao,
    Edital,
    Evidencia,
    ItemChecklist,
    Recomendacao,
    Referencia,
    ResultadoChecklist,
    Topico,
    TrechoVago,
)
from editalcheck.domain.topics import edital_dos_topicos
from editalcheck.domain.vagueness import dividir_sentencas

_CLAUSULA_INICIAL = re.compile(r"^\d{1,2}(?:\.\d{1,2})*\.?\s+")
_VERSAO_IFC = re.compile(r"\bifc\s*-?\s*(2x3|4x3|4(?:\.\d)?)\b")
_MARCADOR = re.compile(r"^\[p\.\s*(\d+)\]$")


def tem_criterio_mensuravel(sentenca: str) -> bool:
    corpo = _CLAUSULA_INICIAL.sub("", sentenca.strip())
    return bool(re.search(r"\d", corpo))


class RulesEditalAnalyzer:
    def __init__(self, regras_checklist: Sequence[RegraChecklist]) -> None:
        self._regras = list(regras_checklist)

    def confirm_vagueness(self, candidatos: Sequence[TrechoVago]) -> list[AmbiguidadeConfirmada]:
        confirmadas: list[AmbiguidadeConfirmada] = []
        for candidato in candidatos:
            mensuravel = tem_criterio_mensuravel(candidato.trecho)
            confirmadas.append(
                AmbiguidadeConfirmada(
                    trecho=candidato,
                    ambiguo=not mensuravel,
                    justificativa=(
                        "A frase traz número ou norma identificada; o termo não impede a verificação."
                        if mensuravel
                        else "A frase não traz valor, norma numerada nem lista fechada que permita verificar."
                    ),
                    redacao_sugerida="",
                    confirmado_por="regras",
                )
            )
        return confirmadas

    def evaluate_checklist(
        self, edital: Edital, topicos: Sequence[Topico], itens: Sequence[ItemChecklist]
    ) -> list[ResultadoChecklist]:
        alvo = edital_dos_topicos(edital, topicos) if topicos else edital
        return checklist_domain.avaliar_por_regras(alvo, itens, self._regras)

    def find_contradictions(self, topicos: Sequence[Topico]) -> list[Contradicao]:
        versoes: dict[str, Evidencia] = {}
        for topico in topicos:
            pagina = topico.pagina_inicio
            bloco: list[str] = []
            linhas = topico.texto.splitlines() + ["[p. 0]"]
            for linha in linhas:
                marcador = _MARCADOR.match(linha.strip())
                if not marcador:
                    bloco.append(linha)
                    continue
                for sentenca in dividir_sentencas("\n".join(bloco)):
                    encontradas = {
                        v.upper()
                        for v in _VERSAO_IFC.findall(remover_acentos(normalizar(sentenca)))
                    }
                    if len(encontradas) != 1:
                        continue
                    versao = encontradas.pop()
                    versoes.setdefault(versao, Evidencia(pagina=pagina, trecho=sentenca))
                pagina, bloco = int(marcador.group(1)), []
        if len(versoes) < 2:
            return []
        (versao_a, a), (versao_b, b) = list(versoes.items())[:2]
        return [
            Contradicao(
                evidencia_a=a,
                evidencia_b=b,
                explicacao=(
                    f"O edital cita IFC {versao_a} e IFC {versao_b} como formato de entrega. "
                    "O projetista não sabe qual versão exportar."
                ),
            )
        ]


class RulesTopicClassifier:
    """Mantém a relevância por palavras-chave e gera um resumo curto."""

    def classify(self, topicos: Sequence[Topico]) -> list[Topico]:
        classificados: list[Topico] = []
        for topico in topicos:
            linhas = [
                linha_
                for linha_ in topico.texto.splitlines()
                if not _MARCADOR.match(linha_.strip())
            ]
            sentencas = dividir_sentencas("\n".join(linhas[1:]))
            resumo = " ".join(sentencas[0].split()[:20]) if sentencas else ""
            classificados.append(replace(topico, resumo=resumo or None))
        return classificados


class TemplateRecommendationWriter:
    """Fallback sem LLM: mantém os textos de template do apontamento."""

    def write(self, apontamento: Apontamento, referencias: Sequence[Referencia]) -> Recomendacao:
        return Recomendacao(
            como_agir=apontamento.como_agir,
            por_que=apontamento.por_que,
            referencias=apontamento.referencias,
            gerado_por_ia=False,
        )
