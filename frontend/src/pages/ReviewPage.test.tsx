import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { fakeApi, makeDoc, renderApp } from "../test/helpers";

describe("ReviewPage", () => {
  it("lists only the documents that need attention, each with what to do", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", {
      body: [
        makeDoc({ period_month: 7, status: "done" }),
        makeDoc({ period_month: 5, status: "needs_review" }),
        makeDoc({ period_month: 4, status: "failed" }),
      ],
    });
    renderApp("/da-controllare");
    expect(await screen.findByRole("link", { name: "Maggio 2026" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Aprile 2026" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Luglio 2026" })).not.toBeInTheDocument();
    expect(screen.getByText(/I conti non tornano/)).toBeInTheDocument();
    expect(screen.getByText(/La lettura del PDF non è riuscita/)).toBeInTheDocument();
  });

  it("says when everything is verified", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [makeDoc()] });
    renderApp("/da-controllare");
    expect(await screen.findByText(/Tutti i documenti sono verificati/)).toBeInTheDocument();
  });
});
