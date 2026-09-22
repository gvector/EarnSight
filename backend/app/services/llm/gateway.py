"""Gateway LLM pluggable (Ollama locale primario, OpenAI per il deploy online).

Usato in Fase 1 solo come fallback mirato: richiede all'LLM i valori dei campi
segnalati dalla validazione, mai una nuova estrazione completa.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import settings

_SYSTEM_PROMPT = (
    "Sei un estrattore di dati da cedolini paga italiani. Ti vengono forniti il "
    "testo del documento e i campi da recuperare con i relativi problemi. "
    "Rispondi SOLO con un oggetto JSON della forma "
    '{"fields": {"nome_campo": valore}} '
    "dove nome_campo è uno dei campi richiesti e valore è il valore corretto "
    "tratto dal testo (numeri come decimali con punto, es. 2250.00). "
    "Se un campo non è presente nel testo, non includerlo nella risposta."
)


class LlmUnavailable(RuntimeError):
    pass


class BaseGateway:
    name = "base"

    def resolve_fields(
        self, raw_text: str, field_names: list[str], issues: list[dict[str, Any]]
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _parse_response(self, content: str) -> dict[str, Any]:
        data = json.loads(content)
        fields = data.get("fields", {})
        return fields if isinstance(fields, dict) else {}

    def _build_prompt(self, raw_text: str, field_names: list[str], issues: list) -> str:
        issues_text = "\n".join(
            f"- {i.get('field') or 'documento'}: {i.get('message')}" for i in issues
        )
        return (
            f"Campi richiesti: {', '.join(field_names)}\n\n"
            f"Problemi rilevati dalla validazione:\n{issues_text}\n\n"
            f"Testo del documento:\n{raw_text[:12000]}"
        )


class OpenAiGateway(BaseGateway):
    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def resolve_fields(
        self, raw_text: str, field_names: list[str], issues: list[dict[str, Any]]
    ) -> dict[str, Any]:
        response = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_prompt(raw_text, field_names, issues)},
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=60,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return self._parse_response(content)


class OllamaGateway(BaseGateway):
    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    def resolve_fields(
        self, raw_text: str, field_names: list[str], issues: list[dict[str, Any]]
    ) -> dict[str, Any]:
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": self._build_prompt(raw_text, field_names, issues)},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
            },
            timeout=120,
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
        return self._parse_response(content)


def get_gateway() -> BaseGateway | None:
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAiGateway(settings.openai_api_key, settings.openai_model)
    if settings.llm_provider == "ollama":
        return OllamaGateway(settings.ollama_base_url, settings.ollama_model)
    return None


async def get_gateway_for_user(db, user) -> BaseGateway | None:  # noqa: ANN001
    """Gateway costruito dalle impostazioni dell'utente (DB), fallback env.

    L'API key OpenAI è cifrata a riposo e decifrata solo qui, alla
    costruzione dell'adapter.
    """
    from sqlalchemy import select

    from app.core.crypto import decrypt_secret
    from app.models.setting import AppSetting

    result = await db.execute(select(AppSetting).where(AppSetting.user_id == user.id))
    row = result.scalar_one_or_none()
    if row is None:
        return get_gateway()
    if row.llm_provider == "openai" and row.openai_api_key_encrypted:
        api_key = decrypt_secret(row.openai_api_key_encrypted)
        return OpenAiGateway(api_key, row.openai_model or settings.openai_model)
    if row.llm_provider == "ollama":
        return OllamaGateway(
            row.ollama_base_url or settings.ollama_base_url,
            row.ollama_model or settings.ollama_model,
        )
    return None
