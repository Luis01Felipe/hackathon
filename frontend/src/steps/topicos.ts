// Passo 2 — Seleção dos tópicos do edital, em árvore (seções e subtópicos).
import { api, falhaPassageira } from "../api";
import type { Ctx } from "../state";
import type { EirResposta, GeracaoIr, Topico } from "../types";
import {
  barraFiltros,
  botaoLimpar,
  campoBusca,
  contador as contadorFiltro,
  contem,
  filtrosReiniciaveis,
  selectFiltro,
} from "../filtros";
import { badge, botao, carregando, erro, h, limpar, mensagemErro, paginas, vazio } from "../ui";
import { abrirConfirmacaoTopicos } from "./confirmacao";

/** Agrupadores não têm texto próprio: só os demais tópicos vão para os requisitos de informação (IR). */
const selecionavel = (t: Topico): boolean => !t.agrupador;

type Mostrar = "todos" | "relevantes" | "selecionados" | "nao_selecionados";
const MOSTRAR: [Mostrar, string][] = [
  ["todos", "Todos os tópicos"],
  ["relevantes", "Relevantes para BIM"],
  ["selecionados", "Selecionados"],
  ["nao_selecionados", "Não selecionados"],
];
const filtros = filtrosReiniciaveis<{ busca: string; mostrar: Mostrar }>({ busca: "", mostrar: "todos" });

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
        ctx.atualizarNoPasso(2);
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
  const gerar = h("button", { type: "button", class: "btn btn-primario" }, "Gerar requisitos (IR)");
  const checkboxes = new Map<string, HTMLInputElement>();
  const itens = new Map<string, HTMLElement>();
  const recolhidos = new Set<string>();

  const contagem = contadorFiltro();
  const passaMostrar = (t: Topico): boolean => {
    switch (filtros.mostrar) {
      case "relevantes":
        return t.relevante_bim;
      case "selecionados":
        return estado.selecionados.has(t.id);
      case "nao_selecionados":
        return selecionavel(t) && !estado.selecionados.has(t.id);
      default:
        return true;
    }
  };
  /** Ids visíveis com busca ou filtro ativos; null quando nada filtra. */
  const visiveisPeloFiltro = (): Set<string> | null => {
    if (!filtros.busca.trim() && filtros.mostrar === "todos") return null;
    const visiveis = new Set<string>();
    for (const t of topicos) {
      if (!passaMostrar(t) || !contem(filtros.busca, t.numero, t.titulo, t.resumo)) continue;
      visiveis.add(t.id);
      for (const a of arvore.ancestrais(t.id)) visiveis.add(a);
    }
    return visiveis;
  };

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
    const visiveis = visiveisPeloFiltro();
    for (const t of topicos) {
      const item = itens.get(t.id);
      if (!item) continue;
      // Com busca ou filtro, mostra quem atende e os ancestrais (contexto), mesmo recolhidos.
      item.hidden = visiveis
        ? !visiveis.has(t.id)
        : arvore.ancestrais(t.id).some((a) => recolhidos.has(a));
    }
    contagem.definir(visiveis ? topicos.filter((t) => visiveis.has(t.id)).length : topicos.length, topicos.length);
    const n = estado.selecionados.size;
    contador.textContent = `${n} de ${totalSelecionaveis} tópico(s) selecionado(s)`;
    gerar.disabled = n === 0;
    gerar.textContent = n ? `Conferir no edital e gerar IR (${n}) →` : "Gerar requisitos (IR)";
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

  const executarGeracao = async () => {
    const selecionados = topicos.filter((t) => estado.selecionados.has(t.id)).map((t) => t.id);
    if (!selecionados.length) return;
    gerar.disabled = true;
    const inicio = performance.now();
    const andamento = h("span", null, textoAndamento(null, inicio));
    limpar(status);
    status.append(h("div", { class: "carregando", role: "status" }, h("span", { class: "spinner" }), andamento));
    // Outro projeto aberto no meio da geração: o resultado deste não vale mais.
    const vigente = () => estado.projeto?.id === projeto.id;
    try {
      const eir = await acompanharGeracao(projeto.id, selecionados, vigente, (g) => {
        andamento.textContent = textoAndamento(g, inicio);
      });
      if (!eir || !vigente()) return;
      estado.eir = eir;
      estado.ids = null;
      ctx.irPara(3);
    } catch (e) {
      if (!vigente()) return;
      limpar(status);
      status.append(erro(mensagemErro(e)));
      gerar.disabled = false;
    }
  };

  // Antes de gerar, a pessoa confere no próprio edital o que foi selecionado.
  gerar.addEventListener("click", () => {
    if (!estado.selecionados.size) return;
    abrirConfirmacaoTopicos({
      projetoId: projeto.id,
      topicos,
      selecionados: estado.selecionados,
      aoMudar: () => sincronizar(),
      aoConfirmar: () => void executarGeracao(),
    });
  });

  const temSecoes = topicos.some((t) => arvore.filhos(t.id).length);
  const busca = campoBusca("Buscar tópico por número, título ou resumo", filtros.busca, (termo) => {
    filtros.busca = termo;
    sincronizar();
  });
  const mostrar = selectFiltro("Mostrar", MOSTRAR, filtros.mostrar, (valor) => {
    filtros.mostrar = valor as Mostrar;
    sincronizar();
  });
  corpo.append(
    barraFiltros(
      busca,
      mostrar,
      botaoLimpar(() => {
        filtros.busca = "";
        filtros.mostrar = "todos";
        busca.value = "";
        mostrar.value = "todos";
        sincronizar();
      }),
      h("span", { class: "espaco" }),
      contagem.el,
    ),
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
    // O status fica na barra fixa, ao lado do botão: no fim de uma lista longa ninguém o veria.
    h(
      "div",
      { class: "acoes acoes-fixas" },
      botao("← Voltar", () => ctx.irPara(1), "fantasma"),
      estado.eir ? botao("Ver requisitos (IR)", () => ctx.irPara(3), "secundario") : null,
      gerar,
      status,
    ),
  );
  sincronizar();
  return secao;
}

