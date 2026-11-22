"""Caso de uso: gerar o EIR dos tópicos selecionados, com salvaguardas S2–S4."""

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace

from editalcheck.application.errors import EntradaInvalidaError, NaoEncontradoError
from editalcheck.application.observability import agora, etapa, logger
from editalcheck.application.ports import (
    DictionaryLookup,
    IfcModelReader,
    ProjectRepository,
    RequirementExtractor,
)
from editalcheck.domain.evidence import (
    clausula_do_trecho,
    conferir_evidencia,
    normalizar,
    remover_acentos,
)
from editalcheck.domain.models import (
    ContextoVocabulario,
    Eir,
    OrigemVocabulario,
    Projeto,
    PropriedadeOficial,
    Requisito,
    TermoDicionario,
    TipoFaceta,
    Topico,
)
from editalcheck.domain.topics import expandir_selecao, paginas_do_topico
from editalcheck.domain.vocabulary import classificar_origem

MAX_PARALELO = 4


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


def _chave(requisito: Requisito) -> tuple:
    return (
        (requisito.ifc_class or "").lower(),
        requisito.faceta,
        (requisito.pset or "").lower(),
        (requisito.propriedade or "").lower(),
        requisito.restricao,
        normalizar(requisito.evidencia.trecho) if not requisito.verificavel_por_ids else "",
    )


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
            ThreadPoolExecutor(self._paralelismo) as executor,
        ):
            for resultado in executor.map(self._dicionario.search, consultas):
                for termo in resultado:
                    termos.setdefault(termo.uri, termo)
        if consultas and not termos and getattr(self._dicionario, "falhou", False):
            avisos.append("bSDD indisponível: o EIR usa só os Psets oficiais.")
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

    def executar(self, projeto_id: str, topico_ids: Sequence[str]) -> ResultadoEir:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        if not topico_ids or any(projeto.topico(t) is None for t in topico_ids):
            raise EntradaInvalidaError("Selecione ao menos um tópico válido.")
        # Agrupadores não têm texto próprio: entram os subtópicos deles.
        selecionados = expandir_selecao(projeto.topicos, topico_ids)
        if not selecionados:
            raise EntradaInvalidaError("Os tópicos selecionados não têm texto para verificar.")

        avisos: list[str] = []
        contexto = self._validador.contexto(
            projeto, selecionados, self._vocab, self._termos_bsdd(selecionados, avisos)
        )
        with ThreadPoolExecutor(self._paralelismo) as executor:
            extraidos = list(executor.map(lambda t: self._extrair(t, contexto), selecionados))

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
                    logger.info(
                        "S2: citação descartada (p. %s): %.80s",
                        requisito.evidencia.pagina,
                        requisito.evidencia.trecho,
                    )
                    continue
                chave = _chave(validado)
                if chave in vistos:
                    continue
                vistos.add(chave)
                aprovados.append(validado)
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
