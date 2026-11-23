// Passo 3 — Revisão humana dos requisitos de informação (IR): aceitar, editar ou rejeitar
// cada requisito, cadastrar marcos de entrega e conferir as lições aprendidas.
import { api, urls } from "../api";
import {
  barraFiltros,
  botaoLimpar,
  campoBusca,
  contador,
  contem,
  filtrosReiniciaveis,
  selectFiltro,
} from "../filtros";
import {
  CARDINALIDADE,
  DESCRICAO_VERIFICACAO,
  FACETA,
  ITEM_CHECAGEM,
  ORIGEM,
  STATUS_REQUISITO,
  TIPO_RESTRICAO,
  TIPO_VERIFICACAO,
  descreverRestricao,
  mapeamento,
  rotulo,
  verificacaoDe,
  verificacaoEntraNoIds,
} from "../labels";
import type { Ctx } from "../state";
import type {
  AcaoRequisito,
  Cardinalidade,
  CamposEdicao,
  Evidencia,
  Faceta,
  ItemChecagem,
  MarcoEntrega,
  ProjetoResumo,
  Requisito,
  Restricao,
  TipoRestricao,
  TipoVerificacao,
  Topico,
} from "../types";
import {
  abrirModal,
  append,
  avisos,
  badge,
  botao,
  carregando,
  erro,
  h,
  limpar,
  linkDownload,
  mensagemErro,
  toast,
  vazio,
} from "../ui";

interface FiltrosEir {
  busca: string;
  status: string;
  topico: string;
  ambiente: string;
  item: string;
  verificacao: string;
  origem: string;
}

const TODOS = "todos";
const SEM_AMBIENTE = "__sem_ambiente__";
const FILTROS_PADRAO: FiltrosEir = {
  busca: "",
  status: TODOS,
  topico: TODOS,
  ambiente: TODOS,
  item: TODOS,
  verificacao: TODOS,
  origem: TODOS,
};
const filtros = filtrosReiniciaveis<FiltrosEir>(FILTROS_PADRAO);
const COLUNAS_TABELA = 6;

const VARIANTE_STATUS: Record<string, string> = {
  proposto: "neutro",
  aprovado: "sucesso",
  editado: "info",
  rejeitado: "alta",
};

const VARIANTE_ORIGEM: Record<string, string> = {
  pset_oficial: "sucesso",
  bsdd: "info",
  customizado: "media",
};

export const VARIANTE_VERIFICACAO: Record<TipoVerificacao, string> = {
  ids: "sucesso",
  ids_script: "info",
  script: "media",
  manual: "neutro",
};

const TOPICOS_ESPECIAIS: Record<string, string> = {
  LICOES: "Lições aprendidas",
  LACUNA: "Sugerido por lacuna",
};

type OrigemRequisito = "edital" | "licao" | "lacuna";
const ORIGEM_REQUISITO: Record<OrigemRequisito, string> = {
  edital: "Do edital",
  licao: "De lições aprendidas",
  lacuna: "Sugeridos por lacuna",
};

function origemDe(req: Requisito): OrigemRequisito {
  if (req.sugerido_por_lacuna) return "lacuna";
  if (req.gerado_por === "licao") return "licao";
  return "edital";
}

const aprovadoOuEditado = (r: Requisito) => r.status === "aprovado" || r.status === "editado";

interface RotuloTopico {
  numero: string;
  titulo: string;
  caminho: string;
}

/** Tópico de origem do requisito: número, título e caminho até a seção de nível 1. */
export function rotuloTopico(topicoId: string, topicos: Topico[] | null): RotuloTopico {
  const especial = TOPICOS_ESPECIAIS[topicoId];
  if (especial) return { numero: "—", titulo: especial, caminho: especial };
  const porId = new Map((topicos ?? []).map((t) => [t.id, t]));
  const topico = porId.get(topicoId);
  if (!topico) return { numero: topicoId, titulo: "", caminho: topicoId };
  const cadeia: string[] = [];
  for (let atual: Topico | undefined = topico; atual; atual = atual.pai_id ? porId.get(atual.pai_id) : undefined) {
    cadeia.unshift(`${atual.numero} ${atual.titulo}`);
  }
  return { numero: topico.numero, titulo: topico.titulo, caminho: cadeia.join(" › ") };
}

