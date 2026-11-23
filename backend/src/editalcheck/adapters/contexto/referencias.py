"""Documentos de referência autorizados, usados como contexto do LLM (RF-142).

Coloque arquivos .txt, .md ou .pdf em ``backend/resources/contexto/``. Exemplo:
o modelo de requisitos de informação cedido pela banca do hackathon. Para cada
tópico do edital, o sistema escolhe só os parágrafos mais parecidos com o
tópico, dentro de um orçamento de caracteres (RNF-16). Assim o contexto ajuda
sem inflar o prompt, o que aumentaria o risco de alucinação.

O texto vai ao LLM entre delimitadores, como dado e nunca como instrução (G3).
"""

import logging
from dataclasses import dataclass
from pathlib import Path

from editalcheck.adapters.pdf.pymupdf_reader import TextoOuPdfReader
from editalcheck.domain.evidence import compactar_espacos
from editalcheck.domain.licoes import palavras_chave

logger = logging.getLogger("editalcheck.contexto")
EXTENSOES = (".txt", ".md", ".pdf")
IGNORADOS = frozenset({"LEIA-ME", "README"})
TAMANHO_MINIMO_PARAGRAFO = 80
TAMANHO_MAXIMO_PARAGRAFO = 1200
ORCAMENTO_CARACTERES = 6000  # ~1.500 tokens por chamada
MAX_TRECHOS = 6


@dataclass(frozen=True)
class _Paragrafo:
    documento: str
    texto: str
    chaves: frozenset[str]


class ContextoReferencia:
    def __init__(self, pasta: Path, orcamento: int = ORCAMENTO_CARACTERES) -> None:
        self._orcamento = orcamento
        self._paragrafos = self._carregar(pasta)

    @property
    def documentos(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(p.documento for p in self._paragrafos))

    def _carregar(self, pasta: Path) -> list[_Paragrafo]:
        if not pasta.is_dir():
            return []
        leitor = TextoOuPdfReader()
        paragrafos: list[_Paragrafo] = []
        for arquivo in sorted(pasta.iterdir()):
            if arquivo.suffix.lower() not in EXTENSOES or arquivo.stem.upper() in IGNORADOS:
                continue
            try:
                documento = leitor.read(arquivo.read_bytes(), arquivo.name)
            except ValueError as erro:
                logger.warning("Documento de referência ignorado (%s): %s", arquivo.name, erro)
                continue
            for pagina in documento.paginas:
                for bloco in pagina.texto.split("\n\n"):
                    texto = compactar_espacos(bloco)[:TAMANHO_MAXIMO_PARAGRAFO]
                    if len(texto) < TAMANHO_MINIMO_PARAGRAFO:
                        continue
                    paragrafos.append(
                        _Paragrafo(arquivo.name, texto, frozenset(palavras_chave(texto)))
                    )
        if paragrafos:
            logger.info("Contexto de referência: %d parágrafos carregados", len(paragrafos))
        return paragrafos

    def select(self, texto: str) -> list[tuple[str, str]]:
        if not self._paragrafos:
            return []
        alvo = palavras_chave(texto)
        if not alvo:
            return []
        pontuados = sorted(
            (
                (len(alvo & p.chaves) / (len(p.chaves) ** 0.5 or 1), p)
                for p in self._paragrafos
                if alvo & p.chaves
            ),
            key=lambda item: item[0],
            reverse=True,
        )
        escolhidos: list[tuple[str, str]] = []
        usados = 0
        for _, paragrafo in pontuados[:MAX_TRECHOS]:
            if usados + len(paragrafo.texto) > self._orcamento:
                break
            escolhidos.append((paragrafo.documento, paragrafo.texto))
            usados += len(paragrafo.texto)
        return escolhidos
