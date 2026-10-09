// Impostazioni: quale LLM usare per compilare i campi segnalati, e se è pronto.
import { useEffect, useState, type FormEvent } from "react";
import { api, type LlmSettings, type LlmSettingsInput } from "../api";
import { Notice } from "../components/ui";

type Provider = "" | "ollama" | "openai";

export function SettingsPage() {
  const [saved, setSaved] = useState<LlmSettings | null>(null);
  const [provider, setProvider] = useState<Provider>("");
  const [ollamaUrl, setOllamaUrl] = useState("");
  const [ollamaModel, setOllamaModel] = useState("");
  const [openaiModel, setOpenaiModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const show = (s: LlmSettings) => {
    setSaved(s);
    setProvider((s.llm_provider ?? "") as Provider);
    setOllamaUrl(s.ollama_base_url ?? "");
    setOllamaModel(s.ollama_model ?? "");
    setOpenaiModel(s.openai_model ?? "");
    setApiKey("");
  };

  useEffect(() => {
    api.getSettings().then(show, (e: Error) => setError(e.message));
  }, []);

  const submit = async (input: LlmSettingsInput, done: string) => {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      show(await api.saveSettings(input));
      setMessage(done);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const base = (): LlmSettingsInput => ({
    llm_provider: provider,
    ollama_base_url: provider === "ollama" ? ollamaUrl : saved?.ollama_base_url,
    ollama_model: provider === "ollama" ? ollamaModel : saved?.ollama_model,
    openai_model: provider === "openai" ? openaiModel : saved?.openai_model,
  });

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    const input = base();
    if (provider === "openai" && apiKey.trim()) input.openai_api_key = apiKey.trim();
    void submit(input, "Impostazioni salvate.");
  };

  if (!saved) return error ? <Notice tone="error">{error}</Notice> : <p className="muted">Caricamento…</p>;

  return (
    <>
      <h1>Impostazioni</h1>
      <p className="lead">
        Quando un cedolino ha campi mancanti o incoerenti puoi chiedere a un LLM di compilarli. Con Ollama tutto
        resta sul tuo computer; con OpenAI il testo del cedolino viene inviato a OpenAI.
      </p>

      <Notice tone={saved.llm_ready ? "ok" : "warn"}>
        {saved.llm_ready ? `LLM pronto: ${saved.llm_detail}.` : saved.llm_detail}
      </Notice>

      <form className="panel settings" onSubmit={onSubmit}>
        <fieldset className="choice">
          <legend>LLM da usare</legend>
          {(
            [
              ["", "Nessuno"],
              ["ollama", "Ollama, sul tuo computer"],
              ["openai", "OpenAI"],
            ] as const
          ).map(([value, label]) => (
            <label key={value}>
              <input type="radio" name="provider" checked={provider === value} onChange={() => setProvider(value)} />
              {label}
            </label>
          ))}
        </fieldset>

        {provider === "ollama" && (
          <div className="field-grid">
            <label className="field">
              <span>Indirizzo di Ollama</span>
              <input value={ollamaUrl} onChange={(e) => setOllamaUrl(e.target.value)} />
            </label>
            <label className="field">
              <span>Modello</span>
              <input value={ollamaModel} onChange={(e) => setOllamaModel(e.target.value)} />
            </label>
          </div>
        )}

        {provider === "openai" && (
          <div className="field-grid">
            <label className="field">
              <span>Modello</span>
              <input value={openaiModel} onChange={(e) => setOpenaiModel(e.target.value)} />
            </label>
            <label className="field">
              <span>API key</span>
              <input
                type="password"
                autoComplete="off"
                value={apiKey}
                placeholder={saved.openai_api_key_set ? "Chiave salvata: lascia vuoto per tenerla" : "sk-…"}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </label>
          </div>
        )}

        {message && <Notice tone="ok">{message}</Notice>}
        {error && <Notice tone="error">{error}</Notice>}

        <div className="actions">
          <button type="submit" className="button button-primary" disabled={busy}>
            Salva impostazioni
          </button>
          {saved.openai_api_key_set && (
            <button
              type="button"
              className="button"
              disabled={busy}
              onClick={() => void submit({ ...base(), openai_api_key: "" }, "Chiave rimossa.")}
            >
              Rimuovi la chiave salvata
            </button>
          )}
        </div>
      </form>
    </>
  );
}