function atende(req: Requisito, topicos: Topico[] | null): boolean {
  const verificacao = verificacaoDe(req);
  if (filtros.status === "aprovados" && !aprovadoOuEditado(req)) return false;
  if (![TODOS, "aprovados"].includes(filtros.status) && req.status !== filtros.status) return false;
  if (filtros.topico !== TODOS && req.topico_id !== filtros.topico) return false;
  if (filtros.ambiente === SEM_AMBIENTE && req.ambientes.length) return false;
  if (![TODOS, SEM_AMBIENTE].includes(filtros.ambiente) && !req.ambientes.includes(filtros.ambiente)) return false;
  if (filtros.item !== TODOS && (req.item_checagem ?? "") !== filtros.item) return false;
  if (filtros.verificacao === "entra_ids" && !verificacaoEntraNoIds(verificacao)) return false;
  if (filtros.verificacao === "fora_ids" && verificacaoEntraNoIds(verificacao)) return false;
  if (!["entra_ids", "fora_ids", TODOS].includes(filtros.verificacao) && verificacao !== filtros.verificacao) {
    return false;
  }
  if (filtros.origem !== TODOS && origemDe(req) !== filtros.origem) return false;
  const topico = rotuloTopico(req.topico_id, topicos);
  return contem(
    filtros.busca,
    req.id,
    req.descricao,
    req.evidencia.trecho,
    req.ifc_class,
    req.pset,
    req.propriedade,
    req.ambientes.join(" "),
    req.item_checagem ? `${req.item_checagem} ${ITEM_CHECAGEM[req.item_checagem]}` : null,
    `${topico.numero} ${topico.titulo}`,
  );
}

