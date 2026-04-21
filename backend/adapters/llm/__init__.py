"""LLM provider adapters."""

from adapters.llm.base import LLMProvider
from adapters.llm.openai_provider import OpenAIProvider
from adapters.llm.openrouter_provider import OpenRouterProvider
from adapters.llm.hf_precision_provider import HFPrecisionProvider


def get_default_provider() -> LLMProvider:
    """Return OpenRouter if configured, otherwise fall back to OpenAI."""
    from infrastructure.config import settings
    if settings.openrouter_api_key:
        return OpenRouterProvider()
    return OpenAIProvider()


__all__ = ["LLMProvider", "OpenAIProvider", "OpenRouterProvider", "HFPrecisionProvider", "get_default_provider"]
