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

    # LLM Providers — OpenAI
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str = "gpt-4o"

    # LLM Providers — OpenRouter (optional, overrides OpenAI for rewrite tasks when set)
    # Get key at https://openrouter.ai/keys
    # Recommended models (different distribution → harder for GPTZero to detect):
    #   mistralai/mixtral-8x7b-instruct       — best quality
    #   mistralai/mistral-7b-instruct:free     — free
    #   meta-llama/llama-3.1-8b-instruct:free  — free
    #   qwen/qwen-2.5-72b-instruct             — very different (Chinese model)
    openrouter_api_key: str | None = None
    openrouter_model: str = "mistralai/mixtral-8x7b-instruct"

    # Auth
    jwt_secret_key: str = "change-me-in-production-use-strong-random-secret"
    jwt_ttl_minutes: int = 60 * 24  # 24 hours

    # Observability
    log_level: str = "INFO"
    enable_prometheus: bool = True

    # HuggingFace access token — required for gated models (LLaMA-3, etc.)
    # Get yours at https://huggingface.co/settings/tokens
    hf_token: str | None = None

    # NLP / ML models
    sentence_transformer_model: str = "paraphrase-multilingual-MiniLM-L12-v2"
    deberta_model: str = "microsoft/deberta-v3-large"
    perplexity_model: str = "gpt2"

    # Best-of-N mode — generate N API variants, pick the one with lowest AI-detector score.
    # Only requires local RoBERTa detector (~0.5 GB VRAM); no local LLM needed.
    best_of_n_count: int = 5

    # Algorithm 1 (Cheng et al. 2025 arXiv:2506.07001v1) — Adversarial Paraphrasing
    #
    # Paraphraser LLM — requires AutoModelForCausalLM with logit access.
    # Paper uses LLaMA-3-8B-Instruct (needs 16 GB VRAM / 32 GB RAM).
    # For ≤6 GB VRAM: use Qwen/Qwen2.5-3B-Instruct with precision_model_load_in_4bit=true (~1.5 GB).
    # For ≤4 GB VRAM: use Qwen/Qwen2.5-1.5B-Instruct with 4-bit (~0.9 GB).
    # gpt2 is the dev/testing fallback only (very low paraphrase quality).
    precision_model: str = "gpt2"
    #
    # Load paraphraser in 4-bit quantization (bitsandbytes required).
    # Cuts VRAM ~4x with minor quality loss. Required for consumer GPUs (≤8 GB VRAM).
    # Install: pip install bitsandbytes accelerate
    precision_model_load_in_4bit: bool = False
    #
    # Guidance detector D — trained AI-text classifier, lower output = more human-like.
    # Paper uses openai-community/roberta-large-openai-detector (1.4 GB VRAM).
    # For constrained VRAM (<1 GB free): use openai-community/roberta-base-openai-detector (0.5 GB).
    # If unset, RobertaAIDetector will auto-load roberta-base-openai-detector.
    ai_detector_model: str | None = None

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = value.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @field_validator("openai_api_key", "openai_base_url", "openrouter_api_key", mode="before")
    @classmethod
    def _blank_str_to_none(cls, value: str | None) -> str | None:
        if isinstance(value, str) and not value.strip():
            return None
        return value


settings = Settings()
