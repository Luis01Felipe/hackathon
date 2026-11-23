// Rótulos em português para os enums do contrato.
import type { ItemChecagem, Requisito, Restricao, TipoVerificacao } from "./types";
import { num } from "./ui";

export const TIPO_APONTAMENTO: Record<string, string> = {
  nao_conformidade: "Não conformidade",
  ambiguidade: "Ambiguidade",
  nao_verificavel: "Não verificável",
  item_ausente: "Item ausente",
  contradicao: "Contradição",
  lacuna_cobertura: "Lacuna de cobertura",
  qualidade_modelo: "Qualidade do modelo",
  licao_nao_explicita: "Lição aprendida",
  duplicidade: "Texto repetido",
};

/** Onde está o problema: no edital (contratante corrige) ou no modelo (contratado corrige). */
export const ORIGEM_INCONSISTENCIA: Record<string, string> = {
  edital: "Edital",
  modelo: "Modelo IFC",
};

export const QUEM_CORRIGE: Record<string, string> = {
  edital: "Corrigir no edital · contratante age",
  modelo: "Corrigir no modelo · contratado age",
};

export const DECISAO: Record<string, string> = {
  pendente: "Pendente",
  aceito: "Aceito",
  rejeitado: "Rejeitado",
  em_discussao: "Em discussão",
  dispensado: "Dispensado",
};

export const PERFIL: Record<string, string> = {
  contratante: "Contratante (quem publica o edital)",
  contratado_lider: "Contratado líder",
  contratado: "Contratado / projetista",
  verificador: "Verificador independente",
};

export const SEVERIDADE: Record<string, string> = {
  alta: "Alta",
  media: "Média",
  baixa: "Baixa",
};

export const DESTINATARIO: Record<string, string> = {
  projetista: "Contratado / projetista",
  contratante: "Contratante",
};

export const ORIGEM: Record<string, string> = {
  pset_oficial: "Pset oficial",
  bsdd: "bSDD",
  customizado: "Customizado",
};

export const STATUS_REQUISITO: Record<string, string> = {
  proposto: "Proposto",
  aprovado: "Aprovado",
  editado: "Editado",
  rejeitado: "Rejeitado",
};

export const FACETA: Record<string, string> = {
  property: "Propriedade",
  attribute: "Atributo",
  classification: "Classificação",
  material: "Material",
  partOf: "Parte de",
};

export const CARDINALIDADE: Record<string, string> = {
  required: "Obrigatória",
  optional: "Opcional",
  prohibited: "Proibida",
};

export const TIPO_RESTRICAO: Record<string, string> = {
  valor: "Valor exato",
  enumeracao: "Enumeração",
  padrao: "Padrão (regex)",
  intervalo: "Intervalo",
};

/** Itens de checagem (disciplinas) da planilha de IR. */
export const ITEM_CHECAGEM: Record<ItemChecagem, string> = {
  ILUM: "Iluminação",
  VENT: "Ventilação e climatização",
  ELET: "Instalações elétricas",
  INCE: "Proteção contra incêndio e rotas de fuga",
  ACES: "Acessibilidade",
  ACUS: "Acústica",
  HIDR: "Instalações hidrossanitárias e drenagem",
  DADO: "Comunicação, dados e sinalização",
  ACAB: "Materiais e acabamentos",
  OPER: "Operação e manutenção",
  DIME: "Dimensões e programa de espaços",
  ESTR: "Estrutura, concreto e durabilidade",
};

export const TIPO_VERIFICACAO: Record<TipoVerificacao, string> = {
  ids: "IDS",
  ids_script: "IDS + script",
  script: "Script geométrico",
  manual: "Manual / documental",
};

export const DESCRICAO_VERIFICACAO: Record<TipoVerificacao, string> = {
  ids: "O IDS verifica sozinho.",
  ids_script: "O IDS confere a informação; parte da exigência precisa de script.",
  script: "Só análise geométrica do modelo (IfcOpenShell). Não entra no IDS.",
  manual: "Conferência documental. Não entra no IDS.",
};

/** Verificação efetiva: a escolhida ou, em requisitos antigos, a derivada da S3. */
export function verificacaoDe(req: Requisito): TipoVerificacao {
  if (req.verificacao) return req.verificacao;
  return req.verificavel_por_ids ? "ids" : "manual";
}

export function verificacaoEntraNoIds(tipo: TipoVerificacao): boolean {
  return tipo === "ids" || tipo === "ids_script";
}

export const ANALISE: Record<string, string> = {
  A: "Análise A · Conformidade",
  B: "Análise B · Qualidade do edital",
  C: "Análise C · Cobertura",
  saude: "Saúde do modelo",
  licoes: "Lições aprendidas",
};

export const ETAPA_VERIFICACAO: Record<string, { titulo: string; descricao: string }> = {
  conformidade: { titulo: "Conformidade do modelo", descricao: "Análise A — IFC validado contra o IDS (ifctester)" },
  qualidade_edital: {
    titulo: "Qualidade do edital",
    descricao: "Análise B — termos vagos, itens mínimos, contradições e texto repetido",
  },
  licoes: {
    titulo: "Lições aprendidas",
    descricao: "O edital explicita cada lição? Ambientes e elementos afetados no modelo",
  },
  cobertura: { titulo: "Cobertura do edital", descricao: "Análise C — classes do modelo sem requisito" },
  saude_modelo: { titulo: "Saúde do modelo", descricao: "Schema, proxies, pavimentos, GlobalIds e espaços" },
  relatorio: { titulo: "Relatório e BCF", descricao: "Recomendações, relatório HTML e arquivo BCF" },
};

