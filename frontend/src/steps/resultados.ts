// Passo 6 — Resultados: painel, visualizador 3D, apontamentos por origem, decisões e detalhe.
import { api, baixarArquivo, urls } from "../api";
import {
  ANALISE,
  DECISAO,
  DESTINATARIO,
  ESTADO_ELEMENTO,
  ORIGEM_INCONSISTENCIA,
  PERFIL,
  QUEM_CORRIGE,
  SEVERIDADE,
  STATUS_CHECKLIST,
  TIPO_APONTAMENTO,
  descreverRestricao,
  mapeamento,
  rotulo,
} from "../labels";
import type { Ctx } from "../state";
import type {
  Apontamento,
  Decisao,
  ElementoRef,
  EstadoElemento,
  Evidencia,
  FalhaElemento,
  Posicao,
  Relatorio,
  Requisito,
  StatusDecisao,
} from "../types";
import { barraFiltros, botaoLimpar, campoBusca, contador, contem, selectFiltro } from "../filtros";
import { citacao } from "./eir";
import { renderAbaEdital, type AbaEdital } from "./edital";
import {
  append,
  avisos,
  badge,
  botao,
  botaoDownload,
  carregando,
  dataHora,
  h,
  limpar,
  linkDownload,
  mensagemErro,
  num,
  pct,
  toast,
  vazio,
} from "../ui";
import { Viewer3D } from "../viewer";

let viewer: Viewer3D | null = null;
let geracao = 0;

type Visao = "painel" | "edital";
let visao: Visao = "painel";
let focoEdital: string | null = null;
let abaEdital: AbaEdital | null = null;

export function descartarResultados(): void {
  geracao += 1;
  viewer?.dispose();
  viewer = null;
  abaEdital?.dispose();
  abaEdital = null;
}

/** Abre os resultados direto na aba "Edital", no trecho do apontamento (link do relatório HTML). */
export function pedirFocoNoEdital(apontamentoId: string | null): void {
  visao = "edital";
  focoEdital = apontamentoId;
}

type Aba = "edital" | "modelo" | "manual" | "todos";
const filtros = {
  tipo: "todos",
  severidade: "todas",
  decisao: "todas",
  busca: "",
  mostrarBaixa: false,
  aba: "" as Aba | "",
};
const CHAVE_PERFIL = "editalcheck.perfil";
const ABA_DO_PERFIL: Record<string, Aba> = {
  contratante: "edital",
  contratado_lider: "modelo",
  contratado: "modelo",
  verificador: "todos",
};

function lerPerfil(): string {
  try {
    return window.localStorage.getItem(CHAVE_PERFIL) ?? "verificador";
  } catch {
    return "verificador";
  }
}

function salvarPerfil(perfil: string): void {
  try {
    window.localStorage.setItem(CHAVE_PERFIL, perfil);
  } catch {
    // preferência só desta sessão
  }
}

function formatarXyz(p: Posicao | null | undefined): string | null {
  if (!p) return null;
  const f = (v: number) => v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const [x, y, z] = p.centro;
  return `X ${f(x)} · Y ${f(y)} · Z ${f(z)} m`;
}

function seloOrigem(apt: Apontamento): HTMLElement {
  return h(
    "span",
    { class: `selo-origem origem-${apt.origem}`, title: QUEM_CORRIGE[apt.origem] },
    apt.origem === "edital" ? "EDITAL" : "MODELO",
  );
}
const ORDEM_SEVERIDADE: Record<string, number> = { alta: 0, media: 1, baixa: 2 };
/** Tempo máximo da conversão do IFC sem nenhum avanço antes de recriar o visualizador. */
const LIMITE_SEM_AVANCO_MS = 3 * 60 * 1000;
/** Recriações automáticas seguidas do 3D antes do plano B. */
const MAX_RECRIACOES_3D = 3;
/** Depois desse tempo estável, uma nova queda volta a contar do zero. */
const ESTAVEL_MS = 60 * 1000;

const esperar = (ms: number) => new Promise<void>((resolve) => window.setTimeout(resolve, ms));

/** Com a aba do navegador em segundo plano, a GPU fica para depois: espera ela reaparecer. */
const esperarAba = () =>
  document.visibilityState === "visible"
    ? Promise.resolve()
    : new Promise<void>((resolve) => {
        const aoMudar = () => {
          if (document.visibilityState !== "visible") return;
          document.removeEventListener("visibilitychange", aoMudar);
          resolve();
        };
        document.addEventListener("visibilitychange", aoMudar);
      });
const VARIANTE_SEVERIDADE: Record<string, string> = { alta: "alta", media: "media", baixa: "baixa" };
const VARIANTE_CHECKLIST: Record<string, string> = { presente: "sucesso", parcial: "media", ausente: "alta" };

interface Indices {
  aptsPorElemento: Map<string, Apontamento[]>;
  elementos: Map<string, ElementoRef>;
  falhasPorElemento: Map<string, { requisitoId: string | null; falha: FalhaElemento }[]>;
  estadoPorGuid: Map<string, EstadoElemento>;
  requisitos: Map<string, Requisito>;
}

function indexar(r: Relatorio): Indices {
  const indices: Indices = {
    aptsPorElemento: new Map(),
    elementos: new Map(),
    falhasPorElemento: new Map(),
    estadoPorGuid: new Map(),
    requisitos: new Map(r.requisitos.map((req) => [req.id, req])),
  };
  for (const apt of r.apontamentos) {
    for (const el of apt.elementos) {
      const anterior = indices.elementos.get(el.global_id);
      indices.elementos.set(el.global_id, { ...anterior, ...el, posicao: el.posicao ?? anterior?.posicao ?? null });
      const lista = indices.aptsPorElemento.get(el.global_id) ?? [];
      lista.push(apt);
      indices.aptsPorElemento.set(el.global_id, lista);
    }
  }
  for (const res of r.resultados_ids) {
    for (const falha of res.falhas) {
      const lista = indices.falhasPorElemento.get(falha.global_id) ?? [];
      lista.push({ requisitoId: res.requisito_id, falha });
      indices.falhasPorElemento.set(falha.global_id, lista);
      if (!indices.elementos.has(falha.global_id)) {
        indices.elementos.set(falha.global_id, {
          global_id: falha.global_id,
          step_id: falha.step_id,
          classe: falha.classe,
          nome: falha.nome,
        });
      }
    }
  }
  for (const item of r.estado_elementos) indices.estadoPorGuid.set(item.global_id, item.estado);
  return indices;
}

