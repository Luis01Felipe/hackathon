"""Caso de uso: gerar os requisitos de informação (IR) dos tópicos selecionados.

Aplica as salvaguardas S2 a S4. As lições aprendidas também geram requisitos
propostos (RF-105), que passam pela aprovação humana como os demais.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from editalcheck.application.concorrencia import por_projeto
from editalcheck.application.consumo import ExecutorComContexto, em_projeto
from editalcheck.application.errors import EntradaInvalidaError, NaoEncontradoError
from editalcheck.application.observability import agora, etapa, logger
from editalcheck.application.ports import (
    DictionaryLookup,
    IfcModelReader,
    ProjectRepository,
    RequirementExtractor,
)
from editalcheck.domain.classificacao import classificar, limpar_ambientes
from editalcheck.domain.evidence import (
    clausula_do_trecho,
    conferir_evidencia,
    normalizar,
    remover_acentos,
)
from editalcheck.domain.models import (
    ContextoVocabulario,
    Edital,
    Eir,
    LicaoAprendida,
    OrigemVocabulario,
    Pagina,
    Projeto,
    PropriedadeOficial,
    Requisito,
    TermoDicionario,
    TipoFaceta,
    TipoRestricao,
    Topico,
)
from editalcheck.domain.restricoes import problema_no_padrao
from editalcheck.domain.topics import expandir_selecao, paginas_do_topico
from editalcheck.domain.vocabulary import classificar_origem

MAX_PARALELO = 4
AVISO_LICAO = (
    "Veio de uma lição aprendida, não do edital. Para cobrar do contratado, inclua a regra "
    "no edital."
)


@dataclass(frozen=True)
class ResultadoEir:
    eir: Eir
    avisos: tuple[str, ...]
    descartados: int


class ValidadorRequisitos:
    """Aplica as salvaguardas determinísticas S2, S3 e S4 aos requisitos."""

    def __init__(self, ifc_reader: IfcModelReader, dicionario: DictionaryLookup | None) -> None:
        self._ifc = ifc_reader
        self._dicionario = dicionario

    def contexto(
        self,
        projeto: Projeto,
        topicos: Sequence[Topico],
        vocabulario_classes: Mapping[str, Sequence[str]],
        termos_bsdd: Sequence[TermoDicionario] = (),
        classes_extras: Sequence[str] = (),
    ) -> ContextoVocabulario:
        schema = projeto.modelo.schema
        classes = [c.nome for c in projeto.modelo.classes if c.especificavel]
        texto = remover_acentos(normalizar(" ".join(t.texto for t in topicos)))
        citadas = [
            classe
            for classe, termos in vocabulario_classes.items()
            if any(remover_acentos(normalizar(t)) in texto for t in termos)
        ]
        for classe in [*citadas, *classes_extras]:
            canonica = self._ifc.canonical_class(schema, classe)
            if canonica and canonica not in classes and self._ifc.is_entity(schema, canonica):
                classes.append(canonica)
        oficiais: dict[tuple[str, str], PropriedadeOficial] = {}
        por_classe: list[tuple[str, tuple[str, ...]]] = []
        for classe in classes:
            propriedades = self._ifc.official_properties(schema, classe)
            for prop in propriedades:
                oficiais.setdefault((prop.pset, prop.nome), prop)
            por_classe.append((classe, tuple(f"{p.pset}.{p.nome}" for p in propriedades)))
        return ContextoVocabulario(
            schema=schema,
            classes_modelo=projeto.modelo.classes,
            propriedades_oficiais=tuple(oficiais.values()),
            propriedades_por_classe=tuple(por_classe),
            termos_bsdd=tuple(termos_bsdd),
            ambientes_modelo=ambientes_do_modelo(projeto),
        )

    def validar(
        self,
        requisito: Requisito,
        projeto: Projeto,
        contexto: ContextoVocabulario,
        paginas_permitidas: Sequence[int] | None,
    ) -> Requisito | None:
        """Retorna o requisito validado ou None se a citação não confere (S2)."""
        schema = projeto.modelo.schema
        evidencia = conferir_evidencia(requisito.evidencia, projeto.edital, paginas_permitidas)
        if evidencia is None:
            return None
        pagina = projeto.edital.pagina(evidencia.pagina)
        clausula = clausula_do_trecho(pagina.texto, evidencia.trecho) if pagina else None
        requisito = replace(requisito, evidencia=evidencia, clausula=clausula)
        return self.validar_mapeamento(requisito, schema, contexto)

    def validar_mapeamento(
        self, requisito: Requisito, schema: str, contexto: ContextoVocabulario
    ) -> Requisito:
        avisos = list(requisito.avisos)
        verificavel = requisito.verificavel_por_ids
        motivo = requisito.motivo_nao_verificavel

        def nao_verificavel(texto: str) -> None:
            nonlocal verificavel, motivo
            if verificavel:
                verificavel, motivo = False, texto
                avisos.append(texto)

        classe = requisito.ifc_class
        if classe:
            canonica = self._ifc.canonical_class(schema, classe)
            if canonica is None or not self._ifc.is_entity(schema, canonica):
                nao_verificavel(
                    f"A classe {classe} não existe no schema {schema} (salvaguarda S3)."
                )
            else:
                classe = canonica
        elif verificavel:
            nao_verificavel("O requisito não indica a classe IFC a que se aplica.")

        tipo_dado = requisito.tipo_dado
        if tipo_dado:
            canonico = self._ifc.canonical_class(schema, tipo_dado)
            if canonico is None or self._ifc.is_entity(schema, canonico):
                avisos.append(f"Tipo de dado {tipo_dado} inexistente no schema: removido.")
                tipo_dado = None
            else:
                tipo_dado = canonico

        restricao = requisito.restricao
        if restricao and restricao.tipo == TipoRestricao.PADRAO:
            problema = next((p for v in restricao.valores if (p := problema_no_padrao(v))), None)
            if problema:
                avisos.append(f"Restrição por padrão removida: {problema}")
                restricao = None

        faceta = requisito.faceta
        if verificavel and faceta is None:
            nao_verificavel(
                "O requisito não tem faceta IDS (propriedade, atributo, classificação...)."
            )
        if (
            verificavel
            and faceta == TipoFaceta.PROPRIEDADE
            and not (requisito.pset and requisito.propriedade)
        ):
            nao_verificavel("Falta o Pset ou o nome da propriedade.")
        if verificavel and faceta == TipoFaceta.ATRIBUTO and not requisito.propriedade:
            nao_verificavel("Falta o nome do atributo.")

        requisito = replace(
            requisito,
            ifc_class=classe,
            tipo_dado=tipo_dado,
            restricao=restricao,
            verificavel_por_ids=verificavel,
            motivo_nao_verificavel=None if verificavel else motivo,
        )
        origem, uri, aviso = classificar_origem(requisito, contexto)
        if origem == OrigemVocabulario.CUSTOMIZADO and self._dicionario and requisito.propriedade:
            for termo in self._dicionario.search(requisito.propriedade):
                if termo.nome.lower() == requisito.propriedade.lower():
                    origem, uri, aviso = OrigemVocabulario.BSDD, termo.uri, None
                    break
        if aviso:
            avisos.append(aviso)
        return replace(
            requisito, origem_vocabulario=origem, bsdd_uri=uri, avisos=tuple(dict.fromkeys(avisos))
        )


def ambientes_do_modelo(projeto: Projeto) -> tuple[str, ...]:
    """Nomes dos ambientes (IfcSpace) do modelo: LongName ou, sem ele, Name."""
    nomes = (
        e.nome_longo or e.nome or ""
        for e in projeto.modelo.elementos
        if e.classe.lower() == "ifcspace"
    )
    return limpar_ambientes(nomes)


def _chave(requisito: Requisito) -> tuple:
    return (
        (requisito.ifc_class or "").lower(),
        requisito.faceta,
        (requisito.pset or "").lower(),
        (requisito.propriedade or "").lower(),
        requisito.restricao,
        normalizar(requisito.evidencia.trecho) if not requisito.verificavel_por_ids else "",
    )


def _sem_progresso() -> None:
    return None


def numerar(requisitos: Sequence[Requisito], inicio: int = 1) -> list[Requisito]:
    return [replace(r, id=f"REQ-{i:03d}") for i, r in enumerate(requisitos, start=inicio)]


class GerarEir:
    def __init__(
        self,
        repositorio: ProjectRepository,
        validador: ValidadorRequisitos,
        extrator: RequirementExtractor,
        extrator_reserva: RequirementExtractor,
        dicionario: DictionaryLookup | None,
        vocabulario_classes: Mapping[str, Sequence[str]],
        termos_bsdd_en: Mapping[str, str],
        paralelismo: int = MAX_PARALELO,
    ) -> None:
        self._repo = repositorio
        self._validador = validador
        self._extrator = extrator
        self._reserva = extrator_reserva
        self._dicionario = dicionario
        self._vocab = vocabulario_classes
        self._en = termos_bsdd_en
        self._paralelismo = max(1, paralelismo)

    def _termos_bsdd(self, topicos: Sequence[Topico], avisos: list[str]) -> list[TermoDicionario]:
        if self._dicionario is None:
            return []
        texto = remover_acentos(normalizar(" ".join(t.texto for t in topicos)))
        consultas = [
            self._en[classe]
            for classe, termos in self._vocab.items()
            if classe in self._en and any(remover_acentos(normalizar(t)) in texto for t in termos)
        ]
        termos: dict[str, TermoDicionario] = {}
        with (
            etapa("bsdd.contexto", consultas=len(consultas)),
            ExecutorComContexto(self._paralelismo) as executor,
        ):
            for resultado in executor.map(self._dicionario.search, consultas):
                for termo in resultado:
                    termos.setdefault(termo.uri, termo)
        if consultas and not termos and getattr(self._dicionario, "falhou", False):
            avisos.append("bSDD indisponível: os IR usam só os Psets oficiais.")
        return list(termos.values())

    def _extrair(
        self, topico: Topico, contexto: ContextoVocabulario
    ) -> tuple[list[Requisito], str | None]:
        with etapa("eir.extrair", topico=topico.id) as extra:
            try:
                requisitos = self._extrator.extract(topico, contexto)
                extra["requisitos"] = len(requisitos)
                return requisitos, None
            except Exception as erro:  # RNF-02
                logger.warning("Extração pelo LLM falhou no tópico %s: %s", topico.id, erro)
                requisitos = self._reserva.extract(topico, contexto)
                extra["requisitos"] = len(requisitos)
                extra["reserva"] = True
                return (
                    requisitos,
                    f"LLM indisponível no tópico {topico.numero}: usando regras determinísticas.",
                )

    def validar_selecao(self, projeto_id: str, topico_ids: Sequence[str]) -> int:
        """Confere a seleção sem chamar o LLM e devolve quantas extrações a geração fará."""
        projeto = self._projeto(projeto_id)
        return len(self._selecionar(projeto, topico_ids)) + len(projeto.licoes)

    @por_projeto
    def executar(
        self,
        projeto_id: str,
        topico_ids: Sequence[str],
        progresso: Callable[[], None] | None = None,
    ) -> ResultadoEir:
        """Gera os IR. ``progresso`` é chamado ao fim de cada tópico e de cada lição."""
        with em_projeto(projeto_id):
            return self._executar(projeto_id, topico_ids, progresso or _sem_progresso)

    def _projeto(self, projeto_id: str) -> Projeto:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        return projeto

    @staticmethod
    def _selecionar(projeto: Projeto, topico_ids: Sequence[str]) -> list[Topico]:
        if not topico_ids or any(projeto.topico(t) is None for t in topico_ids):
            raise EntradaInvalidaError("Selecione ao menos um tópico válido.")
        # Agrupadores não têm texto próprio: entram os subtópicos deles.
        selecionados = expandir_selecao(projeto.topicos, topico_ids)
        if not selecionados:
            raise EntradaInvalidaError("Os tópicos selecionados não têm texto para verificar.")
        return selecionados

    def _executar(
        self, projeto_id: str, topico_ids: Sequence[str], progresso: Callable[[], None]
    ) -> ResultadoEir:
        projeto = self._projeto(projeto_id)
        selecionados = self._selecionar(projeto, topico_ids)

        avisos: list[str] = []
        contexto = self._validador.contexto(
            projeto, selecionados, self._vocab, self._termos_bsdd(selecionados, avisos)
        )

        def do_topico(topico: Topico) -> tuple[list[Requisito], str | None]:
            try:
                return self._extrair(topico, contexto)
            finally:
                progresso()

        def da_licao(licao: LicaoAprendida) -> tuple[list[Requisito], str | None]:
            try:
                return self._da_licao(projeto, licao)
            finally:
                progresso()

        with ExecutorComContexto(self._paralelismo) as executor:
            # Tópicos e lições entram juntos na fila: as lições não esperam o tópico mais lento.
            pendentes_topicos = executor.map(do_topico, selecionados)
            pendentes_licoes = executor.map(da_licao, projeto.licoes)
            extraidos = list(pendentes_topicos)
            das_licoes = list(pendentes_licoes)

        aprovados: list[Requisito] = []
        vistos: set[tuple] = set()
        descartados = 0
        for topico, (requisitos, aviso) in zip(selecionados, extraidos, strict=True):
            if aviso:
                avisos.append(aviso)
            paginas = list(paginas_do_topico(topico))
            for requisito in requisitos:
                validado = self._validador.validar(requisito, projeto, contexto, paginas)
                if validado is None:
                    descartados += 1
                    # O trecho não vai para o log: o edital pode ter dados do cliente.
                    logger.info(
                        "S2: citação descartada (tópico %s, p. %s)",
                        topico.id,
                        requisito.evidencia.pagina,
                    )
                    continue
                chave = _chave(validado)
                if chave in vistos:
                    continue
                vistos.add(chave)
                aprovados.append(classificar(validado, contexto.ambientes_modelo, topico.titulo))
        for requisitos, aviso in das_licoes:
            if aviso:
                avisos.append(aviso)
            for requisito in requisitos:
                chave = _chave(requisito)
                if chave in vistos:
                    continue  # o edital já exige o mesmo: a lição não duplica
                vistos.add(chave)
                aprovados.append(requisito)
        if descartados:
            avisos.append(
                f"{descartados} requisito(s) descartado(s): o trecho citado não existe no edital (salvaguarda S2)."
            )

        anteriores = projeto.eir.requisitos if projeto.eir else ()
        lacunas = [r for r in anteriores if r.sugerido_por_lacuna]
        requisitos_finais = numerar([*aprovados, *lacunas])
        eir = Eir(
            versao=(projeto.eir.versao + 1) if projeto.eir else 1,
            data=agora(),
            topicos_selecionados=tuple(t.id for t in selecionados),
            requisitos=tuple(requisitos_finais),
        )
        projeto.eir = eir
        projeto.ids_gerado = False
        self._repo.save(projeto)
        return ResultadoEir(eir=eir, avisos=tuple(avisos), descartados=descartados)

    def _da_licao(
        self, projeto: Projeto, licao: LicaoAprendida
    ) -> tuple[list[Requisito], str | None]:
        """Requisitos propostos a partir de uma lição aprendida (RF-105).

        O extrator lê a regra como se fosse um tópico. A citação é conferida contra
        o próprio texto da lição; a evidência final é o trecho literal do documento
        de lições, já conferido na importação.
        """
        pagina = licao.evidencia.pagina
        texto = f"{licao.evidencia.trecho}\n{licao.regra}"
        topico = Topico(
            id=licao.id,
            numero=licao.id,
            titulo=f"Lição aprendida: {licao.titulo}",
            nivel=1,
            pagina_inicio=pagina,
            pagina_fim=pagina,
            texto=f"[p. {pagina}]\n{texto}",
            relevante_bim=True,
        )
        fonte = Edital(arquivo=licao.documento, paginas=(Pagina(numero=pagina, texto=texto),))
        extras = [licao.ifc_class] if licao.ifc_class else []
        contexto = self._validador.contexto(projeto, [topico], self._vocab, classes_extras=extras)
        requisitos, aviso = self._extrair(topico, contexto)
        validados: list[Requisito] = []
        for requisito in requisitos:
            if conferir_evidencia(requisito.evidencia, fonte) is None:
                continue
            ajustado = replace(
                requisito,
                topico_id="LICOES",
                evidencia=licao.evidencia,
                clausula=None,
                gerado_por="licao",
                licao_id=licao.id,
                avisos=(*requisito.avisos, AVISO_LICAO),
            )
            validado = self._validador.validar_mapeamento(ajustado, projeto.modelo.schema, contexto)
            validados.append(classificar(validado, contexto.ambientes_modelo, licao.titulo))
        return validados, (f"Lição {licao.id}: {aviso}" if aviso else None)
