"""Regras puras: cobertura, severidade, checklist, vocabulário, apontamentos e indicadores."""

from dataclasses import replace

from editalcheck.domain import checklist, coverage, findings, indicators
from editalcheck.domain import severity as sev
from editalcheck.domain.checklist import RegraChecklist
from editalcheck.domain.models import (
    Cardinalidade,
    ClasseModelo,
    ContextoVocabulario,
    Destinatario,
    Edital,
    ElementoModelo,
    EstadoElemento,
    Evidencia,
    FalhaElemento,
    ItemChecklist,
    ModeloResumo,
    OrigemVocabulario,
    Pagina,
    PropriedadeOficial,
    Referencia,
    Requisito,
    ResultadoChecklist,
    ResultadoEspecificacao,
    SaudeModelo,
    Severidade,
    StatusChecklist,
    StatusRequisito,
    TermoDicionario,
    TipoApontamento,
    TipoFaceta,
)
from editalcheck.domain.vocabulary import classificar_origem, filtrar_referencias

PORTA = ClasseModelo("IfcDoor", 12, True, ("IfcBuildingElement", "IfcElement"))
PILAR = ClasseModelo("IfcColumn", 4, True, ("IfcBuildingElement", "IfcElement"))
PROXY = ClasseModelo("IfcBuildingElementProxy", 3, False)


def requisito(**campos) -> Requisito:
    base = dict(
        id="REQ-001",
        topico_id="TOP-01",
        descricao="Portas com FireRating",
        evidencia=Evidencia(4, "Todas as portas deverão conter FireRating."),
        verificavel_por_ids=True,
        ifc_class="IfcDoor",
        faceta=TipoFaceta.PROPRIEDADE,
        pset="Pset_DoorCommon",
        propriedade="FireRating",
        tipo_dado="IfcLabel",
        status=StatusRequisito.APROVADO,
        clausula="5.1.1",
    )
    base.update(campos)
    return Requisito(**base)


# ------------------------------------------------------------------ cobertura


def test_cobertura_conta_so_classes_especificaveis_e_requisitos_aprovados() -> None:
    resultado = coverage.calcular(
        [PORTA, PILAR, PROXY],
        [
            requisito(),
            requisito(id="REQ-002", ifc_class="IfcColumn", status=StatusRequisito.REJEITADO),
        ],
    )
    assert resultado.percentual == 50.0
    assert [c.classe for c in resultado.lacunas] == ["IfcColumn"]


def test_requisito_em_supertipo_cobre_subtipos() -> None:
    resultado = coverage.calcular([PORTA, PILAR], [requisito(ifc_class="IfcBuildingElement")])
    assert resultado.percentual == 100.0


def test_cobertura_sem_classes_especificaveis() -> None:
    assert coverage.calcular([PROXY], []).percentual is None


def test_sugestao_prefere_pset_common_e_prioridade() -> None:
    oficiais = [
        PropriedadeOficial("Pset_ManufacturerTypeInformation", "Manufacturer"),
        PropriedadeOficial("Pset_ColumnCommon", "Reference"),
        PropriedadeOficial("Pset_ColumnCommon", "LoadBearing"),
        PropriedadeOficial("Pset_ColumnCommon", "FireRating"),
    ]
    sugeridas = coverage.sugerir_propriedades("IfcColumn", oficiais, limite=2)
    assert [(s.pset, s.nome) for s in sugeridas] == [
        ("Pset_ColumnCommon", "FireRating"),
        ("Pset_ColumnCommon", "LoadBearing"),
    ]


# ------------------------------------------------------------------ severidade


