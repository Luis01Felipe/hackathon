"""Caso de uso: executar as análises A, B e C, as lições aprendidas e a saúde do modelo.

As análises são independentes: a falha de uma não impede as outras (seção 8.5).
Sem modelo IFC (modo "revisar edital"), só rodam a análise B e as lições.
"""

import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from threading import Lock

from editalcheck.application.consumo import ExecutorComContexto, em_projeto
from editalcheck.application.errors import NaoEncontradoError
from editalcheck.application.observability import agora, etapa, logger
from editalcheck.application.ports import (
    AuditLog,
    EditalAnalyzer,
    ElementGeometry,
    IfcModelReader,
    IfcValidator,
    LessonChecker,
    ProjectRepository,
)
from editalcheck.application.use_cases.gerar_ids import ARQUIVO_IDS, GerarIds
from editalcheck.application.use_cases.gerar_relatorio import GerarRelatorio, ResultadosAnalises
from editalcheck.application.use_cases.importar_documentos import ARQUIVO_MODELO
from editalcheck.domain import checklist as checklist_domain
from editalcheck.domain import coverage, duplicidade, findings, licoes, vagueness, versao_ifc
from editalcheck.domain.evidence import conferir_evidencia
from editalcheck.domain.models import (
    AmbiguidadeConfirmada,
    Apontamento,
    Cobertura,
    Contradicao,
    ItemChecklist,
    Projeto,
    ResultadoChecklist,
    ResultadoEspecificacao,
    StatusVerificacao,
    TermoVago,
    Topico,
    Verificacao,
    VerificacaoLicao,
)
from editalcheck.domain.severity import ConfigSeveridade

ANALISES = ("conformidade", "qualidade_edital", "licoes", "cobertura", "saude_modelo")
SO_COM_MODELO = frozenset({"conformidade", "cobertura", "saude_modelo"})


@dataclass
class _Coletor:
    resultados_ids: tuple[ResultadoEspecificacao, ...] = ()
    cobertura: Cobertura | None = None
    checklist: tuple[ResultadoChecklist, ...] = ()
    verificacoes_licoes: tuple[VerificacaoLicao, ...] = ()
    apontamentos: list[Apontamento] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    duracoes: dict[str, float] = field(default_factory=dict)


