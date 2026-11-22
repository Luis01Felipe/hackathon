// Cliente HTTP tipado da API do EditalCheck (docs/api.md).
import type {
  AcaoRequisito,
  Config,
  EirResposta,
  IdsResposta,
  ProjetoResumo,
  Relatorio,
  Requisito,
  Topico,
  Verificacao,
} from "./types";

export class ApiError extends Error {
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
    response = await fetch(url, init);
  } catch {
    throw new ApiError("Não foi possível conectar ao servidor do EditalCheck.", 0);
  }
  if (!response.ok) throw await extrairErro(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

const enc = encodeURIComponent;

export const api = {
  config: () => request<Config>("GET", "/api/config"),

  criarProjeto: (edital: File, modelo: File) => {
    const form = new FormData();
    form.append("edital", edital);
    form.append("modelo", modelo);
    return request<ProjetoResumo>("POST", "/api/projetos", form);
  },
  criarProjetoDemo: () => request<ProjetoResumo>("POST", "/api/projetos/demo"),
  projeto: (id: string) => request<ProjetoResumo>("GET", `/api/projetos/${enc(id)}`),
  topicos: (id: string) => request<Topico[]>("GET", `/api/projetos/${enc(id)}/topicos`),

  gerarEir: (id: string, topicos: string[]) =>
    request<EirResposta>("POST", `/api/projetos/${enc(id)}/eir`, { topicos }),
  eir: (id: string) => request<EirResposta>("GET", `/api/projetos/${enc(id)}/eir`),
  atualizarRequisito: (id: string, reqId: string, acao: AcaoRequisito) =>
    request<Requisito>("PATCH", `/api/projetos/${enc(id)}/eir/requisitos/${enc(reqId)}`, acao),
  aprovarTodos: (id: string, somenteVerificaveis: boolean) =>
    request<EirResposta>("POST", `/api/projetos/${enc(id)}/eir/aprovar-todos`, {
      somente_verificaveis: somenteVerificaveis,
    }),
  adicionarDeLacuna: (id: string, verificacaoId: string, apontamentoId: string) =>
    request<Requisito[]>("POST", `/api/projetos/${enc(id)}/eir/requisitos`, {
      verificacao_id: verificacaoId,
      apontamento_id: apontamentoId,
    }),

  gerarIds: (id: string) => request<IdsResposta>("POST", `/api/projetos/${enc(id)}/ids`),

  iniciarVerificacao: (id: string) =>
    request<Verificacao>("POST", `/api/projetos/${enc(id)}/verificacoes`),
  verificacao: (vid: string) => request<Verificacao>("GET", `/api/verificacoes/${enc(vid)}`),
  relatorio: (vid: string) => request<Relatorio>("GET", `/api/verificacoes/${enc(vid)}/relatorio`),
};

export const urls = {
  eirXlsx: (id: string) => `/api/projetos/${enc(id)}/eir.xlsx`,
  idsXml: (id: string) => `/api/projetos/${enc(id)}/ids.xml`,
  modeloIfc: (id: string) => `/api/projetos/${enc(id)}/modelo.ifc`,
  relatorioJson: (vid: string) => `/api/verificacoes/${enc(vid)}/relatorio`,
  relatorioHtml: (vid: string) => `/api/verificacoes/${enc(vid)}/relatorio.html`,
  bcf: (vid: string) => `/api/verificacoes/${enc(vid)}/resultado.bcf`,
};
