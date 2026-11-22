from editalcheck.domain.evidence import (
    clausula_do_trecho,
    conferir_evidencia,
    normalizar,
    trecho_confere,
)
from editalcheck.domain.models import Edital, Evidencia, Pagina

PAGINA = """5.1 Portas
5.1.1 Todas as portas deverão conter a propriedade FireRating do
Pset_DoorCommon, com a resis-
tência ao fogo da porta.
5.1.2 Todas as portas deverão indicar se fazem parte de rota de fuga."""


def test_normalizar_trata_espacos_hifenizacao_e_caixa() -> None:
    assert normalizar("A  RESIS-\ntência\n ao   Fogo") == "a resistência ao fogo"


def test_normalizar_unifica_aspas_tipograficas() -> None:
    assert normalizar("“Sala de aula 01”") == '"sala de aula 01"'


def test_trecho_literal_confere_com_quebra_de_linha() -> None:
    assert trecho_confere(
        "deverão conter a propriedade FireRating do Pset_DoorCommon, com a resistência ao fogo",
        PAGINA,
    )


def test_trecho_parafraseado_nao_confere() -> None:
    assert not trecho_confere("As portas precisam ter resistência ao fogo informada.", PAGINA)


def test_trecho_com_reticencias_exige_segmentos_na_ordem() -> None:
    assert trecho_confere("Todas as portas deverão conter ... resistência ao fogo da porta", PAGINA)
    assert not trecho_confere(
        "resistência ao fogo da porta ... Todas as portas deverão conter", PAGINA
    )


def test_conferir_evidencia_corrige_pagina_dentro_das_permitidas() -> None:
    edital = Edital("e.pdf", (Pagina(1, "Preâmbulo do edital."), Pagina(2, PAGINA)))
    evidencia = Evidencia(pagina=1, trecho="indicar se fazem parte de rota de fuga")
    assert conferir_evidencia(evidencia, edital, [1, 2]) == Evidencia(2, evidencia.trecho)
    assert conferir_evidencia(evidencia, edital, [1]) is None


def test_conferir_evidencia_descarta_trecho_inventado() -> None:
    edital = Edital("e.pdf", (Pagina(1, PAGINA),))
    assert (
        conferir_evidencia(Evidencia(1, "As portas deverão ser de madeira maciça."), edital) is None
    )


def test_conferir_evidencia_descarta_trecho_curto_demais() -> None:
    edital = Edital("e.pdf", (Pagina(1, PAGINA),))
    assert conferir_evidencia(Evidencia(1, "portas"), edital) is None


def test_clausula_do_trecho() -> None:
    assert clausula_do_trecho(PAGINA, "indicar se fazem parte de rota de fuga") == "5.1.2"
    assert clausula_do_trecho(PAGINA, "resistência ao fogo da porta") == "5.1.1"
    assert clausula_do_trecho(PAGINA, "texto inexistente na página") is None
