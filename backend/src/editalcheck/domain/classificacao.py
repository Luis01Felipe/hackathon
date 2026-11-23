"""Classificação dos requisitos de informação (IR): item de checagem, verificação e ambientes.

Regras determinísticas e independentes de IA. Servem de reserva quando a IA não
classifica o requisito e garantem que a classificação seja coerente com a
salvaguarda S3 (``verificavel_por_ids``). O catálogo segue a aba "Itens de
checagem" da planilha de IR adotada como template.
"""

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace

from editalcheck.domain.evidence import normalizar, remover_acentos
from editalcheck.domain.models import ItemChecagem, Requisito, TipoVerificacao

MAX_AMBIENTES = 4


@dataclass(frozen=True)
class DefinicaoItem:
    item: ItemChecagem
    nome: str
    palavras_chave: tuple[str, ...]  # prefixos sem acento, comparados no início de palavra
    critico: bool


CATALOGO_ITENS: tuple[DefinicaoItem, ...] = (
    DefinicaoItem(
        ItemChecagem.ILUM,
        "Iluminação",
        ("iluminamento", "iluminacao", "lux", "luminot", "luminaria"),
        critico=False,
    ),
    DefinicaoItem(
        ItemChecagem.VENT,
        "Ventilação e climatização",
        ("ventilacao", "climatiz", "temperatura", "umidade", "ar condicionado", "exaust"),
        critico=False,
    ),
    DefinicaoItem(
        ItemChecagem.ELET,
        "Instalações elétricas",
        ("eletric", "tensao", "energia", "cabos", "gerador", "aterramento"),
        critico=True,
    ),
    DefinicaoItem(
        ItemChecagem.INCE,
        "Proteção contra incêndio e rotas de fuga",
        (
            "corta-fogo",
            "corta fogo",
            "pcf",
            "incendio",
            "rota de fuga",
            "rotas de fuga",
            "saida de emergencia",
            "nfpa",
            "pressuriz",
            "resistencia ao fogo",
            "fire",
            "extintor",
            "hidrante",
            "sprinkler",
        ),
        critico=True,
    ),
    DefinicaoItem(
        ItemChecagem.ACES,
        "Acessibilidade",
        ("nbr 9050", "acessivel", "acessibilidade", "pcd", "deficiencia", "elevador", "rampa"),
        critico=True,
    ),
    DefinicaoItem(
        ItemChecagem.ACUS,
        "Acústica",
        ("acustic", "ruido", "nbr 10152", "reverbera"),
        critico=False,
    ),
    DefinicaoItem(
        ItemChecagem.HIDR,
        "Instalações hidrossanitárias e drenagem",
        (
            "reservat",
            "drenagem",
            "sanitar",
            "hidraulic",
            "estanque",
            "agua",
            "ralo",
            "esgoto",
            "pluvia",
        ),
        critico=True,
    ),
    DefinicaoItem(
        ItemChecagem.DADO,
        "Comunicação, dados e sinalização",
        ("intercomunic", "cftv", "sonoriza", "comunicacao visual", "sinaliza", "telefon"),
        critico=False,
    ),
    DefinicaoItem(
        ItemChecagem.ACAB,
        "Materiais e acabamentos",
        (
            "acabamento",
            "piso",
            "forro",
            "revestimento",
            "vidro",
            "pintura",
            "esquadria",
            "porta",
            "janela",
            "materia",
        ),
        critico=False,
    ),
    DefinicaoItem(
        ItemChecagem.OPER,
        "Operação e manutenção",
        ("manutencao", "limpeza", "operac", "alcapao", "monovia"),
        critico=False,
    ),
    DefinicaoItem(
        ItemChecagem.DIME,
        "Dimensões e programa de espaços",
        (
            "pe direito",
            "pe-direito",
            "largura",
            "comprimento",
            "area",
            "dimens",
            "capacidade",
            "altura",
            "profundidade",
        ),
        critico=False,
    ),
    DefinicaoItem(
        ItemChecagem.ESTR,
        "Estrutura, concreto e durabilidade",
        ("concreto", "fck", "cobrimento", "armadura", "vida util", "espessura", "estrutura"),
        critico=True,
    ),
)
_DEFINICAO = {d.item: d for d in CATALOGO_ITENS}

