// Passo 4 — Geração do IDS a partir dos requisitos de informação aprovados (código, não LLM).
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
import { ITEM_CHECAGEM } from "../labels";
import type { Ctx } from "../state";
import type { Requisito, VersaoIfc } from "../types";
import { badge, botao, carregando, erro, h, limpar, linkDownload, mensagemErro, num, vazio } from "../ui";
import { metrica } from "./upload";

/** Escolha de escopo e versão, mantida entre redesenhos da tela. */
const escolha: { projeto: string | null; marco: string; versao: string } = { projeto: null, marco: "", versao: "" };

/** Busca e filtros da lista de requisitos do escopo, mantidos entre redesenhos. */
const filtros = filtrosReiniciaveis({ busca: "", item: "", classe: "" });

function listaDoEscopo(requisitos: Requisito[]): HTMLElement {
  const lista = h("ul", { class: "lista-compacta" });
  const contagem = contador();
  const desenhar = () => {
    limpar(lista);
    const visiveis = requisitos.filter(
      (r) =>
        (!filtros.item || r.item_checagem === filtros.item) &&
        (!filtros.classe || r.ifc_class === filtros.classe) &&
        contem(filtros.busca, r.id, r.descricao, r.ifc_class, r.pset, r.propriedade, r.ambientes.join(" ")),
    );
    contagem.definir(visiveis.length, requisitos.length);
    if (!visiveis.length) {
      lista.append(h("li", { class: "texto-suave" }, "Nenhum requisito com esses filtros."));
      return;
    }
    for (const r of visiveis) {
      lista.append(
        h(
          "li",
          null,
          h("strong", null, r.id),
          r.item_checagem
            ? [" ", badge(r.item_checagem, `item badge-item-${r.item_checagem.toLowerCase()}`, ITEM_CHECAGEM[r.item_checagem])]
            : null,
          " · ",
          r.descricao,
        ),
      );
    }
  };
  const classes = [...new Set(requisitos.map((r) => r.ifc_class).filter((c): c is string => Boolean(c)))].sort();
  const itens = [...new Set(requisitos.map((r) => r.item_checagem).filter((i) => i !== null))].sort();
  const mudar = (chave: keyof typeof filtros) => (valor: string) => {
    filtros[chave] = valor;
    desenhar();
  };
  const busca = campoBusca("Buscar requisito por ID, texto, classe ou ambiente", filtros.busca, mudar("busca"));
  const selectItem = selectFiltro(
    "Item de checagem",
    [["", "Item: todos"], ...itens.map((i) => [i, `${i} · ${ITEM_CHECAGEM[i]}`] as [string, string])],
    filtros.item,
    mudar("item"),
  );
  const selectClasse = selectFiltro(
    "Classe IFC",
    [["", "Classe IFC: todas"], ...classes.map((c) => [c, c] as [string, string])],
    filtros.classe,
    mudar("classe"),
  );
  desenhar();
  return h(
    "div",
    null,
    barraFiltros(
      busca,
      selectItem,
      selectClasse,
      botaoLimpar(() => {
        Object.assign(filtros, { busca: "", item: "", classe: "" });
        busca.value = "";
        selectItem.value = "";
        selectClasse.value = "";
        desenhar();
      }),
      h("span", { class: "espaco" }),
      contagem.el,
    ),
    lista,
  );
}

