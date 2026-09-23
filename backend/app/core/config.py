from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# Segreti noti-che-non-sono-segreti: l'avvio fallisce se SECRET_KEY è uno di questi.
_PLACEHOLDER_SECRET_KEYS = frozenset(
    {"dev-secret-change-me", "change-me", "change-me-with-a-long-random-string"}
)
MIN_SECRET_KEY_LENGTH = 32

# Driver async → controparte sync: la derivazione copre solo i driver noti e
# fallisce in modo chiaro sugli altri, invece di produrre un URL rotto.
_SYNC_DRIVER_MAP = {
    "postgresql+asyncpg": "postgresql+psycopg",
    "sqlite+aiosqlite": "sqlite+pysqlite",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://earnsight:earnsight@localhost:5432/earnsight"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = "./data"

    secret_key: str = "dev-secret-change-me"
    auth_username: str = "admin"
    auth_password: str = "admin"
    access_token_expire_minutes: int = 1440

    max_upload_mb: int = 10

    llm_provider: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    @property
    def sync_database_url(self) -> str:
        """URL sync del database (Celery/worker, Alembic).

        replace() a mani basse non copre driver diversi da asyncpg: qui la
        mappa è esplicita e i driver sconosciuti sollevano un errore chiaro
        all'avvio, non a runtime su una connessione rotta.
        """
        url = make_url(self.database_url)
        try:
            return url.set(drivername=_SYNC_DRIVER_MAP[url.drivername]).render_as_string(
                hide_password=False
            )
        except KeyError:
            known = ", ".join(sorted(_SYNC_DRIVER_MAP))
            raise ValueError(
                f"DATABASE_URL usa il driver {url.drivername!r}: "
                f"nessuna controparte sync configurata (supportati: {known})"
            ) from None

    @property
    def secret_key_is_placeholder(self) -> bool:
        return (
            self.secret_key in _PLACEHOLDER_SECRET_KEYS
            or len(self.secret_key) < MIN_SECRET_KEY_LENGTH
        )

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
