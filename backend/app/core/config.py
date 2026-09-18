from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://earnsight:earnsight@localhost:5432/earnsight"
    redis_url: str = "redis://localhost:6379/0"
    data_dir: str = "./data"

    secret_key: str = "dev-secret-change-me"
    auth_username: str = "admin"
    auth_password: str = "admin"
    access_token_expire_minutes: int = 1440

    llm_provider: str = ""
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
