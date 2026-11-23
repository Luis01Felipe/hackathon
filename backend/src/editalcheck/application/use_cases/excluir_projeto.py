"""Caso de uso: encerrar o projeto e apagar todos os dados dele (RF-094)."""

from collections.abc import Callable, Mapping

from editalcheck.application.consumo import MedidorConsumo
from editalcheck.application.errors import NaoEncontradoError
from editalcheck.application.ports import AuditLog, ProjectRepository
from editalcheck.application.use_cases.importar_documentos import ARQUIVO_EDITAL, ARQUIVO_MODELO


class ExcluirProjeto:
    def __init__(
        self,
        repositorio: ProjectRepository,
        medidor: MedidorConsumo,
        auditoria: AuditLog,
        ao_apagar: Callable[[str, Mapping[str, bytes]], None] | None = None,
    ) -> None:
        self._repo = repositorio
        self._medidor = medidor
        self._auditoria = auditoria
        self._ao_apagar = ao_apagar

    def executar(self, projeto_id: str) -> None:
        arquivos = {
            nome: conteudo
            for nome in (ARQUIVO_EDITAL, ARQUIVO_MODELO)
            if (conteudo := self._repo.read_file(projeto_id, nome)) is not None
        }
        if not self._repo.delete(projeto_id):
            raise NaoEncontradoError("Projeto não encontrado (já apagado ou expirado).")
        # Caches em memória (IFC aberto, PDF indexado, PDFs anotados) saem junto.
        if self._ao_apagar:
            self._ao_apagar(projeto_id, arquivos)
        self._medidor.esquecer(projeto_id)
        self._auditoria.record("projeto.apagar", projeto=projeto_id)
