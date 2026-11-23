"""Caixa envolvente dos elementos em coordenadas do projeto (metros).

Alimenta a coordenada XYZ do relatório, do visualizador e do BCF (RF-170).
"""

from collections.abc import Sequence

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.placement as util_placement
import ifcopenshell.util.unit as util_unit
import numpy as np

from editalcheck.adapters.ifc.abrir import abrir_ifc
from editalcheck.domain.models import CaixaEnvolvente

MEIA_CAIXA_SEM_GEOMETRIA_M = 0.5
MAX_ELEMENTOS = 2000


def _arredondar(vetor: np.ndarray) -> tuple[float, float, float]:
    x, y, z = (round(float(v), 3) for v in vetor)
    return (x, y, z)


class IfcOpenShellGeometry:
    def boxes(self, conteudo_ifc: bytes, global_ids: Sequence[str]) -> dict[str, CaixaEnvolvente]:
        modelo = abrir_ifc(conteudo_ifc)
        escala = util_unit.calculate_unit_scale(modelo)
        configuracao = ifcopenshell.geom.settings()
        configuracao.set("use-world-coords", True)
        caixas: dict[str, CaixaEnvolvente] = {}
        for global_id in list(dict.fromkeys(global_ids))[:MAX_ELEMENTOS]:
            try:
                elemento = modelo.by_guid(global_id)
            except RuntimeError:
                continue
            caixa = self._caixa(elemento, configuracao, escala)
            if caixa is not None:
                caixas[global_id] = caixa
        return caixas

    def _caixa(
        self, elemento: ifcopenshell.entity_instance, configuracao, escala: float
    ) -> CaixaEnvolvente | None:
        try:
            forma = ifcopenshell.geom.create_shape(configuracao, elemento)
            vertices = np.asarray(forma.geometry.verts, dtype=float).reshape(-1, 3)
            if len(vertices):
                return CaixaEnvolvente(
                    _arredondar(vertices.min(axis=0)), _arredondar(vertices.max(axis=0))
                )
        except Exception:  # elemento sem representação 3D ou geometria inválida
            pass
        posicionamento = getattr(elemento, "ObjectPlacement", None)
        if posicionamento is None:
            return None
        origem = util_placement.get_local_placement(posicionamento)[:3, 3] * escala
        folga = np.full(3, MEIA_CAIXA_SEM_GEOMETRIA_M)
        return CaixaEnvolvente(_arredondar(origem - folga), _arredondar(origem + folga))
