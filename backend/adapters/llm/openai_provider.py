"""OpenAI API provider implementation."""

from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

from adapters.llm.base import LLMProvider
from infrastructure.config import settings
from infrastructure.llm_cost_tracker import llm_cost_tracker
from infrastructure.logging import get_logger

logger = get_logger(__name__)


class OpenAIProvider(LLMProvider):
    """OpenAI-compatible LLM provider."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key or settings.openai_api_key or "",
            base_url=base_url or settings.openai_base_url,
        )
        self._default_model = settings.openai_model

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> dict[str, Any]:
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs,
        )
        choice = response.choices[0]
        usage = {
            "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
            "completion_tokens": response.usage.completion_tokens if response.usage else 0,
            "total_tokens": response.usage.total_tokens if response.usage else 0,
        }
        try:
            await llm_cost_tracker.record(
                project_id=kwargs.get("project_id"),
                model=response.model,
                usage=usage,
                task_id=kwargs.get("task_id"),
            )
        except Exception:
            pass
        return {
            "text": choice.message.content or "",
            "finish_reason": choice.finish_reason,
            "usage": usage,
            "model": response.model,
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_multiple(
        self,
        prompt: str,
        n: int = 3,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        response = await self._client.chat.completions.create(
            model=model or self._default_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=max_tokens,
            n=n,
            **kwargs,
        )
        results: list[dict[str, Any]] = []
        for choice in response.choices:
            results.append(
                {
                    "text": choice.message.content or "",
                    "finish_reason": choice.finish_reason,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                        "completion_tokens": (response.usage.completion_tokens if response.usage else 0) // max(n, 1),
                        "total_tokens": response.usage.total_tokens if response.usage else 0,
                    },
                    "model": response.model,
                }
            )
        return results
