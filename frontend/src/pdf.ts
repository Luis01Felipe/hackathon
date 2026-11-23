// Visualizador do edital em PDF, só leitura, com pdf.js (pdfjs-dist, licença Apache-2.0).
//
// - Desenha só as páginas perto da área visível (editais de centenas de páginas não travam)
//   e devolve a memória das páginas que saem dela. A memória de vídeo é dividida com o 3D.
// - Por cima de cada página, uma camada de marcas: grifos com posição em frações da página
//   (0 a 1, origem no canto superior esquerdo), calculadas pelo backend.
// - Não edita o PDF: a navegação e os grifos são só uma camada de visualização.
// Usa a versão "legacy" do pdf.js: traz compatibilidade com navegadores sem os recursos
// mais novos de JavaScript (ex.: Edge e Firefox de versões estendidas).
import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist/legacy/build/pdf.mjs";
import type { RegiaoPdf } from "./types";
import { h, limpar } from "./ui";

export interface MarcaPdf {
  id: string;
  regioes: RegiaoPdf[];
  /** Classes CSS extras da marca (ex.: "sev-alta origem-edital", "topico-selecionado"). */
  classe: string;
  /** Etiqueta exibida na margem esquerda da primeira região (ex.: "APT-006"). */
  rotulo?: string;
  titulo?: string;
}

const ESCALAS = [0.6, 0.8, 1, 1.25, 1.5, 2];
/** Densidade máxima de pixels do canvas de cada página. */
const PIXEL_RATIO_MAXIMO = 2;
/** Altura de uma etiqueta da margem, em fração da página: etiquetas na mesma linha empilham. */
const ALTURA_ETIQUETA = 0.016;

type Pdfjs = typeof import("pdfjs-dist/legacy/build/pdf.mjs");
let pdfjsCarregado: Promise<Pdfjs> | null = null;

/** Carrega o pdf.js sob demanda: o restante do app não paga o tamanho da biblioteca. */
function carregarPdfjs(): Promise<Pdfjs> {
  pdfjsCarregado ??= Promise.all([
    import("pdfjs-dist/legacy/build/pdf.mjs"),
    import("pdfjs-dist/legacy/build/pdf.worker.min.mjs?url"),
  ]).then(([pdfjs, worker]) => {
    pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
    return pdfjs;
  });
  return pdfjsCarregado;
}

interface PaginaVisual {
  numero: number;
  caixa: HTMLDivElement;
  camada: HTMLDivElement;
  canvas: HTMLCanvasElement | null;
  desenhadaEm: number;
}

export class VisualizadorPdf {
  onMarca: ((id: string) => void) | null = null;

  private readonly rolagem: HTMLDivElement;
  private readonly paginasHost: HTMLDivElement;
  private readonly indicadorPagina: HTMLSpanElement;
  private readonly paginas: PaginaVisual[] = [];
  private marcas: MarcaPdf[] = [];
  private escala = 1;
  private larguraBase = 612;
  private alturaBase = 792;
  private observador: IntersectionObserver | null = null;
  private descartado = false;
  private pausado = false;

  private constructor(
    host: HTMLElement,
    private readonly documento: PDFDocumentProxy,
  ) {
    this.indicadorPagina = h("span", { class: "pdf-pagina-atual" }, "");
    const barra = h(
      "div",
      { class: "pdf-barra" },
      h("button", { type: "button", class: "btn btn-fantasma btn-pequeno", title: "Diminuir", onclick: () => void this.zoom(-1) }, "−"),
      h("button", { type: "button", class: "btn btn-fantasma btn-pequeno", title: "Ajustar à largura", onclick: () => void this.ajustarLargura() }, "Largura"),
      h("button", { type: "button", class: "btn btn-fantasma btn-pequeno", title: "Aumentar", onclick: () => void this.zoom(1) }, "+"),
      this.indicadorPagina,
      h("span", { class: "pdf-so-leitura" }, "Somente leitura"),
    );
    this.paginasHost = h("div", { class: "pdf-paginas" });
    this.rolagem = h("div", { class: "pdf-rolagem" }, this.paginasHost);
    limpar(host);
    host.append(barra, this.rolagem);
    this.rolagem.addEventListener("scroll", () => this.atualizarIndicador(), { passive: true });
  }

