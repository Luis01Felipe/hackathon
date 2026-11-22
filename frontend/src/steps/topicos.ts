// Passo 2 — Seleção dos tópicos do edital.
import { api } from "../api";
import type { Ctx } from "../state";
import type { Topico } from "../types";
import { badge, botao, carregando, erro, h, limpar, mensagemErro, paginas, vazio } from "../ui";

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
        "O edital foi separado em tópicos pela numeração e pelos títulos (regra determinística). ",
        "Os tópicos marcados como relevantes para BIM já vêm selecionados.",
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
        estado.selecionados = new Set(topicos.filter((t) => t.relevante_bim).map((t) => t.id));
        ctx.atualizar();
      })
      .catch((e) => {
        limpar(corpo);
        corpo.append(erro(mensagemErro(e)));
      });
    return secao;
  }

  const topicos = estado.topicos;
  const status = h("div", { class: "status-acao" });
  const contador = h("span", { class: "texto-suave" });
  const gerar = h("button", { type: "button", class: "btn btn-primario" }, "Gerar EIR");

  const atualizarContador = () => {
    const n = estado.selecionados.size;
    contador.textContent = `${n} de ${topicos.length} tópico(s) selecionado(s)`;
    gerar.disabled = n === 0;
    gerar.textContent = n ? `Gerar EIR dos ${n} tópico(s) →` : "Gerar EIR";
  };

  const lista = h("ul", { class: "lista-topicos" });
  const checkboxes = new Map<string, HTMLInputElement>();
  for (const t of topicos) {
    const cb = h("input", { type: "checkbox", id: `top-${t.id}` });
    cb.checked = estado.selecionados.has(t.id);
    cb.addEventListener("change", () => {
      if (cb.checked) estado.selecionados.add(t.id);
      else estado.selecionados.delete(t.id);
      atualizarContador();
    });
    checkboxes.set(t.id, cb);
    lista.append(itemTopico(t, cb));
  }

  const marcar = (predicado: (t: Topico) => boolean) => {
    estado.selecionados = new Set(topicos.filter(predicado).map((t) => t.id));
    for (const [id, cb] of checkboxes) cb.checked = estado.selecionados.has(id);
    atualizarContador();
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

  corpo.append(
    h(
      "div",
      { class: "barra-ferramentas" },
      botao("Marcar relevantes para BIM", () => marcar((t) => t.relevante_bim), "fantasma"),
      botao("Marcar todos", () => marcar(() => true), "fantasma"),
      botao("Limpar seleção", () => marcar(() => false), "fantasma"),
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
  atualizarContador();
  return secao;
}

function itemTopico(t: Topico, cb: HTMLInputElement): HTMLElement {
  const indentacao = Math.max(0, Math.min(t.nivel - 1, 3));
  return h(
    "li",
    { class: `topico nivel-${indentacao}${t.relevante_bim ? " relevante" : ""}` },
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
      h("span", { class: "topico-meta" }, paginas(t.pagina_inicio, t.pagina_fim)),
      t.relevante_bim ? badge("Relevante para BIM", "info") : null,
    ),
    t.resumo ? h("p", { class: "topico-resumo" }, t.resumo) : null,
    h("details", { class: "detalhes" }, h("summary", null, "Ver texto do tópico"), h("pre", { class: "texto-edital" }, t.texto)),
  );
}
