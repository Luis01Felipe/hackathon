"""Construção dos apontamentos a partir dos resultados das análises (RF-50, RF-51).

Cada apontamento sai completo: severidade (matriz determinística), destinatário,
evidências, referências da lista fechada e textos "como agir" / "por que" por
template. O LLM pode reescrever os textos depois (RF-52), mas a demo nunca
fica sem recomendação.
"""

from collections.abc import Mapping, Sequence
from dataclasses import replace

from editalcheck.domain import severity as sev
from editalcheck.domain.evidence import normalizar, rotulo_clausula
from editalcheck.domain.models import (
    AmbiguidadeConfirmada,
    Apontamento,
    Cobertura,
    Contradicao,
    Destinatario,
    Evidencia,
    ItemChecklist,
    ModeloResumo,
    OrigemVocabulario,
    PropriedadeSugerida,
    Referencia,
    Requisito,
    Restricao,
    ResultadoChecklist,
    ResultadoEspecificacao,
    StatusChecklist,
    StatusRequisito,
    TipoApontamento,
    TipoFaceta,
    TipoRestricao,
)
from editalcheck.domain.vocabulary import uri_bsdd_propriedade

SCHEMAS_SUPORTADOS = ("IFC2X3", "IFC4", "IFC4X3", "IFC4X3_ADD2")
_ORDEM_ANALISE = {"A": 0, "C": 1, "B": 2, "saude": 3}


# --------------------------------------------------------------------------- textos


def _numero(valor: float) -> str:
    return f"{valor:g}".replace(".", ",")


def texto_restricao(restricao: Restricao | None) -> str:
    if restricao is None:
        return ""
    if restricao.tipo == TipoRestricao.VALOR and restricao.valores:
        return f' igual a "{restricao.valores[0]}"'
    if restricao.tipo == TipoRestricao.ENUMERACAO and restricao.valores:
        return " com um dos valores: " + ", ".join(f'"{v}"' for v in restricao.valores)
    if restricao.tipo == TipoRestricao.PADRAO and restricao.valores:
        return f" no padrão {restricao.valores[0]}"
    if restricao.tipo == TipoRestricao.INTERVALO:
        if restricao.minimo is not None and restricao.maximo is not None:
            return f" entre {_numero(restricao.minimo)} e {_numero(restricao.maximo)}"
        if restricao.minimo is not None:
            return f" maior ou igual a {_numero(restricao.minimo)}"
        if restricao.maximo is not None:
            return f" menor ou igual a {_numero(restricao.maximo)}"
    return ""


def exigencia(requisito: Requisito) -> str:
    """Descrição curta do que o requisito exige do modelo."""
    restricao = texto_restricao(requisito.restricao)
    match requisito.faceta:
        case TipoFaceta.PROPRIEDADE:
            return f"a propriedade {requisito.pset}.{requisito.propriedade}{restricao}"
        case TipoFaceta.ATRIBUTO:
            return f"o atributo {requisito.propriedade}{restricao}"
        case TipoFaceta.CLASSIFICACAO:
            sistema = f" do sistema {requisito.pset}" if requisito.pset else ""
            return f"uma classificação{sistema}{restricao}"
        case TipoFaceta.MATERIAL:
            return f"um material associado{restricao}"
        case TipoFaceta.PARTE_DE:
            return f"a relação {requisito.propriedade or ''} com {requisito.pset or 'o contêiner'}"
        case _:
            return requisito.descricao


def referencias_do_requisito(requisito: Requisito) -> tuple[Referencia, ...]:
    refs = [
        Referencia(
            tipo="clausula_edital",
            rotulo=rotulo_clausula(requisito.evidencia, requisito.clausula),
        )
    ]
    if requisito.pset and requisito.propriedade:
        if requisito.origem_vocabulario == OrigemVocabulario.PSET_OFICIAL:
            refs.append(
                Referencia(
                    tipo="pset_oficial",
                    rotulo=f"{requisito.pset}.{requisito.propriedade} (Pset oficial buildingSMART)",
                    uri=requisito.bsdd_uri,
                )
            )
        elif requisito.origem_vocabulario == OrigemVocabulario.BSDD:
            refs.append(
                Referencia(
                    tipo="bsdd", rotulo=f"bSDD: {requisito.propriedade}", uri=requisito.bsdd_uri
                )
            )
    return tuple(refs)


# --------------------------------------------------------------------------- análise A


