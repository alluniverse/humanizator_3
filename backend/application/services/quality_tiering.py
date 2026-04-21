"""Corpus Quality Tiering service: L1/L2/L3 classification."""

from __future__ import annotations

import re
from typing import Any

from domain.enums import QualityTier


class QualityTieringService:
    """Heuristic-based quality tiering for style samples.

    Based on docs/2501.03437v1 (Masrour et al., 2025):
    - L1: strong, clean, consistent style
    - L2: working but non-homogeneous
    - L3: noisy, weak, or conflicting material
    """

    L3_PATTERNS = [
        r"\[citation needed\]",
        r"\[source\?\]",
        r"\[ dubious \- discuss \]",
        r"\{\{cite",
        r"\{\{fact",
        r"asdf",  # keyboard mashing
        r"lorem ipsum",
    ]

    def __init__(self) -> None:
        self._l3_regex = re.compile(
            "|".join(self.L3_PATTERNS),
            flags=re.IGNORECASE,
        )

    def tier_sample(self, text: str) -> QualityTier:
        """Classify a single sample into L1/L2/L3."""
        text_lower = text.lower()

        # L3 detection: hallucinated citations, nonsensical insertions, placeholders
        if self._detect_l3(text_lower):
            return QualityTier.L3

        # L2 detection: short, overly generic, or low-variety text
        if self._detect_l2(text_lower):
            return QualityTier.L2

        return QualityTier.L1

    def _detect_l3(self, text: str) -> bool:
        if self._l3_regex.search(text):
            return True
        # Excessive repetition can indicate generated noise
        words = text.split()
        if len(words) > 20:
            unique_ratio = len(set(words)) / len(words)
            if unique_ratio < 0.3:
                return True
        # Very short or fragment-like
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        if len(sentences) < 2 and len(words) < 15:
            return True
        return False

    def _detect_l2(self, text: str) -> bool:
        words = text.split()
        if len(words) < 30:
            return True
        unique_ratio = len(set(words)) / len(words)
        if unique_ratio < 0.4:
            return True
        sentences = [s.strip() for s in text.split(".") if s.strip()]
        avg_len = sum(len(s.split()) for s in sentences) / max(len(sentences), 1)
        if avg_len < 5:
            return True
        return False

    def diagnose_library(
        self,
        samples: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute library-level diagnostics from sample tiers."""
        total = len(samples)
        if total == 0:
            return {
                "total_samples": 0,
                "l1_count": 0,
                "l2_count": 0,
                "l3_count": 0,
                "l1_ratio": 0.0,
                "l2_ratio": 0.0,
                "l3_ratio": 0.0,
                "is_valid_for_profiling": False,
                "warnings": ["Library is empty."],
                "recommendations": ["Upload at least 10–15 samples."],
            }

        l1 = sum(1 for s in samples if s.get("quality_tier") == QualityTier.L1)
        l2 = sum(1 for s in samples if s.get("quality_tier") == QualityTier.L2)
        l3 = sum(1 for s in samples if s.get("quality_tier") == QualityTier.L3)

        l1_ratio = round(l1 / total, 2)
        l2_ratio = round(l2 / total, 2)
        l3_ratio = round(l3 / total, 2)

        warnings: list[str] = []
        recommendations: list[str] = []

        is_valid = l1 >= max(1, total * 0.3)

        if total < 10:
            warnings.append("Library volume is below recommended minimum (10).")
            recommendations.append("Add more samples for a stable style profile.")
        if l3_ratio > 0.2:
            warnings.append(f"High L3 ratio ({l3_ratio:.0%}): noisy samples detected.")
            recommendations.append("Review and remove L3 samples before profiling.")
        if l1_ratio < 0.5:
            warnings.append("Less than 50% of samples are L1.")
            recommendations.append("Curate stronger reference texts for best results.")
        if l2_ratio > 0.5:
            warnings.append("Majority of samples are L2 (non-homogeneous).")
            recommendations.append("Consider splitting library into more focused subsets.")

        return {
            "total_samples": total,
            "l1_count": l1,
            "l2_count": l2,
            "l3_count": l3,
            "l1_ratio": l1_ratio,
            "l2_ratio": l2_ratio,
            "l3_ratio": l3_ratio,
            "is_valid_for_profiling": is_valid,
            "warnings": warnings,
            "recommendations": recommendations,
        }


quality_tiering_service = QualityTieringService()
