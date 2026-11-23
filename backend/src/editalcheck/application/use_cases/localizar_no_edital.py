"""Caso de uso: posição dos tópicos e dos apontamentos no PDF do edital.

Alimenta o visualizador do navegador (só leitura): a confirmação dos tópicos
antes de gerar os IR e a aba "Edital" dos resultados. O PDF continua só em
memória; as posições ficam num cache pequeno, por projeto e por verificação.
"""

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock

from editalcheck.application.errors import NaoEncontradoError
from editalcheck.application.observability import etapa
from editalcheck.application.ports import EditalLocator, ProjectRepository
from editalcheck.application.use_cases.importar_documentos import ARQUIVO_EDITAL
from editalcheck.domain.models import FonteEvidencia, RegiaoPdf

MAX_ENTRADAS_CACHE = 64


@dataclass(frozen=True)
class LocalApontamento:
    apontamento_id: str
    regioes: tuple[RegiaoPdf, ...]
    paginas: tuple[int, ...]  # páginas citadas no edital, mesmo sem trecho localizado

    @property
    def localizado(self) -> bool:
        return bool(self.regioes)


class LocalizarNoEdital:
    def __init__(self, repositorio: ProjectRepository, localizador: EditalLocator) -> None:
        self._repo = repositorio
        self._localizador = localizador
        self._cache: OrderedDict[str, object] = OrderedDict()
        self._trava = Lock()

    def _guardar(self, chave: str, valor: object) -> None:
        with self._trava:
            self._cache[chave] = valor
            while len(self._cache) > MAX_ENTRADAS_CACHE:
                self._cache.popitem(last=False)

    def _em_cache(self, chave: str) -> object | None:
        with self._trava:
            return self._cache.get(chave)

    def _pdf(self, projeto_id: str) -> bytes:
        pdf = self._repo.read_file(projeto_id, ARQUIVO_EDITAL)
        if pdf is None:
            raise NaoEncontradoError("O edital deste projeto não está disponível.")
        return pdf

    def topicos(self, projeto_id: str) -> dict[str, list[RegiaoPdf]]:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        chave = f"topicos:{projeto_id}"
        guardado = self._em_cache(chave)
        if isinstance(guardado, dict):
            return guardado
        with etapa("edital.localizar_topicos", projeto=projeto_id, topicos=len(projeto.topicos)):
            faixas = self._localizador.topicos(self._pdf(projeto_id), projeto.topicos)
        self._guardar(chave, faixas)
        return faixas

    def apontamentos(self, verificacao_id: str) -> list[LocalApontamento]:
        relatorio = self._repo.get_relatorio(verificacao_id)
        if relatorio is None:
            raise NaoEncontradoError("Relatório não encontrado.")
        chave = f"apontamentos:{verificacao_id}"
        guardado = self._em_cache(chave)
        if isinstance(guardado, list):
            return guardado
        do_edital = [
            (apontamento.id, evidencia)
            for apontamento in relatorio.apontamentos
            for evidencia in apontamento.evidencias_edital
            if evidencia.fonte == FonteEvidencia.EDITAL
        ]
        with etapa("edital.localizar_apontamentos", verificacao=verificacao_id):
            regioes = self._localizador.trechos(
                self._pdf(relatorio.projeto_id), [e for _, e in do_edital]
            )
        por_apontamento: dict[str, list[RegiaoPdf]] = {}
        paginas: dict[str, list[int]] = {}
        for (apontamento_id, evidencia), achadas in zip(do_edital, regioes, strict=True):
            por_apontamento.setdefault(apontamento_id, []).extend(achadas)
            paginas.setdefault(apontamento_id, []).append(evidencia.pagina)
        locais = [
            LocalApontamento(
                apontamento_id=a.id,
                regioes=tuple(por_apontamento.get(a.id, ())),
                paginas=tuple(dict.fromkeys(paginas.get(a.id, ()))),
            )
            for a in relatorio.apontamentos
        ]
        self._guardar(chave, locais)
        return locais
