// Visualizador 3D com @thatopen/components v3 (MIT).
// O IFC é convertido em fragments no navegador. O wasm do web-ifc e o worker de
// fragments são servidos localmente (public/wasm e public/fragments).
//
// Perda de contexto WebGL: o navegador pode derrubar a aceleração 3D a qualquer
// momento (pouca memória de vídeo, troca de GPU, driver reiniciado). A restauração
// do próprio SimpleRenderer deixa a tela em branco nos testes, então a tela recria o
// visualizador num canvas novo a partir dos fragments já convertidos (sem converter
// o IFC de novo).
//
// Descarte: o descarte espera as operações em andamento no worker terminarem. Descartar
// o modelo com o CREATE_MODEL ainda rodando deixa mensagens do worker antigo na fila; ao
// respondê-las, o Fragments abre um worker novo, que recebe uma resposta sem pedido
// ("e is not a function" no worker). Por isso a carga é abortada pela API oficial
// (FragmentsModels.abort) e o Components só é descartado quando tudo assentou.
import * as OBC from "@thatopen/components";
import * as FRAGS from "@thatopen/fragments";
import * as THREE from "three";
import type { EstadoElemento, EstadoElementoItem } from "./types";
import { CargaCancelada } from "./viewer-erros";

type Mundo = OBC.SimpleWorld<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>;

const MODELO_ID = "modelo";

/** Limite da densidade de pixels: telas 4K com escala 200% quadruplicam a memória de vídeo. */
const PIXEL_RATIO_MAXIMO = 1.5;

const CORES = {
  conforme: new THREE.Color("#2e9e4f"),
  nao_conforme: new THREE.Color("#d93025"),
  sem_requisito: new THREE.Color("#b9c0c8"),
  selecionado: new THREE.Color("#f5a400"),
};

function material(cor: THREE.Color, opacidade = 1): FRAGS.MaterialDefinition {
  return {
    color: cor,
    renderedFaces: FRAGS.RenderedFaces.TWO,
    opacity: opacidade,
    transparent: opacidade < 1,
  };
}

export interface EscolhaElemento {
  globalId: string | null;
  localId: number;
}

/**
 * Converte o IFC em fragments na thread principal (web-ifc em wasm). Usa as mesmas
 * configurações do OBC.IfcLoader, mas não depende de um visualizador: a conversão
 * sobrevive ao descarte da tela e pode ser reaproveitada.
 */
export async function converterIfc(fonte: string | File, aoProgredir?: (fracao: number) => void): Promise<Uint8Array> {
  const bytes = await lerIfc(fonte);
  const importador = new FRAGS.IfcImporter();
  importador.wasm.path = new URL(`${import.meta.env.BASE_URL}wasm/`, location.origin).href;
  importador.wasm.absolute = true;
  importador.webIfcSettings = { COORDINATE_TO_ORIGIN: true };
  return importador.process({ bytes, progressCallback: (p) => aoProgredir?.(p) });
}

async function lerIfc(fonte: string | File): Promise<Uint8Array> {
  if (typeof fonte !== "string") return new Uint8Array(await fonte.arrayBuffer());
  const resposta = await fetch(fonte);
  if (!resposta.ok) throw new Error(`Não foi possível baixar o IFC (HTTP ${resposta.status}).`);
  return new Uint8Array(await resposta.arrayBuffer());
}

/** Falha antes de criar o mundo 3D: sem WebGL 2 o three.js não desenha nada. */
function exigirWebGl2(): void {
  const teste = document.createElement("canvas").getContext("webgl2");
  if (!teste) {
    throw new Error(
      "Este navegador ou computador não oferece WebGL 2 (aceleração 3D desligada ou bloqueada pela política da empresa).",
    );
  }
  teste.getExtension("WEBGL_lose_context")?.loseContext();
}

export class Viewer3D {
  onPick: ((escolha: EscolhaElemento | null) => void) | null = null;
  /** O navegador derrubou o contexto WebGL; a tela recria o visualizador. */
  onContextoPerdido: (() => void) | null = null;

