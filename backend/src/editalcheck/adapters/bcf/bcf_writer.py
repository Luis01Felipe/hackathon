"""Exportação dos apontamentos do modelo em BCF 2.1 (RF-55).

Usa o módulo ``bcf`` do IfcOpenShell (bcf-client). Cada apontamento com
elementos (não conformidade e qualidade do modelo) vira um tópico com:

- um viewpoint de visão geral, com todos os elementos selecionados (quando o
  apontamento tem mais de um elemento);
- **um viewpoint por elemento**, com só aquele elemento selecionado e
  destacado em vermelho, e a câmera enquadrando a caixa envolvente dele;
- um comentário por viewpoint, que diz qual elemento é e por que falhou.

O primeiro viewpoint de cada tópico se chama ``viewpoint.bcfv``, o nome
padrão que ferramentas do BCF 2.0 procuram. Os demais usam o GUID.
"""

import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement as util_placement
import ifcopenshell.util.unit as util_unit
import numpy as np
from bcf.geometry import camera_vectors_from_target_position
from bcf.v2 import model as mdl
from bcf.v2.bcfxml import BcfXml
from bcf.v2.topic import TopicHandler
from bcf.v2.visinfo import VisualizationInfoHandler, build_camera_from_vectors
from bcf.xml_parser import XmlParserSerializer
from xsdata.models.datatype import XmlDateTime

from editalcheck.domain.models import Apontamento, Relatorio, Severidade, TipoApontamento

TIPOS_BCF = (TipoApontamento.NAO_CONFORMIDADE, TipoApontamento.QUALIDADE_MODELO)
AUTOR = "EditalCheck"
VIEWPOINT_PADRAO = "viewpoint.bcfv"
COR_DESTAQUE = "FF0000"  # vermelho (RGB em hexadecimal, BCF 2.1)
DIRECAO_CAMERA = np.array([1.0, -1.0, 0.9]) / np.linalg.norm([1.0, -1.0, 0.9])
DISTANCIA_MINIMA_M = 4.0
FOLGA_ENQUADRAMENTO = 1.3
MEIA_CAIXA_SEM_GEOMETRIA_M = 0.5
PRIORIDADE = {Severidade.ALTA: "Alta", Severidade.MEDIA: "Média", Severidade.BAIXA: "Baixa"}
ROTULO_TIPO = {
    TipoApontamento.NAO_CONFORMIDADE: "Não conformidade",
    TipoApontamento.QUALIDADE_MODELO: "Qualidade do modelo",
}


@dataclass(frozen=True)
class _Caixa:
    minimo: np.ndarray
    maximo: np.ndarray

    @property
    def centro(self) -> np.ndarray:
        return (self.minimo + self.maximo) / 2

    @property
    def diagonal(self) -> float:
        return float(np.linalg.norm(self.maximo - self.minimo))

    @staticmethod
    def unir(caixas: list["_Caixa"]) -> "_Caixa | None":
        if not caixas:
            return None
        return _Caixa(
            np.min([c.minimo for c in caixas], axis=0), np.max([c.maximo for c in caixas], axis=0)
        )


@dataclass(frozen=True)
class _Elemento:
    global_id: str
    classe: str
    nome: str
    motivo: str
    caixa: _Caixa | None


def _descricao(apontamento: Apontamento) -> str:
    partes = [apontamento.titulo]
    if apontamento.requisito_id:
        partes.append(f"Requisito: {apontamento.requisito_id}")
    for evidencia in apontamento.evidencias_edital:
        partes.append(f'Edital, p. {evidencia.pagina}: "{evidencia.trecho}"')
    if apontamento.como_agir:
        partes.append(f"Como agir: {apontamento.como_agir}")
    if apontamento.por_que:
        partes.append(f"Por que: {apontamento.por_que}")
    if apontamento.referencias:
        partes.append("Referências: " + "; ".join(r.rotulo for r in apontamento.referencias))
    if apontamento.gerado_por_ia:
        partes.append("Texto gerado por IA: revisar.")
    partes.append(
        f"Viewpoints: {len(apontamento.elementos)} elemento(s), um viewpoint para cada um."
    )
    return "\n".join(partes)


class _Geometria:
    """Caixa envolvente de cada elemento em coordenadas do mundo (metros)."""

    def __init__(self, modelo: ifcopenshell.file) -> None:
        self._modelo = modelo
        self._escala = util_unit.calculate_unit_scale(modelo)
        self._configuracao = ifcopenshell.geom.settings()
        self._configuracao.set("use-world-coords", True)

    def elemento(self, global_id: str) -> ifcopenshell.entity_instance | None:
        try:
            return self._modelo.by_guid(global_id)
        except RuntimeError:
            return None

    def caixa(self, elemento: ifcopenshell.entity_instance) -> _Caixa | None:
        try:
            forma = ifcopenshell.geom.create_shape(self._configuracao, elemento)
            vertices = np.asarray(forma.geometry.verts, dtype=float).reshape(-1, 3)
            if len(vertices):
                return _Caixa(vertices.min(axis=0), vertices.max(axis=0))
        except Exception:  # elemento sem representação 3D ou geometria inválida
            pass
        posicionamento = getattr(elemento, "ObjectPlacement", None)
        if posicionamento is None:
            return None
        origem = util_placement.get_local_placement(posicionamento)[:3, 3] * self._escala
        folga = np.full(3, MEIA_CAIXA_SEM_GEOMETRIA_M)
        return _Caixa(origem - folga, origem + folga)


