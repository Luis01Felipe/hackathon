"""Repositório em sistema de arquivos (sem banco, conforme o escopo do hackathon).

Estrutura:
    <raiz>/projetos/<id>/projeto.json, edital.pdf, modelo.ifc, ids.xml
    <raiz>/verificacoes/<vid>/verificacao.json, relatorio.json, relatorio.html, resultado.bcf
"""

import re
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

    def file_path(self, projeto_id: str, nome: str) -> str:
        return str(self._pasta_projeto(projeto_id) / _validar(nome, _NOME_SEGURO))

    def write_file(self, projeto_id: str, nome: str, conteudo: bytes) -> str:
        caminho = Path(self.file_path(projeto_id, nome))
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(conteudo)
        return str(caminho)

    def read_file(self, projeto_id: str, nome: str) -> bytes | None:
        try:
            caminho = Path(self.file_path(projeto_id, nome))
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

    def save_relatorio(self, relatorio: Relatorio, html: str, bcf: bytes | None) -> None:
        pasta = self._pasta_verificacao(relatorio.verificacao_id)
        pasta.mkdir(parents=True, exist_ok=True)
        (pasta / "relatorio.json").write_bytes(_RELATORIO.dump_json(relatorio, indent=2))
        (pasta / "relatorio.html").write_text(html, encoding="utf-8")
        if bcf is not None:
            (pasta / "resultado.bcf").write_bytes(bcf)

    def get_relatorio(self, verificacao_id: str) -> Relatorio | None:
        try:
            arquivo = self._pasta_verificacao(verificacao_id) / "relatorio.json"
        except ValueError:
            return None
        if not arquivo.exists():
            return None
        return _RELATORIO.validate_json(arquivo.read_bytes())

    def relatorio_file(self, verificacao_id: str, nome: str) -> str | None:
        try:
            caminho = self._pasta_verificacao(verificacao_id) / _validar(nome, _NOME_SEGURO)
        except ValueError:
            return None
        return str(caminho) if caminho.exists() else None
