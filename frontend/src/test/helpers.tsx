// Helper dei test: API finta (fetch intercettato per metodo + percorso) e render dell'app.
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import type { DocumentDetail, DocumentSummary, LlmSettings } from "../api";
import { App } from "../App";
import { SessionProvider } from "../state";

type Reply = { status?: number; body?: unknown };
type Handler = (request: { body: unknown; init: RequestInit }) => Reply | Promise<Reply>;

export interface FakeApi {
  calls: { method: string; path: string; body: unknown; headers: Headers }[];
  /** Registra una rotta; registrarla due volte è un errore (nasconderebbe la prima). */
  on: (method: string, path: string, handler: Handler | Reply) => void;
}

/** Risposta trattenuta finché il test non chiama `release`: per osservare gli stati «in corso». */
export function deferred(reply: Reply) {
  let release!: () => void;
  const promise = new Promise<Reply>((resolve) => (release = () => resolve(reply)));
  return { handler: () => promise, release };
}

/**
 * Sostituisce fetch: ogni chiamata non prevista risponde 500 con un messaggio esplicito.
 * (vitest: unstubGlobals ripristina fetch a fine test.)
 */
export function fakeApi(): FakeApi {
  const routes = new Map<string, Handler>();
  const calls: FakeApi["calls"] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const method = (init.method ?? "GET").toUpperCase();
      const path = url.replace(/^\/api/, "");
      const body =
        init.body instanceof FormData ? init.body : typeof init.body === "string" ? JSON.parse(init.body) : undefined;
      calls.push({ method, path, body, headers: new Headers(init.headers) });
      const handler = routes.get(`${method} ${path}`);
      const result = handler
        ? await handler({ body, init })
        : { status: 500, body: { detail: `non previsto: ${method} ${path}` } };
      return new Response(JSON.stringify(result.body ?? null), {
        status: result.status ?? 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  return {
    calls,
    on: (method, path, handler) => {
      const key = `${method} ${path}`;
      if (routes.has(key)) throw new Error(`rotta già registrata: ${key}`);
      routes.set(key, typeof handler === "function" ? handler : () => handler);
    },
  };
}

export function renderApp(path = "/", { loggedIn = true } = {}) {
  if (loggedIn) sessionStorage.setItem("earnsight.token", "token-di-test");
  return render(
    <MemoryRouter initialEntries={[path]}>
      <SessionProvider>
        <App />
      </SessionProvider>
    </MemoryRouter>,
  );
}

let seq = 0;
export function makeDoc(overrides: Partial<DocumentSummary> = {}): DocumentSummary {
  seq += 1;
  return {
    id: `doc-${seq}`,
    doc_type: "cedolino",
    filename: `cedolino-${seq}.pdf`,
    status: "done",
    template: "zucchetti",
    period_month: 4,
    period_year: 2026,
    gross_pay: "2005.00",
    net_pay: "1571.00",
    total_deductions: "434.66",
    taxable_income: "1820.74",
    income_tax: "250.00",
    employer_tax_code: "01234567890",
    error: null,
    created_at: `2026-05-0${(seq % 9) + 1}T10:00:00Z`,
    additional_payment: false,
    ...overrides,
  };
}

export function makeDetail(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    ...makeDoc(),
    raw_text: "testo",
    extraction: {
      fields: {
        taxable_income: { value: 1820.74, confidence: 0.9 },
        income_tax: { value: 250, confidence: 0.9 },
        ytd_taxable_income: { value: 8950, confidence: 0.9 },
        ytd_income_tax: { value: 1234, confidence: 0.9 },
      },
      issues: [],
      pages: ["cedolino"],
    },
    entries: [],
    ...overrides,
  };
}

export const READY_LLM: LlmSettings = {
  llm_provider: "ollama",
  ollama_base_url: "http://ollama:11434",
  ollama_model: "llama3.1:8b",
  openai_model: "gpt-4o-mini",
  openai_api_key_set: false,
  llm_ready: true,
  llm_detail: "ollama · impostazioni utente",
};

export const NOT_READY_LLM: LlmSettings = {
  ...READY_LLM,
  llm_provider: null,
  llm_ready: false,
  llm_detail: "Nessun provider LLM configurato: scegli Ollama o OpenAI nelle Impostazioni",
};
