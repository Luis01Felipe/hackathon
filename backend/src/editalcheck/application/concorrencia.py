"""Travas por chave (projeto ou verificação) para operações de ler-alterar-gravar.

O repositório devolve objetos que os casos de uso leem, alteram e gravam de volta. Sem trava,
duas requisições simultâneas no mesmo projeto (ex.: dois PATCH de requisitos, ou uma decisão
enquanto o relatório é publicado) perdem uma das alterações. As travas valem para o processo:
o deploy roda uma réplica por projeto (sessão fixa no proxy), como o repositório em memória.
"""

import functools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Concatenate


class TravasPorChave:
    def __init__(self) -> None:
        self._travas: dict[str, threading.RLock] = {}
        self._guarda = threading.Lock()

    @contextmanager
    def segurar(self, chave: str) -> Iterator[None]:
        with self._guarda:
            trava = self._travas.setdefault(chave, threading.RLock())
        with trava:
            yield

    def esquecer(self, chave: str) -> None:
        with self._guarda:
            self._travas.pop(chave, None)


travas_projeto = TravasPorChave()
travas_relatorio = TravasPorChave()


def por_projeto[S, **P, R](
    metodo: Callable[Concatenate[S, str, P], R],
) -> Callable[Concatenate[S, str, P], R]:
    """Serializa o método por projeto: o primeiro argumento depois de ``self`` é o id."""

    @functools.wraps(metodo)
    def envolvido(self: S, projeto_id: str, *args: P.args, **kwargs: P.kwargs) -> R:
        with travas_projeto.segurar(projeto_id):
            return metodo(self, projeto_id, *args, **kwargs)

    return envolvido
