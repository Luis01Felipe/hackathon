"""Edital anotado: cópia do PDF com destaque e nota em cada trecho apontado (RF-151).

Gerado em memória com PyMuPDF. Cada nota traz o ID do apontamento, o tipo, o
problema, a sugestão de redação e a decisão registrada (aceito, rejeitado...).
"""

from collections.abc import Sequence

import pymupdf

from editalcheck.domain.models import (
    Apontamento,
    DecisaoApontamento,
    FonteEvidencia,
    OrigemInconsistencia,
    Severidade,
)

CORES = {
    Severidade.ALTA: (0.95, 0.45, 0.42),
    Severidade.MEDIA: (1.0, 0.78, 0.35),
    Severidade.BAIXA: (0.75, 0.82, 0.9),
}
ROTULO_DECISAO = {
    "pendente": "Pendente",
    "aceito": "Aceito",
    "rejeitado": "Rejeitado",
    "em_discussao": "Em discussão",
    "dispensado": "Dispensado",
}
TAMANHO_BUSCA = 120  # PyMuPDF procura trechos curtos com mais precisão


def _nota(apontamento: Apontamento, decisao: DecisaoApontamento | None) -> str:
    linhas = [
        f"{apontamento.id} · {apontamento.titulo}",
        f"Severidade: {apontamento.severidade.value} · Quem age: contratante",
    ]
    if apontamento.como_agir:
        linhas.append(f"Como agir: {apontamento.como_agir}")
    if apontamento.por_que:
        linhas.append(f"Por que: {apontamento.por_que}")
    if decisao:
        texto = f"Decisão: {ROTULO_DECISAO.get(decisao.status.value, decisao.status.value)}"
        if decisao.comentario:
            texto += f" — {decisao.comentario}"
        if decisao.autor:
            texto += f" ({decisao.autor})"
        linhas.append(texto)
    if apontamento.gerado_por_ia:
        linhas.append("Texto gerado por IA: revisar.")
    return "\n".join(linhas)


def _areas(pagina: pymupdf.Page, trecho: str) -> list[pymupdf.Rect]:
    texto = " ".join(trecho.split())
    for tamanho in (len(texto), TAMANHO_BUSCA, 60, 30):
        alvo = texto[:tamanho].strip()
        if len(alvo) < 12:
            break
        areas = pagina.search_for(alvo)
        if areas:
            return areas
    return []


class PyMuPdfEditalAnnotator:
    def annotate(
        self,
        pdf: bytes,
        apontamentos: Sequence[Apontamento],
        decisoes: Sequence[DecisaoApontamento],
    ) -> bytes:
        por_id = {d.apontamento_id: d for d in decisoes}
        with pymupdf.open(stream=pdf, filetype="pdf") as documento:
            sem_trecho: dict[int, list[str]] = {}
            for apontamento in apontamentos:
                if apontamento.origem != OrigemInconsistencia.EDITAL:
                    continue
                nota = _nota(apontamento, por_id.get(apontamento.id))
                for evidencia in apontamento.evidencias_edital:
                    if evidencia.fonte != FonteEvidencia.EDITAL:
                        continue
                    if not 1 <= evidencia.pagina <= documento.page_count:
                        continue
                    pagina = documento[evidencia.pagina - 1]
                    areas = _areas(pagina, evidencia.trecho)
                    if not areas:
                        sem_trecho.setdefault(evidencia.pagina, []).append(nota)
                        continue
                    destaque = pagina.add_highlight_annot(areas)
                    destaque.set_colors(stroke=CORES[apontamento.severidade])
                    destaque.set_info(title=f"EditalCheck {apontamento.id}", content=nota)
                    destaque.update()
            for numero, notas in sem_trecho.items():
                pagina = documento[numero - 1]
                icone = pagina.add_text_annot(pymupdf.Point(20, 20), "\n\n".join(notas))
                icone.set_info(title="EditalCheck — apontamentos desta página")
                icone.update()
            return documento.tobytes(garbage=3, deflate=True)
