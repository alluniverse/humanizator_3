"""Unit tests: TokenPrecisionEngine and helper utilities (no model loading)."""

from unittest.mock import MagicMock, patch
from typing import Any

import pytest
import torch

from application.services.token_precision import (
    TokenPrecisionEngine,
    SimpleAIScorer,
    _top_p_top_k_filter,
    DEFAULT_TOP_K,
    DEFAULT_TOP_P,
)
from rewrite.prompts import build_precision_prompt


# ---------------------------------------------------------------------------
# Filter helpers
# ---------------------------------------------------------------------------


class TestTopPTopKFilter:
    def test_top_k_limits_candidates(self) -> None:
        logits = torch.randn(1000)
        filtered = _top_p_top_k_filter(logits.clone(), top_k=10, top_p=1.0)
        finite_count = (filtered > float("-inf")).sum().item()
        assert finite_count <= 10

    def test_top_p_limits_cumulative(self) -> None:
        # Uniform logits: top_p=0.01 should keep only 1% of vocab
        logits = torch.zeros(1000)
        filtered = _top_p_top_k_filter(logits.clone(), top_k=1000, top_p=0.01)
        finite_count = (filtered > float("-inf")).sum().item()
        assert finite_count <= 15  # allow a bit of slack for rounding

    def test_full_top_k_top_p_combined(self) -> None:
        logits = torch.randn(500)
        filtered = _top_p_top_k_filter(logits.clone(), top_k=50, top_p=0.99)
        finite_count = (filtered > float("-inf")).sum().item()
        assert 1 <= finite_count <= 50

    def test_no_filter_passthrough(self) -> None:
        logits = torch.randn(100)
        filtered = _top_p_top_k_filter(logits.clone(), top_k=0, top_p=1.0)
        # top_k=0 means no top-k filter applied
        assert (filtered > float("-inf")).all()


# ---------------------------------------------------------------------------
# SimpleAIScorer
# ---------------------------------------------------------------------------


class TestSimpleAIScorer:
    def test_score_returns_float_in_range(self) -> None:
        scorer = SimpleAIScorer()
        # Without loading model, patch _load and _model
        scorer._model = MagicMock()
        scorer._tokenizer = MagicMock()
        scorer._torch = torch

        mock_tokens = {"input_ids": torch.ones(1, 5, dtype=torch.long)}
        scorer._tokenizer.return_value = mock_tokens
        mock_loss = MagicMock()
        mock_loss.item.return_value = 3.0
        scorer._model.return_value.loss = mock_loss

        score = scorer.score("This is a test sentence for scoring purposes.")
        assert 0.0 <= score <= 1.0

    def test_empty_text_returns_neutral(self) -> None:
        scorer = SimpleAIScorer()
        assert scorer.score("") == 0.5
        assert scorer.score("   ") == 0.5


# ---------------------------------------------------------------------------
# Precision prompt builder
# ---------------------------------------------------------------------------


class TestBuildPrecisionPrompt:
    def test_basic_prompt_contains_text(self) -> None:
        text = "Artificial intelligence is transforming industries worldwide."
        prompt = build_precision_prompt(text)
        assert text in prompt
        assert "Rephrased:" in prompt

    def test_contract_entities_in_prompt(self) -> None:
        text = "Tesla launched a new vehicle."
        contract = {
            "protected_entities": [{"text": "Tesla"}],
            "protected_numbers": [],
            "key_terms": ["vehicle"],
        }
        prompt = build_precision_prompt(text, contract=contract)
        assert "Tesla" in prompt

    def test_style_profile_adds_formality(self) -> None:
        text = "Some text here."
        profile = {"guidance_signals": {"target_formality": "formal"}}
        prompt = build_precision_prompt(text, style_profile=profile)
        assert "formal" in prompt.lower()

    def test_no_profile_no_contract_is_concise(self) -> None:
        text = "Short text."
        prompt = build_precision_prompt(text)
        # Should be under 300 chars for efficiency
        assert len(prompt) < 500


# ---------------------------------------------------------------------------
# TokenPrecisionEngine (mocked provider)
# ---------------------------------------------------------------------------


def _make_engine() -> tuple[TokenPrecisionEngine, Any]:
    """Return engine + mock provider for testing without real model."""
    engine = TokenPrecisionEngine.__new__(TokenPrecisionEngine)
    engine.top_k = DEFAULT_TOP_K
    engine.top_p = DEFAULT_TOP_P
    engine.max_new_tokens = 5  # small for tests

    # Mock AI scorer: always returns 0.5
    mock_scorer = MagicMock(spec=SimpleAIScorer)
    mock_scorer.score.return_value = 0.5
    engine._ai_scorer = mock_scorer

    # Mock provider
    mock_provider = MagicMock()
    vocab_size = 100
    # next_token_logits returns uniform logits
    mock_provider.next_token_logits.return_value = torch.zeros(vocab_size)
    # encode returns tensor
    mock_provider.encode.return_value = torch.zeros(1, 3, dtype=torch.long)
    # decode_tokens returns readable string
    mock_provider.decode_tokens.side_effect = lambda ids: "word" if ids else ""
    mock_provider.eos_token_id = 0
    mock_provider.device = "cpu"
    engine._provider = mock_provider

    return engine, mock_provider


class TestTokenPrecisionEngine:
    def test_generate_returns_structure(self) -> None:
        engine, _ = _make_engine()
        result = engine.generate("Rephrase this sentence for natural reading.")
        assert "text" in result
        assert "tokens_generated" in result
        assert "steps" in result
        assert result["algorithm"] == "token_precision_v1"

    def test_steps_count_matches_tokens(self) -> None:
        engine, mock_provider = _make_engine()
        # Make EOS never trigger until max_new_tokens
        mock_provider.eos_token_id = 99999
        result = engine.generate("Test prompt")
        assert len(result["steps"]) == result["tokens_generated"]

    def test_eos_terminates_early(self) -> None:
        engine, mock_provider = _make_engine()
        # Set eos_token_id to 0 (same as argmax of zeros logits) → stops at step 1
        mock_provider.eos_token_id = 0
        # next_token_logits: top candidate should be 0
        logits = torch.zeros(100)
        logits[0] = 10.0  # id=0 strongly preferred
        mock_provider.next_token_logits.return_value = logits
        result = engine.generate("Test")
        assert result["tokens_generated"] == 1  # EOS on first token

    def test_fallback_on_provider_error(self) -> None:
        """Engine should propagate exceptions (fallback handled at caller level)."""
        engine = TokenPrecisionEngine.__new__(TokenPrecisionEngine)
        engine.top_k = 50
        engine.top_p = 0.99
        engine.max_new_tokens = 5
        engine._ai_scorer = MagicMock()
        engine._ai_scorer.score.return_value = 0.5

        broken_provider = MagicMock()
        broken_provider.encode.side_effect = RuntimeError("model unavailable")
        engine._provider = broken_provider

        with pytest.raises(RuntimeError, match="model unavailable"):
            engine.generate("prompt")
