"""Extrator de requisitos por regras (modo sem LLM e base de comparação).

Lê cada frase com verbo de obrigação, identifica a classe IFC pelo
vocabulário em português e a propriedade pelo nome oficial ou por sinônimo.
O trecho é sempre a frase literal, então passa na salvaguarda S2.
"""

import re
from collections.abc import Iterator
from dataclasses import dataclass, replace

from editalcheck.adapters.resources import VocabularioPt
from editalcheck.domain.evidence import normalizar, remover_acentos
from editalcheck.domain.findings import exigencia
from editalcheck.domain.models import (
    Cardinalidade,
    ContextoVocabulario,
    Evidencia,
    Requisito,
    Restricao,
    TipoFaceta,
    TipoRestricao,
    Topico,
)
from editalcheck.domain.vagueness import dividir_sentencas

_MARCADOR = re.compile(r"^\[p\.\s*(\d+)\]$")
_NUMERO = r"(\d+(?:[.,]\d+)?)"
_UNIDADE = r"\s*(m|cm|mm)?\b"
_INTERVALO = re.compile(rf"entre\s+{_NUMERO}{_UNIDADE}\s+e\s+{_NUMERO}{_UNIDADE}")
_MINIMO = re.compile(
    rf"(?:minim[oa] de|no minimo|maior ou igual a|superior a)\s+{_NUMERO}{_UNIDADE}"
)
_MAXIMO = re.compile(
    rf"(?:maxim[oa] de|no maximo|menor ou igual a|inferior a)\s+{_NUMERO}{_UNIDADE}"
)
_ENTRE_ASPAS = re.compile(r"[\"“]([^\"”]{1,60})[\"”]")
_OPCIONAL = ("quando houver", "se houver", "quando aplicavel", "se aplicavel")
_PROIBIDO = ("nao devera", "nao deverao", "e vedado", "e vedada", "proibido", "proibida")
_ESCALA = {"m": 1.0, "cm": 0.01, "mm": 0.001, None: 1.0}
_TEMAS_GERAIS = ("modelo", "ifc", "arquivo", "arquivos", "projeto", "elementos")
_MATERIAL = re.compile(
    r"(informar|indicar|possuir|ter|conter|associad\w*|atribuid\w*)\s+(o\s+|um\s+|os\s+)?materia(l|is)\b"
)


@dataclass(frozen=True)
class _Faceta:
    faceta: TipoFaceta
    pset: str | None
    propriedade: str | None
    tipo_dado: str | None
    posicao: int


def _numero(texto: str, unidade: str | None) -> float:
    return float(texto.replace(",", ".")) * _ESCALA.get(unidade, 1.0)


def _chave(texto: str) -> str:
    return remover_acentos(normalizar(texto))


def _contem(chave: str, termo: str) -> int:
    encontrado = re.search(rf"(?<!\w){re.escape(_chave(termo))}(?!\w)", chave)
    return encontrado.start() if encontrado else -1


def sentencas_com_pagina(texto_topico: str) -> Iterator[tuple[int, str]]:
    pagina = 0
    bloco: list[str] = []
    for linha in texto_topico.splitlines():
        marcador = _MARCADOR.match(linha.strip())
        if marcador:
            if bloco:
                yield from ((pagina, s) for s in dividir_sentencas("\n".join(bloco)))
            pagina, bloco = int(marcador.group(1)), []
            continue
        bloco.append(linha)
    if bloco:
        yield from ((pagina, s) for s in dividir_sentencas("\n".join(bloco)))


