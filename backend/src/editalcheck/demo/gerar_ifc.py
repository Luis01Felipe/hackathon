"""Gera o IFC4 sintético da demo: escola de 2 pavimentos com acertos e erros planejados.

Os elementos são caixas extrudadas (geometria simples, suficiente para o 3D).
As propriedades seguem os Psets oficiais. Os erros são intencionais e estão
documentados em data/demo/gabarito.json.
"""

from pathlib import Path

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.context
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.project
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
import ifcopenshell.api.unit
import numpy as np

COMPRIMENTO = 40.0  # eixo X (m)
LARGURA = 14.0  # eixo Y (m)
PE_DIREITO = 3.5
ESPESSURA_PAREDE = 0.2
CORREDOR = (6.0, 8.0)  # faixa Y do corredor
MODULO = 8.0  # largura das salas no eixo X
TIPOS_SALA_TERREO = (
    "Secretaria",
    "Diretoria",
    "Biblioteca",
    "Sala de aula 01",
    "Refeitório",
    "Sala de baterias",  # caso real citado pela banca: não pode ter janelas
    "Sanitário feminino",
    "Sanitário masculino",
)
TIPOS_SALA_SUPERIOR = (
    "Sala de aula 02",
    "Sala de aula 03",
    "Sala de aula 04",
    "Sala de aula 05",
    "Sala de aula 06",
    "Sala de aula 07",
    "Laboratório de ciências",
    "Sala de informática",
)


def _matriz(x: float, y: float, z: float, rotacao_z_graus: float = 0.0) -> np.ndarray:
    angulo = np.radians(rotacao_z_graus)
    matriz = np.eye(4)
    matriz[0, 0], matriz[0, 1] = np.cos(angulo), -np.sin(angulo)
    matriz[1, 0], matriz[1, 1] = np.sin(angulo), np.cos(angulo)
    matriz[:3, 3] = (x, y, z)
    return matriz


class _Construtor:
    def __init__(self) -> None:
        self.f = ifcopenshell.api.project.create_file(version="IFC4")
        self.projeto = ifcopenshell.api.root.create_entity(
            self.f, ifc_class="IfcProject", name="Escola Municipal Vila Exemplo (sintético)"
        )
        ifcopenshell.api.unit.assign_unit(self.f, length={"is_metric": True, "raw": "METERS"})
        modelo = ifcopenshell.api.context.add_context(self.f, context_type="Model")
        self.corpo = ifcopenshell.api.context.add_context(
            self.f,
            context_type="Model",
            context_identifier="Body",
            target_view="MODEL_VIEW",
            parent=modelo,
        )
        self.site = ifcopenshell.api.root.create_entity(self.f, ifc_class="IfcSite", name="Terreno")
        self.edificio = ifcopenshell.api.root.create_entity(
            self.f, ifc_class="IfcBuilding", name="Bloco escolar"
        )
        ifcopenshell.api.aggregate.assign_object(
            self.f, products=[self.site], relating_object=self.projeto
        )
        ifcopenshell.api.aggregate.assign_object(
            self.f, products=[self.edificio], relating_object=self.site
        )
        self.pavimentos = []
        for indice, nome in enumerate(("Térreo", "Pavimento superior")):
            pavimento = ifcopenshell.api.root.create_entity(
                self.f, ifc_class="IfcBuildingStorey", name=nome
            )
            pavimento.Elevation = indice * PE_DIREITO
            ifcopenshell.api.geometry.edit_object_placement(
                self.f, product=pavimento, matrix=_matriz(0, 0, indice * PE_DIREITO)
            )
            self.pavimentos.append(pavimento)
        ifcopenshell.api.aggregate.assign_object(
            self.f, products=self.pavimentos, relating_object=self.edificio
        )
        self.concreto = ifcopenshell.api.material.add_material(
            self.f, name="Concreto armado", category="concrete"
        )
        self.alvenaria = ifcopenshell.api.material.add_material(
            self.f, name="Alvenaria de bloco cerâmico", category="block"
        )
        self.contadores: dict[str, int] = {}

    def nome(self, prefixo: str) -> str:
        self.contadores[prefixo] = self.contadores.get(prefixo, 0) + 1
        return f"{prefixo}{self.contadores[prefixo]:02d}"

    def caixa(
        self,
        classe: str,
        nome: str,
        pavimento,
        x: float,
        y: float,
        z: float,
        comprimento: float,
        largura: float,
        altura: float,
        rotacao: float = 0.0,
        predefinido: str | None = None,
        conter: bool = True,
    ):
        elemento = ifcopenshell.api.root.create_entity(
            self.f, ifc_class=classe, name=nome, predefined_type=predefinido
        )
        representacao = ifcopenshell.api.geometry.add_wall_representation(
            self.f, context=self.corpo, length=comprimento, height=altura, thickness=largura
        )
        ifcopenshell.api.geometry.assign_representation(
            self.f, product=elemento, representation=representacao
        )
        ifcopenshell.api.geometry.edit_object_placement(
            self.f, product=elemento, matrix=_matriz(x, y, z, rotacao)
        )
        if conter and pavimento is not None:
            if classe == "IfcSpace":
                ifcopenshell.api.aggregate.assign_object(
                    self.f, products=[elemento], relating_object=pavimento
                )
            else:
                ifcopenshell.api.spatial.assign_container(
                    self.f, products=[elemento], relating_structure=pavimento
                )
        return elemento

    def pset(self, elemento, nome: str, propriedades: dict) -> None:
        pset = ifcopenshell.api.pset.add_pset(self.f, product=elemento, name=nome)
        ifcopenshell.api.pset.edit_pset(self.f, pset=pset, properties=propriedades)

    def material(self, elementos: list, material) -> None:
        ifcopenshell.api.material.assign_material(
            self.f, products=elementos, type="IfcMaterial", material=material
        )


