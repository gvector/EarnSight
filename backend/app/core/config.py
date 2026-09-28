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
    """Typed application settings loaded from environment and ``.env``.

    Centralizes every external knob of EarnSight: database and Redis URLs,
    storage directory, authentication material, upload limits and LLM
    gateway parameters. Values are bound and validated by pydantic-settings
    at construction, so a malformed environment fails at startup rather
    than surfacing as a broken connection at runtime.

    Parameters
    ----------
    **kwargs : Any, optional
        Explicit field overrides; when omitted, values come from
        environment variables or the ``.env`` file (unknown keys are
        ignored per ``extra="ignore"``).

    Attributes
    ----------
    database_url : str
        Async SQLAlchemy URL used by the API (asyncpg by default).
    redis_url : str
        Celery broker URL for document processing jobs.
    data_dir : str
        Root directory where uploaded payslip files are stored.
    secret_key : str
        Master secret signing JWTs and deriving the Fernet key for
        stored API keys; must be replaced before production startup.
    auth_username : str
        Username seeded for the bootstrap admin account.
    auth_password : str
        Password seeded for the bootstrap admin account.
    access_token_expire_minutes : int
        JWT lifetime in minutes (default 1440, i.e. one day).
    max_upload_mb : int
        Maximum accepted payslip upload size in megabytes.
    llm_provider : str
        Selected gateway provider (``"ollama"`` or ``"openai"``);
        empty disables LLM-assisted correction.
    openai_api_key : str
        API key for the OpenAI gateway.
    openai_model : str
        Model name used by the OpenAI gateway.
    ollama_base_url : str
        Base URL of the local Ollama server.
    ollama_model : str
        Model tag used by the Ollama gateway.

    Methods
    -------
    sync_database_url
        Derive the sync-driver URL for workers and Alembic.
    secret_key_is_placeholder
        Report whether the master secret is still unsafe.
    max_upload_bytes
        Express the upload cap in bytes.

    Dependencies
    -----------
    - pydantic_settings.BaseSettings : environment binding and validation.
    - sqlalchemy.engine.make_url : URL parsing in ``sync_database_url``.

    Examples
    --------
    >>> s = Settings(secret_key="x" * 48)  # doctest: +SKIP
    >>> s.max_upload_bytes
    10485760
    """

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
        """str: Sync-driver counterpart of ``database_url``.

        Hand-rolled string replacement only covers asyncpg: here the
        driver mapping is explicit and unknown drivers fail with a clear
        error at startup, not at runtime on a broken connection.

        Returns
        -------
        str
            Database URL with the sync driver substituted (e.g.
            ``postgresql+psycopg`` for ``postgresql+asyncpg``).

        Raises
        ------
        ValueError
            If ``database_url`` uses a driver with no configured sync
            counterpart.

        Dependencies
        -----------
        - sqlalchemy.engine.make_url : parses and re-renders the URL.
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
        """bool: Whether SECRET_KEY is a known placeholder or too short.

        Guards startup against deploying with an unsafe master secret:
        both membership in the placeholder set and the minimum length
        are checked, since a weak key undermines JWT signing and Fernet
        key derivation alike.

        Returns
        -------
        bool
            True when the key must be replaced before production use.
        """
        return (
            self.secret_key in _PLACEHOLDER_SECRET_KEYS
            or len(self.secret_key) < MIN_SECRET_KEY_LENGTH
        )

    @property
    def max_upload_bytes(self) -> int:
        """int: Upload cap expressed in bytes.

        Converts ``max_upload_mb`` once so route handlers can compare
        an incoming file's size directly, without per-request arithmetic.

        Returns
        -------
        int
            ``max_upload_mb`` scaled by 1024 squared.
        """
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Build the Settings instance once per process and cache it.

    The lru_cache guarantees a single instantiation even under
    concurrent imports, keeping environment parsing cost off the
    request path; the module-level ``settings`` singleton is produced
    here at import time.

    Returns
    -------
    Settings
        The process-wide settings object.
    """
    return Settings()


settings = get_settings()
