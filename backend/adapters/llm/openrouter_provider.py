"""OpenRouter API provider — OpenAI-compatible, supports Mixtral/Llama/Qwen/etc."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from adapters.llm.base import LLMProvider
from infrastructure.config import settings
from infrastructure.logging import get_logger

logger = get_logger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

# Models known to produce distributions that GPTZero detects less reliably than GPT-4o.
# Ordered by quality for humanization tasks.
RECOMMENDED_MODELS = [
    "mistralai/mixtral-8x7b-instruct",       # best quality, ~$0.24/M tokens
    "mistralai/mistral-7b-instruct:free",     # free tier
    "meta-llama/llama-3.1-8b-instruct:free",  # free tier
    "qwen/qwen-2.5-72b-instruct",             # Chinese model, very different distribution
    "google/gemma-2-9b-it:free",              # free tier
]


class OpenRouterProvider(LLMProvider):
    """OpenRouter provider — wraps OpenAI SDK with OpenRouter base URL.

    Supports any model on openrouter.ai. The key advantage: Mixtral, Llama,
    Qwen etc. have different token probability distributions than GPT-4o,
    so their outputs are harder for GPTZero to classify as AI-generated.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        resolved_key = api_key or settings.openrouter_api_key
        if not resolved_key:
            raise RuntimeError("OPENROUTER_API_KEY is not configured")
        self._client = AsyncOpenAI(
            api_key=resolved_key,
            base_url=OPENROUTER_BASE_URL,
            default_headers={
                "HTTP-Referer": "https://humanizator.app",
                "X-Title": "Humanizator",
            },
        )
        self._default_model = model or settings.openrouter_model

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(RuntimeError),
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        used_model = model or self._default_model
        logger.debug("openrouter generate model=%s", used_model)

        response = await self._client.chat.completions.create(
            model=used_model,
            messages=messages,
            temperature=min(temperature, 1.5),  # some OR models cap at 1.5
            max_tokens=max_tokens,
        )
        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        return {
            "text": choice.message.content or "",
            "finish_reason": choice.finish_reason,
            "usage": usage,
            "model": response.model,
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_not_exception_type(RuntimeError),
    )
    async def generate_multiple(
        self,
        prompt: str,
        n: int = 3,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        # OpenRouter doesn't support n>1 for all models — generate sequentially
        import asyncio
        tasks = [
            self.generate(prompt, system_prompt, model, temperature, max_tokens)
            for _ in range(n)
        ]
        return await asyncio.gather(*tasks)
