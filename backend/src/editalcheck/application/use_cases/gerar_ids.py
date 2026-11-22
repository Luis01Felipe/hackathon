"""Caso de uso: gerar o IDS do EIR aprovado (RF-30 a RF-33) com a salvaguarda S6."""

from dataclasses import dataclass, replace

from editalcheck.application.errors import ConflitoError, NaoEncontradoError
from editalcheck.application.observability import etapa
from editalcheck.application.ports import IdsBuilder, ProjectRepository

ARQUIVO_IDS = "ids.xml"


@dataclass(frozen=True)
class ResultadoIds:
    especificacoes: int
    valido: bool
    erros: tuple[str, ...]
    requisitos_incluidos: tuple[str, ...]


class GerarIds:
    def __init__(self, repositorio: ProjectRepository, construtor: IdsBuilder) -> None:
        self._repo = repositorio
        self._construtor = construtor

    def executar(self, projeto_id: str) -> ResultadoIds:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        if projeto.eir is None or not projeto.eir.requisitos_para_ids:
            raise ConflitoError(
                "Aprove ao menos um requisito verificável por IDS antes de gerar o IDS."
            )
        eir = projeto.eir
        titulo = f"EditalCheck — {projeto.edital.arquivo}"
        incluidos = tuple(r.id for r in eir.requisitos_para_ids)

        with etapa("ids.gerar", projeto=projeto_id, especificacoes=len(incluidos)) as extra:
            erros = self._problemas(eir, projeto.modelo.schema, titulo)
            if erros:
                extra["erros"] = len(erros)
                projeto.ids_gerado = False
                self._repo.save(projeto)
                return ResultadoIds(len(incluidos), False, tuple(erros), incluidos)
            xml = self._construtor.build(eir, projeto.modelo.schema, titulo)

        self._repo.write_file(projeto_id, ARQUIVO_IDS, xml)
        projeto.ids_gerado = True
        self._repo.save(projeto)
        return ResultadoIds(len(incluidos), True, (), incluidos)

    def _problemas(self, eir, schema: str, titulo: str) -> list[str]:
        """S6: gera e recarrega o IDS; se falhar, isola cada requisito problemático."""
        try:
            erros = self._construtor.check(self._construtor.build(eir, schema, titulo))
        except ValueError as erro:
            erros = [str(erro)]
        if not erros:
            return []
        problemas: list[str] = []
        for requisito in eir.requisitos_para_ids:
            sozinho = replace(eir, requisitos=(requisito,))
            try:
                individuais = self._construtor.check(
                    self._construtor.build(sozinho, schema, titulo)
                )
            except ValueError as erro:
                individuais = [str(erro)]
            problemas.extend(f"{requisito.id}: {e}" for e in individuais)
        return problemas or erros
