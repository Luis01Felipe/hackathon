"""Chamada estruturada ao LLM: prompts versionados, cache opcional e reparo (S1).

- RNF-03: temperatura 0, prompts versionados em arquivo e cache por
  hash(prompt_version + modelo + entrada). No modo efêmero não há cache em
  disco (RF-093): as respostas trazem trechos do edital.
- RF-195: cada chamada (e cada reparo) informa tokens e duração ao medidor.
- S1: a resposta precisa validar no schema Pydantic; se falhar, o erro volta
  ao LLM para reparo (máximo 2 tentativas).
- RNF-05: trocar de provedor exige só um novo ``JsonCompletion``.
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("editalcheck.llm")
T = TypeVar("T", bound=BaseModel)
_VERSAO = re.compile(r"^<!--\s*versao:\s*(\S+)\s*-->\s*$", re.MULTILINE)
MAX_REPAROS = 2


class LlmIndisponivelError(RuntimeError):
    """O provedor de LLM falhou (rede, cota, chave) ou não respondeu no schema."""


@dataclass(frozen=True)
class Uso:
    tokens_entrada: int = 0
    tokens_saida: int = 0


class RegistroConsumo(Protocol):
    def registrar(
        self,
        nome_prompt: str,
        tokens_entrada: int,
        tokens_saida: int,
        duracao_s: float,
        cache: bool = False,
    ) -> None: ...


class JsonCompletion(Protocol):
    modelo: str

    def complete(
        self, *, sistema: str, prompt: str, schema: type[BaseModel]
    ) -> tuple[str, Uso]: ...


@dataclass(frozen=True)
class Prompt:
    nome: str
    versao: str
    template: str


class PromptLoader:
    def __init__(self, pasta: Path) -> None:
        self._pasta = pasta
        self._env = Environment(
            undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True
        )

    def carregar(self, nome: str) -> Prompt:
        texto = (self._pasta / f"{nome}.md").read_text(encoding="utf-8")
        encontrada = _VERSAO.search(texto)
        versao = encontrada.group(1) if encontrada else "0"
        corpo = _VERSAO.sub("", texto).strip()
        return Prompt(nome=nome, versao=versao, template=corpo)

    def renderizar(self, nome: str, **variaveis) -> tuple[str, str]:
        prompt = self.carregar(nome)
        return self._env.from_string(prompt.template).render(**variaveis), prompt.versao


class StructuredLlm:
    def __init__(
        self,
        cliente: JsonCompletion,
        prompts: PromptLoader,
        pasta_cache: Path | None,
        medidor: RegistroConsumo | None = None,
    ) -> None:
        self._cliente = cliente
        self._prompts = prompts
        self._cache = pasta_cache
        self._medidor = medidor
        if self._cache is not None:
            self._cache.mkdir(parents=True, exist_ok=True)

    @property
    def modelo(self) -> str:
        return self._cliente.modelo

    def _chave(self, versao: str, entrada: str) -> str:
        bruto = f"{versao}\n{self._cliente.modelo}\n{entrada}".encode()
        return hashlib.sha256(bruto).hexdigest()

    def gerar(self, nome_prompt: str, schema: type[T], /, **variaveis) -> T:
        """Renderiza o prompt com ``variaveis`` e devolve a saída validada em ``schema``.

        ``nome_prompt`` e ``schema`` são só posicionais: nenhuma variável do
        template pode colidir com eles.
        """
        sistema, versao_sistema = self._prompts.renderizar("sistema")
        prompt, versao = self._prompts.renderizar(nome_prompt, **variaveis)
        versao_total = f"{nome_prompt}@{versao}+sistema@{versao_sistema}"
        arquivo = self._cache / f"{self._chave(versao_total, prompt)}.json" if self._cache else None
        if arquivo is not None and arquivo.exists():
            logger.info(json.dumps({"etapa": f"llm.{nome_prompt}", "cache": True}))
            if self._medidor:
                self._medidor.registrar(nome_prompt, 0, 0, 0.0, cache=True)
            return schema.model_validate_json(arquivo.read_text(encoding="utf-8"))

        resultado = self._gerar_com_reparo(nome_prompt, sistema, prompt, schema)
        if arquivo is not None:
            arquivo.write_text(resultado.model_dump_json(), encoding="utf-8")
        return resultado

    def _gerar_com_reparo(self, nome: str, sistema: str, prompt: str, schema: type[T]) -> T:
        mensagem = prompt
        ultimo_erro = ""
        for tentativa in range(MAX_REPAROS + 1):
            inicio = time.perf_counter()
            try:
                texto, uso = self._cliente.complete(sistema=sistema, prompt=mensagem, schema=schema)
            except Exception as erro:  # SDKs lançam tipos variados
                raise LlmIndisponivelError(f"Falha ao chamar o LLM: {erro}") from erro
            duracao = time.perf_counter() - inicio
            if self._medidor:
                self._medidor.registrar(nome, uso.tokens_entrada, uso.tokens_saida, duracao)
            logger.info(
                json.dumps(
                    {
                        "etapa": f"llm.{nome}",
                        "tentativa": tentativa,
                        "duracao_s": round(duracao, 2),
                        "tokens_entrada": uso.tokens_entrada,
                        "tokens_saida": uso.tokens_saida,
                        "modelo": self._cliente.modelo,
                    }
                )
            )
            try:
                return schema.model_validate_json(_extrair_json(texto))
            except ValidationError as erro:
                ultimo_erro = str(erro)[:2000]
                mensagem = (
                    f"{prompt}\n\n## Correção necessária\nSua resposta anterior não validou no "
                    f"schema. Erros:\n{ultimo_erro}\nResponda de novo, só com o JSON válido."
                )
        raise LlmIndisponivelError(
            f"Resposta fora do schema após {MAX_REPAROS} reparos: {ultimo_erro}"
        )


def _extrair_json(texto: str) -> str:
    texto = texto.strip()
    if texto.startswith("```"):
        texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    return texto
