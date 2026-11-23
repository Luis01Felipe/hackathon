// Passo 3 — Revisão humana dos requisitos de informação (RI): aceitar, editar ou rejeitar
// cada requisito, cadastrar marcos de entrega e conferir as lições aprendidas.
import { api, urls } from "../api";
import {
  CARDINALIDADE,
  FACETA,
  ORIGEM,
  STATUS_REQUISITO,
  TIPO_RESTRICAO,
  descreverRestricao,
  mapeamento,
  rotulo,
} from "../labels";
import type { Ctx } from "../state";
import type {
  AcaoRequisito,
  Cardinalidade,
  CamposEdicao,
  Evidencia,
  Faceta,
  MarcoEntrega,
  ProjetoResumo,
  Requisito,
  Restricao,
  TipoRestricao,
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
  status: string;
  somenteNaoVerificaveis: boolean;
}

const filtros: FiltrosEir = { status: "todos", somenteNaoVerificaveis: false };

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

export function renderEir(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  const secao = h(
    "section",
    { class: "passo-conteudo" },
    h(
      "div",
      { class: "cabecalho-passo" },
      h("h2", null, "3. Revise os requisitos de informação (RI)"),
      h(
        "p",
        null,
        "Os RI são o contrato de dados da contratação: o que o modelo deve conter em cada entrega. ",
        "Cada requisito mostra o trecho original do edital (ou da lição aprendida), conferido literalmente. ",
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
      .ri(projeto.id)
      .then((eir) => {
        estado.eir = eir;
        ctx.atualizar();
      })
      .catch((e) => {
        secao.lastChild?.remove();
        secao.append(erro(mensagemErro(e)), botao("← Voltar aos tópicos", () => ctx.irPara(2), "fantasma"));
      });
    return secao;
  }

  const eir = estado.eir;
  const resumo = h("div", { class: "resumo-eir" });
  const corpoTabela = h("tbody", null);
  const status = h("div", { class: "status-acao" });

  const atualizarResumo = () => {
    limpar(resumo);
    const reqs = eir.requisitos;
    const contar = (f: (r: Requisito) => boolean) => reqs.filter(f).length;
    const aprovados = contar((r) => r.status === "aprovado" || r.status === "editado");
    const paraIds = contar((r) => (r.status === "aprovado" || r.status === "editado") && r.verificavel_por_ids);
    resumo.append(
      chip("Requisitos", reqs.length),
      chip("Propostos", contar((r) => r.status === "proposto")),
      chip("Aprovados", aprovados, "sucesso"),
      chip("Rejeitados", contar((r) => r.status === "rejeitado"), "alta"),
      chip("Não verificáveis por IDS", contar((r) => !r.verificavel_por_ids), "media"),
      chip("De lições aprendidas", contar((r) => r.gerado_por === "licao"), "licao"),
      chip("Entram no IDS", paraIds, "info"),
    );
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
      desenharLinhas();
      atualizarResumo();
    } catch (e) {
      toast(mensagemErro(e), "erro");
    }
  };

  const desenharLinhas = () => {
    limpar(corpoTabela);
    const visiveis = eir.requisitos.filter((r) => {
      if (filtros.somenteNaoVerificaveis && r.verificavel_por_ids) return false;
      if (filtros.status !== "todos" && r.status !== filtros.status) return false;
      return true;
    });
    if (!visiveis.length) {
      corpoTabela.append(h("tr", null, h("td", { colspan: "6" }, vazio("Nenhum requisito com esses filtros."))));
      return;
    }
    for (const req of visiveis) corpoTabela.append(linhaRequisito(req, agir, (r) => editar(r), marcosPorId()));
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
        estado.eir = await api.ri(projeto.id);
        ctx.atualizar();
      }),
    );
  };
  desenharMarcos();

  const selectStatus = h(
    "select",
    { "aria-label": "Filtrar por status" },
    h("option", { value: "todos" }, "Todos os status"),
    Object.entries(STATUS_REQUISITO).map(([valor, texto]) => h("option", { value: valor }, texto)),
  );
  selectStatus.value = filtros.status;
  selectStatus.addEventListener("change", () => {
    filtros.status = selectStatus.value;
    desenharLinhas();
  });
  const cbNaoVerificaveis = h("input", { type: "checkbox", id: "filtro-nao-verificaveis" });
  cbNaoVerificaveis.checked = filtros.somenteNaoVerificaveis;
  cbNaoVerificaveis.addEventListener("change", () => {
    filtros.somenteNaoVerificaveis = cbNaoVerificaveis.checked;
    desenharLinhas();
  });

  const aprovarTodos = async () => {
    limpar(status);
    status.append(carregando("Aprovando requisitos verificáveis…"));
    try {
      const novo = await api.aprovarTodos(projeto.id, true);
      estado.eir = novo;
      estado.ids = null;
      toast("Requisitos verificáveis aprovados.", "sucesso");
      ctx.atualizar();
    } catch (e) {
      limpar(status);
      status.append(erro(mensagemErro(e)));
    }
  };

  const podeGerarIds = () =>
    eir.requisitos.some((r) => (r.status === "aprovado" || r.status === "editado") && r.verificavel_por_ids);

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
    h(
      "div",
      { class: "barra-ferramentas" },
      selectStatus,
      h("label", { class: "check-inline", for: cbNaoVerificaveis.id }, cbNaoVerificaveis, "Somente não verificáveis"),
      h("span", { class: "espaco" }),
      botao("Aceitar todos os verificáveis", () => void aprovarTodos(), "sucesso"),
      linkDownload("Baixar RI (.xlsx)", urls.riXlsx(projeto.id)),
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
            h("th", null, "Mapeamento IFC"),
            h("th", null, "Vocabulário"),
            h("th", null, "Verificável por IDS"),
            h("th", null, "Ações"),
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
  atualizarResumo();
  desenharLinhas();
  return secao;
}