def _paredes(c: _Construtor, pavimento, z: float, indice_pav: int) -> None:
    paredes = []
    externas = [
        (0, 0, COMPRIMENTO, 0),
        (COMPRIMENTO, 0, LARGURA, 90),
        (COMPRIMENTO, LARGURA, COMPRIMENTO, 180),
        (0, LARGURA, LARGURA, 270),
    ]
    for x, y, comprimento, rotacao in externas:
        parede = c.caixa(
            "IfcWall",
            c.nome("Parede PE"),
            pavimento,
            x,
            y,
            z,
            comprimento,
            ESPESSURA_PAREDE,
            PE_DIREITO,
            rotacao,
        )
        c.pset(parede, "Pset_WallCommon", {"IsExternal": True, "LoadBearing": False})
        paredes.append(parede)
    for y in CORREDOR:
        parede = c.caixa(
            "IfcWall", c.nome("Parede PI"), pavimento, 0, y, z, COMPRIMENTO, 0.15, PE_DIREITO
        )
        c.pset(parede, "Pset_WallCommon", {"IsExternal": False, "LoadBearing": False})
        paredes.append(parede)
    for modulo in range(1, 5):
        x = modulo * MODULO
        for y0, comprimento in ((0, CORREDOR[0]), (CORREDOR[1], LARGURA - CORREDOR[1])):
            if modulo == 4 and y0 == 0:
                continue  # vão da escada
            parede = c.caixa(
                "IfcWall",
                c.nome("Parede PI"),
                pavimento,
                x,
                y0,
                z,
                comprimento,
                0.15,
                PE_DIREITO,
                90,
            )
            c.pset(parede, "Pset_WallCommon", {"IsExternal": False, "LoadBearing": False})
            paredes.append(parede)
    c.material(paredes, c.alvenaria)


