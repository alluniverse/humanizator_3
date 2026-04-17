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
    build_adversarial_prompt,
    build_diversifying_prompt,
    build_mimicking_prompt,
    build_precision_prompt,
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
        prompt = self._build_prompt(text, mode, style_profile, contract, reference_samples)
        response = await self._provider.generate(
            prompt,
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

        for i, chunk in enumerate(chunks):
            chunk_text = self._add_context_prefix(chunk, prev_context, i)
            prompt = self._build_prompt(
                chunk_text, mode, style_profile, contract,
                reference_samples, is_chunk=True, chunk_idx=i, total_chunks=len(chunks)
            )
            try:
                response = await self._provider.generate(
                    prompt,
                    temperature=self._temperature_for_mode(mode),
                    max_tokens=512,
                )
                rewritten = response["text"]
                # Strip context prefix echo if model repeated it
                rewritten = self._strip_context_echo(rewritten, prev_context)
                rewritten_chunks.append(rewritten)
                # Update usage
                for k in total_usage:
                    total_usage[k] += response.get("usage", {}).get(k, 0)
                # Build context for next chunk (first sentence of current result)
                prev_context = self._first_sentence(rewritten)
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

    def _add_context_prefix(self, chunk: str, prev_context: str | None, idx: int) -> str:
        """Prepend cross-chunk context to maintain narrative continuity."""
        if prev_context and idx > 0:
            return f"[Previous context: {prev_context}]\n\n{chunk}"
        return chunk

    def _strip_context_echo(self, text: str, prev_context: str | None) -> str:
        """Remove echoed context prefix if the model repeated it."""
        if not prev_context:
            return text
        prefix_marker = "[Previous context:"
        if text.startswith(prefix_marker):
            # Strip up to the end of the context block
            end = text.find("]")
            if end != -1:
                text = text[end + 1:].lstrip("\n ")
        return text

    def _first_sentence(self, text: str) -> str:
        """Extract first sentence for cross-chunk context."""
        match = re.search(r"[^.!?]+[.!?]", text)
        return match.group(0).strip() if match else text[:100]

    def _reassemble_chunks(self, chunks: list[str]) -> str:
        """Join chunks with paragraph separators."""
        return "\n\n".join(c.strip() for c in chunks if c.strip())

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_prompt(
        self,
        text: str,
        mode: str,
        style_profile: dict[str, Any] | None,
        contract: dict[str, Any] | None,
        reference_samples: list[str] | None,
        is_chunk: bool = False,
        chunk_idx: int = 0,
        total_chunks: int = 1,
    ) -> str:
        chunk_note = (
            f"\n\n[Note: This is chunk {chunk_idx + 1} of {total_chunks}. "
            "Maintain consistent style with surrounding chunks.]"
            if is_chunk and total_chunks > 1
            else ""
        )
        if mode == "expressive" and reference_samples:
            ref = reference_samples[0]
            return build_mimicking_prompt(text + chunk_note, ref, style_profile, contract, mode)
        if mode == "conservative":
            return build_adversarial_prompt(text + chunk_note, style_profile, contract)
        return build_diversifying_prompt(text + chunk_note, style_profile, contract, mode)

    def _temperature_for_mode(self, mode: str) -> float:
        return {"conservative": 0.3, "balanced": 0.6, "expressive": 0.9}.get(mode, 0.6)


guided_rewrite_engine = GuidedRewriteEngine()
