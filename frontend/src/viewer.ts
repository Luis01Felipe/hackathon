// Visualizador 3D com @thatopen/components v3 (MIT).
// O IFC é convertido em fragments no navegador. O wasm do web-ifc e o worker de
// fragments são servidos localmente (public/wasm e public/fragments).
import * as OBC from "@thatopen/components";
import * as FRAGS from "@thatopen/fragments";
import * as THREE from "three";
import type { EstadoElemento, EstadoElementoItem } from "./types";

type Mundo = OBC.SimpleWorld<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>;

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

export class Viewer3D {
  onPick: ((escolha: EscolhaElemento | null) => void) | null = null;

  private model: FRAGS.FragmentsModel | null = null;
  private readonly guidParaLocal = new Map<string, number>();
  private readonly localParaGuid = new Map<number, string>();
  private readonly estados = new Map<number, EstadoElemento>();
  private readonly espacos = new Set<number>();
  private todos: number[] = [];
  private selecionados: number[] = [];
  private transparencia = true;
  private inicioToque = { x: 0, y: 0 };
  private descartado = false;

  private constructor(
    private readonly components: OBC.Components,
    private readonly world: Mundo,
    private readonly fragments: OBC.FragmentsManager,
  ) {}

  static async criar(container: HTMLElement): Promise<Viewer3D> {
    const components = new OBC.Components();
    const worlds = components.get(OBC.Worlds);
    const world = worlds.create<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>();
    world.scene = new OBC.SimpleScene(components);
    world.scene.setup();
    world.scene.three.background = new THREE.Color("#eef1f5");
    world.renderer = new OBC.SimpleRenderer(components, container);
    world.camera = new OBC.OrthoPerspectiveCamera(components);
    await world.camera.controls.setLookAt(40, 30, 40, 0, 0, 0);
    components.init();
    components.get(OBC.Grids).create(world);

    const fragments = components.get(OBC.FragmentsManager);
    fragments.init(new URL("fragments/worker.mjs", document.baseURI).href);
    world.camera.controls.addEventListener("update", () => {
      void fragments.core.update();
    });
    fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(world.camera.three);
      world.scene.three.add(model.object);
      void fragments.core.update(true);
    });
    // Evita z-fighting entre portas/janelas e paredes coplanares.
    fragments.core.models.materials.list.onItemSet.add(({ value: mat }) => {
      if ("isLodMaterial" in mat && mat.isLodMaterial) return;
      mat.polygonOffset = true;
      mat.polygonOffsetUnits = 1;
      mat.polygonOffsetFactor = Math.random();
    });

    const viewer = new Viewer3D(components, world, fragments);
    viewer.ligarCliques();
    return viewer;
  }

  async carregarIfc(url: string, aoProgredir?: (fracao: number) => void): Promise<void> {
    const resposta = await fetch(url);
    if (!resposta.ok) throw new Error(`Não foi possível baixar o IFC (HTTP ${resposta.status}).`);
    const bytes = new Uint8Array(await resposta.arrayBuffer());
    const loader = this.components.get(OBC.IfcLoader);
    await loader.setup({
      autoSetWasm: false,
      wasm: { path: new URL("wasm/", document.baseURI).href, absolute: true },
    });
    this.model = await loader.load(bytes, false, "modelo", {
      processData: { progressCallback: (p) => aoProgredir?.(p) },
    });
    if (this.descartado) return;
    this.todos = await this.model.getItemsIdsWithGeometry();
    const categorias = await this.model.getItemsOfCategories([/^IFCSPACE$/i]);
    for (const ids of Object.values(categorias)) ids.forEach((id) => this.espacos.add(id));
    await this.world.camera.fitToItems();
  }

  /** Liga cada GlobalId ao localId do fragments. Usa o step_id como reserva. */
  async mapearElementos(itens: { global_id: string; step_id: number | null }[]): Promise<void> {
    if (!this.model) return;
    const pendentes = itens.filter((i) => !this.guidParaLocal.has(i.global_id));
    if (!pendentes.length) return;
    const locais = await this.model.getLocalIdsByGuids(pendentes.map((i) => i.global_id));
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
    if (!this.model) return 0;
    const ids = globalIds
      .map((g) => this.guidParaLocal.get(g))
      .filter((id): id is number => id !== undefined);
    this.selecionados = ids;
    await this.pintar();
    if (ids.length) {
      await this.world.camera.fitToItems({ [this.model.modelId]: new Set(ids) });
    }
    return ids.length;
  }

  async limparSelecao(): Promise<void> {
    this.selecionados = [];
    await this.pintar();
  }

  async enquadrarTudo(): Promise<void> {
    if (!this.model) return;
    await this.world.camera.fitToItems();
  }

  async alternarTransparencia(): Promise<boolean> {
    this.transparencia = !this.transparencia;
    await this.pintar();
    return this.transparencia;
  }

  guidDe(localId: number): string | null {
    return this.localParaGuid.get(localId) ?? null;
  }

  dispose(): void {
    this.descartado = true;
    this.onPick = null;
    this.components.dispose();
  }

  private async pintar(): Promise<void> {
    const model = this.model;
    if (!model) return;
    await model.resetHighlight();
    const grupos = new Map<string, { def: FRAGS.MaterialDefinition; ids: number[] }>();
    const adicionar = (chave: string, def: FRAGS.MaterialDefinition, id: number) => {
      const grupo = grupos.get(chave) ?? { def, ids: [] };
      grupo.ids.push(id);
      grupos.set(chave, grupo);
    };
    const selecionados = new Set(this.selecionados);
    const opacidadeNeutra = this.transparencia ? 0.32 : 1;
    for (const id of this.todos) {
      const espaco = this.espacos.has(id);
      if (selecionados.has(id)) {
        adicionar("sel", material(CORES.selecionado, espaco ? 0.55 : 1), id);
        continue;
      }
      const estado = this.estados.get(id);
      if (estado) {
        const opacidade = espaco ? 0.35 : 1;
        adicionar(`${estado}-${espaco}`, material(CORES[estado], opacidade), id);
        continue;
      }
      const opacidade = espaco ? 0.08 : opacidadeNeutra;
      adicionar(`neutro-${espaco}`, material(CORES.sem_requisito, opacidade), id);
    }
    for (const { def, ids } of grupos.values()) {
      await model.highlight(ids, def);
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
    const acertos = ((await model.raycastAll(dados)) ?? []).sort((a, b) => a.distance - b.distance);
    if (!acertos.length) {
      this.onPick(null);
      return;
    }
    const comEstado = acertos.find((a) => this.estados.has(a.localId) && !this.espacos.has(a.localId));
    const naoEspaco = acertos.find((a) => !this.espacos.has(a.localId));
    const alvo = comEstado ?? (this.transparencia ? acertos.find((a) => this.estados.has(a.localId)) : undefined) ?? naoEspaco ?? acertos[0];
    let guid = this.localParaGuid.get(alvo.localId) ?? null;
    if (!guid) {
      const [encontrado] = await model.getGuidsByLocalIds([alvo.localId]);
      guid = encontrado ?? null;
      if (guid) {
        this.localParaGuid.set(alvo.localId, guid);
        this.guidParaLocal.set(guid, alvo.localId);
      }
    }
    this.selecionados = [alvo.localId];
    await this.pintar();
    this.onPick({ globalId: guid, localId: alvo.localId });
  }
}
