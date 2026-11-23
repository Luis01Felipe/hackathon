"""Medição do consumo de IA por projeto e por etapa (RF-195).

O adaptador de LLM informa cada chamada ao ``MedidorConsumo``. O projeto da
chamada vem de uma variável de contexto, definida pelo caso de uso com
``em_projeto``. As threads de trabalho herdam o contexto porque os casos de
uso usam ``ExecutorComContexto`` no lugar do ``ThreadPoolExecutor``.
"""

from collections.abc import Callable, Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import ContextVar, copy_context
from dataclasses import replace
from threading import Lock

from editalcheck.domain.models import ConsumoEtapa

_PROJETO: ContextVar[str | None] = ContextVar("editalcheck_projeto", default=None)

# Nome do prompt → etapa exibida no painel "Custo e tempo".
ETAPAS = {
    "topicos": "Tópicos",
    "extracao_requisitos": "Requisitos de informação",
    "licoes": "Lições aprendidas",
    "licao_no_edital": "Lições no edital",
    "ambiguidade": "Qualidade do edital",
    "checklist": "Qualidade do edital",
    "contradicoes": "Qualidade do edital",
    "recomendacao": "Recomendações",
}


@contextmanager
def em_projeto(projeto_id: str) -> Iterator[None]:
    """Atribui ao projeto as chamadas de IA feitas dentro do bloco."""
    token = _PROJETO.set(projeto_id)
    try:
        yield
    finally:
        _PROJETO.reset(token)


class ExecutorComContexto(ThreadPoolExecutor):
    """``ThreadPoolExecutor`` que repassa as variáveis de contexto a cada tarefa."""

    def submit(self, fn: Callable, /, *args, **kwargs) -> Future:  # type: ignore[override]
        contexto = copy_context()
        return super().submit(contexto.run, fn, *args, **kwargs)


class MedidorConsumo:
    def __init__(self) -> None:
        self._trava = Lock()
        self._por_projeto: dict[str, dict[str, ConsumoEtapa]] = {}

    def registrar(
        self,
        nome_prompt: str,
        tokens_entrada: int,
        tokens_saida: int,
        duracao_s: float,
        cache: bool = False,
    ) -> None:
        projeto_id = _PROJETO.get()
        if projeto_id is None:
            return
        etapa = ETAPAS.get(nome_prompt, nome_prompt)
        with self._trava:
            etapas = self._por_projeto.setdefault(projeto_id, {})
            atual = etapas.get(etapa, ConsumoEtapa(etapa=etapa))
            etapas[etapa] = replace(
                atual,
                chamadas=atual.chamadas + (0 if cache else 1),
                chamadas_cache=atual.chamadas_cache + (1 if cache else 0),
                tokens_entrada=atual.tokens_entrada + tokens_entrada,
                tokens_saida=atual.tokens_saida + tokens_saida,
                duracao_s=round(atual.duracao_s + duracao_s, 3),
            )

    def consumo(self, projeto_id: str) -> tuple[ConsumoEtapa, ...]:
        with self._trava:
            return tuple(self._por_projeto.get(projeto_id, {}).values())

    def esquecer(self, projeto_id: str) -> None:
        with self._trava:
            self._por_projeto.pop(projeto_id, None)
