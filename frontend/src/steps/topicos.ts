// Passo 2 — Seleção dos tópicos do edital, em árvore (seções e subtópicos).
import { api } from "../api";
import type { Ctx } from "../state";
import type { Topico } from "../types";
import { badge, botao, carregando, erro, h, limpar, mensagemErro, paginas, vazio } from "../ui";

/** Agrupadores não têm texto próprio: só os demais tópicos vão para o EIR. */
const selecionavel = (t: Topico): boolean => !t.agrupador;

export function renderTopicos(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  const secao = h(
    "section",
    { class: "passo-conteudo" },
    h(
      "div",
      { class: "cabecalho-passo" },
      h("h2", null, "2. Escolha os tópicos a verificar"),
      h(
        "p",
        null,
        "O edital foi separado em seções e subtópicos pela numeração e pelos títulos (regra determinística). ",
        "Marcar uma seção marca todos os subtópicos dela. Os tópicos relevantes para BIM já vêm selecionados.",
      ),
    ),
  );
  const projeto = estado.projeto;
  if (!projeto) {
    secao.append(vazio("Envie os documentos no passo 1."));
    return secao;
  }
  const corpo = h("div", null);
  secao.append(corpo);

  if (!estado.topicos) {
    corpo.append(carregando("Carregando tópicos…"));
    api
      .topicos(projeto.id)
      .then((topicos) => {
        estado.topicos = topicos;
        estado.selecionados = new Set(
          topicos.filter((t) => t.relevante_bim && selecionavel(t)).map((t) => t.id),
        );
        ctx.atualizar();
      })
      .catch((e) => {
        limpar(corpo);
        corpo.append(erro(mensagemErro(e)));
      });
    return secao;
  }

  const topicos = estado.topicos;
  const arvore = montarArvore(topicos);
  const totalSelecionaveis = topicos.filter(selecionavel).length;
  const status = h("div", { class: "status-acao" });
  const contador = h("span", { class: "texto-suave" });
  const gerar = h("button", { type: "button", class: "btn btn-primario" }, "Gerar EIR");
  const checkboxes = new Map<string, HTMLInputElement>();
  const itens = new Map<string, HTMLElement>();
  const recolhidos = new Set<string>();

  /** Tópicos selecionáveis que um clique no tópico marca ou desmarca. */
  const alvo = (t: Topico): Topico[] =>
    [t, ...arvore.descendentes(t.id)].filter(selecionavel);

  const sincronizar = () => {
    for (const t of topicos) {
      const cb = checkboxes.get(t.id);
      if (!cb) continue;
      const lista = alvo(t);
      const marcados = lista.filter((x) => estado.selecionados.has(x.id)).length;
      cb.checked = lista.length > 0 && marcados === lista.length;
      cb.indeterminate = marcados > 0 && marcados < lista.length;
      cb.disabled = lista.length === 0;
    }
    for (const t of topicos) {
      const item = itens.get(t.id);
      if (item) item.hidden = arvore.ancestrais(t.id).some((a) => recolhidos.has(a));
    }
    const n = estado.selecionados.size;
    contador.textContent = `${n} de ${totalSelecionaveis} tópico(s) selecionado(s)`;
    gerar.disabled = n === 0;
    gerar.textContent = n ? `Gerar EIR dos ${n} tópico(s) →` : "Gerar EIR";
  };

  const lista = h("ul", { class: "lista-topicos" });
  for (const t of topicos) {
    const cb = h("input", { type: "checkbox", id: `top-${t.id}` });
    cb.addEventListener("change", () => {
      for (const x of alvo(t)) {
        if (cb.checked) estado.selecionados.add(x.id);
        else estado.selecionados.delete(x.id);
      }
      sincronizar();
    });
    checkboxes.set(t.id, cb);

    const subtopicos = arvore.filhos(t.id).length;
    let recolher: HTMLElement;
    if (subtopicos) {
      const botaoRecolher = h(
        "button",
        {
          type: "button",
          class: "topico-recolher",
          title: "Recolher ou expandir os subtópicos",
          "aria-expanded": "true",
        },
        "▾",
      );
      botaoRecolher.addEventListener("click", () => {
        const recolhido = !recolhidos.has(t.id);
        if (recolhido) recolhidos.add(t.id);
        else recolhidos.delete(t.id);
        botaoRecolher.textContent = recolhido ? "▸" : "▾";
        botaoRecolher.setAttribute("aria-expanded", String(!recolhido));
        sincronizar();
      });
      recolher = botaoRecolher;
    } else {
      recolher = h("span", { class: "topico-recolher-vazio" });
    }
    const item = itemTopico(t, cb, recolher, arvore.descendentes(t.id).length);
    itens.set(t.id, item);
    lista.append(item);
  }

  const marcar = (predicado: (t: Topico) => boolean) => {
    estado.selecionados = new Set(
      topicos.filter((t) => selecionavel(t) && predicado(t)).map((t) => t.id),
    );
    sincronizar();
  };
  const recolherTudo = (recolher: boolean) => {
    recolhidos.clear();
    for (const t of topicos) {
      if (recolher && arvore.filhos(t.id).length) recolhidos.add(t.id);
    }
    for (const b of lista.querySelectorAll<HTMLButtonElement>(".topico-recolher")) {
      b.textContent = recolher ? "▸" : "▾";
      b.setAttribute("aria-expanded", String(!recolher));
    }
    sincronizar();
  };

  gerar.addEventListener("click", async () => {
    const selecionados = topicos.filter((t) => estado.selecionados.has(t.id)).map((t) => t.id);
    if (!selecionados.length) return;
    gerar.disabled = true;
    limpar(status);
    status.append(
      carregando(
        "Extraindo requisitos dos tópicos e conferindo cada citação contra o texto do edital… Isso pode levar alguns segundos.",
      ),
    );
    try {
      estado.eir = await api.gerarEir(projeto.id, selecionados);
      estado.ids = null;
      ctx.irPara(3);
    } catch (e) {
      limpar(status);
      status.append(erro(mensagemErro(e)));
      gerar.disabled = false;
    }
  });

  const temSecoes = topicos.some((t) => arvore.filhos(t.id).length);
  corpo.append(
    h(
      "div",
      { class: "barra-ferramentas" },
      botao("Marcar relevantes para BIM", () => marcar((t) => t.relevante_bim), "fantasma"),
      botao("Marcar todos", () => marcar(() => true), "fantasma"),
      botao("Limpar seleção", () => marcar(() => false), "fantasma"),
      temSecoes ? botao("Recolher seções", () => recolherTudo(true), "fantasma") : null,
      temSecoes ? botao("Expandir tudo", () => recolherTudo(false), "fantasma") : null,
      h("span", { class: "espaco" }),
      contador,
    ),
    topicos.length ? lista : vazio("Nenhum tópico encontrado no edital."),
    h(
      "div",
      { class: "acoes acoes-fixas" },
      botao("← Voltar", () => ctx.irPara(1), "fantasma"),
      estado.eir ? botao("Ver EIR atual", () => ctx.irPara(3), "secundario") : null,
      gerar,
    ),
    status,
  );
  sincronizar();
  return secao;
}