def de_resultados_ids(
    resultados: Sequence[ResultadoEspecificacao], requisitos: Sequence[Requisito]
) -> list[Apontamento]:
    por_id = {r.id: r for r in requisitos}
    apontamentos: list[Apontamento] = []
    for resultado in resultados:
        if resultado.status or not resultado.falhas:
            continue
        requisito = por_id.get(resultado.requisito_id or "")
        if requisito is None:
            continue
        falhas = len(resultado.falhas)
        classe = requisito.ifc_class or "elementos"
        o_que = exigencia(requisito)
        motivos = sorted({f.motivo for f in resultado.falhas if f.motivo})
        rotulo = rotulo_clausula(requisito.evidencia, requisito.clausula)
        apontamentos.append(
            Apontamento(
                id="",
                tipo=TipoApontamento.NAO_CONFORMIDADE,
                severidade=sev.nao_conformidade(requisito.cardinalidade),
                destinatario=Destinatario.PROJETISTA,
                titulo=f"{falhas} de {resultado.aplicaveis} {classe} sem {o_que}",
                analise="A",
                evidencias_edital=(requisito.evidencia,),
                elementos=tuple(f.global_id for f in resultado.falhas),
                requisito_id=requisito.id,
                como_agir=(
                    f"Preencha {o_que} nos {falhas} elementos listados e exporte o IFC novamente. "
                    "Use o arquivo BCF para localizar cada elemento na sua ferramenta BIM."
                ),
                por_que=(
                    f"O {rotulo} exige essa informação. O requisito {requisito.id} foi aprovado "
                    "no EIR e a verificação IDS falhou nesses elementos."
                ),
                referencias=referencias_do_requisito(requisito),
                classe_ifc=requisito.ifc_class,
                detalhe="; ".join(motivos[:3]),
            )
        )
    return apontamentos


# --------------------------------------------------------------------------- análise B


def _sentenca_gera_requisito(
    sentenca: str, clausula: str | None, requisitos: Sequence[Requisito]
) -> bool:
    alvo = normalizar(sentenca)
    for requisito in requisitos:
        if requisito.status == StatusRequisito.REJEITADO:
            continue
        if clausula and requisito.clausula == clausula:
            return True
        trecho = normalizar(requisito.evidencia.trecho)
        if trecho and (trecho in alvo or alvo in trecho):
            return True
    return False


def de_ambiguidades(
    confirmadas: Sequence[AmbiguidadeConfirmada], requisitos: Sequence[Requisito]
) -> list[Apontamento]:
    apontamentos: list[Apontamento] = []
    for item in confirmadas:
        if not item.ambiguo:
            continue
        trecho = item.trecho
        evidencia = Evidencia(pagina=trecho.pagina, trecho=trecho.trecho)
        gera_requisito = _sentenca_gera_requisito(trecho.trecho, trecho.clausula, requisitos)
        redacao = item.redacao_sugerida or trecho.sugestao
        como_agir = "Reescreva a cláusula com um critério mensurável (valor, norma com número e versão, ou lista fechada)."
        if redacao:
            como_agir = f'Reescreva a cláusula com critério mensurável. Sugestão: "{redacao}"'
        apontamentos.append(
            Apontamento(
                id="",
                tipo=TipoApontamento.AMBIGUIDADE,
                severidade=sev.ambiguidade(gera_requisito),
                destinatario=Destinatario.CONTRATANTE,
                titulo=f'Termo vago "{trecho.termo}" sem critério mensurável',
                analise="B",
                evidencias_edital=(evidencia,),
                como_agir=como_agir,
                por_que=(
                    f'O termo "{trecho.termo}" não define um valor verificável. Cada projetista pode '
                    "interpretar de um jeito, e a verificação do modelo fica subjetiva."
                ),
                referencias=(
                    Referencia(
                        tipo="clausula_edital", rotulo=rotulo_clausula(evidencia, trecho.clausula)
                    ),
                ),
                gerado_por_ia=item.confirmado_por == "llm",
                detalhe=item.justificativa,
            )
        )
    return apontamentos


def de_nao_verificaveis(requisitos: Sequence[Requisito]) -> list[Apontamento]:
    apontamentos: list[Apontamento] = []
    for requisito in requisitos:
        if requisito.status == StatusRequisito.REJEITADO or requisito.verificavel_por_ids:
            continue
        motivo = requisito.motivo_nao_verificavel or "Não há faceta IDS que represente o requisito."
        apontamentos.append(
            Apontamento(
                id="",
                tipo=TipoApontamento.NAO_VERIFICAVEL,
                severidade=sev.nao_verificavel(),
                destinatario=Destinatario.CONTRATANTE,
                titulo=f"{requisito.id} exige verificação manual: {requisito.descricao}",
                analise="B",
                evidencias_edital=(requisito.evidencia,),
                requisito_id=requisito.id,
                como_agir=(
                    "Faça a verificação manual deste requisito ou reescreva a cláusula como "
                    "informação do modelo (classe IFC, propriedade e valor esperado)."
                ),
                por_que=f"{motivo} O IDS só verifica informação alfanumérica do modelo.",
                referencias=(
                    Referencia(
                        tipo="clausula_edital",
                        rotulo=rotulo_clausula(requisito.evidencia, requisito.clausula),
                    ),
                ),
                detalhe=motivo,
            )
        )
    return apontamentos


