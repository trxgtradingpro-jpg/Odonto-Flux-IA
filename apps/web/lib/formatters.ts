export const numberFormatter = new Intl.NumberFormat("pt-BR");
export const currencyFormatter = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
});
export const percentFormatter = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

export function formatDateTimeBR(value?: string | Date | null) {
  if (!value) return "-";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

export function formatDateBR(value?: string | Date | null) {
  if (!value) return "-";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "-";
  return date.toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

export function formatHourBR(value?: string | Date | null) {
  if (!value) return "--:--";
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  });
}

export function formatPhoneBR(value?: string | null) {
  if (!value) return "-";
  const digits = value.replace(/\D/g, "");
  if (digits.length < 10) return value;

  const normalized = digits.startsWith("55") && digits.length >= 12 ? digits.slice(2) : digits;
  const ddd = normalized.slice(0, 2);
  const first = normalized.length >= 11 ? normalized.slice(2, 7) : normalized.slice(2, 6);
  const second = normalized.length >= 11 ? normalized.slice(7, 11) : normalized.slice(6, 10);
  return `(${ddd}) ${first}-${second}`;
}

export function formatRelativeTime(value?: string | Date | null) {
  if (!value) return "Sem atividade";
  const target = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(target.getTime())) return "Sem atividade";

  const diffMs = Date.now() - target.getTime();
  const diffMin = Math.max(1, Math.floor(Math.abs(diffMs) / 60_000));
  const suffix = diffMs >= 0 ? "atrás" : "a partir de agora";

  if (diffMin < 60) return `${diffMin} min ${suffix}`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} h ${suffix}`;
  const diffD = Math.floor(diffH / 24);
  return `${diffD} d ${suffix}`;
}

export function initials(name?: string | null) {
  if (!name) return "??";
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join("");
}

export function toTitleCase(value?: string | null) {
  if (!value) return "-";
  return value
    .replace(/_/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

export function maskToken(value?: string | null) {
  if (!value) return "-";
  if (value.length <= 8) return "********";
  return `${value.slice(0, 4)}******${value.slice(-4)}`;
}

export const ROLE_LABELS: Record<string, string> = {
  owner: "Proprietário(a)",
  manager: "Gestor(a)",
  receptionist: "Recepção",
  analyst: "Analista",
  admin_platform: "Admin da plataforma",
};

export const STAGE_LABELS: Record<string, string> = {
  novo: "Novo",
  qualificado: "Qualificado",
  em_contato: "Em contato",
  orcamento_enviado: "Orçamento enviado",
  agendado: "Agendado",
  perdido: "Perdido",
};
