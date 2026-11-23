from pathlib import Path

import pytest

from editalcheck.bootstrap import Container, construir
from editalcheck.config import RAIZ_REPO, carregar

PASTA_DEMO = RAIZ_REPO / "data" / "demo"


def configuracao_de_teste(tmp_path: Path, **extras: str) -> dict[str, str]:
    """Modo offline, sem rede (bSDD desligado), dados temporários e sem o .env local."""
    return {
        "GEMINI_API_KEY": "",
        "GOOGLE_API_KEY": "",
        "LLM_ATIVO": "false",
        "BSDD_ATIVO": "false",
        "EDITALCHECK_MODO_DADOS": "efemero",
        "EDITALCHECK_DOCS": "true",
        "LIMITE_UPLOAD_MB": "200",
        "EDITALCHECK_DATA_DIR": str(tmp_path / "dados"),
        "EDITALCHECK_CACHE_DIR": str(tmp_path / "cache"),
        "EDITALCHECK_DEMO_DIR": str(PASTA_DEMO),
        "EDITALCHECK_FRONTEND_DIR": str(tmp_path / "sem-frontend"),
        **extras,
    }


@pytest.fixture()
def container(tmp_path: Path) -> Container:
    return construir(carregar(configuracao_de_teste(tmp_path), ler_dotenv=False))


@pytest.fixture()
def arquivos_demo() -> tuple[bytes, bytes]:
    return (PASTA_DEMO / "edital.pdf").read_bytes(), (PASTA_DEMO / "modelo.ifc").read_bytes()