def test_matriz_de_severidade() -> None:
    config = sev.ConfigSeveridade()
    assert sev.nao_conformidade(Cardinalidade.OBRIGATORIA) == Severidade.ALTA
    assert sev.nao_conformidade(Cardinalidade.OPCIONAL) == Severidade.MEDIA
    assert sev.lacuna_cobertura("IfcColumn", 10, config) == Severidade.ALTA
    assert sev.lacuna_cobertura("IfcDoor", 1, config) == Severidade.ALTA  # segurança
    assert sev.lacuna_cobertura("IfcSlab", 3, config) == Severidade.MEDIA
    assert sev.item_ausente(True) == Severidade.ALTA
    assert sev.item_ausente(False) == Severidade.MEDIA
    assert sev.ambiguidade(True) == Severidade.MEDIA
    assert sev.ambiguidade(False) == Severidade.BAIXA
    assert sev.nao_verificavel() == Severidade.BAIXA
    assert sev.qualidade_modelo(0.25, False, config) == Severidade.ALTA
    assert sev.qualidade_modelo(0.05, True, config) == Severidade.ALTA
    assert sev.qualidade_modelo(0.05, False, config) == Severidade.MEDIA
    assert sev.destinatario(TipoApontamento.NAO_CONFORMIDADE) == Destinatario.PROJETISTA
    assert sev.destinatario(TipoApontamento.LACUNA_COBERTURA) == Destinatario.CONTRATANTE


# ------------------------------------------------------------------ checklist


EDITAL_CHK = Edital(
    "e.pdf",
    (Pagina(1, "4.1.1 O modelo deverá ser entregue em IFC 4. 4.1.2 Haverá nomenclatura própria."),),
)
ITENS = [
    ItemChecklist("CHK-01", "Formato IFC", True, palavras_chave=("ifc",)),
    ItemChecklist("CHK-04", "Nomenclatura", False, palavras_chave=("nomenclatura",)),
    ItemChecklist("CHK-08", "Coordenadas", False, palavras_chave=("coordenadas",)),
]
REGRAS = [RegraChecklist("CHK-01", (r"\bifc\s*4\b",), ("ifc",))]


def test_checklist_por_regras() -> None:
    resultado = checklist.avaliar_por_regras(EDITAL_CHK, ITENS, REGRAS)
    assert [r.status for r in resultado] == [
        StatusChecklist.PRESENTE,
        StatusChecklist.PARCIAL,
        StatusChecklist.AUSENTE,
    ]
    assert resultado[0].evidencia and resultado[0].evidencia.pagina == 1


def test_salvaguarda_rebaixa_resposta_sem_evidencia_conferida() -> None:
    respostas = [
        ResultadoChecklist(
            "CHK-01", StatusChecklist.PRESENTE, Evidencia(1, "deverá ser entregue em IFC 4")
        ),
        ResultadoChecklist(
            "CHK-04", StatusChecklist.PARCIAL, Evidencia(1, "trecho que o LLM inventou aqui")
        ),
        ResultadoChecklist("CHK-08", StatusChecklist.PRESENTE, None),
    ]
    conferidas = checklist.aplicar_salvaguarda(respostas, EDITAL_CHK)
    assert [c.status for c in conferidas] == [
        StatusChecklist.PRESENTE,
        StatusChecklist.AUSENTE,
        StatusChecklist.AUSENTE,
    ]


def test_completar_garante_um_resultado_por_item() -> None:
    completos = checklist.completar([ResultadoChecklist("CHK-04", StatusChecklist.PARCIAL)], ITENS)
    assert [c.item_id for c in completos] == ["CHK-01", "CHK-04", "CHK-08"]
    assert completos[0].status == StatusChecklist.AUSENTE


# ------------------------------------------------------------------ vocabulário (S4 e S5)


CONTEXTO = ContextoVocabulario(
    schema="IFC4",
    classes_modelo=(PORTA,),
    propriedades_oficiais=(PropriedadeOficial("Pset_DoorCommon", "FireRating", "IfcLabel"),),
    termos_bsdd=(TermoDicionario("AcousticRatingBR", "https://bsdd/x", "propriedade"),),
)


def test_origem_do_vocabulario() -> None:
    origem, uri, aviso = classificar_origem(requisito(), CONTEXTO)
    assert origem == OrigemVocabulario.PSET_OFICIAL and uri and uri.endswith("/prop/FireRating")
    assert aviso is None
    origem, uri, _ = classificar_origem(
        requisito(pset="Pset_X", propriedade="AcousticRatingBR"), CONTEXTO
    )
    assert origem == OrigemVocabulario.BSDD and uri == "https://bsdd/x"
    origem, _, aviso = classificar_origem(
        requisito(pset="Pset_X", propriedade="Inventada"), CONTEXTO
    )
    assert origem == OrigemVocabulario.CUSTOMIZADO and aviso


