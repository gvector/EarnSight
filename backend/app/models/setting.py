from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    """Impostazioni per utente: provider LLM e API key (cifrata a riposo)."""

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
