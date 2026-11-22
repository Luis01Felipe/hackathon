"""Detecção de termos vagos por léxico (análise B, parte determinística — RF-42)."""

import re
from collections.abc import Iterable, Sequence

from editalcheck.domain.evidence import (
    clausula_do_trecho,
    compactar_espacos,
    normalizar,
    remover_acentos,
)
from editalcheck.domain.models import Edital, TermoVago, Topico, TrechoVago

_FIM_SENTENCA = re.compile(r"(?<=[.;!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9\"“(])")
_INICIO_CLAUSULA = re.compile(r"\s+(?=\d{1,2}(?:\.\d{1,2})+\.?\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ])")
_TAMANHO_MAXIMO_SENTENCA = 400


def _chave(texto: str) -> str:
    return remover_acentos(normalizar(texto))


def dividir_sentencas(texto: str) -> list[str]:
    texto = compactar_espacos(texto)
    sentencas: list[str] = []
    for bloco in _FIM_SENTENCA.split(texto):
        sentencas.extend(s.strip() for s in _INICIO_CLAUSULA.split(bloco) if s.strip())
    return [s[:_TAMANHO_MAXIMO_SENTENCA] for s in sentencas]


def _padrao(termo: str) -> re.Pattern[str]:
    return re.compile(rf"(?<!\w){re.escape(_chave(termo))}(?!\w)")


def _topico_da_sentenca(sentenca: str, pagina: int, topicos: Sequence[Topico]) -> Topico | None:
    alvo = normalizar(sentenca)[:60]
    for topico in topicos:
        if not topico.pagina_inicio <= pagina <= topico.pagina_fim:
            continue
        if alvo in normalizar(topico.texto):
            return topico
    return None


def detectar(
    edital: Edital,
    termos: Sequence[TermoVago],
    topicos: Sequence[Topico] = (),
    topicos_alvo: Iterable[str] | None = None,
) -> list[TrechoVago]:
    """Encontra sentenças do edital que usam termos vagos do léxico.

    Se ``topicos_alvo`` for informado, só considera sentenças desses tópicos.
    """
    alvo = set(topicos_alvo) if topicos_alvo is not None else None
    padroes = [(termo, _padrao(termo.termo)) for termo in termos]
    encontrados: list[TrechoVago] = []
    vistos: set[tuple[int, str]] = set()
    for pagina in edital.paginas:
        for sentenca in dividir_sentencas(pagina.texto):
            chave = _chave(sentenca)
            casados = [termo for termo, padrao in padroes if padrao.search(chave)]
            if not casados:
                continue
            casados = [
                t
                for t in casados
                if not any(
                    _chave(t.termo) != _chave(o.termo) and _chave(t.termo) in _chave(o.termo)
                    for o in casados
                )
            ]
            topico = _topico_da_sentenca(sentenca, pagina.numero, topicos) if topicos else None
            if alvo is not None and (topico is None or topico.id not in alvo):
                continue
            if (pagina.numero, chave) in vistos:
                continue
            vistos.add((pagina.numero, chave))
            principal = casados[0]
            encontrados.append(
                TrechoVago(
                    pagina=pagina.numero,
                    trecho=sentenca,
                    termo="; ".join(t.termo for t in casados),
                    categoria=principal.categoria,
                    topico_id=topico.id if topico else None,
                    clausula=clausula_do_trecho(pagina.texto, sentenca),
                    sugestao=principal.sugestao,
                )
            )
    return encontrados
