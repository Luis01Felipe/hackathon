"""Texto repetido ou sobrescrito no edital (análise B, determinística).

Compara frases de cláusulas diferentes por sobreposição de trigramas de
palavras (Jaccard). Frases quase iguais viram ``DUPLICIDADE``. Frases
parecidas com valores numéricos diferentes viram candidatas a contradição.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass

from editalcheck.domain.evidence import normalizar, remover_acentos
from editalcheck.domain.models import Evidencia, Topico
from editalcheck.domain.vagueness import dividir_sentencas

LIMITE_DUPLICIDADE = 0.85
LIMITE_CONTRADICAO = 0.8
PALAVRAS_MINIMAS = 8
# O mesmo texto com números trocados 3+ vezes é lista ou tabela (itens de planilha,
# prazos por etapa), não contradição.
REPETICOES_DE_LISTA = 3
MAX_PARES = 20  # o relatório mostra os casos mais fortes; o resto seria ruído
TRIGRAMAS_EM_COMUM = 3
TRIGRAMA_FREQUENTE = 40  # trigramas presentes em muitas frases não indicam semelhança
_MARCADOR = re.compile(r"\[p\.\s*(\d+)\]")
_NUMERO_CLAUSULA = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2})+\.?\s+")
_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
_PALAVRA = re.compile(r"[a-z0-9]+(?:[.,]\d+)?")
_NUMERACAO_PAGINA = re.compile(r"\bpagina\s*\d+\s*(?:de|/)\s*\d+\b")
PAGINAS_CABECALHO = 3  # texto repetido em 3+ páginas é cabeçalho ou rodapé


@dataclass(frozen=True)
class ParSentencas:
    a: Evidencia
    b: Evidencia
    similaridade: float
    valores_diferentes: bool


@dataclass(frozen=True)
class _Frase:
    evidencia: Evidencia
    topico_id: str
    trigramas: frozenset[tuple[str, ...]]
    numeros: tuple[str, ...]


def _frases(topico: Topico) -> list[_Frase]:
    frases: list[_Frase] = []
    pagina = topico.pagina_inicio
    for parte in _MARCADOR.split(topico.texto):
        if parte.isdigit():
            pagina = int(parte)
            continue
        for sentenca in dividir_sentencas(parte):
            corpo = remover_acentos(normalizar(_NUMERO_CLAUSULA.sub("", sentenca)))
            if _NUMERACAO_PAGINA.search(corpo):
                continue
            # Números viram "#": a similaridade compara o texto; os valores, à parte.
            palavras = ["#" if _NUMERO.fullmatch(p) else p for p in _PALAVRA.findall(corpo)]
            if len(palavras) < PALAVRAS_MINIMAS:
                continue
            trigramas = frozenset(zip(palavras, palavras[1:], palavras[2:], strict=False))
            frases.append(
                _Frase(
                    evidencia=Evidencia(pagina=pagina, trecho=sentenca),
                    topico_id=topico.id,
                    trigramas=trigramas,
                    numeros=tuple(_NUMERO.findall(corpo)),
                )
            )
    return frases


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sem_cabecalhos(frases: list[_Frase]) -> list[_Frase]:
    paginas: dict[frozenset, set[int]] = {}
    for frase in frases:
        paginas.setdefault(frase.trigramas, set()).add(frase.evidencia.pagina)
    return [f for f in frases if len(paginas[f.trigramas]) < PAGINAS_CABECALHO]


def _candidatos(frases: Sequence[_Frase]) -> list[tuple[int, int]]:
    """Pares que compartilham trigramas raros (índice invertido: evita comparar tudo com tudo)."""
    indice: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for posicao, frase in enumerate(frases):
        for trigrama in frase.trigramas:
            indice[trigrama].append(posicao)
    em_comum: Counter[tuple[int, int]] = Counter()
    for posicoes in indice.values():
        if len(posicoes) > TRIGRAMA_FREQUENTE:
            continue
        for x, i in enumerate(posicoes):
            for j in posicoes[x + 1 :]:
                em_comum[(i, j)] += 1
    return [par for par, total in em_comum.items() if total >= TRIGRAMAS_EM_COMUM]


def encontrar(topicos: Sequence[Topico]) -> list[ParSentencas]:
    frases = _sem_cabecalhos([f for t in topicos if not t.agrupador for f in _frases(t)])
    repeticoes = Counter(f.trigramas for f in frases)
    frases = [f for f in frases if repeticoes[f.trigramas] < REPETICOES_DE_LISTA]
    achados: list[tuple[float, int, int, bool]] = []
    for i, j in _candidatos(frases):
        a, b = frases[i], frases[j]
        if a.evidencia.trecho == b.evidencia.trecho and a.topico_id == b.topico_id:
            continue
        similaridade = _jaccard(a.trigramas, b.trigramas)
        diferentes = bool(a.numeros) and bool(b.numeros) and a.numeros != b.numeros
        if similaridade >= LIMITE_DUPLICIDADE and not diferentes:
            achados.append((similaridade, i, j, False))
        elif similaridade >= LIMITE_CONTRADICAO and diferentes:
            achados.append((similaridade, i, j, True))
    # Cada frase entra em um par só, do mais parecido para o menos parecido.
    achados.sort(key=lambda item: item[0], reverse=True)
    usadas: set[int] = set()
    pares: list[ParSentencas] = []
    for similaridade, i, j, diferentes in achados:
        if i in usadas or j in usadas:
            continue
        usadas.update((i, j))
        pares.append(
            ParSentencas(frases[i].evidencia, frases[j].evidencia, similaridade, diferentes)
        )
        if len(pares) >= MAX_PARES:
            break
    return pares