# Classes IFC que indicam a disciplina mesmo sem palavra-chave no texto.
_ITEM_DA_CLASSE: dict[str, ItemChecagem] = {
    "ifclightfixture": ItemChecagem.ILUM,
    "ifclamp": ItemChecagem.ILUM,
    "ifcductsegment": ItemChecagem.VENT,
    "ifcairterminal": ItemChecagem.VENT,
    "ifcunitaryequipment": ItemChecagem.VENT,
    "ifcelectricgenerator": ItemChecagem.ELET,
    "ifcelectricdistributionboard": ItemChecagem.ELET,
    "ifccablesegment": ItemChecagem.ELET,
    "ifcfiresuppressionterminal": ItemChecagem.INCE,
    "ifcalarm": ItemChecagem.INCE,
    "ifctransportelement": ItemChecagem.ACES,
    "ifcramp": ItemChecagem.ACES,
    "ifcpipesegment": ItemChecagem.HIDR,
    "ifctank": ItemChecagem.HIDR,
    "ifcsanitaryterminal": ItemChecagem.HIDR,
    "ifccommunicationsappliance": ItemChecagem.DADO,
    "ifcdoor": ItemChecagem.ACAB,
    "ifcwindow": ItemChecagem.ACAB,
    "ifccovering": ItemChecagem.ACAB,
    "ifcslab": ItemChecagem.ESTR,
    "ifcbeam": ItemChecagem.ESTR,
    "ifccolumn": ItemChecagem.ESTR,
    "ifcfooting": ItemChecagem.ESTR,
}
_PESO_CLASSE = 1  # desempata; as palavras do texto mandam

ROTULO_VERIFICACAO: dict[TipoVerificacao, str] = {
    TipoVerificacao.IDS: "IDS",
    TipoVerificacao.IDS_SCRIPT: "IDS + script",
    TipoVerificacao.SCRIPT: "Script geométrico (IfcOpenShell)",
    TipoVerificacao.MANUAL: "Manual / documental",
}
_VERIFICACOES_IDS = frozenset({TipoVerificacao.IDS, TipoVerificacao.IDS_SCRIPT})
_MOTIVO_GEOMETRICO = re.compile(
    r"\b(geometr|folga|distanc|percurso|rota|dimens|altura|largura|comprimento|area|"
    r"posic|localiza|afastamento|inclinac|volume|pe.direito)"
)

# Ambientes comuns em editais de edificação, para quando o modelo não tem IfcSpace.
_AMBIENTES_COMUNS: dict[str, str] = {
    "plataforma": "Plataformas",
    "hall": "Hall",
    "mezanino": "Mezanino",
    "bilheteria": "Bilheterias",
    "sanitario": "Sanitários",
    "banheiro": "Sanitários",
    "vestiario": "Vestiários",
    "refeitorio": "Refeitório",
    "cozinha": "Cozinha",
    "escritorio": "Escritórios",
    "estacionamento": "Estacionamento",
    "garagem": "Garagem",
    "almoxarifado": "Almoxarifado",
    "oficina": "Oficinas",
    "bicicletario": "Bicicletário",
    "circulacao": "Circulação",
    "corredor": "Circulação",
    "recepcao": "Recepção",
    "auditorio": "Auditório",
}
_SALA_DE = re.compile(
    r"\b(salas?|ambientes?|casas?|abrigos?|dep[óo]sitos?|centra(?:l|is)|compartimentos?|"
    r"[áa]reas?|po[çc]os?)\s+(de|do|da|dos|das)\s+([a-zà-ÿ]{3,})(?:\s+([a-zà-ÿ]{4,}))?",
    re.IGNORECASE,
)
# Palavras que encerram o nome do ambiente ("sala de baterias deverá ..." → "Sala de baterias").
_FIM_DO_NOME = re.compile(
    r"^(dever|poder|possu|ser[aã]|ter[aã]|tem|deve|pode|est[aã]|conforme|quando|onde|para|"
    r"pelo|pela|sendo|como|devid|junto|entre|sobre|cujo|cuja|nest|dess|dest|tamb)"
)


def _chave(texto: str) -> str:
    return remover_acentos(normalizar(texto))


def _ocorre(chave_termo: str, chave_texto: str) -> bool:
    return re.search(rf"\b{re.escape(chave_termo)}", chave_texto) is not None


def definicao_item(item: ItemChecagem) -> DefinicaoItem:
    return _DEFINICAO[item]


def rotulo_item(item: ItemChecagem | None) -> str:
    if item is None:
        return ""
    return f"{item.value} · {_DEFINICAO[item].nome}"


def classificar_item(texto: str, ifc_class: str | None = None) -> ItemChecagem | None:
    """Item de checagem com mais palavras-chave no texto (a classe IFC pesa mais)."""
    chave = _chave(texto)
    pontos: dict[ItemChecagem, int] = {}
    for definicao in CATALOGO_ITENS:
        acertos = sum(1 for termo in definicao.palavras_chave if _ocorre(termo, chave))
        if acertos:
            pontos[definicao.item] = acertos
    item_da_classe = _ITEM_DA_CLASSE.get((ifc_class or "").lower())
    if item_da_classe:
        pontos[item_da_classe] = pontos.get(item_da_classe, 0) + _PESO_CLASSE
    if not pontos:
        return None
    ordem = {d.item: indice for indice, d in enumerate(CATALOGO_ITENS)}
    return max(pontos, key=lambda item: (pontos[item], -ordem[item]))


