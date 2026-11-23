"""Regras novas da v2: lições aprendidas, marcos, versão IFC, origem, decisões e duplicidade."""

import pytest

from editalcheck.domain import duplicidade, findings, licoes, marcos, severity, versao_ifc
from editalcheck.domain.models import (
    AmbiguidadeConfirmada,
    CaixaEnvolvente,
    ClasseModelo,
    DecisaoApontamento,
    Edital,
    ElementoModelo,
    Evidencia,
    FonteEvidencia,
    ModeloResumo,
    OrigemInconsistencia,
    Pagina,
    SaudeModelo,
    StatusDecisao,
    TipoApontamento,
    Topico,
    TrechoVago,
)

EDITAL = Edital(
    arquivo="edital.pdf",
    paginas=(
        Pagina(
            1,
            "4.1.1 O modelo deverá ser entregue no formato aberto IFC 4.\n"
            "4.1.2 As entregas ocorrerão em três marcos: estudo preliminar, anteprojeto e "
            "projeto executivo.\n"
            "5.1.1 Todas as portas deverão conter a propriedade FireRating do Pset_DoorCommon.\n"
            "5.3.2 As janelas deverão garantir iluminação natural adequada aos ambientes.\n",
        ),
    ),
)
LICOES = Edital(
    arquivo="licoes.txt",
    paginas=(
        Pagina(
            1,
            "LIÇÕES APRENDIDAS\nDocumento de exemplo.\n\n"
            "1. Salas de baterias não podem ter janelas nem iluminação natural. Houve retrabalho.\n\n"
            "2. Todas as portas deverão conter a propriedade FireRating do Pset_DoorCommon.\n\n"
            "- A casa de bombas deve ter acesso independente pela área externa.\n",
        ),
    ),
)


def _modelo() -> ModeloResumo:
    elementos = (
        ElementoModelo("ESPACO", 1, "IfcSpace", "S106", "T", "Sala de baterias"),
        ElementoModelo("AULA", 2, "IfcSpace", "S101", "T", "Sala de aula 01"),
        ElementoModelo("JANELA", 3, "IfcWindow", "Janela J11", "T"),
    )
    return ModeloResumo(
        arquivo="m.ifc",
        schema="IFC4",
        classes=(ClasseModelo("IfcSpace", 2, True),),
        elementos=elementos,
        saude=SaudeModelo(schema="IFC4", total_elementos=1, proxies=0),
    )


def test_licoes_por_regras_ignora_cabecalho_e_cita_trecho_literal() -> None:
    lidas = licoes.licoes_por_regras(LICOES)
    assert [licao.id for licao in lidas] == ["LIC-01", "LIC-02", "LIC-03"]
    assert lidas[0].evidencia.fonte == FonteEvidencia.LICOES
    assert lidas[0].evidencia.trecho.startswith("Salas de baterias não podem ter janelas")
    assert lidas[0].termos_elemento == ("baterias",)
    assert lidas[2].termos_elemento == ("bombas",)


def test_licao_explicita_e_licao_ausente_com_clausula_relacionada() -> None:
    baterias, portas, _ = licoes.licoes_por_regras(LICOES)
    explicita = licoes.verificar_por_regras(portas, EDITAL)
    assert explicita.explicita and explicita.evidencia is not None
    ausente = licoes.verificar_por_regras(baterias, EDITAL)
    assert not ausente.explicita
    assert ausente.trecho_relacionado is not None
    assert "iluminação natural" in ausente.trecho_relacionado.trecho
    assert ausente.redacao_sugerida.startswith("Salas de baterias")


def test_elementos_candidatos_e_janelas_no_ambiente() -> None:
    baterias = licoes.licoes_por_regras(LICOES)[0]
    assert licoes.elementos_candidatos(baterias, _modelo()) == ("ESPACO",)
    assert licoes.classes_proibidas(baterias) == ("IfcWindow",)
    sala = CaixaEnvolvente((0.0, 0.0, 0.0), (5.0, 4.0, 0.05))  # ambiente modelado como placa
    janela = CaixaEnvolvente((1.0, 3.85, 1.0), (2.5, 4.15, 2.2))
    longe = CaixaEnvolvente((20.0, 20.0, 1.0), (21.0, 21.0, 2.0))
    assert licoes.elementos_no_ambiente(sala, {"J1": janela, "J2": longe}) == ["J1"]


def test_licao_ausente_vira_apontamento_alto_ao_contratante() -> None:
    baterias = licoes.licoes_por_regras(LICOES)[0]
    verificacao = licoes.verificar_por_regras(baterias, EDITAL)
    [apontamento] = findings.de_licoes(
        [baterias], [verificacao], {baterias.id: ("ESPACO",)}, {baterias.id: ("JANELA",)}
    )
    assert apontamento.tipo == TipoApontamento.LICAO_NAO_EXPLICITA
    assert apontamento.origem == OrigemInconsistencia.EDITAL
    assert apontamento.severidade == severity.Severidade.ALTA
    assert apontamento.elementos == ("ESPACO", "JANELA")
    assert "repete o erro" in apontamento.detalhe
    assert {e.fonte for e in apontamento.evidencias_edital} == {
        FonteEvidencia.EDITAL,
        FonteEvidencia.LICOES,
    }


