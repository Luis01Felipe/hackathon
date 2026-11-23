"""Edital anotado em PDF (RF-151): o mesmo resultado da aba "Edital", para baixar.

Estrutura do arquivo gerado (em memória, com PyMuPDF):

- **Sumário de ajustes** nas primeiras páginas: um item por apontamento, com o
  problema, como agir, a decisão registrada e as referências. Cada item é um
  link para o trecho; cada referência com endereço é um link externo.
- **Marcadores (bookmarks)** "Corrigir no edital" e "Corrigir no modelo", com um
  marcador por apontamento. Leitores como Acrobat, Edge e Foxit mostram esse
  índice e os comentários num painel lateral.
- **No edital:** grifo na cor da severidade, nota com o detalhe completo e uma
  etiqueta na margem (ex.: APT-006) que volta ao sumário.

Os apontamentos do modelo aparecem na cláusula do edital que gerou o requisito.
"""

import html
from collections.abc import Sequence
from dataclasses import dataclass

import pymupdf

from editalcheck.adapters.pdf.localizador import PaginasIndexadas, retangulos_do_trecho
from editalcheck.domain.models import (
    Apontamento,
    DecisaoApontamento,
    FonteEvidencia,
    OrigemInconsistencia,
    Severidade,
)

CORES_GRIFO = {
    Severidade.ALTA: (0.95, 0.45, 0.42),
    Severidade.MEDIA: (1.0, 0.78, 0.35),
    Severidade.BAIXA: (0.75, 0.82, 0.9),
}
COR_ORIGEM = {
    OrigemInconsistencia.EDITAL: (0.416, 0.247, 0.71),
    OrigemInconsistencia.MODELO: (0.0, 0.475, 0.42),
}
HEX_SEVERIDADE = {
    Severidade.ALTA: "#c62828",
    Severidade.MEDIA: "#a15c00",
    Severidade.BAIXA: "#3f5f7d",
}
ROTULO_SEVERIDADE = {Severidade.ALTA: "Alta", Severidade.MEDIA: "Média", Severidade.BAIXA: "Baixa"}
ROTULO_DECISAO = {
    "pendente": "Pendente",
    "aceito": "Aceito",
    "rejeitado": "Rejeitado",
    "em_discussao": "Em discussão",
    "dispensado": "Dispensado",
}
SECAO = {
    OrigemInconsistencia.EDITAL: "Corrigir no edital — o contratante age",
    OrigemInconsistencia.MODELO: "Corrigir no modelo — o contratado age (cláusula de origem)",
}
MARGEM = 40
ALTURA_ETIQUETA = 11
CSS = "* { font-family: sans-serif; } p { margin: 0 0 2pt 0; }"
AVISO_JURIDICO = (
    "Sugestões geradas automaticamente (parte por IA) e conferidas contra o texto do edital. "
    "Valide com o jurídico antes de protocolar pedido de esclarecimento ou impugnação."
)


@dataclass
class _Local:
    pagina: int  # índice da página no edital original (0 = primeira)
    y: float


@dataclass
class _Marcador:
    pagina: int
    rect: pymupdf.Rect
    apontamento_id: str


def _esc(texto: str) -> str:
    return html.escape(texto, quote=False)


def _nota(apontamento: Apontamento, decisao: DecisaoApontamento | None) -> str:
    quem = "contratante" if apontamento.origem == OrigemInconsistencia.EDITAL else "contratado"
    linhas = [
        f"{apontamento.id} · {apontamento.titulo}",
        f"Corrigir no {apontamento.origem.value} · {quem} age · severidade "
        f"{ROTULO_SEVERIDADE[apontamento.severidade].lower()}",
    ]
    if apontamento.detalhe:
        linhas.append(f"Detalhe: {apontamento.detalhe}")
    if apontamento.como_agir:
        linhas.append(f"Como agir: {apontamento.como_agir}")
    if apontamento.por_que:
        linhas.append(f"Por que: {apontamento.por_que}")
    referencias = [r.rotulo + (f" ({r.uri})" if r.uri else "") for r in apontamento.referencias]
    if referencias:
        linhas.append("Referências: " + "; ".join(referencias))
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


def _do_edital(apontamento: Apontamento):
    return [e for e in apontamento.evidencias_edital if e.fonte == FonteEvidencia.EDITAL]


class _Sumario:
    """Sumário diagramado de uma vez com `pymupdf.Story`, num PDF à parte.

    Uma única diagramação embute a fonte uma vez (inserir bloco a bloco embutia a fonte
    a cada bloco e o arquivo crescia centenas de MB). Cada item é um `<div id=...>`:
    a posição dele vira o link para o trecho; `<a href>` externos viram links nativos.
    """

    def __init__(self, conteudo_html: str, largura: float, altura: float) -> None:
        self.areas: dict[str, tuple[int, pymupdf.Rect]] = {}  # id -> (página, área)
        area_util = pymupdf.Rect(MARGEM, MARGEM, largura - MARGEM, altura - MARGEM)
        pagina = pymupdf.Rect(0, 0, largura, altura)

        def retangulo(_numero: int, _preenchido: pymupdf.Rect):
            return pagina, area_util, None

        def posicao(elemento) -> None:
            if not (elemento.open_close & 1) or not elemento.id:
                return
            self.areas.setdefault(elemento.id, (elemento.page_num - 1, pymupdf.Rect(elemento.rect)))

        historia = pymupdf.Story(html=conteudo_html, user_css=CSS)
        self.documento: pymupdf.Document = historia.write_with_links(retangulo, posicao)
        self.paginas: int = self.documento.page_count

    def pagina_do_item(self, apontamento_id: str) -> int | None:
        area = self.areas.get(_ancora(apontamento_id))
        return area[0] if area else None


