"""Geração dos IR em segundo plano: a API responde na hora e o navegador consulta o andamento."""

from collections.abc import Callable, Sequence

from fastapi.testclient import TestClient

from editalcheck.application.errors import EntradaInvalidaError
from editalcheck.application.use_cases.gerar_eir_em_segundo_plano import (
    GerarEirEmSegundoPlano,
    StatusGeracao,
)
from editalcheck.bootstrap import Container
from editalcheck.entrypoints.api.main import criar_app


def _projeto_demo(cliente: TestClient) -> tuple[str, list[str]]:
    projeto = cliente.post("/api/projetos/demo?com_licoes=true")
    assert projeto.status_code == 201, projeto.text
    pid = projeto.json()["id"]
    topicos = cliente.get(f"/api/projetos/{pid}/topicos").json()
    return pid, [t["id"] for t in topicos if t["relevante_bim"]]


def test_geracao_em_segundo_plano_entrega_o_mesmo_ir(container: Container) -> None:
    cliente = TestClient(criar_app(container))
    pid, selecionados = _projeto_demo(cliente)

    inicio = cliente.post(f"/api/projetos/{pid}/ir/geracao", json={"topicos": selecionados})
    assert inicio.status_code == 202, inicio.text
    assert inicio.json()["status"] == "processando"

    # O TestClient roda a tarefa em segundo plano antes de devolver a resposta.
    geracao = cliente.get(f"/api/projetos/{pid}/ir/geracao").json()
    assert geracao["id"] == inicio.json()["id"]
    assert geracao["status"] == "concluida", geracao["erro"]
    assert geracao["erro"] is None
    licoes = len(cliente.get(f"/api/projetos/{pid}/licoes").json())
    assert licoes > 0
    assert geracao["total"] == geracao["concluidos"] > licoes
    assert geracao["ir"]["requisitos"]
    assert (
        geracao["ir"]["requisitos"] == cliente.get(f"/api/projetos/{pid}/ir").json()["requisitos"]
    )

    # Nova geração depois de concluída: roda de novo e sobe a versão do IR.
    de_novo = cliente.post(f"/api/projetos/{pid}/ir/geracao", json={"topicos": selecionados})
    assert de_novo.json()["id"] != geracao["id"]
    assert cliente.get(f"/api/projetos/{pid}/ir/geracao").json()["ir"]["versao"] == 2


def test_geracao_recusa_selecao_invalida_na_hora(container: Container) -> None:
    cliente = TestClient(criar_app(container))
    pid, _ = _projeto_demo(cliente)

    assert cliente.get(f"/api/projetos/{pid}/ir/geracao").status_code == 404
    vazia = cliente.post(f"/api/projetos/{pid}/ir/geracao", json={"topicos": []})
    assert vazia.status_code == 422
    inexistente = cliente.post(f"/api/projetos/{pid}/ir/geracao", json={"topicos": ["TOP-99"]})
    assert inexistente.status_code == 422
    assert cliente.get(f"/api/projetos/{pid}/ir/geracao").status_code == 404

    outro = cliente.post("/api/projetos/nao-existe/ir/geracao", json={"topicos": ["TOP-01"]})
    assert outro.status_code == 404
    assert cliente.get("/api/projetos/nao-existe/ir/geracao").status_code == 404


def test_projeto_apagado_leva_a_geracao_junto(container: Container) -> None:
    cliente = TestClient(criar_app(container))
    pid, selecionados = _projeto_demo(cliente)
    cliente.post(f"/api/projetos/{pid}/ir/geracao", json={"topicos": selecionados})
    assert container.geracao_eir.obter(pid) is not None

    assert cliente.delete(f"/api/projetos/{pid}").status_code == 204
    assert container.geracao_eir.obter(pid) is None


class _GeradorFalso:
    """Substitui o ``GerarEir``: conta as chamadas e deixa o teste decidir o desfecho."""

    def __init__(self, total: int = 3, erro: Exception | None = None) -> None:
        self.total = total
        self.erro = erro
        self.chamadas = 0
        self.antes_de_terminar: Callable[[], None] = lambda: None

    def validar_selecao(self, projeto_id: str, topico_ids: Sequence[str]) -> int:
        if not topico_ids:
            raise EntradaInvalidaError("Selecione ao menos um tópico válido.")
        return self.total

    def executar(
        self, projeto_id: str, topico_ids: Sequence[str], progresso: Callable[[], None]
    ) -> object:
        self.chamadas += 1
        for _ in range(self.total):
            progresso()
        self.antes_de_terminar()
        if self.erro:
            raise self.erro
        return object()


def test_clique_repetido_nao_dispara_outra_geracao() -> None:
    gerador = _GeradorFalso()
    servico = GerarEirEmSegundoPlano(gerador)  # type: ignore[arg-type]

    primeira, nova = servico.iniciar("p1", ["TOP-01"])
    repetida, nova_de_novo = servico.iniciar("p1", ["TOP-01"])
    assert nova and not nova_de_novo
    assert repetida.id == primeira.id

    servico.executar(primeira)
    final = servico.obter("p1")
    assert final is not None
    assert final.status == StatusGeracao.CONCLUIDA
    assert final.concluidos == final.total == 3
    assert gerador.chamadas == 1


def test_falha_fica_registrada_com_mensagem_para_o_usuario() -> None:
    servico = GerarEirEmSegundoPlano(
        _GeradorFalso(erro=EntradaInvalidaError("Selecione ao menos um tópico válido."))  # type: ignore[arg-type]
    )
    geracao, _ = servico.iniciar("p1", ["TOP-01"])
    servico.executar(geracao)
    final = servico.obter("p1")
    assert final is not None and final.status == StatusGeracao.FALHOU
    assert final.erro == "Selecione ao menos um tópico válido."

    inesperado = GerarEirEmSegundoPlano(_GeradorFalso(erro=RuntimeError("segredo")))  # type: ignore[arg-type]
    geracao, _ = inesperado.iniciar("p2", ["TOP-01"])
    inesperado.executar(geracao)
    final = inesperado.obter("p2")
    assert final is not None and final.status == StatusGeracao.FALHOU
    assert final.erro is not None
    assert "Código para o suporte" in final.erro and "segredo" not in final.erro


def test_projeto_apagado_no_meio_da_geracao_nao_volta() -> None:
    gerador = _GeradorFalso()
    servico = GerarEirEmSegundoPlano(gerador)  # type: ignore[arg-type]
    geracao, _ = servico.iniciar("p1", ["TOP-01"])
    gerador.antes_de_terminar = lambda: servico.esquecer("p1")

    servico.executar(geracao)
    assert servico.obter("p1") is None
