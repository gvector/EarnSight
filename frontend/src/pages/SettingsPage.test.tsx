import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { fakeApi, NOT_READY_LLM, READY_LLM, renderApp } from "../test/helpers";

function serve(settings = NOT_READY_LLM) {
  const server = fakeApi();
  server.on("GET", "/payslips", { body: [] });
  server.on("GET", "/settings", { body: settings });
  return server;
}

describe("SettingsPage", () => {
  it("says why the LLM is not ready", async () => {
    serve();
    renderApp("/impostazioni");
    expect(await screen.findByText(/Nessun provider LLM configurato/)).toBeInTheDocument();
  });

  it("saves OpenAI with a new key and shows the new state", async () => {
    const server = serve();
    server.on("PUT", "/settings", {
      body: { ...READY_LLM, llm_provider: "openai", openai_api_key_set: true, llm_detail: "openai · impostazioni utente" },
    });
    renderApp("/impostazioni");
    await userEvent.click(await screen.findByLabelText("OpenAI"));
    await userEvent.type(screen.getByLabelText("API key"), "  sk-nuova  ");
    await userEvent.click(screen.getByRole("button", { name: "Salva impostazioni" }));
    expect(await screen.findByText("Impostazioni salvate.")).toBeInTheDocument();
    expect(screen.getByText("LLM pronto: openai · impostazioni utente.")).toBeInTheDocument();
    const sent = server.calls.find((c) => c.method === "PUT")?.body as Record<string, unknown>;
    expect(sent).toMatchObject({ llm_provider: "openai", openai_api_key: "sk-nuova" });
    expect(screen.getByLabelText("API key")).toHaveValue(""); // la chiave non resta nel campo
  });

  it("keeps the saved key when the field is left empty", async () => {
    const server = serve({ ...READY_LLM, llm_provider: "openai", openai_api_key_set: true });
    server.on("PUT", "/settings", { body: { ...READY_LLM, llm_provider: "openai", openai_api_key_set: true } });
    renderApp("/impostazioni");
    await userEvent.click(await screen.findByRole("button", { name: "Salva impostazioni" }));
    await screen.findByText("Impostazioni salvate.");
    expect(server.calls.find((c) => c.method === "PUT")?.body).not.toHaveProperty("openai_api_key");
  });

  it("removes the saved key", async () => {
    const server = serve({ ...READY_LLM, llm_provider: "openai", openai_api_key_set: true });
    server.on("PUT", "/settings", { body: { ...NOT_READY_LLM, llm_provider: "openai" } });
    renderApp("/impostazioni");
    await userEvent.click(await screen.findByRole("button", { name: "Rimuovi la chiave salvata" }));
    expect(await screen.findByText("Chiave rimossa.")).toBeInTheDocument();
    expect(server.calls.find((c) => c.method === "PUT")?.body).toMatchObject({ openai_api_key: "" });
    expect(screen.queryByRole("button", { name: "Rimuovi la chiave salvata" })).not.toBeInTheDocument();
  });

  it("saves the Ollama address and model, keeping the other provider's model", async () => {
    const server = serve();
    server.on("PUT", "/settings", { body: READY_LLM });
    renderApp("/impostazioni");
    await userEvent.click(await screen.findByLabelText("Ollama, sul tuo computer"));
    const url = screen.getByLabelText("Indirizzo di Ollama");
    await userEvent.clear(url);
    await userEvent.type(url, "http://ollama:11434");
    const model = screen.getByLabelText("Modello");
    await userEvent.clear(model);
    await userEvent.type(model, "qwen3:8b");
    await userEvent.click(screen.getByRole("button", { name: "Salva impostazioni" }));
    await screen.findByText("Impostazioni salvate.");
    expect(server.calls.find((c) => c.method === "PUT")?.body).toEqual({
      llm_provider: "ollama",
      ollama_base_url: "http://ollama:11434",
      ollama_model: "qwen3:8b",
      openai_model: NOT_READY_LLM.openai_model,
    });
  });

  it("shows a save error and lets the user try again", async () => {
    const server = serve();
    let puts = 0;
    server.on("PUT", "/settings", () => (++puts === 1 ? { status: 500, body: { detail: "Database non raggiungibile" } } : { body: READY_LLM }));
    renderApp("/impostazioni");
    await userEvent.click(await screen.findByRole("button", { name: "Salva impostazioni" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Database non raggiungibile");
    await userEvent.click(screen.getByRole("button", { name: "Salva impostazioni" }));
    expect(await screen.findByText("Impostazioni salvate.")).toBeInTheDocument();
    expect(puts).toBe(2);
  });
});
