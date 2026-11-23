"""Indicadores do painel (seção 13.3) e estado de cada elemento no 3D."""

from collections import Counter
from collections.abc import Sequence

from editalcheck.domain.models import (
    Apontamento,
    Cobertura,
    ConsumoEtapa,
    Custo,
    EstadoElemento,
    Indicadores,
    Requisito,
    ResultadoChecklist,
    ResultadoEspecificacao,
    StatusChecklist,
    VerificacaoLicao,
)


def estado_elementos(resultados: Sequence[ResultadoEspecificacao]) -> dict[str, EstadoElemento]:
    estados: dict[str, EstadoElemento] = {}
    for resultado in resultados:
        for global_id in resultado.elementos_aprovados:
            estados.setdefault(global_id, EstadoElemento.CONFORME)
    for resultado in resultados:
        for falha in resultado.falhas:
            estados[falha.global_id] = EstadoElemento.NAO_CONFORME
    return estados


def calcular(
    resultados: Sequence[ResultadoEspecificacao],
    cobertura: Cobertura | None,
    checklist: Sequence[ResultadoChecklist],
    requisitos: Sequence[Requisito],
    apontamentos: Sequence[Apontamento],
    verificacoes_licoes: Sequence[VerificacaoLicao] = (),
) -> Indicadores:
    """Indicadores do painel. A verificação manual tem contagem própria (RF-161)."""
    principais = [a for a in apontamentos if not a.verificacao_manual]
    aplicaveis = [r for r in resultados if r.aplicaveis > 0]
    aprovadas = sum(1 for r in aplicaveis if r.status)
    conformidade = round(100 * aprovadas / len(aplicaveis), 1) if aplicaveis else None
    estados = estado_elementos(resultados)
    nao_conformes = sum(1 for e in estados.values() if e == EstadoElemento.NAO_CONFORME)
    return Indicadores(
        conformidade_percentual=conformidade,
        especificacoes_total=len(aplicaveis),
        especificacoes_aprovadas=aprovadas,
        elementos_verificados=len(estados),
        elementos_nao_conformes=nao_conformes,
        cobertura_percentual=cobertura.percentual if cobertura else None,
        classes_especificaveis=len(cobertura.classes) if cobertura else 0,
        classes_cobertas=cobertura.classes_cobertas if cobertura else 0,
        checklist_presentes=sum(1 for c in checklist if c.status == StatusChecklist.PRESENTE),
        checklist_parciais=sum(1 for c in checklist if c.status == StatusChecklist.PARCIAL),
        checklist_total=len(checklist),
        requisitos_aprovados=sum(1 for r in requisitos if r.aprovado),
        requisitos_nao_verificaveis=sum(
            1 for r in requisitos if r.aprovado and not r.verificavel_por_ids
        ),
        apontamentos_por_severidade=dict(Counter(a.severidade.value for a in principais)),
        apontamentos_por_destinatario=dict(Counter(a.destinatario.value for a in principais)),
        apontamentos_por_tipo=dict(Counter(a.tipo.value for a in apontamentos)),
        apontamentos_por_origem=dict(Counter(a.origem.value for a in principais)),
        verificacao_manual=len(apontamentos) - len(principais),
        licoes_total=len(verificacoes_licoes),
        licoes_nao_explicitas=sum(1 for v in verificacoes_licoes if not v.explicita),
    )


def somar_consumo(consumo: Sequence[ConsumoEtapa]) -> tuple[int, int]:
    return sum(c.tokens_entrada for c in consumo), sum(c.tokens_saida for c in consumo)


def calcular_custo(
    consumo: Sequence[ConsumoEtapa],
    preco_entrada_usd_mtok: float | None,
    preco_saida_usd_mtok: float | None,
    fonte_preco: str = "",
) -> Custo:
    """Custo estimado em dólares a partir dos tokens medidos e dos preços configurados."""
    entrada, saida = somar_consumo(consumo)
    if preco_entrada_usd_mtok is None or preco_saida_usd_mtok is None:
        return Custo(
            entrada, saida, None, preco_entrada_usd_mtok, preco_saida_usd_mtok, fonte_preco
        )
    usd = (entrada * preco_entrada_usd_mtok + saida * preco_saida_usd_mtok) / 1_000_000
    return Custo(
        entrada, saida, round(usd, 6), preco_entrada_usd_mtok, preco_saida_usd_mtok, fonte_preco
    )
