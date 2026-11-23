// Confirmação dos tópicos no edital, antes de gerar os requisitos de informação (RI).
// À esquerda, o PDF com os tópicos selecionados grifados; à direita, a lista para conferir,
// marcar ou desmarcar. Os tópicos relevantes para BIM que ficaram de fora aparecem tracejados.
import { api, urls } from "../api";
import { VisualizadorPdf, type MarcaPdf } from "../pdf";
import type { RegiaoPdf, Topico } from "../types";
import { append, badge, carregando, erro, h, limpar, mensagemErro, paginas } from "../ui";

const regioesEmCache = new Map<string, Record<string, RegiaoPdf[]>>();

interface Opcoes {
  projetoId: string;
  topicos: Topico[];
  /** Conjunto vivo da seleção (o mesmo da tela de tópicos). */
  selecionados: Set<string>;
  aoMudar: () => void;
  aoConfirmar: () => void;
}

export function abrirConfirmacaoTopicos(opcoes: Opcoes): void {
  const { topicos, selecionados } = opcoes;
  const selecionaveis = topicos.filter((t) => !t.agrupador);
  let visualizador: VisualizadorPdf | null = null;
  let regioes: Record<string, RegiaoPdf[]> = regioesEmCache.get(opcoes.projetoId) ?? {};

  const host = h("div", { class: "revisao-pdf-visualizador" }, carregando("Abrindo o edital…"));
  const lateral = h("div", { class: "revisao-pdf-lista" });
  const confirmar = h("button", { type: "button", class: "btn btn-primario" }, "Confirmar e gerar RI");
  const fundo = h("div", { class: "revisao-pdf", role: "dialog", "aria-modal": "true", "aria-label": "Confirmar os tópicos no edital" });

  const fechar = () => {
    visualizador?.dispose();
    fundo.remove();
    document.removeEventListener("keydown", aoTeclar);
  };
  const aoTeclar = (ev: KeyboardEvent) => {
    if (ev.key === "Escape") fechar();
  };

  const marcas = (): MarcaPdf[] =>
    selecionaveis.flatMap((t) => {
      const escolhido = selecionados.has(t.id);
      if (!escolhido && !t.relevante_bim) return [];
      return [
        {
          id: t.id,
          regioes: regioes[t.id] ?? [],
          classe: escolhido ? "topico-selecionado" : "topico-sugerido",
          rotulo: t.numero,
          titulo: `${t.numero} ${t.titulo}${escolhido ? "" : " (relevante para BIM, não selecionado)"}`,
        },
      ];
    });

  const desenharLista = () => {
    limpar(lateral);
    const escolhidos = selecionaveis.filter((t) => selecionados.has(t.id));
    const sugeridos = selecionaveis.filter((t) => !selecionados.has(t.id) && t.relevante_bim);
    const outros = selecionaveis.filter((t) => !selecionados.has(t.id) && !t.relevante_bim);
    append(lateral, [
      grupo(`Selecionados (${escolhidos.length})`, escolhidos, "Nenhum tópico selecionado."),
      sugeridos.length
        ? grupo(`Relevantes para BIM fora da seleção (${sugeridos.length})`, sugeridos, "")
        : null,
      outros.length
        ? h(
            "details",
            { class: "revisao-grupo" },
            h("summary", null, `Demais tópicos (${outros.length})`),
            outros.map(item),
          )
        : null,
    ]);
    confirmar.disabled = escolhidos.length === 0;
    confirmar.textContent = `Confirmar e gerar RI (${escolhidos.length} tópico(s))`;
    visualizador?.definirMarcas(marcas());
  };

  const grupo = (titulo: string, lista: Topico[], vazio: string) =>
    h(
      "div",
      { class: "revisao-grupo" },
      h("h4", null, titulo),
      lista.length ? lista.map(item) : h("p", { class: "texto-suave" }, vazio),
    );

  const item = (t: Topico) => {
    const cb = h("input", { type: "checkbox", "aria-label": `Selecionar ${t.numero} ${t.titulo}` });
    cb.checked = selecionados.has(t.id);
    cb.addEventListener("change", () => {
      if (cb.checked) selecionados.add(t.id);
      else selecionados.delete(t.id);
      opcoes.aoMudar();
      desenharLista();
    });
    const localizado = (regioes[t.id] ?? []).length > 0;
    return h(
      "div",
      { class: `revisao-item${selecionados.has(t.id) ? " escolhido" : ""}`, "data-topico": t.id },
      cb,
      h(
        "button",
        {
          type: "button",
          class: "link-botao revisao-item-titulo",
          title: localizado ? "Ir para o tópico no edital" : "Ir para a página do tópico",
          onclick: () => {
            visualizador?.irParaMarca(t.id, t.pagina_inicio);
            marcarNaLista(t.id);
          },
        },
        h("strong", null, t.numero),
        ` ${t.titulo}`,
      ),
      h("small", { class: "texto-suave" }, paginas(t.pagina_inicio, t.pagina_fim)),
      t.relevante_bim ? badge("BIM", "info") : null,
    );
  };

  const marcarNaLista = (id: string) => {
    for (const el of lateral.querySelectorAll<HTMLElement>("[data-topico]")) {
      el.classList.toggle("ativo", el.dataset.topico === id);
    }
    const item = lateral.querySelector<HTMLElement>(`[data-topico="${CSS.escape(id)}"]`);
    const painel = lateral.parentElement;
    if (item && painel) painel.scrollTo({ top: Math.max(0, item.offsetTop - 40), behavior: "smooth" });
  };

  confirmar.addEventListener("click", () => {
    fechar();
    opcoes.aoConfirmar();
  });

  fundo.append(
    h(
      "div",
      { class: "revisao-pdf-caixa" },
      h(
        "div",
        { class: "revisao-pdf-cabecalho" },
        h(
          "div",
          null,
          h("h3", null, "Confira os tópicos no edital"),
          h(
            "p",
            { class: "texto-suave" },
            "Grifo cheio: tópico selecionado. Tracejado: relevante para BIM, mas fora da seleção. ",
            "Clique num tópico para ir até ele. O edital não é alterado.",
          ),
        ),
        h("button", { type: "button", class: "btn-icone", "aria-label": "Fechar", onclick: () => fechar() }, "×"),
      ),
      h("div", { class: "revisao-pdf-corpo" }, host, h("aside", { class: "revisao-pdf-lateral" }, lateral)),
      h(
        "div",
        { class: "revisao-pdf-rodape" },
        h("button", { type: "button", class: "btn btn-fantasma", onclick: () => fechar() }, "← Voltar e ajustar"),
        h("span", { class: "espaco" }),
        confirmar,
      ),
    ),
  );
  document.addEventListener("keydown", aoTeclar);
  document.body.append(fundo);
  desenharLista();

  void (async () => {
    try {
      if (!regioesEmCache.has(opcoes.projetoId)) {
        regioes = await api.regioesTopicos(opcoes.projetoId);
        regioesEmCache.set(opcoes.projetoId, regioes);
        desenharLista();
      }
      visualizador = await VisualizadorPdf.criar(host, urls.editalPdf(opcoes.projetoId));
      if (!fundo.isConnected) {
        visualizador.dispose();
        return;
      }
      visualizador.onMarca = (id) => marcarNaLista(id);
      visualizador.definirMarcas(marcas());
      const primeiro = selecionaveis.find((t) => selecionados.has(t.id));
      if (primeiro) visualizador.irParaMarca(primeiro.id, primeiro.pagina_inicio);
    } catch (e) {
      limpar(host);
      host.append(
        erro(`Não foi possível abrir o edital: ${mensagemErro(e)}. Você ainda pode confirmar pela lista.`),
      );
    }
  })();
}
