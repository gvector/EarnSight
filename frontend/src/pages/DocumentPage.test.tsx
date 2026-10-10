import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { DocumentDetail } from "../api";
import { deferred, fakeApi, makeDetail, NOT_READY_LLM, READY_LLM, renderApp } from "../test/helpers";
import { toCorrection } from "./DocumentPage";

const inconsistent: DocumentDetail = makeDetail({
  id: "d1",
  status: "needs_review",
  net_pay: "1900.00",
  extraction: {
    fields: { net_pay: { value: 1900, confidence: 0.3 }, rounding: { value: 0.66, confidence: 0.9 } },
    issues: [
      { field: "net_pay", check: "net_consistency", message: "Lordo − trattenute non combacia con il netto", action: "user" },
      { field: null, check: "entries_sum", message: "Somma voci diversa dal lordo", action: "llm" },
    ],
    pages: ["presenze", "cedolino"],
  },
  entries: [
    { code: "000014", description: "Retribuzione", amount: 2000, entry_type: "spettanza" },
    { code: "F03020", description: "Ritenute IRPEF", amount: 250, entry_type: "trattenuta" },
  ],
});

function serve(detail: DocumentDetail, llm = READY_LLM) {
  const server = fakeApi();
  server.on("GET", "/payslips", { body: [detail] });
  server.on("GET", `/payslips/${detail.id}`, { body: detail });
  server.on("GET", "/settings", { body: llm });
  return server;
}

describe("toCorrection", () => {
  it("sends numbers for amounts and integers, trimmed text otherwise", () => {
    expect(toCorrection("net_pay", "2.250,50")).toBe(2250.5);
    expect(toCorrection("period_month", "4")).toBe(4);
    expect(toCorrection("company_name", "  ACME  ")).toBe("ACME");
    expect(() => toCorrection("period_month", "aprile")).toThrow();
  });
});