  static async criar(host: HTMLElement, url: string): Promise<VisualizadorPdf> {
    const pdfjs = await carregarPdfjs();
    const documento = await pdfjs.getDocument({ url }).promise;
    const visualizador = new VisualizadorPdf(host, documento);
    await visualizador.montar();
    return visualizador;
  }

  get totalPaginas(): number {
    return this.documento.numPages;
  }

  private async montar(): Promise<void> {
    const primeira = await this.documento.getPage(1);
    const viewport = primeira.getViewport({ scale: 1 });
    this.larguraBase = viewport.width;
    this.alturaBase = viewport.height;
    this.observador = new IntersectionObserver((entradas) => this.aoVer(entradas), {
      root: this.rolagem,
      rootMargin: "600px 0px",
    });
    for (let numero = 1; numero <= this.documento.numPages; numero += 1) {
      const camada = h("div", { class: "pdf-camada" });
      const caixa = h("div", { class: "pdf-pagina", "data-pagina": String(numero) }, camada);
      this.paginasHost.append(caixa);
      this.paginas.push({ numero, caixa, camada, canvas: null, desenhadaEm: 0 });
      this.observador.observe(caixa);
    }
    this.ajustarLargura();
    this.atualizarIndicador();
  }

  /** Escala que faz a página caber na largura da área de rolagem. */
  ajustarLargura(): void {
    const disponivel = Math.max(280, this.rolagem.clientWidth - 32);
    this.aplicarEscala(disponivel / this.larguraBase);
  }

  private zoom(direcao: 1 | -1): void {
    const atual = ESCALAS.findIndex((e) => e >= this.escala - 0.01);
    const indice = Math.min(ESCALAS.length - 1, Math.max(0, (atual < 0 ? 2 : atual) + direcao));
    this.aplicarEscala(ESCALAS[indice]);
  }

  private aplicarEscala(escala: number): void {
    const pagina = this.paginaAtual();
    this.escala = escala;
    for (const p of this.paginas) {
      p.caixa.style.width = `${Math.round(this.larguraBase * escala)}px`;
      p.caixa.style.height = `${Math.round(this.alturaBase * escala)}px`;
      p.desenhadaEm = 0;
    }
    this.desenharMarcas();
    this.irParaPagina(pagina, false);
    for (const p of this.paginas) {
      if (this.visivel(p)) void this.desenhar(p);
    }
  }

  private visivel(p: PaginaVisual): boolean {
    const caixa = p.caixa.getBoundingClientRect();
    const area = this.rolagem.getBoundingClientRect();
    return caixa.bottom > area.top - 600 && caixa.top < area.bottom + 600;
  }

  private aoVer(entradas: IntersectionObserverEntry[]): void {
    for (const entrada of entradas) {
      const numero = Number((entrada.target as HTMLElement).dataset.pagina);
      const pagina = this.paginas[numero - 1];
      if (!pagina) continue;
      if (entrada.isIntersecting) void this.desenhar(pagina);
      else this.liberar(pagina);
    }
  }

  /** Devolve a memória do canvas na hora (zerar o tamanho não espera o coletor de lixo). */
  private liberar(p: PaginaVisual): void {
    p.desenhadaEm = 0;
    if (!p.canvas) return;
    p.canvas.width = 0;
    p.canvas.height = 0;
    p.canvas.remove();
    p.canvas = null;
  }

  /** Aba escondida: libera todas as páginas. Visível de novo: redesenha as da área visível. */
  definirVisivel(visivel: boolean): void {
    this.pausado = !visivel;
    if (!visivel) {
      this.paginas.forEach((p) => this.liberar(p));
      return;
    }
    for (const p of this.paginas) {
      if (this.visivel(p)) void this.desenhar(p);
    }
  }

