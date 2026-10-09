import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fakeApi, makeDoc, renderApp } from "../test/helpers";

describe("DocumentsPage", () => {
  it("lists documents newest first with formatted amounts, links and status", async () => {
    const march = makeDoc({ id: "m", period_month: 3, net_pay: "1185.00", filename: "marzo.pdf" });
    const june = makeDoc({ id: "g", period_month: 6, net_pay: "1900.00", status: "needs_review" });
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [march, june] });
    renderApp("/documenti");
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => within(r).getAllByRole("cell")[0]!.textContent)).toEqual(["Giugno 2026", "Marzo 2026"]);
    expect(within(rows[0]!).getByText("1.900,00 €")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("Da controllare")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("marzo.pdf")).toBeInTheDocument();
    expect(within(rows[1]!).getByRole("link", { name: "Marzo 2026" })).toHaveAttribute("href", "/documenti/m");
  });

  it("invites to upload when the list is empty", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    renderApp("/documenti");
    expect(await screen.findByText("Nessun documento: caricane uno qui sotto.")).toBeInTheDocument();
  });
});