class RulesRequirementExtractor:
    def __init__(self, vocabulario: VocabularioPt) -> None:
        self._vocab = vocabulario

    # ------------------------------------------------------------------ detecção

    def _tem_obrigacao(self, chave: str) -> bool:
        return any(_contem(chave, termo) >= 0 for termo in self._vocab.obrigacao)

    def _classes(self, chave: str, contexto: ContextoVocabulario) -> list[str]:
        presentes = {c.nome for c in contexto.classes_modelo}
        encontradas: list[tuple[int, str]] = []
        for classe, termos in self._vocab.classes.items():
            posicoes = [p for p in (_contem(chave, t) for t in termos) if p >= 0]
            if posicoes:
                encontradas.append((min(posicoes), classe))
        encontradas.sort()
        nomes = [classe for _, classe in encontradas]
        no_modelo = [c for c in nomes if c in presentes]
        return no_modelo[:1] or nomes[:1]

    def _oficiais(self, contexto: ContextoVocabulario, classe: str) -> list[tuple[str, str]]:
        for nome, propriedades in contexto.propriedades_por_classe:
            if nome == classe:
                pares = (p.split(".", 1) for p in propriedades)
                return [(pset, nome) for pset, nome in pares]
        return []

    def _tipo(self, contexto: ContextoVocabulario, pset: str, nome: str) -> str | None:
        oficial = contexto.propriedade_oficial(pset, nome)
        return oficial.tipo_dado if oficial else None

    def _facetas(
        self, sentenca: str, chave: str, classe: str, contexto: ContextoVocabulario
    ) -> list[_Faceta]:
        facetas: list[_Faceta] = []
        vistas: set[str] = set()
        oficiais = self._oficiais(contexto, classe)
        pset_citado = re.search(r"\b(Pset_\w+)", sentenca)
        for pset, nome in oficiais:
            posicao = sentenca.find(nome)
            if posicao < 0 or not re.search(rf"\b{re.escape(nome)}\b", sentenca) or nome in vistas:
                continue
            if (
                pset_citado
                and pset_citado.group(1) != pset
                and any(p == pset_citado.group(1) and n == nome for p, n in oficiais)
            ):
                continue
            vistas.add(nome)
            facetas.append(
                _Faceta(
                    TipoFaceta.PROPRIEDADE, pset, nome, self._tipo(contexto, pset, nome), posicao
                )
            )
        for nome, sinonimos in self._vocab.propriedades.items():
            if nome in vistas:
                continue
            posicoes = [p for p in (_contem(chave, s) for s in sinonimos) if p >= 0]
            candidatos = [pset for pset, n in oficiais if n == nome]
            if not posicoes or not candidatos:
                continue
            pset = next((p for p in candidatos if p.lower().endswith("common")), candidatos[0])
            vistas.add(nome)
            facetas.append(
                _Faceta(
                    TipoFaceta.PROPRIEDADE,
                    pset,
                    nome,
                    self._tipo(contexto, pset, nome),
                    min(posicoes),
                )
            )
        for atributo in self._vocab.atributos:
            encontrado = re.search(rf"atributo\s+[\"“]?{atributo}\b", sentenca)
            if encontrado:
                facetas.append(
                    _Faceta(TipoFaceta.ATRIBUTO, None, atributo, None, encontrado.start())
                )
        if "classifica" in chave:
            for sistema in self._vocab.sistemas_classificacao:
                posicao = _contem(chave, sistema)
                if posicao >= 0:
                    facetas.append(_Faceta(TipoFaceta.CLASSIFICACAO, sistema, None, None, posicao))
                    break
        material = _MATERIAL.search(chave)
        if material and not facetas:
            facetas.append(_Faceta(TipoFaceta.MATERIAL, None, None, None, material.start()))
        return sorted(facetas, key=lambda f: f.posicao)

    def _restricao(self, chave: str, sentenca: str) -> tuple[Restricao | None, int]:
        intervalo = _INTERVALO.search(chave)
        if intervalo:
            minimo = _numero(intervalo.group(1), intervalo.group(2) or intervalo.group(4))
            maximo = _numero(intervalo.group(3), intervalo.group(4))
            return Restricao(
                TipoRestricao.INTERVALO, minimo=minimo, maximo=maximo
            ), intervalo.start()
        minimo = _MINIMO.search(chave)
        if minimo:
            valor = _numero(minimo.group(1), minimo.group(2))
            return Restricao(TipoRestricao.INTERVALO, minimo=valor), minimo.start()
        maximo = _MAXIMO.search(chave)
        if maximo:
            valor = _numero(maximo.group(1), maximo.group(2))
            return Restricao(TipoRestricao.INTERVALO, maximo=valor), maximo.start()
        if "um dos valores" in chave or "valores:" in chave:
            valores = tuple(v.strip() for v in _ENTRE_ASPAS.findall(sentenca))
            if valores:
                return Restricao(TipoRestricao.ENUMERACAO, valores=valores), _contem(
                    chave, "valores"
                )
        return None, -1

    def _cardinalidade(self, chave: str) -> Cardinalidade:
        if any(termo in chave for termo in _PROIBIDO):
            return Cardinalidade.PROIBIDA
        if any(termo in chave for termo in _OPCIONAL):
            return Cardinalidade.OPCIONAL
        return Cardinalidade.OBRIGATORIA

    # ------------------------------------------------------------------ extração

    def _nao_verificavel(
        self, topico: Topico, pagina: int, sentenca: str, classe: str | None, motivo: str
    ) -> Requisito:
        return Requisito(
            id="TMP",
            topico_id=topico.id,
            descricao=sentenca if len(sentenca) <= 160 else sentenca[:157] + "...",
            evidencia=Evidencia(pagina=pagina, trecho=sentenca),
            verificavel_por_ids=False,
            motivo_nao_verificavel=motivo,
            ifc_class=classe,
            gerado_por="regras",
        )

    def extract(self, topico: Topico, contexto: ContextoVocabulario) -> list[Requisito]:
        requisitos: list[Requisito] = []
        for pagina, sentenca in sentencas_com_pagina(topico.texto):
            chave = _chave(sentenca)
            if not self._tem_obrigacao(chave):
                continue
            classes = self._classes(chave, contexto)
            if not classes:
                if any(_contem(chave, t) >= 0 for t in self._vocab.nao_modelo):
                    requisitos.append(
                        self._nao_verificavel(
                            topico,
                            pagina,
                            sentenca,
                            None,
                            "Prazo, custo ou condição contratual: não é informação do modelo.",
                        )
                    )
                elif any(_contem(chave, t) >= 0 for t in _TEMAS_GERAIS):
                    requisitos.append(
                        self._nao_verificavel(
                            topico,
                            pagina,
                            sentenca,
                            None,
                            "Exigência geral sobre o modelo, os arquivos ou o projeto, sem classe IFC: "
                            "verificação manual.",
                        )
                    )
                continue
            classe = classes[0]
            facetas = self._facetas(sentenca, chave, classe, contexto)
            if not facetas:
                requisitos.append(
                    self._nao_verificavel(
                        topico,
                        pagina,
                        sentenca,
                        classe,
                        "A exigência não define propriedade, atributo ou valor verificável no modelo.",
                    )
                )
                continue
            restricao, posicao_restricao = self._restricao(chave, sentenca)
            alvo_restricao = None
            if restricao is not None:
                anteriores = [f for f in facetas if f.posicao <= posicao_restricao] or facetas
                alvo_restricao = anteriores[-1]
            cardinalidade = self._cardinalidade(chave)
            for faceta in facetas:
                requisito = Requisito(
                    id="TMP",
                    topico_id=topico.id,
                    descricao="",
                    evidencia=Evidencia(pagina=pagina, trecho=sentenca),
                    verificavel_por_ids=True,
                    ifc_class=classe,
                    faceta=faceta.faceta,
                    pset=faceta.pset,
                    propriedade=faceta.propriedade,
                    tipo_dado=faceta.tipo_dado,
                    restricao=restricao if faceta is alvo_restricao else None,
                    cardinalidade=cardinalidade,
                    gerado_por="regras",
                )
                requisitos.append(
                    replace(requisito, descricao=f"{classe} deve ter {exigencia(requisito)}")
                )
        return requisitos
