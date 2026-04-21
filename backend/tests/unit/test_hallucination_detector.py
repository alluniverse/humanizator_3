"""Unit tests: HallucinationDetector — pure checks (no sentence-transformer)."""

from unittest.mock import MagicMock, patch

import pytest

from application.services.hallucination_detector import HallucinationDetector


def _detector() -> HallucinationDetector:
    """Create detector without loading sentence-transformer model."""
    obj = object.__new__(HallucinationDetector)
    obj._sentence_model = MagicMock()
    return obj


class TestEntityDrift:
    def test_no_contract_passes(self) -> None:
        det = _detector()
        result = det._check_entity_drift("Original.", "Rewritten.", contract=None)
        assert result["passed"] is True

    def test_all_entities_present_passes(self) -> None:
        det = _detector()
        contract = {
            "protected_entities": [{"text": "Tesla"}, {"text": "Musk"}],
            "protected_numbers": [],
            "key_terms": [],
        }
        result = det._check_entity_drift("...", "Tesla and Musk announced...", contract)
        assert result["passed"] is True
        assert result["missing"] == []

    def test_missing_entity_fails(self) -> None:
        det = _detector()
        contract = {
            "protected_entities": [{"text": "OpenAI"}],
            "protected_numbers": [{"text": "2023"}],
            "key_terms": [],
        }
        result = det._check_entity_drift("...", "A company announced something.", contract)
        assert result["passed"] is False
        assert "OpenAI" in result["missing"]
        assert "2023" in result["missing"]


class TestStructuralArtifacts:
    def test_clean_text_passes(self) -> None:
        det = _detector()
        text = "This is a complete and well-formed rewritten sentence with sufficient length."
        result = det._check_structural_artifacts(text)
        assert result["passed"] is True
        assert result["issues"] == []

    def test_truncation_marker_fails(self) -> None:
        det = _detector()
        result = det._check_structural_artifacts("This text ends abruptly...")
        assert result["passed"] is False
        assert any("truncation" in issue for issue in result["issues"])

    def test_repeated_ngrams_fails(self) -> None:
        det = _detector()
        # Repeat the same 5-gram 3+ times
        phrase = "the quick brown fox jumps"
        text = f"{phrase} over the lazy dog. {phrase} over the lazy dog. {phrase} over."
        result = det._check_structural_artifacts(text)
        assert result["passed"] is False
        assert any("repeated" in issue for issue in result["issues"])

    def test_very_short_output_fails(self) -> None:
        det = _detector()
        result = det._check_structural_artifacts("Too short.")
        assert result["passed"] is False
        assert any("short" in issue for issue in result["issues"])


class TestLengthRatio:
    def test_same_length_passes(self) -> None:
        det = _detector()
        text = "word " * 50
        result = det._check_length_ratio(text, text, (0.5, 2.0))
        assert result["passed"] is True
        assert result["ratio"] == pytest.approx(1.0)

    def test_too_short_fails(self) -> None:
        det = _detector()
        original = "word " * 100
        rewritten = "word " * 10  # ratio = 0.1 < 0.5
        result = det._check_length_ratio(original, rewritten, (0.5, 2.0))
        assert result["passed"] is False
        assert result["ratio"] < 0.5

    def test_too_long_fails(self) -> None:
        det = _detector()
        original = "word " * 10
        rewritten = "word " * 50  # ratio = 5.0 > 2.0
        result = det._check_length_ratio(original, rewritten, (0.5, 2.0))
        assert result["passed"] is False
        assert result["ratio"] > 2.0

    def test_within_bounds_passes(self) -> None:
        det = _detector()
        original = "word " * 50
        rewritten = "word " * 60  # ratio = 1.2
        result = det._check_length_ratio(original, rewritten, (0.5, 2.0))
        assert result["passed"] is True


class TestDetectIntegration:
    def test_clean_rewrite_passes(self) -> None:
        det = _detector()

        import torch
        mock_model = MagicMock()
        # Identical embeddings → similarity = 1.0
        v = torch.tensor([1.0, 0.0, 0.0])
        mock_model.encode.return_value = v
        det._sentence_model = mock_model

        original = "Tesla launched a new vehicle model in 2023 with impressive range."
        rewritten = "Tesla released an electric car in 2023 featuring exceptional battery range."
        contract = {
            "protected_entities": [{"text": "Tesla"}],
            "protected_numbers": [{"text": "2023"}],
            "key_terms": [],
        }
        result = det.detect(original, rewritten, contract=contract)
        assert result["passed"] is True
        assert "checks" in result
        assert "score" in result

    def test_missing_entity_fails_detect(self) -> None:
        det = _detector()

        import torch
        v = torch.tensor([1.0, 0.0, 0.0])
        det._sentence_model.encode.return_value = v

        original = "NASA launched the James Webb telescope in 2021."
        rewritten = "A space agency launched a telescope recently."
        contract = {
            "protected_entities": [{"text": "NASA"}, {"text": "James Webb"}],
            "protected_numbers": [{"text": "2021"}],
            "key_terms": [],
        }
        result = det.detect(original, rewritten, contract=contract)
        assert result["passed"] is False
        assert result["checks"]["entity_drift"]["passed"] is False
