"""Segmentação determinística do edital em tópicos hierárquicos (RF-10).

Regras:
- Um tópico começa num título numerado de nível 1 ou 2 ("5 DOS REQUISITOS",
  "5.1 Portas", "5 – DOS REQUISITOS"). Cláusulas de nível 3 ("5.1.1 ...")
  ficam dentro do tópico.
- A numeração precisa crescer dentro do mesmo escopo, o que evita confundir
  itens de lista com títulos.
- Todo subtópico aponta para o pai (``pai_id``). Um título de seção sem texto
  próprio vira **agrupador**: aparece na árvore, mas não é verificado.
- Se um subtópico aparece sem o título da seção (ex.: "4.1" logo depois de
  "3.2"), o sistema cria o agrupador implícito "Seção 4".
- "ANEXO I – ..." (ou "APÊNDICE") abre um novo escopo: a numeração reinicia e
  os títulos numerados do anexo ficam abaixo dele.
- As linhas do sumário impresso nunca viram títulos. Se o sumário tem entradas
  suficientes, só abrem tópicos os números que constam nele, com título
  compatível (ver ``sumario``).
- Sem títulos reconhecidos, cada página vira um tópico.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from editalcheck.domain.evidence import desifenizar, normalizar, remover_acentos
from editalcheck.domain.models import Edital, Pagina, Topico
from editalcheck.domain.sumario import Sumario, ler_sumario

_NUMERADO = re.compile(r"^(\d{1,2})(?:\.(\d{1,2}))?\.?(?:\s*[-–—:])?\s+(.{3,100})$")
_ANEXO = re.compile(
    r"^(ANEXO|AP[ÊE]NDICE)\s+([IVXLC]+|\d{1,3}|[A-Z])\b\s*(?:[-–—:.]\s*)?(.{0,100})$"
)
_TAMANHO_MINIMO_CORPO = 20
_MAX_SUBTOPICOS_IMPLICITOS = 3  # "4.1".."4.3" sem título "4" ainda abrem a seção

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
_MARCADOR = re.compile(r"^\[p\.\s*(\d+)\]$")


@dataclass(frozen=True)
class _Linha:
    pagina: int
    texto: str


@dataclass(frozen=True)
class _Titulo:
    indice_linha: int | None  # None: agrupador implícito, sem linha própria
    numero: str
    titulo: str
    nivel: int
    pai: int | None  # posição do título pai na lista de títulos


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


class _Leitor:
    """Percorre as linhas e reconhece os títulos, mantendo o escopo da numeração."""

    def __init__(self, sumario: Sumario) -> None:
        self._sumario = sumario
        self.titulos: list[_Titulo] = []
        self._anexo: int | None = None
        self._secao: int | None = None
        self._maior = 0
        self._menor = 0

    def _adicionar(self, titulo: _Titulo) -> int:
        self.titulos.append(titulo)
        return len(self.titulos) - 1

    @property
    def _base(self) -> int:
        return 1 if self._anexo is not None else 0

    def _titulo_aceito(self, numero: str, titulo: str) -> str | None:
        if not self._sumario.ativo:
            return titulo
        return self._sumario.titulo_conferido(numero, titulo)

    def _titulo_implicito(self, maior: int) -> str:
        if not self._sumario.ativo:
            return f"Seção {maior}"
        return self._sumario.titulo(str(maior)) or f"Seção {maior}"

    def anexo(self, indice: int, encontrado: re.Match[str]) -> None:
        tipo = encontrado.group(1).capitalize()
        numero = f"{tipo} {encontrado.group(2)}"
        titulo = self._titulo_aceito(numero, encontrado.group(3).strip() or numero)
        if titulo is None:
            return
        self._anexo = self._adicionar(_Titulo(indice, numero, titulo, 1, None))
        self._secao, self._maior, self._menor = None, 0, 0

    def numerado(self, indice: int, maior: int, menor: int | None, titulo: str) -> None:
        numero = str(maior) if menor is None else f"{maior}.{menor}"
        aceito = self._titulo_aceito(numero, titulo)
        if aceito is None:
            return
        titulo = aceito
        if menor is None:
            if maior <= self._maior:
                return
            self._secao = self._adicionar(
                _Titulo(indice, str(maior), titulo, 1 + self._base, self._anexo)
            )
            self._maior, self._menor = maior, 0
            return
        if maior < self._maior or (maior == self._maior and menor <= self._menor):
            return
        if maior > self._maior:
            if menor > _MAX_SUBTOPICOS_IMPLICITOS:
                return
            self._secao = self._adicionar(
                _Titulo(
                    None, str(maior), self._titulo_implicito(maior), 1 + self._base, self._anexo
                )
            )
            self._maior = maior
        self._adicionar(_Titulo(indice, numero, titulo, 2 + self._base, self._secao))
        self._menor = menor

    def ler(self, linhas: list[_Linha]) -> list[_Titulo]:
        for indice, linha in enumerate(linhas):
            if indice in self._sumario.linhas:
                continue
            anexo = _ANEXO.match(linha.texto)
            if anexo:
                self.anexo(indice, anexo)
                continue
            numerado = _NUMERADO.match(linha.texto)
            if not numerado or not _eh_titulo_plausivel(numerado.group(3)):
                continue
            menor = int(numerado.group(2)) if numerado.group(2) else None
            self.numerado(indice, int(numerado.group(1)), menor, numerado.group(3).strip())
        return self.titulos


def _texto_com_marcadores(linhas: Sequence[_Linha]) -> str:
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


def _corpo(linhas: Sequence[_Linha]) -> int:
    return sum(len(linha.texto) for linha in linhas)


def _por_pagina(edital: Edital) -> list[Topico]:
    topicos: list[Topico] = []
    for pagina in edital.paginas:
        linhas = [
            _Linha(pagina.numero, " ".join(texto.split())) for texto in pagina.texto.splitlines()
        ]
        linhas = [linha for linha in linhas if linha.texto]
        if not linhas:
            continue
        texto = _texto_com_marcadores(linhas)
        topicos.append(
            Topico(
                id=f"TOP-{len(topicos) + 1:02d}",
                numero=str(pagina.numero),
                titulo=f"Página {pagina.numero}",
                nivel=1,
                pagina_inicio=pagina.numero,
                pagina_fim=pagina.numero,
                texto=texto,
                relevante_bim=eh_relevante_bim(texto),
            )
        )
    return topicos


def _trechos(titulos: list[_Titulo], linhas: list[_Linha]) -> list[list[_Linha]]:
    """Linhas próprias de cada título: do título até o próximo título com linha."""
    trechos: list[list[_Linha]] = []
    for posicao, titulo in enumerate(titulos):
        if titulo.indice_linha is None:
            trechos.append([])
            continue
        proximo = next(
            (t.indice_linha for t in titulos[posicao + 1 :] if t.indice_linha is not None),
            len(linhas),
        )
        trechos.append(linhas[titulo.indice_linha : proximo])
    return trechos


def segmentar(edital: Edital) -> list[Topico]:
    linhas = _linhas(edital)
    if not linhas:
        return []
    sumario = ler_sumario([linha.texto for linha in linhas])
    titulos = _Leitor(sumario).ler(linhas)
    if not titulos:
        return _por_pagina(edital)

    trechos = _trechos(titulos, linhas)
    # De baixo para cima: um título fica se tem texto próprio ou algum filho que ficou.
    manter = [False] * len(titulos)
    for posicao in reversed(range(len(titulos))):
        filho_mantido = any(
            manter[q] for q in range(posicao + 1, len(titulos)) if titulos[q].pai == posicao
        )
        manter[posicao] = filho_mantido or _corpo(trechos[posicao][1:]) >= _TAMANHO_MINIMO_CORPO
    mantidos = [posicao for posicao, fica in enumerate(manter) if fica]
    tem_filhos = {titulos[q].pai for q in mantidos if titulos[q].pai is not None}

    topicos: list[Topico] = []
    primeira_linha = next(t.indice_linha for t in titulos if t.indice_linha is not None)
    preambulo = linhas[:primeira_linha]
    if _corpo(preambulo) >= _TAMANHO_MINIMO_CORPO:
        texto = _texto_com_marcadores(preambulo)
        topicos.append(
            Topico(
                id="TOP-01",
                numero="0",
                titulo="Preâmbulo",
                nivel=1,
                pagina_inicio=preambulo[0].pagina,
                pagina_fim=preambulo[-1].pagina,
                texto=texto,
                relevante_bim=eh_relevante_bim(texto),
            )
        )

    ids: dict[int, str] = {}
    for posicao in mantidos:
        titulo, trecho = titulos[posicao], trechos[posicao]
        identificador = f"TOP-{len(topicos) + 1:02d}"
        ids[posicao] = identificador
        if not trecho:  # agrupador implícito: herda a página do primeiro subtópico
            pagina = next(trechos[p][0].pagina for p in mantidos if p > posicao and trechos[p])
            inicio = fim = pagina
        else:
            inicio, fim = trecho[0].pagina, trecho[-1].pagina
        texto = _texto_com_marcadores(trecho)
        topicos.append(
            Topico(
                id=identificador,
                numero=titulo.numero,
                titulo=titulo.titulo,
                nivel=titulo.nivel,
                pagina_inicio=inicio,
                pagina_fim=fim,
                texto=texto,
                relevante_bim=eh_relevante_bim(texto),
                pai_id=ids.get(titulo.pai) if titulo.pai is not None else None,
                agrupador=posicao in tem_filhos and _corpo(trecho[1:]) < _TAMANHO_MINIMO_CORPO,
            )
        )
    return propagar_relevancia(topicos)


# --------------------------------------------------------------------------- árvore


def filhos(topicos: Sequence[Topico], topico_id: str) -> list[Topico]:
    return [t for t in topicos if t.pai_id == topico_id]


def descendentes(topicos: Sequence[Topico], topico_id: str) -> list[Topico]:
    encontrados: list[Topico] = []
    for filho in filhos(topicos, topico_id):
        encontrados.append(filho)
        encontrados.extend(descendentes(topicos, filho.id))
    return encontrados


def propagar_relevancia(topicos: Sequence[Topico]) -> list[Topico]:
    """Um agrupador é relevante para BIM se algum descendente for."""
    resultado = list(topicos)
    for posicao in reversed(range(len(resultado))):
        topico = resultado[posicao]
        if not topico.agrupador:
            continue
        relevante = any(t.relevante_bim for t in resultado if t.pai_id == topico.id)
        resultado[posicao] = replace(topico, relevante_bim=relevante)
    return resultado


def expandir_selecao(topicos: Sequence[Topico], ids: Iterable[str]) -> list[Topico]:
    """Tópicos verificáveis da seleção: agrupadores viram seus descendentes."""
    por_id = {t.id: t for t in topicos}
    escolhidos: dict[str, Topico] = {}
    for identificador in ids:
        topico = por_id.get(identificador)
        if topico is None:
            continue
        candidatos = [topico, *descendentes(topicos, topico.id)] if topico.agrupador else [topico]
        for candidato in candidatos:
            if not candidato.agrupador:
                escolhidos.setdefault(candidato.id, candidato)
    return [t for t in topicos if t.id in escolhidos]


# --------------------------------------------------------------------------- páginas


def paginas_do_topico(topico: Topico) -> range:
    return range(topico.pagina_inicio, topico.pagina_fim + 1)


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
