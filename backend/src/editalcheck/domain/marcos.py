"""Marcos de entrega citados no edital (fases da Lei 14.133/2021 e afins).

A detecção é determinística: procura o nome de cada fase no texto e guarda a
primeira frase que a cita como evidência. O usuário revisa a lista.
"""

import re

from editalcheck.domain.evidence import normalizar, remover_acentos
from editalcheck.domain.models import Edital, Evidencia, MarcoEntrega
from editalcheck.domain.vagueness import dividir_sentencas

# (nome exibido, padrão sem acento), na ordem usual do ciclo de projeto.
FASES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Estudo preliminar", re.compile(r"\bestudos? preliminar(es)?\b")),
    ("Anteprojeto", re.compile(r"\banteprojetos?\b")),
    ("Projeto legal", re.compile(r"\bprojetos? lega(l|is)\b")),
    ("Projeto básico", re.compile(r"\bprojetos? basicos?\b")),
    ("Projeto executivo", re.compile(r"\bprojetos? executivos?\b")),
    ("Como construído (as built)", re.compile(r"\bas[- ]?built\b|\bcomo construido\b")),
)


def detectar(edital: Edital) -> list[MarcoEntrega]:
    encontrados: dict[str, Evidencia] = {}
    for pagina in edital.paginas:
        for sentenca in dividir_sentencas(pagina.texto):
            chave = remover_acentos(normalizar(sentenca))
            for nome, padrao in FASES:
                if nome not in encontrados and padrao.search(chave):
                    encontrados[nome] = Evidencia(pagina=pagina.numero, trecho=sentenca)
    return [
        MarcoEntrega(id=f"MAR-{i:02d}", nome=nome, evidencia=encontrados[nome])
        for i, nome in enumerate((n for n, _ in FASES if n in encontrados), start=1)
    ]


def novo_id(marcos: list[MarcoEntrega] | tuple[MarcoEntrega, ...]) -> str:
    numeros = [int(m.id.split("-")[1]) for m in marcos if m.id.startswith("MAR-")]
    return f"MAR-{max(numeros, default=0) + 1:02d}"
