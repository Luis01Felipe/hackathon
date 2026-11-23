"""Métricas da seção 14.3 contra o gabarito anotado manualmente (data/demo/gabarito.json)."""

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from editalcheck.domain.evidence import normalizar
from editalcheck.domain.models import Relatorio, Requisito, TipoApontamento


@dataclass(frozen=True)
class Metricas:
    requisitos_gabarito: int
    requisitos_extraidos: int
    requisitos_encontrados: int
    requisitos_corretos: int
    citacoes_geradas: int
    citacoes_conferidas: int
    ids_valido: bool | None
    checklist_acertos: int
    checklist_total: int
    ambiguidades_apontadas: int
    ambiguidades_corretas: int
    trechos_vagos_gabarito: int
    trechos_vagos_encontrados: int
    tempo_pipeline_s: float | None = None
    nao_encontrados: tuple[str, ...] = ()
    extras: tuple[str, ...] = ()
    checklist_divergencias: tuple[str, ...] = field(default_factory=tuple)

    @staticmethod
    def _razao(a: int, b: int) -> float | None:
        return round(100 * a / b, 1) if b else None

    @property
    def recall(self) -> float | None:
        return self._razao(self.requisitos_encontrados, self.requisitos_gabarito)

    @property
    def precisao(self) -> float | None:
        return self._razao(self.requisitos_corretos, self.requisitos_extraidos)

    @property
    def citacoes_percentual(self) -> float | None:
        return self._razao(self.citacoes_conferidas, self.citacoes_geradas)

    @property
    def checklist_percentual(self) -> float | None:
        return self._razao(self.checklist_acertos, self.checklist_total)

    @property
    def ambiguidade_precisao(self) -> float | None:
        return self._razao(self.ambiguidades_corretas, self.ambiguidades_apontadas)

    @property
    def ambiguidade_recall(self) -> float | None:
        return self._razao(self.trechos_vagos_encontrados, self.trechos_vagos_gabarito)


def carregar_gabarito(caminho: Path) -> dict:
    return json.loads(caminho.read_text(encoding="utf-8"))


def _casa(item: dict, requisito: Requisito) -> bool:
    if item.get("verificavel"):
        return (
            requisito.verificavel_por_ids
            and (requisito.ifc_class or "").lower() == item["ifc_class"].lower()
            and (requisito.propriedade or "").lower() == item["propriedade"].lower()
        )
    return normalizar(item["chave"]) in normalizar(requisito.evidencia.trecho)


def avaliar(
    gabarito: dict,
    requisitos: Sequence[Requisito],
    descartados: int,
    relatorio: Relatorio | None,
    ids_valido: bool | None,
    tempo_pipeline_s: float | None = None,
) -> Metricas:
    # O gabarito cobre só o edital: lacunas e lições aprendidas ficam fora da métrica.
    extraidos = [r for r in requisitos if not r.sugerido_por_lacuna and r.gerado_por != "licao"]
    itens = gabarito["requisitos"]
    encontrados = [i for i in itens if any(_casa(i, r) for r in extraidos)]
    corretos = [r for r in extraidos if any(_casa(i, r) for i in itens)]

    checklist_esperado: dict[str, str] = gabarito.get("checklist", {})
    obtido = {c.item_id: c.status.value for c in relatorio.checklist} if relatorio else {}
    divergencias = tuple(
        f"{item}: esperado {esperado}, obtido {obtido.get(item, '—')}"
        for item, esperado in checklist_esperado.items()
        if obtido.get(item) != esperado
    )

    vagos = gabarito.get("trechos_vagos", [])
    ambiguidades = (
        [a for a in relatorio.apontamentos if a.tipo == TipoApontamento.AMBIGUIDADE]
        if relatorio
        else []
    )

    def trecho_vago(apontamento) -> bool:
        textos = [normalizar(e.trecho) for e in apontamento.evidencias_edital]
        return any(normalizar(v["chave"]) in t for v in vagos for t in textos)

    vagos_encontrados = [
        v
        for v in vagos
        if any(
            normalizar(v["chave"]) in normalizar(e.trecho)
            for a in ambiguidades
            for e in a.evidencias_edital
        )
    ]
    return Metricas(
        requisitos_gabarito=len(itens),
        requisitos_extraidos=len(extraidos),
        requisitos_encontrados=len(encontrados),
        requisitos_corretos=len(corretos),
        citacoes_geradas=len(extraidos) + descartados,
        citacoes_conferidas=len(extraidos),
        ids_valido=ids_valido,
        checklist_acertos=len(checklist_esperado) - len(divergencias),
        checklist_total=len(checklist_esperado),
        ambiguidades_apontadas=len(ambiguidades),
        ambiguidades_corretas=sum(1 for a in ambiguidades if trecho_vago(a)),
        trechos_vagos_gabarito=len(vagos),
        trechos_vagos_encontrados=len(vagos_encontrados),
        tempo_pipeline_s=tempo_pipeline_s,
        nao_encontrados=tuple(
            i["id"] + " " + i.get("clausula", "") for i in itens if i not in encontrados
        ),
        extras=tuple(f"{r.id} ({r.evidencia.trecho[:60]})" for r in extraidos if r not in corretos),
        checklist_divergencias=divergencias,
    )
