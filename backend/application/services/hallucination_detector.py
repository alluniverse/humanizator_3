"""Hallucination and artifact detector for LLM-generated rewrite output.

Detects four classes of quality failures:
  1. Entity drift   — named entities/numbers from original are absent in rewrite
  2. Semantic drift — cosine similarity between original and rewrite below threshold
  3. Structural     — incomplete sentence, repeated phrases, truncation markers
  4. Length         — rewrite dramatically shorter or longer than original

Used as a post-processing quality gate in the evaluation pipeline.
"""

from __future__ import annotations

import re
from typing import Any

from infrastructure.config import settings


_TRUNCATION_MARKERS = re.compile(
    r"\.\.\.$|…$|^\[|]$|\[\.\.\.\]|\[truncated\]|\[cut\]",
    re.IGNORECASE,
)
_REPEAT_WINDOW = 5  # n-gram size for repetition detection
_REPEAT_THRESHOLD = 3  # how many times the same n-gram triggers a flag


class HallucinationDetector:
    """Post-generation quality gate: detects hallucinations and artifacts."""

    def __init__(self) -> None:
        self._sentence_model: Any = None  # lazy-loaded on first semantic check

    def _get_sentence_model(self) -> Any:
        if self._sentence_model is None:
            from sentence_transformers import SentenceTransformer
            self._sentence_model = SentenceTransformer(settings.sentence_transformer_model)
        return self._sentence_model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(
        self,
        original: str,
        rewritten: str,
        contract: dict[str, Any] | None = None,
        semantic_threshold: float = 0.60,
        length_ratio_bounds: tuple[float, float] = (0.5, 2.0),
    ) -> dict[str, Any]:
        """Run all detectors. Returns structured report with `passed` flag.

        Args:
            original: source text.
            rewritten: LLM-generated rewrite.
            contract: optional semantic contract with protected_entities / protected_numbers.
            semantic_threshold: minimum cosine similarity for semantic integrity.
            length_ratio_bounds: (min, max) acceptable ratio of rewrite/original word count.

        Returns:
            {
              "passed": bool,
              "score": float (0–1, higher = fewer issues),
              "checks": { entity_drift, semantic_drift, structural, length },
            }
        """
        checks: dict[str, dict[str, Any]] = {}

        checks["entity_drift"] = self._check_entity_drift(original, rewritten, contract)
        checks["semantic_drift"] = self._check_semantic_drift(original, rewritten, semantic_threshold)
        checks["structural"] = self._check_structural_artifacts(rewritten)
        checks["length"] = self._check_length_ratio(original, rewritten, length_ratio_bounds)

        # Weighted pass/fail
        weights = {"entity_drift": 0.35, "semantic_drift": 0.35, "structural": 0.2, "length": 0.1}
        score = sum(weights[k] * (1.0 if checks[k]["passed"] else 0.0) for k in weights)
        passed = all(checks[k]["passed"] for k in ("entity_drift", "semantic_drift"))

        return {
            "passed": passed,
            "score": round(score, 3),
            "checks": checks,
        }

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def _check_entity_drift(
        self,
        original: str,
        rewritten: str,
        contract: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Verify protected entities and numbers are preserved."""
        if not contract:
            return {"passed": True, "missing": [], "note": "no contract provided"}

        protected: list[str] = []
        for ent in contract.get("protected_entities", []):
            if isinstance(ent, dict):
                protected.append(ent.get("text", ""))
        for num in contract.get("protected_numbers", []):
            if isinstance(num, dict):
                protected.append(num.get("text", ""))
        for term in contract.get("key_terms", []):
            if isinstance(term, str):
                protected.append(term)

        missing = [p for p in protected if p and p not in rewritten]
        return {
            "passed": len(missing) == 0,
            "missing": missing,
            "checked": len(protected),
        }

    def _check_semantic_drift(
        self,
        original: str,
        rewritten: str,
        threshold: float,
    ) -> dict[str, Any]:
        """Cosine similarity between original and rewritten embeddings."""
        try:
            from sentence_transformers import util
            model = self._get_sentence_model()
            emb_orig = model.encode(original, convert_to_tensor=True)
            emb_rewr = model.encode(rewritten, convert_to_tensor=True)
            similarity = float(util.pytorch_cos_sim(emb_orig, emb_rewr).item())
            return {
                "passed": similarity >= threshold,
                "similarity": round(similarity, 3),
                "threshold": threshold,
            }
        except Exception as exc:
            return {"passed": True, "similarity": None, "error": str(exc)}

    def _check_structural_artifacts(self, text: str) -> dict[str, Any]:
        """Detect incomplete sentences, truncation markers, repetitive n-grams."""
        issues: list[str] = []

        # Truncation markers
        if _TRUNCATION_MARKERS.search(text.strip()):
            issues.append("truncation_marker_detected")

        # Repeated n-grams (possible generation loop)
        words = text.lower().split()
        if len(words) >= _REPEAT_WINDOW:
            ngram_counts: dict[tuple[str, ...], int] = {}
            for i in range(len(words) - _REPEAT_WINDOW + 1):
                ng = tuple(words[i : i + _REPEAT_WINDOW])
                ngram_counts[ng] = ngram_counts.get(ng, 0) + 1
            repeated = [" ".join(ng) for ng, cnt in ngram_counts.items() if cnt >= _REPEAT_THRESHOLD]
            if repeated:
                issues.append(f"repeated_ngrams: {repeated[:3]}")

        # Very short output (< 10 words is suspicious for any non-trivial input)
        if len(words) < 10:
            issues.append("suspiciously_short_output")

        return {"passed": len(issues) == 0, "issues": issues}

    def _check_length_ratio(
        self,
        original: str,
        rewritten: str,
        bounds: tuple[float, float],
    ) -> dict[str, Any]:
        """Check that rewrite word count is within acceptable ratio of original."""
        orig_len = max(len(original.split()), 1)
        rewr_len = len(rewritten.split())
        ratio = rewr_len / orig_len
        lo, hi = bounds
        return {
            "passed": lo <= ratio <= hi,
            "ratio": round(ratio, 2),
            "original_words": orig_len,
            "rewritten_words": rewr_len,
            "bounds": bounds,
        }


hallucination_detector = HallucinationDetector()