export function renderEir(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  const secao = h(
    "section",
    { class: "passo-conteudo" },
    h(
      "div",
      { class: "cabecalho-passo" },
      h("h2", null, "3. Revise os requisitos de informação (IR)"),
      h(
        "p",
        null,
        "Os IR (Information Requirements) são o contrato de dados da contratação: o que o modelo deve conter em cada entrega. ",
        "Cada requisito mostra o tópico de origem, os ambientes, a disciplina e como será verificado. ",
        "Nenhum requisito vira IDS sem a sua aprovação.",
      ),
    ),
  );
  const projeto = estado.projeto;
  if (!projeto) {
    secao.append(vazio("Envie os documentos no passo 1."));
    return secao;
  }
  if (!estado.eir) {
    secao.append(carregando("Carregando os requisitos de informação…"));
    api
      .ir(projeto.id)
      .then((eir) => {
        estado.eir = eir;
        ctx.atualizarNoPasso(3);
      })
      .catch((e) => {
        secao.lastChild?.remove();
        secao.append(erro(mensagemErro(e)), botao("← Voltar aos tópicos", () => ctx.irPara(2), "fantasma"));
      });
    return secao;
  }
  if (!estado.topicos) {
    // A coluna Tópico mostra número e título: busca os tópicos se a página abriu direto aqui.
    api
      .topicos(projeto.id)
      .then((topicos) => {
        estado.topicos = topicos;
        ctx.atualizarNoPasso(3);
      })
      .catch(() => undefined);
  }

  const eir = estado.eir;
  const resumo = h("div", { class: "resumo-eir" });
  const barra = h("div", null);
  const corpoTabela = h("tbody", null);
  const status = h("div", { class: "status-acao" });
  const contagem = contador();

  const atualizarResumo = () => {
    limpar(resumo);
    const reqs = eir.requisitos;
    const contar = (f: (r: Requisito) => boolean) => reqs.filter(f).length;
    const aprovados = contar(aprovadoOuEditado);
    const paraIds = contar((r) => aprovadoOuEditado(r) && verificacaoEntraNoIds(verificacaoDe(r)));
    resumo.append(
      chipFiltro("Requisitos", reqs.length, "neutro", {}),
      chipFiltro("Propostos", contar((r) => r.status === "proposto"), "neutro", { status: "proposto" }),
      chipFiltro("Aprovados", aprovados, "sucesso", { status: "aprovados" }),
      chipFiltro("Rejeitados", contar((r) => r.status === "rejeitado"), "alta", { status: "rejeitado" }),
      chipFiltro("Fora do IDS", contar((r) => !verificacaoEntraNoIds(verificacaoDe(r))), "media", {
        verificacao: "fora_ids",
      }),
      chipFiltro("De lições aprendidas", contar((r) => origemDe(r) === "licao"), "licao", { origem: "licao" }),
      chipFiltro("Entram no IDS", paraIds, "info", { status: "aprovados", verificacao: "entra_ids" }),
    );
  };

  /** Chip do resumo que aplica um filtro; clicar de novo (ou em "Requisitos") limpa. */
  const chipFiltro = (texto: string, valor: number, variante: string, alvo: Partial<FiltrosEir>): HTMLElement => {
    const chaves = Object.keys(alvo) as (keyof FiltrosEir)[];
    const ativo =
      chaves.length > 0 &&
      (Object.keys(FILTROS_PADRAO) as (keyof FiltrosEir)[]).every((k) =>
        k in alvo ? filtros[k] === alvo[k] : filtros[k] === FILTROS_PADRAO[k],
      );
    return h(
      "button",
      {
        type: "button",
        class: `chip chip-${variante} chip-filtro${ativo ? " chip-ativo" : ""}`,
        "aria-pressed": ativo ? "true" : "false",
        title: chaves.length ? `Filtrar: ${texto}` : "Mostrar todos",
        onclick: () => aplicarFiltros(ativo ? {} : alvo),
      },
      h("strong", null, String(valor)),
      h("span", null, texto),
    );
  };

  const aplicarFiltros = (alvo: Partial<FiltrosEir>) => {
    Object.assign(filtros, FILTROS_PADRAO, { busca: filtros.busca }, alvo);
    desenharBarra();
    atualizarResumo();
    desenharLinhas();
  };

  const substituir = (req: Requisito) => {
    const indice = eir.requisitos.findIndex((r) => r.id === req.id);
    if (indice >= 0) eir.requisitos[indice] = req;
    else eir.requisitos.push(req);
    estado.ids = null;
  };

  const agir = async (req: Requisito, acao: AcaoRequisito) => {
    try {
      substituir(await api.atualizarRequisito(projeto.id, req.id, acao));
      if (acao.acao === "editar") desenharBarra();
      desenharLinhas();
      atualizarResumo();
    } catch (e) {
      toast(mensagemErro(e), "erro");
    }
  };

  const desenharLinhas = () => {
    limpar(corpoTabela);
    const visiveis = eir.requisitos.filter((r) => atende(r, estado.topicos));
    contagem.definir(visiveis.length, eir.requisitos.length);
    if (!visiveis.length) {
      corpoTabela.append(
        h("tr", null, h("td", { colspan: String(COLUNAS_TABELA) }, vazio("Nenhum requisito com esses filtros."))),
      );
      return;
    }
    const marcos = marcosPorId();
    for (const req of visiveis) {
      corpoTabela.append(linhaRequisito(req, estado.topicos, agir, (r) => editar(r), marcos));
    }
  };

  const ambientesConhecidos = () =>
    [...new Set(eir.requisitos.flatMap((r) => r.ambientes))].sort((a, b) => a.localeCompare(b, "pt-BR"));

  const desenharBarra = () => {
    limpar(barra);
    const mudar = (chave: keyof FiltrosEir) => (valor: string) => {
      filtros[chave] = valor;
      atualizarResumo();
      desenharLinhas();
    };
    const topicosUsados = [...new Set(eir.requisitos.map((r) => r.topico_id))].map((id) => {
      const t = rotuloTopico(id, estado.topicos);
      return [id, t.numero === "—" ? t.titulo : `${t.numero} ${t.titulo}`.trim()] as [string, string];
    });
    barra.append(
      barraFiltros(
        campoBusca("Buscar por ID, texto, classe IFC, ambiente ou tópico", filtros.busca, mudar("busca")),
        selectFiltro(
          "Status",
          [[TODOS, "Status: todos"], ["aprovados", "Aprovados e editados"], ...Object.entries(STATUS_REQUISITO)],
          filtros.status,
          mudar("status"),
        ),
        selectFiltro("Tópico", [[TODOS, "Tópico: todos"], ...topicosUsados], filtros.topico, mudar("topico")),
        selectFiltro(
          "Ambiente",
          [
            [TODOS, "Ambiente: todos"],
            [SEM_AMBIENTE, "Sem ambiente (todo o tópico)"],
            ...ambientesConhecidos().map((a) => [a, a] as [string, string]),
          ],
          filtros.ambiente,
          mudar("ambiente"),
        ),
        selectFiltro(
          "Item de checagem",
          [
            [TODOS, "Item: todos"],
            ...Object.entries(ITEM_CHECAGEM).map(([sigla, nome]) => [sigla, `${sigla} · ${nome}`] as [string, string]),
          ],
          filtros.item,
          mudar("item"),
        ),
        selectFiltro(
          "Verificação",
          [
            [TODOS, "Verificação: toda"],
            ["entra_ids", "Entram no IDS"],
            ["fora_ids", "Fora do IDS"],
            ...Object.entries(TIPO_VERIFICACAO),
          ],
          filtros.verificacao,
          mudar("verificacao"),
        ),
        selectFiltro("Origem", [[TODOS, "Origem: toda"], ...Object.entries(ORIGEM_REQUISITO)], filtros.origem, mudar("origem")),
        botaoLimpar(() => {
          Object.assign(filtros, FILTROS_PADRAO);
          desenharBarra();
          atualizarResumo();
          desenharLinhas();
        }),
        h("span", { class: "espaco" }),
        contagem.el,
      ),
      h(
        "datalist",
        { id: "lista-ambientes" },
        ambientesConhecidos().map((a) => h("option", { value: a })),
      ),
    );
  };

  const marcosPorId = () => new Map(projeto.marcos.map((m) => [m.id, m.nome]));
  const editar = (req: Requisito) => {
    abrirEdicao(req, projeto.marcos, async (campos) => {
      await agir(req, { acao: "editar", campos });
    });
  };
  const blocoMarcos = h("div", null);
  const desenharMarcos = () => {
    limpar(blocoMarcos);
    blocoMarcos.append(
      editorMarcos(projeto, async (marcos) => {
        projeto.marcos = marcos;
        estado.ids = null;
        estado.eir = await api.ir(projeto.id);
        ctx.atualizarNoPasso(3);
      }),
    );
  };
  desenharMarcos();

  const aprovarTodos = async () => {
    limpar(status);
    status.append(carregando("Aprovando requisitos verificáveis…"));
    try {
      const novo = await api.aprovarTodos(projeto.id, true);
      estado.eir = novo;
      estado.ids = null;
      toast("Requisitos verificáveis aprovados.", "sucesso");
      ctx.atualizarNoPasso(3);
    } catch (e) {
      limpar(status);
      status.append(erro(mensagemErro(e)));
    }
  };

  const podeGerarIds = () => eir.requisitos.some((r) => aprovadoOuEditado(r) && r.verificavel_por_ids);

  append(secao, [
    resumo,
    blocoLicoes(projeto),
    blocoMarcos,
    avisos(eir.avisos, "Avisos da extração"),
    eir.descartados > 0
      ? h(
          "div",
          { class: "alerta alerta-info" },
          h("strong", null, `${eir.descartados} requisito(s) descartado(s). `),
          "A citação do edital não conferiu literalmente com o texto da página (salvaguarda S2).",
        )
      : null,
    barra,
    h(
      "div",
      { class: "barra-ferramentas" },
      h("span", { class: "espaco" }),
      botao("Aceitar todos os verificáveis", () => void aprovarTodos(), "sucesso"),
      linkDownload("Baixar IR (.xlsx)", urls.irXlsx(projeto.id)),
    ),
    status,
    h(
      "div",
      { class: "tabela-rolagem" },
      h(
        "table",
        { class: "tabela tabela-eir" },
        h(
          "thead",
          null,
          h(
            "tr",
            null,
            h("th", null, "ID"),
            h("th", null, "Requisito e trecho de origem"),
            h("th", null, "Tópico, ambiente e item"),
            h("th", null, "Mapeamento IFC"),
            h("th", null, "Verificação"),
            h("th", { class: "col-acoes" }, "Ações"),
          ),
        ),
        corpoTabela,
      ),
    ),
    h(
      "div",
      { class: "acoes acoes-fixas" },
      botao("← Tópicos", () => ctx.irPara(2), "fantasma"),
      h("span", { class: "espaco" }),
      h(
        "button",
        {
          type: "button",
          class: "btn btn-primario",
          onclick: () => {
            if (!podeGerarIds()) {
              toast("Aprove pelo menos um requisito verificável por IDS.", "erro");
              return;
            }
            ctx.irPara(4);
          },
        },
        "Gerar IDS →",
      ),
    ),
  ]);
  desenharBarra();
  atualizarResumo();
  desenharLinhas();
  return secao;
}

