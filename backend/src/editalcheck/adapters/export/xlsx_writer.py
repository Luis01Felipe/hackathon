"""Exportação para planilha XLSX: requisitos de informação (RF-27) e esclarecimentos (RF-152)."""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from editalcheck.domain.classificacao import (
    CATALOGO_ITENS,
    ROTULO_VERIFICACAO,
    nivel_ids,
    rotulo_item,
    verificacao_coerente,
)
from editalcheck.domain.findings import texto_restricao
from editalcheck.domain.models import (
    Cardinalidade,
    Eir,
    FonteEvidencia,
    ItemChecagem,
    OrigemInconsistencia,
    OrigemVocabulario,
    Projeto,
    Relatorio,
    Requisito,
    StatusDecisao,
    StatusRequisito,
    TipoVerificacao,
)

COR_CABECALHO = "E8EAF0"
COR_TEM = "D7F0DD"
COR_SEM = "EEEEEE"
MAX_IDS_CELULA = 4

# Aba "Requisitos": as 20 colunas do template de IR, na mesma ordem, e depois as extras.
COLUNAS = (
    ("ID", 9),
    ("Escopo", 26),
    ("Categorias", 34),
    ("Item de checagem", 26),
    ("Descrição", 60),
    ("Pág.", 7),
    ("Trecho literal do edital", 50),
    ("Verificação", 22),
    ("Verificável por IDS", 12),
    ("Motivo / observação", 46),
    ("Classe IFC", 20),
    ("PredefinedType", 16),
    ("Faceta IDS", 12),
    ("Pset.Propriedade ou atributo", 40),
    ("Tipo de dado", 18),
    ("Restrição", 26),
    ("Cardinalidade", 13),
    ("Origem do vocabulário", 20),
    ("Aplica a todas do escopo", 12),
    ("Status", 10),
    ("Cláusula", 9),
    ("Marcos de entrega", 22),
    ("Lição aprendida", 11),
    ("URI bSDD", 40),
    ("Gerado por", 11),
    ("Fonte do trecho", 14),
)
FONTE = {FonteEvidencia.EDITAL: "edital", FonteEvidencia.LICOES: "lições aprendidas"}
CARDINALIDADE = {
    Cardinalidade.OBRIGATORIA: "obrigatório",
    Cardinalidade.OPCIONAL: "opcional",
    Cardinalidade.PROIBIDA: "proibido",
}
ORIGEM = {
    OrigemVocabulario.PSET_OFICIAL: "pset_oficial (conferir)",
    OrigemVocabulario.BSDD: "bSDD",
    OrigemVocabulario.CUSTOMIZADO: "customizado",
}
TOPICOS_ESPECIAIS = {"LICOES": "Lições aprendidas", "LACUNA": "Sugerido por lacuna"}
SEM_AMBIENTE = "(sem ambiente: vale para todo o tópico)"

ACEITACAO = (
    (
        "Não aplicável",
        "NA",
        "Requisito não se aplica à categoria. É decisão do usuário, com justificativa.",
    ),
    (
        "Não cumpre",
        "0",
        "Nenhum elemento aplicável passa no IDS, ou a informação exigida está ausente.",
    ),
    (
        "Cumpre parcialmente",
        "1",
        "A maioria dos elementos aplicáveis falha. Não basta para aprovação.",
    ),
    ("Cumpre substancialmente", "2", "A maioria dos elementos passa. Aprovação condicional."),
    ("Cumpre totalmente", "3", "Todos os elementos aplicáveis passam."),
)
NOTA_MINIMA = (
    "Nota mínima para aceitação: 2. Decisões do usuário (pendente, em discussão, aceito) ficam "
    "numa camada separada e não alteram o resultado bruto da verificação."
)
QUALIDADE_MODELO = (
    (
        "Origem e sistema de coordenadas",
        "Script (IfcMapConversion / IfcProjectedCRS)",
        "Coordenadas georreferenciadas presentes.",
    ),
    (
        "Orientação",
        "Script (IfcGeometricRepresentationContext.TrueNorth)",
        "Modelo orientado ao Norte.",
    ),
    ("Eixos estruturais", "IDS (entidade IfcGrid)", "Eixos coordenados com o arquivo base."),
    ("Pisos", "IDS (entidade IfcBuildingStorey)", "Níveis coordenados com o arquivo base."),
    ("Duplicações", "Script (elementos sobrepostos)", "Não existem duplicações."),
    (
        "Unidades",
        "Script (IfcUnitAssignment)",
        "Unidades coerentes com as restrições dos requisitos (m ou mm).",
    ),
    (
        "Nomes de ambientes",
        "IDS (atributo Name/LongName de IfcSpace)",
        "Nomes seguem o programa do edital.",
    ),
    (
        "Informação alfanumérica",
        "IDS (propriedades da aba Requisitos)",
        "Propriedades exigidas preenchidas nos elementos aplicáveis.",
    ),
    (
        "Nível de Informação Necessário",
        "Manual",
        "Detalhe, dimensão, localização, aparência e comportamento conforme o acordado.",
    ),
)


