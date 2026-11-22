"""Logs estruturados por etapa, com duração (RNF-07)."""

import json
import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

logger = logging.getLogger("editalcheck")


@contextmanager
def etapa(nome: str, **campos) -> Iterator[dict]:
    """Registra início, fim e duração de uma etapa. ``extra`` aceita mais campos."""
    extra: dict = {}
    inicio = time.perf_counter()
    try:
        yield extra
    except Exception as erro:
        registro = {"etapa": nome, "status": "falhou", "erro": str(erro), **campos, **extra}
        registro["duracao_s"] = round(time.perf_counter() - inicio, 3)
        logger.warning(json.dumps(registro, ensure_ascii=False, default=str))
        raise
    registro = {"etapa": nome, "status": "ok", **campos, **extra}
    registro["duracao_s"] = round(time.perf_counter() - inicio, 3)
    logger.info(json.dumps(registro, ensure_ascii=False, default=str))


def agora() -> str:
    return datetime.now().replace(microsecond=0).isoformat()