export function renderResultados(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  descartarResultados();
  const minhaGeracao = geracao;
  const secao = h("section", { class: "passo-conteudo resultados" });
  const relatorio = estado.relatorio;
  if (!relatorio) {
    secao.append(vazio("Execute a verificação no passo 5."));
    return secao;
  }
  const indices = indexar(relatorio);
  const projetoId = relatorio.projeto_id;
  const vid = relatorio.verificacao_id;
  const decisoes = new Map<string, Decisao>(relatorio.decisoes.map((d) => [d.apontamento_id, d]));
  let perfil = lerPerfil();
  if (!filtros.aba) filtros.aba = relatorio.sem_modelo ? "edital" : ABA_DO_PERFIL[perfil] ?? "todos";

  // ---------------------------------------------------------------- detalhe
  const detalhe = h("aside", { class: "detalhe", "aria-live": "polite" });
  const listaApts = h("div", { class: "lista-apontamentos" });
  let selecionado: string | null = null;

  const detalheVazio = () => {
    limpar(detalhe);
    detalhe.append(
      h("h3", null, "Detalhe"),
      h(
        "p",
        { class: "texto-suave" },
        "Clique num apontamento da lista ou num elemento do modelo 3D para ver o requisito, o trecho e a página do edital.",
      ),
    );
  };

  const marcarNaLista = () => {
    for (const el of listaApts.querySelectorAll<HTMLElement>("[data-apt]")) {
      el.classList.toggle("selecionado", el.dataset.apt === selecionado);
    }
  };

  const mostrarApontamento = (apt: Apontamento, focar3d = true) => {
    selecionado = apt.id;
    marcarNaLista();
    limpar(detalhe);
    detalhe.append(detalheApontamento(apt, indices, relatorio, decisoes.get(apt.id) ?? null, {
      focarElemento: (guid) => {
        void viewer?.focar([guid]);
        mostrarElemento(guid, false);
      },
      isolar: () => void viewer?.isolar(apt.elementos.map((e) => e.global_id)),
      adicionarAoEir: () => void adicionarAoEir(apt),
      decidir: async (status, comentario, autor) => {
        const decisao = await api.decidir(vid, apt.id, status, comentario, autor);
        if (decisao.status === "pendente") decisoes.delete(apt.id);
        else decisoes.set(apt.id, decisao);
        relatorio.decisoes = [...decisoes.values()];
        toast(`Decisão registrada: ${rotulo(DECISAO, decisao.status)}.`, "sucesso");
        desenharLista();
      },
    }));
    if (focar3d && viewer && apt.elementos.length) {
      void viewer.focar(apt.elementos.map((e) => e.global_id));
    }
  };

  const mostrarElemento = (guid: string, focar3d = true) => {
    limpar(detalhe);
    detalhe.append(
      detalheElemento(guid, indices, (apt) => mostrarApontamento(apt)),
    );
    if (focar3d) void viewer?.focar([guid]);
  };

  const adicionarAoEir = async (apt: Apontamento) => {
    try {
      const novos = await api.adicionarDeLacuna(projetoId, vid, apt.id);
      estado.eir = await api.ir(projetoId);
      estado.ids = null;
      toast(`${novos.length} requisito(s) sugerido(s) adicionado(s) aos IR para revisão.`, "sucesso");
      ctx.irPara(3);
    } catch (e) {
      toast(mensagemErro(e), "erro");
    }
  };

  // ---------------------------------------------------------------- lista
  const tiposPresentes = [...new Set(relatorio.apontamentos.map((a) => a.tipo))];
  const selectTipo = selectFiltro(
    "Tipo",
    [["todos", "Todos os tipos"], ...tiposPresentes.map((t) => [t, rotulo(TIPO_APONTAMENTO, t)] as [string, string])],
    filtros.tipo,
    (v) => {
      filtros.tipo = v;
      desenharLista();
    },
  );
  const selectSeveridade = selectFiltro(
    "Severidade",
    [["todas", "Todas as severidades"], ["alta", "Alta"], ["media", "Média"], ["baixa", "Baixa"]],
    filtros.severidade,
    (v) => {
      filtros.severidade = v;
      desenharLista();
    },
  );
  const contarAba = (aba: Aba) => relatorio.apontamentos.filter((a) => naAba(a, aba)).length;
  const abas = h("div", { class: "abas", role: "tablist", "aria-label": "Onde corrigir" });
  const desenharAbas = () => {
    limpar(abas);
    const opcoes: [Aba, string][] = [
      ["edital", `Corrigir no edital · contratante (${contarAba("edital")})`],
      ["modelo", `Corrigir no modelo · contratado (${contarAba("modelo")})`],
      ["manual", `Verificação manual (${contarAba("manual")})`],
      ["todos", `Todos (${relatorio.apontamentos.length})`],
    ];
    for (const [aba, texto] of opcoes) {
      if (aba === "modelo" && relatorio.sem_modelo) continue;
      abas.append(
        h(
          "button",
          {
            type: "button",
            role: "tab",
            class: `aba aba-${aba}${filtros.aba === aba ? " ativa" : ""}`,
            "aria-selected": filtros.aba === aba ? "true" : "false",
            onclick: () => {
              filtros.aba = aba;
              desenharAbas();
              desenharLista();
            },
          },
          texto,
        ),
      );
    }
  };
  const selectPerfil = selectFiltro(
    "Estou usando como",
    Object.entries(PERFIL) as [string, string][],
    perfil,
    (v) => {
      perfil = v;
      salvarPerfil(v);
      filtros.aba = relatorio.sem_modelo ? "edital" : ABA_DO_PERFIL[v] ?? "todos";
      desenharAbas();
      desenharLista();
    },
  );
  const selectDecisao = selectFiltro(
    "Decisão",
    [["todas", "Todas as decisões"], ...Object.entries(DECISAO)],
    filtros.decisao,
    (v) => {
      filtros.decisao = v;
      desenharLista();
    },
  );
  const busca = campoBusca(
    "Buscar por ID, título, como agir, página, elemento ou GUID",
    filtros.busca,
    (termo) => {
      filtros.busca = termo;
      desenharLista();
    },
  );
  const contagem = h("span", { class: "texto-suave" });
  const decisaoDe = (a: Apontamento) => decisoes.get(a.id)?.status ?? "pendente";
  const textoBusca = (a: Apontamento): string[] => [
    a.id,
    a.titulo,
    a.como_agir,
    a.detalhe,
    a.classe_ifc ?? "",
    a.requisito_id ?? "",
    rotulo(TIPO_APONTAMENTO, a.tipo),
    ...a.evidencias_edital.map((e) => `p. ${e.pagina} p.${e.pagina} ${e.trecho}`),
    ...a.elementos.map((e) => [e.global_id, e.nome, e.nome_longo, e.classe].filter(Boolean).join(" ")),
  ];

  const desenharLista = () => {
    limpar(listaApts);
    const filtrados = relatorio.apontamentos
      .filter((a) => naAba(a, filtros.aba || "todos"))
      .filter((a) => filtros.tipo === "todos" || a.tipo === filtros.tipo)
      .filter((a) => filtros.severidade === "todas" || a.severidade === filtros.severidade)
      .filter((a) => filtros.decisao === "todas" || decisaoDe(a) === filtros.decisao)
      .filter((a) => contem(filtros.busca, ...textoBusca(a)))
      .sort(
        (a, b) =>
          (ORDEM_SEVERIDADE[a.severidade] ?? 9) - (ORDEM_SEVERIDADE[b.severidade] ?? 9) || a.id.localeCompare(b.id),
      );
    // RF-162: a severidade baixa fica recolhida, com contagem visível.
    const recolher = filtros.severidade === "todas" && filtros.aba !== "manual" && !filtros.mostrarBaixa;
    const baixas = filtrados.filter((a) => a.severidade === "baixa");
    const visiveis = recolher ? filtrados.filter((a) => a.severidade !== "baixa") : filtrados;
    contagem.textContent = `${visiveis.length} de ${relatorio.apontamentos.length} apontamento(s)`;
    if (!visiveis.length && !baixas.length) {
      listaApts.append(vazio("Nenhum apontamento com esses filtros."));
      return;
    }
    for (const apt of visiveis) {
      listaApts.append(cartaoApontamento(apt, decisoes.get(apt.id) ?? null, () => mostrarApontamento(apt)));
    }
    if (recolher && baixas.length) {
      listaApts.append(
        botao(`+ ${baixas.length} apontamento(s) de severidade baixa`, () => {
          filtros.mostrarBaixa = true;
          desenharLista();
        }, "fantasma", { class: "btn btn-fantasma mostrar-baixa" }),
      );
    } else if (filtros.mostrarBaixa && baixas.length && filtros.severidade === "todas") {
      listaApts.append(
        botao("Recolher severidade baixa", () => {
          filtros.mostrarBaixa = false;
          desenharLista();
        }, "fantasma", { class: "btn btn-fantasma mostrar-baixa" }),
      );
    }
    marcarNaLista();
  };

  // ---------------------------------------------------------------- 3D
  const canvasHost = h("div", { class: "viewer-canvas" });
  const overlay = h("div", { class: "viewer-overlay" }, carregando("Preparando o visualizador 3D…"));
  const botaoTransparencia = h("button", { type: "button", class: "btn btn-fantasma btn-pequeno" }, "Sem requisito: translúcido");
  botaoTransparencia.addEventListener("click", async () => {
    if (!viewer) return;
    const ativo = await viewer.alternarTransparencia();
    botaoTransparencia.textContent = ativo ? "Sem requisito: translúcido" : "Sem requisito: opaco";
  });
  const blocoViewer = h(
    "div",
    { class: "viewer" },
    h(
      "div",
      { class: "viewer-barra" },
      h(
        "div",
        { class: "legenda" },
        h("span", { class: "legenda-item" }, h("i", { class: "cor cor-nao-conforme" }), "Não conforme"),
        h("span", { class: "legenda-item" }, h("i", { class: "cor cor-conforme" }), "Conforme"),
        h("span", { class: "legenda-item" }, h("i", { class: "cor cor-sem" }), "Sem requisito"),
        h("span", { class: "legenda-item" }, h("i", { class: "cor cor-sel" }), "Selecionado"),
      ),
      h(
        "div",
        { class: "viewer-acoes" },
        botaoTransparencia,
        botao(
          "Mostrar tudo",
          () => void viewer?.mostrarTudo(),
          "fantasma",
          { class: "btn btn-fantasma btn-pequeno", title: "Desfaz o isolamento" },
        ),
        botao("Enquadrar tudo", () => void viewer?.enquadrarTudo(), "fantasma", { class: "btn btn-fantasma btn-pequeno" }),
        botao(
          "Limpar seleção",
          () => {
            selecionado = null;
            marcarNaLista();
            detalheVazio();
            void viewer?.limparSelecao();
          },
          "fantasma",
          { class: "btn btn-fantasma btn-pequeno" },
        ),
      ),
    ),
    h("div", { class: "viewer-area" }, canvasHost, overlay),
  );

  // Recuperação automática do 3D. Cada montagem tem um número: montagens antigas
  // (substituídas por uma recuperação) param de mexer na tela. O IFC convertido fica
  // em memória como fragments, e a recriação num canvas novo não converte de novo.
  let montagem = 0;
  let recriacoes = 0;
  let fragmentosEmCache: ArrayBuffer | null = null;
  const vigente = (minha: number) => minhaGeracao === geracao && minha === montagem;
  const areaViewer = () => blocoViewer.querySelector(".viewer-area");

  const avisoNoViewer = (texto: string) => {
    if (!overlay.isConnected) areaViewer()?.append(overlay);
    overlay.classList.remove("viewer-falha");
    limpar(overlay);
    overlay.append(carregando(texto));
  };

  const planoB = (motivo: string) => {
    limpar(overlay);
    if (!overlay.isConnected) areaViewer()?.append(overlay);
    overlay.classList.add("viewer-falha");
    overlay.append(
      h(
        "div",
        { class: "alerta alerta-aviso" },
        h("strong", null, "O visualizador 3D não carregou. "),
        motivo,
        h(
          "p",
          null,
          `Tentamos recuperar ${MAX_RECRIACOES_3D} vezes. Use o relatório HTML ou abra o BCF numa ferramenta BIM `,
          "que leia BCF. O restante da tela continua funcionando.",
        ),
        h(
          "div",
          { class: "acoes" },
          linkDownload("Relatório HTML", urls.relatorioHtml(vid)),
          linkDownload("BCF dos apontamentos do modelo", urls.bcf(vid)),
          botao(
            "Tentar de novo",
            () => {
              recriacoes = 0;
              avisoNoViewer("Preparando o visualizador 3D…");
              void montarViewer();
            },
            "fantasma",
          ),
        ),
      ),
    );
  };

  /** Recria o visualizador com espera crescente; depois do limite, mostra o plano B. */
  const recuperar = async (motivo: string) => {
    if (minhaGeracao !== geracao) return;
    montagem += 1; // cala a montagem que falhou
    recriacoes += 1;
    if (recriacoes > MAX_RECRIACOES_3D) {
      viewer?.dispose();
      viewer = null;
      planoB(motivo);
      return;
    }
    console.warn(`EditalCheck: recuperando o 3D (${recriacoes}/${MAX_RECRIACOES_3D}): ${motivo}`);
    avisoNoViewer(`Recuperando o visualizador 3D (tentativa ${recriacoes} de ${MAX_RECRIACOES_3D})…`);
    await esperarAba();
    await esperar(800 * recriacoes);
    if (minhaGeracao !== geracao) return;
    await montarViewer();
  };

  const aoPerderContexto = (v: Viewer3D) => {
    avisoNoViewer("O navegador reiniciou a aceleração 3D. Recuperando o modelo…");
    // Durante a conversão, quem recria é a montagem, depois de guardar o modelo.
    if (v.carregado) void guardarFragmentos(v).then(() => recuperar("O navegador desligou a aceleração 3D."));
  };

  /** Guarda o modelo convertido para uma recuperação rápida. */
  const guardarFragmentos = async (v: Viewer3D) => {
    if (fragmentosEmCache) return;
    try {
      const buffer = await v.exportarFragmentos();
      if (buffer && minhaGeracao === geracao) fragmentosEmCache = buffer;
    } catch (e) {
      console.warn("EditalCheck: não foi possível guardar o modelo convertido", e);
    }
  };

  const montarViewer = async (): Promise<void> => {
    const minha = ++montagem;
    viewer?.dispose();
    viewer = null;
    limpar(canvasHost);
    botaoTransparencia.textContent = "Sem requisito: translúcido";
    let ultimoAvanco = performance.now();
    // Vigia: a conversão roda no navegador e pode travar sem erro.
    const vigia = window.setInterval(() => {
      if (!vigente(minha)) {
        window.clearInterval(vigia);
        return;
      }
      if (performance.now() - ultimoAvanco > LIMITE_SEM_AVANCO_MS) {
        window.clearInterval(vigia);
        void recuperar(
          `A conversão do IFC ficou mais de ${LIMITE_SEM_AVANCO_MS / 60000} minutos sem avançar. ` +
            "O modelo pode ser grande demais para este computador.",
        );
      }
    }, 5000);
    try {
      const v = await Viewer3D.criar(canvasHost);
      if (!vigente(minha)) {
        v.dispose();
        return;
      }
      viewer = v;
      v.definirVisivel(visao === "painel");
      v.onContextoPerdido = () => {
        if (vigente(minha)) aoPerderContexto(v);
      };
      v.onPick = (escolha) => {
        if (!escolha) return;
        if (!escolha.globalId) {
          limpar(detalhe);
          detalhe.append(h("h3", null, "Elemento"), h("p", { class: "texto-suave" }, "Elemento sem GlobalId."));
          return;
        }
        mostrarElemento(escolha.globalId, false);
      };
      if (fragmentosEmCache) {
        avisoNoViewer("Recarregando o modelo 3D…");
        await v.carregarFragmentos(fragmentosEmCache);
      } else {
        avisoNoViewer("Convertendo o IFC no navegador…");
        await v.carregarIfc(estado.ifcLocal ?? urls.modeloIfc(projetoId), (p) => {
          ultimoAvanco = performance.now();
          if (!vigente(minha)) return;
          const fracao = p > 1 ? p / 100 : p;
          overlay.querySelector(".carregando")?.replaceWith(
            carregando(`Convertendo o IFC no navegador… ${Math.round(fracao * 100)}%`),
          );
        });
      }
      window.clearInterval(vigia);
      if (!vigente(minha)) return;
      if (!v.contextoAtivo) {
        // Caiu durante a conversão: guarda o modelo e recria num canvas novo.
        await guardarFragmentos(v);
        if (vigente(minha)) void recuperar("O navegador desligou a aceleração 3D durante a conversão.");
        return;
      }
      void guardarFragmentos(v);
      try {
        await v.mapearElementos([...indices.elementos.values()].map((e) => ({ global_id: e.global_id, step_id: e.step_id })));
        await v.aplicarEstados(relatorio.estado_elementos);
      } catch (e) {
        // O modelo já aparece; só as cores por situação ficaram de fora.
        console.error("EditalCheck: falha ao colorir o modelo", e);
        areaViewer()?.append(
          h("div", { class: "viewer-aviso" }, `Modelo carregado sem as cores de conformidade: ${mensagemErro(e)}`),
        );
      }
      if (!vigente(minha) || !v.contextoAtivo) return;
      overlay.remove();
      window.setTimeout(() => {
        if (vigente(minha) && v.contextoAtivo) recriacoes = 0;
      }, ESTAVEL_MS);
    } catch (e) {
      window.clearInterval(vigia);
      if (!vigente(minha)) return;
      console.error("EditalCheck: falha no visualizador 3D", e);
      void recuperar(mensagemErro(e));
    }
  };
  // As duas visões ficam montadas e só alternam a visibilidade: o modelo 3D não é
  // descartado no meio do carregamento e mantém a seleção ao voltar ao painel.
  const painelConteudo = h("div", { class: "visao-painel" });
  const editalConteudo = h("div", { class: "visao-edital" });
  let viewerIniciado = false;
  const botoesVisao = new Map<Visao, HTMLButtonElement>();

  const mostrarVisao = (nova: Visao) => {
    visao = nova;
    for (const [valor, botaoVisao] of botoesVisao) {
      botaoVisao.classList.toggle("ativa", valor === nova);
      botaoVisao.setAttribute("aria-selected", valor === nova ? "true" : "false");
    }
    painelConteudo.hidden = nova !== "painel";
    editalConteudo.hidden = nova !== "edital";
    // O 3D escondido não desenha: a GPU fica livre para o PDF, e vice-versa.
    requestAnimationFrame(() => viewer?.definirVisivel(visao === "painel"));
    abaEdital?.definirVisivel(nova === "edital");
    if (nova === "edital" && !abaEdital) {
      abaEdital = renderAbaEdital(relatorio, decisoes, {
        foco: focoEdital,
        abrirNoPainel: (apt) => {
          filtros.aba = "todos";
          mostrarVisao("painel");
          desenharAbas();
          desenharLista();
          mostrarApontamento(apt, true);
          requestAnimationFrame(() => detalhe.scrollIntoView({ behavior: "smooth", block: "start" }));
        },
      });
      focoEdital = null;
      editalConteudo.append(abaEdital.elemento);
    }
    if (nova === "painel" && !viewerIniciado && !relatorio.sem_modelo) {
      viewerIniciado = true;
      requestAnimationFrame(() => void montarViewer());
    }
  };

  const alternador = h(
    "div",
    { class: "alternador-visao", role: "tablist", "aria-label": "Visão dos resultados" },
    (
      [
        ["painel", relatorio.sem_modelo ? "Painel de apontamentos" : "Painel e modelo 3D"],
        ["edital", "Edital com os ajustes (PDF)"],
      ] as [Visao, string][]
    ).map(([valor, texto]) => {
      const botaoVisao = h(
        "button",
        { type: "button", role: "tab", class: "visao", onclick: () => mostrarVisao(valor) },
        texto,
      );
      botoesVisao.set(valor, botaoVisao);
      return botaoVisao;
    }),
  );

  // ---------------------------------------------------------------- montagem
  append(painelConteudo, [
    relatorio.sem_modelo
      ? h("div", { class: "grade-resultados sem-modelo" }, detalhe)
      : h("div", { class: "grade-resultados" }, blocoViewer, detalhe),
    h(
      "div",
      { class: "cartao" },
      h(
        "div",
        { class: "cartao-titulo" },
        h("h3", null, "Apontamentos"),
        h("label", { class: "campo-inline" }, "Estou usando como: ", selectPerfil),
        contagem,
      ),
      abas,
      barraFiltros(
        busca,
        selectTipo,
        selectSeveridade,
        selectDecisao,
        botaoLimpar(() => {
          Object.assign(filtros, { tipo: "todos", severidade: "todas", decisao: "todas", busca: "" });
          busca.value = "";
          selectTipo.value = "todos";
          selectSeveridade.value = "todas";
          selectDecisao.value = "todas";
          desenharLista();
        }),
      ),
      listaApts,
    ),
    secoesComplementares(relatorio),
    h(
      "div",
      { class: "acoes" },
      botao("← Verificação", () => ctx.irPara(5), "fantasma"),
      botao("Revisar os IR", () => ctx.irPara(3), "fantasma"),
    ),
  ]);
  append(secao, [
    cabecalhoResultados(relatorio),
    painelIndicadores(relatorio),
    avisos(relatorio.avisos),
    alternador,
    painelConteudo,
    editalConteudo,
  ]);
  mostrarVisao(visao);
  detalheVazio();
  desenharAbas();
  desenharLista();
  return secao;
}