def _camera(caixa: _Caixa | None) -> mdl.PerspectiveCamera:
    """Câmera em perspectiva olhando para o centro da caixa, de cima e de lado."""
    if caixa is None:
        caixa = _Caixa(np.zeros(3), np.zeros(3))
    distancia = max(caixa.diagonal * FOLGA_ENQUADRAMENTO, DISTANCIA_MINIMA_M)
    posicao, direcao, para_cima = camera_vectors_from_target_position(
        caixa.centro, DIRECAO_CAMERA * distancia
    )
    return build_camera_from_vectors(posicao, direcao, para_cima)


def _visualizacao(global_ids: list[str], caixa: _Caixa | None) -> mdl.VisualizationInfo:
    componentes = [mdl.Component(ifc_guid=g) for g in global_ids]
    return mdl.VisualizationInfo(
        guid=str(uuid.uuid4()),
        components=mdl.Components(
            selection=mdl.ComponentSelection(component=componentes),
            visibility=mdl.ComponentVisibility(default_visibility=True),
            coloring=mdl.ComponentColoring(
                color=[mdl.ComponentColoringColor(component=list(componentes), color=COR_DESTAQUE)]
            ),
        ),
        perspective_camera=_camera(caixa),
    )


def _motivos(relatorio: Relatorio, apontamento: Apontamento) -> dict[str, str]:
    motivos: dict[str, str] = {}
    for resultado in relatorio.resultados_ids:
        if resultado.requisito_id != apontamento.requisito_id:
            continue
        for falha in resultado.falhas:
            motivos[falha.global_id] = falha.motivo
    return motivos


class BcfClientWriter:
    def __init__(self) -> None:
        self._xml = XmlParserSerializer()

    def write(self, relatorio: Relatorio, ifc_path: str) -> bytes:
        geometria = _Geometria(ifcopenshell.open(ifc_path))
        bcf = BcfXml.create_new(f"EditalCheck — {relatorio.modelo_arquivo}", self._xml)
        indice_topico = 0
        for apontamento in relatorio.apontamentos:
            if apontamento.tipo not in TIPOS_BCF or not apontamento.elementos:
                continue
            indice_topico += 1
            topico = bcf.add_topic(
                title=f"{apontamento.id} · {apontamento.titulo}"[:250],
                description=_descricao(apontamento),
                author=AUTOR,
                topic_type="Error"
                if apontamento.tipo == TipoApontamento.NAO_CONFORMIDADE
                else "Issue",
                topic_status="Open",
            )
            topico.topic.priority = PRIORIDADE[apontamento.severidade]
            topico.topic.index = indice_topico
            topico.topic.labels = [
                r for r in (ROTULO_TIPO[apontamento.tipo], apontamento.requisito_id) if r
            ]
            self._viewpoints(
                topico, apontamento, self._elementos(relatorio, apontamento, geometria)
            )
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "resultado.bcf"
            bcf.save(destino)
            conteudo = destino.read_bytes()
        bcf.close()
        return conteudo

    def _elementos(
        self, relatorio: Relatorio, apontamento: Apontamento, geometria: _Geometria
    ) -> list[_Elemento]:
        motivos = _motivos(relatorio, apontamento)
        elementos: list[_Elemento] = []
        for global_id in dict.fromkeys(apontamento.elementos):
            entidade = geometria.elemento(global_id)
            elementos.append(
                _Elemento(
                    global_id=global_id,
                    classe=entidade.is_a() if entidade else "elemento",
                    nome=(getattr(entidade, "Name", None) or "sem nome")
                    if entidade
                    else "sem nome",
                    motivo=motivos.get(global_id, apontamento.titulo),
                    caixa=geometria.caixa(entidade) if entidade else None,
                )
            )
        return elementos

    def _viewpoints(
        self, topico: TopicHandler, apontamento: Apontamento, elementos: list[_Elemento]
    ) -> None:
        geral = _Caixa.unir([e.caixa for e in elementos if e.caixa])
        if len(elementos) > 1:
            self._adicionar(
                topico,
                _visualizacao([e.global_id for e in elementos], geral),
                f"Visão geral: {len(elementos)} elementos de {apontamento.id}.",
            )
        total = len(elementos)
        for posicao, elemento in enumerate(elementos, start=1):
            self._adicionar(
                topico,
                _visualizacao([elemento.global_id], elemento.caixa or geral),
                f"Elemento {posicao} de {total}: {elemento.nome} ({elemento.classe}, GlobalId "
                f"{elemento.global_id}). {elemento.motivo}",
            )

    def _adicionar(
        self, topico: TopicHandler, visualizacao: mdl.VisualizationInfo, comentario: str
    ) -> None:
        indice = len(topico.markup.viewpoints)
        arquivo = VIEWPOINT_PADRAO if indice == 0 else f"{visualizacao.guid}.bcfv"
        topico.viewpoints[arquivo] = VisualizationInfoHandler(
            visualization_info=visualizacao, xml_handler=self._xml
        )
        topico.markup.viewpoints.append(
            mdl.ViewPoint(viewpoint=arquivo, snapshot=None, index=indice, guid=visualizacao.guid)
        )
        topico.markup.comment.append(
            mdl.Comment(
                guid=str(uuid.uuid4()),
                date=XmlDateTime.from_datetime(datetime.now()),
                author=AUTOR,
                comment=comentario,
                viewpoint=mdl.CommentViewpoint(guid=visualizacao.guid),
            )
        )