export function renderIds(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  const secao = h(
    "section",
    { class: "passo-conteudo" },
    h(
      "div",
      { class: "cabecalho-passo" },
      h("h2", null, "4. Gere o IDS"),
      h(
        "p",
        null,
        "O IDS 1.0 é montado por código a partir dos requisitos aprovados e verificáveis. O LLM não escreve XML. ",
        "Escolha se o IDS cobre o contrato inteiro ou um marco de entrega, e em qual versão do IFC. ",
        "O arquivo é recarregado no ifctester como teste de integridade.",
      ),
    ),
  );
  const projeto = estado.projeto;
  const eir = estado.eir;
  if (!projeto || !eir) {
    secao.append(vazio("Gere e revise os requisitos de informação (IR) no passo 3."));
    return secao;
  }
  const selectMarco = h(
    "select",
    { id: "ids-marco", "aria-label": "Escopo do IDS" },
    h("option", { value: "" }, "Contrato inteiro"),
    projeto.marcos.map((m) => h("option", { value: m.id }, `Marco: ${m.nome}`)),
  );
  if (escolha.projeto !== projeto.id) {
    escolha.projeto = projeto.id;
    escolha.marco = estado.ids?.marco_id ?? projeto.ids_marco_id ?? "";
    escolha.versao = estado.ids?.versao_ifc ?? "";
  }
  selectMarco.value = escolha.marco;
  const versoes = estado.config?.versoes_ifc ?? ["IFC2X3", "IFC4", "IFC4X3_ADD2"];
  const selectVersao = h(
    "select",
    { id: "ids-versao", "aria-label": "Versão IFC do IDS" },
    h("option", { value: "" }, projeto.sem_modelo ? "Versão esperada" : `Versão do modelo (${projeto.schema_ifc})`),
    versoes.map((v) => h("option", { value: v }, v)),
  );
  selectVersao.value = escolha.versao;
  selectMarco.addEventListener("change", () => {
    escolha.marco = selectMarco.value;
    ctx.atualizar();
  });
  selectVersao.addEventListener("change", () => {
    escolha.versao = selectVersao.value;
  });
  const aprovados = eir.requisitos.filter(
    (r) => (r.status === "aprovado" || r.status === "editado") && r.verificavel_por_ids,
  );
  const doEscopo = () =>
    aprovados.filter((r) => !selectMarco.value || !r.marcos.length || r.marcos.includes(selectMarco.value));
  const paraIds = doEscopo();
  const naoVerificaveis = eir.requisitos.filter(
    (r) => (r.status === "aprovado" || r.status === "editado") && !r.verificavel_por_ids,
  );
  const resultado = h("div", null);
  const status = h("div", { class: "status-acao" });

  const gerar = async () => {
    limpar(status);
    status.append(carregando("Gerando o IDS e validando contra o XSD oficial…"));
    try {
      estado.ids = await api.gerarIds(
        projeto.id,
        selectMarco.value || null,
        (selectVersao.value || null) as VersaoIfc | null,
      );
      ctx.atualizarNoPasso(4);
    } catch (e) {
      limpar(status);
      status.append(erro(mensagemErro(e)));
    }
  };

  if (estado.ids) {
    const ids = estado.ids;
    resultado.append(
      h(
        "div",
        { class: `cartao ${ids.valido ? "cartao-ok" : "cartao-erro"}` },
        h(
          "div",
          { class: "cartao-titulo" },
          h("h3", null, "IDS gerado"),
          ids.valido
            ? badge("Integridade conferida (S6)", "sucesso", "O IDS foi recarregado no ifctester sem erro.")
            : badge("Falhou na integridade (S6)", "alta"),
        ),
        h(
          "dl",
          { class: "metricas" },
          metrica("Escopo", ids.escopo),
          metrica("Versão IFC", ids.versao_ifc),
          metrica("Especificações", num(ids.especificacoes)),
          metrica("Requisitos incluídos", num(ids.requisitos_incluidos.length)),
        ),
        ids.avisos.length
          ? h("div", { class: "alerta alerta-aviso" }, ids.avisos.map((a) => h("p", null, a)))
          : null,
        ids.requisitos_incluidos.length
          ? h("p", { class: "lista-ids" }, ids.requisitos_incluidos.map((id) => badge(id, "neutro")))
          : null,
        ids.erros.length
          ? h(
              "div",
              { class: "alerta alerta-erro" },
              h("strong", null, "Erros do IDS"),
              h("ul", null, ids.erros.map((e) => h("li", null, e))),
            )
          : null,
        h(
          "div",
          { class: "acoes" },
          linkDownload("Baixar IDS (.ids)", urls.idsXml(projeto.id)),
          botao("Gerar novamente", () => void gerar(), "fantasma"),
          h("span", { class: "espaco" }),
          ids.valido ? botao("Executar verificação →", () => ctx.irPara(5), "primario") : null,
        ),
      ),
    );
  }

  secao.append(
    h(
      "div",
      { class: "cartao" },
      h(
        "dl",
        { class: "metricas" },
        metrica("Aprovados e verificáveis no escopo", num(paraIds.length)),
        metrica("Aprovados não verificáveis (manual)", num(naoVerificaveis.length)),
        metrica(projeto.sem_modelo ? "Schema esperado" : "Schema do modelo", projeto.schema_ifc),
      ),
      h(
        "div",
        { class: "barra-ferramentas" },
        h("label", { class: "campo-inline", for: selectMarco.id }, "Escopo: ", selectMarco),
        h("label", { class: "campo-inline", for: selectVersao.id }, "Versão IFC: ", selectVersao),
      ),
      paraIds.length
        ? listaDoEscopo(paraIds)
        : h("div", { class: "alerta alerta-aviso" }, "Nenhum requisito aprovado e verificável neste escopo. Volte aos IR."),
      h(
        "div",
        { class: "acoes" },
        botao("← Requisitos (IR)", () => ctx.irPara(3), "fantasma"),
        h("span", { class: "espaco" }),
        h(
          "button",
          { type: "button", class: "btn btn-primario", disabled: paraIds.length === 0, onclick: () => void gerar() },
          estado.ids ? "Gerar de novo com este escopo" : "Gerar IDS",
        ),
      ),
      status,
    ),
    resultado,
  );
  return secao;
}
