import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { YearSummary } from "../api";
import { fakeApi, makeDoc, renderApp } from "../test/helpers";

function makeYear(overrides: Partial<YearSummary> = {}): YearSummary {
  return {
    year: 2025,
    employer_tax_code: "01234567890",
    template: "ranocchi",
    payslips: [
      { id: "p11", month: 11, additional_payment: false },
      { id: "p12", month: 12, additional_payment: false },
    ],
    missing_months: [],
    duplicates: [],
    to_review: [],
    totals: {
      gross_pay: "4000.00",
      net_pay: "3100.50",
      total_deductions: "899.50",
      taxable_income: "3600.00",
      income_tax: null,
    },
    completeness: { status: "complete", taxable_diff: null, tax_diff: null },
    cu: { id: "cu1", status: "match", taxable_diff: "0.00", tax_diff: "0.00" },
    ...overrides,
  };
}

function setup(years: YearSummary[], docs = [makeDoc()]) {
  const server = fakeApi();
  server.on("GET", "/payslips", { body: docs });
  server.on("GET", "/years", { body: years });
  renderApp("/anni");
  return server;
}

describe("YearsPage", () => {
  it("invites to upload when there is nothing to show", async () => {
    setup([]);
    expect(
      await screen.findByText("Nessun anno da mostrare: carica i cedolini per vedere totali e verifiche."),
    ).toBeInTheDocument();
  });

  it("shows the card with heading, month links, totals and a matching CU", async () => {
    setup([makeYear()]);
    expect(await screen.findByRole("heading", { name: "2025 · Ranocchi · datore 01234567890" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "nov" })).toHaveAttribute("href", "/documenti/p11");
    expect(screen.getByRole("link", { name: "dic" })).toHaveAttribute("href", "/documenti/p12");
    expect(screen.getByText("3.100,50 €")).toBeInTheDocument();
    expect(screen.queryByText("IRPEF trattenuta")).not.toBeInTheDocument();
    expect(screen.getByText("somma dei cedolini caricati")).toBeInTheDocument();
    expect(screen.getByText("Cedolini completi: le somme dei mesi tornano con i progressivi")).toBeInTheDocument();
    expect(screen.getByText("La CU combacia con i progressivi del cedolino di dicembre")).toBeInTheDocument();
  });

  it("reports the differences of a mismatching CU with a link to it", async () => {
    setup([makeYear({ cu: { id: "cu1", status: "mismatch", taxable_diff: "-123.41", tax_diff: "35.50" } })]);
    const notice = await screen.findByRole("alert");
    expect(notice).toHaveTextContent("La CU non combacia: imponibile -123,41 €, IRPEF 35,50 €");
    expect(within(notice).getByRole("link", { name: "Apri la CU" })).toHaveAttribute("href", "/documenti/cu1");
  });

  it("treats a missing CU as optional, not as an error", async () => {
    setup([makeYear({ cu: null })]);
    expect(
      await screen.findByText("Nessuna CU per quest'anno: è facoltativa, puoi caricarla da Panoramica"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("compresses consecutive missing months", async () => {
    setup([makeYear({ missing_months: [1, 2, 3, 4, 5, 6, 7, 8, 10] })]);
    expect(
      await screen.findByText("Mancano gen–ago, ott: carica i cedolini per completare l'anno"),
    ).toBeInTheDocument();
  });

  it("explains the gap when the payslips are incomplete", async () => {
    setup([makeYear({ completeness: { status: "incomplete", taxable_diff: "1500.00", tax_diff: "300.00" } })]);
    expect(
      await screen.findByText(
        "Mancano cedolini: rispetto ai progressivi mancano 1.500,00 € di imponibile e 300,00 € di IRPEF",
      ),
    ).toBeInTheDocument();
  });

  it("lists duplicates and documents to review by period", async () => {
    const dup = makeDoc({ id: "d1", period_month: 3, period_year: 2025 });
    setup([makeYear({ duplicates: ["d1"], to_review: ["zz"] })], [dup]);
    expect(await screen.findByText(/Caricati due volte, conta il più recente:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Marzo 2025" })).toHaveAttribute("href", "/documenti/d1");
    expect(screen.getByText(/Da controllare, esclusi dai conti:/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "documento" })).toHaveAttribute("href", "/documenti/zz");
  });

  it("a CU without payslips shows neither totals nor a payslip diagnosis", async () => {
    const empty = { gross_pay: null, net_pay: null, total_deductions: null, taxable_income: null, income_tax: null };
    setup([
      makeYear({
        template: null,
        payslips: [],
        totals: empty,
        completeness: { status: "no_fiscal_data", taxable_diff: null, tax_diff: null },
        cu: { id: "cu1", status: "no_payslips", taxable_diff: null, tax_diff: null },
      }),
    ]);
    expect(await screen.findByText("Nessun cedolino di quest'anno da confrontare con la CU")).toBeInTheDocument();
    expect(screen.queryByText("somma dei cedolini caricati")).not.toBeInTheDocument();
    expect(screen.queryByText(/rielaborali/)).not.toBeInTheDocument();
  });

  it("labels December's additional payment as the 13th, the others by month", async () => {
    setup([
      makeYear({
        payslips: [
          { id: "p06", month: 6, additional_payment: true },
          { id: "p12", month: 12, additional_payment: false },
          { id: "p13", month: 12, additional_payment: true },
        ],
      }),
    ]);
    expect(await screen.findByRole("link", { name: "+ 13ª" })).toHaveAttribute("href", "/documenti/p13");
    expect(screen.getByRole("link", { name: "+ agg. giu" })).toHaveAttribute("href", "/documenti/p06");
  });

  it("says only once that the payslips lack the fiscal data", async () => {
    setup([
      makeYear({
        completeness: { status: "no_fiscal_data", taxable_diff: null, tax_diff: null },
        cu: { id: "cu1", status: "no_fiscal_data", taxable_diff: null, tax_diff: null },
      }),
    ]);
    expect(await screen.findAllByText("I cedolini non hanno i dati fiscali: rielaborali")).toHaveLength(1);
  });

  it("is reachable from the navigation", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    server.on("GET", "/years", { body: [makeYear()] });
    renderApp("/documenti");
    await userEvent.click(await screen.findByRole("link", { name: "Anni" }));
    expect(await screen.findByRole("heading", { level: 1, name: "Anni" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /2025 · Ranocchi/ })).toBeInTheDocument();
  });
});
