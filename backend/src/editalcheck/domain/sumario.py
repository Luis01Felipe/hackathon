"""Leitura do sumário impresso do edital (RF-10).

O sumário é o conjunto de linhas "número + título + pontilhado + página"
("4.1. ARQUITETURA ........ 28"). Ele serve para duas coisas na segmentação:

- as próprias linhas do sumário nunca viram títulos de tópico;
- quando há entradas suficientes, só os números que constam nele abrem tópicos,
  e o título do corpo precisa bater com o do sumário. Isso descarta itens de
  tabela ("4 CP's por peça") e anexos internos de um capítulo.

Uma entrada longa pode quebrar em duas linhas: a primeira abre a entrada
(começa com o número) e a segunda termina com o pontilhado e a página. Quando a
linha está quase cheia, o pontilhado fica curto ("... ATENDIDAS .. 62").
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from editalcheck.domain.evidence import remover_acentos

_PONTILHADO_FINAL = re.compile(r"\s*(\.{2,})\s*\d{1,4}$")
_PONTILHADO_LONGO = 4
_ABRE_NUMERADA = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.?\s*(.*)$")
_ABRE_ANEXO = re.compile(
    r"^(ANEXO|AP[ÊE]NDICE)\s+([IVXLC]+|\d{1,3}|[A-Z])\b\s*(?:[-–—:.]\s*)?(.*)$"
)
_NAO_ALFANUMERICO = re.compile(r"[^0-9A-Z]")
_NIVEL_MAXIMO = 2  # capítulos e seções; cláusulas ficam dentro do tópico
MINIMO_ENTRADAS = 5
_MINIMO_CHAVE = 6


@dataclass(frozen=True)
class _Abertura:
    indice: int
    numero: str
    titulo: str


@dataclass(frozen=True)
class Sumario:
    titulos: dict[str, str]  # número ("4.1", "Anexo I") → título impresso
    linhas: frozenset[int]  # índices das linhas que pertencem ao sumário

    @property
    def ativo(self) -> bool:
        return len(self.titulos) >= MINIMO_ENTRADAS

    def titulo(self, numero: str) -> str | None:
        return self.titulos.get(numero)

    def titulo_conferido(self, numero: str, titulo_corpo: str) -> str | None:
        """Título do tópico se o do corpo bate com o do sumário; senão, None.

        Compara sem acentos, caixa, espaços e pontuação, e aceita que um seja o
        começo do outro (título do corpo quebrado em duas linhas ou colado a
        outro texto). Se só o começo bate, fica o título do sumário. Se batem por
        inteiro, fica a versão com mais palavras: a extração às vezes cola duas
        palavras ("SAÍDASDE"), num lado ou no outro.
        """
        impresso = self.titulos.get(numero)
        if impresso is None:
            return None
        corpo, sumario = _chave(titulo_corpo), _chave(impresso)
        if corpo == sumario:
            return max((titulo_corpo, impresso), key=lambda titulo: len(titulo.split()))
        menor = min(len(corpo), len(sumario))
        if menor < _MINIMO_CHAVE or not (corpo.startswith(sumario) or sumario.startswith(corpo)):
            return None
        return impresso


def _chave(titulo: str) -> str:
    return _NAO_ALFANUMERICO.sub("", remover_acentos(titulo).upper())


def _abertura(indice: int, linha: str) -> _Abertura | None:
    anexo = _ABRE_ANEXO.match(linha)
    if anexo:
        numero = f"{anexo.group(1).capitalize()} {anexo.group(2)}"
        return _Abertura(indice, numero, anexo.group(3).strip() or numero)
    numerada = _ABRE_NUMERADA.match(linha)
    if not numerada or not numerada.group(2)[:1].isalpha():
        return None
    return _Abertura(indice, numerada.group(1), numerada.group(2).strip())


def _nivel(numero: str) -> int:
    if not numero[:1].isdigit():
        return 1
    return numero.count(".") + 1


def ler_sumario(linhas: Sequence[str]) -> Sumario:
    titulos: dict[str, str] = {}
    do_sumario: set[int] = set()
    pendente: _Abertura | None = None

    def registrar(abertura: _Abertura, titulo: str) -> None:
        if _nivel(abertura.numero) <= _NIVEL_MAXIMO:
            titulos.setdefault(abertura.numero, " ".join(titulo.split()))

    for indice, linha in enumerate(linhas):
        final = _PONTILHADO_FINAL.search(linha)
        abertura = _abertura(indice, linha)
        if final is None:
            pendente = abertura
            continue
        resto = linha[: final.start()].strip()
        longo = len(final.group(1)) >= _PONTILHADO_LONGO
        if abertura is not None:
            titulo = _abertura(indice, resto)
            registrar(abertura, titulo.titulo if titulo else abertura.titulo)
            do_sumario.add(indice)
        elif pendente is not None:
            registrar(pendente, f"{pendente.titulo} {resto}")
            do_sumario.update((pendente.indice, indice))
        elif longo:
            do_sumario.add(indice)
        pendente = None
    return Sumario(titulos=titulos, linhas=frozenset(do_sumario))