function cabecalhoResultados(relatorio: Relatorio): HTMLElement {
  const projetoId = relatorio.projeto_id;
  const vid = relatorio.verificacao_id;
  return (    h(
      "div",
      { class: "cabecalho-passo cabecalho-resultados" },
      h(
        "div",
        null,
        h("h2", null, "6. Resultados"),
        h(
          "p",
          null,
          relatorio.sem_modelo
            ? `${relatorio.edital_arquivo} · revisão do edital (sem modelo) · `
            : `${relatorio.edital_arquivo} × ${relatorio.modelo_arquivo} (${relatorio.schema_ifc}) · `,
          `escopo: ${relatorio.escopo}${relatorio.versao_ifc_ids ? ` (${relatorio.versao_ifc_ids})` : ""} · `,
          `gerado em ${dataHora(relatorio.gerado_em)} · `,
          relatorio.modo_ia === "offline" ? "modo offline (regras)" : `IA: ${relatorio.modo_ia}`,
        ),
      ),
      h(
        "div",
        { class: "downloads" },
        h("a", { class: "btn btn-primario", href: urls.relatorioHtml(vid), target: "_blank", rel: "noopener" }, "Relatório HTML"),
        botaoDownload("Edital anotado (PDF)", () => baixarArquivo(urls.editalAnotado(vid)), "edital-anotado.pdf"),
        botaoDownload(
          "Esclarecimentos (.xlsx)",
          () => baixarArquivo(urls.esclarecimentos(vid)),
          "esclarecimentos.xlsx",
        ),
        relatorio.sem_modelo ? null : linkDownload("BCF", urls.bcf(vid)),
        relatorio.sem_modelo ? null : linkDownload("IDS", urls.idsXml(projetoId)),
        linkDownload("IR (.xlsx)", urls.irXlsx(projetoId)),
        linkDownload("JSON", urls.relatorioJson(vid)),
      ),
    ));
}