def tipo_verificacao_padrao(requisito: Requisito) -> TipoVerificacao:
    if requisito.verificavel_por_ids:
        return TipoVerificacao.IDS
    if _MOTIVO_GEOMETRICO.search(_chave(requisito.motivo_nao_verificavel or "")):
        return TipoVerificacao.SCRIPT
    return TipoVerificacao.MANUAL


def verificacao_coerente(requisito: Requisito) -> TipoVerificacao:
    """Tipo de verificação compatível com ``verificavel_por_ids`` (que manda, pela S3)."""
    atual = requisito.verificacao
    if atual is None:
        return tipo_verificacao_padrao(requisito)
    if requisito.verificavel_por_ids == (atual in _VERIFICACOES_IDS):
        return atual
    return tipo_verificacao_padrao(requisito)


def verificavel_pelo_tipo(tipo: TipoVerificacao) -> bool:
    return tipo in _VERIFICACOES_IDS


def nivel_ids(tipo: TipoVerificacao) -> str:
    """Coluna "Verificável por IDS" do template: Sim, Parcial ou Não."""
    if tipo == TipoVerificacao.IDS:
        return "Sim"
    if tipo == TipoVerificacao.IDS_SCRIPT:
        return "Parcial"
    return "Não"


def _capitalizar(nome: str) -> str:
    nome = " ".join(nome.split())
    return nome[:1].upper() + nome[1:]


def _nome_sala(match: re.Match[str]) -> str:
    tipo, preposicao, primeira, segunda = match.groups()
    partes = [tipo.lower(), preposicao.lower(), primeira.lower()]
    if segunda and not _FIM_DO_NOME.match(remover_acentos(segunda.lower())):
        partes.append(segunda.lower())
    return _capitalizar(" ".join(partes))


def limpar_ambientes(nomes: Iterable[str]) -> tuple[str, ...]:
    """Remove vazios e repetidos (sem diferenciar acento e caixa), mantendo a ordem."""
    vistos: set[str] = set()
    limpos: list[str] = []
    for nome in nomes:
        texto = " ".join(nome.split())
        chave = _chave(texto)
        if not texto or chave in vistos:
            continue
        vistos.add(chave)
        limpos.append(texto)
    return tuple(limpos)


def sugerir_ambientes(texto: str, conhecidos: Sequence[str] = ()) -> tuple[str, ...]:
    """Ambientes citados no texto.

    Primeiro procura os nomes de ambiente do modelo (IfcSpace). Sem resultado,
    reconhece expressões como "sala de baterias" e ambientes comuns em editais.
    """
    chave = _chave(texto)
    if not chave:
        return ()
    do_modelo = [nome for nome in conhecidos if _chave(nome) and _ocorre(_chave(nome), chave)]
    if do_modelo:
        return limpar_ambientes(do_modelo)[:MAX_AMBIENTES]
    achados = [_nome_sala(m) for m in _SALA_DE.finditer(texto)]
    achados += [nome for termo, nome in _AMBIENTES_COMUNS.items() if _ocorre(termo, chave)]
    return limpar_ambientes(achados)[:MAX_AMBIENTES]


def classificar(
    requisito: Requisito, ambientes_conhecidos: Sequence[str] = (), contexto: str = ""
) -> Requisito:
    """Completa o que falta da classificação e alinha a verificação com a S3.

    ``contexto`` (ex.: título do tópico) só é usado para achar ambientes quando a
    descrição e o trecho não citam nenhum.
    """
    texto = " ".join(
        filter(
            None,
            [
                requisito.descricao,
                requisito.evidencia.trecho,
                requisito.pset,
                requisito.propriedade,
            ],
        )
    )
    item = requisito.item_checagem or classificar_item(texto, requisito.ifc_class)
    ambientes = limpar_ambientes(requisito.ambientes)
    if not ambientes:
        frase = f"{requisito.descricao} {requisito.evidencia.trecho}"
        ambientes = sugerir_ambientes(frase, ambientes_conhecidos) or sugerir_ambientes(
            contexto, ambientes_conhecidos
        )
    return replace(
        requisito,
        item_checagem=item,
        verificacao=verificacao_coerente(requisito),
        ambientes=ambientes,
    )
