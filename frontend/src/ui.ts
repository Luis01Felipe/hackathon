// Utilitários de DOM sem framework. Todo texto entra via textContent (sem innerHTML),
// porque o conteúdo do edital e do modelo é dado externo.

type Filho = Node | string | number | null | undefined | false;
type Atributos = Record<string, string | number | boolean | null | undefined | EventListener>;

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: Atributos | null = null,
  ...filhos: (Filho | Filho[])[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  if (attrs) {
    for (const [chave, valor] of Object.entries(attrs)) {
      if (valor === null || valor === undefined || valor === false) continue;
      if (chave.startsWith("on") && typeof valor === "function") {
        el.addEventListener(chave.slice(2).toLowerCase(), valor as EventListener);
        continue;
      }
      if (chave === "class") {
        el.className = String(valor);
        continue;
      }
      if (valor === true) {
        el.setAttribute(chave, "");
        continue;
      }
      el.setAttribute(chave, String(valor));
    }
  }
  append(el, filhos);
  return el;
}

export function append(el: HTMLElement, filhos: (Filho | Filho[])[]): void {
  for (const filho of filhos.flat()) {
    if (filho === null || filho === undefined || filho === false) continue;
    el.append(filho instanceof Node ? filho : String(filho));
  }
}

export function limpar(el: HTMLElement): void {
  el.replaceChildren();
}

export function badge(texto: string, variante = "neutro", titulo?: string): HTMLSpanElement {
  return h("span", { class: `badge badge-${variante}`, title: titulo ?? null }, texto);
}

export function botao(
  texto: string,
  onClick: () => void,
  variante: "primario" | "secundario" | "perigo" | "sucesso" | "fantasma" = "secundario",
  extras: Atributos = {},
): HTMLButtonElement {
  return h(
    "button",
    { type: "button", class: `btn btn-${variante}`, onclick: () => onClick(), ...extras },
    texto,
  );
}

export function linkDownload(texto: string, href: string, variante = "secundario"): HTMLAnchorElement {
  return h("a", { class: `btn btn-${variante}`, href, download: "", target: "_blank", rel: "noopener" }, texto);
}

/**
 * Botão de download com retorno visível: mostra "Gerando…" enquanto o servidor monta o
 * arquivo e exibe o erro, se houver (um link comum falharia em silêncio).
 */
export function botaoDownload(
  texto: string,
  baixar: () => Promise<{ blob: Blob; nome: string | null }>,
  nomePadrao: string,
  variante = "secundario",
): HTMLSpanElement {
  const falha = h("small", { class: "download-falha", role: "alert" });
  const botaoBaixar = h("button", { type: "button", class: `btn btn-${variante}` }, texto);
  botaoBaixar.addEventListener("click", async () => {
    if (botaoBaixar.disabled) return;
    botaoBaixar.disabled = true;
    botaoBaixar.textContent = "Gerando o arquivo…";
    falha.textContent = "";
    try {
      const { blob, nome } = await baixar();
      const endereco = URL.createObjectURL(blob);
      const ancora = h("a", { href: endereco, download: nome ?? nomePadrao, hidden: true });
      document.body.append(ancora);
      ancora.click();
      ancora.remove();
      window.setTimeout(() => URL.revokeObjectURL(endereco), 60_000);
    } catch (e) {
      console.error("EditalCheck: falha no download", e);
      falha.textContent = `Não foi possível gerar o arquivo: ${mensagemErro(e)}`;
    } finally {
      botaoBaixar.disabled = false;
      botaoBaixar.textContent = texto;
    }
  });
  return h("span", { class: "botao-download" }, botaoBaixar, falha);
}

export function carregando(texto: string): HTMLDivElement {
  return h("div", { class: "carregando", role: "status" }, h("span", { class: "spinner" }), texto);
}

export function vazio(texto: string): HTMLDivElement {
  return h("div", { class: "vazio" }, texto);
}

export function avisos(lista: string[], titulo = "Avisos"): HTMLElement | null {
  if (!lista.length) return null;
  return h(
    "div",
    { class: "alerta alerta-aviso" },
    h("strong", null, titulo),
    h("ul", null, lista.map((a) => h("li", null, a))),
  );
}

export function erro(texto: string): HTMLDivElement {
  return h("div", { class: "alerta alerta-erro", role: "alert" }, texto);
}

let toastHost: HTMLDivElement | null = null;

export function toast(texto: string, tipo: "info" | "erro" | "sucesso" = "info"): void {
  if (!toastHost) {
    toastHost = h("div", { class: "toasts", "aria-live": "polite" });
    document.body.append(toastHost);
  }
  const item = h("div", { class: `toast toast-${tipo}` }, texto);
  toastHost.append(item);
  window.setTimeout(() => item.classList.add("saindo"), 4200);
  window.setTimeout(() => item.remove(), 4700);
}

export function mensagemErro(e: unknown): string {
  if (e instanceof Error) return e.message;
  return String(e);
}

export interface Modal {
  fechar: () => void;
  corpo: HTMLDivElement;
}

export function abrirModal(titulo: string, conteudo: HTMLElement, rodape: HTMLElement[]): Modal {
  const corpo = h("div", { class: "modal-corpo" }, conteudo);
  const fundo = h("div", { class: "modal-fundo" });
  const fechar = () => {
    fundo.remove();
    document.removeEventListener("keydown", aoTeclar);
  };
  const aoTeclar = (ev: KeyboardEvent) => {
    if (ev.key === "Escape") fechar();
  };
  const caixa = h(
    "div",
    { class: "modal", role: "dialog", "aria-modal": "true", "aria-label": titulo },
    h(
      "div",
      { class: "modal-cabecalho" },
      h("h3", null, titulo),
      h("button", { type: "button", class: "btn-icone", "aria-label": "Fechar", onclick: () => fechar() }, "×"),
    ),
    corpo,
    h("div", { class: "modal-rodape" }, rodape),
  );
  fundo.append(caixa);
  fundo.addEventListener("click", (ev) => {
    if (ev.target === fundo) fechar();
  });
  document.addEventListener("keydown", aoTeclar);
  document.body.append(fundo);
  return { fechar, corpo };
}

const formatoPercentual = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 });
const formatoNumero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 3 });
const formatoData = new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" });

export function pct(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  return `${formatoPercentual.format(valor)}%`;
}

export function num(valor: number | null | undefined): string {
  if (valor === null || valor === undefined) return "—";
  return formatoNumero.format(valor);
}

export function dataHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const data = new Date(iso);
  if (Number.isNaN(data.getTime())) return iso;
  return formatoData.format(data);
}

export function paginas(inicio: number, fim: number): string {
  return inicio === fim ? `p. ${inicio}` : `p. ${inicio}–${fim}`;
}
