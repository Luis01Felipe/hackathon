// Barra de filtros e busca reutilizada em todas as páginas. O estado de cada filtro fica no
// módulo de cada passo, para sobreviver ao redesenho da página (ctx.atualizar).
import { h } from "./ui";

const ESPERA_BUSCA_MS = 150;

/** Texto sem acento e em minúsculas, para a busca não depender de grafia. */
export function normalizarBusca(texto: string): string {
  return texto
    .normalize("NFD")
    .replace(/\p{Mn}/gu, "")
    .toLowerCase()
    .trim();
}

/** Todas as palavras do termo aparecem em algum dos textos. Termo vazio aceita tudo. */
export function contem(termo: string, ...textos: (string | number | null | undefined)[]): boolean {
  const palavras = normalizarBusca(termo).split(/\s+/).filter(Boolean);
  if (!palavras.length) return true;
  const alvo = normalizarBusca(textos.filter((t) => t !== null && t !== undefined).join(" "));
  return palavras.every((p) => alvo.includes(p));
}

export function campoBusca(
  placeholder: string,
  valor: string,
  aoMudar: (termo: string) => void,
): HTMLInputElement {
  const input = h("input", {
    type: "search",
    class: "campo-busca",
    placeholder,
    "aria-label": placeholder,
    autocomplete: "off",
    spellcheck: "false",
  });
  input.value = valor;
  let espera: number | undefined;
  input.addEventListener("input", () => {
    window.clearTimeout(espera);
    espera = window.setTimeout(() => aoMudar(input.value), ESPERA_BUSCA_MS);
  });
  input.addEventListener("keydown", (ev) => {
    if (ev.key !== "Escape" || !input.value) return;
    ev.stopPropagation();
    input.value = "";
    window.clearTimeout(espera);
    aoMudar("");
  });
  return input;
}

export function selectFiltro(
  rotuloTexto: string,
  opcoes: [string, string][],
  atual: string,
  aoMudar: (v: string) => void,
): HTMLSelectElement {
  const sel = h(
    "select",
    { "aria-label": rotuloTexto, title: rotuloTexto },
    opcoes.map(([valor, texto]) => h("option", { value: valor }, texto)),
  );
  sel.value = opcoes.some(([v]) => v === atual) ? atual : opcoes[0][0];
  sel.addEventListener("change", () => aoMudar(sel.value));
  return sel;
}

export function caixaFiltro(rotuloTexto: string, marcado: boolean, aoMudar: (v: boolean) => void): HTMLLabelElement {
  const cb = h("input", { type: "checkbox" });
  cb.checked = marcado;
  cb.addEventListener("change", () => aoMudar(cb.checked));
  return h("label", { class: "check-inline" }, cb, rotuloTexto);
}

/** Contador "X de Y" que a página atualiza a cada redesenho da lista. */
export function contador(): { el: HTMLSpanElement; definir: (visiveis: number, total: number) => void } {
  const el = h("span", { class: "contagem-filtro", "aria-live": "polite" });
  return {
    el,
    definir: (visiveis, total) => {
      el.textContent = visiveis === total ? `${total} no total` : `${visiveis} de ${total}`;
    },
  };
}

/** Barra com busca, filtros e contagem; os demais filhos (ex.: botões) vão depois. */
export function barraFiltros(...filhos: (HTMLElement | null)[]): HTMLDivElement {
  return h("div", { class: "barra-ferramentas barra-filtros", role: "search" }, ...filhos);
}

export function botaoLimpar(aoLimpar: () => void): HTMLButtonElement {
  return h("button", { type: "button", class: "btn btn-fantasma btn-pequeno", onclick: () => aoLimpar() }, "Limpar filtros");
}
