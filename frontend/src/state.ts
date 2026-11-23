import type {
  Config,
  EirResposta,
  IdsResposta,
  ProjetoResumo,
  Relatorio,
  Topico,
  Verificacao,
} from "./types";

export type Passo = 1 | 2 | 3 | 4 | 5 | 6;

export interface Estado {
  config: Config | null;
  projeto: ProjetoResumo | null;
  topicos: Topico[] | null;
  selecionados: Set<string>;
  eir: EirResposta | null;
  ids: IdsResposta | null;
  verificacao: Verificacao | null;
  relatorio: Relatorio | null;
  passo: Passo;
  /** IFC escolhido no navegador: o 3D usa este arquivo e não o baixa de volta (RF-097). */
  ifcLocal: File | null;
}

export interface Ctx {
  estado: Estado;
  irPara: (passo: Passo) => void;
  atualizar: () => void;
}

export function estadoInicial(config: Config | null = null): Estado {
  return {
    config,
    projeto: null,
    topicos: null,
    selecionados: new Set(),
    eir: null,
    ids: null,
    verificacao: null,
    relatorio: null,
    passo: 1,
    ifcLocal: null,
  };
}

/** Maior passo que o usuário já pode abrir, dado o que existe no estado. */
export function passoMaximo(e: Estado): Passo {
  if (e.relatorio) return 6;
  if (e.verificacao) return 5;
  if (e.ids) return 5;
  if (e.eir) return 4;
  if (e.projeto) return 2;
  return 1;
}

export const PASSOS: { numero: Passo; titulo: string; descricao: string }[] = [
  { numero: 1, titulo: "Upload", descricao: "Edital, IFC e lições" },
  { numero: 2, titulo: "Tópicos", descricao: "O que verificar" },
  { numero: 3, titulo: "Requisitos (IR)", descricao: "Uma pessoa aprova" },
  { numero: 4, titulo: "IDS", descricao: "Gerado por código" },
  { numero: 5, titulo: "Verificação", descricao: "Análises e lições" },
  { numero: 6, titulo: "Resultados", descricao: "Relatório, 3D e BCF" },
];
