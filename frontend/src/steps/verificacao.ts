// Passo 5 — Execução das análises A, B e C (assíncrona, com polling de 1 s).
import { api } from "../api";
import { barraFiltros, campoBusca, contador, contem, filtrosReiniciaveis, selectFiltro } from "../filtros";
import { ETAPA_VERIFICACAO, STATUS_ANALISE, rotulo } from "../labels";
import type { Ctx } from "../state";
import type { StatusAnalise, Verificacao } from "../types";
import { append, avisos, badge, botao, carregando, erro, h, limpar, mensagemErro, toast, vazio } from "../ui";

let timer: number | null = null;
/**
 * Muda a cada parada do polling. Uma consulta que ainda estava em voo quando o usuário saiu
 * do passo (ou começou outro projeto) descarta a resposta: não reagenda nem muda de passo.
 */
let geracaoPolling = 0;
let inicioLocal = 0;
/** Busca e filtro das análises; ficam fora do painel, que é atualizado a cada segundo. */
const filtros = filtrosReiniciaveis({ busca: "", status: "" });

export function pararPolling(): void {
  geracaoPolling += 1;
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

interface ItemAnalise {
  li: HTMLLIElement;
  simbolo: HTMLSpanElement;
  selo: HTMLSpanElement;
}

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
      [["", "Status: todos"], ...Object.entries(STATUS_ANALISE)],
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
    const minha = geracaoPolling;
    limpar(status);
    status.append(carregando("Disparando as análises…"));
    try {
      estado.relatorio = null;
      estado.verificacao = await api.iniciarVerificacao(projeto.id);
      inicioLocal = performance.now();
      if (minha !== geracaoPolling) return;
      limpar(status);
      desenhar(estado.verificacao);
      agendar();
    } catch (e) {
      if (minha !== geracaoPolling) return;
      limpar(status);
      status.append(erro(mensagemErro(e)));
    }
  };

  const agendar = () => {
    pararPolling();
    const minha = geracaoPolling;
    timer = window.setTimeout(() => void consultar(minha), 1000);
  };

  const consultar = async (minha: number) => {
    const atual = estado.verificacao;
    if (!atual) return;
    const vigente = () => minha === geracaoPolling && estado.verificacao?.id === atual.id;
    try {
      const v = await api.verificacao(atual.id);
      if (!vigente()) return;
      estado.verificacao = v;
      desenhar(v);
      if (v.status === "concluida") {
        const relatorio = await api.relatorio(v.id);
        if (!vigente()) return;
        estado.relatorio = relatorio;
        toast("Verificação concluída.", "sucesso");
        ctx.irPara(6);
        return;
      }
      if (v.status === "falhou") return;
      agendar();
    } catch (e) {
      if (!vigente()) return;
      limpar(status);
      status.append(erro(`Falha ao consultar o status: ${mensagemErro(e)}`));
      agendar();
    }
  };

  // Estrutura do progresso montada uma vez: a cada consulta só mudam largura, textos e
  // classes. Recriar tudo reiniciava a animação do ícone e anulava a transição da barra.
  const seloGeral = h("span", null);
  const preenchimento = h("div", { class: "barra-preenchimento", style: "width:0%" });
  const barraProgresso = h(
    "div",
    { class: "barra-progresso", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": "0" },
    preenchimento,
  );
  const semAnalises = h("li", { class: "texto-suave" }, "Nenhuma análise com esses filtros.");
  const listaAnalises = h("ul", { class: "lista-analises" });
  const tempo = h("p", { class: "texto-suave" });
  const rodape = h("div", { class: "verificacao-rodape" });
  const itens = new Map<string, ItemAnalise>();
  let montado = false;

  const montarProgresso = () => {
    limpar(painel);
    limpar(listaAnalises);
    itens.clear();
    listaAnalises.append(semAnalises);
    painel.append(
      h("div", { class: "cartao-titulo" }, h("h3", null, "Progresso"), seloGeral),
      barraProgresso,
      listaAnalises,
      tempo,
      rodape,
    );
    montado = true;
  };

  const itemAnalise = (chave: string): ItemAnalise => {
    const existente = itens.get(chave);
    if (existente) return existente;
    const info = ETAPA_VERIFICACAO[chave] ?? { titulo: chave, descricao: "" };
    const simbolo = h("span", { class: "analise-icone", "aria-hidden": "true" });
    const selo = h("span", null);
    const li = h(
      "li",
      null,
      simbolo,
      h("span", { class: "analise-texto" }, h("strong", null, info.titulo), h("small", null, info.descricao)),
      selo,
    );
    listaAnalises.append(li);
    const novo = { li, simbolo, selo };
    itens.set(chave, novo);
    return novo;
  };

  const desenhar = (v: Verificacao | null) => {
    barra.hidden = !v;
    if (!v) {
      montado = false;
      limpar(painel);
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
    if (!montado) montarProgresso();

    const etapas = Object.keys(ETAPA_VERIFICACAO);
    const extras = Object.keys(v.progresso).filter((k) => !etapas.includes(k));
    const chaves = [...etapas.filter((k) => k in v.progresso), ...extras];
    const finalizadas = chaves.filter((k) => FINAIS.includes(v.progresso[k])).length;
    const percentual = chaves.length ? Math.round((finalizadas / chaves.length) * 100) : 0;

    limpar(seloGeral);
    seloGeral.append(badge(rotulo(STATUS_ANALISE, v.status), VARIANTE_ANALISE[v.status] ?? "neutro"));
    preenchimento.style.width = `${percentual}%`;
    barraProgresso.setAttribute("aria-valuenow", String(percentual));

    let visiveis = 0;
    for (const chave of chaves) {
      const info = ETAPA_VERIFICACAO[chave] ?? { titulo: chave, descricao: "" };
      const st = v.progresso[chave];
      const item = itemAnalise(chave);
      // Mesma classe: o navegador não reinicia a animação do ícone.
      const classe = `analise analise-${st}`;
      if (item.li.className !== classe) item.li.className = classe;
      item.simbolo.textContent = icone(st);
      limpar(item.selo);
      item.selo.append(badge(rotulo(STATUS_ANALISE, st), VARIANTE_ANALISE[st] ?? "neutro"));
      const passa =
        (!filtros.status || st === filtros.status) &&
        contem(filtros.busca, info.titulo, info.descricao, rotulo(STATUS_ANALISE, st));
      item.li.hidden = !passa;
      if (passa) visiveis += 1;
    }
    semAnalises.hidden = visiveis > 0;
    contagem.definir(visiveis, chaves.length);

    const segundos = inicioLocal ? (performance.now() - inicioLocal) / 1000 : null;
    tempo.hidden = segundos === null;
    tempo.textContent = segundos === null ? "" : `Tempo decorrido: ${segundos.toFixed(1).replace(".", ",")} s`;

    limpar(rodape);
    append(rodape, [
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
