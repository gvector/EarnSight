// Formattazione e parsing in italiano: importi, periodi, stati.
import type { DocStatus, DocumentSummary } from "./api";

export const MONTHS = [
  "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
  "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
];

const eurFormat = new Intl.NumberFormat("it-IT", {
  style: "currency",
  currency: "EUR",
  minimumFractionDigits: 2,
  useGrouping: "always", // l'italiano di default omette il punto sotto le 5 cifre (2468,00)
});

/** "2250.5" | 2250.5 → "2.250,50 €"; null → "—". */
export function eur(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const n = typeof value === "number" ? value : Number(value);
  return Number.isFinite(n) ? eurFormat.format(n) : "—";
}

/** (4, 2026) → "aprile 2026"; con additional → "aprile 2026, mensilità aggiuntiva". */
export function period(doc: Pick<DocumentSummary, "period_month" | "period_year" | "additional_payment" | "doc_type">): string {
  if (doc.doc_type === "cu") return doc.period_year ? `CU ${doc.period_year}` : "CU";
  const month = doc.period_month ? MONTHS[doc.period_month - 1] : undefined;
  if (!month || !doc.period_year) return "periodo non riconosciuto";
  return doc.additional_payment ? `${month} ${doc.period_year}, mensilità aggiuntiva` : `${month} ${doc.period_year}`;
}

export const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const STATUS: Record<DocStatus, { label: string; tone: "ok" | "warn" | "error" | "busy" }> = {
  pending: { label: "In coda", tone: "busy" },
  processing: { label: "In elaborazione", tone: "busy" },
  done: { label: "Verificato", tone: "ok" },
  needs_review: { label: "Da controllare", tone: "warn" },
  needs_ocr: { label: "PDF scansionato", tone: "error" },
  failed: { label: "Elaborazione fallita", tone: "error" },
};

export const NEEDS_ATTENTION: DocStatus[] = ["needs_review", "needs_ocr", "failed"];
export const BUSY: DocStatus[] = ["pending", "processing"];

/** Ordina dal periodo più recente; a parità di mese la mensilità aggiuntiva dopo l'ordinaria. */
export function byPeriodDesc(a: DocumentSummary, b: DocumentSummary): number {
  const key = (d: DocumentSummary) =>
    (d.period_year ?? 0) * 100 + (d.period_month ?? 0) + (d.additional_payment ? 0.5 : 0);
  return key(b) - key(a) || b.created_at.localeCompare(a.created_at);
}

const MIGLIAIA = /^\d{1,3}(\.\d{3})+$/;

/**
 * Importo digitato dall'utente → numero. Accetta "2.250,50", "2,250.50",
 * "2250.50", "250,00", "2.250" (migliaia), "-0,66". Lancia Error se non è un importo.
 */
export function parseAmount(raw: string): number {
  let text = raw.replace(/[\s€]/g, "");
  if (!text) throw new Error("importo vuoto");
  if (text.includes(",") && text.includes(".")) {
    text = text.lastIndexOf(",") > text.lastIndexOf(".")
      ? text.replace(/\./g, "").replace(",", ".") // 2.250,50
      : text.replace(/,/g, ""); // 2,250.50
  } else if (text.includes(",")) {
    text = text.replace(",", "."); // 250,00
  } else if (MIGLIAIA.test(text.replace(/^-/, ""))) {
    text = text.replace(/\./g, ""); // 2.250
  }
  if (!/^-?\d+(\.\d+)?$/.test(text)) throw new Error(`«${raw}» non è un importo`);
  return Number(text);
}

/** Intero digitato dall'utente (mese, anno); lancia Error se non lo è. */
export function parseInteger(raw: string): number {
  const text = raw.trim();
  if (!/^\d+$/.test(text)) throw new Error(`«${raw}» non è un numero intero`);
  return Number(text);
}
