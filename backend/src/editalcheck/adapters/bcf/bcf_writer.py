"""Exportação dos apontamentos do modelo em BCF 2.1 (RF-55).

Usa o módulo ``bcf`` do IfcOpenShell (bcf-client). Cada apontamento com
elementos (não conformidade e qualidade do modelo) vira um tópico, com os
GlobalIds selecionados e a câmera apontada para o centro dos elementos.
"""

import tempfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.util.placement as util_placement
import ifcopenshell.util.unit as util_unit
import numpy as np
from bcf.v2.bcfxml import BcfXml

from editalcheck.domain.models import Apontamento, Relatorio, TipoApontamento

TIPOS_BCF = (TipoApontamento.NAO_CONFORMIDADE, TipoApontamento.QUALIDADE_MODELO)
AUTOR = "EditalCheck"


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
    return "\n".join(partes)


def _centro(modelo: ifcopenshell.file, guids: tuple[str, ...], escala: float) -> np.ndarray:
    pontos: list[np.ndarray] = []
    for guid in guids:
        try:
            elemento = modelo.by_guid(guid)
        except RuntimeError:
            continue
        posicionamento = getattr(elemento, "ObjectPlacement", None)
        if posicionamento is None:
            continue
        matriz = util_placement.get_local_placement(posicionamento)
        pontos.append(np.array(matriz[:3, 3], dtype=float) * escala)
    if not pontos:
        return np.zeros(3)
    return np.mean(pontos, axis=0)


class BcfClientWriter:
    def write(self, relatorio: Relatorio, ifc_path: str) -> bytes:
        modelo = ifcopenshell.open(ifc_path)
        escala = util_unit.calculate_unit_scale(modelo)
        bcf = BcfXml.create_new(f"EditalCheck — {relatorio.modelo_arquivo}")
        for apontamento in relatorio.apontamentos:
            if apontamento.tipo not in TIPOS_BCF or not apontamento.elementos:
                continue
            topico = bcf.add_topic(
                title=f"{apontamento.id} · {apontamento.titulo}"[:250],
                description=_descricao(apontamento),
                author=AUTOR,
                topic_type="Error"
                if apontamento.tipo == TipoApontamento.NAO_CONFORMIDADE
                else "Issue",
                topic_status="Open",
            )
            alvo = _centro(modelo, apontamento.elementos, escala)
            topico.add_viewpoint_from_point_and_guids(alvo, *apontamento.elementos)
        with tempfile.TemporaryDirectory() as pasta:
            destino = Path(pasta) / "resultado.bcf"
            bcf.save(destino)
            conteudo = destino.read_bytes()
        bcf.close()
        return conteudo
