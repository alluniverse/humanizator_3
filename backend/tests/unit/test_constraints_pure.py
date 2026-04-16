"""Unit tests: RewriteConstraintLayer — pure methods (no NLP models)."""

import pytest

from constraints.rewrite_constraints import RewriteConstraintLayer


class TestMprConstraint:
    """Maximum Perturbed Ratio — pure arithmetic, no model needed."""

    def _layer(self) -> RewriteConstraintLayer:
        # Instantiate without loading NLP models by bypassing __init__
        obj = object.__new__(RewriteConstraintLayer)
        return obj

    def test_identical_text_zero_ratio(self) -> None:
        layer = self._layer()
        text = "The quick brown fox jumps over the lazy dog"
        result = layer.check_mpr_constraint(text, text)
        assert result["valid"] is True
        assert result["ratio"] == 0.0

    def test_completely_different_text_exceeds_limit(self) -> None:
        layer = self._layer()
        original = "apple orange banana grape lemon pear"
        rewritten = "cat dog bird fish snake turtle"
        result = layer.check_mpr_constraint(original, rewritten, max_ratio=0.4)
        assert result["valid"] is False
        assert result["ratio"] > 0.4

    def test_small_change_within_limit(self) -> None:
        layer = self._layer()
        # Change only 1 word out of 10
        original = "the quick brown fox jumps over lazy dog now"
        rewritten = "the quick brown fox leaps over lazy dog now"
        result = layer.check_mpr_constraint(original, rewritten, max_ratio=0.4)
        assert result["valid"] is True

    def test_custom_max_ratio(self) -> None:
        layer = self._layer()
        original = "word1 word2 word3 word4 word5"
        rewritten = "wordA wordB word3 word4 word5"
        result = layer.check_mpr_constraint(original, rewritten, max_ratio=0.3)
        assert result["ratio"] == pytest.approx(0.4, abs=0.05)
        assert result["valid"] is False

    def test_length_difference_counted(self) -> None:
        layer = self._layer()
        original = "a b c d e"
        rewritten = "a b c d e f g h"  # 3 extra tokens
        result = layer.check_mpr_constraint(original, rewritten, max_ratio=0.4)
        assert result["changed_tokens"] >= 3


class TestProtectedSpans:
    """Protected span checks — pure string matching."""

    def _layer(self) -> RewriteConstraintLayer:
        return object.__new__(RewriteConstraintLayer)

    def test_all_protected_preserved(self) -> None:
        layer = self._layer()
        rewritten = "OpenAI released GPT-4 in 2023 with remarkable capabilities."
        spans = [{"text": "OpenAI"}, {"text": "GPT-4"}, {"text": "2023"}]
        result = layer.check_protected_spans(rewritten, spans)
        assert result["valid"] is True
        assert result["violations"] == []

    def test_missing_span_violation(self) -> None:
        layer = self._layer()
        rewritten = "A company released a model with remarkable capabilities."
        spans = [{"text": "OpenAI"}, {"text": "GPT-4"}]
        result = layer.check_protected_spans(rewritten, spans)
        assert result["valid"] is False
        assert len(result["violations"]) == 2

    def test_empty_protected_spans(self) -> None:
        layer = self._layer()
        result = layer.check_protected_spans("any text here", [])
        assert result["valid"] is True

    def test_partial_preservation(self) -> None:
        layer = self._layer()
        rewritten = "The report mentions 2023 results."
        spans = [{"text": "2023"}, {"text": "OpenAI"}]
        result = layer.check_protected_spans(rewritten, spans)
        assert result["valid"] is False
        missing_texts = [v["missing"] for v in result["violations"]]
        assert "OpenAI" in missing_texts
        assert "2023" not in missing_texts
