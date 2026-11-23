"""Consulta ao bSDD (buildingSMART Data Dictionary) pela API REST pública.

Usa ``GET /api/TextSearch/v1``. Falhas de rede não derrubam o fluxo
(RNF-02): o cliente devolve lista vazia e registra o erro. As respostas ficam
em cache em disco para a demo não depender da rede.
"""

import hashlib
import json
import logging
from pathlib import Path

import httpx

from editalcheck.domain.models import TermoDicionario

logger = logging.getLogger("editalcheck.bsdd")
URL_BASE = "https://api.bsdd.buildingsmart.org"
DICIONARIO_IFC = "https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3"


class BsddHttpClient:
    def __init__(self, pasta_cache: Path, timeout_s: float = 5.0, limite: int = 5) -> None:
        self._cache = pasta_cache
        self._cache.mkdir(parents=True, exist_ok=True)
        self._timeout = timeout_s
        self._limite = limite
        # Última consulta falhou? Vale por consulta: uma queda passageira não fica "grudada".
        self.falhou = False

    def _consultar(self, params: dict[str, str | int]) -> dict:
        chave = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
        arquivo = self._cache / f"{chave}.json"
        if arquivo.exists():
            try:
                return json.loads(arquivo.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                logger.warning("Cache do bSDD corrompido; consultando de novo: %s", arquivo.name)
        resposta = httpx.get(f"{URL_BASE}/api/TextSearch/v1", params=params, timeout=self._timeout)
        resposta.raise_for_status()
        dados = resposta.json()
        # Grava num temporário e renomeia: uma gravação interrompida não deixa JSON pela metade.
        temporario = arquivo.with_suffix(".tmp")
        temporario.write_text(json.dumps(dados), encoding="utf-8")
        temporario.replace(arquivo)
        return dados

    def search(self, termo: str, ifc_class: str | None = None) -> list[TermoDicionario]:
        params: dict[str, str | int] = {
            "SearchText": termo,
            "TypeFilter": "Properties",
            "Limit": self._limite,
            "DictionaryUris": DICIONARIO_IFC,
        }
        try:
            dados = self._consultar(params)
            self.falhou = False
        except (httpx.HTTPError, ValueError, OSError) as erro:
            self.falhou = True
            logger.warning(json.dumps({"etapa": "bsdd.search", "erro": str(erro)}))
            return []
        termos: list[TermoDicionario] = []
        for item in dados.get("properties", []) or []:
            uri = item.get("uri", "")
            codigo = uri.rstrip("/").rsplit("/", 1)[-1] if uri else item.get("name", "")
            termos.append(
                TermoDicionario(
                    nome=codigo,
                    uri=uri,
                    tipo="propriedade",
                    dicionario=item.get("dictionaryName", ""),
                    descricao=item.get("name", ""),
                )
            )
        return termos
