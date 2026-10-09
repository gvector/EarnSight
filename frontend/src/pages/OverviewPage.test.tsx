import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeApi, makeDoc, renderApp } from "../test/helpers";
import { receivedSentence } from "./OverviewPage";

describe("receivedSentence", () => {
  it("uses «Ad» before a vowel and names the additional month", () => {
    expect(receivedSentence(makeDoc({ period_month: 8, period_year: 2026 }))).toBe("Ad agosto 2026 hai ricevuto");
    expect(receivedSentence(makeDoc({ period_month: 3, period_year: 2026 }))).toBe("A marzo 2026 hai ricevuto");
    expect(receivedSentence(makeDoc({ period_month: 6, additional_payment: true }))).toBe(
      "Con la mensilità aggiuntiva di giugno 2026 hai ricevuto",
    );
  });
});

describe("OverviewPage", () => {
  const march = makeDoc({ period_month: 3, net_pay: "1185.00" });
  const june = makeDoc({ period_month: 6, net_pay: "1900.00" });
  const extra = makeDoc({ period_month: 6, net_pay: "642.00", additional_payment: true });
  const cu = makeDoc({ doc_type: "cu", period_month: null, period_year: 2025, net_pay: "20000.00" });
  const failed = makeDoc({ period_month: 7, status: "failed", net_pay: null });

  // Testing Library normalizza gli spazi: l'NBSP prima dell'€ si confronta come spazio
  it("shows the latest regular-or-additional payslip and ignores CU and failed documents", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [march, failed, cu, june, extra] });
    renderApp("/");
    const hero = await screen.findByRole("region", { name: "Netto ricevuto" });
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(/hai ricevuto$/);
    // l'ultimo periodo è giugno: la 14ª viene dopo l'ordinaria dello stesso mese
    expect(within(hero).getByText("Con la mensilità aggiuntiva di giugno 2026 hai ricevuto")).toBeInTheDocument();
    expect(within(hero).getByText("642,00 €")).toBeInTheDocument();
    expect(within(hero).getAllByRole("button")).toHaveLength(3); // marzo, giugno, 14ª: niente CU
  });

  it("switches the sentence when a bar is chosen", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [march, june, extra] });
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: /^marzo 2026/ }));
    expect(screen.getByText("A marzo 2026 hai ricevuto")).toBeInTheDocument();
    expect(screen.getByText("1.185,00 €", { selector: ".hero-amount" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^marzo 2026/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("invites to upload when there are no documents", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Benvenuto in EarnSight" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Carica" })).toBeDisabled();
  });

  it("shows the API error instead of an empty page", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { status: 500, body: { detail: "Database non raggiungibile" } });
    renderApp("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Database non raggiungibile");
  });

  it("gives distinct names to two bars of the same month with the same net", async () => {
    const server = fakeApi();
    const a = makeDoc({ period_month: 12, net_pay: "1530.00", additional_payment: true, filename: "tredicesima.pdf" });
    const b = makeDoc({ period_month: 12, net_pay: "1530.00", additional_payment: true, filename: "quattordicesima.pdf" });
    server.on("GET", "/payslips", { body: [a, b, march] });
    renderApp("/");
    expect(await screen.findByRole("button", { name: /tredicesima\.pdf/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /quattordicesima\.pdf/ })).toBeInTheDocument();
  });
});