// ==================================================================== componentes

function naAba(apt: Apontamento, aba: Aba): boolean {
  switch (aba) {
    case "edital":
      return apt.origem === "edital" && !apt.verificacao_manual;
    case "modelo":
      return apt.origem === "modelo";
    case "manual":
      return apt.verificacao_manual;
    default:
      return true;
  }
}

function painelIndicadores(r: Relatorio): HTMLElement {
  const i = r.indicadores;
  const sev = i.apontamentos_por_severidade;
  const origem = i.apontamentos_por_origem ?? {};
  return h(
    "div",
    { class: "indicadores" },
    h(
      "div",
      { class: "indicador indicador-origem origem-edital" },
      h("span", { class: "indicador-rotulo" }, "Corrigir no edital"),
      h("strong", { class: "indicador-valor" }, num(origem.edital ?? 0)),
      h("small", null, "apontamentos para o contratante"),
    ),
    r.sem_modelo
      ? null
      : h(
          "div",
          { class: "indicador indicador-origem origem-modelo" },
          h("span", { class: "indicador-rotulo" }, "Corrigir no modelo"),
          h("strong", { class: "indicador-valor" }, num(origem.modelo ?? 0)),
          h("small", null, "apontamentos para o contratado"),
        ),
    r.sem_modelo
      ? null
      : indicador(
          "Conformidade do modelo",
          pct(i.conformidade_percentual),
          `${num(i.especificacoes_aprovadas)} de ${num(i.especificacoes_total)} especificações IDS aprovadas · ${num(i.elementos_nao_conformes)} de ${num(i.elementos_verificados)} elementos não conformes`,
          i.conformidade_percentual,
        ),
    r.sem_modelo
      ? null
      : indicador(
          "Cobertura do edital",
          pct(i.cobertura_percentual),
          `${num(i.classes_cobertas)} de ${num(i.classes_especificaveis)} classes especificáveis do modelo têm requisito`,
          i.cobertura_percentual,
        ),
    indicador(
      "Itens mínimos do edital",
      `${num(i.checklist_presentes)} de ${num(i.checklist_total)}`,
      `${num(i.checklist_parciais)} parcial(is) na checklist inspirada na ISO 19650`,
      i.checklist_total ? (i.checklist_presentes / i.checklist_total) * 100 : null,
    ),
    i.licoes_total
      ? h(
          "div",
          { class: "indicador" },
          h("span", { class: "indicador-rotulo" }, "Lições aprendidas"),
          h("strong", { class: "indicador-valor" }, `${num(i.licoes_nao_explicitas)} de ${num(i.licoes_total)}`),
          h("small", null, "ausentes do edital"),
        )
      : null,
    h(
      "div",
      { class: "indicador" },
      h("span", { class: "indicador-rotulo" }, "Severidade"),
      h(
        "div",
        { class: "chips-linha" },
        badge(`Alta ${num(sev.alta ?? 0)}`, "alta"),
        badge(`Média ${num(sev.media ?? 0)}`, "media"),
        badge(`Baixa ${num(sev.baixa ?? 0)}`, "baixa"),
      ),
      h("small", null, `${num(i.verificacao_manual)} item(ns) de verificação manual, à parte`),
    ),
  );
}