const INTERVALO_CONSULTA_MS = 2000;
/** Falhas seguidas de rede toleradas na consulta (~1 min sem falar com o servidor). */
const FALHAS_TOLERADAS = 30;
const TENTATIVAS_INICIO = 3;

const esperar = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

/**
 * Gera os IR em segundo plano e consulta o andamento a cada 2 s.
 *
 * A geração leva cerca de 1 minuto. Uma requisição aberta por tanto tempo cai em proxies,
 * firewalls e redes móveis ("Failed to fetch"); consultas curtas não. Quedas passageiras
 * de rede não interrompem a geração: a consulta tenta de novo. Devolve null se o projeto
 * deixou de ser o atual no meio do caminho.
 */
async function acompanharGeracao(
  projetoId: string,
  topicos: string[],
  vigente: () => boolean,
  aoAtualizar: (g: GeracaoIr) => void,
): Promise<EirResposta | null> {
  let geracao: GeracaoIr | null = null;
  // O servidor devolve a geração em andamento se o pedido repetido chegar duas vezes.
  for (let tentativa = 1; !geracao; tentativa++) {
    try {
      geracao = await api.iniciarGeracaoIr(projetoId, topicos);
    } catch (e) {
      if (!falhaPassageira(e) || tentativa >= TENTATIVAS_INICIO) throw e;
      await esperar(INTERVALO_CONSULTA_MS);
      if (!vigente()) return null;
    }
  }
  let falhas = 0;
  while (geracao.status === "processando") {
    aoAtualizar(geracao);
    await esperar(INTERVALO_CONSULTA_MS);
    if (!vigente()) return null;
    try {
      geracao = await api.geracaoIr(projetoId);
      falhas = 0;
    } catch (e) {
      falhas += 1;
      if (!falhaPassageira(e) || falhas > FALHAS_TOLERADAS) throw e;
    }
  }
  if (geracao.status === "falhou" || !geracao.ir) {
    throw new Error(geracao.erro ?? "A geração dos requisitos falhou. Tente de novo.");
  }
  return geracao.ir;
}

function textoAndamento(g: GeracaoIr | null, inicio: number): string {
  const segundos = Math.round((performance.now() - inicio) / 1000);
  const lidos = g?.total ? ` ${g.concluidos} de ${g.total} tópicos e lições lidos (${segundos} s).` : "";
  return `Extraindo requisitos e conferindo as citações no edital…${lidos} Leva cerca de 1 minuto.`;
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