def _cabecalho(
    aba, colunas: Sequence[tuple[str, int]], linha: int = 1, cor: str = "1F3A5F"
) -> None:
    claro = cor == COR_CABECALHO
    for indice, (nome, largura) in enumerate(colunas, start=1):
        if largura:
            aba.column_dimensions[get_column_letter(indice)].width = largura
        celula = aba.cell(row=linha, column=indice, value=nome)
        celula.font = Font(bold=True, size=10) if claro else Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=cor)
        celula.alignment = Alignment(wrap_text=True, vertical="center")


def _finalizar(aba, congelar: str = "B2") -> None:
    for linha in aba.iter_rows(min_row=2):
        for celula in linha:
            celula.alignment = Alignment(wrap_text=True, vertical="top")
    aba.freeze_panes = congelar
    aba.auto_filter.ref = aba.dimensions


def _numero_req(requisito: Requisito) -> str:
    return requisito.id.removeprefix("REQ-")


def _rotulo_topico(projeto: Projeto, topico_id: str) -> str:
    if topico_id in TOPICOS_ESPECIAIS:
        return TOPICOS_ESPECIAIS[topico_id]
    topico = projeto.topico(topico_id)
    if topico is None:
        return topico_id
    return f"{topico.numero} — {topico.titulo}"


def _pset_propriedade(requisito: Requisito) -> str:
    if requisito.pset and requisito.propriedade:
        return f"{requisito.pset}.{requisito.propriedade}"
    return requisito.pset or requisito.propriedade or ""


def _verificacao(requisito: Requisito) -> TipoVerificacao:
    return verificacao_coerente(requisito)


def _ativos(eir: Eir) -> list[Requisito]:
    """Requisitos que contam na matriz: os rejeitados ficam de fora."""
    return [r for r in eir.requisitos if r.status != StatusRequisito.REJEITADO]


@dataclass(frozen=True)
class _LinhaMatriz:
    ambiente: str
    requisitos: tuple[Requisito, ...]

    def do_item(self, item: ItemChecagem) -> list[Requisito]:
        return [r for r in self.requisitos if r.item_checagem == item]

    @property
    def itens_cobertos(self) -> int:
        return len({r.item_checagem for r in self.requisitos if r.item_checagem})


def _matriz(eir: Eir) -> list[_LinhaMatriz]:
    por_ambiente: dict[str, list[Requisito]] = {}
    for requisito in _ativos(eir):
        for ambiente in requisito.ambientes or (SEM_AMBIENTE,):
            por_ambiente.setdefault(ambiente, []).append(requisito)
    return [_LinhaMatriz(nome, tuple(reqs)) for nome, reqs in por_ambiente.items()]


def _celula_matriz(requisitos: Sequence[Requisito]) -> str:
    if not requisitos:
        return "Sem requisito"
    numeros = [_numero_req(r) for r in requisitos]
    extra = len(numeros) - MAX_IDS_CELULA
    texto = "Tem · " + ", ".join(numeros[:MAX_IDS_CELULA])
    return f"{texto} +{extra}" if extra > 0 else texto