class ExecutarVerificacao:
    def __init__(
        self,
        repositorio: ProjectRepository,
        ifc_reader: IfcModelReader,
        validador_ifc: IfcValidator,
        analisador: EditalAnalyzer,
        analisador_reserva: EditalAnalyzer,
        gerar_ids: GerarIds,
        gerar_relatorio: GerarRelatorio,
        termos_vagos: Sequence[TermoVago],
        itens_checklist: Sequence[ItemChecklist],
        config_severidade: ConfigSeveridade,
        verificador_licoes: LessonChecker,
        verificador_licoes_reserva: LessonChecker,
        auditoria: AuditLog,
        geometria: ElementGeometry,
    ) -> None:
        self._repo = repositorio
        self._ifc = ifc_reader
        self._validador = validador_ifc
        self._analisador = analisador
        self._reserva = analisador_reserva
        self._gerar_ids = gerar_ids
        self._relatorio = gerar_relatorio
        self._termos = list(termos_vagos)
        self._itens = list(itens_checklist)
        self._config = config_severidade
        self._licoes = verificador_licoes
        self._licoes_reserva = verificador_licoes_reserva
        self._auditoria = auditoria
        self._geometria = geometria
        self._trava = Lock()

    # ------------------------------------------------------------------ ciclo de vida

    def iniciar(self, projeto_id: str) -> Verificacao:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        verificacao = Verificacao(
            id=uuid.uuid4().hex[:10],
            projeto_id=projeto_id,
            status=StatusVerificacao.PENDENTE,
            progresso={
                nome: "ignorada"
                if projeto.modelo.sem_arquivo and nome in SO_COM_MODELO
                else "pendente"
                for nome in (*ANALISES, "relatorio")
            },
            iniciado_em=agora(),
        )
        self._repo.save_verificacao(verificacao)
        return verificacao

    def _progresso(self, verificacao: Verificacao, analise: str, estado: str) -> None:
        with self._trava:
            verificacao.progresso[analise] = estado
            self._repo.save_verificacao(verificacao)

    def executar(self, verificacao_id: str) -> Verificacao:
        verificacao = self._repo.get_verificacao(verificacao_id)
        if verificacao is None:
            raise NaoEncontradoError("Verificação não encontrada.")
        with em_projeto(verificacao.projeto_id):
            return self._executar(verificacao)

    def _executar(self, verificacao: Verificacao) -> Verificacao:
        projeto = self._repo.get(verificacao.projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        verificacao.status = StatusVerificacao.EXECUTANDO
        self._repo.save_verificacao(verificacao)
        coletor = _Coletor()
        try:
            with etapa("verificacao", verificacao=verificacao.id, projeto=projeto.id):
                self._rodar_analises(verificacao, projeto, coletor)
                self._progresso(verificacao, "relatorio", "executando")
                relatorio = self._relatorio.montar(
                    verificacao.id,
                    projeto,
                    ResultadosAnalises(
                        resultados_ids=coletor.resultados_ids,
                        cobertura=coletor.cobertura,
                        checklist=coletor.checklist,
                        apontamentos=tuple(coletor.apontamentos),
                        verificacoes_licoes=coletor.verificacoes_licoes,
                    ),
                    coletor.avisos,
                    coletor.duracoes,
                    self._repo.read_file(projeto.id, ARQUIVO_MODELO),
                )
                relatorio = self._relatorio.publicar(relatorio, projeto.modelo)
                self._progresso(verificacao, "relatorio", "concluida")
            verificacao.status = StatusVerificacao.CONCLUIDA
            verificacao.avisos = relatorio.avisos
        except Exception as erro:
            logger.exception("Verificação %s falhou", verificacao.id)
            verificacao.status = StatusVerificacao.FALHOU
            verificacao.erro = f"Falha ao montar o relatório: {erro}"
            verificacao.avisos = tuple(coletor.avisos)
        verificacao.concluido_em = agora()
        self._repo.save_verificacao(verificacao)
        self._auditoria.record(
            "verificacao.concluir",
            projeto=projeto.id,
            verificacao=verificacao.id,
            status=verificacao.status.value,
        )
        return verificacao

    def _rodar_analises(
        self, verificacao: Verificacao, projeto: Projeto, coletor: _Coletor
    ) -> None:
        tarefas: dict[str, Callable[[], str | None]] = {
            "conformidade": lambda: self._conformidade(projeto, coletor),
            "qualidade_edital": lambda: self._qualidade_edital(projeto, coletor),
            "licoes": lambda: self._licoes_aprendidas(projeto, coletor),
            "cobertura": lambda: self._cobertura(projeto, coletor),
            "saude_modelo": lambda: self._saude(projeto, coletor),
        }
        if projeto.modelo.sem_arquivo:
            tarefas = {nome: f for nome, f in tarefas.items() if nome not in SO_COM_MODELO}

        def rodar(nome: str) -> None:
            self._progresso(verificacao, nome, "executando")
            inicio = time.perf_counter()
            try:
                with etapa(f"analise.{nome}", verificacao=verificacao.id):
                    estado = tarefas[nome]() or "concluida"
            except Exception as erro:
                logger.exception("Análise %s falhou", nome)
                with self._trava:
                    coletor.avisos.append(f"A análise '{nome}' falhou: {erro}")
                estado = "falhou"
            with self._trava:
                coletor.duracoes[nome] = round(time.perf_counter() - inicio, 3)
            self._progresso(verificacao, nome, estado)

        with ExecutorComContexto(len(tarefas)) as executor:
            list(executor.map(rodar, tarefas))

    def _adicionar(
        self, coletor: _Coletor, apontamentos: Sequence[Apontamento], avisos: Sequence[str] = ()
    ) -> None:
        with self._trava:
            coletor.apontamentos.extend(apontamentos)
            coletor.avisos.extend(avisos)

    # ------------------------------------------------------------------ análise A

    def _conformidade(self, projeto: Projeto, coletor: _Coletor) -> str | None:
        eir = projeto.eir
        if eir is None or not eir.requisitos_para_ids:
            self._adicionar(
                coletor,
                [],
                ["Análise A ignorada: não há requisito aprovado e verificável por IDS."],
            )
            return "ignorada"
        if not projeto.ids_gerado or self._repo.read_file(projeto.id, ARQUIVO_IDS) is None:
            resultado = self._gerar_ids.executar(
                projeto.id, projeto.ids_marco_id, projeto.ids_versao_ifc
            )
            if not resultado.valido:
                self._adicionar(coletor, [], [f"IDS inválido (S6): {'; '.join(resultado.erros)}"])
                return "falhou"
            projeto = self._repo.get(projeto.id) or projeto
        ids_xml = self._repo.read_file(projeto.id, ARQUIVO_IDS) or b""
        resultados = self._validador.validate(
            ids_xml, self._repo.read_file(projeto.id, ARQUIVO_MODELO) or b""
        )
        with self._trava:
            coletor.resultados_ids = tuple(resultados)
        sem_elementos = [r.requisito_id for r in resultados if r.aplicaveis == 0 and r.requisito_id]
        avisos = (
            [f"Requisitos sem elementos aplicáveis no modelo: {', '.join(sem_elementos)}."]
            if sem_elementos
            else []
        )
        self._adicionar(coletor, findings.de_resultados_ids(resultados, eir.requisitos), avisos)
        return None

    # ------------------------------------------------------------------ análise B

    def _topicos_alvo(self, projeto: Projeto) -> list[Topico]:
        selecionados = set(projeto.eir.topicos_selecionados) if projeto.eir else set()
        return [t for t in projeto.topicos if t.relevante_bim or t.id in selecionados]

    def _com_reserva(self, nome: str, primario: Callable, reserva: Callable, avisos: list[str]):
        try:
            return primario()
        except Exception as erro:  # RNF-02
            logger.warning("%s pelo LLM falhou: %s", nome, erro)
            avisos.append(f"LLM indisponível em '{nome}': usando regras determinísticas.")
            return reserva()

    def _qualidade_edital(self, projeto: Projeto, coletor: _Coletor) -> None:
        avisos: list[str] = []
        topicos = self._topicos_alvo(projeto)
        requisitos = projeto.eir.requisitos if projeto.eir else ()
        candidatos = vagueness.detectar(
            projeto.edital, self._termos, projeto.topicos, [t.id for t in topicos]
        )
        # As três consultas são independentes: rodam em paralelo (cada uma com reserva).
        with ExecutorComContexto(3) as executor:
            futuro_ambiguidade = executor.submit(
                self._com_reserva,
                "ambiguidade",
                lambda: self._analisador.confirm_vagueness(candidatos) if candidatos else [],
                lambda: self._reserva.confirm_vagueness(candidatos),
                avisos,
            )
            futuro_checklist = executor.submit(
                self._com_reserva,
                "checklist",
                lambda: self._analisador.evaluate_checklist(projeto.edital, topicos, self._itens),
                lambda: self._reserva.evaluate_checklist(projeto.edital, topicos, self._itens),
                avisos,
            )
            futuro_contradicoes = executor.submit(
                self._com_reserva,
                "contradicoes",
                lambda: self._analisador.find_contradictions(topicos),
                lambda: self._reserva.find_contradictions(topicos),
                avisos,
            )
            confirmadas: list[AmbiguidadeConfirmada] = futuro_ambiguidade.result()
            brutos: list[ResultadoChecklist] = futuro_checklist.result()
            contradicoes: list[Contradicao] = futuro_contradicoes.result()

        checklist = checklist_domain.completar(
            checklist_domain.aplicar_salvaguarda(brutos, projeto.edital), self._itens
        )
        with self._trava:
            coletor.checklist = tuple(checklist)
        conferidas = [
            c
            for c in contradicoes
            if conferir_evidencia(c.evidencia_a, projeto.edital)
            and conferir_evidencia(c.evidencia_b, projeto.edital)
        ]
        apontamentos = [
            *findings.de_ambiguidades(confirmadas, requisitos),
            *findings.de_nao_verificaveis(requisitos),
            *findings.de_checklist(checklist, self._itens),
            *findings.de_contradicoes(conferidas),
            *findings.de_duplicidades(duplicidade.encontrar(topicos)),
        ]
        self._adicionar(coletor, apontamentos, avisos)

    # ------------------------------------------------------------------ lições aprendidas

    def _licoes_aprendidas(self, projeto: Projeto, coletor: _Coletor) -> str | None:
        """RF-104 a RF-106. As lições só acrescentam apontamentos (G1)."""
        if not projeto.licoes:
            return "ignorada"
        avisos: list[str] = []
        topicos = self._topicos_alvo(projeto) or [t for t in projeto.topicos if not t.agrupador]
        brutos = self._com_reserva(
            "lições aprendidas",
            lambda: self._licoes.check(projeto.licoes, projeto.edital, topicos),
            lambda: self._licoes_reserva.check(projeto.licoes, projeto.edital, topicos),
            avisos,
        )
        respondidas = {v.licao_id for v in brutos}
        faltantes = [licao for licao in projeto.licoes if licao.id not in respondidas]
        if faltantes:
            brutos = [*brutos, *self._licoes_reserva.check(faltantes, projeto.edital, topicos)]
        verificacoes = [self._conferir_licao(v, projeto) for v in brutos]
        candidatos = {
            licao.id: licoes.elementos_candidatos(licao, projeto.modelo) for licao in projeto.licoes
        }
        proibidos = self._proibidos_no_modelo(projeto, candidatos, avisos)
        with self._trava:
            coletor.verificacoes_licoes = tuple(verificacoes)
        self._adicionar(
            coletor,
            findings.de_licoes(projeto.licoes, verificacoes, candidatos, proibidos),
            avisos,
        )
        return None

    def _proibidos_no_modelo(
        self, projeto: Projeto, candidatos: dict[str, tuple[str, ...]], avisos: list[str]
    ) -> dict[str, tuple[str, ...]]:
        """Elementos que a lição proíbe e que tocam o ambiente citado (ex.: janelas na
        sala de baterias). Checagem geométrica simples, por caixa envolvente."""
        alvos = {
            licao.id: licoes.classes_proibidas(licao)
            for licao in projeto.licoes
            if candidatos.get(licao.id) and licoes.classes_proibidas(licao)
        }
        conteudo = self._repo.read_file(projeto.id, ARQUIVO_MODELO)
        if not alvos or not conteudo:
            return {}
        classes = {c for lista in alvos.values() for c in lista}
        suspeitos = [e.global_id for e in projeto.modelo.elementos if e.classe in classes]
        ambientes = [g for lista in candidatos.values() for g in lista]
        try:
            caixas = self._geometria.boxes(conteudo, [*ambientes, *suspeitos])
        except Exception as erro:  # a checagem geométrica é um extra
            logger.warning("Checagem geométrica das lições falhou: %s", erro)
            avisos.append("Não foi possível conferir a geometria dos ambientes das lições.")
            return {}
        classe_de = {e.global_id: e.classe for e in projeto.modelo.elementos}
        encontrados: dict[str, tuple[str, ...]] = {}
        for licao_id, proibidas in alvos.items():
            dos_tipos = {
                g: caixas[g] for g in suspeitos if g in caixas and classe_de[g] in proibidas
            }
            tocam = [
                guid
                for ambiente in candidatos[licao_id]
                if ambiente in caixas
                for guid in licoes.elementos_no_ambiente(caixas[ambiente], dos_tipos)
            ]
            if tocam:
                encontrados[licao_id] = tuple(dict.fromkeys(tocam))
        return encontrados

    @staticmethod
    def _conferir_licao(verificacao: VerificacaoLicao, projeto: Projeto) -> VerificacaoLicao:
        """S2: sem trecho conferido no edital, a lição não conta como explícita."""
        evidencia = (
            conferir_evidencia(verificacao.evidencia, projeto.edital)
            if verificacao.evidencia
            else None
        )
        relacionado = (
            conferir_evidencia(verificacao.trecho_relacionado, projeto.edital)
            if verificacao.trecho_relacionado
            else None
        )
        explicita = verificacao.explicita and evidencia is not None
        return replace(
            verificacao,
            explicita=explicita,
            evidencia=evidencia if explicita else None,
            trecho_relacionado=None if explicita else relacionado,
        )

    # ------------------------------------------------------------------ análise C

    def _cobertura(self, projeto: Projeto, coletor: _Coletor) -> None:
        requisitos = projeto.eir.requisitos if projeto.eir else ()
        resultado = coverage.calcular(projeto.modelo.classes, requisitos)
        schema = projeto.modelo.schema
        sugestoes = {
            lacuna.classe: coverage.sugerir_propriedades(
                lacuna.classe, self._ifc.official_properties(schema, lacuna.classe)
            )
            for lacuna in resultado.lacunas
        }
        elementos: dict[str, list[str]] = {}
        for elemento in projeto.modelo.elementos:
            elementos.setdefault(elemento.classe, []).append(elemento.global_id)
        with self._trava:
            coletor.cobertura = resultado
        self._adicionar(coletor, findings.de_lacunas(resultado, sugestoes, elementos, self._config))

    # ------------------------------------------------------------------ saúde

    def _saude(self, projeto: Projeto, coletor: _Coletor) -> None:
        schema = projeto.modelo.schema
        self._adicionar(
            coletor,
            [
                *findings.de_saude(projeto.modelo, self._config),
                *findings.de_versao_exigida(
                    schema, versao_ifc.exigida(projeto.edital), versao_ifc.canonica(schema)
                ),
            ],
        )
