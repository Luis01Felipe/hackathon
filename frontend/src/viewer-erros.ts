// Erros do visualizador 3D num módulo sem three.js: a tela de resultados reconhece um
// cancelamento sem precisar carregar a biblioteca 3D, que só chega quando o 3D abre.

/** O visualizador foi descartado antes de a carga terminar. Não é falha: a tela saiu. */
export class CargaCancelada extends Error {
  constructor() {
    super("Carga do modelo 3D cancelada: o visualizador foi descartado.");
    this.name = "CargaCancelada";
  }
}

/** Cancelamento esperado (nosso ou do Fragments), que não deve ir para o console. */
export function foiCancelamento(erro: unknown): boolean {
  if (erro instanceof CargaCancelada) return true;
  return erro instanceof Error && erro.name === "LoadAbortedError";
}
