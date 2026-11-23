"""Log de auditoria SEM conteúdo de documento (RF-096, RNF-12).

Registra quando cada etapa rodou, em qual projeto (ID aleatório), com quantos
tokens e quanto tempo. Nunca registra texto do edital, das lições ou do modelo.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

CAMPOS_PROIBIDOS = frozenset({"texto", "trecho", "conteudo", "edital", "regra", "prompt"})


class JsonLinesAuditLog:
    def __init__(self, arquivo: Path) -> None:
        self._arquivo = arquivo
        self._trava = threading.Lock()
        self._arquivo.parent.mkdir(parents=True, exist_ok=True)

    def record(self, evento: str, **campos: object) -> None:
        seguros = {k: v for k, v in campos.items() if k not in CAMPOS_PROIBIDOS}
        registro = {"data": datetime.now().replace(microsecond=0).isoformat(), "evento": evento}
        registro.update(seguros)
        linha = json.dumps(registro, ensure_ascii=False, default=str)
        with self._trava, self._arquivo.open("a", encoding="utf-8") as saida:
            saida.write(linha + "\n")


class AuditLogNulo:
    def record(self, evento: str, **campos: object) -> None:
        return None
