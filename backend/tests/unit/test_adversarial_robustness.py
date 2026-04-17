"""Unit tests: AdversarialRobustnessEvaluator — pure attack logic (no sentence-transformer)."""

from unittest.mock import MagicMock

import torch

from application.services.adversarial_robustness import (
    AdversarialRobustnessEvaluator,
    ATTACK_REGISTRY,
    _attack_char_substitution,
    _attack_negation_flip,
    _attack_sentence_shuffle,
    _attack_tag_injection,
    _attack_word_deletion,
)


# ---------------------------------------------------------------------------
# Attack function tests
# ---------------------------------------------------------------------------


class TestCharSubstitution:
    def test_output_differs_from_input(self) -> None:
        text = "Tesla launched a new vehicle model in 2023."
        result = _attack_char_substitution(text)
        # Some chars should be replaced
        assert result != text or len(text) == 0

    def test_same_length(self) -> None:
        text = "The quick brown fox."
        assert len(_attack_char_substitution(text)) == len(text)

    def test_deterministic(self) -> None:
        text = "OpenAI announced new capabilities."
        assert _attack_char_substitution(text, seed=1) == _attack_char_substitution(text, seed=1)


class TestWordDeletion:
    def test_output_shorter_than_input(self) -> None:
        text = "The artificial intelligence model produces excellent results every single time."
        result = _attack_word_deletion(text, rate=0.3)
        assert len(result.split()) < len(text.split())

    def test_single_word_unchanged(self) -> None:
        # With 1 word the only candidate may be removed but output should not crash
        result = _attack_word_deletion("Hello", rate=1.0)
        assert isinstance(result, str)

    def test_deterministic(self) -> None:
        text = "Neural networks are capable of recognizing complex patterns in data."
        assert _attack_word_deletion(text, seed=7) == _attack_word_deletion(text, seed=7)


class TestSentenceShuffle:
    def test_single_sentence_unchanged(self) -> None:
        text = "This is a single sentence without any period at the end"
        assert _attack_sentence_shuffle(text) == text

    def test_multi_sentence_shuffled(self) -> None:
        text = "First sentence. Second sentence. Third sentence."
        # Not guaranteed to differ (if shuffle returns same order), but should not crash
        result = _attack_sentence_shuffle(text)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_preserves_all_words(self) -> None:
        text = "Apple is red. Banana is yellow. Cherry is dark."
        result = _attack_sentence_shuffle(text)
        assert sorted(result.split()) == sorted(text.split())


class TestTagInjection:
    def test_injects_tags_around_multiword_caps(self) -> None:
        text = "Elon Musk founded SpaceX back in 2002."
        result = _attack_tag_injection(text)
        assert "<TAG>" in result

    def test_plain_lowercase_unchanged(self) -> None:
        text = "the quick brown fox jumps over the lazy dog"
        result = _attack_tag_injection(text)
        assert result == text


class TestNegationFlip:
    def test_inserts_not_after_modal(self) -> None:
        result = _attack_negation_flip("This is very important.")
        assert "NOT" in result

    def test_only_first_occurrence(self) -> None:
        text = "This is important and it is correct."
        result = _attack_negation_flip(text)
        assert result.count("NOT") == 1

    def test_no_modal_unchanged(self) -> None:
        text = "The sun rises in the east."
        result = _attack_negation_flip(text)
        # No auxiliary/modal in sentence → unchanged
        assert result == text


# ---------------------------------------------------------------------------
# Evaluator integration
# ---------------------------------------------------------------------------


def _evaluator() -> AdversarialRobustnessEvaluator:
    """Create evaluator without loading sentence-transformer."""
    obj = AdversarialRobustnessEvaluator.__new__(AdversarialRobustnessEvaluator)
    mock_model = MagicMock()
    v = torch.tensor([1.0, 0.0, 0.0])
    mock_model.encode.return_value = v
    obj._model = mock_model
    return obj


class TestEvaluatorIntegration:
    def test_all_attacks_registered(self) -> None:
        expected = {"char_substitution", "word_deletion", "sentence_shuffle", "tag_injection", "negation_flip"}
        assert expected.issubset(set(ATTACK_REGISTRY.keys()))

    def test_identical_embeddings_passes(self) -> None:
        ev = _evaluator()
        text = "Tesla launched a new vehicle model in 2023 with impressive range capabilities."
        result = ev.evaluate(text, attacks=["tag_injection", "negation_flip"])
        # All embeddings identical (mock returns same vector) → similarity = 1.0 → passes
        assert result["passed"] is True
        assert result["mean_similarity"] == 1.0
        assert result["fragile_attacks"] == []

    def test_result_structure(self) -> None:
        ev = _evaluator()
        text = "This is a test sentence for robustness evaluation purposes."
        result = ev.evaluate(text)
        assert "passed" in result
        assert "mean_similarity" in result
        assert "threshold" in result
        assert "attack_results" in result
        assert "fragile_attacks" in result

    def test_subset_attacks(self) -> None:
        ev = _evaluator()
        text = "OpenAI released a new language model in 2024."
        result = ev.evaluate(text, attacks=["char_substitution", "word_deletion"])
        assert set(result["attack_results"].keys()) == {"char_substitution", "word_deletion"}

    def test_low_similarity_fails(self) -> None:
        ev = _evaluator()
        # Override mock to return orthogonal vectors for perturbed text
        call_count = [0]
        original_vec = torch.tensor([1.0, 0.0, 0.0])
        perturbed_vec = torch.tensor([0.0, 1.0, 0.0])  # orthogonal → similarity = 0.0

        def encode_side_effect(text, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return original_vec
            return perturbed_vec

        ev._model.encode.side_effect = encode_side_effect

        text = "This is important content that should remain stable under perturbations."
        result = ev.evaluate(text, attacks=["tag_injection"], semantic_threshold=0.75)
        assert result["passed"] is False
        assert result["mean_similarity"] < 0.75
