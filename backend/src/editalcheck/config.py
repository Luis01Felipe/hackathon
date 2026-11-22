"""Configuração por variáveis de ambiente (.env fora do Git — RNF-06)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ_BACKEND = Path(__file__).resolve().parents[2]
RAIZ_REPO = RAIZ_BACKEND.parent


def _bool(valor: str | None, padrao: bool) -> bool:
    if valor is None or valor.strip() == "":
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes", "on")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None
    gemini_model: str
    llm_ativo: bool
    llm_timeout_s: float
    bsdd_ativo: bool
    bsdd_timeout_s: float
    pasta_dados: Path
    pasta_cache: Path
    pasta_demo: Path
    pasta_prompts: Path
    pasta_recursos: Path
    pasta_frontend: Path
    limite_upload_mb: int
    nivel_log: str

    @property
    def modo_ia(self) -> str:
        return "gemini" if self.llm_ativo else "offline"


def carregar(sobrescrever: dict[str, str] | None = None) -> Settings:
    load_dotenv(RAIZ_REPO / ".env")
    load_dotenv(RAIZ_BACKEND / ".env")
    env = {**os.environ, **(sobrescrever or {})}
    chave = (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip() or None
    dados = Path(env.get("EDITALCHECK_DATA_DIR") or RAIZ_REPO / "var")
    return Settings(
        gemini_api_key=chave,
        gemini_model=env.get("GEMINI_MODEL", "gemini-4-hydrogen"),
        llm_ativo=chave is not None and _bool(env.get("LLM_ATIVO"), True),
        llm_timeout_s=float(env.get("LLM_TIMEOUT_S", "90")),
        bsdd_ativo=_bool(env.get("BSDD_ATIVO"), True),
        bsdd_timeout_s=float(env.get("BSDD_TIMEOUT_S", "5")),
        pasta_dados=dados,
        pasta_cache=Path(env.get("EDITALCHECK_CACHE_DIR") or RAIZ_REPO / ".cache"),
        pasta_demo=Path(env.get("EDITALCHECK_DEMO_DIR") or RAIZ_REPO / "data" / "demo"),
        pasta_prompts=RAIZ_BACKEND / "prompts",
        pasta_recursos=RAIZ_BACKEND / "resources",
        pasta_frontend=Path(env.get("EDITALCHECK_FRONTEND_DIR") or RAIZ_REPO / "frontend" / "dist"),
        limite_upload_mb=int(env.get("LIMITE_UPLOAD_MB", "200")),
        nivel_log=env.get("LOG_LEVEL", "INFO"),
    )
