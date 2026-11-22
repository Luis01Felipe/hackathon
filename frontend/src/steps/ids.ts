// Passo 4 — Geração do IDS a partir do EIR aprovado (código determinístico, não LLM).
import { api, urls } from "../api";
import type { Ctx } from "../state";
import { badge, botao, carregando, erro, h, limpar, linkDownload, mensagemErro, num, vazio } from "../ui";
import { metrica } from "./upload";

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
        "Cada especificação leva o ID do requisito, e o arquivo é recarregado no ifctester como teste de integridade.",
      ),
    ),
  );
  const projeto = estado.projeto;
  const eir = estado.eir;
  if (!projeto || !eir) {
    secao.append(vazio("Gere e revise o EIR no passo 3."));
    return secao;
  }
  const paraIds = eir.requisitos.filter(
    (r) => (r.status === "aprovado" || r.status === "editado") && r.verificavel_por_ids,
  );
  const naoVerificaveis = eir.requisitos.filter(
    (r) => (r.status === "aprovado" || r.status === "editado") && !r.verificavel_por_ids,
  );
  const resultado = h("div", null);
  const status = h("div", { class: "status-acao" });

  const gerar = async () => {
    limpar(status);
    status.append(carregando("Gerando o IDS e validando contra o XSD oficial…"));
    try {
      estado.ids = await api.gerarIds(projeto.id);
      ctx.atualizar();
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
          metrica("Especificações", num(ids.especificacoes)),
          metrica("Requisitos incluídos", num(ids.requisitos_incluidos.length)),
        ),
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
          linkDownload("Baixar IDS (.ids)", ids.url || urls.idsXml(projeto.id)),
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
        metrica("Aprovados e verificáveis", num(paraIds.length)),
        metrica("Aprovados não verificáveis (manual)", num(naoVerificaveis.length)),
        metrica("Schema do modelo", projeto.schema_ifc),
      ),
      paraIds.length
        ? h(
            "ul",
            { class: "lista-compacta" },
            paraIds.map((r) => h("li", null, h("strong", null, r.id), " · ", r.descricao)),
          )
        : h("div", { class: "alerta alerta-aviso" }, "Nenhum requisito aprovado e verificável. Volte ao EIR."),
      h(
        "div",
        { class: "acoes" },
        botao("← Revisão do EIR", () => ctx.irPara(3), "fantasma"),
        h("span", { class: "espaco" }),
        !estado.ids
          ? h(
              "button",
              { type: "button", class: "btn btn-primario", disabled: paraIds.length === 0, onclick: () => void gerar() },
              "Gerar IDS",
            )
          : null,
      ),
      status,
    ),
    resultado,
  );
  return secao;
}
