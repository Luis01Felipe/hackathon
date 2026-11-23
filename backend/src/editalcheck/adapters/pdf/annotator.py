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

from editalcheck.adapters.pdf.localizador import retangulos_do_trecho
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
    """Escreve o sumário em páginas novas no início do documento."""

    def __init__(self, documento: pymupdf.Document, largura: float, altura: float) -> None:
        self._doc = documento
        self._largura = largura
        self._altura = altura
        self.paginas = 0
        self._y = 0.0
        self.itens: list[
            tuple[int, pymupdf.Rect, str]
        ] = []  # (página do sumário, área, apontamento)
        self.links_externos: list[tuple[int, pymupdf.Rect, str]] = []
        self.pagina_do_item: dict[str, int] = {}

    def _nova_pagina(self) -> None:
        self._doc.new_page(pno=self.paginas, width=self._largura, height=self._altura)
        self.paginas += 1
        self._y = MARGEM

    def escrever(self, conteudo: str) -> pymupdf.Rect:
        """Escreve um bloco HTML; abre página nova se não couber. Devolve a área usada."""
        if self.paginas == 0:
            self._nova_pagina()
        for tentativa in range(2):
            pagina = self._doc[self.paginas - 1]
            area = pymupdf.Rect(MARGEM, self._y, self._largura - MARGEM, self._altura - MARGEM)
            sobra, _ = pagina.insert_htmlbox(
                area, conteudo, css=CSS, scale_low=1 if tentativa == 0 else 0
            )
            if sobra >= 0:
                usada = pymupdf.Rect(area.x0, area.y0, area.x1, area.y1 - sobra)
                self._y = usada.y1 + 4
                return usada
            self._nova_pagina()
        return pymupdf.Rect(MARGEM, self._y, self._largura - MARGEM, self._y)

    @property
    def pagina_atual(self) -> int:
        return self.paginas - 1


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
            sumario = _Sumario(documento, primeira.width, primeira.height)
            self._escrever_sumario(sumario, itens, locais, por_id)
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
        ocupadas: dict[int, list[float]] = {}  # alturas já usadas por etiquetas, por página
        for apontamento in itens:
            nota = _nota(apontamento, decisoes.get(apontamento.id))
            for evidencia in _do_edital(apontamento):
                if not 1 <= evidencia.pagina <= documento.page_count:
                    continue
                pagina = documento[evidencia.pagina - 1]
                areas = retangulos_do_trecho(pagina, evidencia.trecho)
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

    def _escrever_sumario(
        self,
        sumario: _Sumario,
        itens: Sequence[Apontamento],
        locais: dict[str, _Local],
        decisoes: dict[str, DecisaoApontamento],
    ) -> None:
        sumario.escrever(
            "<p style='font-size:15pt'><b>Ajustes sugeridos pelo EditalCheck</b></p>"
            f"<p style='font-size:9pt;color:#444'>{len(itens)} apontamento(s). Clique num item "
            "para ir ao trecho. No trecho, clique na etiqueta da margem (ex.: APT-006) para "
            "voltar a este sumário. Os detalhes também estão nas notas dos grifos.</p>"
            f"<p style='font-size:8pt;color:#8a4b16'>{_esc(AVISO_JURIDICO)}</p>"
        )
        for origem in (OrigemInconsistencia.EDITAL, OrigemInconsistencia.MODELO):
            grupo = [a for a in itens if a.origem == origem]
            if not grupo:
                continue
            cor = "#6a3fb5" if origem == OrigemInconsistencia.EDITAL else "#00796b"
            sumario.escrever(
                f"<p style='font-size:12pt;color:{cor}'><b>{_esc(SECAO[origem])} "
                f"({len(grupo)})</b></p>"
            )
            for apontamento in grupo:
                self._item(sumario, apontamento, locais.get(apontamento.id), decisoes)

    @staticmethod
    def _item(
        sumario: _Sumario,
        apontamento: Apontamento,
        local: _Local | None,
        decisoes: dict[str, DecisaoApontamento],
    ) -> None:
        onde = (
            f"página {local.pagina + 1} do edital"
            if local
            else "sem trecho no edital: cláusula nova"
        )
        decisao = decisoes.get(apontamento.id)
        partes = [
            f"<p style='font-size:9pt'><b>{apontamento.id}</b> · "
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
        area = sumario.escrever("".join(partes))
        sumario.pagina_do_item[apontamento.id] = sumario.pagina_atual
        if local:
            sumario.itens.append((sumario.pagina_atual, area, apontamento.id))
        for referencia in apontamento.referencias:
            if not referencia.uri:
                continue
            linha = sumario.escrever(
                f"<p style='font-size:8pt;color:#1f5fbf'>Referência: {_esc(referencia.rotulo)}"
                f" — {_esc(referencia.uri)}</p>"
            )
            sumario.links_externos.append((sumario.pagina_atual, linha, referencia.uri))
        sumario.escrever("<p style='font-size:4pt'>&nbsp;</p>")

    # ------------------------------------------------------------------ links

    @staticmethod
    def _ligar(
        documento: pymupdf.Document,
        sumario: _Sumario,
        locais: dict[str, _Local],
        marcadores: Sequence[_Marcador],
    ) -> None:
        deslocamento = sumario.paginas
        for pagina, area, apontamento_id in sumario.itens:
            local = locais[apontamento_id]
            documento[pagina].insert_link(
                {
                    "kind": pymupdf.LINK_GOTO,
                    "from": area,
                    "page": local.pagina + deslocamento,
                    "to": pymupdf.Point(0, max(0.0, local.y - 30)),
                }
            )
        for pagina, area, uri in sumario.links_externos:
            documento[pagina].insert_link({"kind": pymupdf.LINK_URI, "from": area, "uri": uri})
        for marcador in marcadores:
            destino = sumario.pagina_do_item.get(marcador.apontamento_id)
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
                    else sumario.pagina_do_item.get(apontamento.id, 0) + 1
                )
                titulo = f"{apontamento.id} · {apontamento.titulo}"
                indice.append([2, titulo[:120], pagina])
        return indice
