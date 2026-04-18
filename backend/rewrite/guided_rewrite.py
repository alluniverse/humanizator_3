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
    PRECISION_SYSTEM_PROMPT,
    build_precision_prompt,
    build_user_prompt,
    get_system_prompt,
    get_refinement_system_prompt,
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
        user_instruction: str | None = None,
    ) -> dict[str, Any]:
        """Generate a single rewrite variant (direct, chunk-level, precision, or best_of_n)."""
        if mode == "precision":
            return await self._rewrite_precision(text, style_profile, contract, reference_samples)
        if mode == "best_of_n":
            return await self._rewrite_best_of_n(
                text, style_profile, contract, reference_samples, user_instruction
            )
        word_count = len(text.split())
        if word_count > CHUNK_THRESHOLD_WORDS:
            return await self._rewrite_chunked(
                text, mode, style_profile, contract, reference_samples, user_instruction
            )
        return await self._rewrite_direct(
            text, mode, style_profile, contract, reference_samples, user_instruction
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
    # Best-of-N: generate N variants via API, pick lowest AI-score
    # ------------------------------------------------------------------

    async def _rewrite_best_of_n(
        self,
        text: str,
        style_profile: dict[str, Any] | None,
        contract: dict[str, Any] | None,
        reference_samples: list[str] | None,
        user_instruction: str | None = None,
    ) -> dict[str, Any]:
        """Generate N variants concurrently, score with AI detector, return the best.

        Unlike precision mode (requires local LLM + logit access), this works with
        any API provider.  Only a local AI detector (~0.5 GB) is needed for scoring.
        """
        import asyncio
        from infrastructure.config import settings

        n = getattr(settings, "best_of_n_count", 5)

        # Use balanced mode at high temperature for maximum diversity
        tasks = [
            self._rewrite_direct(
                text, "balanced", style_profile, contract, reference_samples, user_instruction
            )
            for _ in range(n)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        variants = [r for r in results if isinstance(r, dict) and r.get("text", "").strip()]

        if not variants:
            logger.warning("best_of_n: all %d variants failed, returning empty", n)
            return {"mode": "best_of_n", "text": "", "usage": {}, "chunks_count": 0, "candidates_count": 0}

        # Score each variant with composite heuristic scorer.
        # roberta-base-openai-detector scores ALL GPT-4o text near 0.000 (useless).
        # CompositeHumanLikenessScorer combines perplexity + burstiness + marker count.
        try:
            from application.services.token_precision import build_best_of_n_scorer
            scorer = build_best_of_n_scorer()
            scored = [(v, scorer.score(v["text"])) for v in variants]
            scored.sort(key=lambda x: x[1])  # ascending: lower = more human-like
            best, best_score = scored[0]
            all_scores = [round(s, 3) for _, s in scored]
            logger.info(
                "best_of_n: %d variants scored — best=%.3f worst=%.3f",
                len(variants), best_score, scored[-1][1],
            )
        except Exception as exc:
            logger.warning("best_of_n: scoring failed (%s) — using first variant", exc)
            best = variants[0]
            best_score = None
            all_scores = []

        # Aggregate token usage across all variants
        total_usage: dict[str, int] = {}
        for v in variants:
            for k, val in v.get("usage", {}).items():
                total_usage[k] = total_usage.get(k, 0) + val

        return {
            "mode": "best_of_n",
            "text": best["text"],
            "usage": total_usage,
            "chunks_count": best.get("chunks_count", 1),
            "candidates_count": len(variants),
            "best_ai_score": round(best_score, 3) if best_score is not None else None,
            "all_ai_scores": all_scores,
        }

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
        """Token-level adversarial paraphrasing (Algorithm 1, Cheng et al. 2025).

        Uses HFPrecisionProvider (local CausalLM with logit access) + a guidance
        detector to select the most human-like token at each decoding step.
        Falls back to standard balanced generation if the local model is unavailable.
        """
        try:
            from application.services.token_precision import token_precision_engine
            # build_precision_prompt now returns the user text only.
            # PRECISION_SYSTEM_PROMPT (Figure 2 exact text) is passed as system_prompt
            # so the engine can place it in the chat template slot for LLaMA-3-8B-Instruct,
            # or prepend it as raw text for models without a chat template.
            user_text = build_precision_prompt(text, style_profile, contract)
            result = await token_precision_engine.generate_async(
                user_text, system_prompt=PRECISION_SYSTEM_PROMPT
            )
            if not result.get("text", "").strip():
                raise ValueError("Precision engine returned empty text")
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
        user_instruction: str | None = None,
    ) -> dict[str, Any]:
        ref = reference_samples[0] if reference_samples else None
        system = get_system_prompt(mode, ref)
        user = build_user_prompt(text, style_profile, contract, ref, user_instruction=user_instruction)
        response = await self._provider.generate(
            user,
            system_prompt=system,
            temperature=self._temperature_for_mode(mode),
        )
        result_text = response["text"]
        total_usage = dict(response.get("usage", {}))

        # Refinement pass: if AI markers still detected, do a targeted second pass
        if self._has_ai_markers(result_text):
            refinement_user = f"Text to refine:\n{result_text}"
            ref_response = await self._provider.generate(
                refinement_user,
                system_prompt=get_refinement_system_prompt(),
                temperature=self._temperature_for_mode(mode),
            )
            if ref_response.get("text", "").strip():
                result_text = ref_response["text"]
                for k, v in ref_response.get("usage", {}).items():
                    total_usage[k] = total_usage.get(k, 0) + v

        return {
            "mode": mode,
            "text": result_text,
            "usage": total_usage,
            "chunks_count": 1,
        }

    _AI_MARKER_PATTERNS = [
        # English
        "it is important to note", "it is worth", "it should be noted",
        "furthermore", "moreover", "in addition", "in conclusion", "to summarize",
        "in summary", "first and foremost", "absolutely", "undoubtedly", "certainly",
        "notably", "crucially", "essentially", "fundamentally",
        "in the realm of", "at its core", "at the heart of",
        # Russian
        "стоит отметить", "необходимо отметить", "следует отметить",
        "важно понимать", "нельзя не отметить", "таким образом",
        "в заключение", "подводя итог", "в целом", "безусловно",
        "несомненно", "очевидно", "действительно",
    ]

    def _has_ai_markers(self, text: str) -> bool:
        lower = text.lower()
        return any(marker in lower for marker in self._AI_MARKER_PATTERNS)

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
        user_instruction: str | None = None,
    ) -> dict[str, Any]:
        """Rewrite long text by splitting into paragraph-level chunks.

        Cross-chunk context: each chunk receives a 1-sentence summary of the
        previous chunk as context prefix, preserving narrative flow.
        """
        chunks = self._split_into_chunks(text)
        rewritten_chunks: list[str] = []
        total_usage: dict[str, int] = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        prev_context: str | None = None

        ref = reference_samples[0] if reference_samples else None
        system = get_system_prompt(mode, ref)
        for i, chunk in enumerate(chunks):
            user = build_user_prompt(
                chunk, style_profile, contract, ref,
                is_chunk=True, chunk_idx=i, total_chunks=len(chunks),
                prev_context=prev_context,
                user_instruction=user_instruction,
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
            except Exception as exc:
                # Re-raise provider/config errors so the task fails visibly
                from openai import APIConnectionError, APIStatusError, AuthenticationError
                if isinstance(exc, (RuntimeError, AuthenticationError, APIConnectionError, APIStatusError)):
                    raise
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
        return {"conservative": 0.75, "balanced": 0.90, "expressive": 1.05}.get(mode, 0.90)


guided_rewrite_engine = GuidedRewriteEngine()
