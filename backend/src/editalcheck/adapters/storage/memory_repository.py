"""Repositório em memória para o modo efêmero (RF-090 a RF-094, RNF-11).

Nada do usuário vai para o disco: edital, IFC, lições, projeto, IDS, relatório
e BCF ficam só na RAM do processo. Cada projeto expira depois do TTL sem
acesso, é apagado pelo botão "Encerrar e apagar dados" e some quando o
processo termina. As verificações são apagadas junto com o projeto.
"""

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from editalcheck.application.errors import NaoEncontradoError
from editalcheck.domain.models import Projeto, Relatorio, Verificacao

LIMITE_PROJETOS_PADRAO = 50


@dataclass
class _Entrada:
    projeto: Projeto
    arquivos: dict[str, bytes] = field(default_factory=dict)
    verificacoes: set[str] = field(default_factory=set)
    acesso: float = field(default_factory=time.monotonic)


@dataclass
class _EntradaVerificacao:
    verificacao: Verificacao
    relatorio: Relatorio | None = None
    arquivos: dict[str, bytes] = field(default_factory=dict)


class MemoryProjectRepository:
    def __init__(
        self,
        ttl_s: float,
        limite_projetos: int = LIMITE_PROJETOS_PADRAO,
        ao_expirar: Callable[[str, Mapping[str, bytes]], None] | None = None,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_s
        self._limite = max(1, limite_projetos)
        self._ao_expirar = ao_expirar
        self._relogio = relogio
        self._trava = threading.RLock()
        self._projetos: dict[str, _Entrada] = {}
        self._verificacoes: dict[str, _EntradaVerificacao] = {}

    # ------------------------------------------------------------------ manutenção

    def _remover(self, projeto_id: str) -> bool:
        entrada = self._projetos.pop(projeto_id, None)
        if entrada is None:
            return False
        for verificacao_id in entrada.verificacoes:
            self._verificacoes.pop(verificacao_id, None)
        if self._ao_expirar:
            self._ao_expirar(projeto_id, entrada.arquivos)
        return True

    def _limpar_expirados(self) -> None:
        agora = self._relogio()
        vencidos = [pid for pid, e in self._projetos.items() if agora - e.acesso > self._ttl]
        for projeto_id in vencidos:
            self._remover(projeto_id)
        excedentes = len(self._projetos) - self._limite
        if excedentes > 0:
            antigos = sorted(self._projetos.items(), key=lambda item: item[1].acesso)
            for projeto_id, _ in antigos[:excedentes]:
                self._remover(projeto_id)

    def _entrada(self, projeto_id: str) -> _Entrada | None:
        self._limpar_expirados()
        entrada = self._projetos.get(projeto_id)
        if entrada is not None:
            entrada.acesso = self._relogio()
        return entrada

    # ------------------------------------------------------------------ projetos

    def save(self, projeto: Projeto) -> None:
        with self._trava:
            entrada = self._entrada(projeto.id)
            if entrada is None:
                self._projetos[projeto.id] = _Entrada(projeto=projeto)
                self._limpar_expirados()
                return
            entrada.projeto = projeto

    def get(self, projeto_id: str) -> Projeto | None:
        with self._trava:
            entrada = self._entrada(projeto_id)
            return entrada.projeto if entrada else None

    def delete(self, projeto_id: str) -> bool:
        with self._trava:
            return self._remover(projeto_id)

    def write_file(self, projeto_id: str, nome: str, conteudo: bytes) -> None:
        with self._trava:
            entrada = self._entrada(projeto_id)
            if entrada is None:
                raise NaoEncontradoError(
                    "Projeto não encontrado (pode ter expirado ou sido apagado)."
                )
            entrada.arquivos[nome] = conteudo

    def read_file(self, projeto_id: str, nome: str) -> bytes | None:
        with self._trava:
            entrada = self._entrada(projeto_id)
            return entrada.arquivos.get(nome) if entrada else None

    # ------------------------------------------------------------------ verificações

    def save_verificacao(self, verificacao: Verificacao) -> None:
        with self._trava:
            entrada = self._entrada(verificacao.projeto_id)
            if entrada is None:
                return
            entrada.verificacoes.add(verificacao.id)
            atual = self._verificacoes.get(verificacao.id)
            if atual is None:
                self._verificacoes[verificacao.id] = _EntradaVerificacao(verificacao)
                return
            atual.verificacao = verificacao

    def get_verificacao(self, verificacao_id: str) -> Verificacao | None:
        with self._trava:
            self._limpar_expirados()
            atual = self._verificacoes.get(verificacao_id)
            return atual.verificacao if atual else None

    def save_relatorio(self, relatorio: Relatorio) -> None:
        with self._trava:
            atual = self._verificacoes.get(relatorio.verificacao_id)
            if atual is not None:
                atual.relatorio = relatorio

    def get_relatorio(self, verificacao_id: str) -> Relatorio | None:
        with self._trava:
            self._limpar_expirados()
            atual = self._verificacoes.get(verificacao_id)
            return atual.relatorio if atual else None

    def write_relatorio_file(self, verificacao_id: str, nome: str, conteudo: bytes) -> None:
        with self._trava:
            atual = self._verificacoes.get(verificacao_id)
            if atual is not None:
                atual.arquivos[nome] = conteudo

    def read_relatorio_file(self, verificacao_id: str, nome: str) -> bytes | None:
        with self._trava:
            self._limpar_expirados()
            atual = self._verificacoes.get(verificacao_id)
            return atual.arquivos.get(nome) if atual else None
