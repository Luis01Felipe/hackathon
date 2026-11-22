"""Segmentação determinística do edital em tópicos (RF-10).

Um tópico começa num título numerado de nível 1 ou 2 ("5 DOS REQUISITOS",
"5.1 Portas"). A numeração precisa crescer, o que evita confundir itens de
lista com títulos. Sem títulos reconhecidos, cada página vira um tópico.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass

from editalcheck.domain.evidence import desifenizar, normalizar, remover_acentos
from editalcheck.domain.models import Edital, Pagina, Topico

_TITULO = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?\.?\s+(.{3,100})$")
_TAMANHO_MINIMO_CORPO = 20

PALAVRAS_BIM: tuple[str, ...] = (
    "bim",
    "ifc",
    "ids",
    "bcf",
    "bsdd",
    "pset",
    "modelo",
    "modelagem",
    "propriedade",
    "nivel de informacao",
    "nivel de detalhe",
    "loin",
    "lod",
    "classificacao",
    "nomenclatura",
    "georreferenc",
    "coordenadas",
    "ambiente comum de dados",
    "cde",
    "porta",
    "parede",
    "janela",
    "escada",
    "ambiente",
    "laje",
    "pilar",
    "viga",
    "extintor",
    "elemento",
    "modelad",
    "atributo",
    "colaboracao",
    "plataforma",
    "troca de arquivos",
    "disciplinas",
)
_PALAVRAS_FORTES = (
    "bim",
    "ifc",
    "pset",
    "modelo",
    "modelagem",
    "modelad",
    "propriedade",
    "atributo",
)
_NOME_IFC = re.compile(r"\b(?:Ifc[A-Z]\w+|Pset_\w+|[A-Z][a-z]+(?:[A-Z][a-z]+){1,4})\b")


@dataclass(frozen=True)
class _Linha:
    pagina: int
    texto: str


@dataclass(frozen=True)
class _Titulo:
    indice_linha: int
    numero: str
    titulo: str
    nivel: int


def _eh_titulo_plausivel(titulo: str) -> bool:
    titulo = titulo.strip()
    if not titulo or not titulo[0].isalpha() or not titulo[0].isupper():
        return False
    if titulo.endswith((".", ";", ",", ":")):
        return False
    return sum(c.isalpha() for c in titulo) >= 3


def _linhas(edital: Edital) -> list[_Linha]:
    linhas: list[_Linha] = []
    for pagina in edital.paginas:
        for linha in desifenizar(pagina.texto).splitlines():
            texto = " ".join(linha.split())
            if texto:
                linhas.append(_Linha(pagina=pagina.numero, texto=texto))
    return linhas


def _titulos(linhas: list[_Linha]) -> list[_Titulo]:
    titulos: list[_Titulo] = []
    maior_atual = 0
    menor_atual = 0
    for indice, linha in enumerate(linhas):
        encontrado = _TITULO.match(linha.texto)
        if not encontrado or not _eh_titulo_plausivel(encontrado.group(3)):
            continue
        maior = int(encontrado.group(1))
        menor = int(encontrado.group(2)) if encontrado.group(2) else None
        if menor is None:
            if maior <= maior_atual:
                continue
            maior_atual, menor_atual = maior, 0
            titulos.append(_Titulo(indice, str(maior), encontrado.group(3).strip(), 1))
            continue
        if maior != maior_atual or menor <= menor_atual:
            continue
        menor_atual = menor
        titulos.append(_Titulo(indice, f"{maior}.{menor}", encontrado.group(3).strip(), 2))
    return titulos


def _texto_com_marcadores(linhas: list[_Linha]) -> str:
    partes: list[str] = []
    pagina_atual: int | None = None
    for linha in linhas:
        if linha.pagina != pagina_atual:
            partes.append(f"[p. {linha.pagina}]")
            pagina_atual = linha.pagina
        partes.append(linha.texto)
    return "\n".join(partes)


def eh_relevante_bim(texto: str) -> bool:
    """Heurística determinística; o LLM refina quando disponível (RF-11)."""
    if _NOME_IFC.search(texto):
        return True
    alvo = remover_acentos(normalizar(texto))
    acertos = [p for p in PALAVRAS_BIM if re.search(rf"\b{re.escape(p)}", alvo)]
    if any(p in _PALAVRAS_FORTES for p in acertos):
        return True
    return len(acertos) >= 2


def _novo_topico(indice: int, numero: str, titulo: str, nivel: int, linhas: list[_Linha]) -> Topico:
    texto = _texto_com_marcadores(linhas)
    return Topico(
        id=f"TOP-{indice:02d}",
        numero=numero,
        titulo=titulo,
        nivel=nivel,
        pagina_inicio=linhas[0].pagina,
        pagina_fim=linhas[-1].pagina,
        texto=texto,
        relevante_bim=eh_relevante_bim(texto),
    )


def _por_pagina(edital: Edital) -> list[Topico]:
    topicos: list[Topico] = []
    for pagina in edital.paginas:
        linhas = [
            _Linha(pagina.numero, " ".join(linha_.split())) for linha_ in pagina.texto.splitlines()
        ]
        linhas = [linha_ for linha_ in linhas if linha_.texto]
        if not linhas:
            continue
        topicos.append(
            _novo_topico(len(topicos) + 1, str(pagina.numero), f"Página {pagina.numero}", 1, linhas)
        )
    return topicos


def segmentar(edital: Edital) -> list[Topico]:
    linhas = _linhas(edital)
    if not linhas:
        return []
    titulos = _titulos(linhas)
    if not titulos:
        return _por_pagina(edital)

    topicos: list[Topico] = []
    preambulo = linhas[: titulos[0].indice_linha]
    if sum(len(linha_.texto) for linha_ in preambulo) >= _TAMANHO_MINIMO_CORPO:
        topicos.append(_novo_topico(1, "0", "Preâmbulo", 1, preambulo))

    for posicao, titulo in enumerate(titulos):
        fim = titulos[posicao + 1].indice_linha if posicao + 1 < len(titulos) else len(linhas)
        trecho = linhas[titulo.indice_linha : fim]
        corpo = sum(len(linha_.texto) for linha_ in trecho[1:])
        if corpo < _TAMANHO_MINIMO_CORPO:
            continue
        topicos.append(
            _novo_topico(len(topicos) + 1, titulo.numero, titulo.titulo, titulo.nivel, trecho)
        )
    return topicos


def paginas_do_topico(topico: Topico) -> range:
    return range(topico.pagina_inicio, topico.pagina_fim + 1)


_MARCADOR = re.compile(r"^\[p\.\s*(\d+)\]$")


def edital_dos_topicos(edital: Edital, topicos: Sequence[Topico]) -> Edital:
    """Edital reduzido ao texto dos tópicos informados, com as páginas originais."""
    por_pagina: dict[int, list[str]] = {}
    for topico in topicos:
        pagina = topico.pagina_inicio
        for linha in topico.texto.splitlines():
            marcador = _MARCADOR.match(linha.strip())
            if marcador:
                pagina = int(marcador.group(1))
                continue
            por_pagina.setdefault(pagina, []).append(linha)
    paginas = tuple(Pagina(numero=n, texto="\n".join(por_pagina[n])) for n in sorted(por_pagina))
    return Edital(arquivo=edital.arquivo, paginas=paginas)