def _salas(c: _Construtor, pavimento, z: float, indice_pav: int) -> None:
    tipos = TIPOS_SALA_TERREO if indice_pav == 0 else TIPOS_SALA_SUPERIOR
    posicoes = [(m * MODULO, 0.0, CORREDOR[0]) for m in range(4)] + [
        (m * MODULO, CORREDOR[1], LARGURA - CORREDOR[1]) for m in range(4)
    ]
    for indice, ((x, y, profundidade), uso) in enumerate(zip(posicoes, tipos, strict=True)):
        codigo = f"S{indice_pav + 1}{indice + 1:02d}"
        sala = c.caixa(
            "IfcSpace",
            codigo,
            pavimento,
            x + 0.1,
            y + 0.1,
            z,
            MODULO - 0.2,
            profundidade - 0.2,
            0.05,
        )
        # Erro planejado: 2 ambientes do pavimento superior sem LongName.
        sala.LongName = None if (indice_pav == 1 and indice in (5, 6)) else uso
        c.pset(
            sala,
            "Pset_SpaceCommon",
            {
                "IsExternal": False,
                "GrossPlannedArea": round((MODULO - 0.2) * (profundidade - 0.2), 2),
            },
        )
        porta_x = x + MODULO / 2
        porta_y = CORREDOR[0] if y == 0 else CORREDOR[1]
        porta = c.caixa(
            "IfcDoor",
            c.nome("Porta P"),
            pavimento,
            porta_x,
            porta_y - 0.15,
            z,
            0.9,
            0.3,
            2.1,
            predefinido="DOOR",
        )
        numero = int(porta.Name.split("P")[-1])
        propriedades = {"IsExternal": False, "FireExit": False, "HandicapAccessible": True}
        # Erro planejado: 5 portas sem FireRating (P03, P07, P10, P13, P16).
        if numero not in (3, 7, 10, 13, 16):
            propriedades["FireRating"] = "EI 30"
        c.pset(porta, "Pset_DoorCommon", propriedades)
        janela_y = 0.0 if y == 0 else LARGURA
        for deslocamento in (2.0, 5.0):
            janela = c.caixa(
                "IfcWindow",
                c.nome("Janela J"),
                pavimento,
                x + deslocamento,
                janela_y - 0.15,
                z + 1.0,
                1.5,
                0.3,
                1.2,
                predefinido="WINDOW",
            )
            numero_janela = int(janela.Name.split("J")[-1])
            propriedades_janela = {"IsExternal": True}
            # Erro planejado: 4 janelas sem ThermalTransmittance (J04, J11, J19, J27).
            if numero_janela not in (4, 11, 19, 27):
                propriedades_janela["ThermalTransmittance"] = 5.7
            c.pset(janela, "Pset_WindowCommon", propriedades_janela)
    corredor = c.caixa(
        "IfcSpace",
        f"C{indice_pav + 1}",
        pavimento,
        0.1,
        CORREDOR[0] + 0.1,
        z,
        COMPRIMENTO - 0.2,
        1.8,
        0.05,
    )
    corredor.LongName = "Circulação"
    c.pset(corredor, "Pset_SpaceCommon", {"IsExternal": False})


def _estrutura(c: _Construtor, pavimento, z: float, indice_pav: int) -> None:
    pilares = []
    for x in np.arange(0, COMPRIMENTO + 0.1, MODULO):
        for y in (0.0, LARGURA - 0.3):
            pilares.append(
                c.caixa(
                    "IfcColumn",
                    c.nome("Pilar PL"),
                    pavimento,
                    float(x) - 0.15,
                    y,
                    z,
                    0.3,
                    0.3,
                    PE_DIREITO,
                    predefinido="COLUMN",
                )
            )
    vigas = []
    for y in (0.0, LARGURA - 0.2):
        for x in np.arange(0, COMPRIMENTO, 2 * MODULO):
            comprimento = min(2 * MODULO, COMPRIMENTO - float(x))
            vigas.append(
                c.caixa(
                    "IfcBeam",
                    c.nome("Viga V"),
                    pavimento,
                    float(x),
                    y,
                    z + PE_DIREITO - 0.5,
                    comprimento,
                    0.2,
                    0.5,
                    predefinido="BEAM",
                )
            )
    laje = c.caixa(
        "IfcSlab",
        c.nome("Laje L"),
        pavimento,
        0,
        0,
        z - 0.12,
        COMPRIMENTO,
        LARGURA,
        0.12,
        predefinido="FLOOR",
    )
    c.material([*pilares, *vigas, laje], c.concreto)


