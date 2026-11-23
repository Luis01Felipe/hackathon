"""Lições aprendidas por regras (modo sem LLM e reserva quando o LLM falha)."""

from collections.abc import Sequence

from editalcheck.domain import licoes
from editalcheck.domain.models import Edital, LicaoAprendida, Topico, VerificacaoLicao
from editalcheck.domain.topics import paginas_do_topico


class RulesLessonExtractor:
    """Cada item do documento (marcador, numeração ou parágrafo) vira uma lição."""

    def extract(self, documento: Edital) -> list[LicaoAprendida]:
        return licoes.licoes_por_regras(documento)


class RulesLessonChecker:
    """Procura no edital uma frase que cite o ambiente e a maior parte da regra."""

    def check(
        self, lista: Sequence[LicaoAprendida], edital: Edital, topicos: Sequence[Topico]
    ) -> list[VerificacaoLicao]:
        paginas = sorted({p for t in topicos for p in paginas_do_topico(t)}) or None
        return [licoes.verificar_por_regras(licao, edital, paginas) for licao in lista]
