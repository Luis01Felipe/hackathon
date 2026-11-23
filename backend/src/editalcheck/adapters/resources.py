"""Carga dos recursos YAML (léxico, checklist e vocabulário em português)."""

from dataclasses import dataclass
from pathlib import Path

import yaml

from editalcheck.domain.checklist import RegraChecklist
from editalcheck.domain.models import ItemChecklist, ReferenciaTempoManual, TermoVago


@dataclass(frozen=True)
class VocabularioPt:
    classes: dict[str, tuple[str, ...]]  # IfcDoor → ("porta", "portas")
    classes_en: dict[str, str]  # IfcDoor → "door"
    propriedades: dict[str, tuple[str, ...]]  # FireRating → ("resistência ao fogo", ...)
    atributos: tuple[str, ...]
    sistemas_classificacao: tuple[str, ...]
    obrigacao: tuple[str, ...]
    nao_modelo: tuple[str, ...]


def _ler(caminho: Path) -> dict:
    return yaml.safe_load(caminho.read_text(encoding="utf-8")) or {}


def carregar_termos_vagos(caminho: Path) -> list[TermoVago]:
    dados = _ler(caminho)
    return [
        TermoVago(
            termo=t["termo"], categoria=t.get("categoria", ""), sugestao=t.get("sugestao", "")
        )
        for t in dados.get("termos", [])
    ]


def carregar_checklist(caminho: Path) -> tuple[list[ItemChecklist], list[RegraChecklist]]:
    dados = _ler(caminho)
    itens: list[ItemChecklist] = []
    regras: list[RegraChecklist] = []
    for item in dados.get("itens", []):
        palavras = tuple(item.get("palavras_chave", []))
        itens.append(
            ItemChecklist(
                id=item["id"],
                item=item["item"],
                critico=bool(item.get("critico", False)),
                descricao=item.get("descricao", ""),
                palavras_chave=palavras,
            )
        )
        regras.append(
            RegraChecklist(
                item_id=item["id"],
                padroes_presente=tuple(item.get("padroes_presente", [])),
                palavras_chave=palavras,
            )
        )
    return itens, regras


def carregar_vocabulario(caminho: Path) -> VocabularioPt:
    dados = _ler(caminho)
    classes = dados.get("classes", {})
    return VocabularioPt(
        classes={nome: tuple(v.get("pt", [])) for nome, v in classes.items()},
        classes_en={nome: v.get("en", "") for nome, v in classes.items()},
        propriedades={nome: tuple(v) for nome, v in dados.get("propriedades", {}).items()},
        atributos=tuple(dados.get("atributos", [])),
        sistemas_classificacao=tuple(dados.get("sistemas_classificacao", [])),
        obrigacao=tuple(dados.get("obrigacao", [])),
        nao_modelo=tuple(str(v) for v in dados.get("nao_modelo", [])),
    )


def carregar_tempo_manual(caminho: Path) -> ReferenciaTempoManual:
    """Tempo manual medido pelo time. Sem medição registrada, o painel mostra "não medido"."""
    if not caminho.exists():
        return ReferenciaTempoManual(medido=False)
    dados = _ler(caminho)
    horas = dados.get("horas")
    if horas in (None, ""):
        return ReferenciaTempoManual(medido=False, tarefa=str(dados.get("tarefa") or ""))
    return ReferenciaTempoManual(
        medido=True,
        horas=float(horas),
        tarefa=str(dados.get("tarefa") or ""),
        amostra=str(dados.get("amostra") or ""),
        metodo=str(dados.get("metodo") or ""),
        data=str(dados.get("data") or ""),
    )
