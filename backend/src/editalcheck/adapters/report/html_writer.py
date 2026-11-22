"""Relatório HTML em português com Jinja2 (RF-53)."""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from editalcheck.domain.findings import texto_restricao
from editalcheck.domain.models import Relatorio, Severidade

ROTULOS_TIPO = {
    "nao_conformidade": "Não conformidade",
    "ambiguidade": "Ambiguidade",
    "nao_verificavel": "Não verificável",
    "item_ausente": "Item ausente",
    "contradicao": "Contradição",
    "lacuna_cobertura": "Lacuna de cobertura",
    "qualidade_modelo": "Qualidade do modelo",
}
ROTULOS_SEVERIDADE = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
ROTULOS_DESTINATARIO = {"projetista": "Projetista", "contratante": "Contratante"}


def _data(valor: str) -> str:
    try:
        return datetime.fromisoformat(valor).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return valor


def _percentual(valor: float | None) -> str:
    if valor is None:
        return "—"
    return f"{valor:.1f}%".replace(".", ",")


class JinjaHtmlReportWriter:
    def __init__(self) -> None:
        self._env = Environment(
            loader=FileSystemLoader(Path(__file__).parent / "templates"),
            autoescape=select_autoescape(["html", "j2"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self._env.filters["data"] = _data
        self._env.filters["percentual"] = _percentual
        self._env.filters["restricao"] = lambda r: texto_restricao(r).strip()
        self._env.globals.update(
            ROTULOS_TIPO=ROTULOS_TIPO,
            ROTULOS_SEVERIDADE=ROTULOS_SEVERIDADE,
            ROTULOS_DESTINATARIO=ROTULOS_DESTINATARIO,
        )

    def write_html(self, relatorio: Relatorio) -> str:
        nomes: dict[str, str] = {}
        for resultado in relatorio.resultados_ids:
            for falha in resultado.falhas:
                nomes[falha.global_id] = f"{falha.classe} · {falha.nome or 'sem nome'}"
        grupos = {
            destinatario: [
                a for a in relatorio.apontamentos if a.destinatario.value == destinatario
            ]
            for destinatario in ("projetista", "contratante")
        }
        itens = {i.id: i for i in relatorio.itens_checklist}
        return self._env.get_template("relatorio.html.j2").render(
            r=relatorio,
            grupos=grupos,
            nomes=nomes,
            itens=itens,
            Severidade=Severidade,
        )
