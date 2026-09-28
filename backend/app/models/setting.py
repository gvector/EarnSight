from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    """Per-user gateway settings: LLM provider and encrypted API key.

    One row per user (unique ``user_id``) configuring the LLM gateway:
    which provider to use (Ollama local or OpenAI remote), the
    connection details for the chosen provider, and the OpenAI API key
    encrypted at rest. Consumed by the gateway adapters when the
    pipeline needs an LLM pass.

    Attributes
    ----------
    id : Integer, primary key, autoincrement
        Unique identifier of the settings row.
    user_id : Integer, FK ``user.id``, unique
        Owner user; one settings row per user.
    llm_provider : String(16), nullable
        Selected provider: ``"ollama"`` or ``"openai"``.
    ollama_base_url : String(256), nullable
        Base URL of the local Ollama server.
    ollama_model : String(64), nullable
        Model name requested from Ollama.
    openai_model : String(64), nullable
        Model name requested from OpenAI.
    openai_api_key_encrypted : Text, nullable
        OpenAI API key encrypted at rest; never returned by the API.
    updated_at : DateTime(timezone=True), nullable
        Last update timestamp, refreshed on UPDATE.

    Dependencies
    -----------
    - app.db.base.Base : declarative base and metadata registry.
    - app.core security/crypto helpers : key encryption at rest.
    - app.services LLM gateway : adapter selected from these settings.

    Examples
    --------
    >>> setting = AppSetting(user_id=1, llm_provider="ollama")
    >>> setting.llm_provider
    'ollama'
    """

    __tablename__ = "app_setting"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True)
    llm_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ollama_base_url: Mapped[str | None] = mapped_column(String(256), nullable=True)
    ollama_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    openai_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    openai_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )
