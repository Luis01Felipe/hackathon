"""Configuração por variáveis de ambiente (.env fora do Git — RNF-06)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

RAIZ_BACKEND = Path(__file__).resolve().parents[2]
RAIZ_REPO = RAIZ_BACKEND.parent


MODOS_DADOS = ("efemero", "persistente")


def _float(valor: str | None) -> float | None:
    if valor is None or not valor.strip():
        return None
    return float(valor.replace(",", "."))


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
    llm_paralelismo: int
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
    caminho_raiz: str = ""  # prefixo do proxy (ex.: "/editalcheck"); vazio em desenvolvimento
    modo_dados: str = "efemero"  # efemero (só RAM, padrão) | persistente (disco, desenvolvimento)
    ttl_min: int = 120  # minutos sem acesso até um projeto ser apagado no modo efêmero
    disponivel_ate: str | None = None  # data de desligamento do ambiente de demonstração
    pasta_contexto: Path | None = None  # documentos de referência autorizados
    arquivo_auditoria: Path | None = None  # log de auditoria sem conteúdo
    preco_entrada_usd_mtok: float | None = None
    preco_saida_usd_mtok: float | None = None
    fonte_preco: str = ""

    @property
    def modo_ia(self) -> str:
        return "gemini" if self.llm_ativo else "offline"


def carregar(sobrescrever: dict[str, str] | None = None) -> Settings:
    load_dotenv(RAIZ_REPO / ".env")
    load_dotenv(RAIZ_BACKEND / ".env")
    env = {**os.environ, **(sobrescrever or {})}
    chave = (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY") or "").strip() or None
    dados = Path(env.get("EDITALCHECK_DATA_DIR") or RAIZ_REPO / "var")
    modo_dados = (env.get("EDITALCHECK_MODO_DADOS") or "efemero").strip().lower()
    if modo_dados not in MODOS_DADOS:
        raise ValueError(f"EDITALCHECK_MODO_DADOS inválido: {modo_dados!r} (use {MODOS_DADOS}).")
    auditoria = (env.get("EDITALCHECK_AUDITORIA") or "").strip()
    return Settings(
        gemini_api_key=chave,
        gemini_model=env.get("GEMINI_MODEL", "gemini-4-hydrogen"),
        llm_ativo=chave is not None and _bool(env.get("LLM_ATIVO"), True),
        llm_timeout_s=float(env.get("LLM_TIMEOUT_S", "90")),
        llm_paralelismo=int(env.get("LLM_PARALELISMO", "6")),
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
        caminho_raiz=env.get("EDITALCHECK_ROOT_PATH", "").strip().rstrip("/"),
        modo_dados=modo_dados,
        ttl_min=int(env.get("EDITALCHECK_TTL_MIN", "120")),
        disponivel_ate=(env.get("EDITALCHECK_DISPONIVEL_ATE") or "").strip() or None,
        pasta_contexto=Path(
            env.get("EDITALCHECK_CONTEXTO_DIR") or RAIZ_BACKEND / "resources" / "contexto"
        ),
        arquivo_auditoria=(
            None
            if auditoria.lower() in ("0", "false", "nao", "off")
            else Path(auditoria or dados / "auditoria" / "auditoria.jsonl")
        ),
        preco_entrada_usd_mtok=_float(env.get("LLM_PRECO_ENTRADA_USD_MTOK")),
        preco_saida_usd_mtok=_float(env.get("LLM_PRECO_SAIDA_USD_MTOK")),
        fonte_preco=(env.get("LLM_PRECO_FONTE") or "").strip(),
    )
