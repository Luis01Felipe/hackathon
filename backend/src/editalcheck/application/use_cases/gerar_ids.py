"""Caso de uso: gerar o IDS dos requisitos de informação aprovados (RF-30 a RF-33).

O IDS pode cobrir o contrato inteiro ou um marco de entrega (RF-130b), e a
versão IFC pode ser escolhida (RF-131). A salvaguarda S6 recarrega o IDS no
XSD oficial e no ifctester antes de liberar a verificação.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from editalcheck.application.errors import ConflitoError, EntradaInvalidaError, NaoEncontradoError
from editalcheck.application.observability import etapa
from editalcheck.application.ports import AuditLog, IdsBuilder, ProjectRepository
from editalcheck.domain import versao_ifc
from editalcheck.domain.models import Eir, Projeto, Requisito

ARQUIVO_IDS = "ids.xml"


@dataclass(frozen=True)
class ResultadoIds:
    especificacoes: int
    valido: bool
    erros: tuple[str, ...]
    requisitos_incluidos: tuple[str, ...]
    escopo: str = "Contrato inteiro"
    marco_id: str | None = None
    versao_ifc: str = ""
    avisos: tuple[str, ...] = ()


def versao_padrao(projeto: Projeto) -> str:
    """Versão do modelo; sem modelo, a versão exigida no edital (ou IFC4)."""
    if not projeto.modelo.sem_arquivo:
        return versao_ifc.canonica(projeto.modelo.schema)
    exigida = versao_ifc.exigida(projeto.edital)
    return exigida[0] if exigida else versao_ifc.canonica(projeto.modelo.schema)


class GerarIds:
    def __init__(
        self, repositorio: ProjectRepository, construtor: IdsBuilder, auditoria: AuditLog
    ) -> None:
        self._repo = repositorio
        self._construtor = construtor
        self._auditoria = auditoria

    def executar(
        self, projeto_id: str, marco_id: str | None = None, versao: str | None = None
    ) -> ResultadoIds:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        if projeto.eir is None or not projeto.eir.requisitos_para_ids:
            raise ConflitoError(
                "Aprove ao menos um requisito verificável por IDS antes de gerar o IDS."
            )
        marco = projeto.marco(marco_id) if marco_id else None
        if marco_id and marco is None:
            raise EntradaInvalidaError(f"Marco de entrega {marco_id} não encontrado.")
        versao = versao or versao_padrao(projeto)
        if versao not in versao_ifc.VERSOES_IDS:
            raise EntradaInvalidaError(
                f"Versão IFC inválida: {versao} (use {', '.join(versao_ifc.VERSOES_IDS)})."
            )
        eir = projeto.eir
        requisitos = eir.requisitos_do_marco(marco_id)
        if not requisitos:
            raise ConflitoError("Nenhum requisito aprovado e verificável se aplica a este marco.")
        escopo = marco.nome if marco else "Contrato inteiro"
        titulo = f"EditalCheck — {projeto.edital.arquivo} — {escopo}"
        incluidos = tuple(r.id for r in requisitos)
        avisos = self._avisos(projeto, versao)

        with etapa("ids.gerar", projeto=projeto_id, especificacoes=len(incluidos)) as extra:
            erros = self._problemas(eir, requisitos, versao, titulo, escopo)
            if erros:
                extra["erros"] = len(erros)
                projeto.ids_gerado = False
                self._repo.save(projeto)
                return ResultadoIds(
                    len(incluidos), False, tuple(erros), incluidos, escopo, marco_id, versao, avisos
                )
            xml = self._construtor.build(eir, versao, titulo, escopo, requisitos)

        self._repo.write_file(projeto_id, ARQUIVO_IDS, xml)
        projeto.ids_gerado = True
        projeto.ids_marco_id = marco_id
        projeto.ids_versao_ifc = versao
        self._repo.save(projeto)
        self._auditoria.record(
            "ids.gerar", projeto=projeto_id, especificacoes=len(incluidos), versao=versao
        )
        return ResultadoIds(len(incluidos), True, (), incluidos, escopo, marco_id, versao, avisos)

    def _avisos(self, projeto: Projeto, versao: str) -> tuple[str, ...]:
        if projeto.modelo.sem_arquivo:
            return ()
        do_modelo = versao_ifc.canonica(projeto.modelo.schema)
        if versao == do_modelo:
            return ()
        return (
            f"O IDS está em {versao}, mas o modelo está em {projeto.modelo.schema}. "
            "Com versões diferentes, a validação do modelo perde o sentido (RF-133).",
        )

    def _problemas(
        self, eir: Eir, requisitos: Sequence[Requisito], versao: str, titulo: str, escopo: str
    ) -> list[str]:
        """S6: gera e recarrega o IDS; se falhar, isola cada requisito problemático."""
        try:
            erros = self._construtor.check(
                self._construtor.build(eir, versao, titulo, escopo, requisitos)
            )
        except ValueError as erro:
            erros = [str(erro)]
        if not erros:
            return []
        problemas: list[str] = []
        for requisito in requisitos:
            try:
                individuais = self._construtor.check(
                    self._construtor.build(eir, versao, titulo, escopo, [requisito])
                )
            except ValueError as erro:
                individuais = [str(erro)]
            problemas.extend(f"{requisito.id}: {e}" for e in individuais)
        return problemas or erros
