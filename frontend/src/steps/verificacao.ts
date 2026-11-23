// Passo 5 — Execução das análises A, B e C (assíncrona, com polling de 1 s).
import { api } from "../api";
import { barraFiltros, campoBusca, contador, contem, selectFiltro } from "../filtros";
import { ETAPA_VERIFICACAO, STATUS_ANALISE, rotulo } from "../labels";
import type { Ctx } from "../state";
import type { StatusAnalise, Verificacao } from "../types";
import { append, avisos, badge, botao, carregando, erro, h, limpar, mensagemErro, toast, vazio } from "../ui";

let timer: number | null = null;
let inicioLocal = 0;
/** Busca e filtro das análises; ficam fora do painel, que é redesenhado a cada segundo. */
const filtros = { busca: "", status: "" };

export function pararPolling(): void {
  if (timer !== null) window.clearTimeout(timer);
  timer = null;
}

const VARIANTE_ANALISE: Record<string, string> = {
  pendente: "neutro",
  executando: "info",
  concluida: "sucesso",
  falhou: "alta",
  ignorada: "media",
};

const FINAIS: StatusAnalise[] = ["concluida", "falhou", "ignorada"];

export function renderVerificacao(ctx: Ctx): HTMLElement {
  const { estado } = ctx;
  const secao = h(
    "section",
    { class: "passo-conteudo" },
    h(
      "div",
      { class: "cabecalho-passo" },
      h("h2", null, "5. Verifique o modelo e o edital"),
      h(
        "p",
        null,
        "Três análises independentes: conformidade do IFC contra o IDS (A), qualidade do edital (B) e cobertura do edital sobre o modelo (C). ",
        "A falha de uma não impede as outras.",
      ),
    ),
  );
  const projeto = estado.projeto;
  if (!projeto) {
    secao.append(vazio("Envie os documentos no passo 1."));
    return secao;
  }

  const painel = h("div", { class: "cartao" });
  const status = h("div", { class: "status-acao" });
  const contagem = contador();
  const redesenhar = () => desenhar(estado.verificacao);
  const barra = barraFiltros(
    campoBusca("Buscar análise", filtros.busca, (termo) => {
      filtros.busca = termo;
      redesenhar();
    }),
    selectFiltro(
      "Status da análise",
      [["", "Todos os status"], ...Object.entries(STATUS_ANALISE)],
      filtros.status,
      (valor) => {
        filtros.status = valor;
        redesenhar();
      },
    ),
    h("span", { class: "espaco" }),
    contagem.el,
  );
  secao.append(barra, painel, status);

  const iniciar = async () => {
    pararPolling();
    limpar(status);
    status.append(carregando("Disparando as análises…"));
    try {
      estado.relatorio = null;
      estado.verificacao = await api.iniciarVerificacao(projeto.id);
      inicioLocal = performance.now();
      limpar(status);
      desenhar(estado.verificacao);
      agendar();
    } catch (e) {
      limpar(status);
      status.append(erro(mensagemErro(e)));
    }
  };

  const agendar = () => {
    pararPolling();
    timer = window.setTimeout(() => void consultar(), 1000);
  };

  const consultar = async () => {
    const atual = estado.verificacao;
    if (!atual) return;
    try {
      const v = await api.verificacao(atual.id);
      estado.verificacao = v;
      desenhar(v);
      if (v.status === "concluida") {
        pararPolling();
        estado.relatorio = await api.relatorio(v.id);
        toast("Verificação concluída.", "sucesso");
        ctx.irPara(6);
        return;
      }
      if (v.status === "falhou") {
        pararPolling();
        return;
      }
      agendar();
    } catch (e) {
      limpar(status);
      status.append(erro(`Falha ao consultar o status: ${mensagemErro(e)}`));
      agendar();
    }
  };

  const desenhar = (v: Verificacao | null) => {
    limpar(painel);
    barra.hidden = !v;
    if (!v) {
      painel.append(
        h(
          "div",
          { class: "inicio-verificacao" },
          h("p", null, estado.ids ? "IDS pronto. Inicie a verificação." : "Ainda não há IDS: a análise A será ignorada."),
          botao("Iniciar verificação", () => void iniciar(), "primario"),
          botao("← IDS", () => ctx.irPara(4), "fantasma"),
        ),
      );
      return;
    }
    const etapas = Object.keys(ETAPA_VERIFICACAO);
    const extras = Object.keys(v.progresso).filter((k) => !etapas.includes(k));
    const chaves = [...etapas.filter((k) => k in v.progresso), ...extras];
    const finalizadas = chaves.filter((k) => FINAIS.includes(v.progresso[k])).length;
    const visiveis = chaves.filter((chave) => {
      const info = ETAPA_VERIFICACAO[chave] ?? { titulo: chave, descricao: "" };
      if (filtros.status && v.progresso[chave] !== filtros.status) return false;
      return contem(filtros.busca, info.titulo, info.descricao, rotulo(STATUS_ANALISE, v.progresso[chave]));
    });
    contagem.definir(visiveis.length, chaves.length);
    const fracao = chaves.length ? finalizadas / chaves.length : 0;
    const segundos = inicioLocal ? (performance.now() - inicioLocal) / 1000 : null;

    append(painel, [
      h(
        "div",
        { class: "cartao-titulo" },
        h("h3", null, "Progresso"),
        badge(rotulo(STATUS_ANALISE, v.status === "concluida" ? "concluida" : v.status), VARIANTE_ANALISE[v.status] ?? "neutro"),
      ),
      h(
        "div",
        { class: "barra-progresso", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(Math.round(fracao * 100)) },
        h("div", { class: "barra-preenchimento", style: `width:${Math.round(fracao * 100)}%` }),
      ),
      h(
        "ul",
        { class: "lista-analises" },
        visiveis.length ? null : h("li", { class: "texto-suave" }, "Nenhuma análise com esses filtros."),
        visiveis.map((chave) => {
          const info = ETAPA_VERIFICACAO[chave] ?? { titulo: chave, descricao: "" };
          const st = v.progresso[chave];
          return h(
            "li",
            { class: `analise analise-${st}` },
            h("span", { class: "analise-icone", "aria-hidden": "true" }, icone(st)),
            h("span", { class: "analise-texto" }, h("strong", null, info.titulo), h("small", null, info.descricao)),
            badge(rotulo(STATUS_ANALISE, st), VARIANTE_ANALISE[st] ?? "neutro"),
          );
        }),
      ),
      segundos !== null
        ? h("p", { class: "texto-suave" }, `Tempo decorrido: ${segundos.toFixed(1).replace(".", ",")} s`)
        : null,
      v.erro ? erro(v.erro) : null,
      avisos(v.avisos),
      v.status === "falhou"
        ? h("div", { class: "acoes" }, botao("Tentar novamente", () => void iniciar(), "primario"))
        : null,
      v.status === "concluida" && !estado.relatorio
        ? h(
            "div",
            { class: "acoes" },
            botao(
              "Abrir resultados →",
              async () => {
                try {
                  estado.relatorio = await api.relatorio(v.id);
                  ctx.irPara(6);
                } catch (e) {
                  toast(mensagemErro(e), "erro");
                }
              },
              "primario",
            ),
          )
        : null,
      v.status === "concluida" && estado.relatorio
        ? h(
            "div",
            { class: "acoes" },
            botao("Nova verificação", () => void iniciar(), "fantasma"),
            botao("Ver resultados →", () => ctx.irPara(6), "primario"),
          )
        : null,
    ]);
  };

  desenhar(estado.verificacao);
  if (estado.verificacao && !["concluida", "falhou"].includes(estado.verificacao.status)) {
    agendar();
  }
  return secao;
}

function icone(status: StatusAnalise): string {
  switch (status) {
    case "concluida":
      return "✓";
    case "falhou":
      return "✕";
    case "executando":
      return "…";
    case "ignorada":
      return "–";
    default:
      return "○";
  }
}
