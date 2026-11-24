// Cliente HTTP tipado da API do EditalCheck (docs/api.md).
import type {
  AcaoRequisito,
  Config,
  Decisao,
  EirResposta,
  GeracaoIr,
  IdsResposta,
  LocalApontamento,
  MarcoEntrega,
  ProjetoResumo,
  RegiaoPdf,
  Relatorio,
  Requisito,
  StatusDecisao,
  Topico,
  Verificacao,
  VersaoIfc,
} from "./types";

/**
 * Caminho base do app: "/" em desenvolvimento e "/editalcheck/" atrás do proxy
 * (definido no build com `vite build --base`).
 */
const BASE = import.meta.env.BASE_URL.replace(/\/$/, "");

/** Prefixa um caminho da API ("/api/...") com o caminho base do app. */
const rota = (caminho: string): string => `${BASE}${caminho}`;

/** Evento disparado quando o servidor não tem mais o projeto (expirou ou foi apagado). */
export const EVENTO_PROJETO_EXPIRADO = "editalcheck:projeto-expirado";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const MENSAGENS_STATUS: Record<number, string> = {
  404: "Recurso não encontrado.",
  409: "Operação não permitida no estado atual.",
  413: "Arquivo acima do limite de tamanho.",
  422: "Dados inválidos.",
  500: "Erro interno do servidor.",
  502: "Servidor indisponível.",
  503: "Servidor indisponível.",
};

async function extrairErro(response: Response): Promise<ApiError> {
  let mensagem = MENSAGENS_STATUS[response.status] ?? `Erro HTTP ${response.status}.`;
  try {
    const corpo = await response.json();
    if (typeof corpo?.detail === "string") {
      mensagem = corpo.detail;
    } else if (Array.isArray(corpo?.detail)) {
      mensagem = corpo.detail
        .map((d: { msg?: string; loc?: unknown[] }) => d.msg ?? JSON.stringify(d))
        .join("; ");
    }
  } catch {
    // corpo não é JSON: mantém a mensagem padrão
  }
  return new ApiError(mensagem, response.status);
}

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: "application/json" } };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { ...init.headers, "Content-Type": "application/json" };
  }
  let response: Response;
  try {
    response = await fetch(rota(url), init);
  } catch {
    throw new ApiError("Não foi possível conectar ao servidor do EditalCheck.", 0);
  }
  if (!response.ok) {
    const erro = await extrairErro(response);
    if (erro.status === 404 && erro.message.startsWith("Projeto não encontrado")) {
      window.dispatchEvent(new CustomEvent(EVENTO_PROJETO_EXPIRADO));
    }
    throw erro;
  }
  if (response.status === 204) return undefined as T;
  try {
    return (await response.json()) as T;
  } catch {
    // A conexão caiu no meio da resposta (ou veio uma página do proxy no lugar do JSON).
    throw new ApiError("Não foi possível ler a resposta do servidor do EditalCheck.", 0);
  }
}

/** Falha de rede ou do proxy que costuma passar sozinha: vale tentar de novo. */
export function falhaPassageira(e: unknown): boolean {
  return e instanceof ApiError && [0, 502, 503, 504].includes(e.status);
}

/** Nome do arquivo no cabeçalho Content-Disposition, se houver. */
function nomeDoAnexo(disposicao: string | null): string | null {
  if (!disposicao) return null;
  const codificado = /filename\*=UTF-8''([^;]+)/i.exec(disposicao)?.[1];
  if (codificado) {
    try {
      return decodeURIComponent(codificado);
    } catch {
      return null;
    }
  }
  return /filename="?([^";]+)"?/i.exec(disposicao)?.[1] ?? null;
}

/** Baixa um arquivo gerado no servidor (URL de `urls`, já com o caminho base). */
export async function baixarArquivo(url: string): Promise<{ blob: Blob; nome: string | null }> {
  let response: Response;
  try {
    response = await fetch(url);
  } catch {
    throw new ApiError("Não foi possível conectar ao servidor do EditalCheck.", 0);
  }
  if (!response.ok) throw await extrairErro(response);
  return { blob: await response.blob(), nome: nomeDoAnexo(response.headers.get("Content-Disposition")) };
}

const enc = encodeURIComponent;

