// Rótulos em português para os enums do contrato.
import type { Requisito, Restricao } from "./types";
import { num } from "./ui";

export const TIPO_APONTAMENTO: Record<string, string> = {
  nao_conformidade: "Não conformidade",
  ambiguidade: "Ambiguidade",
  nao_verificavel: "Não verificável",
  item_ausente: "Item ausente",
  contradicao: "Contradição",
  lacuna_cobertura: "Lacuna de cobertura",
  qualidade_modelo: "Qualidade do modelo",
};

export const SEVERIDADE: Record<string, string> = {
  alta: "Alta",
  media: "Média",
  baixa: "Baixa",
};

export const DESTINATARIO: Record<string, string> = {
  projetista: "Projetista",
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

export const ANALISE: Record<string, string> = {
  A: "Análise A · Conformidade",
  B: "Análise B · Qualidade do edital",
  C: "Análise C · Cobertura",
  saude: "Saúde do modelo",
};

export const ETAPA_VERIFICACAO: Record<string, { titulo: string; descricao: string }> = {
  conformidade: { titulo: "Conformidade do modelo", descricao: "Análise A — IFC validado contra o IDS (ifctester)" },
  qualidade_edital: {
    titulo: "Qualidade do edital",
    descricao: "Análise B — termos vagos, itens mínimos e não verificáveis",
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
