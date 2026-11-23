"""Relatório HTML em português com Jinja2 (RF-53)."""

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from editalcheck.adapters.bcf.bcf_writer import texto_coordenada
from editalcheck.domain.findings import texto_restricao
from editalcheck.domain.models import OrigemInconsistencia, Relatorio, Severidade, StatusDecisao

ROTULOS_TIPO = {
    "nao_conformidade": "Não conformidade",
    "ambiguidade": "Ambiguidade",
    "nao_verificavel": "Não verificável",
    "item_ausente": "Item ausente",
    "contradicao": "Contradição",
    "lacuna_cobertura": "Lacuna de cobertura",
    "qualidade_modelo": "Qualidade do modelo",
    "licao_nao_explicita": "Lição aprendida",
    "duplicidade": "Texto repetido",
}
ROTULOS_SEVERIDADE = {"alta": "Alta", "media": "Média", "baixa": "Baixa"}
ROTULOS_DESTINATARIO = {
    "projetista": "Contratado / projetista",
    "contratante": "Contratante",
}
ROTULOS_DECISAO = {
    "pendente": "Pendente",
    "aceito": "Aceito",
    "rejeitado": "Rejeitado",
    "em_discussao": "Em discussão",
    "dispensado": "Dispensado",
}
POSICIONAMENTO = (
    "O EditalCheck transforma as exigências de um edital, escritas em linguagem natural, num "
    "contrato de dados operacional: os requisitos de informação (IR) e o IDS. Depois, verifica o "
    "modelo IFC contra esse contrato e o edital contra boas práticas. O objetivo é chegar a um "
    "consenso entre contratante e contratado antes que o problema chegue à obra."
)
# Normas citadas: versões conferidas em 22/11/2026 em catálogos públicos (ISO e distribuidores).
# Confirme a vigência no catálogo oficial antes de citar em contrato.
GLOSSARIO = (
    (
        "IR — Requisitos de informação (Information Requirements)",
        "O que o contratante exige que o modelo contenha em cada entrega do contrato. Aqui são extraídos do edital e aprovados por uma pessoa.",
        "ISO 19650-1:2018 (no Brasil, ABNT NBR ISO 19650-1:2022) usa os termos OIR, PIR, AIR e EIR.",
    ),
    (
        "Marco de entrega",
        "Momento em que o contratado entrega informação ao contratante (ex.: anteprojeto, projeto executivo).",
        "ISO 19650-2:2018 (ABNT NBR ISO 19650-2:2022).",
    ),
    (
        "IDM — Manual de entrega de informação",
        "Método para descrever processos, atores e as trocas de informação entre eles.",
        "ISO 29481-1:2025 (metodologia e formato).",
    ),
    (
        "IDS — Especificação de entrega de informação",
        "Arquivo que define, de forma verificável por máquina, a informação exigida no modelo IFC.",
        "buildingSMART, IDS 1.0.",
    ),
    (
        "IFC",
        "Formato aberto do modelo BIM.",
        "ISO 16739-1 (IFC 4); IFC 4.3 ADD2 pela buildingSMART.",
    ),
    (
        "BCF",
        "Formato aberto para comunicar problemas ligados a elementos do modelo.",
        "buildingSMART, BCF 2.1.",
    ),
    (
        "bSDD",
        "Dicionário de dados aberto da buildingSMART, com classes e propriedades.",
        "buildingSMART.",
    ),
    (
        "Pset",
        "Conjunto de propriedades de um elemento IFC. Os Psets oficiais são da buildingSMART.",
        "IFC.",
    ),
    (
        "Nível de informação necessária",
        "Quanta informação (geométrica, alfanumérica e documental) cada entrega exige.",
        "ISO 7817-1:2024, que substituiu a EN 17412-1:2020 (CEN).",
    ),
    (
        "Sistema de classificação",
        "Tabelas para classificar elementos e informações da construção.",
        "ABNT NBR 15965 (série em partes; confira as partes vigentes no catálogo da ABNT).",
    ),
)


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
        self._env.filters["coordenada"] = texto_coordenada
        self._env.filters["usd"] = lambda v: (
            f"US$ {v:,.4f}".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        self._env.filters["milhar"] = lambda v: f"{v:,}".replace(",", ".")
        self._env.globals.update(
            ROTULOS_TIPO=ROTULOS_TIPO,
            ROTULOS_SEVERIDADE=ROTULOS_SEVERIDADE,
            ROTULOS_DESTINATARIO=ROTULOS_DESTINATARIO,
            ROTULOS_DECISAO=ROTULOS_DECISAO,
            POSICIONAMENTO=POSICIONAMENTO,
            GLOSSARIO=GLOSSARIO,
        )

    def write_html(self, relatorio: Relatorio) -> str:
        nomes: dict[str, str] = {}
        for resultado in relatorio.resultados_ids:
            for falha in resultado.falhas:
                nomes[falha.global_id] = f"{falha.classe} · {falha.nome or 'sem nome'}"
        decisoes = {d.apontamento_id: d for d in relatorio.decisoes}
        dispensados = {
            d.apontamento_id for d in relatorio.decisoes if d.status == StatusDecisao.DISPENSADO
        }

        def grupo(origem: OrigemInconsistencia) -> list:
            return [
                a
                for a in relatorio.apontamentos
                if a.origem == origem and not a.verificacao_manual and a.id not in dispensados
            ]

        secoes = {
            "edital": grupo(OrigemInconsistencia.EDITAL),
            "modelo": grupo(OrigemInconsistencia.MODELO),
        }
        manuais = [a for a in relatorio.apontamentos if a.verificacao_manual]
        lista_dispensados = [a for a in relatorio.apontamentos if a.id in dispensados]
        verificacoes = {v.licao_id: v for v in relatorio.verificacoes_licoes}
        itens = {i.id: i for i in relatorio.itens_checklist}
        return self._env.get_template("relatorio.html.j2").render(
            r=relatorio,
            secoes=secoes,
            manuais=manuais,
            dispensados=lista_dispensados,
            decisoes=decisoes,
            verificacoes_licoes=verificacoes,
            nomes=nomes,
            itens=itens,
            Severidade=Severidade,
        )
