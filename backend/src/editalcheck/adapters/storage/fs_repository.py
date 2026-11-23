"""Repositório em sistema de arquivos (modo ``persistente``, para desenvolvimento).

O deploy usa o modo ``efemero`` (``MemoryProjectRepository``), que não grava
arquivos do usuário em disco. Estrutura deste modo:
    <raiz>/projetos/<id>/projeto.json, edital.pdf, modelo.ifc, ids.xml
    <raiz>/verificacoes/<vid>/verificacao.json, relatorio.json, relatorio.html, resultado.bcf
"""

import re
import shutil
import threading
from pathlib import Path

from pydantic import TypeAdapter

from editalcheck.domain.models import Projeto, Relatorio, Verificacao

_ID_SEGURO = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NOME_SEGURO = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_PROJETO = TypeAdapter(Projeto)
_VERIFICACAO = TypeAdapter(Verificacao)
_RELATORIO = TypeAdapter(Relatorio)


def _validar(identificador: str, padrao: re.Pattern[str] = _ID_SEGURO) -> str:
    if not padrao.match(identificador) or ".." in identificador:
        raise ValueError(f"Identificador inválido: {identificador!r}")
    return identificador


class FsProjectRepository:
    def __init__(self, raiz: Path) -> None:
        self._projetos = raiz / "projetos"
        self._verificacoes = raiz / "verificacoes"
        self._projetos.mkdir(parents=True, exist_ok=True)
        self._verificacoes.mkdir(parents=True, exist_ok=True)
        self._trava = threading.Lock()
        self._cache_projetos: dict[str, Projeto] = {}

    # ------------------------------------------------------------------ projetos

    def _pasta_projeto(self, projeto_id: str) -> Path:
        return self._projetos / _validar(projeto_id)

    def save(self, projeto: Projeto) -> None:
        pasta = self._pasta_projeto(projeto.id)
        pasta.mkdir(parents=True, exist_ok=True)
        with self._trava:
            (pasta / "projeto.json").write_bytes(_PROJETO.dump_json(projeto))
            self._cache_projetos[projeto.id] = projeto

    def get(self, projeto_id: str) -> Projeto | None:
        try:
            pasta = self._pasta_projeto(projeto_id)
        except ValueError:
            return None
        if projeto_id in self._cache_projetos:
            return self._cache_projetos[projeto_id]
        arquivo = pasta / "projeto.json"
        if not arquivo.exists():
            return None
        projeto = _PROJETO.validate_json(arquivo.read_bytes())
        self._cache_projetos[projeto_id] = projeto
        return projeto

    def delete(self, projeto_id: str) -> bool:
        try:
            pasta = self._pasta_projeto(projeto_id)
        except ValueError:
            return False
        with self._trava:
            self._cache_projetos.pop(projeto_id, None)
        if not pasta.exists():
            return False
        for arquivo in self._verificacoes.glob("*/verificacao.json"):
            verificacao = _VERIFICACAO.validate_json(arquivo.read_bytes())
            if verificacao.projeto_id == projeto_id:
                shutil.rmtree(arquivo.parent, ignore_errors=True)
        shutil.rmtree(pasta, ignore_errors=True)
        return True

    def _arquivo(self, projeto_id: str, nome: str) -> Path:
        return self._pasta_projeto(projeto_id) / _validar(nome, _NOME_SEGURO)

    def write_file(self, projeto_id: str, nome: str, conteudo: bytes) -> None:
        caminho = self._arquivo(projeto_id, nome)
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)

    def read_file(self, projeto_id: str, nome: str) -> bytes | None:
        try:
            caminho = self._arquivo(projeto_id, nome)
        except ValueError:
            return None
        return caminho.read_bytes() if caminho.exists() else None

    # ------------------------------------------------------------------ verificações

    def _pasta_verificacao(self, verificacao_id: str) -> Path:
        return self._verificacoes / _validar(verificacao_id)

    def save_verificacao(self, verificacao: Verificacao) -> None:
        pasta = self._pasta_verificacao(verificacao.id)
        pasta.mkdir(parents=True, exist_ok=True)
        with self._trava:
            (pasta / "verificacao.json").write_bytes(_VERIFICACAO.dump_json(verificacao))

    def get_verificacao(self, verificacao_id: str) -> Verificacao | None:
        try:
            arquivo = self._pasta_verificacao(verificacao_id) / "verificacao.json"
        except ValueError:
            return None
        if not arquivo.exists():
            return None
        with self._trava:
            return _VERIFICACAO.validate_json(arquivo.read_bytes())

    def save_relatorio(self, relatorio: Relatorio) -> None:
        pasta = self._pasta_verificacao(relatorio.verificacao_id)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "relatorio.json").write_bytes(_RELATORIO.dump_json(relatorio, indent=2))

    def get_relatorio(self, verificacao_id: str) -> Relatorio | None:
        try:
            arquivo = self._pasta_verificacao(verificacao_id) / "relatorio.json"
        except ValueError:
            return None
        if not arquivo.exists():
            return None
        return _RELATORIO.validate_json(arquivo.read_bytes())

    def write_relatorio_file(self, verificacao_id: str, nome: str, conteudo: bytes) -> None:
        pasta = self._pasta_verificacao(verificacao_id)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / _validar(nome, _NOME_SEGURO)).write_bytes(conteudo)

    def read_relatorio_file(self, verificacao_id: str, nome: str) -> bytes | None:
        try:
            caminho = self._pasta_verificacao(verificacao_id) / _validar(nome, _NOME_SEGURO)
        except ValueError:
            return None
        return caminho.read_bytes() if caminho.exists() else None
