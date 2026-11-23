"""Localização de trechos e tópicos no PDF do edital (PyMuPDF), palavra por palavra.

A busca de texto do PyMuPDF não acha frases que quebram de linha nem palavras
hifenizadas. Aqui o trecho vira uma sequência de palavras normalizadas (sem
acento, caixa e pontuação), procurada na sequência de palavras da página. As
caixas das palavras encontradas são unidas por linha.

As regiões saem em frações da página (0 a 1, origem no canto superior
esquerdo), prontas para o visualizador do navegador e para o PDF anotado.
"""

import hashlib
import re
import unicodedata
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock

import pymupdf

from editalcheck.domain.models import Evidencia, FonteEvidencia, RegiaoPdf, Topico

_MARCADOR_PAGINA = re.compile(r"^\[p\.\s*\d+\]$")
_NAO_PALAVRA = re.compile(r"[^0-9a-z]+")
MINIMO_PALAVRAS_PREFIXO = 6
MAX_DOCUMENTOS_EM_CACHE = 4


def _token(palavra: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", palavra.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return _NAO_PALAVRA.sub("", sem_acento)


def tokens(texto: str) -> list[str]:
    return [t for t in (_token(p) for p in texto.replace("-\n", "").split()) if t]


@dataclass(frozen=True)
class _Palavra:
    token: str
    rect: pymupdf.Rect
    bloco: int
    linha: int


def _palavras(pagina: pymupdf.Page) -> list[_Palavra]:
    """Palavras da página em ordem de leitura; junta hifenização de fim de linha."""
    brutas = pagina.get_text("words", sort=True)
    palavras: list[_Palavra] = []
    pendente: tuple[str, pymupdf.Rect] | None = None
    for x0, y0, x1, y1, texto, bloco, linha, _ in brutas:
        rect = pymupdf.Rect(x0, y0, x1, y1)
        if pendente is not None:
            texto = pendente[0] + texto
            palavras.append(_Palavra(_token(texto), pendente[1], bloco, linha))
            pendente = None
        if texto.endswith("-") and len(texto) > 2 and texto[-2].isalpha():
            pendente = (texto[:-1], rect)
            continue
        token = _token(texto)
        if token:
            palavras.append(_Palavra(token, rect, bloco, linha))
    return palavras


def _procurar(sequencia: list[str], palavras: list[_Palavra]) -> list[_Palavra]:
    """Acha a sequência; se não achar inteira, o maior prefixo com ao menos 6 palavras."""
    if not sequencia:
        return []
    tokens_pagina = [p.token for p in palavras]
    tamanho = len(sequencia)
    for inicio in range(len(tokens_pagina) - tamanho + 1):
        if tokens_pagina[inicio : inicio + tamanho] == sequencia:
            return palavras[inicio : inicio + tamanho]
    melhor: list[_Palavra] = []
    for inicio, token in enumerate(tokens_pagina):
        if token != sequencia[0]:
            continue
        fim = inicio
        while (
            fim < len(tokens_pagina)
            and fim - inicio < tamanho
            and tokens_pagina[fim] == sequencia[fim - inicio]
        ):
            fim += 1
        if fim - inicio > len(melhor):
            melhor = palavras[inicio:fim]
    minimo = min(MINIMO_PALAVRAS_PREFIXO, tamanho)
    return melhor if len(melhor) >= minimo else []


def _por_linha(palavras: list[_Palavra]) -> list[pymupdf.Rect]:
    linhas: dict[tuple[int, int], pymupdf.Rect] = {}
    for palavra in palavras:
        chave = (palavra.bloco, palavra.linha)
        linhas[chave] = linhas[chave] | palavra.rect if chave in linhas else +palavra.rect
    return list(linhas.values())


def retangulos_do_trecho(pagina: pymupdf.Page, trecho: str) -> list[pymupdf.Rect]:
    """Retângulos (um por linha) do trecho na página, em coordenadas do PyMuPDF."""
    return _por_linha(_procurar(tokens(trecho), _palavras(pagina)))


def _normalizar(pagina: pymupdf.Page, rect: pymupdf.Rect) -> RegiaoPdf:
    if pagina.rotation:
        rect = rect * pagina.rotation_matrix
    largura, altura = pagina.rect.width or 1, pagina.rect.height or 1
    return RegiaoPdf(
        pagina=pagina.number + 1,
        x0=round(max(0.0, rect.x0 / largura), 4),
        y0=round(max(0.0, rect.y0 / altura), 4),
        x1=round(min(1.0, rect.x1 / largura), 4),
        y1=round(min(1.0, rect.y1 / altura), 4),
    )


class PyMuPdfLocalizador:
    def __init__(self) -> None:
        self._cache: OrderedDict[str, pymupdf.Document] = OrderedDict()
        self._trava = Lock()

    def _documento(self, pdf: bytes) -> pymupdf.Document:
        chave = hashlib.sha256(pdf).hexdigest()
        with self._trava:
            if chave in self._cache:
                self._cache.move_to_end(chave)
                return self._cache[chave]
            documento = pymupdf.open(stream=pdf, filetype="pdf")
            self._cache[chave] = documento
            while len(self._cache) > MAX_DOCUMENTOS_EM_CACHE:
                self._cache.popitem(last=False)[1].close()
            return documento

    def trechos(self, pdf: bytes, evidencias: Sequence[Evidencia]) -> list[list[RegiaoPdf]]:
        documento = self._documento(pdf)
        with self._trava:
            resultado: list[list[RegiaoPdf]] = []
            for evidencia in evidencias:
                if evidencia.fonte != FonteEvidencia.EDITAL:
                    resultado.append([])
                    continue
                if not 1 <= evidencia.pagina <= documento.page_count:
                    resultado.append([])
                    continue
                pagina = documento[evidencia.pagina - 1]
                retangulos = retangulos_do_trecho(pagina, evidencia.trecho)
                resultado.append([_normalizar(pagina, r) for r in retangulos])
            return resultado

    def topicos(self, pdf: bytes, topicos: Sequence[Topico]) -> dict[str, list[RegiaoPdf]]:
        documento = self._documento(pdf)
        with self._trava:
            inicios = [self._inicio(documento, t) for t in topicos]
            faixas: dict[str, list[RegiaoPdf]] = {}
            for indice, topico in enumerate(topicos):
                inicio = inicios[indice]
                fim = next((i for i in inicios[indice + 1 :] if i is not None), None)
                faixas[topico.id] = self._faixas(documento, topico, inicio, fim)
            return faixas

    @staticmethod
    def _primeira_linha(topico: Topico) -> str:
        for linha in topico.texto.splitlines():
            limpa = linha.strip()
            if limpa and not _MARCADOR_PAGINA.match(limpa):
                return limpa
        return f"{topico.numero} {topico.titulo}"

    def _inicio(self, documento: pymupdf.Document, topico: Topico) -> tuple[int, float] | None:
        """(índice da página, y do topo) da primeira linha do tópico."""
        if not 1 <= topico.pagina_inicio <= documento.page_count:
            return None
        pagina = documento[topico.pagina_inicio - 1]
        sequencia = tokens(self._primeira_linha(topico))[:12]
        achadas = _procurar(sequencia, _palavras(pagina))
        if not achadas:
            return None
        return pagina.number, min(p.rect.y0 for p in achadas)

    def _faixas(
        self,
        documento: pymupdf.Document,
        topico: Topico,
        inicio: tuple[int, float] | None,
        fim: tuple[int, float] | None,
    ) -> list[RegiaoPdf]:
        primeira = inicio[0] if inicio else topico.pagina_inicio - 1
        ultima = topico.pagina_fim - 1
        if fim is not None:
            ultima = min(ultima, fim[0]) if fim[0] >= primeira else ultima
        faixas: list[RegiaoPdf] = []
        for indice in range(max(0, primeira), min(documento.page_count - 1, ultima) + 1):
            pagina = documento[indice]
            palavras = _palavras(pagina)
            if not palavras:
                continue
            x0 = min(p.rect.x0 for p in palavras)
            x1 = max(p.rect.x1 for p in palavras)
            topo = min(p.rect.y0 for p in palavras)
            base = max(p.rect.y1 for p in palavras)
            if inicio and indice == inicio[0]:
                topo = inicio[1]
            if fim and indice == fim[0]:
                base = fim[1]
            if base - topo < 2:
                continue
            faixas.append(_normalizar(pagina, pymupdf.Rect(x0 - 3, topo - 2, x1 + 3, base)))
        return faixas
