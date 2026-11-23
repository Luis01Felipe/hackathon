"""Caso de uso: ler o documento de lições aprendidas (TXT ou PDF) — RF-100 a RF-103.

As lições entram como quarta entrada (ciclo PDCA). Cada lição cita um trecho
literal do documento, conferido por código (S2). As lições só acrescentam
verificações: nunca removem nem rebaixam apontamentos (salvaguarda G1).
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import PurePath

from editalcheck.application.consumo import em_projeto
from editalcheck.application.errors import EntradaInvalidaError, NaoEncontradoError
from editalcheck.application.observability import etapa, logger
from editalcheck.application.ports import (
    AuditLog,
    EditalReader,
    LessonExtractor,
    ProjectRepository,
)
from editalcheck.domain import licoes as licoes_domain
from editalcheck.domain.evidence import conferir_evidencia
from editalcheck.domain.models import Edital, LicaoAprendida, Projeto

EXTENSOES_LICOES = (".txt", ".md", ".pdf")
MAX_DOCUMENTOS = 10


@dataclass(frozen=True)
class ResultadoLicoes:
    licoes: tuple[LicaoAprendida, ...]
    avisos: tuple[str, ...]
    descartadas: int


def validar_arquivos(arquivos: Sequence[tuple[bytes, str]]) -> None:
    if len(arquivos) > MAX_DOCUMENTOS:
        raise EntradaInvalidaError(f"Envie até {MAX_DOCUMENTOS} documentos de lições aprendidas.")
    for conteudo, nome in arquivos:
        if PurePath(nome).suffix.lower() not in EXTENSOES_LICOES:
            raise EntradaInvalidaError(
                f"Lições aprendidas: envie arquivos .txt, .md ou .pdf ({nome} não é aceito)."
            )
        if not conteudo.strip():
            raise EntradaInvalidaError(f"O arquivo de lições {nome} está vazio.")


class ImportarLicoes:
    def __init__(
        self,
        repositorio: ProjectRepository,
        leitor: EditalReader,
        extrator: LessonExtractor,
        extrator_reserva: LessonExtractor,
        auditoria: AuditLog,
    ) -> None:
        self._repo = repositorio
        self._leitor = leitor
        self._extrator = extrator
        self._reserva = extrator_reserva
        self._auditoria = auditoria

    def executar(self, projeto_id: str, arquivos: Sequence[tuple[bytes, str]]) -> ResultadoLicoes:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        with em_projeto(projeto_id):
            resultado = self.adicionar(projeto, arquivos)
        self._repo.save(projeto)
        return resultado

    def adicionar(self, projeto: Projeto, arquivos: Sequence[tuple[bytes, str]]) -> ResultadoLicoes:
        """Lê os documentos e substitui as lições de documentos com o mesmo nome."""
        validar_arquivos(arquivos)
        avisos: list[str] = []
        descartadas = 0
        novos_documentos: list[Edital] = []
        novas: list[LicaoAprendida] = []
        for conteudo, nome in arquivos:
            try:
                documento = self._leitor.read(conteudo, PurePath(nome).name)
            except ValueError as erro:
                raise EntradaInvalidaError(str(erro)) from erro
            lidas, aviso, perdidas = self._extrair(documento)
            descartadas += perdidas
            if aviso:
                avisos.append(aviso)
            if not lidas:
                avisos.append(f"Nenhuma lição encontrada em {documento.arquivo}.")
            novos_documentos.append(documento)
            novas.extend(lidas)

        nomes = {d.arquivo for d in novos_documentos}
        mantidas = [licao for licao in projeto.licoes if licao.documento not in nomes]
        projeto.documentos_licoes = (
            *(d for d in projeto.documentos_licoes if d.arquivo not in nomes),
            *novos_documentos,
        )
        projeto.licoes = tuple(licoes_domain.numerar([*mantidas, *novas]))
        if descartadas:
            avisos.append(
                f"{descartadas} lição(ões) descartada(s): o trecho citado não existe no "
                "documento (salvaguarda S2)."
            )
        self._auditoria.record(
            "licoes.importar",
            projeto=projeto.id,
            documentos=len(novos_documentos),
            licoes=len(projeto.licoes),
            bytes=sum(len(c) for c, _ in arquivos),
        )
        return ResultadoLicoes(projeto.licoes, tuple(avisos), descartadas)

    def _extrair(self, documento: Edital) -> tuple[list[LicaoAprendida], str | None, int]:
        with etapa("licoes.extrair", documento=documento.arquivo) as extra:
            aviso = None
            try:
                brutas = self._extrator.extract(documento)
            except Exception as erro:  # RNF-02: falha do LLM não derruba o fluxo
                logger.warning("Leitura das lições pelo LLM falhou: %s", erro)
                brutas = self._reserva.extract(documento)
                aviso = f"LLM indisponível nas lições de {documento.arquivo}: usando regras."
            conferidas: list[LicaoAprendida] = []
            for licao in brutas:
                evidencia = conferir_evidencia(licao.evidencia, documento)
                if evidencia is None:
                    continue
                conferidas.append(replace(licao, evidencia=evidencia, documento=documento.arquivo))
            perdidas = len(brutas) - len(conferidas)
            if brutas and not conferidas:
                conferidas = self._reserva.extract(documento)
                aviso = f"Nenhuma citação do LLM conferiu em {documento.arquivo}: usando regras."
            extra["licoes"] = len(conferidas)
            return conferidas, aviso, perdidas
