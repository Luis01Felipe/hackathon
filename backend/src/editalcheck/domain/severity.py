"""Matriz de severidade determinística (seção 9.5 da especificação)."""

from dataclasses import dataclass, field

from editalcheck.domain.models import Cardinalidade, Destinatario, Severidade, TipoApontamento

CLASSES_SEGURANCA_PADRAO = frozenset(
    {
        "ifcdoor",
        "ifcstair",
        "ifcstairflight",
        "ifcramp",
        "ifcrampflight",
        "ifcrailing",
        "ifcfiresuppressionterminal",
        "ifcalarm",
        "ifcsensor",
    }
)


@dataclass(frozen=True)
class ConfigSeveridade:
    classes_seguranca: frozenset[str] = field(default=CLASSES_SEGURANCA_PADRAO)
    limite_contagem_lacuna: int = 10
    limite_proxies: float = 0.20


def nao_conformidade(cardinalidade: Cardinalidade) -> Severidade:
    if cardinalidade == Cardinalidade.OBRIGATORIA:
        return Severidade.ALTA
    return Severidade.MEDIA


def lacuna_cobertura(classe: str, contagem: int, config: ConfigSeveridade) -> Severidade:
    if contagem >= config.limite_contagem_lacuna:
        return Severidade.ALTA
    if classe.lower() in config.classes_seguranca:
        return Severidade.ALTA
    return Severidade.MEDIA


def item_ausente(critico: bool) -> Severidade:
    return Severidade.ALTA if critico else Severidade.MEDIA


def ambiguidade(em_clausula_com_requisito: bool) -> Severidade:
    return Severidade.MEDIA if em_clausula_com_requisito else Severidade.BAIXA


def nao_verificavel() -> Severidade:
    return Severidade.BAIXA


def contradicao() -> Severidade:
    # Fora da matriz da seção 9.5: o time adotou "média" (registrado no JOURNAL).
    return Severidade.MEDIA


def qualidade_modelo(
    proporcao_proxies: float, guid_duplicado: bool, config: ConfigSeveridade
) -> Severidade:
    if guid_duplicado or proporcao_proxies > config.limite_proxies:
        return Severidade.ALTA
    return Severidade.MEDIA


def destinatario(tipo: TipoApontamento) -> Destinatario:
    if tipo in (TipoApontamento.NAO_CONFORMIDADE, TipoApontamento.QUALIDADE_MODELO):
        return Destinatario.PROJETISTA
    return Destinatario.CONTRATANTE


ORDEM_SEVERIDADE = {Severidade.ALTA: 0, Severidade.MEDIA: 1, Severidade.BAIXA: 2}
