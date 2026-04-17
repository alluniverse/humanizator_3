"""Style conflict detector for style libraries.

Identifies samples whose stylistic signature deviates significantly from the
library median, indicating a mixed or incoherent corpus. Uses:
  - Burstiness (CV of sentence lengths)
  - Average sentence length
  - Lexical diversity (type-token ratio)
  - Formality proxy (ratio of function words to content words)

Each sample is scored against the library median. Samples whose z-score
exceeds the outlier_threshold (default 2.0) on ≥2 dimensions are flagged
as conflicting.
"""

from __future__ import annotations

import math
import re
from typing import Any


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]


def _words(text: str) -> list[str]:
    return re.findall(r"\b\w+\b", text.lower())


_FUNCTION_WORDS = frozenset(
    "a an the is are was were be been being have has had do does did "
    "will would shall should may might can could must and or but nor "
    "so yet for as if when while although because since though that "
    "this these those in on at by to of from with about through ".split()
    + "я ты он она мы вы они это это тот та те в на с по к у за из "
      "и а но да или не же ли бы то что как так уже ещё вот тоже".split()
)


def _extract_features(text: str) -> dict[str, float]:
    """Compute stylometric features for a single text."""
    sents = _sentences(text)
    words_list = _words(text)

    n_sents = max(len(sents), 1)
    n_words = max(len(words_list), 1)

    sent_lengths = [len(_words(s)) for s in sents] or [0]
    avg_sent_len = sum(sent_lengths) / n_sents

    # Burstiness = CV of sentence lengths
    if n_sents > 1:
        mean_l = avg_sent_len
        std_l = math.sqrt(sum((l - mean_l) ** 2 for l in sent_lengths) / n_sents)
        burstiness = std_l / mean_l if mean_l > 0 else 0.0
    else:
        burstiness = 0.0

    # Lexical diversity (type-token ratio)
    ttr = len(set(words_list)) / n_words

    # Formality: ratio of function words
    func_count = sum(1 for w in words_list if w in _FUNCTION_WORDS)
    formality = func_count / n_words

    return {
        "avg_sent_len": avg_sent_len,
        "burstiness": burstiness,
        "ttr": ttr,
        "formality": formality,
    }


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2


def _stdev(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 1.0  # avoid division by zero; no variance if single sample
    return math.sqrt(sum((v - mean) ** 2 for v in values) / len(values))


class StyleConflictDetector:
    """Detects stylistic outliers in a style library corpus."""

    def __init__(self, outlier_threshold: float = 2.0) -> None:
        self._outlier_threshold = outlier_threshold

    def detect_conflicts(
        self,
        samples: list[dict[str, Any]],
        outlier_threshold: float | None = None,
    ) -> dict[str, Any]:
        """Analyse a list of samples for style conflicts.

        Args:
            samples: list of dicts with at minimum {"id": ..., "content": str}.
            outlier_threshold: z-score threshold to flag a dimension as conflicting.
                               Overrides instance default if provided.

        Returns:
            {
              "has_conflicts": bool,
              "conflict_count": int,
              "outliers": [{"id", "content_preview", "deviating_dimensions", "z_scores"}],
              "library_profile": {"avg_sent_len", "burstiness", "ttr", "formality"},
              "recommendations": [str],
            }
        """
        threshold = outlier_threshold if outlier_threshold is not None else self._outlier_threshold

        if len(samples) < 3:
            return {
                "has_conflicts": False,
                "conflict_count": 0,
                "outliers": [],
                "library_profile": {},
                "recommendations": ["Need at least 3 samples for conflict detection."],
            }

        # Extract features for all samples
        features_list: list[dict[str, float]] = []
        for s in samples:
            content = s.get("content", "")
            features_list.append(_extract_features(content))

        dims = ["avg_sent_len", "burstiness", "ttr", "formality"]

        # Library-level statistics
        dim_values: dict[str, list[float]] = {d: [f[d] for f in features_list] for d in dims}
        dim_means = {d: sum(vs) / len(vs) for d, vs in dim_values.items()}
        dim_stds = {d: _stdev(dim_values[d], dim_means[d]) for d in dims}

        library_profile = {d: round(dim_means[d], 3) for d in dims}

        # Score each sample
        outliers: list[dict[str, Any]] = []
        for i, (sample, feats) in enumerate(zip(samples, features_list)):
            z_scores: dict[str, float] = {}
            for d in dims:
                std = dim_stds[d]
                z = abs(feats[d] - dim_means[d]) / std if std > 0 else 0.0
                z_scores[d] = round(z, 2)

            deviating = [d for d, z in z_scores.items() if z >= threshold]
            if len(deviating) >= 2:
                content = sample.get("content", "")
                outliers.append(
                    {
                        "id": sample.get("id", f"sample_{i}"),
                        "content_preview": content[:120] + ("..." if len(content) > 120 else ""),
                        "deviating_dimensions": deviating,
                        "z_scores": z_scores,
                        "features": {d: round(feats[d], 3) for d in dims},
                    }
                )

        recommendations: list[str] = []
        if outliers:
            recommendations.append(
                f"{len(outliers)} sample(s) have conflicting style — consider removing or moving to a separate library."
            )
        high_burst_outliers = [o for o in outliers if "burstiness" in o["deviating_dimensions"]]
        if high_burst_outliers:
            recommendations.append("Burstiness outliers detected: check for very short or very long sentences.")
        high_ttr_outliers = [o for o in outliers if "ttr" in o["deviating_dimensions"]]
        if high_ttr_outliers:
            recommendations.append("TTR outliers: some samples may be too repetitive or too vocabulary-dense.")

        return {
            "has_conflicts": len(outliers) > 0,
            "conflict_count": len(outliers),
            "total_samples": len(samples),
            "outliers": outliers,
            "library_profile": library_profile,
            "recommendations": recommendations,
        }


style_conflict_detector = StyleConflictDetector()
