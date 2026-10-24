"""Richieste dei gateway LLM: cosa parte davvero verso il provider."""

from app.services.llm import gateway as gateway_module
from app.services.llm.gateway import OllamaGateway


class _Response:
    def raise_for_status(self):
        return None

    def json(self):
        return {"message": {"content": '{"fields": {}}'}}


def test_ollama_context_window_fits_the_prompt(monkeypatch):
    """Il prompt arriva a ~12.000 caratteri di testo: con il contesto di default di
    Ollama (2048-4096 token, secondo la versione) l'inizio, cioè le istruzioni, veniva
    troncato in silenzio. num_ctx esplicito e abbastanza grande per l'intero prompt."""
    sent = {}

    def fake_post(url, json, timeout):  # noqa: A002 — stessa firma di httpx.post
        sent.update(json)
        return _Response()

    monkeypatch.setattr(gateway_module.httpx, "post", fake_post)
    gw = OllamaGateway(base_url="http://ollama:11434", model="llama3.1:8b")
    # testo di un cedolino: numeri e punteggiatura, il caso peggiore per il tokenizer
    gw.resolve_fields("1.234,56 7,89 % 12/2025 " * 1_000, ["net_pay"], [])

    prompt_chars = sum(len(m["content"]) for m in sent["messages"])
    # 1,5 caratteri per token: prudente per testo così fitto; 1024 token per la risposta
    assert sent["options"]["num_ctx"] >= prompt_chars / 1.5 + 1024
