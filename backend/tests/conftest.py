from pathlib import Path

import pytest

from editalcheck.bootstrap import Container, construir
from editalcheck.config import RAIZ_REPO, carregar

PASTA_DEMO = RAIZ_REPO / "data" / "demo"


@pytest.fixture()
def container(tmp_path: Path) -> Container:
    """Container no modo offline, sem rede (bSDD desligado) e com dados temporários."""
    settings = carregar(
        {
            "GEMINI_API_KEY": "",
            "GOOGLE_API_KEY": "",
            "BSDD_ATIVO": "false",
            "EDITALCHECK_DATA_DIR": str(tmp_path / "dados"),
            "EDITALCHECK_CACHE_DIR": str(tmp_path / "cache"),
            "EDITALCHECK_DEMO_DIR": str(PASTA_DEMO),
            "EDITALCHECK_FRONTEND_DIR": str(tmp_path / "sem-frontend"),
        }
    )
    return construir(settings)


@pytest.fixture()
def arquivos_demo() -> tuple[bytes, bytes]:
    return (PASTA_DEMO / "edital.pdf").read_bytes(), (PASTA_DEMO / "modelo.ifc").read_bytes()
