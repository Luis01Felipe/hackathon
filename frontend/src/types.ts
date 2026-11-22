// Tipos do contrato HTTP (docs/api.md). Os nomes espelham o domínio do backend.

export type StatusRequisito = "proposto" | "aprovado" | "editado" | "rejeitado";
export type Faceta = "property" | "attribute" | "classification" | "material" | "partOf";
export type OrigemVocabulario = "pset_oficial" | "bsdd" | "customizado";
export type Cardinalidade = "required" | "optional" | "prohibited";
export type TipoRestricao = "valor" | "enumeracao" | "padrao" | "intervalo";
export type TipoApontamento =
  | "nao_conformidade"
  | "ambiguidade"
  | "nao_verificavel"
  | "item_ausente"
  | "contradicao"
  | "lacuna_cobertura"
  | "qualidade_modelo";
export type Severidade = "alta" | "media" | "baixa";
export type Destinatario = "projetista" | "contratante";
export type StatusChecklist = "presente" | "parcial" | "ausente";
export type EstadoElemento = "conforme" | "nao_conforme";
export type StatusVerificacao = "pendente" | "executando" | "concluida" | "falhou";
export type StatusAnalise = "pendente" | "executando" | "concluida" | "falhou" | "ignorada";

export interface Config {
  versao: string;
  modo_ia: string;
  modelo_llm: string | null;
  bsdd_ativo: boolean;
  demo_disponivel: boolean;
  limite_upload_mb: number;
}

export interface ClasseResumo {
  nome: string;
  contagem: number;
  especificavel: boolean;
}

export interface ProjetoResumo {
  id: string;
  criado_em: string;
  edital_arquivo: string;
  modelo_arquivo: string;
  schema_ifc: string;
  paginas: number;
  total_elementos: number;
  classes: ClasseResumo[];
  topicos_total: number;
  requisitos_total: number;
  ids_gerado: boolean;
  avisos: string[];
  modo_ia: string;
}

export interface Topico {
  id: string;
  numero: string;
  titulo: string;
  nivel: number;
  pagina_inicio: number;
  pagina_fim: number;
  texto: string;
  relevante_bim: boolean;
  resumo: string | null;
}

export interface Evidencia {
  pagina: number;
  trecho: string;
}

export interface Restricao {
  tipo: TipoRestricao;
  valores: string[];
  minimo: number | null;
  maximo: number | null;
}

export interface Requisito {
  id: string;
  topico_id: string;
  descricao: string;
  evidencia: Evidencia;
  verificavel_por_ids: boolean;
  motivo_nao_verificavel: string | null;
  ifc_class: string | null;
  predefined_type: string | null;
  faceta: Faceta | null;
  pset: string | null;
  propriedade: string | null;
  tipo_dado: string | null;
  restricao: Restricao | null;
  cardinalidade: Cardinalidade;
  origem_vocabulario: OrigemVocabulario | null;
  bsdd_uri: string | null;
  status: StatusRequisito;
  sugerido_por_lacuna: boolean;
  clausula: string | null;
  gerado_por: string;
  avisos: string[];
}

export interface EirResposta {
  versao: number;
  data: string;
  topicos_selecionados: string[];
  aprovado_por: string | null;
  requisitos: Requisito[];
  avisos: string[];
  descartados: number;
}

export interface CamposEdicao {
  descricao?: string;
  ifc_class?: string | null;
  predefined_type?: string | null;
  faceta?: Faceta | null;
  pset?: string | null;
  propriedade?: string | null;
  tipo_dado?: string | null;
  restricao?: Restricao | null;
  cardinalidade?: Cardinalidade;
  verificavel_por_ids?: boolean;
  motivo_nao_verificavel?: string | null;
}

export type AcaoRequisito =
  | { acao: "aprovar" }
  | { acao: "rejeitar" }
  | { acao: "reabrir" }
  | { acao: "editar"; campos: CamposEdicao };

export interface IdsResposta {
  especificacoes: number;
  valido: boolean;
  erros: string[];
  requisitos_incluidos: string[];
  url: string;
}

export interface Verificacao {
  id: string;
  projeto_id: string;
  status: StatusVerificacao;
  progresso: Record<string, StatusAnalise>;
  iniciado_em: string | null;
  concluido_em: string | null;
  erro: string | null;
  avisos: string[];
}

export interface Referencia {
  tipo: string;
  rotulo: string;
  uri: string | null;
}

export interface ElementoRef {
  global_id: string;
  step_id: number | null;
  classe: string | null;
  nome: string | null;
}

export interface PropriedadeSugerida {
  pset: string;
  nome: string;
  tipo_dado: string | null;
}

export interface Apontamento {
  id: string;
  tipo: TipoApontamento;
  severidade: Severidade;
  destinatario: Destinatario;
  titulo: string;
  analise: string;
  evidencias_edital: Evidencia[];
  elementos: ElementoRef[];
  requisito_id: string | null;
  como_agir: string;
  por_que: string;
  referencias: Referencia[];
  gerado_por_ia: boolean;
  referencia_a_confirmar: boolean;
  classe_ifc: string | null;
  propriedades_sugeridas: PropriedadeSugerida[];
  detalhe: string;
}

export interface FalhaElemento {
  global_id: string;
  step_id: number;
  classe: string;
  nome: string | null;
  motivo: string;
}

export interface ResultadoEspecificacao {
  nome_especificacao: string;
  requisito_id: string | null;
  status: boolean;
  aplicaveis: number;
  aprovados: number;
  falhas: FalhaElemento[];
  elementos_aprovados: string[];
}

export interface CoberturaClasse {
  classe: string;
  contagem: number;
  coberta: boolean;
  requisitos: string[];
}

export interface Cobertura {
  percentual: number | null;
  classes: CoberturaClasse[];
}

export interface ResultadoChecklist {
  item_id: string;
  status: StatusChecklist;
  evidencia: Evidencia | null;
  justificativa: string;
  avaliado_por: string;
}

export interface ItemChecklist {
  id: string;
  item: string;
  critico: boolean;
  descricao: string;
  palavras_chave: string[];
}

export interface Indicadores {
  conformidade_percentual: number | null;
  especificacoes_total: number;
  especificacoes_aprovadas: number;
  elementos_verificados: number;
  elementos_nao_conformes: number;
  cobertura_percentual: number | null;
  classes_especificaveis: number;
  classes_cobertas: number;
  checklist_presentes: number;
  checklist_parciais: number;
  checklist_total: number;
  requisitos_aprovados: number;
  requisitos_nao_verificaveis: number;
  apontamentos_por_severidade: Record<string, number>;
  apontamentos_por_destinatario: Record<string, number>;
  apontamentos_por_tipo: Record<string, number>;
}

export interface EstadoElementoItem {
  global_id: string;
  step_id: number | null;
  estado: EstadoElemento;
}

export interface Relatorio {
  verificacao_id: string;
  projeto_id: string;
  gerado_em: string;
  edital_arquivo: string;
  modelo_arquivo: string;
  schema_ifc: string;
  modo_ia: string;
  indicadores: Indicadores;
  apontamentos: Apontamento[];
  resultados_ids: ResultadoEspecificacao[];
  cobertura: Cobertura | null;
  checklist: ResultadoChecklist[];
  itens_checklist: ItemChecklist[];
  requisitos: Requisito[];
  estado_elementos: EstadoElementoItem[];
  avisos: string[];
  duracoes_s: Record<string, number>;
}
