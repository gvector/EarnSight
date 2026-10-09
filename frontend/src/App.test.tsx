import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeApi, makeDoc, renderApp } from "./test/helpers";

describe("session and routing", () => {
  it("sends a visitor without a session to the login page", async () => {
    fakeApi();
    renderApp("/documenti", { loggedIn: false });
    expect(await screen.findByRole("button", { name: "Accedi" })).toBeInTheDocument();
  });

  it("logs in, keeps the token for the tab and returns to the requested page", async () => {
    const server = fakeApi();
    server.on("POST", "/auth/login", { body: { access_token: "nuovo" } });
    server.on("GET", "/payslips", { body: [] });
    renderApp("/documenti", { loggedIn: false });
    await userEvent.type(await screen.findByLabelText("Nome utente"), "admin");
    await userEvent.type(screen.getByLabelText("Password"), "segreta");
    await userEvent.click(screen.getByRole("button", { name: "Accedi" }));
    expect(await screen.findByRole("heading", { name: "Documenti" })).toBeInTheDocument();
    expect(sessionStorage.getItem("earnsight.token")).toBe("nuovo");
  });

  it("shows the API message on wrong credentials", async () => {
    const server = fakeApi();
    server.on("POST", "/auth/login", { status: 401, body: { detail: "Username o password non validi" } });
    renderApp("/", { loggedIn: false });
    await userEvent.type(await screen.findByLabelText("Nome utente"), "admin");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Accedi" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Username o password non validi");
  });

  it("returns to the login page when the token expires", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { status: 401, body: { detail: "Credenziali non valide" } });
    renderApp("/");
    expect(await screen.findByRole("button", { name: "Accedi" })).toBeInTheDocument();
    expect(sessionStorage.getItem("earnsight.token")).toBeNull();
  });

  it("logs out", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Esci" }));
    expect(await screen.findByRole("button", { name: "Accedi" })).toBeInTheDocument();
    expect(sessionStorage.getItem("earnsight.token")).toBeNull();
  });

  it("counts the documents that need attention in the navigation", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", {
      body: [makeDoc({ status: "needs_review" }), makeDoc({ status: "failed" }), makeDoc()],
    });
    renderApp("/");
    expect(await screen.findByLabelText("2 da controllare")).toBeInTheDocument();
  });

  it("lists what to do for each document that needs attention", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [makeDoc({ status: "needs_ocr", period_month: 3 })] });
    renderApp("/da-controllare");
    expect(await screen.findByText(/scansione senza testo/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Marzo 2026" })).toBeInTheDocument();
  });

  it("polls while a document is being processed", async () => {
    const server = fakeApi();
    let calls = 0;
    server.on("GET", "/payslips", () => {
      calls += 1;
      return { body: [makeDoc({ id: "p", status: calls < 2 ? "processing" : "done" })] };
    });
    renderApp("/documenti");
    await waitFor(() => expect(screen.getByText("Verificato")).toBeInTheDocument(), { timeout: 4000 });
    expect(calls).toBeGreaterThanOrEqual(2);
  });
});

describe("polling", () => {
  it("polls a freshly uploaded (pending) document and stops once nothing is busy", async () => {
    const server = fakeApi();
    let calls = 0;
    server.on("GET", "/payslips", () => {
      calls += 1;
      return { body: [makeDoc({ id: "p", status: calls < 2 ? "pending" : "done" })] };
    });
    renderApp("/documenti");
    expect(await screen.findByText("In coda")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("Verificato")).toBeInTheDocument(), { timeout: 4000 });
    const settled = calls;
    await new Promise((r) => setTimeout(r, 2 * 2000 + 300));
    expect(calls).toBe(settled);
  }, 10_000);
});

describe("login in flight", () => {
  it("disables the button while logging in and lets the user retry after a wrong password", async () => {
    const { deferred } = await import("./test/helpers");
    const server = fakeApi();
    const first = deferred({ status: 401, body: { detail: "Username o password non validi" } });
    let attempts = 0;
    server.on("POST", "/auth/login", () => (++attempts === 1 ? first.handler() : { body: { access_token: "ok" } }));
    server.on("GET", "/payslips", { body: [] });
    renderApp("/", { loggedIn: false });
    await userEvent.type(await screen.findByLabelText("Nome utente"), "admin");
    await userEvent.type(screen.getByLabelText("Password"), "x");
    await userEvent.click(screen.getByRole("button", { name: "Accedi" }));
    expect(screen.getByRole("button", { name: "Accesso…" })).toBeDisabled();
    first.release();
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Accedi" }));
    expect(await screen.findByRole("button", { name: "Esci" })).toBeInTheDocument();
    expect(attempts).toBe(2);
  });
});

describe("stale responses", () => {
  it("ignores an older list response that arrives after a newer one", async () => {
    const { deferred, makeDetail } = await import("./test/helpers");
    const server = fakeApi();
    const doc = makeDoc({ id: "s", status: "needs_review", period_month: 5 });
    const slowFirst = deferred({ body: [doc] }); // risposta vecchia: ancora da controllare
    let lists = 0;
    server.on("GET", "/payslips", () => (++lists === 1 ? slowFirst.handler() : { body: [{ ...doc, status: "done" }] }));
    server.on("GET", "/payslips/s", { body: makeDetail({ ...doc, status: "done" }) });
    server.on("GET", "/settings", { body: { llm_ready: false, llm_detail: "" } });
    server.on("POST", "/payslips/s/reprocess", { body: { ...doc, status: "done" } });
    renderApp("/documenti/s");
    // l'azione ricarica la lista (seconda richiesta, veloce) mentre la prima è ancora in volo
    await userEvent.click(await screen.findByRole("button", { name: "Rielabora il PDF" }));
    await waitFor(() => expect(lists).toBe(2));
    slowFirst.release();
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.queryByLabelText(/da controllare/)).not.toBeInTheDocument();
  });
});