def test_lista_fechada_de_referencias() -> None:
    permitidas = [Referencia("clausula_edital", "Edital, item 5.1.1, p. 4")]
    citadas = [
        Referencia("citada", "Edital, item 5.1.1, p. 4"),
        Referencia("citada", "NBR 9077:2001"),
    ]
    mantidas, removida = filtrar_referencias(citadas, permitidas)
    assert mantidas == tuple(permitidas) and removida


# ------------------------------------------------------------------ apontamentos e indicadores


def test_nao_conformidade_e_indicadores() -> None:
    resultado = ResultadoEspecificacao(
        nome_especificacao="REQ-001 · Portas",
        requisito_id="REQ-001",
        status=False,
        aplicaveis=3,
        aprovados=2,
        falhas=(
            FalhaElemento("G3", 30, "IfcDoor", "P03", "O Pset não contém a propriedade exigida"),
        ),
        elementos_aprovados=("G1", "G2"),
    )
    apontamentos = findings.de_resultados_ids([resultado], [requisito()])
    assert len(apontamentos) == 1
    apontamento = apontamentos[0]
    assert apontamento.severidade == Severidade.ALTA
    assert apontamento.elementos == ("G3",)
    assert apontamento.referencias[0].rotulo == "Edital, item 5.1.1, p. 4"
    assert "1 de 3 IfcDoor" in apontamento.titulo

    estados = indicators.estado_elementos([resultado])
    assert estados == {
        "G1": EstadoElemento.CONFORME,
        "G2": EstadoElemento.CONFORME,
        "G3": EstadoElemento.NAO_CONFORME,
    }
    painel = indicators.calcular([resultado], None, [], [requisito()], apontamentos)
    assert painel.conformidade_percentual == 0.0
    assert painel.elementos_nao_conformes == 1
    assert painel.apontamentos_por_severidade == {"alta": 1}


def test_requisito_opcional_gera_severidade_media() -> None:
    resultado = ResultadoEspecificacao(
        "REQ-001", "REQ-001", False, 1, 0, (FalhaElemento("G", 1, "IfcDoor", None, "x"),)
    )
    apontamento = findings.de_resultados_ids(
        [resultado], [requisito(cardinalidade=Cardinalidade.OPCIONAL)]
    )[0]
    assert apontamento.severidade == Severidade.MEDIA


def test_saude_do_modelo() -> None:
    elementos = tuple(ElementoModelo(f"G{i}", i, "IfcWall") for i in range(7)) + tuple(
        ElementoModelo(f"P{i}", 100 + i, "IfcBuildingElementProxy") for i in range(3)
    )
    modelo = ModeloResumo(
        "m.ifc",
        "IFC4",
        (),
        elementos,
        SaudeModelo("IFC4", 10, 3, sem_pavimento=("G1",), guids_duplicados=(), espacos=0),
    )
    apontamentos = findings.de_saude(modelo, sev.ConfigSeveridade())
    titulos = {a.titulo: a.severidade for a in apontamentos}
    assert titulos["30% dos elementos são IfcBuildingElementProxy (3 de 10)"] == Severidade.ALTA
    assert "Modelo sem ambientes (IfcSpace)" in titulos
    assert any("sem pavimento" in t for t in titulos)


def test_numerar_ordena_por_severidade() -> None:
    baixa = replace(findings.de_nao_verificaveis([requisito(verificavel_por_ids=False)])[0])
    alta = findings.de_saude(
        ModeloResumo(
            "m", "IFC4", (), (), SaudeModelo("IFC4", 1, 0, guids_duplicados=("X",), espacos=1)
        ),
        sev.ConfigSeveridade(),
    )[0]
    numerados = findings.numerar([baixa, alta])
    assert [(a.id, a.severidade) for a in numerados] == [
        ("APT-001", Severidade.ALTA),
        ("APT-002", Severidade.BAIXA),
    ]
