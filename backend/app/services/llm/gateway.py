"""Gateway LLM pluggable (Ollama locale primario, OpenAI per il deploy online).

Usato in Fase 1 solo come fallback mirato: richiede all'LLM i valori dei campi
segnalati dalla validazione, mai una nuova estrazione completa.

The gateway abstracts the LLM provider behind a single interface
(``resolve_fields``) so callers never depend on Ollama or OpenAI directly.
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
    """Raised when no LLM gateway is configured or reachable.

    Signals that the targeted LLM fallback correction cannot run (no
    provider configured, missing credentials, or provider down), so the
    caller can keep the document's deterministic-validation issues and
    surface them to the user instead of silently dropping the fallback.

    Dependencies
    -----------
    - builtins.RuntimeError : base class; the exception carries no extra
      attributes, message-only semantics.

    Examples
    --------
    >>> raise LlmUnavailable("no provider configured")  # doctest: +SKIP
    Traceback (most recent call last):
    ...
    app.services.llm.gateway.LlmUnavailable: no provider configured
    """

    pass


class BaseGateway:
    """Common interface and helpers for LLM provider adapters.

    Defines the contract every provider adapter must fulfill
    (``resolve_fields``) and shares the prompt-building and
    response-parsing helpers so concrete gateways only implement
    transport-specific HTTP calls. Subclasses must set ``name`` and
    override ``resolve_fields``.

    Attributes
    ----------
    name : str
        Short identifier of the provider (e.g. ``"ollama"``,
        ``"openai"``); the base class marks it as ``"base"``.

    Methods
    -------
    resolve_fields(raw_text, field_names, issues)
        Ask the provider for corrected values of flagged fields.
    _build_prompt(raw_text, field_names, issues)
        Compose the user message sent to the provider.
    _parse_response(content)
        Extract the ``fields`` mapping from a JSON response.

    Dependencies
    -----------
    - json : used by ``_parse_response`` to decode the model answer.
    - app.core.config.settings : module-level provider defaults consumed
      by subclasses and ``get_gateway``.

    Examples
    --------
    >>> class FakeGateway(BaseGateway):
    ...     name = "fake"
    ...     def resolve_fields(self, raw_text, field_names, issues):
    ...         return {"net_pay": 2250.00}
    >>> gw = FakeGateway()
    >>> gw.resolve_fields("...", ["net_pay"], [])
    {'net_pay': 2250.0}
    """

    name = "base"

    def resolve_fields(
        self, raw_text: str, field_names: list[str], issues: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Ask the provider for corrected values of validation-flagged fields.

        Abstract method: each concrete adapter implements the
        provider-specific HTTP call (Ollama's ``/api/chat`` or OpenAI's
        chat completions endpoint), reusing ``_build_prompt`` and
        ``_parse_response`` from this class. The request is a targeted
        fallback for fields flagged by deterministic validation, never
        a full re-extraction of the document.

        Parameters
        ----------
        raw_text : str
            Full text of the payslip or CU document; only the first
            12,000 characters are sent (see ``_build_prompt``).
        field_names : list[str]
            Canonical names of the fields to correct, e.g.
            ``["net_pay", "period_month"]``.
        issues : list[dict]
            Validation issues driving the request, each with ``field``
            and ``message`` keys, as produced by the deterministic
            validation of the ``ExtractionResult``.

        Returns
        -------
        dict[str, Any]
            Mapping of field name to the corrected value found in the
            text; fields absent from the document are omitted.

        Raises
        ------
        NotImplementedError
            Always, on the base class; subclasses must override.

        Dependencies
        -----------
        - BaseGateway._build_prompt : builds the user message.
        - BaseGateway._parse_response : decodes the JSON answer.
        """

        raise NotImplementedError

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Extract the ``fields`` mapping from a JSON model response.

        Decodes the raw model content and returns its ``fields`` object,
        tolerating malformed answers: if the payload is not JSON or the
        ``fields`` value is not a dict, an empty mapping is returned so a
        bad LLM answer degrades to "no corrections" instead of crashing
        the pipeline.

        Parameters
        ----------
        content : str
            Raw text produced by the model, expected to be a JSON
            object of the form ``{"fields": {...}}``.

        Returns
        -------
        dict[str, Any]
            The ``fields`` mapping on success; ``{}`` when the content
            is not valid JSON or ``fields`` is not a dict.

        Raises
        ------
        json.JSONDecodeError
            If ``content`` is not valid JSON; the exception is
            deliberately not swallowed here (callers decide the
            fallback policy).

        Dependencies
        -----------
        - json.loads : decodes the model answer.

        Examples
        --------
        >>> gw = BaseGateway()
        >>> gw._parse_response('{"fields": {"net_pay": 2250.00}}')
        {'net_pay': 2250.0}
        """
        data = json.loads(content)
        fields = data.get("fields", {})
        return fields if isinstance(fields, dict) else {}

    def _build_prompt(self, raw_text: str, field_names: list[str], issues: list) -> str:
        """Compose the user message sent to the LLM provider.

        Assembles the targeted-fallback prompt: the requested field
        names, the validation issues that triggered the request, and
        the document text truncated to 12,000 characters to keep the
        request within provider context limits.

        Parameters
        ----------
        raw_text : str
            Full text of the document; only the first 12,000 characters
            are included.
        field_names : list[str]
            Canonical names of the fields to correct.
        issues : list
            Validation issues, each a dict with optional ``field`` and
            ``message`` keys; issues without a field are attributed to
            the whole document.

        Returns
        -------
        str
            The user message combining requested fields, issues, and
            document text.

        Dependencies
        -----------
        - _SYSTEM_PROMPT : paired with this prompt as the system
          message by the concrete gateways.

        Examples
        --------
        >>> prompt = BaseGateway()._build_prompt("text", ["net_pay"], [])
        >>> "net_pay" in prompt
        True
        """
        issues_text = "\n".join(
            f"- {i.get('field') or 'documento'}: {i.get('message')}" for i in issues
        )
        return (
            f"Campi richiesti: {', '.join(field_names)}\n\n"
            f"Problemi rilevati dalla validazione:\n{issues_text}\n\n"
            f"Testo del documento:\n{raw_text[:12000]}"
        )


class OpenAiGateway(BaseGateway):
    """Adapter for the OpenAI chat completions API (online deployments).

    Implements the ``BaseGateway`` contract against OpenAI, requesting
    a JSON-object response at temperature 0 for deterministic,
    schema-shaped answers used as targeted fallback corrections.

    Attributes
    ----------
    name : str
        Class attribute, always ``"openai"``.
    api_key : str
        Bearer token sent in the Authorization header.
    model : str
        OpenAI model identifier, e.g. ``"gpt-4o-mini"``.

    Methods
    -------
    resolve_fields(raw_text, field_names, issues)
        Ask OpenAI for corrected values of flagged fields.

    Dependencies
    -----------
    - httpx : synchronous HTTP client for the API call.
    - BaseGateway._build_prompt : composes the user message.
    - BaseGateway._parse_response : decodes the JSON answer.
    - _SYSTEM_PROMPT : system message framing the extraction task.

    Examples
    --------
    >>> gw = OpenAiGateway(api_key="sk-...", model="gpt-4o-mini")
    >>> gw.name
    'openai'
    """

    name = "openai"

    def __init__(self, api_key: str, model: str) -> None:
        """Store the API credentials and model for later requests.

        Pure attribute initialization: no network calls happen here, so
        constructing the gateway is cheap and safe during startup.

        Parameters
        ----------
        api_key : str
            OpenAI API key used as the Bearer token.
        model : str
            OpenAI model identifier to use for completions.

        Returns
        -------
        None

        Examples
        --------
        >>> gw = OpenAiGateway("sk-...", "gpt-4o-mini")
        >>> gw.model
        'gpt-4o-mini'
        """
        self.api_key = api_key
        self.model = model

    def resolve_fields(
        self, raw_text: str, field_names: list[str], issues: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Ask OpenAI for corrected values of validation-flagged fields.

        Sends the targeted-fallback prompt to the OpenAI chat
        completions endpoint with ``response_format=json_object`` and
        temperature 0, then parses the JSON answer. Runs fully
        synchronously; the pipeline invokes it inside a worker thread.

        Parameters
        ----------
        raw_text : str
            Full text of the document; truncated to 12,000 characters
            by ``_build_prompt``.
        field_names : list[str]
            Canonical names of the fields to correct.
        issues : list[dict]
            Validation issues driving the request, with ``field`` and
            ``message`` keys.

        Returns
        -------
        dict[str, Any]
            Mapping of field name to corrected value; fields absent
            from the document are omitted by the model.

        Raises
        ------
        httpx.HTTPStatusError
            If the API responds with a 4xx/5xx status
            (``raise_for_status``), e.g. invalid key or quota exceeded.
        httpx.HTTPError
            On transport failures such as timeouts (60 s) or connection
            errors.
        json.JSONDecodeError
            If the returned content is not valid JSON (propagated by
            ``_parse_response``).
        KeyError
            If the response payload lacks the expected
            ``choices[0].message.content`` structure.

        Dependencies
        -----------
        - httpx.post : performs the synchronous API request.
        - BaseGateway._build_prompt : composes the user message.
        - BaseGateway._parse_response : decodes the JSON answer.
        - _SYSTEM_PROMPT : system message framing the extraction task.
        """
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
    """Adapter for a local Ollama server (primary provider, privacy by design).

    Implements the ``BaseGateway`` contract against Ollama's ``/api/chat``
    endpoint. Being local, no document text ever leaves the machine,
    which is the default deployment choice for the privacy-first
    EarnSight pipeline.

    Attributes
    ----------
    name : str
        Class attribute, always ``"ollama"``.
    base_url : str
        Base URL of the Ollama server (trailing slash stripped), e.g.
        ``"http://localhost:11434"``.
    model : str
        Ollama model identifier, e.g. ``"llama3"``.

    Methods
    -------
    resolve_fields(raw_text, field_names, issues)
        Ask the local model for corrected values of flagged fields.

    Dependencies
    -----------
    - httpx : synchronous HTTP client for the local API call.
    - BaseGateway._build_prompt : composes the user message.
    - BaseGateway._parse_response : decodes the JSON answer.
    - _SYSTEM_PROMPT : system message framing the extraction task.

    Examples
    --------
    >>> gw = OllamaGateway(base_url="http://localhost:11434/", model="llama3")
    >>> gw.base_url
    'http://localhost:11434'
    >>> gw.name
    'ollama'
    """

    name = "ollama"

    def __init__(self, base_url: str, model: str) -> None:
        """Store the Ollama server URL and model for later requests.

        Normalizes ``base_url`` by stripping any trailing slash, then
        stores the model identifier. No network calls happen here, so
        constructing the gateway is cheap and safe during startup.

        Parameters
        ----------
        base_url : str
            Base URL of the Ollama server; a trailing slash is removed.
        model : str
            Ollama model identifier to use for chat.

        Returns
        -------
        None

        Examples
        --------
        >>> gw = OllamaGateway("http://localhost:11434/", "llama3")
        >>> gw.base_url
        'http://localhost:11434'
        """
        self.base_url = base_url.rstrip("/")
        self.model = model

    def resolve_fields(
        self, raw_text: str, field_names: list[str], issues: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Ask the local Ollama model for corrected values of flagged fields.

        Sends the targeted-fallback prompt to the local ``/api/chat``
        endpoint with JSON output format and temperature 0, then parses
        the answer. Runs fully synchronously; the pipeline invokes it
        inside a worker thread. Local inference keeps payslip data on
        the machine (privacy by design).

        Parameters
        ----------
        raw_text : str
            Full text of the document; truncated to 12,000 characters
            by ``_build_prompt``.
        field_names : list[str]
            Canonical names of the fields to correct.
        issues : list[dict]
            Validation issues driving the request, with ``field`` and
            ``message`` keys.

        Returns
        -------
        dict[str, Any]
            Mapping of field name to corrected value; fields absent
            from the document are omitted by the model.

        Raises
        ------
        httpx.HTTPStatusError
            If the server responds with a 4xx/5xx status
            (``raise_for_status``), e.g. unknown model.
        httpx.HTTPError
            On transport failures such as timeouts (120 s) or the
            Ollama server being unreachable.
        json.JSONDecodeError
            If the returned content is not valid JSON (propagated by
            ``_parse_response``).
        KeyError
            If the response payload lacks the expected
            ``message.content`` structure.

        Dependencies
        -----------
        - httpx.post : performs the synchronous local API request.
        - BaseGateway._build_prompt : composes the user message.
        - BaseGateway._parse_response : decodes the JSON answer.
        - _SYSTEM_PROMPT : system message framing the extraction task.
        """
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
    """Build the process-wide LLM gateway from environment settings.

    Factory function selecting the provider adapter declared in the
    application settings: OpenAI when ``llm_provider`` is ``"openai"``
    and an API key is present, Ollama when it is ``"ollama"``. Returns
    ``None`` when no valid configuration exists, in which case the
    LLM fallback is disabled and deterministic validation issues are
    surfaced to the user instead.

    Returns
    -------
    BaseGateway or None
        The configured gateway adapter, or ``None`` if the provider is
        unknown, unset, or lacks required credentials.

    Dependencies
    -----------
    - app.core.config.settings : provider, credentials, and model names.
    - OpenAiGateway : adapter returned for the ``openai`` provider.
    - OllamaGateway : adapter returned for the ``ollama`` provider.

    Examples
    --------
    >>> gw = get_gateway()
    >>> gw is None or isinstance(gw, BaseGateway)
    True
    """
    if settings.llm_provider == "openai" and settings.openai_api_key:
        return OpenAiGateway(settings.openai_api_key, settings.openai_model)
    if settings.llm_provider == "ollama":
        return OllamaGateway(settings.ollama_base_url, settings.ollama_model)
    return None


async def get_gateway_for_user(db, user) -> BaseGateway | None:  # noqa: ANN001
    """Build the gateway from the user's stored settings (DB), env as fallback.

    Constructs the LLM adapter from the per-user ``AppSetting`` row
    when present, falling back to ``get_gateway()`` (environment
    settings) when the user has no stored configuration. The OpenAI
    API key is encrypted at rest and decrypted only here, at adapter
    construction time, so plaintext credentials never persist in
    memory-bound rows or logs.

    Parameters
    ----------
    db : AsyncSession
        SQLAlchemy async session used to query the user's settings; a
        ``select`` on ``AppSetting`` filtered by ``user_id`` is
        executed.
    user : User
        Authenticated user whose settings are consulted; only ``id``
        is accessed.

    Returns
    -------
    BaseGateway or None
        The gateway built from the user's settings, the environment
        fallback via ``get_gateway()`` when no settings row exists, or
        ``None`` when the stored provider is unknown or lacks required
        credentials.

    Dependencies
    -----------
    - app.models.setting.AppSetting : ORM model holding per-user LLM
      configuration.
    - app.core.crypto.decrypt_secret : decrypts the stored OpenAI key.
    - get_gateway : environment-based fallback factory.
    - OpenAiGateway / OllamaGateway : adapters built from the settings.

    Examples
    --------
    >>> gw = await get_gateway_for_user(db, current_user)  # doctest: +SKIP
    >>> gw is None or gw.name in ("openai", "ollama")  # doctest: +SKIP
    True
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