def _topicos_da_linha(projeto: Projeto, requisitos: Sequence[Requisito]) -> str:
    ids = dict.fromkeys(r.topico_id for r in requisitos)
    return "; ".join(_rotulo_topico(projeto, t) for t in ids)


class XlsxEirExporter:
    """Planilha de requisitos de informação (IR) no template adotado pelo Construtivo."""

    def to_xlsx(self, eir: Eir, projeto: Projeto) -> bytes:
        planilha = Workbook()
        matriz = _matriz(eir)
        self._resumo(planilha.active, eir, projeto, matriz)
        self._requisitos(planilha.create_sheet("Requisitos"), eir, projeto)
        self._aba_matriz(planilha.create_sheet("Matriz"), projeto, matriz)
        self._categorias(planilha.create_sheet("Categorias"), projeto, matriz)
        self._itens(planilha.create_sheet("Itens de checagem"), eir)
        self._aceitacao(planilha.create_sheet("Aceitação e qualidade"))
        saida = BytesIO()
        planilha.save(saida)
        return saida.getvalue()

    def _resumo(self, aba, eir: Eir, projeto: Projeto, matriz: Sequence[_LinhaMatriz]) -> None:
        aba.title = "Resumo"
        aba.column_dimensions["A"].width = 33
        aba.column_dimensions["B"].width = 80
        contagem = Counter(_verificacao(r) for r in eir.requisitos)
        com_ambiente = [linha for linha in matriz if linha.ambiente != SEM_AMBIENTE]
        ambientes = len(com_ambiente)
        celulas = ambientes * len(CATALOGO_ITENS)
        com_requisito = sum(linha.itens_cobertos for linha in com_ambiente)
        aprovados = sum(1 for r in eir.requisitos if r.aprovado)
        linhas: list[tuple[str, str]] = [
            ("Requisitos de informação (IR)", ""),
            (
                "Extraídos do edital e das lições aprendidas pelo EditalCheck. Cada requisito "
                "traz a página e o trecho literal conferido contra o edital.",
                "",
            ),
            (
                f"Requisitos: {len(eir.requisitos)}  ·  aprovados: {aprovados}  ·  "
                + "  ·  ".join(
                    f"{ROTULO_VERIFICACAO[t].lower()}: {contagem.get(t, 0)}"
                    for t in TipoVerificacao
                ),
                "",
            ),
            (
                f"Matriz: {ambientes} ambientes × {len(CATALOGO_ITENS)} itens = {celulas} células"
                f"  ·  com requisito: {com_requisito}  ·  sem requisito: {celulas - com_requisito}",
                "",
            ),
            ("", ""),
            ("Campo", "Valor"),
            ("Projeto", projeto.id),
            ("Edital", projeto.edital.arquivo),
            ("Modelo IFC", projeto.modelo.arquivo or "(sem modelo: revisão do edital)"),
            ("Schema", projeto.modelo.schema),
            ("Versão dos requisitos de informação (IR)", str(eir.versao)),
            ("Data", eir.data),
            ("Aprovado por", eir.aprovado_por or ""),
            (
                "Tópicos selecionados",
                "\n".join(_rotulo_topico(projeto, t) for t in eir.topicos_selecionados),
            ),
        ]
        for linha in linhas:
            aba.append(list(linha))
        aba["A1"].font = Font(bold=True, size=13)
        for numero in range(2, 5):
            aba.merge_cells(start_row=numero, start_column=1, end_row=numero, end_column=2)
        _cabecalho(aba, (("Campo", 0), ("Valor", 0)), linha=6, cor=COR_CABECALHO)
        for linha in aba.iter_rows(min_row=2):
            for celula in linha:
                celula.alignment = Alignment(wrap_text=True, vertical="top")

    def _requisitos(self, aba, eir: Eir, projeto: Projeto) -> None:
        _cabecalho(aba, COLUNAS, cor=COR_CABECALHO)
        marcos = {m.id: m.nome for m in projeto.marcos}
        for r in eir.requisitos:
            verificacao = _verificacao(r)
            motivo = " | ".join(filter(None, [r.motivo_nao_verificavel, *r.avisos]))
            aba.append(
                [
                    r.id,
                    _rotulo_topico(projeto, r.topico_id),
                    "; ".join(r.ambientes),
                    rotulo_item(r.item_checagem),
                    r.descricao,
                    r.evidencia.pagina or "",
                    r.evidencia.trecho,
                    ROTULO_VERIFICACAO[verificacao],
                    nivel_ids(verificacao),
                    motivo,
                    r.ifc_class or "",
                    r.predefined_type or "",
                    r.faceta.value if r.faceta else "",
                    _pset_propriedade(r),
                    r.tipo_dado or "",
                    texto_restricao(r.restricao).strip(),
                    CARDINALIDADE[r.cardinalidade],
                    ORIGEM.get(r.origem_vocabulario, "") if r.origem_vocabulario else "",
                    "não" if r.ambientes else "sim",
                    r.status.value,
                    r.clausula or "",
                    ", ".join(marcos.get(m, m) for m in r.marcos) or "todos",
                    r.licao_id or "",
                    r.bsdd_uri or "",
                    r.gerado_por,
                    FONTE[r.evidencia.fonte],
                ]
            )
        _finalizar(aba)

    def _aba_matriz(self, aba, projeto: Projeto, matriz: Sequence[_LinhaMatriz]) -> None:
        colunas = [
            ("Categoria", 41),
            *((rotulo_item(d.item), 19) for d in CATALOGO_ITENS),
            ("Cobertura", 11),
            ("Tópico(s)", 40),
        ]
        _cabecalho(aba, colunas, cor=COR_CABECALHO)
        total = len(CATALOGO_ITENS)
        for numero, linha in enumerate(matriz, start=2):
            aba.cell(row=numero, column=1, value=linha.ambiente)
            for coluna, definicao in enumerate(CATALOGO_ITENS, start=2):
                do_item = linha.do_item(definicao.item)
                celula = aba.cell(row=numero, column=coluna, value=_celula_matriz(do_item))
                celula.fill = PatternFill("solid", fgColor=COR_TEM if do_item else COR_SEM)
            aba.cell(row=numero, column=total + 2, value=f"{linha.itens_cobertos}/{total}")
            aba.cell(
                row=numero, column=total + 3, value=_topicos_da_linha(projeto, linha.requisitos)
            )
        _finalizar(aba)

    def _categorias(self, aba, projeto: Projeto, matriz: Sequence[_LinhaMatriz]) -> None:
        colunas = (
            ("ID", 10),
            ("Categoria", 54),
            ("Tópico(s)", 50),
            ("Requisitos", 11),
            ("Itens cobertos", 13),
        )
        _cabecalho(aba, colunas, cor=COR_CABECALHO)
        total = len(CATALOGO_ITENS)
        for indice, linha in enumerate(matriz, start=1):
            aba.append(
                [
                    f"CAT-{indice:02d}",
                    linha.ambiente,
                    _topicos_da_linha(projeto, linha.requisitos),
                    len(linha.requisitos),
                    f"{linha.itens_cobertos}/{total}",
                ]
            )
        _finalizar(aba, congelar="C2")

    def _itens(self, aba, eir: Eir) -> None:
        colunas = (
            ("ID", 8),
            ("Item de checagem", 40),
            ("Palavras-chave", 70),
            ("Crítico", 9),
            ("Requisitos", 11),
        )
        _cabecalho(aba, colunas, cor=COR_CABECALHO)
        contagem = Counter(r.item_checagem for r in _ativos(eir))
        for definicao in CATALOGO_ITENS:
            aba.append(
                [
                    definicao.item.value,
                    definicao.nome,
                    " | ".join(definicao.palavras_chave),
                    "sim" if definicao.critico else "não",
                    contagem.get(definicao.item, 0),
                ]
            )
        _finalizar(aba, congelar="A2")

    def _aceitacao(self, aba) -> None:
        for coluna, largura in (("A", 34), ("B", 52), ("C", 90)):
            aba.column_dimensions[coluna].width = largura
        aba.append(["Tabela de aceitação"])
        aba["A1"].font = Font(bold=True, size=10)
        _cabecalho(
            aba,
            (("Critério", 0), ("Nota", 0), ("Descrição na checagem do IFC", 0)),
            linha=2,
            cor=COR_CABECALHO,
        )
        for linha in ACEITACAO:
            aba.append(list(linha))
        aba.append([])
        aba.append([NOTA_MINIMA])
        aba.append([])
        aba.append(["Qualidade do modelo"])
        titulo = aba.max_row
        aba.cell(row=titulo, column=1).font = Font(bold=True, size=10)
        _cabecalho(
            aba,
            (("Verificação", 0), ("Como", 0), ("Critério", 0)),
            linha=titulo + 1,
            cor=COR_CABECALHO,
        )
        for linha in QUALIDADE_MODELO:
            aba.append(list(linha))
        for linha in aba.iter_rows(min_row=3):
            for celula in linha:
                if not celula.font.bold:
                    celula.alignment = Alignment(wrap_text=True, vertical="top")


