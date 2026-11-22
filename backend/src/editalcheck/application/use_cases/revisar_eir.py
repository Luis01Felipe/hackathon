"""Caso de uso: revisão humana do EIR (RF-25) e ciclo fechado de lacunas (RF-59)."""

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from editalcheck.application.errors import ConflitoError, EntradaInvalidaError, NaoEncontradoError
from editalcheck.application.ports import ProjectRepository
from editalcheck.application.use_cases.gerar_eir import ValidadorRequisitos
from editalcheck.domain.findings import exigencia
from editalcheck.domain.models import (
    Apontamento,
    Cardinalidade,
    Eir,
    Evidencia,
    Projeto,
    Requisito,
    Restricao,
    StatusRequisito,
    TipoApontamento,
    TipoFaceta,
    TipoRestricao,
)

CAMPOS_EDITAVEIS = frozenset(
    {
        "descricao",
        "ifc_class",
        "predefined_type",
        "faceta",
        "pset",
        "propriedade",
        "tipo_dado",
        "restricao",
        "cardinalidade",
        "verificavel_por_ids",
        "motivo_nao_verificavel",
    }
)
TRECHO_LACUNA = "Sugerido pela análise de cobertura do EditalCheck: cláusula a incluir no edital."


def _texto_opcional(valor: Any) -> str | None:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def _restricao(valor: Any) -> Restricao | None:
    if valor is None:
        return None
    if not isinstance(valor, Mapping):
        raise EntradaInvalidaError("Restrição inválida.")
    try:
        return Restricao(
            tipo=TipoRestricao(valor.get("tipo")),
            valores=tuple(str(v) for v in valor.get("valores") or ()),
            minimo=float(valor["minimo"]) if valor.get("minimo") is not None else None,
            maximo=float(valor["maximo"]) if valor.get("maximo") is not None else None,
        )
    except (ValueError, TypeError) as erro:
        raise EntradaInvalidaError(f"Restrição inválida: {erro}") from erro


def _converter(campos: Mapping[str, Any]) -> dict[str, Any]:
    desconhecidos = set(campos) - CAMPOS_EDITAVEIS
    if desconhecidos:
        raise EntradaInvalidaError(f"Campos não editáveis: {', '.join(sorted(desconhecidos))}.")
    convertidos: dict[str, Any] = {}
    try:
        for chave, valor in campos.items():
            match chave:
                case "faceta":
                    convertidos[chave] = TipoFaceta(valor) if valor else None
                case "cardinalidade":
                    convertidos[chave] = Cardinalidade(valor or "required")
                case "restricao":
                    convertidos[chave] = _restricao(valor)
                case "verificavel_por_ids":
                    convertidos[chave] = bool(valor)
                case "descricao":
                    texto = _texto_opcional(valor)
                    if not texto:
                        raise EntradaInvalidaError("A descrição não pode ficar vazia.")
                    convertidos[chave] = texto
                case _:
                    convertidos[chave] = _texto_opcional(valor)
    except ValueError as erro:
        raise EntradaInvalidaError(f"Valor inválido: {erro}") from erro
    return convertidos


