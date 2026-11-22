// Passo 6 — Resultados: painel, visualizador 3D, apontamentos e detalhe.
import { api, urls } from "../api";
import {
  ANALISE,
  DESTINATARIO,
  ESTADO_ELEMENTO,
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
  ElementoRef,
  EstadoElemento,
  Evidencia,
  FalhaElemento,
  Relatorio,
  Requisito,
} from "../types";
import {
  append,
  avisos,
  badge,
  botao,
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

export function descartarResultados(): void {
  geracao += 1;
  viewer?.dispose();
  viewer = null;
}

const filtros = { tipo: "todos", severidade: "todas", destinatario: "todos", busca: "" };
const ORDEM_SEVERIDADE: Record<string, number> = { alta: 0, media: 1, baixa: 2 };
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
      indices.elementos.set(el.global_id, el);
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
    detalhe.append(detalheApontamento(apt, indices, relatorio, {
      focarElemento: (guid) => {
        void viewer?.focar([guid]);
        mostrarElemento(guid, false);
      },
      adicionarAoEir: () => void adicionarAoEir(apt),
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
      estado.eir = await api.eir(projetoId);
      estado.ids = null;
      toast(`${novos.length} requisito(s) sugerido(s) adicionado(s) ao EIR para revisão.`, "sucesso");
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
  const selectDestinatario = selectFiltro(
    "Destinatário",
    [["todos", "Todos os destinatários"], ["projetista", "Projetista"], ["contratante", "Contratante"]],
    filtros.destinatario,
    (v) => {
      filtros.destinatario = v;
      desenharLista();
    },
  );
  const busca = h("input", { type: "search", placeholder: "Buscar no título…", "aria-label": "Buscar apontamentos" });
  busca.value = filtros.busca;
  busca.addEventListener("input", () => {
    filtros.busca = busca.value;
    desenharLista();
  });
  const contagem = h("span", { class: "texto-suave" });

  const desenharLista = () => {
    limpar(listaApts);
    const termo = filtros.busca.trim().toLowerCase();
    const visiveis = relatorio.apontamentos
      .filter((a) => filtros.tipo === "todos" || a.tipo === filtros.tipo)
      .filter((a) => filtros.severidade === "todas" || a.severidade === filtros.severidade)
      .filter((a) => filtros.destinatario === "todos" || a.destinatario === filtros.destinatario)
      .filter((a) => !termo || a.titulo.toLowerCase().includes(termo) || a.id.toLowerCase().includes(termo))
      .sort(
        (a, b) =>
          (ORDEM_SEVERIDADE[a.severidade] ?? 9) - (ORDEM_SEVERIDADE[b.severidade] ?? 9) || a.id.localeCompare(b.id),
      );
    contagem.textContent = `${visiveis.length} de ${relatorio.apontamentos.length} apontamento(s)`;
    if (!visiveis.length) {
      listaApts.append(vazio("Nenhum apontamento com esses filtros."));
      return;
    }
    for (const apt of visiveis) listaApts.append(cartaoApontamento(apt, () => mostrarApontamento(apt)));
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

  const planoB = (motivo: string) => {
    limpar(overlay);
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
          "Use o relatório HTML ou abra o BCF numa ferramenta BIM que leia BCF. O restante da tela continua funcionando.",
        ),
        h(
          "div",
          { class: "acoes" },
          linkDownload("Relatório HTML", urls.relatorioHtml(vid)),
          linkDownload("BCF das não conformidades", urls.bcf(vid)),
        ),
      ),
    );
  };

  const iniciarViewer = async () => {
    try {
      const v = await Viewer3D.criar(canvasHost);
      if (minhaGeracao !== geracao) {
        v.dispose();
        return;
      }
      viewer = v;
      v.onPick = (escolha) => {
        if (!escolha) return;
        if (!escolha.globalId) {
          limpar(detalhe);
          detalhe.append(h("h3", null, "Elemento"), h("p", { class: "texto-suave" }, "Elemento sem GlobalId."));
          return;
        }
        mostrarElemento(escolha.globalId, false);
      };
      limpar(overlay);
      overlay.append(carregando("Convertendo o IFC no navegador…"));
      await v.carregarIfc(urls.modeloIfc(projetoId), (p) => {
        const fracao = p > 1 ? p / 100 : p;
        overlay.querySelector(".carregando")?.replaceWith(
          carregando(`Convertendo o IFC no navegador… ${Math.round(fracao * 100)}%`),
        );
      });
      if (minhaGeracao !== geracao) return;
      await v.mapearElementos([...indices.elementos.values()].map((e) => ({ global_id: e.global_id, step_id: e.step_id })));
      await v.aplicarEstados(relatorio.estado_elementos);
      overlay.remove();
    } catch (e) {
      if (minhaGeracao !== geracao) return;
      planoB(mensagemErro(e));
    }
  };
  requestAnimationFrame(() => void iniciarViewer());

  // ---------------------------------------------------------------- montagem
  append(secao, [
    h(
      "div",
      { class: "cabecalho-passo cabecalho-resultados" },
      h(
        "div",
        null,
        h("h2", null, "6. Resultados"),
        h(
          "p",
          null,
          `${relatorio.edital_arquivo} × ${relatorio.modelo_arquivo} (${relatorio.schema_ifc}) · gerado em ${dataHora(relatorio.gerado_em)} · `,
          relatorio.modo_ia === "offline" ? "modo offline (regras)" : `IA: ${relatorio.modo_ia}`,
        ),
      ),
      h(
        "div",
        { class: "downloads" },
        linkDownload("IDS", urls.idsXml(projetoId)),
        linkDownload("BCF", urls.bcf(vid)),
        h("a", { class: "btn btn-secundario", href: urls.relatorioHtml(vid), target: "_blank", rel: "noopener" }, "Relatório HTML"),
        linkDownload("EIR (.xlsx)", urls.eirXlsx(projetoId)),
        linkDownload("JSON", urls.relatorioJson(vid)),
      ),
    ),
    painelIndicadores(relatorio),
    avisos(relatorio.avisos),
    h("div", { class: "grade-resultados" }, blocoViewer, detalhe),
    h(
      "div",
      { class: "cartao" },
      h("div", { class: "cartao-titulo" }, h("h3", null, "Apontamentos"), contagem),
      h("div", { class: "barra-ferramentas" }, selectTipo, selectSeveridade, selectDestinatario, busca),
      listaApts,
    ),
    secoesComplementares(relatorio),
    h("div", { class: "acoes" }, botao("← Verificação", () => ctx.irPara(5), "fantasma"), botao("Revisar o EIR", () => ctx.irPara(3), "fantasma")),
  ]);
  detalheVazio();
  desenharLista();
  return secao;
}

// ==================================================================== componentes

function selectFiltro(
  rotuloTexto: string,
  opcoes: [string, string][],
  atual: string,
  aoMudar: (v: string) => void,
): HTMLSelectElement {
  const sel = h(
    "select",
    { "aria-label": rotuloTexto },
    opcoes.map(([valor, texto]) => h("option", { value: valor }, texto)),
  );
  sel.value = opcoes.some(([v]) => v === atual) ? atual : opcoes[0][0];
  sel.addEventListener("change", () => aoMudar(sel.value));
  return sel;
}

function painelIndicadores(r: Relatorio): HTMLElement {
  const i = r.indicadores;
  const totalApts = r.apontamentos.length;
  const sev = i.apontamentos_por_severidade;
  const dest = i.apontamentos_por_destinatario;
  return h(
    "div",
    { class: "indicadores" },
    indicador(
      "Conformidade do modelo",
      pct(i.conformidade_percentual),
      `${num(i.especificacoes_aprovadas)} de ${num(i.especificacoes_total)} especificações IDS aprovadas · ${num(i.elementos_nao_conformes)} de ${num(i.elementos_verificados)} elementos não conformes`,
      i.conformidade_percentual,
    ),
    indicador(
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
    h(
      "div",
      { class: "indicador" },
      h("span", { class: "indicador-rotulo" }, "Apontamentos"),
      h("strong", { class: "indicador-valor" }, num(totalApts)),
      h(
        "div",
        { class: "chips-linha" },
        badge(`Alta ${num(sev.alta ?? 0)}`, "alta"),
        badge(`Média ${num(sev.media ?? 0)}`, "media"),
        badge(`Baixa ${num(sev.baixa ?? 0)}`, "baixa"),
      ),
      h(
        "small",
        null,
        `Projetista ${num(dest.projetista ?? 0)} · Contratante ${num(dest.contratante ?? 0)}`,
      ),
    ),
    h(
      "div",
      { class: "indicador" },
      h("span", { class: "indicador-rotulo" }, "Verificação manual"),
      h("strong", { class: "indicador-valor" }, num(i.requisitos_nao_verificaveis)),
      h("small", null, `requisito(s) não verificável(is) por IDS · ${num(i.requisitos_aprovados)} aprovado(s) no EIR`),
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

function cartaoApontamento(apt: Apontamento, aoClicar: () => void): HTMLElement {
  const paginasTxt = [...new Set(apt.evidencias_edital.map((e) => e.pagina))].map((p) => `p. ${p}`).join(", ");
  return h(
    "button",
    { type: "button", class: `apontamento sev-${apt.severidade}`, "data-apt": apt.id, onclick: () => aoClicar() },
    h(
      "div",
      { class: "apontamento-topo" },
      badge(rotulo(SEVERIDADE, apt.severidade), VARIANTE_SEVERIDADE[apt.severidade] ?? "neutro"),
      badge(rotulo(TIPO_APONTAMENTO, apt.tipo), "neutro"),
      h("span", { class: "apontamento-id" }, apt.id),
      apt.gerado_por_ia ? badge("IA", "info", "Gerado por IA — revisar") : null,
    ),
    h("strong", { class: "apontamento-titulo" }, apt.titulo),
    h(
      "span",
      { class: "apontamento-meta" },
      `${rotulo(DESTINATARIO, apt.destinatario)} age`,
      apt.requisito_id ? ` · ${apt.requisito_id}` : "",
      paginasTxt ? ` · Edital ${paginasTxt}` : "",
      apt.elementos.length ? ` · ${apt.elementos.length} elemento(s)` : "",
    ),
  );
}

function evidenciaBloco(ev: Evidencia, clausula?: string | null): HTMLElement {
  const local = [clausula ? `item ${clausula}` : null, `p. ${ev.pagina}`].filter(Boolean).join(", ");
  return h("blockquote", { class: "trecho" }, ev.trecho, h("cite", null, `Edital, ${local}`));
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
  acoes: { focarElemento: (guid: string) => void; adicionarAoEir: () => void },
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
      badge(rotulo(SEVERIDADE, apt.severidade), VARIANTE_SEVERIDADE[apt.severidade] ?? "neutro"),
      badge(rotulo(TIPO_APONTAMENTO, apt.tipo), "neutro"),
      badge(rotulo(ANALISE, apt.analise), "neutro"),
    ),
    h("h3", null, h("span", { class: "texto-suave" }, `${apt.id} · `), apt.titulo),
    h("p", { class: "quem-age" }, "Quem age: ", h("strong", null, rotulo(DESTINATARIO, apt.destinatario))),
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
      ? h("div", { class: "detalhe-secao" }, h("h4", null, "Trecho do edital"), evidencias.map((ev) => evidenciaBloco(ev)))
      : null,
    elementos.length
      ? h(
          "div",
          { class: "detalhe-secao" },
          h("h4", null, `Elementos (${apt.elementos.length})`),
          h(
            "ul",
            { class: "lista-elementos" },
            elementos.map((el) =>
              h(
                "li",
                null,
                h(
                  "button",
                  { type: "button", class: "link-botao", onclick: () => acoes.focarElemento(el.global_id) },
                  el.nome ?? "(sem nome)",
                ),
                h("small", null, ` ${el.classe ?? ""} · `, h("code", null, el.global_id)),
              ),
            ),
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
          botao("Adicionar ao EIR", () => acoes.adicionarAoEir(), "primario", {
            title: "Cria requisitos sugeridos e volta à revisão do EIR",
          }),
        )
      : null,
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
    h("h3", null, info?.nome ?? "Elemento do modelo"),
    h(
      "dl",
      { class: "dados-elemento" },
      h("dt", null, "Classe"),
      h("dd", null, info?.classe ?? "—"),
      h("dt", null, "GlobalId"),
      h("dd", null, h("code", null, guid)),
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
            : "Nenhum requisito do EIR se aplica a este elemento.",
        ),
  );
}

function secoesComplementares(r: Relatorio): HTMLElement {
  const itens = new Map(r.itens_checklist.map((i) => [i.id, i]));
  const checklist = h(
    "details",
    { class: "cartao detalhes-cartao" },
    h("summary", null, h("strong", null, "Checklist de itens mínimos do edital"), ` · ${r.checklist.length} itens`),
    r.checklist.length
      ? h(
          "div",
          { class: "tabela-rolagem" },
          h(
            "table",
            { class: "tabela" },
            h(
              "thead",
              null,
              h("tr", null, h("th", null, "Item"), h("th", null, "Crítico"), h("th", null, "Status"), h("th", null, "Evidência"), h("th", null, "Avaliado por")),
            ),
            h(
              "tbody",
              null,
              r.checklist.map((res) => {
                const item = itens.get(res.item_id);
                return h(
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
                );
              }),
            ),
          ),
        )
      : vazio("Checklist não avaliada."),
  );
  const cobertura = h(
    "details",
    { class: "cartao detalhes-cartao" },
    h(
      "summary",
      null,
      h("strong", null, "Cobertura do edital por classe IFC"),
      r.cobertura ? ` · ${pct(r.cobertura.percentual)}` : "",
    ),
    r.cobertura?.classes.length
      ? h(
          "div",
          { class: "tabela-rolagem" },
          h(
            "table",
            { class: "tabela compacta" },
            h("thead", null, h("tr", null, h("th", null, "Classe"), h("th", { class: "num" }, "Elementos"), h("th", null, "Coberta"), h("th", null, "Requisitos"))),
            h(
              "tbody",
              null,
              [...r.cobertura.classes]
                .sort((a, b) => Number(a.coberta) - Number(b.coberta) || b.contagem - a.contagem)
                .map((c) =>
                  h(
                    "tr",
                    null,
                    h("td", null, h("code", null, c.classe)),
                    h("td", { class: "num" }, num(c.contagem)),
                    h("td", null, c.coberta ? badge("Sim", "sucesso") : badge("Lacuna", "alta")),
                    h("td", null, c.requisitos.join(", ") || "—"),
                  ),
                ),
            ),
          ),
        )
      : vazio("Cobertura não calculada."),
  );
  const ids = h(
    "details",
    { class: "cartao detalhes-cartao" },
    h("summary", null, h("strong", null, "Resultados do IDS por especificação"), ` · ${r.resultados_ids.length}`),
    r.resultados_ids.length
      ? h(
          "div",
          { class: "tabela-rolagem" },
          h(
            "table",
            { class: "tabela compacta" },
            h("thead", null, h("tr", null, h("th", null, "Especificação"), h("th", { class: "num" }, "Aplicáveis"), h("th", { class: "num" }, "Aprovados"), h("th", null, "Status"))),
            h(
              "tbody",
              null,
              r.resultados_ids.map((res) =>
                h(
                  "tr",
                  null,
                  h("td", null, res.nome_especificacao),
                  h("td", { class: "num" }, num(res.aplicaveis)),
                  h("td", { class: "num" }, num(res.aprovados)),
                  h(
                    "td",
                    null,
                    res.aplicaveis === 0
                      ? badge("Sem elementos", "neutro")
                      : res.status
                        ? badge("Aprovada", "sucesso")
                        : badge("Reprovada", "alta"),
                  ),
                ),
              ),
            ),
          ),
        )
      : vazio("Nenhuma especificação IDS executada."),
  );
  return h("div", { class: "complementares" }, ids, cobertura, checklist);
}