export const api = {
  config: () => request<Config>("GET", "/api/config"),

  criarProjeto: (edital: File, modelo: File | null, licoes: File[], versaoIfc: VersaoIfc | null) => {
    const form = new FormData();
    form.append("edital", edital);
    if (modelo) form.append("modelo", modelo);
    for (const arquivo of licoes) form.append("licoes", arquivo);
    if (!modelo && versaoIfc) form.append("versao_ifc", versaoIfc);
    return request<ProjetoResumo>("POST", "/api/projetos", form);
  },
  criarProjetoDemo: (comLicoes = true) =>
    request<ProjetoResumo>("POST", `/api/projetos/demo?com_licoes=${comLicoes}`),
  projeto: (id: string) => request<ProjetoResumo>("GET", `/api/projetos/${enc(id)}`),
  apagarProjeto: (id: string) => request<void>("DELETE", `/api/projetos/${enc(id)}`),
  topicos: (id: string) => request<Topico[]>("GET", `/api/projetos/${enc(id)}/topicos`),
  regioesTopicos: (id: string) =>
    request<Record<string, RegiaoPdf[]>>("GET", `/api/projetos/${enc(id)}/topicos/regioes`),
  regioesApontamentos: (vid: string) =>
    request<LocalApontamento[]>("GET", `/api/verificacoes/${enc(vid)}/regioes`),

  definirMarcos: (id: string, marcos: { id?: string | null; nome: string; descricao?: string }[]) =>
    request<MarcoEntrega[]>("PUT", `/api/projetos/${enc(id)}/marcos`, { marcos }),

  iniciarGeracaoIr: (id: string, topicos: string[]) =>
    request<GeracaoIr>("POST", `/api/projetos/${enc(id)}/ir/geracao`, { topicos }),
  geracaoIr: (id: string) => request<GeracaoIr>("GET", `/api/projetos/${enc(id)}/ir/geracao`),
  ir: (id: string) => request<EirResposta>("GET", `/api/projetos/${enc(id)}/ir`),
  atualizarRequisito: (id: string, reqId: string, acao: AcaoRequisito) =>
    request<Requisito>("PATCH", `/api/projetos/${enc(id)}/ir/requisitos/${enc(reqId)}`, acao),
  aprovarTodos: (id: string, somenteVerificaveis: boolean) =>
    request<EirResposta>("POST", `/api/projetos/${enc(id)}/ir/aprovar-todos`, {
      somente_verificaveis: somenteVerificaveis,
    }),
  adicionarDeLacuna: (id: string, verificacaoId: string, apontamentoId: string) =>
    request<Requisito[]>("POST", `/api/projetos/${enc(id)}/ir/requisitos`, {
      verificacao_id: verificacaoId,
      apontamento_id: apontamentoId,
    }),

  gerarIds: (id: string, marcoId: string | null, versaoIfc: VersaoIfc | null) =>
    request<IdsResposta>("POST", `/api/projetos/${enc(id)}/ids`, {
      marco_id: marcoId,
      versao_ifc: versaoIfc,
    }),

  iniciarVerificacao: (id: string) =>
    request<Verificacao>("POST", `/api/projetos/${enc(id)}/verificacoes`),
  verificacao: (vid: string) => request<Verificacao>("GET", `/api/verificacoes/${enc(vid)}`),
  relatorio: (vid: string) => request<Relatorio>("GET", `/api/verificacoes/${enc(vid)}/relatorio`),
  decidir: (vid: string, aptId: string, status: StatusDecisao, comentario: string, autor: string) =>
    request<Decisao>("PATCH", `/api/verificacoes/${enc(vid)}/apontamentos/${enc(aptId)}`, {
      status,
      comentario,
      autor,
    }),
};

export const urls = {
  irXlsx: (id: string) => rota(`/api/projetos/${enc(id)}/ir.xlsx`),
  editalPdf: (id: string) => rota(`/api/projetos/${enc(id)}/edital.pdf`),
  idsXml: (id: string) => rota(`/api/projetos/${enc(id)}/ids.xml`),
  modeloIfc: (id: string) => rota(`/api/projetos/${enc(id)}/modelo.ifc`),
  relatorioJson: (vid: string) => rota(`/api/verificacoes/${enc(vid)}/relatorio`),
  relatorioHtml: (vid: string) => rota(`/api/verificacoes/${enc(vid)}/relatorio.html`),
  bcf: (vid: string) => rota(`/api/verificacoes/${enc(vid)}/resultado.bcf`),
  editalAnotado: (vid: string) => rota(`/api/verificacoes/${enc(vid)}/edital-anotado.pdf`),
  esclarecimentos: (vid: string) => rota(`/api/verificacoes/${enc(vid)}/esclarecimentos.xlsx`),
};
