"""Exportação do EIR para planilha XLSX (RF-27)."""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from editalcheck.domain.findings import texto_restricao
from editalcheck.domain.models import Eir, Projeto

COLUNAS = (
    ("ID", 10),
    ("Status", 11),
    ("Tópico", 9),
    ("Cláusula", 9),
    ("Página", 8),
    ("Descrição", 50),
    ("Trecho do edital", 70),
    ("Classe IFC", 16),
    ("Tipo predefinido", 14),
    ("Faceta", 13),
    ("Pset / sistema", 24),
    ("Propriedade / atributo", 22),
    ("Tipo de dado", 22),
    ("Restrição", 26),
    ("Cardinalidade", 13),
    ("Origem do vocabulário", 18),
    ("URI bSDD", 50),
    ("Verificável por IDS", 12),
    ("Motivo (não verificável)", 40),
    ("Gerado por", 11),
    ("Sugerido por lacuna", 11),
    ("Avisos", 40),
)


class XlsxEirExporter:
    def to_xlsx(self, eir: Eir, projeto: Projeto) -> bytes:
        planilha = Workbook()
        aba = planilha.active
        aba.title = "EIR"
        aba.append([nome for nome, _ in COLUNAS])
        for indice, (_, largura) in enumerate(COLUNAS, start=1):
            aba.column_dimensions[get_column_letter(indice)].width = largura
            celula = aba.cell(row=1, column=indice)
            celula.font = Font(bold=True, color="FFFFFF")
            celula.fill = PatternFill("solid", fgColor="1F3A5F")
            celula.alignment = Alignment(wrap_text=True, vertical="center")
        for r in eir.requisitos:
            aba.append(
                [
                    r.id,
                    r.status.value,
                    r.topico_id,
                    r.clausula or "",
                    r.evidencia.pagina,
                    r.descricao,
                    r.evidencia.trecho,
                    r.ifc_class or "",
                    r.predefined_type or "",
                    r.faceta.value if r.faceta else "",
                    r.pset or "",
                    r.propriedade or "",
                    r.tipo_dado or "",
                    texto_restricao(r.restricao).strip(),
                    r.cardinalidade.value,
                    r.origem_vocabulario.value if r.origem_vocabulario else "",
                    r.bsdd_uri or "",
                    "sim" if r.verificavel_por_ids else "não",
                    r.motivo_nao_verificavel or "",
                    r.gerado_por,
                    "sim" if r.sugerido_por_lacuna else "não",
                    " | ".join(r.avisos),
                ]
            )
        for linha in aba.iter_rows(min_row=2):
            for celula in linha:
                celula.alignment = Alignment(wrap_text=True, vertical="top")
        aba.freeze_panes = "B2"
        aba.auto_filter.ref = aba.dimensions

        info = planilha.create_sheet("Metadados")
        for chave, valor in (
            ("Projeto", projeto.id),
            ("Edital", projeto.edital.arquivo),
            ("Modelo IFC", projeto.modelo.arquivo),
            ("Schema", projeto.modelo.schema),
            ("Versão do EIR", eir.versao),
            ("Data", eir.data),
            ("Tópicos selecionados", ", ".join(eir.topicos_selecionados)),
            ("Aprovado por", eir.aprovado_por or ""),
        ):
            info.append([chave, valor])
        info.column_dimensions["A"].width = 22
        info.column_dimensions["B"].width = 60

        saida = BytesIO()
        planilha.save(saida)
        return saida.getvalue()
