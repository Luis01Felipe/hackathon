"""Caso de uso: gerar os IR em segundo plano e informar o andamento.

A geração faz uma chamada ao LLM por tópico e por lição e leva cerca de um minuto.
Uma requisição HTTP aberta por tanto tempo cai em proxies, firewalls e redes móveis
com limite de inatividade (o navegador mostra "Failed to fetch"). Por isso a API
inicia a geração, responde na hora e o navegador consulta o andamento com
requisições curtas.
"""

import threading
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import StrEnum

from editalcheck.application.errors import EditalCheckError
from editalcheck.application.observability import logger
from editalcheck.application.use_cases.gerar_eir import GerarEir, ResultadoEir

# Gerações terminadas ficam disponíveis por este tempo para o navegador buscar o resultado.
RETENCAO_S = 3600.0


class StatusGeracao(StrEnum):
    PROCESSANDO = "processando"
    CONCLUIDA = "concluida"
    FALHOU = "falhou"


@dataclass(frozen=True)
class GeracaoIr:
    id: str
    projeto_id: str
    topicos: tuple[str, ...]
    total: int
    status: StatusGeracao = StatusGeracao.PROCESSANDO
    concluidos: int = 0
    resultado: ResultadoEir | None = None
    erro: str | None = None
    terminada_em: float | None = None


class GerarEirEmSegundoPlano:
    """Guarda a geração mais recente de cada projeto, na memória do processo.

    O deploy usa sessão fixa no proxy: o projeto e a geração dele vivem na mesma réplica.
    """

    def __init__(self, gerar: GerarEir, retencao_s: float = RETENCAO_S) -> None:
        self._gerar = gerar
        self._retencao_s = retencao_s
        self._trava = threading.Lock()
        self._por_projeto: dict[str, GeracaoIr] = {}

    def iniciar(self, projeto_id: str, topico_ids: Sequence[str]) -> tuple[GeracaoIr, bool]:
        """Registra a geração e devolve ``(geração, nova)``.

        Seleção inválida falha aqui, antes de chamar o LLM. Se o projeto já tem uma
        geração em andamento, ela é devolvida com ``nova=False``: um clique repetido
        ou uma nova tentativa do navegador não dispara outra rodada paga no LLM.
        """
        total = self._gerar.validar_selecao(projeto_id, topico_ids)
        with self._trava:
            self._podar()
            atual = self._por_projeto.get(projeto_id)
            if atual and atual.status == StatusGeracao.PROCESSANDO:
                return atual, False
            geracao = GeracaoIr(
                id=uuid.uuid4().hex[:16],
                projeto_id=projeto_id,
                topicos=tuple(topico_ids),
                total=total,
            )
            self._por_projeto[projeto_id] = geracao
            return geracao, True

    def executar(self, geracao: GeracaoIr) -> None:
        """Roda a geração registrada. Nenhuma exceção escapa: o resultado fica no registro."""
        try:
            resultado = self._gerar.executar(
                geracao.projeto_id, geracao.topicos, progresso=lambda: self._avancar(geracao)
            )
        except EditalCheckError as erro:
            self._terminar(geracao, status=StatusGeracao.FALHOU, erro=str(erro))
        except Exception:
            codigo = uuid.uuid4().hex[:16]
            logger.exception("Geração de IR falhou [%s] (projeto %s)", codigo, geracao.projeto_id)
            self._terminar(
                geracao,
                status=StatusGeracao.FALHOU,
                erro=f"Erro interno do servidor. Código para o suporte: {codigo}.",
            )
        else:
            self._terminar(geracao, status=StatusGeracao.CONCLUIDA, resultado=resultado)

    def obter(self, projeto_id: str) -> GeracaoIr | None:
        with self._trava:
            return self._por_projeto.get(projeto_id)

    def esquecer(self, projeto_id: str) -> None:
        with self._trava:
            self._por_projeto.pop(projeto_id, None)

    def _avancar(self, geracao: GeracaoIr) -> None:
        with self._trava:
            atual = self._por_projeto.get(geracao.projeto_id)
            if atual is None or atual.id != geracao.id:
                return
            concluidos = min(atual.concluidos + 1, atual.total)
            self._por_projeto[geracao.projeto_id] = replace(atual, concluidos=concluidos)

    def _terminar(
        self,
        geracao: GeracaoIr,
        status: StatusGeracao,
        resultado: ResultadoEir | None = None,
        erro: str | None = None,
    ) -> None:
        with self._trava:
            atual = self._por_projeto.get(geracao.projeto_id)
            # Projeto apagado ou expirado durante a geração: não há para quem guardar.
            if atual is None or atual.id != geracao.id:
                return
            concluida = status == StatusGeracao.CONCLUIDA
            self._por_projeto[geracao.projeto_id] = replace(
                atual,
                status=status,
                resultado=resultado,
                erro=erro,
                concluidos=atual.total if concluida else atual.concluidos,
                terminada_em=time.monotonic(),
            )

    def _podar(self) -> None:
        limite = time.monotonic() - self._retencao_s
        vencidas = [
            projeto_id
            for projeto_id, g in self._por_projeto.items()
            if g.terminada_em is not None and g.terminada_em < limite
        ]
        for projeto_id in vencidas:
            del self._por_projeto[projeto_id]