export function citacao(ev: Evidencia, clausula?: string | null): string {
  const local = [`p. ${ev.pagina}`, clausula ? `item ${clausula}` : null].filter(Boolean).join(" · ");
  return `${ev.fonte === "licoes" ? "Lições aprendidas" : "Edital"}, ${local}`;
}

function linhaRequisito(
  req: Requisito,
  topicos: Topico[] | null,
  agir: (req: Requisito, acao: AcaoRequisito) => Promise<void>,
  editar: (req: Requisito) => void,
  marcos: Map<string, string>,
): HTMLElement {
  const aprovado = aprovadoOuEditado(req);
  const restricao = descreverRestricao(req.restricao);
  const topico = rotuloTopico(req.topico_id, topicos);
  const verificacao = verificacaoDe(req);
  return h(
    "tr",
    { class: `linha-req status-${req.status}` },
    h(
      "td",
      { class: "col-id" },
      h("strong", null, req.id),
      badge(rotulo(STATUS_REQUISITO, req.status), VARIANTE_STATUS[req.status] ?? "neutro"),
      req.sugerido_por_lacuna ? badge("Sugerido por lacuna", "info") : null,
      req.licao_id ? badge(`Lição ${req.licao_id}`, "licao", "Requisito proposto a partir de uma lição aprendida") : null,
      req.gerado_por && !["llm", "licao"].includes(req.gerado_por)
        ? h("small", { class: "texto-suave" }, `origem: ${req.gerado_por}`)
        : null,
    ),
    h(
      "td",
      { class: "col-req", "data-rotulo": "Requisito e trecho de origem" },
      h("p", { class: "req-descricao" }, req.descricao),
      h(
        "blockquote",
        { class: `trecho${req.evidencia.fonte === "licoes" ? " trecho-licao" : ""}` },
        req.evidencia.trecho,
        h("cite", null, citacao(req.evidencia, req.clausula)),
      ),
      h(
        "div",
        { class: "marcos-req" },
        req.marcos.length
          ? req.marcos.map((m) => badge(marcos.get(m) ?? m, "neutro", "Marco de entrega"))
          : h("small", { class: "texto-suave" }, "Vale para todos os marcos de entrega"),
      ),
      req.avisos.length ? h("ul", { class: "avisos-req" }, req.avisos.map((a) => h("li", null, a))) : null,
    ),
    h(
      "td",
      { class: "col-classif", "data-rotulo": "Tópico, ambiente e item" },
      h(
        "div",
        { class: "classif-topico", title: topico.caminho },
        topico.numero !== "—" ? h("strong", { class: "ir-topico-numero" }, topico.numero) : null,
        h("span", { class: "ir-topico-titulo" }, topico.titulo || "—"),
      ),
      h(
        "div",
        { class: "classif-ambiente" },
        req.ambientes.length
          ? req.ambientes.map((a) => badge(a, "ambiente", "Ambiente"))
          : h("small", { class: "texto-suave" }, "Todo o tópico"),
      ),
      h(
        "div",
        { class: "classif-item" },
        req.item_checagem
          ? [
              badge(req.item_checagem, `item badge-item-${req.item_checagem.toLowerCase()}`, ITEM_CHECAGEM[req.item_checagem]),
              h("small", { class: "texto-suave item-nome" }, ITEM_CHECAGEM[req.item_checagem]),
            ]
          : h("small", { class: "texto-suave" }, "Sem item de checagem"),
      ),
    ),
    h(
      "td",
      { class: "col-map", "data-rotulo": "Mapeamento IFC" },
      h("code", { class: "mapa" }, mapeamento(req)),
      h(
        "div",
        { class: "mapa-detalhes" },
        req.faceta ? h("span", null, rotulo(FACETA, req.faceta)) : null,
        req.tipo_dado ? h("span", null, req.tipo_dado) : null,
        restricao ? h("span", null, restricao) : null,
        h("span", null, rotulo(CARDINALIDADE, req.cardinalidade)),
      ),
      h(
        "div",
        { class: "mapa-vocabulario" },
        req.origem_vocabulario
          ? badge(rotulo(ORIGEM, req.origem_vocabulario), VARIANTE_ORIGEM[req.origem_vocabulario] ?? "neutro", "Origem do vocabulário")
          : null,
        req.bsdd_uri
          ? h("a", { href: req.bsdd_uri, target: "_blank", rel: "noopener", class: "link-bsdd" }, "ver no bSDD")
          : null,
      ),
    ),
    h(
      "td",
      { class: "col-verif", "data-rotulo": "Verificação" },
      badge(TIPO_VERIFICACAO[verificacao], VARIANTE_VERIFICACAO[verificacao], DESCRICAO_VERIFICACAO[verificacao]),
      !req.verificavel_por_ids && req.motivo_nao_verificavel
        ? h("small", { class: "motivo" }, req.motivo_nao_verificavel)
        : null,
    ),
    h(
      "td",
      { class: "col-acoes" },
      !aprovado && req.status !== "rejeitado"
        ? botao("Aceitar", () => void agir(req, { acao: "aprovar" }), "sucesso", { title: "Aprovar requisito" })
        : null,
      botao("Editar", () => editar(req), "secundario"),
      req.status !== "rejeitado"
        ? botao("Rejeitar", () => void agir(req, { acao: "rejeitar" }), "perigo")
        : null,
      req.status !== "proposto" ? botao("Reabrir", () => void agir(req, { acao: "reabrir" }), "fantasma") : null,
    ),
  );
}