def de_checklist(
    resultados: Sequence[ResultadoChecklist], itens: Sequence[ItemChecklist]
) -> list[Apontamento]:
    por_id = {i.id: i for i in itens}
    apontamentos: list[Apontamento] = []
    for resultado in resultados:
        item = por_id.get(resultado.item_id)
        if item is None or resultado.status == StatusChecklist.PRESENTE:
            continue
        referencia = Referencia(
            tipo="checklist", rotulo=f"Checklist EditalCheck {item.id} — {item.item}"
        )
        if resultado.status == StatusChecklist.PARCIAL:
            evidencias = (resultado.evidencia,) if resultado.evidencia else ()
            apontamentos.append(
                Apontamento(
                    id="",
                    tipo=TipoApontamento.ITEM_AUSENTE,
                    severidade=sev.item_ausente(False),
                    destinatario=Destinatario.CONTRATANTE,
                    titulo=f"Item mínimo incompleto: {item.item}",
                    analise="B",
                    evidencias_edital=evidencias,
                    como_agir=f"Complete o edital com critério objetivo para: {item.item.lower()}. {item.descricao}",
                    por_que=(
                        "O edital cita o tema, mas sem critério que permita verificar a entrega. "
                        + resultado.justificativa
                    ).strip(),
                    referencias=(referencia,),
                    gerado_por_ia=resultado.avaliado_por == "llm",
                    detalhe=resultado.justificativa,
                )
            )
            continue
        apontamentos.append(
            Apontamento(
                id="",
                tipo=TipoApontamento.ITEM_AUSENTE,
                severidade=sev.item_ausente(item.critico),
                destinatario=Destinatario.CONTRATANTE,
                titulo=f"Item mínimo ausente: {item.item}",
                analise="B",
                como_agir=f"Inclua no edital uma cláusula sobre {item.item.lower()}. {item.descricao}",
                por_que=(
                    "Sem esse item, o projetista não sabe o que entregar e o contratante não tem "
                    "critério para aceitar o modelo."
                    + (" O item é crítico na checklist." if item.critico else "")
                ),
                referencias=(referencia,),
                gerado_por_ia=resultado.avaliado_por == "llm",
                detalhe=resultado.justificativa,
            )
        )
    return apontamentos


def de_contradicoes(contradicoes: Sequence[Contradicao]) -> list[Apontamento]:
    apontamentos: list[Apontamento] = []
    for contradicao in contradicoes:
        a, b = contradicao.evidencia_a, contradicao.evidencia_b
        apontamentos.append(
            Apontamento(
                id="",
                tipo=TipoApontamento.CONTRADICAO,
                severidade=sev.contradicao(),
                destinatario=Destinatario.CONTRATANTE,
                titulo=f"Cláusulas contraditórias nas páginas {a.pagina} e {b.pagina}",
                analise="B",
                evidencias_edital=(a, b),
                como_agir="Harmonize as duas cláusulas e mantenha uma única exigência.",
                por_que=contradicao.explicacao,
                referencias=(
                    Referencia(tipo="clausula_edital", rotulo=rotulo_clausula(a, None)),
                    Referencia(tipo="clausula_edital", rotulo=rotulo_clausula(b, None)),
                ),
                gerado_por_ia=True,
            )
        )
    return apontamentos


# --------------------------------------------------------------------------- análise C


def de_lacunas(
    cobertura: Cobertura,
    sugestoes: Mapping[str, Sequence[PropriedadeSugerida]],
    elementos_por_classe: Mapping[str, Sequence[str]],
    config: sev.ConfigSeveridade,
) -> list[Apontamento]:
    apontamentos: list[Apontamento] = []
    for lacuna in cobertura.lacunas:
        sugeridas = tuple(sugestoes.get(lacuna.classe, ()))
        lista = ", ".join(f"{p.pset}.{p.nome}" for p in sugeridas)
        clausula_modelo = (
            f'"Todos os elementos {lacuna.classe} deverão conter as propriedades {lista}."'
            if lista
            else f'"Os elementos {lacuna.classe} deverão conter as propriedades definidas no EIR."'
        )
        referencias = tuple(
            Referencia(
                tipo="pset_oficial",
                rotulo=f"{p.pset}.{p.nome} (Pset oficial buildingSMART)",
                uri=uri_bsdd_propriedade(p.nome),
            )
            for p in sugeridas
        )
        apontamentos.append(
            Apontamento(
                id="",
                tipo=TipoApontamento.LACUNA_COBERTURA,
                severidade=sev.lacuna_cobertura(lacuna.classe, lacuna.contagem, config),
                destinatario=Destinatario.CONTRATANTE,
                titulo=f"{lacuna.contagem} {lacuna.classe} no modelo e nenhum requisito no edital",
                analise="C",
                elementos=tuple(elementos_por_classe.get(lacuna.classe, ())),
                como_agir=f"Inclua no edital uma cláusula como: {clausula_modelo}",
                por_que=(
                    "O edital não especifica nenhuma informação para essa classe. "
                    "Sem requisito, o modelo pode ser entregue sem dados essenciais e nada será verificado."
                ),
                referencias=referencias,
                classe_ifc=lacuna.classe,
                propriedades_sugeridas=sugeridas,
            )
        )
    return apontamentos