def _seguranca(c: _Construtor, pavimento, z: float, indice_pav: int) -> None:
    for x in (4.0, 14.0, 26.0, 36.0):
        extintor = c.caixa(
            "IfcFireSuppressionTerminal",
            c.nome("Extintor EX"),
            pavimento,
            x,
            CORREDOR[0] + 0.2,
            z + 1.2,
            0.2,
            0.2,
            0.5,
            predefinido="USERDEFINED",
        )
        extintor.ObjectType = "Extintor portátil"
    if indice_pav != 0:
        return
    for y, altura_espelho, nome in (
        (0.5, 0.175, "Escada principal"),
        (3.0, 0.19, "Escada de serviço"),
    ):
        escada = c.caixa(
            "IfcStair",
            nome,
            pavimento,
            33.5,
            y,
            z,
            5.0,
            1.4,
            PE_DIREITO,
            predefinido="STRAIGHT_RUN_STAIR",
        )
        # Erro planejado: a escada de serviço tem espelho de 0,19 m (acima de 0,18 m).
        c.pset(
            escada,
            "Pset_StairCommon",
            {"NumberOfRiser": 20, "RiserHeight": altura_espelho, "TreadLength": 0.28},
        )
        c.caixa(
            "IfcRailing",
            c.nome("Guarda-corpo GC"),
            pavimento,
            33.5,
            y + 1.45,
            z,
            5.0,
            0.05,
            1.1,
            predefinido="GUARDRAIL",
        )


def _sanitarios(c: _Construtor, pavimento, z: float) -> None:
    for x in (17.0, 19.0, 25.0, 27.0):
        c.caixa(
            "IfcSanitaryTerminal",
            c.nome("Bacia sanitária BS"),
            pavimento,
            x,
            LARGURA - 1.5,
            z,
            0.4,
            0.6,
            0.4,
            predefinido="TOILETPAN",
        )


def _problemas_de_saude(c: _Construtor, pavimento, z: float) -> None:
    # Erro planejado: 3 objetos genéricos (IfcBuildingElementProxy) e 1 elemento sem pavimento.
    for x in (2.0, 10.0, 18.0):
        c.caixa(
            "IfcBuildingElementProxy",
            c.nome("Mobiliário genérico MG"),
            pavimento,
            x,
            2.0,
            z,
            1.2,
            0.6,
            0.75,
        )
    c.caixa(
        "IfcBuildingElementProxy",
        "Objeto solto (sem pavimento)",
        None,
        20.0,
        20.0,
        0.0,
        1.0,
        1.0,
        1.0,
        conter=False,
    )


def gerar(destino: Path) -> Path:
    c = _Construtor()
    for indice, pavimento in enumerate(c.pavimentos):
        z = indice * PE_DIREITO
        _paredes(c, pavimento, z, indice)
        _salas(c, pavimento, z, indice)
        _estrutura(c, pavimento, z, indice)
        _seguranca(c, pavimento, z, indice)
    cobertura = c.caixa(
        "IfcSlab",
        "Laje de cobertura",
        c.pavimentos[1],
        0,
        0,
        2 * PE_DIREITO,
        COMPRIMENTO,
        LARGURA,
        0.12,
        predefinido="ROOF",
    )
    c.material([cobertura], c.concreto)
    _sanitarios(c, c.pavimentos[0], 0.0)
    _problemas_de_saude(c, c.pavimentos[0], 0.0)
    destino.parent.mkdir(parents=True, exist_ok=True)
    c.f.write(str(destino))
    return destino
