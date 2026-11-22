import "./style.css";
import { api } from "./api";
import { PASSOS, estadoInicial, passoMaximo, type Ctx, type Estado, type Passo } from "./state";
import { renderEir } from "./steps/eir";
import { renderIds } from "./steps/ids";
import { descartarResultados, renderResultados } from "./steps/resultados";
import { renderTopicos } from "./steps/topicos";
import { renderUpload } from "./steps/upload";
import { pararPolling, renderVerificacao } from "./steps/verificacao";
import { badge, h, limpar } from "./ui";

const raiz = document.querySelector<HTMLDivElement>("#app");
if (!raiz) throw new Error("Elemento #app não encontrado");

let estado: Estado = estadoInicial();
const conteudo = h("main", { class: "conteudo", id: "conteudo" });
const stepper = h("nav", { class: "stepper", "aria-label": "Passos do assistente" });
const seloModo = h("span", { class: "selo-modo" });

const ctx: Ctx = {
  get estado() {
    return estado;
  },
  irPara,
  atualizar: () => renderizar(),
};

function novoProjeto(): void {
  pararPolling();
  descartarResultados();
  estado = estadoInicial(estado.config);
  renderizar();
}

function irPara(passo: Passo): void {
  if (passo > passoMaximo(estado)) return;
  if (estado.passo === 6 && passo !== 6) descartarResultados();
  if (estado.passo === 5 && passo !== 5) pararPolling();
  estado.passo = passo;
  renderizar();
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function renderStepper(): void {
  limpar(stepper);
  const maximo = passoMaximo(estado);
  const lista = h("ol", null);
  for (const p of PASSOS) {
    const ativo = p.numero === estado.passo;
    const feito = p.numero < estado.passo || (p.numero <= maximo && !ativo && p.numero < maximo);
    const habilitado = p.numero <= maximo;
    const item = h(
      "li",
      { class: `passo${ativo ? " ativo" : ""}${feito ? " feito" : ""}${habilitado ? "" : " bloqueado"}` },
      h(
        "button",
        {
          type: "button",
          disabled: !habilitado,
          "aria-current": ativo ? "step" : null,
          onclick: () => irPara(p.numero),
        },
        h("span", { class: "passo-numero" }, feito ? "✓" : String(p.numero)),
        h("span", { class: "passo-texto" }, h("strong", null, p.titulo), h("small", null, p.descricao)),
      ),
    );
    lista.append(item);
  }
  stepper.append(lista);
}

function renderModo(): void {
  limpar(seloModo);
  const config = estado.config;
  if (!config) {
    seloModo.append(badge("API indisponível", "alta"));
    return;
  }
  const online = config.modo_ia !== "offline";
  seloModo.append(
    badge(
      online ? `IA: ${config.modelo_llm ?? config.modo_ia}` : "IA offline · regras determinísticas",
      online ? "info" : "neutro",
      online
        ? "Trechos do edital são enviados ao provedor de LLM configurado."
        : "Sem chave de LLM: extração e análises por regras determinísticas.",
    ),
  );
  if (config.bsdd_ativo) seloModo.append(badge("bSDD ativo", "info"));
}

function renderizar(): void {
  renderStepper();
  renderModo();
  limpar(conteudo);
  const renderers: Record<Passo, (c: Ctx) => HTMLElement> = {
    1: renderUpload,
    2: renderTopicos,
    3: renderEir,
    4: renderIds,
    5: renderVerificacao,
    6: renderResultados,
  };
  conteudo.append(renderers[estado.passo](ctx));
}

function montarShell(): void {
  const cabecalho = h(
    "header",
    { class: "topo" },
    h(
      "div",
      { class: "marca" },
      h("span", { class: "logo", "aria-hidden": "true" }, "EC"),
      h(
        "div",
        null,
        h("h1", null, "EditalCheck"),
        h("p", null, "Verificador bidirecional Edital × IFC · IFC · IDS · BCF · bSDD"),
      ),
    ),
    h(
      "div",
      { class: "topo-acoes" },
      seloModo,
      h("button", { type: "button", class: "btn btn-fantasma", onclick: () => novoProjeto() }, "Novo projeto"),
    ),
  );
  const rodape = h(
    "footer",
    { class: "rodape" },
    "A IA interpreta o texto; IDS, validação, BCF e métricas são gerados por código determinístico. ",
    "Use apenas documentos públicos.",
  );
  raiz!.append(cabecalho, stepper, conteudo, rodape);
}

async function iniciar(): Promise<void> {
  montarShell();
  try {
    estado.config = await api.config();
  } catch {
    estado.config = null;
  }
  renderizar();
}

void iniciar();