  private async desenhar(p: PaginaVisual): Promise<void> {
    if (this.descartado || this.pausado || p.desenhadaEm === this.escala) return;
    p.desenhadaEm = this.escala;
    const pagina: PDFPageProxy = await this.documento.getPage(p.numero);
    const viewport = pagina.getViewport({ scale: this.escala });
    const razao = Math.min(window.devicePixelRatio || 1, PIXEL_RATIO_MAXIMO);
    const canvas = h("canvas", { class: "pdf-canvas" });
    canvas.width = Math.floor(viewport.width * razao);
    canvas.height = Math.floor(viewport.height * razao);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    await pagina.render({
      canvas,
      viewport,
      transform: razao !== 1 ? [razao, 0, 0, razao, 0, 0] : undefined,
    }).promise;
    if (this.descartado || this.pausado || p.desenhadaEm !== this.escala) {
      canvas.width = 0;
      canvas.height = 0;
      return;
    }
    p.canvas?.remove();
    p.canvas = canvas;
    p.caixa.prepend(canvas);
  }

  /** Troca as marcas exibidas (grifos e etiquetas). */
  definirMarcas(marcas: MarcaPdf[]): void {
    this.marcas = marcas;
    this.desenharMarcas();
  }

  private desenharMarcas(): void {
    for (const p of this.paginas) limpar(p.camada);
    const ocupadas = new Map<number, number[]>();
    for (const marca of this.marcas) {
      marca.regioes.forEach((r, indice) => {
        const pagina = this.paginas[r.pagina - 1];
        if (!pagina) return;
        const grifo = h("button", {
          type: "button",
          class: `pdf-marca ${marca.classe}`,
          "data-marca": marca.id,
          title: marca.titulo ?? marca.rotulo ?? marca.id,
          style:
            `left:${r.x0 * 100}%;top:${r.y0 * 100}%;` +
            `width:${(r.x1 - r.x0) * 100}%;height:${(r.y1 - r.y0) * 100}%`,
          onclick: () => this.onMarca?.(marca.id),
        });
        pagina.camada.append(grifo);
        if (indice === 0 && marca.rotulo) {
          const usadas = ocupadas.get(r.pagina) ?? [];
          let topo = r.y0;
          while (usadas.some((u) => Math.abs(u - topo) < ALTURA_ETIQUETA)) topo += ALTURA_ETIQUETA;
          usadas.push(topo);
          ocupadas.set(r.pagina, usadas);
          pagina.camada.append(
            h(
              "button",
              {
                type: "button",
                class: `pdf-etiqueta ${marca.classe}`,
                "data-marca": marca.id,
                style: `top:${topo * 100}%`,
                onclick: () => this.onMarca?.(marca.id),
              },
              marca.rotulo,
            ),
          );
        }
      });
    }
  }

  /** Rola até a primeira região da marca e a destaca por alguns segundos. */
  irParaMarca(id: string, paginaReserva?: number): boolean {
    const marca = this.marcas.find((m) => m.id === id);
    const regiao = marca?.regioes[0];
    for (const el of this.paginasHost.querySelectorAll<HTMLElement>(".pdf-marca.realce, .pdf-etiqueta.realce")) {
      el.classList.remove("realce");
    }
    if (!regiao) {
      if (paginaReserva) this.irParaPagina(paginaReserva);
      return false;
    }
    const pagina = this.paginas[regiao.pagina - 1];
    if (!pagina) return false;
    const alvo = pagina.caixa.offsetTop + regiao.y0 * pagina.caixa.offsetHeight - 80;
    this.rolagem.scrollTo({ top: Math.max(0, alvo), behavior: "smooth" });
    for (const el of this.paginasHost.querySelectorAll<HTMLElement>(`[data-marca="${CSS.escape(id)}"]`)) {
      el.classList.add("realce");
    }
    return true;
  }

  irParaPagina(numero: number, suave = true): void {
    const pagina = this.paginas[Math.min(this.paginas.length, Math.max(1, numero)) - 1];
    if (!pagina) return;
    this.rolagem.scrollTo({ top: pagina.caixa.offsetTop - 8, behavior: suave ? "smooth" : "auto" });
  }

  private paginaAtual(): number {
    const topo = this.rolagem.scrollTop + 40;
    const atual = this.paginas.find((p) => p.caixa.offsetTop + p.caixa.offsetHeight > topo);
    return atual?.numero ?? 1;
  }

  private atualizarIndicador(): void {
    this.indicadorPagina.textContent = `Página ${this.paginaAtual()} de ${this.documento.numPages}`;
  }

  dispose(): void {
    this.descartado = true;
    this.onMarca = null;
    this.observador?.disconnect();
    this.paginas.forEach((p) => this.liberar(p));
    void this.documento.loadingTask.destroy();
  }
}