interface Arvore {
  filhos(id: string): Topico[];
  descendentes(id: string): Topico[];
  ancestrais(id: string): string[];
}

function montarArvore(topicos: Topico[]): Arvore {
  const porId = new Map(topicos.map((t) => [t.id, t]));
  const filhosPorPai = new Map<string, Topico[]>();
  for (const t of topicos) {
    if (!t.pai_id || !porId.has(t.pai_id)) continue;
    const irmaos = filhosPorPai.get(t.pai_id) ?? [];
    irmaos.push(t);
    filhosPorPai.set(t.pai_id, irmaos);
  }
  const filhos = (id: string) => filhosPorPai.get(id) ?? [];
  const descendentes = (id: string): Topico[] =>
    filhos(id).flatMap((f) => [f, ...descendentes(f.id)]);
  const ancestrais = (id: string): string[] => {
    const lista: string[] = [];
    let pai = porId.get(id)?.pai_id ?? null;
    while (pai && porId.has(pai) && !lista.includes(pai)) {
      lista.push(pai);
      pai = porId.get(pai)?.pai_id ?? null;
    }
    return lista;
  };
  return { filhos, descendentes, ancestrais };
}

function itemTopico(
  t: Topico,
  cb: HTMLInputElement,
  recolher: HTMLElement,
  totalSubtopicos: number,
): HTMLElement {
  const indentacao = Math.max(0, Math.min(t.nivel - 1, 3));
  const classes = ["topico", `nivel-${indentacao}`];
  if (t.relevante_bim) classes.push("relevante");
  if (t.agrupador) classes.push("agrupador");
  const meta = t.agrupador
    ? `${totalSubtopicos} subtópico(s) · ${paginas(t.pagina_inicio, t.pagina_fim)}`
    : paginas(t.pagina_inicio, t.pagina_fim);
  return h(
    "li",
    { class: classes.join(" ") },
    h(
      "div",
      { class: "topico-linha" },
      recolher,
      h(
        "label",
        { class: "topico-cabecalho", for: cb.id },
        cb,
        h(
          "span",
          { class: "topico-titulo" },
          h("span", { class: "topico-numero" }, t.numero),
          h("strong", null, t.titulo),
        ),
        h("span", { class: "topico-meta" }, meta),
        t.relevante_bim ? badge("Relevante para BIM", "info") : null,
      ),
    ),
    t.resumo && !t.agrupador ? h("p", { class: "topico-resumo" }, t.resumo) : null,
    t.texto && !t.agrupador
      ? h(
          "details",
          { class: "detalhes" },
          h("summary", null, "Ver texto do tópico"),
          h("pre", { class: "texto-edital" }, t.texto),
        )
      : null,
  );
}
