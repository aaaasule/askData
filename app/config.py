"""Application settings via environment / .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "AskData"
    api_prefix: str = "/api"
    api_key: str = "change-me"
    database_url: str = "sqlite+aiosqlite:///./askdata.db"
    cors_origins: str = "*"
    # Default OpenAI-compatible endpoint (optional until models table is used)
    default_model_base_url: str = ""
    default_model_api_key: str = ""
    default_model_name: str = ""
    sql_max_rows: int = 200
    sql_timeout_seconds: int = 30
    analysis_timeout_seconds: int = 120
    # Fernet key for datasource passwords and model api keys. Empty falls back
    # to a key derived from API_KEY. SECRET_ENCRYPTION_KEY is an alias.
    askdata_secret_key: str = ""
    secret_encryption_key: str = ""
    # Prior turns replayed into the model for the same conversation.
    conversation_max_messages: int = 12
    conversation_max_chars: int = 12000

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
