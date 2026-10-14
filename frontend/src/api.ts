// Client HTTP tipizzato verso l'API EarnSight: l'unico modulo che chiama fetch.
// Gli URL sono relativi (/api/...): in produzione nginx li inoltra al backend,
// in sviluppo lo fa il proxy di Vite. Nessun CORS, nessun indirizzo hardcoded.

export type DocStatus = "pending" | "processing" | "done" | "needs_review" | "needs_ocr" | "failed";
export type DocType = "cedolino" | "cu";

export interface DocumentSummary {
  id: string;
  doc_type: DocType;
  filename: string;
  status: DocStatus;
  template: string | null;
  period_month: number | null;
  period_year: number | null;
  gross_pay: string | null; // Decimal serializzato come stringa ("2250.00")
  net_pay: string | null;
  total_deductions: string | null;
  taxable_income: string | null;
  income_tax: string | null;
  employer_tax_code: string | null;
  error: string | null;
  created_at: string;
  additional_payment: boolean;
}

export interface FieldValue {
  value: unknown;
  confidence: number;
  source?: string | null;
  corrected?: boolean;
}

export interface Issue {
  field: string | null;
  check: string;
  message: string;
  action: "user" | "llm";
}

export interface Entry {
  code: string | null;
  description: string | null;
  amount: number;
  entry_type: "spettanza" | "trattenuta";
}

export interface DocumentDetail extends DocumentSummary {
  raw_text: string | null;
  extraction: {
    fields?: Record<string, FieldValue>;
    issues?: Issue[];
    pages?: string[];
  } | null;
  entries: Entry[];
}

export interface LlmSettings {
  llm_provider: string | null;
  ollama_base_url: string | null;
  ollama_model: string | null;
  openai_model: string | null;
  openai_api_key_set: boolean;
  llm_ready: boolean;
  llm_detail: string;
}

export interface LlmSettingsInput {
  llm_provider: string;
  ollama_base_url?: string | null;
  ollama_model?: string | null;
  openai_model?: string | null;
  openai_api_key?: string; // assente = invariata, "" = cancella
}

export interface YearPayslip {
  id: string;
  month: number | null;
  additional_payment: boolean;
}

export interface YearTotals {
  gross_pay: string | null;
  net_pay: string | null;
  total_deductions: string | null;
  taxable_income: string | null;
  income_tax: string | null;
}

export interface YearCompleteness {
  status: "complete" | "incomplete" | "no_fiscal_data";
  taxable_diff: string | null;
  tax_diff: string | null;
}

export interface YearCu {
  id: string;
  status: "match" | "mismatch" | "no_payslips" | "no_fiscal_data" | "to_review";
  taxable_diff: string | null;
  tax_diff: string | null;
}

/** Una scheda della pagina «Anni»: un anno con un datore di lavoro. */
export interface YearSummary {
  year: number;
  employer_tax_code: string | null;
  template: string | null;
  payslips: YearPayslip[]; // in ordine di progressivo: l'ultimo è il riferimento
  missing_months: number[]; // 1-12
  duplicates: string[]; // id dei documenti
  to_review: string[];
  totals: YearTotals;
  completeness: YearCompleteness;
  cu: YearCu | null; // null = nessuna CU (facoltativa, non è un errore)
}

/** Errore dell'API con il messaggio (`detail`) già pronto da mostrare. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

const TOKEN_KEY = "earnsight.token";
let onUnauthorized: () => void = () => {};

/** Il token vive in sessionStorage: sopravvive al refresh, sparisce chiudendo la scheda. */
export const tokenStore = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (token: string) => sessionStorage.setItem(TOKEN_KEY, token),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};

/** Chiamato su ogni 401 di una richiesta autenticata (token scaduto o non valido). */
export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler;
}

function detailOf(body: unknown, fallback: string): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  // errori di validazione FastAPI: lista di {msg, loc}
  if (Array.isArray(detail)) return detail.map((d) => d?.msg ?? String(d)).join("; ");
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}, auth = true): Promise<T> {
  const headers = new Headers(init.headers);
  const token = tokenStore.get();
  if (auth && token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...init, headers });
  } catch {
    throw new ApiError("Il server non risponde: controlla che EarnSight sia avviato.", 0);
  }
  const body = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && auth) onUnauthorized();
    throw new ApiError(detailOf(body, `Errore ${response.status}`), response.status);
  }
  return body as T;
}

const json = (method: string, data: unknown): RequestInit => ({
  method,
  body: JSON.stringify(data),
});

export const api = {
  login: (username: string, password: string) =>
    request<{ access_token: string }>("/auth/login", json("POST", { username, password }), false),

  listDocuments: () => request<DocumentSummary[]>("/payslips"),
  getDocument: (id: string) => request<DocumentDetail>(`/payslips/${id}`),

  upload: (file: File, docType: DocType) => {
    const form = new FormData();
    form.append("file", file);
    form.append("doc_type", docType);
    return request<DocumentSummary>("/payslips/upload", { method: "POST", body: form });
  },

  reprocess: (id: string) => request<DocumentSummary>(`/payslips/${id}/reprocess`, { method: "POST" }),
  correct: (id: string, fields: Record<string, string | number>) =>
    request<DocumentDetail>(`/payslips/${id}/fields`, json("PATCH", { fields })),
  llmResolve: (id: string) => request<DocumentDetail>(`/payslips/${id}/llm-resolve`, { method: "POST" }),

  years: () => request<YearSummary[]>("/years"),

  getSettings: () => request<LlmSettings>("/settings"),
  saveSettings: (input: LlmSettingsInput) => request<LlmSettings>("/settings", json("PUT", input)),
};
