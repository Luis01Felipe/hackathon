"""Abre um IFC a partir dos bytes em memória, sem gravar em disco persistente.

O mesmo arquivo é lido várias vezes no fluxo (resumo, validação IDS e
geometria). O cache LRU, por hash do conteúdo, evita reler o IFC a cada etapa.
"""

import contextlib
import hashlib
import os
import tempfile
from collections import OrderedDict
from threading import Lock

import ifcopenshell

MAX_ARQUIVOS_EM_CACHE = 4
_PASTA_MEMORIA = "/dev/shm"


class IfcInvalidoError(ValueError):
    """O arquivo não pôde ser lido como IFC."""


_cache: OrderedDict[str, ifcopenshell.file] = OrderedDict()
_trava = Lock()


def _de_texto(conteudo: bytes) -> ifcopenshell.file | None:
    try:
        texto = conteudo.decode("utf-8")
    except UnicodeDecodeError:
        return None
    try:
        return ifcopenshell.file.from_string(texto)
    except Exception:  # IfcOpenShell lança vários tipos
        return None


def _de_arquivo_temporario(conteudo: bytes) -> ifcopenshell.file:
    """Reserva: arquivo temporário em memória (/dev/shm), apagado logo após a leitura."""
    pasta = _PASTA_MEMORIA if os.path.isdir(_PASTA_MEMORIA) else None
    descritor, caminho = tempfile.mkstemp(suffix=".ifc", dir=pasta)
    try:
        with os.fdopen(descritor, "wb") as arquivo:
            arquivo.write(conteudo)
        return ifcopenshell.open(caminho)
    except Exception as erro:
        raise IfcInvalidoError(f"Não foi possível ler o IFC: {erro}") from erro
    finally:
        with contextlib.suppress(OSError):
            os.remove(caminho)


def abrir_ifc(conteudo: bytes) -> ifcopenshell.file:
    chave = hashlib.sha256(conteudo).hexdigest()
    with _trava:
        if chave in _cache:
            _cache.move_to_end(chave)
            return _cache[chave]
    modelo = _de_texto(conteudo) or _de_arquivo_temporario(conteudo)
    with _trava:
        _cache[chave] = modelo
        while len(_cache) > MAX_ARQUIVOS_EM_CACHE:
            _cache.popitem(last=False)
    return modelo


def esquecer(conteudo: bytes) -> None:
    """Remove o IFC do cache (usado ao apagar um projeto)."""
    with _trava:
        _cache.pop(hashlib.sha256(conteudo).hexdigest(), None)