class RevisarEir:
    def __init__(
        self,
        repositorio: ProjectRepository,
        validador: ValidadorRequisitos,
        vocabulario_classes: Mapping[str, Sequence[str]],
    ) -> None:
        self._repo = repositorio
        self._validador = validador
        self._vocab = vocabulario_classes

    def _projeto_com_eir(self, projeto_id: str) -> tuple[Projeto, Eir]:
        projeto = self._repo.get(projeto_id)
        if projeto is None:
            raise NaoEncontradoError("Projeto não encontrado.")
        if projeto.eir is None:
            raise ConflitoError("O EIR ainda não foi gerado.")
        return projeto, projeto.eir

    def _salvar(self, projeto: Projeto, eir: Eir, requisitos: Sequence[Requisito]) -> None:
        projeto.eir = replace(eir, requisitos=tuple(requisitos))
        projeto.ids_gerado = False
        self._repo.save(projeto)

    def _trocar(
        self, projeto_id: str, requisito_id: str, novo_status: StatusRequisito
    ) -> Requisito:
        projeto, eir = self._projeto_com_eir(projeto_id)
        atual = eir.requisito(requisito_id)
        if atual is None:
            raise NaoEncontradoError(f"Requisito {requisito_id} não encontrado.")
        novo = replace(atual, status=novo_status)
        self._salvar(projeto, eir, [novo if r.id == requisito_id else r for r in eir.requisitos])
        return novo

    def aprovar(self, projeto_id: str, requisito_id: str) -> Requisito:
        return self._trocar(projeto_id, requisito_id, StatusRequisito.APROVADO)

    def rejeitar(self, projeto_id: str, requisito_id: str) -> Requisito:
        return self._trocar(projeto_id, requisito_id, StatusRequisito.REJEITADO)

    def reabrir(self, projeto_id: str, requisito_id: str) -> Requisito:
        return self._trocar(projeto_id, requisito_id, StatusRequisito.PROPOSTO)

    def editar(self, projeto_id: str, requisito_id: str, campos: Mapping[str, Any]) -> Requisito:
        projeto, eir = self._projeto_com_eir(projeto_id)
        atual = eir.requisito(requisito_id)
        if atual is None:
            raise NaoEncontradoError(f"Requisito {requisito_id} não encontrado.")
        editado = replace(atual, **_converter(campos), status=StatusRequisito.EDITADO, avisos=())
        extras = [editado.ifc_class] if editado.ifc_class else []
        contexto = self._validador.contexto(projeto, [], self._vocab, classes_extras=extras)
        validado = self._validador.validar_mapeamento(editado, projeto.modelo.schema, contexto)
        self._salvar(
            projeto, eir, [validado if r.id == requisito_id else r for r in eir.requisitos]
        )
        return validado

    def aprovar_todos(self, projeto_id: str, somente_verificaveis: bool = True) -> Eir:
        projeto, eir = self._projeto_com_eir(projeto_id)
        requisitos = [
            replace(r, status=StatusRequisito.APROVADO)
            if r.status == StatusRequisito.PROPOSTO
            and (r.verificavel_por_ids or not somente_verificaveis)
            else r
            for r in eir.requisitos
        ]
        self._salvar(projeto, eir, requisitos)
        return projeto.eir  # type: ignore[return-value]

    def adicionar_de_lacuna(self, projeto_id: str, apontamento: Apontamento) -> list[Requisito]:
        if apontamento.tipo != TipoApontamento.LACUNA_COBERTURA or not apontamento.classe_ifc:
            raise EntradaInvalidaError("Só apontamentos de lacuna de cobertura geram requisitos.")
        if not apontamento.propriedades_sugeridas:
            raise EntradaInvalidaError("O apontamento não tem propriedades sugeridas.")
        projeto, eir = self._projeto_com_eir(projeto_id)
        existentes = {
            ((r.ifc_class or "").lower(), (r.pset or "").lower(), (r.propriedade or "").lower())
            for r in eir.requisitos
        }
        contexto = self._validador.contexto(projeto, [], self._vocab)
        proximo = max((int(r.id.split("-")[1]) for r in eir.requisitos), default=0) + 1
        novos: list[Requisito] = []
        for sugerida in apontamento.propriedades_sugeridas:
            chave = (apontamento.classe_ifc.lower(), sugerida.pset.lower(), sugerida.nome.lower())
            if chave in existentes:
                continue
            requisito = Requisito(
                id=f"REQ-{proximo:03d}",
                topico_id="LACUNA",
                descricao="",
                evidencia=Evidencia(pagina=0, trecho=TRECHO_LACUNA),
                verificavel_por_ids=True,
                ifc_class=apontamento.classe_ifc,
                faceta=TipoFaceta.PROPRIEDADE,
                pset=sugerida.pset,
                propriedade=sugerida.nome,
                tipo_dado=sugerida.tipo_dado,
                sugerido_por_lacuna=True,
                gerado_por="lacuna",
            )
            requisito = replace(
                requisito, descricao=f"{apontamento.classe_ifc} deve ter {exigencia(requisito)}"
            )
            novos.append(
                self._validador.validar_mapeamento(requisito, projeto.modelo.schema, contexto)
            )
            proximo += 1
        if not novos:
            raise ConflitoError("As propriedades sugeridas já estão no EIR.")
        self._salvar(projeto, eir, [*eir.requisitos, *novos])
        return novos
