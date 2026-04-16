"""Guided Rewrite Engine: generates rewrite variants."""

from __future__ import annotations

from typing import Any

from adapters.llm import LLMProvider, OpenAIProvider
from rewrite.prompts import build_diversifying_prompt, build_mimicking_prompt


class GuidedRewriteEngine:
    """Generates rewrite variants using LLM providers."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider or OpenAIProvider()

    async def rewrite(
        self,
        text: str,
        mode: str,
        style_profile: dict[str, Any] | None = None,
        contract: dict[str, Any] | None = None,
        reference_samples: list[str] | None = None,
    ) -> dict[str, Any]:
        """Generate a single rewrite variant."""
        prompt = self._build_prompt(text, mode, style_profile, contract, reference_samples)
        response = await self._provider.generate(
            prompt,
            temperature=self._temperature_for_mode(mode),
        )
        return {
            "mode": mode,
            "text": response["text"],
            "usage": response.get("usage", {}),
        }

    async def rewrite_all_modes(
        self,
        text: str,
        style_profile: dict[str, Any] | None = None,
        contract: dict[str, Any] | None = None,
        reference_samples: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Generate Conservative, Balanced, and Expressive variants."""
        variants: list[dict[str, Any]] = []
        for mode in ("conservative", "balanced", "expressive"):
            variant = await self.rewrite(
                text, mode, style_profile, contract, reference_samples
            )
            variants.append(variant)
        return variants

    def _build_prompt(
        self,
        text: str,
        mode: str,
        style_profile: dict[str, Any] | None,
        contract: dict[str, Any] | None,
        reference_samples: list[str] | None,
    ) -> str:
        if reference_samples:
            ref = reference_samples[0]
            return build_mimicking_prompt(text, ref, style_profile, contract, mode)
        return build_diversifying_prompt(text, style_profile, contract, mode)

    def _temperature_for_mode(self, mode: str) -> float:
        return {"conservative": 0.3, "balanced": 0.6, "expressive": 0.9}.get(mode, 0.6)


guided_rewrite_engine = GuidedRewriteEngine()
