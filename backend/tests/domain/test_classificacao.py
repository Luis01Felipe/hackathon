"""Classificação determinística dos requisitos de informação (IR)."""

from editalcheck.domain.classificacao import (
    classificar,
    classificar_item,
    limpar_ambientes,
    nivel_ids,
    sugerir_ambientes,
    tipo_verificacao_padrao,
    verificacao_coerente,
)
from editalcheck.domain.models import (
    Evidencia,
    ItemChecagem,
    Requisito,
    TipoFaceta,
    TipoVerificacao,
)


def requisito(**campos) -> Requisito:
    base = dict(
        id="REQ-001",
        topico_id="TOP-01",
        descricao="Portas corta-fogo com FireRating",
        evidencia=Evidencia(4, "As portas da sala de baterias deverão ser corta-fogo."),
        verificavel_por_ids=True,
        ifc_class="IfcDoor",
        faceta=TipoFaceta.PROPRIEDADE,
        pset="Pset_DoorCommon",
        propriedade="FireRating",
    )
    base.update(campos)
    return Requisito(**base)


def test_item_de_checagem_pelas_palavras_chave() -> None:
    assert classificar_item("Pé-direito mínimo de 3,50 m nas plataformas") == ItemChecagem.DIME
    assert classificar_item("Iluminação de emergência com 300 lux") == ItemChecagem.ILUM
    assert classificar_item("Rotas de fuga conforme NFPA 130") == ItemChecagem.INCE
    assert classificar_item("Texto sem assunto reconhecível") is None


def test_classe_ifc_pesa_na_classificacao() -> None:
    assert classificar_item("Informe o código do fabricante", "IfcDoor") == ItemChecagem.ACAB
    assert classificar_item("Informe o código do fabricante", "IfcSlab") == ItemChecagem.ESTR


def test_tipo_de_verificacao_padrao_e_nivel_ids() -> None:
    assert tipo_verificacao_padrao(requisito()) == TipoVerificacao.IDS
    geometrico = requisito(
        verificavel_por_ids=False, motivo_nao_verificavel="Folga entre elementos é geométrica."
    )
    assert tipo_verificacao_padrao(geometrico) == TipoVerificacao.SCRIPT
    documental = requisito(
        verificavel_por_ids=False, motivo_nao_verificavel="Conformidade com norma."
    )
    assert tipo_verificacao_padrao(documental) == TipoVerificacao.MANUAL
    assert [nivel_ids(t) for t in TipoVerificacao] == ["Sim", "Parcial", "Não", "Não"]


def test_verificacao_acompanha_a_salvaguarda_s3() -> None:
    rebaixado = requisito(verificavel_por_ids=False, verificacao=TipoVerificacao.IDS_SCRIPT)
    assert verificacao_coerente(rebaixado) == TipoVerificacao.MANUAL
    parcial = requisito(verificacao=TipoVerificacao.IDS_SCRIPT)
    assert verificacao_coerente(parcial) == TipoVerificacao.IDS_SCRIPT


def test_ambientes_do_modelo_tem_preferencia() -> None:
    texto = "Na sala de BATERIAS e nas plataformas o piso será antiderrapante."
    assert sugerir_ambientes(texto, ("Sala de Baterias", "Hall")) == ("Sala de Baterias",)


def test_ambientes_sem_modelo_pelo_texto() -> None:
    texto = "A sala de baterias deverá ter exaustão. As plataformas terão piso tátil."
    assert sugerir_ambientes(texto) == ("Sala de baterias", "Plataformas")
    assert sugerir_ambientes("Sala de média tensão com piso elevado.") == ("Sala de média tensão",)
    assert sugerir_ambientes("Nenhum espaço citado.") == ()


def test_limpar_ambientes_remove_repetidos_e_vazios() -> None:
    assert limpar_ambientes(["Hall", " hall ", "", "Plataformas"]) == ("Hall", "Plataformas")


def test_classificar_completa_sem_sobrescrever() -> None:
    classificado = classificar(requisito())
    assert classificado.item_checagem == ItemChecagem.INCE
    assert classificado.verificacao == TipoVerificacao.IDS
    assert classificado.ambientes == ("Sala de baterias",)

    escolhido = classificar(requisito(item_checagem=ItemChecagem.ACAB, ambientes=("Hall",)))
    assert escolhido.item_checagem == ItemChecagem.ACAB
    assert escolhido.ambientes == ("Hall",)


def test_classificar_usa_o_contexto_quando_o_trecho_nao_cita_ambiente() -> None:
    sem_ambiente = requisito(
        evidencia=Evidencia(4, "Todas as portas terão FireRating."), descricao="Portas"
    )
    assert classificar(sem_ambiente, contexto="4.2 Plataformas").ambientes == ("Plataformas",)
