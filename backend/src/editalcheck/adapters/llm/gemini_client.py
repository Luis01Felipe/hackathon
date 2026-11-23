"""Adaptador do Google Gemini (SDK google-genai) com saída JSON estruturada."""

from google import genai
from google.genai import types
from pydantic import BaseModel

from editalcheck.adapters.llm.structured import Uso


class GeminiJsonClient:
    def __init__(self, api_key: str, modelo: str, timeout_s: float = 90.0) -> None:
        self.modelo = modelo
        self._cliente = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(timeout_s * 1000),
                # Falhas temporárias (limite de taxa, servidor ocupado) ganham mais 2 tentativas
                # antes de a análise cair nas regras determinísticas.
                retry_options=types.HttpRetryOptions(attempts=3),
            ),
        )

    def complete(self, *, sistema: str, prompt: str, schema: type[BaseModel]) -> tuple[str, Uso]:
        resposta = self._cliente.models.generate_content(
            model=self.modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=sistema,
                temperature=0.0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        metadados = resposta.usage_metadata
        uso = Uso(
            tokens_entrada=(metadados.prompt_token_count or 0) if metadados else 0,
            tokens_saida=(metadados.candidates_token_count or 0) if metadados else 0,
        )
        texto = resposta.text
        if not texto:
            raise RuntimeError("O Gemini devolveu uma resposta vazia.")
        return texto, uso
