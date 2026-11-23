import "./style.css";
import { api } from "./api";
import { PASSOS, estadoInicial, passoMaximo, type Ctx, type Estado, type Passo } from "./state";
import { renderEir } from "./steps/eir";
import { renderIds } from "./steps/ids";
import { descartarResultados, pedirFocoNoEdital, renderResultados } from "./steps/resultados";
import { renderTopicos } from "./steps/topicos";
import { renderUpload } from "./steps/upload";
import { pararPolling, renderVerificacao } from "./steps/verificacao";
import { barraFiltros, campoBusca, contem } from "./filtros";
import { GLOSSARIO } from "./labels";
import { abrirModal, badge, h, limpar, mensagemErro, toast } from "./ui";

const raiz = document.querySelector<HTMLDivElement>("#app");
if (!raiz) throw new Error("Elemento #app não encontrado");

let estado: Estado = estadoInicial();
const conteudo = h("main", { class: "conteudo", id: "conteudo" });
const stepper = h("nav", { class: "stepper", "aria-label": "Passos do assistente" });
const seloModo = h("span", { class: "selo-modo" });
const faixa = h("div", { class: "faixa-demo", role: "note" });
const CHAVE_CONSENTIMENTO = "editalcheck.aviso-ia";

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

/** RF-094: apaga do servidor o edital, o IFC, as lições e os relatórios do projeto. */
async function encerrarEApagar(): Promise<void> {
  const projeto = estado.projeto;
  if (!projeto) {
    novoProjeto();
    return;
  }
  if (!window.confirm("Apagar do servidor o edital, o modelo, as lições e os relatórios deste projeto?")) return;
  try {
    await api.apagarProjeto(projeto.id);
    toast("Dados do projeto apagados do servidor.", "sucesso");
  } catch (e) {
    toast(mensagemErro(e), "erro");
  }
  novoProjeto();
}

function abrirGlossario(): void {
  const lista = h("dl", { class: "glossario" });
  const desenhar = (termo: string) => {
    const visiveis = GLOSSARIO.filter((g) => contem(termo, g.termo, g.definicao, g.referencia));
    lista.replaceChildren(
      ...(visiveis.length
        ? visiveis.flatMap((g) => [
            h("dt", null, g.termo),
            h("dd", null, g.definicao, h("small", { class: "texto-suave" }, ` Referência: ${g.referencia}`)),
          ])
        : [h("dd", { class: "texto-suave" }, "Nenhum termo encontrado.")]),
    );
  };
  desenhar("");
  const conteudo = h(
    "div",
    null,
    barraFiltros(campoBusca("Buscar termo do glossário", "", desenhar)),
    lista,
    h(
      "p",
      { class: "texto-suave" },
      "Versões das normas conferidas em catálogos públicos em 22/11/2026. Confirme a vigência antes de citar em contrato.",
    ),
  );
  const fechar = h("button", { type: "button", class: "btn btn-primario" }, "Fechar");
  const modal = abrirModal("Glossário", conteudo, [fechar]);
  fechar.addEventListener("click", () => modal.fechar());
}

/** RF-095: antes da primeira chamada à IA, o usuário sabe para onde vão os trechos. */
function pedirConsentimento(): void {
  const aviso = estado.config?.aviso_ia;
  if (!aviso) return;
  try {
    if (window.sessionStorage.getItem(CHAVE_CONSENTIMENTO) === "ok") return;
  } catch {
    // sessionStorage indisponível: mostra o aviso mesmo assim
  }
  const entendi = h("button", { type: "button", class: "btn btn-primario" }, "Entendi e quero continuar");
  const modal = abrirModal("Como seus dados são tratados", h("p", null, aviso), [entendi]);
  entendi.addEventListener("click", () => {
    try {
      window.sessionStorage.setItem(CHAVE_CONSENTIMENTO, "ok");
    } catch {
      // segue sem guardar a confirmação
    }
    modal.fechar();
  });
}

function renderFaixa(): void {
  limpar(faixa);
  const config = estado.config;
  faixa.hidden = !config?.disponivel_ate && config?.modo_dados !== "efemero";
  if (!config) return;
  if (config.disponivel_ate) {
    faixa.append(h("strong", null, `Ambiente de demonstração disponível até ${config.disponivel_ate}. `));
  }
  faixa.append(
    config.modo_dados === "efemero"
      ? "Os arquivos ficam só na memória e são apagados ao encerrar. Não envie dados de clientes."
      : "Modo de desenvolvimento: os arquivos ficam gravados no servidor.",
  );
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
  if (config.modo_dados === "efemero") seloModo.append(badge("Dados só em memória", "sucesso"));
}

function renderizar(): void {
  renderStepper();
  renderModo();
  renderFaixa();
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
        h("p", null, "Contrato de dados da contratação · Edital × IFC · IDS · BCF · bSDD"),
      ),
    ),
    h(
      "div",
      { class: "topo-acoes" },
      seloModo,
      h("button", { type: "button", class: "btn btn-fantasma", onclick: () => abrirGlossario() }, "Glossário"),
      h("button", { type: "button", class: "btn btn-fantasma", onclick: () => novoProjeto() }, "Novo projeto"),
      h(
        "button",
        {
          type: "button",
          class: "btn btn-perigo",
          title: "Apaga do servidor todos os arquivos e relatórios deste projeto",
          onclick: () => void encerrarEApagar(),
        },
        "Encerrar e apagar dados",
      ),
    ),
  );
  const rodape = h(
    "footer",
    { class: "rodape" },
    "A IA interpreta o texto; IDS, validação, BCF e métricas são gerados por código determinístico. ",
    "Lições aprendidas só acrescentam verificações. Use apenas documentos públicos.",
  );
  raiz!.append(faixa, cabecalho, stepper, conteudo, rodape);
}

/**
 * Link do relatório HTML ("Ver no edital"): #verificacao=<id>&apontamento=<APT>.
 * Recarrega os resultados da verificação, se ela ainda estiver em memória no servidor.
 */
async function abrirPorLink(): Promise<boolean> {
  const parametros = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const verificacaoId = parametros.get("verificacao");
  if (!verificacaoId) return false;
  history.replaceState(null, "", window.location.pathname + window.location.search);
  try {
    const relatorio = await api.relatorio(verificacaoId);
    estado.relatorio = relatorio;
    estado.projeto = await api.projeto(relatorio.projeto_id);
    estado.verificacao = await api.verificacao(verificacaoId);
    estado.eir = await api.ir(relatorio.projeto_id).catch(() => null);
    estado.passo = 6;
    pedirFocoNoEdital(parametros.get("apontamento"));
    return true;
  } catch (e) {
    toast(`Não foi possível abrir o resultado: ${mensagemErro(e)} O projeto pode ter expirado.`, "erro");
    return false;
  }
}

async function iniciar(): Promise<void> {
  montarShell();
  try {
    estado.config = await api.config();
  } catch {
    estado.config = null;
  }
  await abrirPorLink();
  renderizar();
  pedirConsentimento();
}

void iniciar();
