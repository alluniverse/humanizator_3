import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(iso: string) {
  return new Date(iso).toLocaleString("ru-RU", {
    day: "2-digit", month: "2-digit", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

export function truncate(str: string, n = 120) {
  return str.length > n ? str.slice(0, n) + "…" : str;
}

export const TIER_COLOR: Record<string, string> = {
  L1: "bg-green-100 text-green-800",
  L2: "bg-yellow-100 text-yellow-800",
  L3: "bg-red-100 text-red-800",
};

export const MODE_LABEL: Record<string, string> = {
  conservative: "Консервативный",
  balanced: "Сбалансированный",
  expressive: "Экспрессивный",
  precision: "Точный (token-level)",
};

/** Extract a human-readable string from any FastAPI error shape. */
export function extractErrorMessage(err: unknown, fallback = "Произошла ошибка"): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  // Pydantic v2 validation errors: [{type, loc, msg, input}, ...]
  if (Array.isArray(detail)) {
    return detail
      .map((d) => {
        const loc = Array.isArray(d.loc) ? d.loc.filter((s: unknown) => s !== "body").join(" → ") : "";
        return loc ? `${loc}: ${d.msg}` : d.msg;
      })
      .join("; ");
  }
  return fallback;
}

export const STATUS_COLOR: Record<string, string> = {
  created: "bg-slate-100 text-slate-700",
  processing: "bg-blue-100 text-blue-700",
  completed: "bg-green-100 text-green-800",
  failed: "bg-red-100 text-red-800",
};