function chip(rotuloTexto: string, valor: number, variante = "neutro"): HTMLElement {
  return h("div", { class: `chip chip-${variante}` }, h("strong", null, String(valor)), h("span", null, rotuloTexto));
}

export function citacao(ev: Evidencia, clausula?: string | null): string {
  const local = [`p. ${ev.pagina}`, clausula ? `item ${clausula}` : null].filter(Boolean).join(" · ");
  return `${ev.fonte === "licoes" ? "Lições aprendidas" : "Edital"}, ${local}`;
}

function linhaRequisito(
  req: Requisito,
  agir: (req: Requisito, acao: AcaoRequisito) => Promise<void>,
  editar: (req: Requisito) => void,
  marcos: Map<string, string>,
): HTMLElement {
  const aprovado = req.status === "aprovado" || req.status === "editado";
  const restricao = descreverRestricao(req.restricao);
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
      { class: "col-req" },
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
      { class: "col-map" },
      h("code", { class: "mapa" }, mapeamento(req)),
      h(
        "div",
        { class: "mapa-detalhes" },
        req.faceta ? h("span", null, rotulo(FACETA, req.faceta)) : null,
        req.tipo_dado ? h("span", null, req.tipo_dado) : null,
        restricao ? h("span", null, restricao) : null,
        h("span", null, rotulo(CARDINALIDADE, req.cardinalidade)),
      ),
    ),
    h(
      "td",
      { class: "col-voc" },
      req.origem_vocabulario
        ? badge(rotulo(ORIGEM, req.origem_vocabulario), VARIANTE_ORIGEM[req.origem_vocabulario] ?? "neutro")
        : h("span", { class: "texto-suave" }, "—"),
      req.bsdd_uri
        ? h("a", { href: req.bsdd_uri, target: "_blank", rel: "noopener", class: "link-bsdd" }, "ver no bSDD")
        : null,
    ),
    h(
      "td",
      { class: "col-verif" },
      req.verificavel_por_ids ? badge("Sim", "sucesso") : badge("Não · manual", "media"),
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

  const verificavel = h("input", { type: "checkbox", id: "ed-verif" });
  verificavel.checked = req.verificavel_por_ids;
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
  const ajustarMotivo = () => {
    motivo.disabled = verificavel.checked;
  };
  verificavel.addEventListener("change", ajustarMotivo);
  ajustarMotivo();

  const mensagem = h("div", null);
  const campo = (rotuloTexto: string, el: HTMLElement) =>
    h("div", { class: "campo" }, h("label", { for: el.id }, rotuloTexto), el);

  const formulario = h(
    "form",
    { class: "form-edicao", onsubmit: (ev: Event) => ev.preventDefault() },
    h("blockquote", { class: "trecho" }, req.evidencia.trecho, h("cite", null, citacao(req.evidencia))),
    campo("Descrição", descricao),
    h("div", { class: "grade-2" }, campo("Classe IFC", ifcClass), campo("PredefinedType", predefined)),
    h("div", { class: "grade-2" }, campo("Faceta IDS", faceta), campo("Cardinalidade", cardinalidade)),
    h("div", { class: "grade-3" }, campo("Pset / sistema", pset), campo("Propriedade / atributo", propriedade), campo("Tipo de dado", tipoDado)),
    campo("Restrição de valor", tipoRestricao),
    linhaValores,
    linhaIntervalo,
    h("label", { class: "check-inline", for: verificavel.id }, verificavel, "Verificável por IDS"),
    campo("Motivo (se não verificável)", motivo),
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
      verificavel_por_ids: verificavel.checked,
      motivo_nao_verificavel: verificavel.checked ? null : nulo(motivo.value),
      marcos: caixasMarcos.filter((cb) => cb.checked).map((cb) => cb.value),
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
