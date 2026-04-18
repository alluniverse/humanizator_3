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

    # Algorithm 1 (Cheng et al. 2025 arXiv:2506.07001v1) — Adversarial Paraphrasing
    #
    # Paraphraser LLM — requires AutoModelForCausalLM with logit access.
    # Paper uses LLaMA-3-8B-Instruct; gpt2 is the dev/testing fallback (low quality).
    # Recommended production value: meta-llama/Meta-Llama-3-8B-Instruct
    precision_model: str = "gpt2"
    #
    # Guidance detector D — trained AI-text classifier, lower output = more human-like.
    # Paper uses openai-community/roberta-large-openai-detector.
    # If unset, RobertaAIDetector will auto-load openai-community/roberta-base-openai-detector.
    # Recommended: openai-community/roberta-large-openai-detector (1.4 GB, better accuracy)
    ai_detector_model: str | None = None

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("openai_api_key", "openai_base_url", mode="before")
    @classmethod
    def _blank_openai_values_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value


settings = Settings()