def test_marcos_e_versao_ifc_citada() -> None:
    nomes = [m.nome for m in marcos.detectar(EDITAL)]
    assert nomes == ["Estudo preliminar", "Anteprojeto", "Projeto executivo"]
    assert marcos.novo_id(marcos.detectar(EDITAL)) == "MAR-04"
    assert versao_ifc.exigida(EDITAL) == (
        "IFC4",
        Evidencia(1, versao_ifc.exigida(EDITAL)[1].trecho),
    )
    assert versao_ifc.canonica("IFC4X3_ADD2") == "IFC4X3_ADD2"
    assert versao_ifc.canonica("IFC2X3") == "IFC2X3"
    [apontamento] = findings.de_versao_exigida("IFC2X3", versao_ifc.exigida(EDITAL), "IFC2X3")
    assert apontamento.origem == OrigemInconsistencia.MODELO
    assert findings.de_versao_exigida("IFC4", versao_ifc.exigida(EDITAL), "IFC4") == []


def test_origem_cobre_todos_os_tipos() -> None:
    for tipo in TipoApontamento:
        esperado = (
            OrigemInconsistencia.MODELO
            if tipo in (TipoApontamento.NAO_CONFORMIDADE, TipoApontamento.QUALIDADE_MODELO)
            else OrigemInconsistencia.EDITAL
        )
        assert severity.origem(tipo) == esperado


def test_decisao_rejeitar_ou_dispensar_exige_justificativa() -> None:
    with pytest.raises(ValueError):
        DecisaoApontamento("APT-001", StatusDecisao.DISPENSADO, comentario="  ")
    with pytest.raises(ValueError):
        DecisaoApontamento("APT-001", StatusDecisao.REJEITADO)
    assert DecisaoApontamento("APT-001", StatusDecisao.ACEITO).status == StatusDecisao.ACEITO


def test_ambiguidades_do_mesmo_termo_e_topico_sao_agrupadas() -> None:
    def confirmada(trecho: str, pagina: int) -> AmbiguidadeConfirmada:
        vago = TrechoVago(pagina, trecho, "adequado", "subjetivo", topico_id="TOP-05")
        return AmbiguidadeConfirmada(vago, True)

    agrupadas = findings.de_ambiguidades(
        [confirmada("A sala será adequada.", 1), confirmada("O piso será adequado.", 2)], []
    )
    assert len(agrupadas) == 1
    assert len(agrupadas[0].evidencias_edital) == 2
    assert "2 ocorrências" in agrupadas[0].titulo


def test_texto_repetido_e_valores_diferentes() -> None:
    def topico(id_: str, texto: str) -> Topico:
        return Topico(id_, id_, id_, 2, 1, 1, f"[p. 1]\n{texto}")

    frase = "O pé-direito mínimo das salas de aula deverá ser de 2,80 m em todos os pavimentos."
    pares = duplicidade.encontrar([topico("A", frase), topico("B", frase)])
    assert len(pares) == 1 and not pares[0].valores_diferentes
    diferente = frase.replace("2,80", "3,00")
    pares = duplicidade.encontrar([topico("A", frase), topico("B", diferente)])
    assert len(pares) == 1 and pares[0].valores_diferentes
    [apontamento] = findings.de_duplicidades(pares)
    assert apontamento.tipo == TipoApontamento.CONTRADICAO


def test_tabela_e_lista_nao_viram_contradicao() -> None:
    """Linhas de planilha e prazos por etapa repetem o texto trocando só o número."""

    def topico(id_: str, texto: str) -> Topico:
        return Topico(id_, id_, id_, 2, 1, 1, f"[p. 1]\n{texto}")

    linhas = [
        f"O item {i} da planilha orçamentária deverá ser entregue em {i + 5} dias corridos."
        for i in range(1, 30)
    ]
    topicos = [topico(f"T{i}", linha) for i, linha in enumerate(linhas)]
    assert duplicidade.encontrar(topicos) == []


def test_duplicidades_limitadas_e_cada_frase_em_um_par() -> None:
    def topico(id_: str, texto: str) -> Topico:
        return Topico(id_, id_, id_, 2, 1, 1, f"[p. 1]\n{texto}")

    temas = [
        "pé-direito mínimo das salas de aula",
        "largura livre das portas de saída de emergência",
        "espessura mínima das lajes de cobertura",
        "resistência ao fogo das paredes corta-fogo",
        "altura dos guarda-corpos das escadas",
        "área mínima dos sanitários acessíveis",
        "iluminância média das salas administrativas",
        "vazão mínima dos chuveiros automáticos",
        "nível de ruído máximo das casas de máquinas",
        "inclinação máxima das rampas acessíveis",
        "distância máxima a percorrer até a saída",
        "taxa de renovação de ar das salas técnicas",
        "carga acidental das áreas de arquivo",
        "espessura do revestimento das fachadas ventiladas",
        "dimensão mínima das vagas de estacionamento",
        "largura mínima dos corredores de circulação",
        "altura livre sob as vigas de transição",
        "temperatura de conforto das salas de reunião",
        "potência instalada dos quadros de distribuição",
        "capacidade do reservatório de água potável",
        "cobrimento mínimo das armaduras de fundação",
        "tempo de autonomia da iluminação de emergência",
    ]
    topicos = []
    for i, tema in enumerate(temas):
        frase = f"O valor exigido para a {tema} do edifício principal deverá ser de {i + 2},5 m."
        topicos += [topico(f"A{i}", frase), topico(f"B{i}", frase)]
    pares = duplicidade.encontrar(topicos)
    assert len(pares) == duplicidade.MAX_PARES
    assert all(par.similaridade >= duplicidade.LIMITE_DUPLICIDADE for par in pares)
