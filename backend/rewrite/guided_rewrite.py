"""Guided Rewrite Engine: generates rewrite variants.

Supports both short-text (direct) and long-text (chunk-level) processing.
Chunk-level pipeline splits by paragraph boundaries, rewrites each chunk
preserving cross-chunk context, then reassembles with coherence check.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from adapters.llm import LLMProvider, OpenAIProvider
from rewrite.prompts import (
    build_precision_prompt,
    build_user_prompt,
    get_system_prompt,
)

logger = logging.getLogger(__name__)

# Texts longer than this threshold use chunk-level processing
CHUNK_THRESHOLD_WORDS = 300
# Target chunk size in words (paragraph-level)
CHUNK_TARGET_WORDS = 200


class GuidedRewriteEngine:
    """Generates rewrite variants using LLM providers.

    For texts > CHUNK_THRESHOLD_WORDS: splits into paragraph chunks,
    rewrites each with cross-chunk context window, reassembles.
    For shorter texts: rewrites as single unit.
    """

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
        """Generate a single rewrite variant (direct, chunk-level, or precision)."""
        if mode == "precision":
            return await self._rewrite_precision(text, style_profile, contract, reference_samples)
        word_count = len(text.split())
        if word_count > CHUNK_THRESHOLD_WORDS:
            return await self._rewrite_chunked(
                text, mode, style_profile, contract, reference_samples
            )
        return await self._rewrite_direct(
            text, mode, style_profile, contract, reference_samples
        )

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

    # ------------------------------------------------------------------
    # Token-level Precision Guided rewrite (T5.4 / Algorithm 1)
    # ------------------------------------------------------------------

    async def _rewrite_precision(
        self,
        text: str,
        style_profile: dict[str, Any] | None,
        contract: dict[str, Any] | None,
        reference_samples: list[str] | None,
    ) -> dict[str, Any]:
        """Token-level guided rewrite: select each token to minimise AI-score.

        Requires HFPrecisionProvider (local HuggingFace model with logit access).
        Falls back to standard balanced generation if provider is unavailable.
        """
        try:
            from application.services.token_precision import token_precision_engine
            prompt = build_precision_prompt(text, style_profile, contract)
            result = await token_precision_engine.generate_async(prompt)
            return {
                "mode": "precision",
                "text": result["text"],
                "usage": {
                    "prompt_tokens": 0,
                    "completion_tokens": result["tokens_generated"],
                    "total_tokens": result["tokens_generated"],
                },
                "chunks_count": 1,
                "precision_metadata": {
                    "tokens_generated": result["tokens_generated"],
                    "algorithm": result["algorithm"],
                    "top_k": result["top_k"],
                    "top_p": result["top_p"],
                },
            }
        except Exception as exc:
            logger.warning("Precision mode failed (%s) — falling back to balanced", exc)
            return await self._rewrite_direct(text, "balanced", style_profile, contract, reference_samples)

    # ------------------------------------------------------------------
    # Direct (single-pass) rewrite
    # ------------------------------------------------------------------

    async def _rewrite_direct(
        self,
        text: str,
        mode: str,
        style_profile: dict[str, Any] | None,
        contract: dict[str, Any] | None,
        reference_samples: list[str] | None,
    ) -> dict[str, Any]:
        ref = reference_samples[0] if reference_samples and mode == "expressive" else None
        system = get_system_prompt(mode, ref)
        user = build_user_prompt(text, style_profile, contract, ref)
        response = await self._provider.generate(
            user,
            system_prompt=system,
            temperature=self._temperature_for_mode(mode),
        )
        return {
            "mode": mode,
            "text": response["text"],
            "usage": response.get("usage", {}),
            "chunks_count": 1,
        }

    # ------------------------------------------------------------------
    # Chunk-level rewrite (T5.5)
    # ------------------------------------------------------------------

    async def _rewrite_chunked(
        self,
        text: str,
        mode: str,
        style_profile: dict[str, Any] | None,
        contract: dict[str, Any] | None,
        reference_samples: list[str] | None,
    ) -> dict[str, Any]:
        """Rewrite long text by splitting into paragraph-level chunks.

        Cross-chunk context: each chunk receives a 1-sentence summary of the
        previous chunk as context prefix, preserving narrative flow.
        """
        chunks = self._split_into_chunks(text)
        rewritten_chunks: list[str] = []
        total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        prev_context: str | None = None

        ref = reference_samples[0] if reference_samples and mode == "expressive" else None
        system = get_system_prompt(mode, ref)
        for i, chunk in enumerate(chunks):
            user = build_user_prompt(
                chunk, style_profile, contract, ref,
                is_chunk=True, chunk_idx=i, total_chunks=len(chunks),
                prev_context=prev_context,
            )
            try:
                response = await self._provider.generate(
                    user,
                    system_prompt=system,
                    temperature=self._temperature_for_mode(mode),
                    max_tokens=600,
                )
                rewritten = response["text"].strip()
                rewritten_chunks.append(rewritten)
                # Update usage
                for k in total_usage:
                    total_usage[k] += response.get("usage", {}).get(k, 0)
                # Build context for next chunk (first sentence of current result)
                prev_context = self._first_sentence(rewritten)
            except RuntimeError:
                raise
            except Exception as exc:
                logger.warning("Chunk %d/%d rewrite failed: %s — using original", i + 1, len(chunks), exc)
                rewritten_chunks.append(chunk)

        final_text = self._reassemble_chunks(rewritten_chunks)
        return {
            "mode": mode,
            "text": final_text,
            "usage": total_usage,
            "chunks_count": len(chunks),
        }

    def _split_into_chunks(self, text: str) -> list[str]:
        """Split text into paragraph-level chunks.

        Strategy:
        1. Split on double newlines (paragraph breaks).
        2. Merge very short paragraphs into the next.
        3. Split very long paragraphs at sentence boundaries.
        """
        raw_paras = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
        chunks: list[str] = []
        buffer = ""

        for para in raw_paras:
            words = (buffer + " " + para).split() if buffer else para.split()
            if len(words) <= CHUNK_TARGET_WORDS:
                buffer = (buffer + "\n\n" + para).strip() if buffer else para
            else:
                if buffer:
                    chunks.append(buffer)
                # Split oversized paragraph at sentence boundary
                sub_chunks = self._split_paragraph(para)
                chunks.extend(sub_chunks[:-1])
                buffer = sub_chunks[-1] if sub_chunks else ""

        if buffer:
            chunks.append(buffer)

        return chunks or [text]

    def _split_paragraph(self, para: str) -> list[str]:
        """Split a single long paragraph into sentence-boundary chunks."""
        sentences = re.split(r"(?<=[.!?])\s+", para)
        chunks: list[str] = []
        current: list[str] = []
        current_words = 0

        for sent in sentences:
            sent_words = len(sent.split())
            if current_words + sent_words > CHUNK_TARGET_WORDS and current:
                chunks.append(" ".join(current))
                current = [sent]
                current_words = sent_words
            else:
                current.append(sent)
                current_words += sent_words

        if current:
            chunks.append(" ".join(current))
        return chunks or [para]

    def _first_sentence(self, text: str) -> str:
        """Extract first sentence for cross-chunk context."""
        match = re.search(r"[^.!?]+[.!?]", text)
        return match.group(0).strip() if match else text[:100]

    def _reassemble_chunks(self, chunks: list[str]) -> str:
        """Join chunks with paragraph separators."""
        return "\n\n".join(c.strip() for c in chunks if c.strip())

    def _temperature_for_mode(self, mode: str) -> float:
        return {"conservative": 0.55, "balanced": 0.75, "expressive": 0.95}.get(mode, 0.75)


guided_rewrite_engine = GuidedRewriteEngine()
