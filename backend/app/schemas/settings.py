from pydantic import BaseModel


class SettingsOut(BaseModel):
    """Serialization of a user's gateway settings for the API.

    Response body of the settings endpoints: the selected LLM provider
    and its connection details, plus a boolean flag telling whether an
    OpenAI API key is stored. The encrypted key itself is never
    serialized.

    Attributes
    ----------
    llm_provider : str | None
        Selected provider: ``"ollama"`` or ``"openai"``.
    ollama_base_url : str | None
        Base URL of the local Ollama server.
    ollama_model : str | None
        Model name requested from Ollama.
    openai_model : str | None
        Model name requested from OpenAI.
    openai_api_key_set : bool
        True when an (encrypted) OpenAI API key is stored.

    Dependencies
    -----------
    - app.models.setting.AppSetting : ORM source of these values.

    Examples
    --------
    >>> out = SettingsOut(llm_provider="ollama")
    >>> out.openai_api_key_set
    False
    """

    llm_provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    openai_model: str | None = None
    openai_api_key_set: bool = False


class SettingsIn(BaseModel):
    """User-submitted update of the gateway settings.

    Request body of the settings update endpoint. Only the provided
    fields are updated. For the OpenAI API key, an empty string deletes
    the stored key; an absent field leaves it unchanged.

    Attributes
    ----------
    llm_provider : str | None
        Provider to select: ``"ollama"`` or ``"openai"``.
    ollama_base_url : str | None
        Base URL of the local Ollama server.
    ollama_model : str | None
        Model name requested from Ollama.
    openai_model : str | None
        Model name requested from OpenAI.
    openai_api_key : str | None
        Plaintext OpenAI API key to store encrypted; an empty string
        clears the stored key, absence leaves it unchanged.

    Dependencies
    -----------
    - app.models.setting.AppSetting : ORM row updated from this body.
    - app.core crypto helpers : encryption of the submitted API key.

    Examples
    --------
    >>> body = SettingsIn(llm_provider="openai", openai_api_key="sk-...")
    >>> body.llm_provider
    'openai'
    """

    llm_provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    openai_model: str | None = None
    # stringa vuota = cancella la chiave salvata; assente = invariata
    openai_api_key: str | None = None