  private model: FRAGS.FragmentsModel | null = null;
  private readonly guidParaLocal = new Map<string, number>();
  private readonly localParaGuid = new Map<number, string>();
  private readonly estados = new Map<number, EstadoElemento>();
  private readonly espacos = new Set<number>();
  private todos: number[] = [];
  private selecionados: number[] = [];
  private transparencia = true;
  private isolado = false;
  private inicioToque = { x: 0, y: 0 };
  private descartado = false;
  private contexto = true;
  private carregando = false;
  private readonly pendentes = new Set<Promise<unknown>>();
  /** Uma definição por cor e opacidade: o Fragments não recria material a cada clique. */
  private readonly materiais = new Map<string, FRAGS.MaterialDefinition>();

  private constructor(
    private readonly components: OBC.Components,
    private readonly world: Mundo,
    private readonly fragments: OBC.FragmentsManager,
  ) {}

  static async criar(container: HTMLElement): Promise<Viewer3D> {
    exigirWebGl2();
    const components = new OBC.Components();
    const worlds = components.get(OBC.Worlds);
    const world = worlds.create<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>();
    world.scene = new OBC.SimpleScene(components);
    world.scene.setup();
    world.scene.three.background = new THREE.Color("#eef1f5");
    world.renderer = new OBC.SimpleRenderer(components, container);
    world.renderer.three.setPixelRatio(Math.min(window.devicePixelRatio || 1, PIXEL_RATIO_MAXIMO));
    world.renderer.resize(undefined);
    world.camera = new OBC.OrthoPerspectiveCamera(components);
    await world.camera.controls.setLookAt(40, 30, 40, 0, 0, 0);
    components.init();
    components.get(OBC.Grids).create(world);

    const fragments = components.get(OBC.FragmentsManager);
    fragments.init(new URL(`${import.meta.env.BASE_URL}fragments/worker.mjs`, location.origin).href);
    const viewer = new Viewer3D(components, world, fragments);
    world.camera.controls.addEventListener("update", () => {
      if (viewer.descartado || !fragments.initialized) return;
      void fragments.core.update();
    });
    fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(world.camera.three);
      world.scene.three.add(model.object);
      void fragments.core.update(true);
    });
    // Evita z-fighting entre portas/janelas e paredes coplanares: cada material recebe um
    // deslocamento de profundidade diferente, em ciclo (determinístico, sem sorteio).
    let indiceMaterial = 0;
    fragments.core.models.materials.list.onItemSet.add(({ value: mat }) => {
      if ("isLodMaterial" in mat && mat.isLodMaterial) return;
      mat.polygonOffset = true;
      mat.polygonOffsetUnits = 1;
      mat.polygonOffsetFactor = (indiceMaterial++ % 8) * 0.125;
    });

    viewer.ligarCliques();
    world.renderer.three.domElement.addEventListener("webglcontextlost", () => viewer.aoPerderContexto());
    return viewer;
  }

  get carregado(): boolean {
    return this.model !== null;
  }

  get contextoAtivo(): boolean {
    return this.contexto;
  }

  /** Pausa o desenho quando o 3D não está na tela (libera a GPU para o PDF). */
  definirVisivel(visivel: boolean): void {
    const renderer = this.world.renderer;
    if (!renderer || this.descartado || !this.contexto) return;
    renderer.enabled = visivel;
    if (!visivel) return;
    renderer.resize(undefined);
    renderer.needsUpdate = true;
    void this.fragments.core.update(true);
  }

  private aoPerderContexto(): void {
    if (this.descartado || !this.contexto) return;
    this.contexto = false;
    this.onContextoPerdido?.();
  }

  /**
   * Carrega fragments já convertidos (de converterIfc ou de outro visualizador).
   * Rejeita com CargaCancelada se o visualizador for descartado antes de terminar.
   */
  async carregarFragmentos(buffer: ArrayBuffer | Uint8Array): Promise<void> {
    if (this.descartado) throw new CargaCancelada();
    this.carregando = true;
    try {
      // O worker recebe o buffer por transferência e o esvazia: manda uma cópia.
      const copia = buffer.slice(0);
      this.model = await this.acompanhar(null, () => this.fragments.core.load(copia, { modelId: MODELO_ID }));
    } finally {
      this.carregando = false;
    }
    if (this.descartado || !this.model) throw new CargaCancelada();
    await this.acompanhar(undefined, () => this.prepararModelo());
  }

  private async prepararModelo(): Promise<void> {
    const model = this.model;
    if (this.descartado || !model) return;
    this.todos = await model.getItemsIdsWithGeometry();
    const categorias = await model.getItemsOfCategories([/^IFCSPACE$/i]);
    for (const ids of Object.values(categorias)) ids.forEach((id) => this.espacos.add(id));
    await this.world.camera.fitToItems();
  }

  /** Liga cada GlobalId ao localId do fragments. Usa o step_id como reserva. */
  async mapearElementos(itens: { global_id: string; step_id: number | null }[]): Promise<void> {
    const model = this.model;
    if (!model) return;
    const pendentes = itens.filter((i) => !this.guidParaLocal.has(i.global_id));
    if (!pendentes.length) return;
    const locais = await this.acompanhar([], () => model.getLocalIdsByGuids(pendentes.map((i) => i.global_id)));
    pendentes.forEach((item, indice) => {
      const local = locais[indice] ?? item.step_id;
      if (local === null || local === undefined) return;
      this.guidParaLocal.set(item.global_id, local);
      this.localParaGuid.set(local, item.global_id);
    });
  }

  async aplicarEstados(itens: EstadoElementoItem[]): Promise<void> {
    await this.mapearElementos(itens);
    this.estados.clear();
    for (const item of itens) {
      const local = this.guidParaLocal.get(item.global_id);
      if (local !== undefined) this.estados.set(local, item.estado);
    }
    await this.pintar();
  }

  async focar(globalIds: string[]): Promise<number> {
    const model = this.model;
    if (!model) return 0;
    const ids = globalIds
      .map((g) => this.guidParaLocal.get(g))
      .filter((id): id is number => id !== undefined);
    await this.trocarSelecao(ids);
    if (ids.length) {
      await this.acompanhar(undefined, () => this.world.camera.fitToItems({ [model.modelId]: new Set(ids) }));
    }
    return ids.length;
  }

  async limparSelecao(): Promise<void> {
    await this.trocarSelecao([]);
  }

  /** Esconde tudo o que não pertence ao apontamento e enquadra o que sobrou (RF-181). */
  async isolar(globalIds: string[]): Promise<number> {
    const model = this.model;
    if (!model) return 0;
    const ids = globalIds
      .map((g) => this.guidParaLocal.get(g))
      .filter((id): id is number => id !== undefined);
    if (!ids.length) return 0;
    await this.acompanhar(undefined, async () => {
      await model.setVisible(undefined, false);
      await model.setVisible(ids, true);
    });
    this.isolado = true;
    await this.trocarSelecao(ids);
    await this.acompanhar(undefined, () => this.world.camera.fitToItems({ [model.modelId]: new Set(ids) }));
    return ids.length;
  }

  async mostrarTudo(): Promise<void> {
    const model = this.model;
    if (!model || !this.isolado) return;
    await this.acompanhar(undefined, async () => {
      await model.resetVisible();
      await this.fragments.core.update(true);
    });
    this.isolado = false;
  }

  get estaIsolado(): boolean {
    return this.isolado;
  }

  async enquadrarTudo(): Promise<void> {
    if (!this.model) return;
    await this.acompanhar(undefined, () => this.world.camera.fitToItems());
  }

  async alternarTransparencia(): Promise<boolean> {
    this.transparencia = !this.transparencia;
    await this.pintar();
    return this.transparencia;
  }

  guidDe(localId: number): string | null {
    return this.localParaGuid.get(localId) ?? null;
  }

  /**
   * Descarta o visualizador sem deixar mensagens órfãs no worker: aborta a carga em
   * andamento e só libera o Components quando as operações pendentes terminarem.
   */
  dispose(): void {
    if (this.descartado) return;
    this.descartado = true;
    this.onPick = null;
    this.onContextoPerdido = null;
    if (this.world.renderer) this.world.renderer.enabled = false;
    if (this.carregando) this.fragments.core.abort(MODELO_ID);
    void Promise.allSettled([...this.pendentes]).then(() => this.components.dispose());
  }

  /**
   * Roda uma operação no worker e a registra até o fim, para o descarte esperar por ela.
   * Depois do descarte não começa nada novo e devolve o valor padrão.
   */
  private async acompanhar<T>(padrao: T, operacao: () => Promise<T>): Promise<T> {
    if (this.descartado) return padrao;
    const promessa = operacao();
    this.pendentes.add(promessa);
    try {
      return await promessa;
    } finally {
      this.pendentes.delete(promessa);
    }
  }

  /** Repinta o modelo inteiro (estados novos ou troca da transparência). */
  private async pintar(): Promise<void> {
    await this.acompanhar(undefined, async () => {
      const model = this.model;
      if (!model) return;
      await model.resetHighlight();
      await this.realcar(this.todos);
    });
  }

  /** Troca a seleção repintando só os itens que entram ou saem dela. */
  private async trocarSelecao(novos: number[]): Promise<void> {
    const afetados = [...new Set([...this.selecionados, ...novos])];
    this.selecionados = novos;
    await this.acompanhar(undefined, () => this.realcar(afetados));
  }

  private materialPorChave(chave: string, cor: THREE.Color, opacidade: number): FRAGS.MaterialDefinition {
    let def = this.materiais.get(chave);
    if (!def) {
      def = material(cor, opacidade);
      this.materiais.set(chave, def);
    }
    return def;
  }

  /** Cor de um item: selecionado, com estado (conforme ou não) ou neutro. */
  private materialDe(id: number, selecionados: Set<number>): FRAGS.MaterialDefinition {
    const espaco = this.espacos.has(id);
    if (selecionados.has(id)) {
      return this.materialPorChave(`sel-${espaco}`, CORES.selecionado, espaco ? 0.55 : 1);
    }
    const estado = this.estados.get(id);
    if (estado) return this.materialPorChave(`${estado}-${espaco}`, CORES[estado], espaco ? 0.35 : 1);
    const opacidade = espaco ? 0.08 : this.transparencia ? 0.32 : 1;
    return this.materialPorChave(`neutro-${espaco}-${opacidade}`, CORES.sem_requisito, opacidade);
  }

  private async realcar(ids: number[]): Promise<void> {
    const model = this.model;
    if (!model || !ids.length) return;
    const selecionados = new Set(this.selecionados);
    const grupos = new Map<FRAGS.MaterialDefinition, number[]>();
    for (const id of ids) {
      const def = this.materialDe(id, selecionados);
      const grupo = grupos.get(def);
      if (grupo) grupo.push(id);
      else grupos.set(def, [id]);
    }
    for (const [def, grupo] of grupos) {
      await model.highlight(grupo, def);
    }
    await this.fragments.core.update(true);
  }

  private ligarCliques(): void {
    const canvas = this.world.renderer?.three.domElement;
    if (!canvas) return;
    canvas.addEventListener("pointerdown", (ev) => {
      this.inicioToque = { x: ev.clientX, y: ev.clientY };
    });
    canvas.addEventListener("pointerup", (ev) => {
      const dx = ev.clientX - this.inicioToque.x;
      const dy = ev.clientY - this.inicioToque.y;
      if (Math.hypot(dx, dy) > 5 || ev.button !== 0) return;
      void this.escolher(ev.clientX, ev.clientY, canvas);
    });
  }

  /**
   * Faz o raycast de todos os itens sob o cursor e prefere o mais próximo que tenha
   * estado (vermelho/verde). Assim o clique atravessa paredes cinza translúcidas.
   */
  private async escolher(x: number, y: number, canvas: HTMLCanvasElement): Promise<void> {
    const model = this.model;
    if (!model || !this.onPick) return;
    const dados = { camera: this.world.camera.three, mouse: new THREE.Vector2(x, y), dom: canvas };
    const brutos = await this.acompanhar(null, () => model.raycastAll(dados));
    const acertos = (brutos ?? []).sort((a, b) => a.distance - b.distance);
    if (!acertos.length) {
      this.onPick(null);
      return;
    }
    const comEstado = acertos.find((a) => this.estados.has(a.localId) && !this.espacos.has(a.localId));
    const naoEspaco = acertos.find((a) => !this.espacos.has(a.localId));
    const alvo = comEstado ?? (this.transparencia ? acertos.find((a) => this.estados.has(a.localId)) : undefined) ?? naoEspaco ?? acertos[0];
    let guid = this.localParaGuid.get(alvo.localId) ?? null;
    if (!guid) {
      const [encontrado] = await this.acompanhar([], () => model.getGuidsByLocalIds([alvo.localId]));
      guid = encontrado ?? null;
      if (guid) {
        this.localParaGuid.set(alvo.localId, guid);
        this.guidParaLocal.set(guid, alvo.localId);
      }
    }
    await this.trocarSelecao([alvo.localId]);
    this.onPick?.({ globalId: guid, localId: alvo.localId });
  }
}