function indicador(titulo: string, valor: string, sub: string, percentual: number | null): HTMLElement {
  const largura = percentual === null || percentual === undefined ? 0 : Math.max(0, Math.min(100, percentual));
  const classe = largura >= 80 ? "bom" : largura >= 50 ? "medio" : "ruim";
  return h(
    "div",
    { class: "indicador" },
    h("span", { class: "indicador-rotulo" }, titulo),
    h("strong", { class: "indicador-valor" }, valor),
    h("div", { class: "medidor" }, h("div", { class: `medidor-barra ${classe}`, style: `width:${largura}%` })),
    h("small", null, sub),
  );
}

const VARIANTE_DECISAO: Record<string, string> = {
  aceito: "sucesso",
  rejeitado: "alta",
  em_discussao: "media",
  dispensado: "neutro",
};

function cartaoApontamento(apt: Apontamento, decisao: Decisao | null, aoClicar: () => void): HTMLElement {
  const paginasTxt = [...new Set(apt.evidencias_edital.filter((e) => e.fonte !== "licoes").map((e) => e.pagina))]
    .map((p) => `p. ${p}`)
    .join(", ");
  return h(
    "button",
    {
      type: "button",
      class: `apontamento sev-${apt.severidade} borda-${apt.origem}`,
      "data-apt": apt.id,
      onclick: () => aoClicar(),
    },
    h(
      "div",
      { class: "apontamento-topo" },
      seloOrigem(apt),
      badge(rotulo(SEVERIDADE, apt.severidade), VARIANTE_SEVERIDADE[apt.severidade] ?? "neutro"),
      badge(rotulo(TIPO_APONTAMENTO, apt.tipo), apt.tipo === "licao_nao_explicita" ? "licao" : "neutro"),
      h("span", { class: "apontamento-id" }, apt.id),
      apt.gerado_por_ia ? badge("IA", "info", "Gerado por IA — revisar") : null,
      decisao ? badge(rotulo(DECISAO, decisao.status), VARIANTE_DECISAO[decisao.status] ?? "neutro") : null,
    ),
    h("strong", { class: "apontamento-titulo" }, apt.titulo),
    h(
      "span",
      { class: "apontamento-meta" },
      `${rotulo(DESTINATARIO, apt.destinatario)} age`,
      apt.requisito_id ? ` · ${apt.requisito_id}` : "",
      apt.licao_id ? ` · ${apt.licao_id}` : "",
      paginasTxt ? ` · Edital ${paginasTxt}` : "",
      apt.elementos.length ? ` · ${apt.elementos.length} elemento(s)` : "",
    ),
  );
}

function evidenciaBloco(ev: Evidencia, clausula?: string | null): HTMLElement {
  return h(
    "blockquote",
    { class: `trecho${ev.fonte === "licoes" ? " trecho-licao" : ""}` },
    ev.trecho,
    h("cite", null, citacao(ev, clausula)),
  );
}