describe("DocumentPage", () => {
  it("shows totals, rounding, entries, issues and the pages of the PDF", async () => {
    serve(inconsistent);
    renderApp("/documenti/d1");
    expect(await screen.findByRole("heading", { name: "Aprile 2026" })).toBeInTheDocument();
    expect(screen.getByText("Arrotondamento")).toBeInTheDocument();
    expect(screen.getByText("Lordo − trattenute non combacia con il netto")).toBeInTheDocument();
    expect(screen.getByText("Somma voci diversa dal lordo")).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Competenze" })).toHaveTextContent("Retribuzione");
    expect(screen.getByRole("table", { name: "Trattenute" })).toHaveTextContent("250,00 €");
    expect(screen.getByText("2 (presenze, cedolino)")).toBeInTheDocument();
    const summary = document.querySelector(".summary")!;
    expect(summary).toHaveTextContent("Lordo2.005,00 €");
    expect(summary).toHaveTextContent("Trattenute434,66 €");
    expect(summary).toHaveTextContent("Arrotondamento0,66 €");
    expect(summary).toHaveTextContent("Netto1.900,00 €");
    const footer = within(screen.getByRole("table", { name: "Competenze" })).getAllByRole("row").at(-1)!;
    expect(footer).toHaveTextContent("Totale2.000,00 €");
  });

  it("saves a correction typed in Italian format as a number", async () => {
    const server = serve(inconsistent);
    server.on("PATCH", "/payslips/d1/fields", {
      body: { ...inconsistent, status: "done", net_pay: "1571.00", extraction: { ...inconsistent.extraction, issues: [] } },
    });
    renderApp("/documenti/d1");
    const input = await screen.findByLabelText("Netto");
    expect(input).toHaveValue("1.900,00");
    await userEvent.clear(input);
    await userEvent.type(input, "1.571,00");
    await userEvent.click(screen.getByRole("button", { name: "Salva correzioni" }));
    expect(await screen.findByText("Correzioni salvate.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ fields: { net_pay: 1571 } });
    expect(screen.getByText("Verificato")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Da correggere" })).not.toBeInTheDocument();
    // la lista condivisa viene ricaricata (contatore «Da controllare» aggiornato)
    expect(server.calls.filter((c) => c.method === "GET" && c.path === "/payslips").length).toBeGreaterThanOrEqual(2);
  });

  it("refuses a value that is not an amount without calling the API", async () => {
    const server = serve(inconsistent);
    renderApp("/documenti/d1");
    const input = await screen.findByLabelText("Netto");
    await userEvent.clear(input);
    await userEvent.type(input, "millenovecento");
    await userEvent.click(screen.getByRole("button", { name: "Salva correzioni" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("non è un importo");
    expect(server.calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("shows the API rejection of a correction", async () => {
    const server = serve(inconsistent);
    server.on("PATCH", "/payslips/d1/fields", { status: 422, body: { detail: "Correzione non valida: net_pay" } });
    renderApp("/documenti/d1");
    await userEvent.click(await screen.findByRole("button", { name: "Salva correzioni" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Correzione non valida: net_pay");
  });

  it("asks the LLM when a provider is ready", async () => {
    const server = serve(inconsistent);
    server.on("POST", "/payslips/d1/llm-resolve", { body: { ...inconsistent, status: "done", extraction: { ...inconsistent.extraction, issues: [] } } });
    renderApp("/documenti/d1");
    const button = await screen.findByRole("button", { name: "Chiedi all'LLM" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByText(/Campi compilati dall'LLM/)).toBeInTheDocument();
    expect(server.calls.some((c) => c.path === "/payslips/d1/llm-resolve")).toBe(true);
    // il documento restituito dall'LLM sostituisce quello mostrato
    expect(screen.getByText("Verificato")).toBeInTheDocument();
    expect(screen.queryByText("Lordo − trattenute non combacia con il netto")).not.toBeInTheDocument();
  });

  it("disables the LLM and explains why when no provider is ready", async () => {
    serve(inconsistent, NOT_READY_LLM);
    renderApp("/documenti/d1");
    const button = await screen.findByRole("button", { name: "Chiedi all'LLM" });
    expect(await screen.findByText(/Nessun provider LLM configurato/)).toBeInTheDocument();
    expect(button).toBeDisabled();
    const hint = document.getElementById("llm-hint")!;
    expect(within(hint).getByRole("link", { name: "Impostazioni" })).toHaveAttribute("href", "/impostazioni");
  });

  it("reprocesses a failed document and follows it until it is done", async () => {
    const failed = makeDetail({ id: "f1", status: "failed", error: "Errore durante l'elaborazione del documento" });
    const server = fakeApi();
    let state: DocumentDetail = failed;
    server.on("GET", "/payslips", () => ({ body: [state] }));
    server.on("GET", "/payslips/f1", () => ({ body: state }));
    server.on("GET", "/settings", { body: READY_LLM });
    server.on("POST", "/payslips/f1/reprocess", () => {
      state = { ...failed, status: "processing", error: null };
      setTimeout(() => (state = { ...failed, status: "done", error: null }), 100);
      return { body: state };
    });
    renderApp("/documenti/f1");
    expect(await screen.findByText("Errore durante l'elaborazione del documento")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Rielabora il PDF" }));
    expect(await screen.findByText(/Lettura del PDF in corso/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByText("Verificato").length).toBeGreaterThan(0), { timeout: 4000 });
    // finita l'elaborazione il dettaglio smette di interrogare l'API
    const detailCalls = () => server.calls.filter((c) => c.path === "/payslips/f1").length;
    const settled = detailCalls();
    await new Promise((r) => setTimeout(r, 2 * 2000 + 300));
    expect(detailCalls()).toBe(settled);
  }, 12_000);

  it("shows the saving state and allows a retry after a rejection", async () => {
    const server = serve(inconsistent);
    const first = deferred({ status: 422, body: { detail: "Correzione non valida: net_pay" } });
    let patches = 0;
    server.on("PATCH", "/payslips/d1/fields", () => (++patches === 1 ? first.handler() : { status: 422, body: { detail: "ancora no" } }));
    renderApp("/documenti/d1");
    await userEvent.click(await screen.findByRole("button", { name: "Salva correzioni" }));
    expect(screen.getByRole("button", { name: "Salvataggio…" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Chiedi all'LLM" })).toBeDisabled();
    first.release();
    expect(await screen.findByRole("alert")).toHaveTextContent("Correzione non valida: net_pay");
    await userEvent.click(screen.getByRole("button", { name: "Salva correzioni" }));
    expect(await screen.findByText("ancora no")).toBeInTheDocument();
    expect(patches).toBe(2);
  });

  it("refuses an all-empty correction without calling the API", async () => {
    const server = serve(inconsistent);
    renderApp("/documenti/d1");
    await userEvent.clear(await screen.findByLabelText("Netto"));
    await userEvent.click(screen.getByRole("button", { name: "Salva correzioni" }));
    expect(await screen.findByText("Inserisci almeno un valore da correggere.")).toBeInTheDocument();
    expect(server.calls.some((c) => c.method === "PATCH")).toBe(false);
  });

  it("sends only the fields that were filled in", async () => {
    const twoFields = makeDetail({
      id: "d2",
      status: "needs_review",
      extraction: {
        fields: { net_pay: { value: 1900, confidence: 0.3 }, gross_pay: { value: 2005, confidence: 0.3 } },
        issues: [
          { field: "net_pay", check: "net_consistency", message: "netto", action: "user" },
          { field: "gross_pay", check: "missing_field", message: "lordo", action: "llm" },
        ],
      },
    });
    const server = serve(twoFields);
    server.on("PATCH", "/payslips/d2/fields", { body: twoFields });
    renderApp("/documenti/d2");
    await userEvent.clear(await screen.findByLabelText("Lordo"));
    await userEvent.click(screen.getByRole("button", { name: "Salva correzioni" }));
    await screen.findByText("Correzioni salvate.");
    expect(server.calls.find((c) => c.method === "PATCH")?.body).toEqual({ fields: { net_pay: 1900 } });
  });

  it("explains a missing document", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    server.on("GET", "/settings", { body: READY_LLM });
    server.on("GET", "/payslips/nope", { status: 404, body: { detail: "Documento non trovato" } });
    renderApp("/documenti/nope");
    expect(await screen.findByRole("alert")).toHaveTextContent("Documento non trovato");
  });
});

describe("DocumentPage reprocess in flight", () => {
  it("cannot start a second reprocess while the first is being sent", async () => {
    const failed = makeDetail({ id: "r1", status: "failed" });
    const server = fakeApi();
    const slow = deferred({ body: { ...failed, status: "pending" } });
    server.on("GET", "/payslips", { body: [failed] });
    server.on("GET", "/payslips/r1", { body: failed });
    server.on("GET", "/settings", { body: READY_LLM });
    server.on("POST", "/payslips/r1/reprocess", slow.handler);
    renderApp("/documenti/r1");
    await userEvent.click(await screen.findByRole("button", { name: "Rielabora il PDF" }));
    const busy = screen.getByRole("button", { name: "Rielaborazione…" });
    expect(busy).toBeDisabled();
    await userEvent.click(busy);
    slow.release();
    await screen.findByRole("button", { name: "Rielabora il PDF" });
    expect(server.calls.filter((c) => c.path === "/payslips/r1/reprocess")).toHaveLength(1);
  });

  it("shows the Fisco block with the month and the year-to-date figures", async () => {
    serve(makeDetail({ id: "f1" }));
    renderApp("/documenti/f1");
    const fisco = await screen.findByRole("region", { name: "Fisco" });
    expect(within(fisco).getByText("1.820,74 €")).toBeInTheDocument();
    expect(within(fisco).getByText("8.950,00 €")).toBeInTheDocument();
    expect(within(fisco).getByText("IRPEF pagata da inizio anno")).toBeInTheDocument();
  });

  it("hides the Fisco block when no fiscal figure was read", async () => {
    serve(makeDetail({ id: "f2", extraction: { fields: {}, issues: [], pages: ["cedolino"] } }));
    renderApp("/documenti/f2");
    await screen.findByRole("heading", { name: "Aprile 2026" });
    expect(screen.queryByRole("region", { name: "Fisco" })).not.toBeInTheDocument();
  });

  it("shows year, point 1 and point 21 of a CU instead of gross and net", async () => {
    serve(
      makeDetail({
        id: "c1",
        doc_type: "cu",
        gross_pay: null,
        net_pay: null,
        total_deductions: null,
        period_month: null,
      }),
    );
    renderApp("/documenti/c1");
    expect(await screen.findByText("Imponibile IRPEF (punto 1)")).toBeInTheDocument();
    expect(screen.getByText("IRPEF trattenuta (punto 21)")).toBeInTheDocument();
    expect(screen.getByText("1.820,74 €")).toBeInTheDocument();
    expect(screen.queryByText("Netto")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Fisco" })).not.toBeInTheDocument();
  });

  it("lists the copy pages of a CU", async () => {
    const base = makeDetail({ id: "c2", doc_type: "cu" });
    serve({ ...base, extraction: { ...base.extraction!, pages: ["cu", "cu", "copia"] } });
    renderApp("/documenti/c2");
    expect(await screen.findByText("3 (cu, cu, copia)")).toBeInTheDocument();
  });
});
