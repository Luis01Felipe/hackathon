// Resultados — aba "Edital": o PDF à esquerda, com um grifo por apontamento, e os ajustes à
// direita. Clicar num ajuste leva ao trecho e abre o detalhe. Só leitura: o PDF não é editado.
import { api, urls } from "../api";
import { DECISAO, ORIGEM_INCONSISTENCIA, QUEM_CORRIGE, SEVERIDADE, TIPO_APONTAMENTO, rotulo } from "../labels";
import { VisualizadorPdf, type MarcaPdf } from "../pdf";
import type { Apontamento, Decisao, LocalApontamento, Relatorio } from "../types";
import { append, badge, botao, carregando, erro, h, limpar, linkDownload, mensagemErro, vazio } from "../ui";
import { citacao } from "./eir";

const ORDEM_SEVERIDADE: Record<string, number> = { alta: 0, media: 1, baixa: 2 };
const filtros = { edital: true, modelo: true, severidade: "todas" };

export interface AbaEdital {
  elemento: HTMLElement;
  dispose: () => void;
}

interface Opcoes {
  foco: string | null;
  abrirNoPainel: (apt: Apontamento) => void;
}

export function renderAbaEdital(r: Relatorio, decisoes: Map<string, Decisao>, opcoes: Opcoes): AbaEdital {
  let visualizador: VisualizadorPdf | null = null;
  let descartado = false;
  let locais = new Map<string, LocalApontamento>();
  let ativo: string | null = opcoes.foco;

  const host = h("div", { class: "edital-visualizador" }, carregando("Abrindo o edital…"));
  const lista = h("div", { class: "edital-lista" });
  const contagem = h("span", { class: "texto-suave" });

  /** Apontamentos que cabem na aba: todos os do edital e os do modelo ligados a uma cláusula. */
  const candidatos = () =>
    r.apontamentos.filter((a) => a.origem === "edital" || (locais.get(a.id)?.paginas.length ?? 0) > 0);

  const visiveis = () =>
    candidatos()
      .filter((a) => (a.origem === "edital" ? filtros.edital : filtros.modelo))
      .filter((a) => filtros.severidade === "todas" || a.severidade === filtros.severidade);

  const marcas = (): MarcaPdf[] =>
    visiveis().map((a) => ({
      id: a.id,
      regioes: locais.get(a.id)?.regioes ?? [],
      classe: `sev-${a.severidade} origem-${a.origem}`,
      rotulo: a.id,
      titulo: `${a.id} · ${a.titulo}`,
    }));

  const primeiraPagina = (a: Apontamento): number | undefined => {
    const local = locais.get(a.id);
    return local?.regioes[0]?.pagina ?? local?.paginas[0];
  };

  const ordenar = (lista: Apontamento[]) =>
    [...lista].sort(
      (a, b) =>
        (primeiraPagina(a) ?? 9999) - (primeiraPagina(b) ?? 9999) ||
        (locais.get(a.id)?.regioes[0]?.y0 ?? 0) - (locais.get(b.id)?.regioes[0]?.y0 ?? 0) ||
        (ORDEM_SEVERIDADE[a.severidade] ?? 9) - (ORDEM_SEVERIDADE[b.severidade] ?? 9),
    );

  const selecionar = (id: string, rolarPdf = true) => {
    ativo = id;
    const apt = r.apontamentos.find((a) => a.id === id);
    if (rolarPdf && apt) visualizador?.irParaMarca(id, primeiraPagina(apt));
    else visualizador?.irParaMarca(id);
    desenharLista();
    // Rola só a lista lateral (scrollIntoView rolaria a página inteira e esconderia o grifo).
    const item = lista.querySelector<HTMLElement>(`[data-apt="${CSS.escape(id)}"]`);
    const lateral = lista.parentElement;
    if (item && lateral) lateral.scrollTo({ top: Math.max(0, item.offsetTop - 8), behavior: "smooth" });
  };

  const desenharLista = () => {
    limpar(lista);
    const todos = visiveis();
    const comTrecho = ordenar(todos.filter((a) => primeiraPagina(a) !== undefined));
    const semTrecho = todos.filter((a) => primeiraPagina(a) === undefined);
    contagem.textContent = `${todos.length} ajuste(s)`;
    if (!todos.length) {
      lista.append(vazio("Nenhum ajuste com esses filtros."));
      return;
    }
    append(lista, [
      comTrecho.length ? h("h4", { class: "edital-grupo" }, "No texto do edital, na ordem das páginas") : null,
      comTrecho.map((a) => itemAjuste(a)),
      semTrecho.length
        ? h(
            "h4",
            { class: "edital-grupo" },
            "Sem trecho no edital",
            h("small", { class: "texto-suave" }, " · pedem uma cláusula nova (itens ausentes, lacunas, lições)"),
          )
        : null,
      semTrecho.map((a) => itemAjuste(a)),
    ]);
  };

  const itemAjuste = (a: Apontamento): HTMLElement => {
    const pagina = primeiraPagina(a);
    const localizado = locais.get(a.id)?.localizado ?? false;
    const decisao = decisoes.get(a.id);
    const aberto = a.id === ativo;
    return h(
      "div",
      { class: `edital-item sev-${a.severidade} borda-${a.origem}${aberto ? " ativo" : ""}`, "data-apt": a.id },
      h(
        "button",
        { type: "button", class: "edital-item-cabecalho", onclick: () => selecionar(a.id) },
        h(
          "span",
          { class: "apontamento-topo" },
          h("span", { class: `selo-origem origem-${a.origem}` }, a.origem === "edital" ? "EDITAL" : "MODELO"),
          badge(rotulo(SEVERIDADE, a.severidade), a.severidade),
          h("span", { class: "apontamento-id" }, a.id),
          pagina !== undefined ? h("small", { class: "texto-suave" }, `p. ${pagina}${localizado ? "" : " (página)"}`) : null,
          decisao ? badge(rotulo(DECISAO, decisao.status), "neutro") : null,
        ),
        h("strong", null, a.titulo),
      ),
      aberto ? detalhe(a, decisao ?? null) : null,
    );
  };

  const detalhe = (a: Apontamento, decisao: Decisao | null): HTMLElement =>
    h(
      "div",
      { class: "edital-detalhe" },
      h(
        "p",
        { class: `quem-age quem-age-${a.origem}` },
        h("strong", null, rotulo(QUEM_CORRIGE, a.origem)),
        ` — problema no ${rotulo(ORIGEM_INCONSISTENCIA, a.origem).toLowerCase()} · ${rotulo(TIPO_APONTAMENTO, a.tipo)}`,
      ),
      a.evidencias_edital.map((ev) =>
        h(
          "blockquote",
          { class: `trecho${ev.fonte === "licoes" ? " trecho-licao" : ""}` },
          ev.trecho,
          h("cite", null, citacao(ev)),
        ),
      ),
      a.detalhe ? h("p", null, a.detalhe) : null,
      a.como_agir ? h("div", { class: "detalhe-secao" }, h("h4", null, "Como agir"), h("p", null, a.como_agir)) : null,
      a.por_que ? h("div", { class: "detalhe-secao" }, h("h4", null, "Por que"), h("p", null, a.por_que)) : null,
      a.referencias.length
        ? h(
            "div",
            { class: "detalhe-secao" },
            h("h4", null, "Referências"),
            h(
              "ul",
              { class: "lista-referencias" },
              a.referencias.map((ref) =>
                h("li", null, ref.uri ? h("a", { href: ref.uri, target: "_blank", rel: "noopener" }, ref.rotulo) : ref.rotulo),
              ),
            ),
          )
        : null,
      decisao
        ? h(
            "p",
            { class: "decisao-registrada" },
            h("strong", null, `Decisão: ${rotulo(DECISAO, decisao.status)}`),
            decisao.comentario ? ` — ${decisao.comentario}` : "",
            decisao.autor ? ` (${decisao.autor})` : "",
          )
        : null,
      a.gerado_por_ia ? badge("Texto gerado por IA — revisar", "media") : null,
      h(
        "div",
        { class: "acoes" },
        botao("Abrir no painel para decidir", () => opcoes.abrirNoPainel(a), "secundario", {
          class: "btn btn-secundario btn-pequeno",
          title: "A decisão é registrada no painel de apontamentos",
        }),
      ),
    );

  const caixa = (texto: string, chave: "edital" | "modelo") => {
    const cb = h("input", { type: "checkbox" });
    cb.checked = filtros[chave];
    cb.addEventListener("change", () => {
      filtros[chave] = cb.checked;
      desenharLista();
      visualizador?.definirMarcas(marcas());
    });
    return h("label", { class: `check-inline filtro-${chave}` }, cb, texto);
  };
  const severidade = h(
    "select",
    { "aria-label": "Severidade" },
    h("option", { value: "todas" }, "Todas as severidades"),
    h("option", { value: "alta" }, "Alta"),
    h("option", { value: "media" }, "Média"),
    h("option", { value: "baixa" }, "Baixa"),
  );
  severidade.value = filtros.severidade;
  severidade.addEventListener("change", () => {
    filtros.severidade = severidade.value;
    desenharLista();
    visualizador?.definirMarcas(marcas());
  });

  const elemento = h(
    "div",
    { class: "cartao aba-edital" },
    h(
      "div",
      { class: "cartao-titulo" },
      h("h3", null, "Edital com os ajustes"),
      contagem,
      h("span", { class: "espaco" }),
      linkDownload("Baixar PDF com as sugestões", urls.editalAnotado(r.verificacao_id), "primario"),
    ),
    h(
      "p",
      { class: "texto-suave" },
      "Clique num ajuste para ir ao trecho, ou num grifo para ver o ajuste. O PDF baixado traz o mesmo conteúdo: ",
      "sumário com links, grifos com notas e índice lateral.",
    ),
    h(
      "div",
      { class: "barra-ferramentas" },
      caixa("Corrigir no edital", "edital"),
      r.sem_modelo ? null : caixa("Corrigir no modelo (na cláusula de origem)", "modelo"),
      severidade,
    ),
    h("div", { class: "edital-grade" }, host, h("aside", { class: "edital-lateral" }, lista)),
  );

  desenharLista();
  void (async () => {
    try {
      const lidos = await api.regioesApontamentos(r.verificacao_id);
      if (descartado) return;
      locais = new Map(lidos.map((l) => [l.apontamento_id, l]));
      desenharLista();
      const v = await VisualizadorPdf.criar(host, urls.editalPdf(r.projeto_id));
      if (descartado) {
        v.dispose();
        return;
      }
      visualizador = v;
      v.onMarca = (id) => selecionar(id, false);
      v.definirMarcas(marcas());
      if (ativo) selecionar(ativo);
    } catch (e) {
      if (descartado) return;
      limpar(host);
      host.append(erro(`Não foi possível abrir o edital: ${mensagemErro(e)}`));
    }
  })();

  return {
    elemento,
    dispose: () => {
      descartado = true;
      visualizador?.dispose();
      visualizador = null;
    },
  };
}