function blocoDecisao(
  decisao: Decisao | null,
  decidir: (status: StatusDecisao, comentario: string, autor: string) => Promise<void>,
): HTMLElement {
  const status = h(
    "select",
    { "aria-label": "Decisão" },
    Object.entries(DECISAO).map(([valor, texto]) => h("option", { value: valor }, texto)),
  );
  status.value = decisao?.status ?? "pendente";
  const comentario = h("textarea", {
    rows: 2,
    placeholder: "Comentário ou justificativa (obrigatória para rejeitar ou dispensar)",
    "aria-label": "Comentário da decisão",
    maxlength: "1000",
  });
  comentario.value = decisao?.comentario ?? "";
  const autor = h("input", { type: "text", placeholder: "Quem decide (nome ou papel)", "aria-label": "Autor", maxlength: "120" });
  autor.value = decisao?.autor ?? "";
  const mensagem = h("div", null);
  const salvar = h("button", { type: "button", class: "btn btn-secundario" }, "Registrar decisão");
  salvar.addEventListener("click", async () => {
    limpar(mensagem);
    salvar.disabled = true;
    try {
      await decidir(status.value as StatusDecisao, comentario.value, autor.value);
    } catch (e) {
      mensagem.append(h("div", { class: "alerta alerta-erro" }, mensagemErro(e)));
    } finally {
      salvar.disabled = false;
    }
  });
  return h(
    "div",
    { class: "detalhe-secao decisao" },
    h("h4", null, "Decisão (registro de consenso)"),
    h(
      "p",
      { class: "texto-suave" },
      "A decisão não apaga o apontamento: um apontamento dispensado continua no relatório, com a justificativa.",
    ),
    status,
    comentario,
    autor,
    h("div", { class: "acoes" }, salvar),
    decisao?.data ? h("small", { class: "texto-suave" }, `Última decisão em ${dataHora(decisao.data)}`) : null,
    mensagem,
  );
}

function blocoRequisito(req: Requisito): HTMLElement {
  const restricao = descreverRestricao(req.restricao);
  return h(
    "div",
    { class: "bloco-requisito" },
    h("div", { class: "bloco-titulo" }, h("strong", null, req.id), " ", req.descricao),
    h("code", { class: "mapa" }, mapeamento(req)),
    restricao ? h("small", null, `Restrição: ${restricao}`) : null,
    evidenciaBloco(req.evidencia, req.clausula),
  );
}

function detalheApontamento(
  apt: Apontamento,
  indices: Indices,
  relatorio: Relatorio,
  decisao: Decisao | null,
  acoes: {
    focarElemento: (guid: string) => void;
    isolar: () => void;
    adicionarAoEir: () => void;
    decidir: (status: StatusDecisao, comentario: string, autor: string) => Promise<void>;
  },
): HTMLElement {
  const req = apt.requisito_id ? indices.requisitos.get(apt.requisito_id) : undefined;
  const reqIds = new Set(apt.requisito_id ? [apt.requisito_id] : []);
  const evidencias = apt.evidencias_edital.filter(
    (ev) => !req || ev.trecho !== req.evidencia.trecho || ev.pagina !== req.evidencia.pagina,
  );
  const elementos = apt.elementos.slice(0, 12);
  const resultado = relatorio.resultados_ids.find((r) => r.requisito_id && reqIds.has(r.requisito_id));
  return h(
    "div",
    { class: "detalhe-conteudo" },
    h(
      "div",
      { class: "detalhe-selos" },
      seloOrigem(apt),
      badge(rotulo(SEVERIDADE, apt.severidade), VARIANTE_SEVERIDADE[apt.severidade] ?? "neutro"),
      badge(rotulo(TIPO_APONTAMENTO, apt.tipo), "neutro"),
      badge(rotulo(ANALISE, apt.analise), "neutro"),
    ),
    h("h3", null, h("span", { class: "texto-suave" }, `${apt.id} · `), apt.titulo),
    h(
      "p",
      { class: `quem-age quem-age-${apt.origem}` },
      h("strong", null, rotulo(QUEM_CORRIGE, apt.origem)),
      ` — o problema está no ${rotulo(ORIGEM_INCONSISTENCIA, apt.origem).toLowerCase()}.`,
    ),
    apt.gerado_por_ia || apt.referencia_a_confirmar
      ? h(
          "div",
          { class: "detalhe-selos" },
          apt.gerado_por_ia ? badge("Gerado por IA — revisar", "media") : null,
          apt.referencia_a_confirmar ? badge("Referência a confirmar", "alta") : null,
        )
      : null,
    apt.detalhe ? h("p", null, apt.detalhe) : null,
    req ? h("div", { class: "detalhe-secao" }, h("h4", null, "Requisito"), blocoRequisito(req)) : null,
    resultado
      ? h(
          "p",
          { class: "texto-suave" },
          `IDS: ${num(resultado.aprovados)} de ${num(resultado.aplicaveis)} elemento(s) aplicável(is) aprovados.`,
        )
      : null,
    evidencias.length
      ? h("div", { class: "detalhe-secao" }, h("h4", null, "Trechos de origem"), evidencias.map((ev) => evidenciaBloco(ev)))
      : null,
    elementos.length
      ? h(
          "div",
          { class: "detalhe-secao" },
          h("h4", null, `Elementos (${apt.elementos.length})`),
          relatorio.sem_modelo
            ? null
            : h("div", { class: "acoes" }, botao("Isolar no 3D", () => acoes.isolar(), "secundario", {
                class: "btn btn-secundario btn-pequeno",
                title: "Esconde o resto do modelo e enquadra estes elementos",
              })),
          h(
            "ul",
            { class: "lista-elementos" },
            elementos.map((el) => {
              const xyz = formatarXyz(el.posicao ?? indices.elementos.get(el.global_id)?.posicao);
              return h(
                "li",
                null,
                h(
                  "button",
                  { type: "button", class: "link-botao", onclick: () => acoes.focarElemento(el.global_id) },
                  el.nome_longo ?? el.nome ?? "(sem nome)",
                ),
                h("small", null, ` ${el.classe ?? ""} · `, h("code", null, el.global_id)),
                xyz ? h("small", { class: "xyz" }, ` · ${xyz}`) : null,
              );
            }),
          ),
          apt.elementos.length > elementos.length
            ? h("small", { class: "texto-suave" }, `e mais ${apt.elementos.length - elementos.length} elemento(s)`)
            : null,
        )
      : null,
    apt.como_agir ? h("div", { class: "detalhe-secao" }, h("h4", null, "Como agir"), h("p", null, apt.como_agir)) : null,
    apt.por_que ? h("div", { class: "detalhe-secao" }, h("h4", null, "Por que"), h("p", null, apt.por_que)) : null,
    apt.referencias.length
      ? h(
          "div",
          { class: "detalhe-secao" },
          h("h4", null, "Referências"),
          h(
            "ul",
            { class: "lista-referencias" },
            apt.referencias.map((ref) =>
              h(
                "li",
                null,
                ref.uri ? h("a", { href: ref.uri, target: "_blank", rel: "noopener" }, ref.rotulo) : ref.rotulo,
              ),
            ),
          ),
        )
      : null,
    apt.propriedades_sugeridas.length
      ? h(
          "div",
          { class: "detalhe-secao" },
          h("h4", null, "Propriedades sugeridas (Psets oficiais)"),
          h(
            "ul",
            { class: "lista-compacta" },
            apt.propriedades_sugeridas.map((p) =>
              h("li", null, h("code", null, `${p.pset}.${p.nome}`), p.tipo_dado ? ` (${p.tipo_dado})` : ""),
            ),
          ),
        )
      : null,
    apt.tipo === "lacuna_cobertura"
      ? h(
          "div",
          { class: "acoes" },
          botao("Adicionar aos IR", () => acoes.adicionarAoEir(), "primario", {
            title: "Cria requisitos sugeridos e volta à revisão dos requisitos de informação",
          }),
        )
      : null,
    blocoDecisao(decisao, acoes.decidir),
  );
}

