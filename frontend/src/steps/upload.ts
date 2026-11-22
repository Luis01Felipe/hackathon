// Passo 1 — Upload do edital (PDF) e do modelo (IFC).
import { api } from "../api";
import type { Ctx } from "../state";
import type { ProjetoResumo } from "../types";
import { avisos, badge, botao, carregando, erro, h, limpar, mensagemErro, num } from "../ui";

export function renderUpload(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  const secao = h("section", { class: "passo-conteudo" });
  secao.append(
    h(
      "div",
      { class: "cabecalho-passo" },
      h("h2", null, "1. Envie o edital e o modelo"),
      h(
        "p",
        null,
        "O EditalCheck lê o edital em PDF (com texto selecionável) e o modelo IFC (IFC2X3 ou IFC4). ",
        "Depois você escolhe os tópicos, revisa o EIR, gera o IDS e verifica o modelo.",
      ),
    ),
  );

  if (estado.projeto) {
    secao.append(resumoProjeto(estado.projeto, ctx));
    return secao;
  }

  const limiteMb = estado.config?.limite_upload_mb ?? 200;
  const status = h("div", { class: "status-acao" });
  const inputPdf = h("input", { type: "file", accept: ".pdf,application/pdf", id: "arquivo-edital" });
  const inputIfc = h("input", { type: "file", accept: ".ifc", id: "arquivo-modelo" });
  const nomePdf = h("span", { class: "arquivo-nome" }, "Nenhum arquivo escolhido");
  const nomeIfc = h("span", { class: "arquivo-nome" }, "Nenhum arquivo escolhido");

  const validar = (): string | null => {
    const pdf = inputPdf.files?.[0];
    const ifc = inputIfc.files?.[0];
    if (!pdf || !ifc) return "Escolha o edital (PDF) e o modelo (IFC).";
    if (!pdf.name.toLowerCase().endsWith(".pdf")) return "O edital precisa ser um arquivo .pdf.";
    if (!ifc.name.toLowerCase().endsWith(".ifc")) return "O modelo precisa ser um arquivo .ifc.";
    const limite = limiteMb * 1024 * 1024;
    if (pdf.size > limite || ifc.size > limite) return `Cada arquivo deve ter até ${limiteMb} MB.`;
    return null;
  };

  const enviar = h("button", { type: "button", class: "btn btn-primario", disabled: true }, "Enviar e analisar");
  const atualizarBotao = () => {
    nomePdf.textContent = inputPdf.files?.[0]?.name ?? "Nenhum arquivo escolhido";
    nomeIfc.textContent = inputIfc.files?.[0]?.name ?? "Nenhum arquivo escolhido";
    const problema = validar();
    enviar.disabled = problema !== null;
    enviar.title = problema ?? "";
  };
  inputPdf.addEventListener("change", atualizarBotao);
  inputIfc.addEventListener("change", atualizarBotao);

  const executar = async (acao: () => Promise<ProjetoResumo>, texto: string) => {
    limpar(status);
    status.append(carregando(texto));
    enviar.disabled = true;
    try {
      estado.projeto = await acao();
      ctx.atualizar();
    } catch (e) {
      limpar(status);
      status.append(erro(mensagemErro(e)));
      atualizarBotao();
    }
  };

  enviar.addEventListener("click", () => {
    const problema = validar();
    if (problema) {
      limpar(status);
      status.append(erro(problema));
      return;
    }
    void executar(
      () => api.criarProjeto(inputPdf.files![0], inputIfc.files![0]),
      "Lendo o edital por página, segmentando tópicos e resumindo o modelo IFC…",
    );
  });

  const campo = (rotulo: string, ajuda: string, input: HTMLInputElement, nome: HTMLElement, icone: string) =>
    h(
      "label",
      { class: "campo-arquivo", for: input.id },
      h("span", { class: "campo-icone", "aria-hidden": "true" }, icone),
      h("span", { class: "campo-texto" }, h("strong", null, rotulo), h("small", null, ajuda), nome),
      input,
    );

  const cartao = h(
    "div",
    { class: "cartao" },
    h(
      "div",
      { class: "grade-2" },
      campo("Edital (PDF)", "PDF com texto selecionável. Escaneados não são aceitos.", inputPdf, nomePdf, "PDF"),
      campo("Modelo (IFC)", "IFC2X3 ou IFC4. O schema é detectado automaticamente.", inputIfc, nomeIfc, "IFC"),
    ),
    h(
      "div",
      { class: "acoes" },
      enviar,
      estado.config?.demo_disponivel !== false
        ? botao(
            "Usar dados de exemplo",
            () => void executar(() => api.criarProjetoDemo(), "Carregando o edital e o modelo de exemplo…"),
            "secundario",
          )
        : null,
      h("small", { class: "texto-suave" }, `Limite de ${limiteMb} MB por arquivo.`),
    ),
    status,
  );
  secao.append(
    cartao,
    h(
      "div",
      { class: "alerta alerta-info" },
      h("strong", null, "Privacidade. "),
      "Use apenas editais e modelos públicos. Quando a IA está ativa, trechos do edital são enviados ao provedor de LLM configurado.",
    ),
  );
  if (!estado.config) {
    secao.append(erro("Não foi possível falar com a API do EditalCheck. Verifique se o backend está rodando."));
  }
  return secao;
}

function resumoProjeto(p: ProjetoResumo, ctx: Ctx): HTMLElement {
  const especificaveis = p.classes.filter((c) => c.especificavel);
  const tabela = h(
    "table",
    { class: "tabela compacta" },
    h("thead", null, h("tr", null, h("th", null, "Classe IFC"), h("th", { class: "num" }, "Elementos"), h("th", null, ""))),
    h(
      "tbody",
      null,
      [...p.classes]
        .sort((a, b) => b.contagem - a.contagem)
        .map((c) =>
          h(
            "tr",
            null,
            h("td", null, h("code", null, c.nome)),
            h("td", { class: "num" }, num(c.contagem)),
            h("td", null, c.especificavel ? badge("especificável", "info") : badge("fora da cobertura", "neutro")),
          ),
        ),
    ),
  );
  return h(
    "div",
    { class: "cartao" },
    h(
      "div",
      { class: "cartao-titulo" },
      h("h3", null, "Documentos recebidos"),
      badge("Projeto " + p.id, "neutro"),
    ),
    h(
      "dl",
      { class: "metricas" },
      metrica("Edital", p.edital_arquivo),
      metrica("Páginas com texto", num(p.paginas)),
      metrica("Tópicos encontrados", num(p.topicos_total)),
      metrica("Modelo", p.modelo_arquivo),
      metrica("Schema IFC", p.schema_ifc),
      metrica("Elementos", num(p.total_elementos)),
      metrica("Classes especificáveis", num(especificaveis.length)),
    ),
    avisos(p.avisos),
    h("details", { class: "detalhes" }, h("summary", null, `Classes do modelo (${p.classes.length})`), tabela),
    h("div", { class: "acoes" }, botao("Continuar para os tópicos →", () => ctx.irPara(2), "primario")),
  );
}

export function metrica(rotulo: string, valor: string): HTMLElement {
  return h("div", { class: "metrica" }, h("dt", null, rotulo), h("dd", null, valor));
}
