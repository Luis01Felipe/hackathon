from editalcheck.domain import topics, vagueness
from editalcheck.domain.models import Edital, Pagina, TermoVago

EDITAL = Edital(
    "e.pdf",
    (
        Pagina(
            1,
            "PREFEITURA DE EXEMPLO\nEdital de concorrência para projeto.\n1 DO OBJETO\n1.1.1 O objeto é o projeto da escola.\n2 DOS PRAZOS\n2.1.1 O prazo será de 120 dias corridos.\n",
        ),
        Pagina(
            2,
            "3 DA MODELAGEM BIM\n3.1 Portas\n3.1.1 As portas deverão conter a propriedade FireRating.\n"
            "3.1.2 Os materiais deverão ser adequados, conforme normas vigentes.\n"
            "1. item de lista que não é título\n3.2 Paredes\n3.2.1 As paredes deverão informar IsExternal.\n",
        ),
    ),
)
TERMOS = [
    TermoVago("adequados", "qualidade"),
    TermoVago("conforme normas vigentes", "norma"),
    TermoVago("normas vigentes", "norma"),
]


def test_segmentar_por_numeracao_e_titulos() -> None:
    resultado = topics.segmentar(EDITAL)
    assert [(t.numero, t.titulo) for t in resultado] == [
        ("0", "Preâmbulo"),
        ("1", "DO OBJETO"),
        ("2", "DOS PRAZOS"),
        ("3", "DA MODELAGEM BIM"),
        ("3.1", "Portas"),
        ("3.2", "Paredes"),
    ]
    portas = resultado[4]
    assert portas.pagina_inicio == 2 and portas.texto.startswith("[p. 2]")
    assert "1. item de lista" in portas.texto


def test_secao_sem_texto_proprio_vira_agrupador_pai_dos_subtopicos() -> None:
    por_numero = {t.numero: t for t in topics.segmentar(EDITAL)}
    secao = por_numero["3"]
    assert secao.agrupador and secao.nivel == 1 and secao.pai_id is None
    assert por_numero["3.1"].pai_id == secao.id
    assert por_numero["3.2"].pai_id == secao.id
    assert por_numero["2"].pai_id is None and not por_numero["2"].agrupador
    assert secao.relevante_bim  # herdada dos subtópicos


def test_subtopico_sem_titulo_de_secao_cria_agrupador_implicito() -> None:
    edital = Edital(
        "e.pdf",
        (
            Pagina(
                1,
                "1 DO OBJETO\n1.1.1 O objeto é o projeto da escola municipal.\n"
                "2.1 Prazos de entrega\n2.1.1 O prazo será de 30 dias corridos.\n"
                "2.2 Pagamento\n2.2.1 O pagamento será mensal após o aceite.\n",
            ),
        ),
    )
    resultado = topics.segmentar(edital)
    assert [(t.numero, t.titulo, t.agrupador) for t in resultado] == [
        ("1", "DO OBJETO", False),
        ("2", "Seção 2", True),
        ("2.1", "Prazos de entrega", False),
        ("2.2", "Pagamento", False),
    ]
    assert resultado[2].pai_id == resultado[1].id == resultado[3].pai_id
    assert resultado[1].pagina_inicio == 1 and resultado[1].texto == ""


def test_anexo_reinicia_a_numeracao_e_agrupa_os_titulos() -> None:
    edital = Edital(
        "e.pdf",
        (
            Pagina(1, "1 DO OBJETO\n1.1.1 O objeto é o projeto da escola municipal.\n"),
            Pagina(
                2,
                "ANEXO I – TERMO DE REFERÊNCIA\n1 – DO MODELO BIM\n1.1 Portas\n"
                "1.1.1 As portas deverão ter FireRating.\n2: DA ENTREGA\n"
                "2.1.1 O modelo será entregue em IFC 4 com arquivos nativos.\n",
            ),
        ),
    )
    resultado = topics.segmentar(edital)
    assert [(t.numero, t.nivel) for t in resultado] == [
        ("1", 1),
        ("Anexo I", 1),
        ("1", 2),
        ("1.1", 3),
        ("2", 2),
    ]
    anexo = resultado[1]
    assert anexo.titulo == "TERMO DE REFERÊNCIA" and anexo.agrupador
    assert resultado[2].pai_id == anexo.id and resultado[4].pai_id == anexo.id
    assert resultado[3].pai_id == resultado[2].id


def test_expandir_selecao_troca_agrupador_pelos_subtopicos() -> None:
    segmentados = topics.segmentar(EDITAL)
    por_numero = {t.numero: t for t in segmentados}
    escolhidos = topics.expandir_selecao(segmentados, [por_numero["3"].id, por_numero["3.1"].id])
    assert [t.numero for t in escolhidos] == ["3.1", "3.2"]
    assert topics.expandir_selecao(segmentados, ["inexistente"]) == []


def test_relevancia_bim() -> None:
    por_numero = {t.numero: t for t in topics.segmentar(EDITAL)}
    assert por_numero["3.1"].relevante_bim
    assert not por_numero["2"].relevante_bim


def test_sem_titulos_vira_um_topico_por_pagina() -> None:
    edital = Edital(
        "e.pdf", (Pagina(1, "texto corrido sem títulos numerados"), Pagina(2, "outro texto"))
    )
    assert [t.titulo for t in topics.segmentar(edital)] == ["Página 1", "Página 2"]


def test_edital_dos_topicos_preserva_paginas() -> None:
    selecionados = [t for t in topics.segmentar(EDITAL) if t.numero == "3.2"]
    reduzido = topics.edital_dos_topicos(EDITAL, selecionados)
    assert [p.numero for p in reduzido.paginas] == [2]
    assert "IsExternal" in reduzido.paginas[0].texto
    assert "FireRating" not in reduzido.paginas[0].texto


def test_termos_vagos_detectados_com_clausula_e_topico() -> None:
    resultado = vagueness.detectar(EDITAL, TERMOS, topics.segmentar(EDITAL))
    assert len(resultado) == 1
    trecho = resultado[0]
    assert trecho.pagina == 2
    assert trecho.clausula == "3.1.2"
    assert trecho.termo == "adequados; conforme normas vigentes"  # "normas vigentes" está contido
    assert trecho.trecho.startswith("3.1.2 Os materiais")


def test_termos_vagos_filtrados_por_topico() -> None:
    segmentados = topics.segmentar(EDITAL)
    paredes = [t.id for t in segmentados if t.numero == "3.2"]
    assert vagueness.detectar(EDITAL, TERMOS, segmentados, paredes) == []


def test_termo_vago_ignora_acentos_e_respeita_limite_de_palavra() -> None:
    edital = Edital("e.pdf", (Pagina(1, "A solução será inadequada. A iluminação será ADEQUADA."),))
    resultado = vagueness.detectar(edital, [TermoVago("adequada", "q")])
    assert [r.trecho for r in resultado] == ["A iluminação será ADEQUADA."]
