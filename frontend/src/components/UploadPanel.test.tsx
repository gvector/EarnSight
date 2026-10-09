import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeApi, renderApp } from "../test/helpers";

const pdf = (name: string) => new File(["%PDF-1.7"], name, { type: "application/pdf" });

describe("UploadPanel", () => {
  it("uploads every chosen file with the chosen type and reports partial failures", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    server.on("POST", "/payslips/upload", ({ body }) => {
      const file = (body as FormData).get("file") as File;
      return file.name === "rotto.pdf"
        ? { status: 400, body: { detail: "Il file non è un PDF valido" } }
        : { status: 201, body: {} };
    });
    renderApp("/documenti");
    const input = await screen.findByLabelText("Scegli i PDF da caricare");
    await userEvent.upload(input, [pdf("a.pdf"), pdf("rotto.pdf"), pdf("b.pdf")]);
    expect(screen.getByText(/3 file pronti/)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("Certificazione Unica"));
    await userEvent.click(screen.getByRole("button", { name: "Carica" }));

    expect(await screen.findByText(/2 documenti caricati/)).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("rotto.pdf: Il file non è un PDF valido");
    const uploads = server.calls.filter((c) => c.path === "/payslips/upload");
    expect(uploads).toHaveLength(3);
    expect(uploads.every((c) => (c.body as FormData).get("doc_type") === "cu")).toBe(true);
    // il selettore si svuota: un secondo clic non ricarica gli stessi file
    expect(screen.getByRole("button", { name: "Carica" })).toBeDisabled();
    expect(server.calls.filter((c) => c.path === "/payslips").length).toBeGreaterThanOrEqual(2); // lista ricaricata
  });
});

describe("UploadPanel edge cases", () => {
  it("clears the file input so the same file can be chosen again after an upload", async () => {
    const server = fakeApi();
    server.on("GET", "/payslips", { body: [] });
    server.on("POST", "/payslips/upload", { status: 201, body: {} });
    renderApp("/documenti");
    const input = await screen.findByLabelText("Scegli i PDF da caricare");
    await userEvent.upload(input, pdf("a.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Carica" }));
    await screen.findByText(/1 documento caricato/);
    expect(input).toHaveValue("");
    await userEvent.upload(input, pdf("a.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Carica" }));
    await screen.findByText(/1 documento caricato/);
    expect(server.calls.filter((c) => c.path === "/payslips/upload")).toHaveLength(2);
  });

  it("cannot be submitted twice while uploading", async () => {
    const { deferred } = await import("../test/helpers");
    const server = fakeApi();
    const slow = deferred({ status: 201, body: {} });
    server.on("GET", "/payslips", { body: [] });
    server.on("POST", "/payslips/upload", slow.handler);
    renderApp("/documenti");
    await userEvent.upload(await screen.findByLabelText("Scegli i PDF da caricare"), pdf("a.pdf"));
    await userEvent.click(screen.getByRole("button", { name: "Carica" }));
    const busy = screen.getByRole("button", { name: "Caricamento…" });
    expect(busy).toBeDisabled();
    await userEvent.click(busy);
    slow.release();
    await screen.findByText(/1 documento caricato/);
    expect(server.calls.filter((c) => c.path === "/payslips/upload")).toHaveLength(1);
  });
});
