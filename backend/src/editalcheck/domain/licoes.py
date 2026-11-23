"""Lições aprendidas: leitura por regras, busca no edital e elementos candidatos.

As lições só ACRESCENTAM verificações (salvaguarda G1). Nada aqui remove ou
rebaixa apontamentos das análises A, B e C.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import replace

from editalcheck.domain.evidence import compactar_espacos, normalizar, remover_acentos
from editalcheck.domain.models import (
    CaixaEnvolvente,
    Edital,
    ElementoModelo,
    Evidencia,
    FonteEvidencia,
    LicaoAprendida,
    ModeloResumo,
    VerificacaoLicao,
)
from editalcheck.domain.vagueness import dividir_sentencas

TAMANHO_MINIMO_ITEM = 25
TAMANHO_MAXIMO_TRECHO = 300
LIMITE_SOBREPOSICAO_EXPLICITA = 0.6
LIMITE_SOBREPOSICAO_RELACIONADA = 0.4
MINIMO_PALAVRAS_RELACIONADA = 2
_MARCADOR_ITEM = re.compile(
    r"^\s*(?:[-•*–—▪●]\s+|\(?\d{1,3}[.)-]\s*(?:\d{1,3}[.)]\s*)*|[a-z]\)\s+|LIC-?\d+\s*[:.-]?\s*)",
    re.IGNORECASE,
)
_AMBIENTE = re.compile(
    r"\b(?:sala|salas|ambiente|ambientes|casa|abrigo|deposito|depositos|central|"
    r"compartimento|area|areas)\s+(?:de|do|da|dos|das)\s+([a-z]{4,})"
)
_PALAVRA = re.compile(r"[a-z0-9]+")
# Um item só é lição se trouxer uma regra (obrigação, proibição ou recomendação).
_REGRA = re.compile(
    r"\b(deve|devem|devera|deverao|deveria|nao pode|nao podem|precisa|precisam|"
    r"obrigatori\w*|proibid\w*|vedad\w*|evit\w*|nunca|sempre|recomenda\w*|exig\w*)\b"
)
# Palavras frequentes demais para indicar o assunto de uma lição.
_GENERICAS = frozenset(
    [
        "para",
        "pela",
        "pelo",
        "pelas",
        "pelos",
        "como",
        "quando",
        "onde",
        "deve",
        "devem",
        "devera",
        "deverao",
        "deveria",
        "nao",
        "sim",
        "todas",
        "todos",
        "toda",
        "todo",
        "cada",
        "mais",
        "menos",
        "sobre",
        "entre",
        "apos",
        "antes",
        "desde",
        "ainda",
        "mesmo",
        "mesma",
        "edital",
        "projeto",
        "projetos",
        "modelo",
        "obra",
        "obras",
        "contratada",
        "contratante",
        "licitacao",
        "clausula",
        "item",
        "itens",
        "sala",
        "salas",
        "ambiente",
        "ambientes",
        "area",
        "areas",
        "local",
        "locais",
        "caso",
        "casos",
        "sempre",
        "possivel",
        "necessario",
        "necessaria",
        "adequado",
        "adequada",
        "existir",
        "possuir",
        "conter",
        "devido",
        "seguinte",
        "seguintes",
        "outro",
        "outra",
        "outros",
        "outras",
        "qualquer",
        "algum",
        "alguma",
        "nenhum",
        "nenhuma",
        "deverao",
        "podera",
        "poderao",
        "sera",
        "serao",
        "estar",
        "esta",
        "estao",
        "seja",
        "sejam",
        "foram",
        "tinha",
        "havia",
    ]
)
_GENERICAS = _GENERICAS | {
    "pode",
    "podem",
    "informar",
    "indicar",
    "conter",
    "propriedade",
    "propriedades",
    "informacao",
    "exigencia",
}


def _chave(texto: str) -> str:
    return remover_acentos(normalizar(texto))


def raiz(palavra: str) -> str:
    """Raiz simples para comparar singular e plural (``baterias`` → ``bateria``)."""
    if len(palavra) > 5 and palavra.endswith("oes"):
        return palavra[:-3] + "ao"
    if len(palavra) > 4 and palavra.endswith("s"):
        return palavra[:-1]
    return palavra


def palavras_chave(texto: str) -> set[str]:
    """Raízes das palavras significativas do texto (sem acento, sem palavras genéricas)."""
    return {
        raiz(p)
        for p in _PALAVRA.findall(_chave(texto))
        if len(p) >= 5 and not p.isdigit() and p not in _GENERICAS
    }


def raizes_dos_termos(termos: Iterable[str]) -> set[str]:
    """Raízes das palavras significativas dos termos ("sala de baterias" → {"bateria"})."""
    raizes: set[str] = set()
    for termo in termos:
        raizes |= palavras_chave(termo) or {raiz(p) for p in _PALAVRA.findall(_chave(termo))}
    return raizes


def termos_de_ambiente(texto: str) -> tuple[str, ...]:
    """Nomes de ambiente citados na regra (ex.: "sala de baterias" → ``baterias``)."""
    return tuple(dict.fromkeys(m.group(1) for m in _AMBIENTE.finditer(_chave(texto))))


# --------------------------------------------------------------------------- leitura


def _blocos(texto: str) -> list[str]:
    """Agrupa as linhas de uma página em itens (marcador, numeração ou parágrafo)."""
    blocos: list[list[str]] = [[]]
    for linha in texto.splitlines():
        limpa = linha.strip()
        if not limpa:
            blocos.append([])
            continue
        marcador = _MARCADOR_ITEM.match(limpa)
        if marcador and marcador.end() < len(limpa):
            blocos.append([limpa[marcador.end() :]])
            continue
        blocos[-1].append(limpa)
    return [compactar_espacos(" ".join(b)) for b in blocos if b]


def dividir_itens(documento: Edital) -> list[tuple[int, str]]:
    """Separa o documento em itens: marcadores, numeração ou parágrafos."""
    return [
        (pagina.numero, bloco)
        for pagina in documento.paginas
        for bloco in _blocos(pagina.texto)
        if len(bloco) >= TAMANHO_MINIMO_ITEM and _REGRA.search(_chave(bloco))
    ]


def _titulo(regra: str) -> str:
    primeira = dividir_sentencas(regra)[0] if regra else regra
    palavras = primeira.split()
    titulo = " ".join(palavras[:12])
    return titulo + ("…" if len(palavras) > 12 else "")


def licoes_por_regras(documento: Edital, inicio: int = 1) -> list[LicaoAprendida]:
    """Cada item do documento vira uma lição. O trecho citado é literal (passa na S2)."""
    licoes: list[LicaoAprendida] = []
    for indice, (pagina, texto) in enumerate(dividir_itens(documento), start=inicio):
        sentencas = dividir_sentencas(texto)
        trecho = (sentencas[0] if sentencas else texto)[:TAMANHO_MAXIMO_TRECHO]
        licoes.append(
            LicaoAprendida(
                id=f"LIC-{indice:02d}",
                titulo=_titulo(texto),
                regra=texto,
                evidencia=Evidencia(pagina=pagina, trecho=trecho, fonte=FonteEvidencia.LICOES),
                documento=documento.arquivo,
                termos_elemento=termos_de_ambiente(texto),
                extraida_por="regras",
            )
        )
    return licoes


def numerar(licoes: Sequence[LicaoAprendida], inicio: int = 1) -> list[LicaoAprendida]:
    return [replace(licao, id=f"LIC-{i:02d}") for i, licao in enumerate(licoes, start=inicio)]


# --------------------------------------------------------------------------- busca no edital


def _sentencas_do_edital(edital: Edital, paginas: Iterable[int] | None) -> list[tuple[int, str]]:
    permitidas = set(paginas) if paginas is not None else None
    return [
        (pagina.numero, sentenca)
        for pagina in edital.paginas
        if permitidas is None or pagina.numero in permitidas
        for sentenca in dividir_sentencas(pagina.texto)
    ]


def verificar_por_regras(
    licao: LicaoAprendida, edital: Edital, paginas: Iterable[int] | None = None
) -> VerificacaoLicao:
    """A lição está explícita se uma frase do edital cita o ambiente e a maior parte da regra.

    Também devolve a cláusula mais parecida (``trecho_relacionado``), que costuma
    ser a regra genérica que induziu o erro (ex.: iluminação natural em todas as salas).
    """
    # Lição lida por regras: a regra é a primeira frase do item (as demais são contexto).
    base = licao.regra if licao.extraida_por == "llm" else licao.evidencia.trecho
    chaves = palavras_chave(base)
    ambientes = raizes_dos_termos(licao.termos_elemento)
    if not chaves:
        return VerificacaoLicao(
            licao_id=licao.id, explicita=False, justificativa="Regra sem termos."
        )
    melhor: tuple[float, int, str] | None = None
    for pagina, sentenca in _sentencas_do_edital(edital, paginas):
        presentes = chaves & palavras_chave(sentenca)
        if not presentes:
            continue
        proporcao = len(presentes) / len(chaves)
        cita_ambiente = not ambientes or ambientes <= presentes
        if cita_ambiente and proporcao >= LIMITE_SOBREPOSICAO_EXPLICITA:
            return VerificacaoLicao(
                licao_id=licao.id,
                explicita=True,
                evidencia=Evidencia(pagina=pagina, trecho=sentenca),
                justificativa="O edital tem uma frase com o ambiente e a maior parte da regra.",
            )
        if melhor is None or proporcao > melhor[0]:
            melhor = (proporcao, pagina, sentenca)
    relacionado = (
        Evidencia(pagina=melhor[1], trecho=melhor[2])
        if melhor
        and melhor[0] >= LIMITE_SOBREPOSICAO_RELACIONADA
        and melhor[0] * len(chaves) >= MINIMO_PALAVRAS_RELACIONADA
        else None
    )
    return VerificacaoLicao(
        licao_id=licao.id,
        explicita=False,
        trecho_relacionado=relacionado,
        justificativa="Nenhuma frase do edital traz esta regra de forma explícita.",
        redacao_sugerida=base,
    )


# --------------------------------------------------------------------------- modelo


def _nomes(elemento: ElementoModelo) -> set[str]:
    texto = " ".join(n for n in (elemento.nome, elemento.nome_longo) if n)
    return {raiz(p) for p in _PALAVRA.findall(_chave(texto))}


def elementos_candidatos(licao: LicaoAprendida, modelo: ModeloResumo) -> tuple[str, ...]:
    """Ambientes (e elementos da classe citada) cujo nome contém o ambiente da lição."""
    termos = raizes_dos_termos(licao.termos_elemento)
    if not termos:
        return ()
    classes = {"IfcSpace"} | ({licao.ifc_class} if licao.ifc_class else set())
    return tuple(
        e.global_id for e in modelo.elementos if e.classe in classes and termos & _nomes(e)
    )


# --------------------------------------------------------------------------- geometria simples

# Elementos que uma lição pode proibir num ambiente (ex.: "não podem ter janelas").
_PROIBIDOS = {
    "IfcWindow": re.compile(r"\bjanelas?\b|\baberturas?\b|\bvaos?\b|\biluminacao natural\b"),
    "IfcDoor": re.compile(r"\bportas?\b"),
}
_NEGACAO = re.compile(r"\b(nao|sem|proibid\w*|vedad\w*|nunca|evit\w*)\b")
FOLGA_CONTATO_M = 0.3
ALTURA_MINIMA_AMBIENTE_M = 3.0  # ambientes modelados como placas finas ganham pé-direito


def classes_proibidas(licao: LicaoAprendida) -> tuple[str, ...]:
    """Classes de elemento que a lição proíbe no ambiente (só quando há negação)."""
    texto = _chave(licao.evidencia.trecho if licao.extraida_por == "regras" else licao.regra)
    if not _NEGACAO.search(texto):
        return ()
    return tuple(classe for classe, padrao in _PROIBIDOS.items() if padrao.search(texto))


def _tocam(a: CaixaEnvolvente, b: CaixaEnvolvente, folga: float) -> bool:
    return all(
        a.minimo[i] - folga <= b.maximo[i] and b.minimo[i] - folga <= a.maximo[i] for i in range(3)
    )


def elementos_no_ambiente(
    ambiente: CaixaEnvolvente,
    caixas: dict[str, CaixaEnvolvente],
    folga: float = FOLGA_CONTATO_M,
) -> list[str]:
    """Elementos cuja caixa envolvente toca a do ambiente (checagem geométrica simples).

    É uma aproximação: caixas alinhadas aos eixos, sem recorte exato da geometria.
    """
    x1, y1, z1 = ambiente.maximo
    alto = CaixaEnvolvente(
        ambiente.minimo, (x1, y1, max(z1, ambiente.minimo[2] + ALTURA_MINIMA_AMBIENTE_M))
    )
    return [guid for guid, caixa in caixas.items() if _tocam(alto, caixa, folga)]