function detalheElemento(guid: string, indices: Indices, abrir: (apt: Apontamento) => void): HTMLElement {
  const info = indices.elementos.get(guid);
  const estadoEl = indices.estadoPorGuid.get(guid);
  const apts = indices.aptsPorElemento.get(guid) ?? [];
  const falhas = indices.falhasPorElemento.get(guid) ?? [];
  return h(
    "div",
    { class: "detalhe-conteudo" },
    h(
      "div",
      { class: "detalhe-selos" },
      estadoEl
        ? badge(rotulo(ESTADO_ELEMENTO, estadoEl), estadoEl === "conforme" ? "sucesso" : "alta")
        : badge("Sem requisito", "neutro"),
    ),
    h("h3", null, info?.nome_longo ?? info?.nome ?? "Elemento do modelo"),
    h(
      "dl",
      { class: "dados-elemento" },
      h("dt", null, "Classe"),
      h("dd", null, info?.classe ?? "—"),
      info?.nome_longo && info?.nome ? h("dt", null, "Nome") : null,
      info?.nome_longo && info?.nome ? h("dd", null, info.nome) : null,
      h("dt", null, "GlobalId"),
      h("dd", null, h("code", null, guid)),
      info?.pavimento ? h("dt", null, "Pavimento") : null,
      info?.pavimento ? h("dd", null, info.pavimento) : null,
      info?.posicao ? h("dt", null, "Coordenada (centro)") : null,
      info?.posicao ? h("dd", null, formatarXyz(info.posicao)) : null,
      info?.step_id ? h("dt", null, "Id no arquivo") : null,
      info?.step_id ? h("dd", null, `#${info.step_id}`) : null,
    ),
    falhas.length
      ? h(
          "div",
          { class: "detalhe-secao" },
          h("h4", null, "Falhas na validação IDS"),
          h(
            "ul",
            { class: "lista-compacta" },
            falhas.map(({ requisitoId, falha }) =>
              h("li", null, requisitoId ? h("strong", null, `${requisitoId}: `) : null, falha.motivo),
            ),
          ),
        )
      : null,
    apts.length
      ? h(
          "div",
          { class: "detalhe-secao" },
          h("h4", null, `Apontamentos ligados (${apts.length})`),
          apts.map((apt) => {
            const req = apt.requisito_id ? indices.requisitos.get(apt.requisito_id) : undefined;
            const ev = req?.evidencia ?? apt.evidencias_edital[0];
            return h(
              "div",
              { class: "apt-ligado" },
              h(
                "button",
                { type: "button", class: "link-botao", onclick: () => abrir(apt) },
                `${apt.id} · ${apt.titulo}`,
              ),
              req ? h("small", null, `${req.id} — ${req.descricao}`) : null,
              ev ? evidenciaBloco(ev, req?.clausula) : null,
            );
          }),
        )
      : h(
          "p",
          { class: "texto-suave" },
          estadoEl === "conforme"
            ? "O elemento atende a todos os requisitos do IDS aplicáveis a ele."
            : "Nenhum requisito de informação (IR) se aplica a este elemento.",
        ),
  );
}

interface LinhaFiltravel {
  el: HTMLElement;
  texto: (string | null | undefined)[];
  grupo: string;
}

/** Busca e filtro por grupo de cada tabela complementar, mantidos entre redesenhos. */
const filtrosTabelas = new Map<string, { busca: string; grupo: string }>();

function filtroDeTabela(
  chave: string,
  linhas: LinhaFiltravel[],
  placeholder: string,
  grupos: [string, string][],
): HTMLElement | null {
  if (linhas.length < 2) return null;
  const estado = filtrosTabelas.get(chave) ?? { busca: "", grupo: "" };
  filtrosTabelas.set(chave, estado);
  const contagem = contador();
  const aplicar = () => {
    let visiveis = 0;
    for (const linha of linhas) {
      linha.el.hidden = (estado.grupo !== "" && linha.grupo !== estado.grupo) || !contem(estado.busca, ...linha.texto);
      if (!linha.el.hidden) visiveis += 1;
    }
    contagem.definir(visiveis, linhas.length);
  };
  aplicar();
  return barraFiltros(
    campoBusca(placeholder, estado.busca, (termo) => {
      estado.busca = termo;
      aplicar();
    }),
    selectFiltro("Filtrar", [["", "Todos"], ...grupos], estado.grupo, (valor) => {
      estado.grupo = valor;
      aplicar();
    }),
    h("span", { class: "espaco" }),
    contagem.el,
  );
}

function secoesComplementares(r: Relatorio): HTMLElement {
  const itens = new Map(r.itens_checklist.map((i) => [i.id, i]));
  const linhasChecklist: LinhaFiltravel[] = r.checklist.map((res) => {
    const item = itens.get(res.item_id);
    return {
      grupo: res.status,
      texto: [res.item_id, item?.item, res.justificativa, res.evidencia?.trecho, rotulo(STATUS_CHECKLIST, res.status)],
      el: h(
        "tr",
        null,
        h("td", null, h("strong", null, res.item_id), " ", item?.item ?? ""),
        h("td", null, item?.critico ? badge("Sim", "alta") : "Não"),
        h("td", null, badge(rotulo(STATUS_CHECKLIST, res.status), VARIANTE_CHECKLIST[res.status] ?? "neutro")),
        h(
          "td",
          { class: "col-evidencia" },
          res.evidencia ? evidenciaBloco(res.evidencia) : h("span", { class: "texto-suave" }, res.justificativa || "—"),
        ),
        h("td", null, res.avaliado_por === "llm" ? "IA (conferida)" : "Regras"),
      ),
    };
  });
  const checklist = h(
    "details",
    { class: "cartao detalhes-cartao" },
    h("summary", null, h("strong", null, "Checklist de itens mínimos do edital"), ` · ${r.checklist.length} itens`),
    r.checklist.length
      ? [
          filtroDeTabela("checklist", linhasChecklist, "Buscar item da checklist", Object.entries(STATUS_CHECKLIST)),
          h(
            "div",
            { class: "tabela-rolagem" },
            h(
              "table",
              { class: "tabela lista-filtrada" },
              h(
                "thead",
                null,
                h("tr", null, h("th", null, "Item"), h("th", null, "Crítico"), h("th", null, "Status"), h("th", null, "Evidência"), h("th", null, "Avaliado por")),
              ),
              h("tbody", null, linhasChecklist.map((l) => l.el)),
            ),
          ),
        ]
      : vazio("Checklist não avaliada."),
  );

  const linhasCobertura: LinhaFiltravel[] = [...(r.cobertura?.classes ?? [])]
    .sort((a, b) => Number(a.coberta) - Number(b.coberta) || b.contagem - a.contagem)
    .map((c) => ({
      grupo: c.coberta ? "coberta" : "lacuna",
      texto: [c.classe, c.requisitos.join(" ")],
      el: h(
        "tr",
        null,
        h("td", null, h("code", null, c.classe)),
        h("td", { class: "num" }, num(c.contagem)),
        h("td", null, c.coberta ? badge("Sim", "sucesso") : badge("Lacuna", "alta")),
        h("td", null, c.requisitos.join(", ") || "—"),
      ),
    }));
  const cobertura = h(
    "details",
    { class: "cartao detalhes-cartao" },
    h(
      "summary",
      null,
      h("strong", null, "Cobertura do edital por classe IFC"),
      r.cobertura ? ` · ${pct(r.cobertura.percentual)}` : "",
    ),
    linhasCobertura.length
      ? [
          filtroDeTabela("cobertura", linhasCobertura, "Buscar classe IFC ou requisito", [
            ["coberta", "Cobertas"],
            ["lacuna", "Lacunas"],
          ]),
          h(
            "div",
            { class: "tabela-rolagem" },
            h(
              "table",
              { class: "tabela compacta lista-filtrada" },
              h("thead", null, h("tr", null, h("th", null, "Classe"), h("th", { class: "num" }, "Elementos"), h("th", null, "Coberta"), h("th", null, "Requisitos"))),
              h("tbody", null, linhasCobertura.map((l) => l.el)),
            ),
          ),
        ]
      : vazio("Cobertura não calculada."),
  );

  const linhasIds: LinhaFiltravel[] = r.resultados_ids.map((res) => {
    const grupo = res.aplicaveis === 0 ? "sem_elementos" : res.status ? "aprovada" : "reprovada";
    return {
      grupo,
      texto: [res.nome_especificacao],
      el: h(
        "tr",
        null,
        h("td", null, res.nome_especificacao),
        h("td", { class: "num" }, num(res.aplicaveis)),
        h("td", { class: "num" }, num(res.aprovados)),
        h(
          "td",
          null,
          grupo === "sem_elementos"
            ? badge("Sem elementos", "neutro")
            : grupo === "aprovada"
              ? badge("Aprovada", "sucesso")
              : badge("Reprovada", "alta"),
        ),
      ),
    };
  });
  const ids = h(
    "details",
    { class: "cartao detalhes-cartao" },
    h("summary", null, h("strong", null, "Resultados do IDS por especificação"), ` · ${r.resultados_ids.length}`),
    linhasIds.length
      ? [
          filtroDeTabela("ids", linhasIds, "Buscar especificação", [
            ["reprovada", "Só reprovadas"],
            ["aprovada", "Aprovadas"],
            ["sem_elementos", "Sem elementos"],
          ]),
          h(
            "div",
            { class: "tabela-rolagem" },
            h(
              "table",
              { class: "tabela compacta lista-filtrada" },
              h("thead", null, h("tr", null, h("th", null, "Especificação"), h("th", { class: "num" }, "Aplicáveis"), h("th", { class: "num" }, "Aprovados"), h("th", null, "Status"))),
              h("tbody", null, linhasIds.map((l) => l.el)),
            ),
          ),
        ]
      : vazio("Nenhuma especificação IDS executada."),
  );
  return h(
    "div",
    { class: "complementares" },
    painelCusto(r),
    blocoLicoesResultado(r),
    r.sem_modelo ? null : ids,
    r.sem_modelo ? null : cobertura,
    checklist,
  );
}