export const STATUS_ANALISE: Record<string, string> = {
  pendente: "Pendente",
  executando: "Executando",
  concluida: "Concluída",
  falhou: "Falhou",
  ignorada: "Ignorada",
};

export const STATUS_CHECKLIST: Record<string, string> = {
  presente: "Presente",
  parcial: "Parcial",
  ausente: "Ausente",
};

export const ESTADO_ELEMENTO: Record<string, string> = {
  conforme: "Conforme",
  nao_conforme: "Não conforme",
};

export function rotulo(mapa: Record<string, string>, chave: string | null | undefined): string {
  if (!chave) return "—";
  return mapa[chave] ?? chave;
}

export function descreverRestricao(r: Restricao | null): string {
  if (!r) return "";
  switch (r.tipo) {
    case "valor":
      return `= ${r.valores.join(", ")}`;
    case "enumeracao":
      return `∈ {${r.valores.join(", ")}}`;
    case "padrao":
      return `padrão ${r.valores.join(" | ")}`;
    case "intervalo": {
      if (r.minimo !== null && r.maximo !== null) return `entre ${num(r.minimo)} e ${num(r.maximo)}`;
      if (r.minimo !== null) return `≥ ${num(r.minimo)}`;
      if (r.maximo !== null) return `≤ ${num(r.maximo)}`;
      return "intervalo";
    }
    default:
      return "";
  }
}

/** Resumo legível do mapeamento IFC de um requisito, ex.: "IfcDoor · Pset_DoorCommon.FireRating". */
export function mapeamento(req: Requisito): string {
  if (!req.ifc_class) return "Sem classe IFC";
  const classe = req.predefined_type ? `${req.ifc_class} [${req.predefined_type}]` : req.ifc_class;
  const partes = [classe];
  if (req.faceta === "property" && (req.pset || req.propriedade)) {
    partes.push(`${req.pset ?? "?"}.${req.propriedade ?? "?"}`);
  } else if (req.faceta === "attribute" && req.propriedade) {
    partes.push(`atributo ${req.propriedade}`);
  } else if (req.faceta === "classification") {
    partes.push(`classificação ${req.pset ?? ""}${req.propriedade ? ` ${req.propriedade}` : ""}`.trim());
  } else if (req.faceta === "material") {
    partes.push("material");
  } else if (req.faceta === "partOf") {
    partes.push(`parte de ${req.pset ?? req.propriedade ?? "?"}`);
  }
  return partes.join(" · ");
}

/**
 * Glossário exibido na interface e no relatório. Versões das normas conferidas em
 * catálogos públicos em 22/11/2026: confirme a vigência antes de citar em contrato.
 */
export const GLOSSARIO: { termo: string; definicao: string; referencia: string }[] = [
  {
    termo: "IR — Requisitos de informação (Information Requirements)",
    definicao:
      "O que o contratante exige que o modelo contenha em cada entrega do contrato. Aqui são extraídos do edital e aprovados por uma pessoa.",
    referencia: "ISO 19650-1:2018 (ABNT NBR ISO 19650-1:2022) usa os termos OIR, PIR, AIR e EIR.",
  },
  {
    termo: "Marco de entrega",
    definicao: "Momento em que o contratado entrega informação ao contratante (ex.: anteprojeto, projeto executivo).",
    referencia: "ISO 19650-2:2018 (ABNT NBR ISO 19650-2:2022).",
  },
  {
    termo: "IDM",
    definicao: "Método para descrever processos, atores e as trocas de informação entre eles.",
    referencia: "ISO 29481-1:2025 (metodologia e formato).",
  },
  {
    termo: "IDS",
    definicao: "Arquivo que define, de forma verificável por máquina, a informação exigida no modelo IFC.",
    referencia: "buildingSMART, IDS 1.0.",
  },
  { termo: "IFC", definicao: "Formato aberto do modelo BIM.", referencia: "ISO 16739-1; IFC 4.3 ADD2 (buildingSMART)." },
  {
    termo: "BCF",
    definicao: "Formato aberto para comunicar problemas ligados a elementos do modelo.",
    referencia: "buildingSMART, BCF 2.1.",
  },
  { termo: "bSDD", definicao: "Dicionário de dados aberto da buildingSMART.", referencia: "buildingSMART." },
  { termo: "Pset", definicao: "Conjunto de propriedades de um elemento IFC.", referencia: "Psets oficiais da buildingSMART." },
  {
    termo: "Nível de informação necessária",
    definicao: "Quanta informação cada entrega exige.",
    referencia: "ISO 7817-1:2024, que substituiu a EN 17412-1:2020 (CEN).",
  },
  {
    termo: "Sistema de classificação",
    definicao: "Tabelas para classificar elementos e informações da construção.",
    referencia: "ABNT NBR 15965 (série em partes; confira as vigentes no catálogo da ABNT).",
  },
];