# --------------------------------------------------------------------------- saúde do modelo


def de_saude(modelo: ModeloResumo, config: sev.ConfigSeveridade) -> list[Apontamento]:
    saude = modelo.saude
    referencia = (Referencia(tipo="modelo", rotulo="Verificação de saúde do modelo (EditalCheck)"),)
    apontamentos: list[Apontamento] = []

    def novo(titulo: str, severidade, elementos=(), como_agir="", por_que="", detalhe=""):
        apontamentos.append(
            Apontamento(
                id="",
                tipo=TipoApontamento.QUALIDADE_MODELO,
                severidade=severidade,
                destinatario=Destinatario.PROJETISTA,
                titulo=titulo,
                analise="saude",
                elementos=tuple(elementos),
                como_agir=como_agir,
                por_que=por_que,
                referencias=referencia,
                detalhe=detalhe,
            )
        )

    if saude.schema.upper() not in SCHEMAS_SUPORTADOS:
        novo(
            f"Schema {saude.schema} fora dos suportados (IFC2X3, IFC4, IFC4X3)",
            sev.Severidade.MEDIA,
            como_agir="Exporte o modelo em IFC4 ou IFC2X3.",
            por_que="O IDS 1.0 só declara versões IFC2X3, IFC4 e IFC4X3_ADD2.",
        )
    if saude.proxies:
        proxies = [e.global_id for e in modelo.elementos if e.classe == "IfcBuildingElementProxy"]
        percentual = 100 * saude.proporcao_proxies
        novo(
            f"{percentual:.0f}% dos elementos são IfcBuildingElementProxy ({saude.proxies} de {saude.total_elementos})",
            sev.qualidade_modelo(saude.proporcao_proxies, False, config),
            proxies,
            "Reclassifique os elementos genéricos com a classe IFC correta (ex.: IfcFurniture, IfcWall).",
            "Elementos genéricos não recebem os Psets oficiais nem entram nas regras do IDS por classe.",
        )
    if saude.guids_duplicados:
        novo(
            f"{len(saude.guids_duplicados)} GlobalIds duplicados",
            sev.qualidade_modelo(0.0, True, config),
            saude.guids_duplicados,
            "Regere os GlobalIds duplicados na ferramenta de autoria antes de exportar.",
            "O GlobalId identifica o elemento no BCF, no IDS e no CDE. Duplicados quebram a rastreabilidade.",
        )
    if saude.sem_pavimento:
        novo(
            f"{len(saude.sem_pavimento)} elementos sem pavimento (IfcBuildingStorey)",
            sev.qualidade_modelo(0.0, False, config),
            saude.sem_pavimento,
            "Associe cada elemento a um pavimento (IfcRelContainedInSpatialStructure).",
            "Elementos fora da estrutura espacial dificultam quantitativos, filtros e a operação do ativo.",
        )
    if saude.espacos == 0:
        novo(
            "Modelo sem ambientes (IfcSpace)",
            sev.qualidade_modelo(0.0, False, config),
            como_agir="Modele os ambientes como IfcSpace com nome e uso.",
            por_que="Sem IfcSpace, requisitos de áreas, usos e ocupação não podem ser verificados.",
        )
    return apontamentos


# --------------------------------------------------------------------------- numeração


def numerar(apontamentos: Sequence[Apontamento]) -> list[Apontamento]:
    ordenados = sorted(
        apontamentos,
        key=lambda a: (
            sev.ORDEM_SEVERIDADE[a.severidade],
            _ORDEM_ANALISE.get(a.analise, 9),
            a.tipo.value,
            a.requisito_id or "",
            a.titulo,
        ),
    )
    return [replace(a, id=f"APT-{i:03d}") for i, a in enumerate(ordenados, start=1)]
