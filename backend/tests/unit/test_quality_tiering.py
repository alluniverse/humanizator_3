"""Unit tests: QualityTieringService — pure rule-based logic."""

import pytest

from application.services.quality_tiering import QualityTieringService
from domain.enums import QualityTier

# Fresh instance per test (no shared state)
svc = QualityTieringService()

LONG_L1 = (
    "This film is a breathtaking masterpiece of visual storytelling that captivates "
    "audiences from the very first frame. Every single shot feels meticulously deliberate "
    "and purposeful, while the pacing consistently rewards patient viewers with depth."
)

# One sentence, <15 words → L3 (fragment)
SHORT_L3 = "Short bad text"

CITATION_L3 = "The fact [citation needed] is disputed by researchers [source?]."

REPETITIVE_L3 = " ".join(["word"] * 30)  # unique_ratio < 0.3

GENERIC_L2 = "This is good. Very good. So good. Very nice. Nice work. Well done."  # avg sent len < 5


class TestTierSample:
    def test_l1_long_diverse_text(self) -> None:
        assert svc.tier_sample(LONG_L1) == QualityTier.L1

    def test_l3_short_fragment(self) -> None:
        assert svc.tier_sample(SHORT_L3) == QualityTier.L3

    def test_l3_citation_needed(self) -> None:
        assert svc.tier_sample(CITATION_L3) == QualityTier.L3

    def test_l3_repetitive(self) -> None:
        assert svc.tier_sample(REPETITIVE_L3) == QualityTier.L3

    def test_l2_generic_short_sentences(self) -> None:
        assert svc.tier_sample(GENERIC_L2) == QualityTier.L2

    def test_l3_lorem_ipsum(self) -> None:
        assert svc.tier_sample("lorem ipsum dolor sit amet consectetur adipiscing elit") == QualityTier.L3

    def test_empty_string_is_l3(self) -> None:
        result = svc.tier_sample("")
        assert result == QualityTier.L3


class TestDiagnoseLibrary:
    def test_empty_library(self) -> None:
        result = svc.diagnose_library([])
        assert result["total_samples"] == 0
        assert result["is_valid_for_profiling"] is False
        assert result["warnings"]

    def test_all_l1(self) -> None:
        samples = [{"quality_tier": QualityTier.L1}] * 5
        result = svc.diagnose_library(samples)
        assert result["l1_count"] == 5
        assert result["l1_ratio"] == 1.0
        assert result["is_valid_for_profiling"] is True

    def test_mostly_l3_invalid(self) -> None:
        samples = [{"quality_tier": QualityTier.L3}] * 8 + [{"quality_tier": QualityTier.L1}]
        result = svc.diagnose_library(samples)
        assert result["l3_ratio"] >= 0.8
        assert result["is_valid_for_profiling"] is False

    def test_warning_for_high_l3(self) -> None:
        samples = [{"quality_tier": QualityTier.L3}] * 3 + [{"quality_tier": QualityTier.L1}] * 7
        result = svc.diagnose_library(samples)
        assert any("L3" in w for w in result["warnings"])

    def test_minimum_volume_warning(self) -> None:
        samples = [{"quality_tier": QualityTier.L1}] * 3
        result = svc.diagnose_library(samples)
        assert any("10" in w for w in result["warnings"])