COLUNAS_ESCLARECIMENTOS = (
    ("Apontamento", 12),
    ("Severidade", 10),
    ("Tipo", 18),
    ("Página", 8),
    ("Trecho do edital", 60),
    ("Problema", 45),
    ("Pergunta sugerida (pedido de esclarecimento)", 55),
    ("Redação sugerida / como agir", 60),
    ("Decisão", 14),
    ("Comentário da decisão", 40),
    ("Autor da decisão", 18),
    ("Gerado por IA", 10),
)
ROTULO_DECISAO = {
    StatusDecisao.PENDENTE: "Pendente",
    StatusDecisao.ACEITO: "Aceito",
    StatusDecisao.REJEITADO: "Rejeitado",
    StatusDecisao.EM_DISCUSSAO: "Em discussão",
    StatusDecisao.DISPENSADO: "Dispensado",
}
AVISO_JURIDICO = (
    "Minuta gerada automaticamente (parte por IA). Valide com o jurídico antes de protocolar "
    "qualquer pedido de esclarecimento ou impugnação do edital."
)


class XlsxClarificationExporter:
    """Matriz de esclarecimentos: um item por apontamento de origem EDITAL (RF-152)."""

    def to_xlsx(self, relatorio: Relatorio) -> bytes:
        planilha = Workbook()
        aba = planilha.active
        aba.title = "Esclarecimentos"
        _cabecalho(aba, COLUNAS_ESCLARECIMENTOS)
        for apontamento in relatorio.apontamentos:
            if apontamento.origem != OrigemInconsistencia.EDITAL:
                continue
            decisao = relatorio.decisao(apontamento.id)
            edital = [e for e in apontamento.evidencias_edital if e.fonte == FonteEvidencia.EDITAL]
            primeira = edital[0] if edital else None
            local = f"na página {primeira.pagina}" if primeira else "no edital"
            pergunta = (
                f"Solicitamos esclarecer o trecho {local}: {apontamento.titulo.rstrip('.')}. "
                "Qual critério objetivo será usado na verificação da entrega?"
            )
            aba.append(
                [
                    apontamento.id,
                    apontamento.severidade.value,
                    apontamento.tipo.value,
                    primeira.pagina if primeira else "",
                    primeira.trecho if primeira else "",
                    apontamento.titulo,
                    pergunta,
                    apontamento.como_agir,
                    ROTULO_DECISAO[decisao.status] if decisao else "Pendente",
                    decisao.comentario if decisao else "",
                    decisao.autor if decisao else "",
                    "sim" if apontamento.gerado_por_ia else "não",
                ]
            )
        _finalizar(aba)
        info = planilha.create_sheet("Leia antes")
        for linha in (
            ("Aviso", AVISO_JURIDICO),
            ("Edital", relatorio.edital_arquivo),
            ("Verificação", relatorio.verificacao_id),
            ("Gerado em", relatorio.gerado_em),
        ):
            info.append(list(linha))
        info.column_dimensions["A"].width = 16
        info.column_dimensions["B"].width = 100
        saida = BytesIO()
        planilha.save(saida)
        return saida.getvalue()