def _ancora(apontamento_id: str) -> str:
    return "item-" + "".join(c if c.isalnum() or c in "-_" else "_" for c in apontamento_id)


def _uri_segura(uri: str) -> bool:
    return uri.startswith(("https://", "http://"))


class PyMuPdfEditalAnnotator:
    """Usa a mesma localização por palavras do visualizador: grifo e tela coincidem."""

    def annotate(
        self,
        pdf: bytes,
        apontamentos: Sequence[Apontamento],
        decisoes: Sequence[DecisaoApontamento],
    ) -> bytes:
        por_id = {d.apontamento_id: d for d in decisoes}
        itens = [
            a for a in apontamentos if a.origem == OrigemInconsistencia.EDITAL or _do_edital(a)
        ]
        itens.sort(key=lambda a: (a.origem != OrigemInconsistencia.EDITAL, a.id))
        with pymupdf.open(stream=pdf, filetype="pdf") as documento:
            locais, marcadores = self._anotar(documento, itens, por_id)
            primeira = documento[0].rect if documento.page_count else pymupdf.paper_rect("a4")
            sumario = _Sumario(
                self._html_sumario(itens, locais, por_id), primeira.width, primeira.height
            )
            with sumario.documento:
                documento.insert_pdf(sumario.documento, start_at=0)
            self._ligar(documento, sumario, locais, marcadores)
            documento.set_toc(self._indice(itens, locais, sumario))
            return documento.tobytes(garbage=3, deflate=True)

    # ------------------------------------------------------------------ edital

    def _anotar(
        self,
        documento: pymupdf.Document,
        itens: Sequence[Apontamento],
        decisoes: dict[str, DecisaoApontamento],
    ) -> tuple[dict[str, _Local], list[_Marcador]]:
        locais: dict[str, _Local] = {}
        marcadores: list[_Marcador] = []
        sem_trecho: dict[int, list[str]] = {}
        indexadas = PaginasIndexadas()
        ocupadas: dict[int, list[float]] = {}  # alturas já usadas por etiquetas, por página
        for apontamento in itens:
            nota = _nota(apontamento, decisoes.get(apontamento.id))
            for evidencia in _do_edital(apontamento):
                if not 1 <= evidencia.pagina <= documento.page_count:
                    continue
                pagina = documento[evidencia.pagina - 1]
                areas = retangulos_do_trecho(pagina, evidencia.trecho, indexadas.de(pagina))
                if not areas:
                    sem_trecho.setdefault(pagina.number, []).append(nota)
                    locais.setdefault(apontamento.id, _Local(pagina.number, 20))
                    continue
                grifo = pagina.add_highlight_annot(areas)
                grifo.set_colors(stroke=CORES_GRIFO[apontamento.severidade])
                grifo.set_info(title=f"EditalCheck {apontamento.id}", content=nota)
                grifo.update()
                topo = min(a.y0 for a in areas)
                locais.setdefault(apontamento.id, _Local(pagina.number, topo))
                usadas = ocupadas.setdefault(pagina.number, [])
                y = topo
                while any(abs(y - u) < ALTURA_ETIQUETA for u in usadas):
                    y += ALTURA_ETIQUETA
                usadas.append(y)
                marcadores.append(self._etiqueta(pagina, apontamento, y))
        for indice, notas in sem_trecho.items():
            icone = documento[indice].add_text_annot(pymupdf.Point(20, 20), "\n\n".join(notas))
            icone.set_info(title="EditalCheck — apontamentos desta página (trecho não localizado)")
            icone.update()
        return locais, marcadores

    @staticmethod
    def _etiqueta(pagina: pymupdf.Page, apontamento: Apontamento, y: float) -> _Marcador:
        """Etiqueta na margem esquerda (ex.: APT-006) que volta ao sumário."""
        area = pymupdf.Rect(3, y - 1, 49, y + ALTURA_ETIQUETA - 1)
        cor = COR_ORIGEM[apontamento.origem]
        etiqueta = pagina.add_freetext_annot(
            area,
            apontamento.id,
            fontsize=6.5,
            text_color=cor,
            fill_color=(1, 1, 1),
            border_width=0.8,
            align=pymupdf.TEXT_ALIGN_CENTER,
        )
        etiqueta.set_info(title=f"EditalCheck {apontamento.id}")
        etiqueta.update()
        return _Marcador(pagina.number, area, apontamento.id)

    # ------------------------------------------------------------------ sumário

    def _html_sumario(
        self,
        itens: Sequence[Apontamento],
        locais: dict[str, _Local],
        decisoes: dict[str, DecisaoApontamento],
    ) -> str:
        partes = [
            "<p style='font-size:15pt'><b>Ajustes sugeridos pelo EditalCheck</b></p>"
            f"<p style='font-size:9pt;color:#444'>{len(itens)} apontamento(s). Clique num item "
            "para ir ao trecho. No trecho, clique na etiqueta da margem (ex.: APT-006) para "
            "voltar a este sumário. Os detalhes também estão nas notas dos grifos.</p>"
            f"<p style='font-size:8pt;color:#8a4b16'>{_esc(AVISO_JURIDICO)}</p>"
        ]
        for origem in (OrigemInconsistencia.EDITAL, OrigemInconsistencia.MODELO):
            grupo = [a for a in itens if a.origem == origem]
            if not grupo:
                continue
            cor = "#6a3fb5" if origem == OrigemInconsistencia.EDITAL else "#00796b"
            partes.append(
                f"<p style='font-size:12pt;color:{cor};margin-top:8pt'>"
                f"<b>{_esc(SECAO[origem])} ({len(grupo)})</b></p>"
            )
            partes.extend(self._item(a, locais.get(a.id), decisoes.get(a.id)) for a in grupo)
        return "".join(partes)

    @staticmethod
    def _item(
        apontamento: Apontamento,
        local: _Local | None,
        decisao: DecisaoApontamento | None,
    ) -> str:
        onde = (
            f"página {local.pagina + 1} do edital"
            if local
            else "sem trecho no edital: cláusula nova"
        )
        partes = [
            f"<div id='{_ancora(apontamento.id)}'>",
            f"<p style='font-size:9pt'><b>{_esc(apontamento.id)}</b> · "
            f"<span style='color:{HEX_SEVERIDADE[apontamento.severidade]}'>"
            f"{ROTULO_SEVERIDADE[apontamento.severidade]}</span> · {_esc(onde)}</p>",
            f"<p style='font-size:9.5pt'><b>{_esc(apontamento.titulo)}</b></p>",
        ]
        if apontamento.como_agir:
            partes.append(
                f"<p style='font-size:8.5pt'><b>Como agir:</b> {_esc(apontamento.como_agir)}</p>"
            )
        if decisao:
            texto = ROTULO_DECISAO.get(decisao.status.value, decisao.status.value)
            if decisao.comentario:
                texto += f" — {decisao.comentario}"
            partes.append(f"<p style='font-size:8.5pt'><b>Decisão:</b> {_esc(texto)}</p>")
        partes.append("</div>")
        for referencia in apontamento.referencias:
            if not referencia.uri or not _uri_segura(referencia.uri):
                continue
            partes.append(
                f"<p style='font-size:8pt'>Referência: <a href='{html.escape(referencia.uri)}' "
                f"style='color:#1f5fbf'>{_esc(referencia.rotulo)}</a> "
                f"<span style='color:#666'>({_esc(referencia.uri)})</span></p>"
            )
        partes.append("<p style='font-size:5pt'>&#160;</p>")
        return "".join(partes)

    # ------------------------------------------------------------------ links

    @staticmethod
    def _ligar(
        documento: pymupdf.Document,
        sumario: _Sumario,
        locais: dict[str, _Local],
        marcadores: Sequence[_Marcador],
    ) -> None:
        deslocamento = sumario.paginas
        for apontamento_id, local in locais.items():
            area = sumario.areas.get(_ancora(apontamento_id))
            if area is None:
                continue
            pagina, retangulo = area
            documento[pagina].insert_link(
                {
                    "kind": pymupdf.LINK_GOTO,
                    "from": retangulo,
                    "page": local.pagina + deslocamento,
                    "to": pymupdf.Point(0, max(0.0, local.y - 30)),
                }
            )
        for marcador in marcadores:
            destino = sumario.pagina_do_item(marcador.apontamento_id)
            if destino is None:
                continue
            documento[marcador.pagina + deslocamento].insert_link(
                {"kind": pymupdf.LINK_GOTO, "from": marcador.rect, "page": destino}
            )

    @staticmethod
    def _indice(
        itens: Sequence[Apontamento], locais: dict[str, _Local], sumario: _Sumario
    ) -> list[list]:
        indice: list[list] = [[1, "Sumário de ajustes (EditalCheck)", 1]]
        for origem in (OrigemInconsistencia.EDITAL, OrigemInconsistencia.MODELO):
            grupo = [a for a in itens if a.origem == origem]
            if not grupo:
                continue
            primeira = locais.get(grupo[0].id)
            indice.append(
                [1, SECAO[origem], (primeira.pagina + sumario.paginas + 1) if primeira else 1]
            )
            for apontamento in grupo:
                local = locais.get(apontamento.id)
                pagina = (
                    local.pagina + sumario.paginas + 1
                    if local
                    else (sumario.pagina_do_item(apontamento.id) or 0) + 1
                )
                titulo = f"{apontamento.id} · {apontamento.titulo}"
                indice.append([2, titulo[:120], pagina])
        return indice
