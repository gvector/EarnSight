from pydantic import BaseModel


class SettingsOut(BaseModel):
    llm_provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    openai_model: str | None = None
    openai_api_key_set: bool = False


class SettingsIn(BaseModel):
    llm_provider: str | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None
    openai_model: str | None = None
    # stringa vuota = cancella la chiave salvata; assente = invariata
    openai_api_key: str | None = None