function abrirEdicao(
  req: Requisito,
  marcos: MarcoEntrega[],
  salvar: (campos: CamposEdicao) => Promise<void>,
): void {
  const texto = (valor: string | null | undefined) => valor ?? "";
  const nulo = (valor: string) => (valor.trim() === "" ? null : valor.trim());

  const descricao = h("textarea", { rows: 3, id: "ed-descricao" });
  descricao.value = req.descricao;
  const ifcClass = h("input", { type: "text", id: "ed-classe", placeholder: "IfcDoor" });
  ifcClass.value = texto(req.ifc_class);
  const predefined = h("input", { type: "text", id: "ed-predef", placeholder: "opcional" });
  predefined.value = texto(req.predefined_type);
  const faceta = h(
    "select",
    { id: "ed-faceta" },
    h("option", { value: "" }, "—"),
    Object.entries(FACETA).map(([v, t]) => h("option", { value: v }, t)),
  );
  faceta.value = req.faceta ?? "";
  const pset = h("input", { type: "text", id: "ed-pset", placeholder: "Pset_DoorCommon" });
  pset.value = texto(req.pset);
  const propriedade = h("input", { type: "text", id: "ed-prop", placeholder: "FireRating" });
  propriedade.value = texto(req.propriedade);
  const tipoDado = h("input", { type: "text", id: "ed-tipo", placeholder: "IfcLabel" });
  tipoDado.value = texto(req.tipo_dado);
  const cardinalidade = h(
    "select",
    { id: "ed-card" },
    Object.entries(CARDINALIDADE).map(([v, t]) => h("option", { value: v }, t)),
  );
  cardinalidade.value = req.cardinalidade;

  const tipoRestricao = h(
    "select",
    { id: "ed-restr" },
    h("option", { value: "" }, "Sem restrição"),
    Object.entries(TIPO_RESTRICAO).map(([v, t]) => h("option", { value: v }, t)),
  );
  tipoRestricao.value = req.restricao?.tipo ?? "";
  const valores = h("input", { type: "text", id: "ed-valores", placeholder: "valores separados por ;" });
  valores.value = req.restricao?.valores.join("; ") ?? "";
  const minimo = h("input", { type: "number", step: "any", id: "ed-min" });
  minimo.value = req.restricao?.minimo?.toString() ?? "";
  const maximo = h("input", { type: "number", step: "any", id: "ed-max" });
  maximo.value = req.restricao?.maximo?.toString() ?? "";

  const verificacao = h(
    "select",
    { id: "ed-verif" },
    Object.entries(TIPO_VERIFICACAO).map(([v, t]) => h("option", { value: v }, t)),
  );
  verificacao.value = verificacaoDe(req);
  const ajuda = h("small", { class: "texto-suave" });
  const item = h(
    "select",
    { id: "ed-item" },
    h("option", { value: "" }, "Sem classificação"),
    Object.entries(ITEM_CHECAGEM).map(([sigla, nome]) => h("option", { value: sigla }, `${sigla} · ${nome}`)),
  );
  item.value = req.item_checagem ?? "";
  const ambientes = h("input", {
    type: "text",
    id: "ed-ambientes",
    list: "lista-ambientes",
    placeholder: "Vazio = todo o tópico",
  });
  ambientes.value = req.ambientes.join("; ");
  const motivo = h("input", { type: "text", id: "ed-motivo", placeholder: "Por que não dá para verificar no modelo?" });
  motivo.value = texto(req.motivo_nao_verificavel);

  const caixasMarcos = marcos.map((m) => {
    const cb = h("input", { type: "checkbox", id: `ed-marco-${m.id}`, value: m.id });
    cb.checked = req.marcos.includes(m.id);
    return cb;
  });
  const linhaMarcos = marcos.length
    ? h(
        "fieldset",
        { class: "campo marcos-edicao" },
        h("legend", null, "Marcos de entrega (nenhum marcado = todos)"),
        marcos.map((m, i) => h("label", { class: "check-inline", for: caixasMarcos[i].id }, caixasMarcos[i], m.nome)),
      )
    : null;
  const linhaValores = h("div", { class: "campo" }, h("label", { for: valores.id }, "Valores"), valores);
  const linhaIntervalo = h(
    "div",
    { class: "grade-2" },
    h("div", { class: "campo" }, h("label", { for: minimo.id }, "Mínimo"), minimo),
    h("div", { class: "campo" }, h("label", { for: maximo.id }, "Máximo"), maximo),
  );
  const ajustarRestricao = () => {
    const tipo = tipoRestricao.value;
    linhaValores.hidden = tipo === "" || tipo === "intervalo";
    linhaIntervalo.hidden = tipo !== "intervalo";
  };
  tipoRestricao.addEventListener("change", ajustarRestricao);
  ajustarRestricao();
  const entraNoIds = () => verificacaoEntraNoIds(verificacao.value as TipoVerificacao);
  const ajustarMotivo = () => {
    motivo.disabled = entraNoIds();
    ajuda.textContent = DESCRICAO_VERIFICACAO[verificacao.value as TipoVerificacao];
  };
  verificacao.addEventListener("change", ajustarMotivo);
  ajustarMotivo();

  const mensagem = h("div", null);
  const campo = (rotuloTexto: string, el: HTMLElement) =>
    h("div", { class: "campo" }, h("label", { for: el.id }, rotuloTexto), el);

  const formulario = h(
    "form",
    { class: "form-edicao", onsubmit: (ev: Event) => ev.preventDefault() },
    h("blockquote", { class: "trecho" }, req.evidencia.trecho, h("cite", null, citacao(req.evidencia))),
    campo("Descrição", descricao),
    h("div", { class: "grade-2" }, campo("Ambientes (separados por ;)", ambientes), campo("Item de checagem", item)),
    h("div", { class: "grade-2" }, campo("Classe IFC", ifcClass), campo("PredefinedType", predefined)),
    h("div", { class: "grade-2" }, campo("Faceta IDS", faceta), campo("Cardinalidade", cardinalidade)),
    h("div", { class: "grade-3" }, campo("Pset / sistema", pset), campo("Propriedade / atributo", propriedade), campo("Tipo de dado", tipoDado)),
    campo("Restrição de valor", tipoRestricao),
    linhaValores,
    linhaIntervalo,
    h("div", { class: "campo" }, h("label", { for: verificacao.id }, "Tipo de verificação"), verificacao, ajuda),
    campo("Motivo (se fica fora do IDS)", motivo),
    linhaMarcos,
    mensagem,
  );

  const montarRestricao = (): Restricao | null => {
    const tipo = tipoRestricao.value as TipoRestricao | "";
    if (!tipo) return null;
    if (tipo === "intervalo") {
      const min = minimo.value === "" ? null : Number(minimo.value);
      const max = maximo.value === "" ? null : Number(maximo.value);
      return { tipo, valores: [], minimo: min, maximo: max };
    }
    const lista = valores.value
      .split(";")
      .map((v) => v.trim())
      .filter(Boolean);
    return { tipo, valores: lista, minimo: null, maximo: null };
  };

  const salvarBotao = h("button", { type: "button", class: "btn btn-primario" }, "Salvar e aprovar como editado");
  const cancelar = h("button", { type: "button", class: "btn btn-fantasma" }, "Cancelar");
  const modal = abrirModal(`Editar ${req.id}`, formulario, [cancelar, salvarBotao]);
  cancelar.addEventListener("click", () => modal.fechar());
  salvarBotao.addEventListener("click", async () => {
    limpar(mensagem);
    const restricao = montarRestricao();
    if (restricao?.tipo === "intervalo" && restricao.minimo === null && restricao.maximo === null) {
      mensagem.append(erro("Informe mínimo, máximo ou ambos para o intervalo."));
      return;
    }
    if (restricao && restricao.tipo !== "intervalo" && !restricao.valores.length) {
      mensagem.append(erro("Informe pelo menos um valor para a restrição."));
      return;
    }
    const campos: CamposEdicao = {
      descricao: descricao.value.trim(),
      ifc_class: nulo(ifcClass.value),
      predefined_type: nulo(predefined.value),
      faceta: (faceta.value || null) as Faceta | null,
      pset: nulo(pset.value),
      propriedade: nulo(propriedade.value),
      tipo_dado: nulo(tipoDado.value),
      restricao,
      cardinalidade: cardinalidade.value as Cardinalidade,
      verificavel_por_ids: entraNoIds(),
      motivo_nao_verificavel: entraNoIds() ? null : nulo(motivo.value),
      marcos: caixasMarcos.filter((cb) => cb.checked).map((cb) => cb.value),
      ambientes: ambientes.value
        .split(";")
        .map((a) => a.trim())
        .filter(Boolean),
      item_checagem: (item.value || null) as ItemChecagem | null,
      verificacao: verificacao.value as TipoVerificacao,
    };
    salvarBotao.disabled = true;
    try {
      await salvar(campos);
      modal.fechar();
    } catch (e) {
      mensagem.append(erro(mensagemErro(e)));
      salvarBotao.disabled = false;
    }
  });
}

