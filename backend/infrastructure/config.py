"""Application configuration via pydantic-settings."""

from pydantic import PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "humanizator"
    app_env: str = "development"
    debug: bool = False

    # Database
    database_url: PostgresDsn = PostgresDsn("postgresql+asyncpg://user:password@localhost:5432/humanizator")
    database_url_sync: str = "postgresql://user:password@localhost:5432/humanizator"

    # Redis
    redis_url: RedisDsn = RedisDsn("redis://localhost:6379/0")
    redis_cache_url: RedisDsn = RedisDsn("redis://localhost:6379/1")

    # Celery
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"

    # LLM Providers
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"

    # Auth
    jwt_secret_key: str = "change-me-in-production-use-strong-random-secret"
    jwt_ttl_minutes: int = 60 * 24  # 24 hours

    # Observability
    log_level: str = "INFO"
    enable_prometheus: bool = True

    # NLP / ML models
    sentence_transformer_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    deberta_model: str = "microsoft/deberta-v3-large"
    perplexity_model: str = "gpt2"

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper


settings = Settings()
