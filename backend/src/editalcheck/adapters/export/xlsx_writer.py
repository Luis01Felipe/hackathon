"""Exportação para planilha XLSX: requisitos de informação (RF-27) e esclarecimentos (RF-152)."""

from collections.abc import Sequence
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from editalcheck.domain.findings import texto_restricao
from editalcheck.domain.models import (
    Eir,
    FonteEvidencia,
    OrigemInconsistencia,
    Projeto,
    Relatorio,
    StatusDecisao,
)

COLUNAS = (
    ("ID", 10),
    ("Status", 11),
    ("Tópico", 9),
    ("Cláusula", 9),
    ("Página", 8),
    ("Descrição", 50),
    ("Trecho citado", 70),
    ("Fonte do trecho", 14),
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
    ("Marcos de entrega", 22),
    ("Lição aprendida", 11),
    ("Avisos", 40),
)
FONTE = {FonteEvidencia.EDITAL: "edital", FonteEvidencia.LICOES: "lições aprendidas"}


def _cabecalho(aba, colunas: Sequence[tuple[str, int]]) -> None:
    aba.append([nome for nome, _ in colunas])
    for indice, (_, largura) in enumerate(colunas, start=1):
        aba.column_dimensions[get_column_letter(indice)].width = largura
        celula = aba.cell(row=1, column=indice)
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor="1F3A5F")
        celula.alignment = Alignment(wrap_text=True, vertical="center")


def _finalizar(aba) -> None:
    for linha in aba.iter_rows(min_row=2):
        for celula in linha:
            celula.alignment = Alignment(wrap_text=True, vertical="top")
    aba.freeze_panes = "B2"
    aba.auto_filter.ref = aba.dimensions


class XlsxEirExporter:
    def to_xlsx(self, eir: Eir, projeto: Projeto) -> bytes:
        planilha = Workbook()
        aba = planilha.active
        aba.title = "Requisitos de informação"
        _cabecalho(aba, COLUNAS)
        marcos = {m.id: m.nome for m in projeto.marcos}
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
                    FONTE[r.evidencia.fonte],
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
                    ", ".join(marcos.get(m, m) for m in r.marcos) or "todos",
                    r.licao_id or "",
                    " | ".join(r.avisos),
                ]
            )
        _finalizar(aba)

        info = planilha.create_sheet("Metadados")
        for chave, valor in (
            ("Projeto", projeto.id),
            ("Edital", projeto.edital.arquivo),
            ("Modelo IFC", projeto.modelo.arquivo or "(sem modelo: revisão do edital)"),
            ("Schema", projeto.modelo.schema),
            ("Versão dos requisitos de informação (RI)", eir.versao),
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


COLUNAS_ESCLARECIMENTOS = (
    ("Apontamento", 12),
    ("Severidade", 10),
    ("Tipo", 18),
    ("Página", 8),
    ("Trecho do edital", 60),
    ("Problema", 45),
    ("Pergunta sugerida (pedido de esclarecimento)", 55),
    ("Redação sugerida / como agir", 60),
    ("Decisão", 14),
    ("Comentário da decisão", 40),
    ("Autor da decisão", 18),
    ("Gerado por IA", 10),
)
ROTULO_DECISAO = {
    StatusDecisao.PENDENTE: "Pendente",
    StatusDecisao.ACEITO: "Aceito",
    StatusDecisao.REJEITADO: "Rejeitado",
    StatusDecisao.EM_DISCUSSAO: "Em discussão",
    StatusDecisao.DISPENSADO: "Dispensado",
}
AVISO_JURIDICO = (
    "Minuta gerada automaticamente (parte por IA). Valide com o jurídico antes de protocolar "
    "qualquer pedido de esclarecimento ou impugnação do edital."
)


class XlsxClarificationExporter:
    """Matriz de esclarecimentos: um item por apontamento de origem EDITAL (RF-152)."""

    def to_xlsx(self, relatorio: Relatorio) -> bytes:
        planilha = Workbook()
        aba = planilha.active
        aba.title = "Esclarecimentos"
        _cabecalho(aba, COLUNAS_ESCLARECIMENTOS)
        for apontamento in relatorio.apontamentos:
            if apontamento.origem != OrigemInconsistencia.EDITAL:
                continue
            decisao = relatorio.decisao(apontamento.id)
            edital = [e for e in apontamento.evidencias_edital if e.fonte == FonteEvidencia.EDITAL]
            primeira = edital[0] if edital else None
            local = f"na página {primeira.pagina}" if primeira else "no edital"
            pergunta = (
                f"Solicitamos esclarecer o trecho {local}: {apontamento.titulo.rstrip('.')}. "
                "Qual critério objetivo será usado na verificação da entrega?"
            )
            aba.append(
                [
                    apontamento.id,
                    apontamento.severidade.value,
                    apontamento.tipo.value,
                    primeira.pagina if primeira else "",
                    primeira.trecho if primeira else "",
                    apontamento.titulo,
                    pergunta,
                    apontamento.como_agir,
                    ROTULO_DECISAO[decisao.status] if decisao else "Pendente",
                    decisao.comentario if decisao else "",
                    decisao.autor if decisao else "",
                    "sim" if apontamento.gerado_por_ia else "não",
                ]
            )
        _finalizar(aba)
        info = planilha.create_sheet("Leia antes")
        for linha in (
            ("Aviso", AVISO_JURIDICO),
            ("Edital", relatorio.edital_arquivo),
            ("Verificação", relatorio.verificacao_id),
            ("Gerado em", relatorio.gerado_em),
        ):
            info.append(list(linha))
        info.column_dimensions["A"].width = 16
        info.column_dimensions["B"].width = 100
        saida = BytesIO()
        planilha.save(saida)
        return saida.getvalue()