function blocoLicoes(projeto: ProjetoResumo): HTMLElement | null {
  if (!projeto.licoes.length) return null;
  return h(
    "details",
    { class: "cartao detalhes-cartao" },
    h(
      "summary",
      null,
      h("strong", null, `Lições aprendidas (${projeto.licoes.length})`),
      " · viram requisitos propostos quando dá para verificar no modelo e são procuradas no edital na verificação",
    ),
    h(
      "ul",
      { class: "lista-licoes" },
      projeto.licoes.map((l) =>
        h(
          "li",
          null,
          badge(l.id, "licao"),
          " ",
          h("strong", null, l.titulo),
          h("div", { class: "texto-suave" }, l.regra),
          h("small", { class: "texto-suave" }, `${l.documento}, p. ${l.evidencia.pagina} · lida por ${l.extraida_por === "llm" ? "IA (citação conferida)" : "regras"}`),
        ),
      ),
    ),
    h(
      "p",
      { class: "texto-suave" },
      "Salvaguarda: as lições só acrescentam verificações. Elas nunca removem nem rebaixam apontamentos.",
    ),
  );
}

function editorMarcos(projeto: ProjetoResumo, aoSalvar: (marcos: MarcoEntrega[]) => Promise<void>): HTMLElement {
  const linhas: { id: string | null; input: HTMLInputElement }[] = projeto.marcos.map((m) => {
    const input = h("input", { type: "text", value: m.nome, "aria-label": `Nome do marco ${m.id}`, maxlength: "80" });
    return { id: m.id, input };
  });
  const lista = h("div", { class: "marcos-lista" });
  const mensagem = h("div", null);
  const desenhar = () => {
    limpar(lista);
    linhas.forEach((linha, indice) => {
      lista.append(
        h(
          "div",
          { class: "marco-linha" },
          h("span", { class: "texto-suave" }, linha.id ?? "novo"),
          linha.input,
          botao("Remover", () => {
            linhas.splice(indice, 1);
            desenhar();
          }, "fantasma"),
        ),
      );
    });
  };
  desenhar();
  const salvar = async () => {
    limpar(mensagem);
    const marcos = linhas
      .map((l) => ({ id: l.id, nome: l.input.value.trim() }))
      .filter((m) => m.nome);
    try {
      const salvos = await api.definirMarcos(projeto.id, marcos);
      toast("Marcos de entrega salvos.", "sucesso");
      await aoSalvar(salvos);
    } catch (e) {
      mensagem.append(erro(mensagemErro(e)));
    }
  };
  return h(
    "details",
    { class: "cartao detalhes-cartao" },
    h(
      "summary",
      null,
      h("strong", null, `Marcos de entrega (${projeto.marcos.length})`),
      " · o IDS pode cobrir o contrato inteiro ou um marco",
    ),
    h(
      "p",
      { class: "texto-suave" },
      "Os marcos citados no edital foram detectados automaticamente. Ajuste a lista e, ao editar um requisito, marque em quais entregas ele vale.",
    ),
    lista,
    h(
      "div",
      { class: "acoes" },
      botao("Adicionar marco", () => {
        linhas.push({ id: null, input: h("input", { type: "text", placeholder: "Ex.: Projeto executivo", maxlength: "80" }) });
        desenhar();
      }, "secundario"),
      botao("Salvar marcos", () => void salvar(), "primario"),
    ),
    mensagem,
  );
}
