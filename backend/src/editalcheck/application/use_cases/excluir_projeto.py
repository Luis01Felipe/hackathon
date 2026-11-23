"""Caso de uso: encerrar o projeto e apagar todos os dados dele (RF-094)."""

from collections.abc import Callable

from editalcheck.application.consumo import MedidorConsumo
from editalcheck.application.errors import NaoEncontradoError
from editalcheck.application.ports import AuditLog, ProjectRepository
from editalcheck.application.use_cases.importar_documentos import ARQUIVO_MODELO


class ExcluirProjeto:
    def __init__(
        self,
        repositorio: ProjectRepository,
        medidor: MedidorConsumo,
        auditoria: AuditLog,
        esquecer_ifc: Callable[[bytes], None] | None = None,
    ) -> None:
        self._repo = repositorio
        self._medidor = medidor
        self._auditoria = auditoria
        self._esquecer_ifc = esquecer_ifc

    def executar(self, projeto_id: str) -> None:
        ifc = self._repo.read_file(projeto_id, ARQUIVO_MODELO)
        if not self._repo.delete(projeto_id):
            raise NaoEncontradoError("Projeto não encontrado (já apagado ou expirado).")
        if ifc is not None and self._esquecer_ifc:
            self._esquecer_ifc(ifc)
        self._medidor.esquecer(projeto_id)
        self._auditoria.record("projeto.apagar", projeto=projeto_id)
