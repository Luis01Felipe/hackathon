// Passo 1 — Upload do edital (PDF), do modelo (IFC, opcional) e das lições aprendidas (TXT ou PDF).
import { api } from "../api";
import type { Ctx } from "../state";
import type { ProjetoResumo, VersaoIfc } from "../types";
import { avisos, badge, botao, carregando, erro, h, limpar, mensagemErro, num } from "../ui";

export const POSICIONAMENTO =
  "O EditalCheck transforma as exigências do edital, escritas em linguagem natural, num contrato de dados " +
  "operacional: os requisitos de informação (RI) e o IDS. Depois, verifica o modelo IFC contra esse contrato " +
  "e o edital contra boas práticas, para que contratante e contratado cheguem a um consenso antes da obra.";

const EXTENSOES_LICOES = [".txt", ".md", ".pdf"];

export function renderUpload(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  const secao = h("section", { class: "passo-conteudo" });
  secao.append(
    h(
      "div",
      { class: "cabecalho-passo" },
      h("h2", null, "1. Envie o edital, o modelo e as lições aprendidas"),
      h("p", { class: "posicionamento" }, POSICIONAMENTO),
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
  const inputLicoes = h("input", {
    type: "file",
    accept: ".txt,.md,.pdf,text/plain,application/pdf",
    id: "arquivo-licoes",
    multiple: true,
  });
  const nomePdf = h("span", { class: "arquivo-nome" }, "Nenhum arquivo escolhido");
  const nomeIfc = h("span", { class: "arquivo-nome" }, "Opcional: sem IFC, só o edital é revisado");
  const nomeLicoes = h("span", { class: "arquivo-nome" }, "Opcional");
  const versoes = estado.config?.versoes_ifc ?? ["IFC2X3", "IFC4", "IFC4X3_ADD2"];
  const selectVersao = h(
    "select",
    { id: "versao-sem-modelo", "aria-label": "Versão IFC esperada" },
    h("option", { value: "" }, "Versão citada no edital (ou IFC4)"),
    versoes.map((v) => h("option", { value: v }, v)),
  );
  const linhaVersao = h(
    "label",
    { class: "campo-inline", for: selectVersao.id },
    "Sem modelo, valide os requisitos contra o schema: ",
    selectVersao,
  );

  const listaLicoes = (): File[] => [...(inputLicoes.files ?? [])];

  const validar = (): string | null => {
    const pdf = inputPdf.files?.[0];
    const ifc = inputIfc.files?.[0];
    if (!pdf) return "Escolha o edital (PDF).";
    if (!pdf.name.toLowerCase().endsWith(".pdf")) return "O edital precisa ser um arquivo .pdf.";
    if (ifc && !ifc.name.toLowerCase().endsWith(".ifc")) return "O modelo precisa ser um arquivo .ifc.";
    const invalida = listaLicoes().find((f) => !EXTENSOES_LICOES.some((e) => f.name.toLowerCase().endsWith(e)));
    if (invalida) return `Lições aprendidas: envie .txt ou .pdf (${invalida.name} não é aceito).`;
    const limite = limiteMb * 1024 * 1024;
    if ([pdf, ifc, ...listaLicoes()].some((f) => f && f.size > limite)) return `Cada arquivo deve ter até ${limiteMb} MB.`;
    return null;
  };

  const enviar = h("button", { type: "button", class: "btn btn-primario", disabled: true }, "Enviar e analisar");
  const atualizarBotao = () => {
    nomePdf.textContent = inputPdf.files?.[0]?.name ?? "Nenhum arquivo escolhido";
    nomeIfc.textContent = inputIfc.files?.[0]?.name ?? "Opcional: sem IFC, só o edital é revisado";
    const licoes = listaLicoes();
    nomeLicoes.textContent = licoes.length ? licoes.map((f) => f.name).join(", ") : "Opcional";
    linhaVersao.hidden = Boolean(inputIfc.files?.[0]);
    const problema = validar();
    enviar.disabled = problema !== null;
    enviar.title = problema ?? "";
  };
  inputPdf.addEventListener("change", atualizarBotao);
  inputIfc.addEventListener("change", atualizarBotao);
  inputLicoes.addEventListener("change", atualizarBotao);

  const executar = async (acao: () => Promise<ProjetoResumo>, texto: string, ifcLocal: File | null) => {
    limpar(status);
    status.append(carregando(texto));
    enviar.disabled = true;
    try {
      estado.projeto = await acao();
      estado.ifcLocal = ifcLocal;
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
    const ifc = inputIfc.files?.[0] ?? null;
    void executar(
      () =>
        api.criarProjeto(inputPdf.files![0], ifc, listaLicoes(), (selectVersao.value || null) as VersaoIfc | null),
      "Lendo o edital por página, segmentando tópicos, lendo as lições e resumindo o modelo IFC…",
      ifc,
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

  linhaVersao.hidden = false;
  const cartao = h(
    "div",
    { class: "cartao" },
    h(
      "div",
      { class: "grade-3" },
      campo("Edital (PDF)", "PDF com texto selecionável. Escaneados não são aceitos.", inputPdf, nomePdf, "PDF"),
      campo("Modelo (IFC)", "IFC2X3, IFC4 ou IFC4X3. O schema é detectado automaticamente.", inputIfc, nomeIfc, "IFC"),
      campo(
        "Lições aprendidas",
        "TXT ou PDF com regras de obras anteriores (ciclo PDCA). Elas só acrescentam verificações.",
        inputLicoes,
        nomeLicoes,
        "PDCA",
      ),
    ),
    linhaVersao,
    h(
      "div",
      { class: "acoes" },
      enviar,
      estado.config?.demo_disponivel !== false
        ? botao(
            estado.config?.demo_com_licoes ? "Usar dados de exemplo (com lições)" : "Usar dados de exemplo",
            () => void executar(() => api.criarProjetoDemo(true), "Carregando o edital, o modelo e as lições de exemplo…", null),
            "secundario",
          )
        : null,
      h("small", { class: "texto-suave" }, `Limite de ${limiteMb} MB por arquivo.`),
    ),
    status,
  );
  secao.append(cartao, avisoPrivacidade(ctx));
  if (!estado.config) {
    secao.append(erro("Não foi possível falar com a API do EditalCheck. Verifique se o backend está rodando."));
  }
  return secao;
}

function avisoPrivacidade(ctx: Ctx): HTMLElement {
  const config = ctx.estado.config;
  const efemero = config?.modo_dados === "efemero";
  return h(
    "div",
    { class: "alerta alerta-info" },
    h("strong", null, "Seus dados. "),
    efemero
      ? `Os arquivos ficam só na memória do servidor e são apagados quando você clica em "Encerrar e apagar dados" ou após ${config?.ttl_min ?? 120} minutos sem uso. Nada é gravado em disco. `
      : "Modo de desenvolvimento: os arquivos ficam gravados na pasta de dados do servidor. ",
    config?.aviso_ia ?? "IA desligada: a análise usa só regras determinísticas, sem enviar dados a terceiros.",
    " Não envie dados pessoais nem documentos sigilosos de clientes.",
  );
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
  const licoes = p.licoes.length
    ? h(
        "details",
        { class: "detalhes", open: true },
        h("summary", null, `Lições aprendidas (${p.licoes.length}) · ${p.documentos_licoes.join(", ")}`),
        h(
          "ul",
          { class: "lista-licoes" },
          p.licoes.map((l) =>
            h(
              "li",
              null,
              badge(l.id, "licao"),
              " ",
              h("strong", null, l.titulo),
              l.termos_elemento.length ? h("small", { class: "texto-suave" }, ` · afeta: ${l.termos_elemento.join(", ")}`) : null,
            ),
          ),
        ),
      )
    : null;
  return h(
    "div",
    { class: "cartao" },
    h(
      "div",
      { class: "cartao-titulo" },
      h("h3", null, "Documentos recebidos"),
      p.sem_modelo ? badge("Revisão do edital (sem IFC)", "media") : null,
      badge("Projeto " + p.id, "neutro"),
    ),
    h(
      "dl",
      { class: "metricas" },
      metrica("Edital", p.edital_arquivo),
      metrica("Páginas com texto", num(p.paginas)),
      metrica("Tópicos encontrados", num(p.topicos_total)),
      metrica("Marcos de entrega", p.marcos.length ? p.marcos.map((m) => m.nome).join(", ") : "nenhum citado"),
      metrica("Modelo", p.sem_modelo ? "—" : p.modelo_arquivo),
      metrica(p.sem_modelo ? "Schema esperado" : "Schema IFC", p.schema_ifc),
      p.sem_modelo ? null : metrica("Elementos", num(p.total_elementos)),
      p.sem_modelo ? null : metrica("Classes especificáveis", num(especificaveis.length)),
      metrica("Lições aprendidas", num(p.licoes.length)),
    ),
    avisos(p.avisos),
    licoes,
    p.sem_modelo
      ? null
      : h("details", { class: "detalhes" }, h("summary", null, `Classes do modelo (${p.classes.length})`), tabela),
    h("div", { class: "acoes" }, botao("Continuar para os tópicos →", () => ctx.irPara(2), "primario")),
  );
}

export function metrica(rotulo: string, valor: string): HTMLElement {
  return h("div", { class: "metrica" }, h("dt", null, rotulo), h("dd", null, valor));
}