function blocoLicoesResultado(r: Relatorio): HTMLElement | null {
  if (!r.licoes.length) return null;
  const porId = new Map(r.verificacoes_licoes.map((v) => [v.licao_id, v]));
  const linhas: LinhaFiltravel[] = r.licoes.map((l) => {
    const v = porId.get(l.id);
    const grupo = !v ? "nao_avaliada" : v.explicita ? "explicita" : "ausente";
    return {
      grupo,
      texto: [l.id, l.titulo, l.regra, l.documento],
      el: h(
        "tr",
        null,
        h("td", null, badge(l.id, "licao"), " ", l.titulo),
        h("td", null, l.regra, h("small", { class: "texto-suave" }, ` (${l.documento}, p. ${l.evidencia.pagina})`)),
        h(
          "td",
          null,
          !v
            ? badge("Não avaliada", "neutro")
            : v.explicita
              ? [badge("Explícita", "sucesso"), v.evidencia ? h("small", null, ` p. ${v.evidencia.pagina}`) : null]
              : badge("Ausente", "alta"),
        ),
      ),
    };
  });
  return h(
    "details",
    { class: "cartao detalhes-cartao", open: true },
    h(
      "summary",
      null,
      h("strong", null, "Lições aprendidas"),
      ` · ${r.indicadores.licoes_nao_explicitas} de ${r.licoes.length} ausentes do edital`,
    ),
    filtroDeTabela("licoes", linhas, "Buscar lição aprendida", [
      ["ausente", "Ausentes do edital"],
      ["explicita", "Explícitas no edital"],
      ["nao_avaliada", "Não avaliadas"],
    ]),
    h(
      "div",
      { class: "tabela-rolagem" },
      h(
        "table",
        { class: "tabela compacta lista-filtrada" },
        h("thead", null, h("tr", null, h("th", null, "Lição"), h("th", null, "Regra"), h("th", null, "No edital?"))),
        h("tbody", null, linhas.map((l) => l.el)),
      ),
    ),
  );
}

const formatoUsd = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "USD", maximumFractionDigits: 4 });

/** RF-195 a RF-197: tokens medidos, custo pelos preços configurados e tempo manual medido. */
function painelCusto(r: Relatorio): HTMLElement {
  const custo = r.custo;
  const tempoIa = Object.values(r.duracoes_s).reduce((a, b) => a + b, 0);
  const manual = r.tempo_manual;
  return h(
    "details",
    { class: "cartao detalhes-cartao" },
    h(
      "summary",
      null,
      h("strong", null, "Custo e tempo"),
      custo ? ` · ${num(custo.tokens_entrada + custo.tokens_saida)} tokens` : "",
      custo?.usd !== null && custo?.usd !== undefined ? ` · ${formatoUsd.format(custo.usd)}` : "",
    ),
    r.consumo.length
      ? h(
          "div",
          { class: "tabela-rolagem" },
          h(
            "table",
            { class: "tabela compacta" },
            h(
              "thead",
              null,
              h("tr", null, h("th", null, "Etapa"), h("th", { class: "num" }, "Chamadas"), h("th", { class: "num" }, "Tokens de entrada"), h("th", { class: "num" }, "Tokens de saída"), h("th", { class: "num" }, "Tempo de IA")),
            ),
            h(
              "tbody",
              null,
              r.consumo.map((c) =>
                h(
                  "tr",
                  null,
                  h("td", null, c.etapa),
                  h("td", { class: "num" }, num(c.chamadas), c.chamadas_cache ? ` (+${num(c.chamadas_cache)} cache)` : ""),
                  h("td", { class: "num" }, num(c.tokens_entrada)),
                  h("td", { class: "num" }, num(c.tokens_saida)),
                  h("td", { class: "num" }, `${num(c.duracao_s)} s`),
                ),
              ),
            ),
          ),
        )
      : h("p", { class: "texto-suave" }, "Sem chamadas de IA nesta verificação (modo de regras determinísticas)."),
    h(
      "dl",
      { class: "metricas" },
      h("div", { class: "metrica" }, h("dt", null, "Tempo das análises"), h("dd", null, `${num(tempoIa)} s`)),
      h(
        "div",
        { class: "metrica" },
        h("dt", null, "Custo estimado"),
        h(
          "dd",
          null,
          custo?.usd !== null && custo?.usd !== undefined
            ? `${formatoUsd.format(custo.usd)} (fonte do preço: ${custo.fonte_preco || "não informada"})`
            : "Configure o preço do modelo para calcular",
        ),
      ),
      h(
        "div",
        { class: "metrica" },
        h("dt", null, "Tempo manual equivalente"),
        h(
          "dd",
          null,
          manual?.medido && manual.horas !== null
            ? `${num(manual.horas)} h medidas (${manual.amostra})`
            : "Não medido pelo time",
        ),
      ),
    ),
    r.contexto_usado.length
      ? h("p", { class: "texto-suave" }, `Documentos de referência usados como contexto: ${r.contexto_usado.join(", ")}.`)
      : null,
  );
}
