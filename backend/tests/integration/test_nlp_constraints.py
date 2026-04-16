"""Integration tests: NLP and constraint pipeline.

Tests SemanticContractBuilder and RewriteConstraintLayer
with mocked spacy / sentence-transformer to avoid loading
large models during CI. Uses pytest monkeypatch.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to build lightweight spacy mock docs
# ---------------------------------------------------------------------------


def _make_token(text: str, pos: str, lemma: str | None = None, is_space: bool = False, is_punct: bool = False) -> MagicMock:
    tok = MagicMock()
    tok.text = text
    tok.pos_ = pos
    tok.lemma_ = lemma or text.lower()
    tok.is_space = is_space
    tok.is_punct = is_punct
    tok.i = 0
    return tok


def _make_doc(tokens: list[MagicMock], ents: list[MagicMock] | None = None) -> MagicMock:
    doc = MagicMock()
    doc.__iter__ = MagicMock(return_value=iter(tokens))
    doc.ents = ents or []
    return doc


# ---------------------------------------------------------------------------
# SemanticContractBuilder tests
# ---------------------------------------------------------------------------


class TestSemanticContractBuilder:
    @pytest.fixture
    def builder(self) -> Any:
        with patch("application.services.semantic_contract.spacy.load") as mock_load:
            mock_nlp = MagicMock()
            mock_load.return_value = mock_nlp

            from application.services.semantic_contract import SemanticContractBuilder
            b = SemanticContractBuilder()
            b._nlp_en = mock_nlp
            b._nlp_ru = mock_nlp
            return b, mock_nlp

    def test_build_contract_structure(self, builder: Any) -> None:
        b, mock_nlp = builder
        # Minimal doc with one entity
        ent = MagicMock()
        ent.text = "OpenAI"
        ent.label_ = "ORG"
        ent.start_char = 0
        ent.end_char = 6

        tok1 = _make_token("OpenAI", "PROPN")
        tok2 = _make_token("released", "VERB")
        tok3 = _make_token("model", "NOUN")
        tok3.lemma_ = "model"

        doc = _make_doc([tok1, tok2, tok3], ents=[ent])
        mock_nlp.return_value = doc

        contract = b.build_contract("OpenAI released a model.", mode="balanced", language="en")

        assert "protected_entities" in contract
        assert "constraints" in contract
        assert "mode" in contract
        assert contract["mode"] == "balanced"
        assert contract["constraints"]["maximum_perturbed_ratio"] == 0.4

    def test_strict_mode_lower_mpr(self, builder: Any) -> None:
        b, mock_nlp = builder
        doc = _make_doc([])
        mock_nlp.return_value = doc

        contract = b.build_contract("Some text.", mode="strict")
        assert contract["constraints"]["maximum_perturbed_ratio"] == 0.2

    def test_expressive_mode_higher_mpr(self, builder: Any) -> None:
        b, mock_nlp = builder
        doc = _make_doc([])
        mock_nlp.return_value = doc

        contract = b.build_contract("Some text.", mode="expressive")
        assert contract["constraints"]["maximum_perturbed_ratio"] == 0.6

    def test_key_terms_extracted_from_repeated_nouns(self, builder: Any) -> None:
        b, mock_nlp = builder
        # Two tokens with the same lemma "model" — should appear in key_terms
        t1 = _make_token("models", "NOUN", lemma="model")
        t1.i = 0
        t2 = _make_token("modeling", "NOUN", lemma="model")
        t2.i = 1
        doc = _make_doc([t1, t2])
        mock_nlp.return_value = doc

        contract = b.build_contract("models modeling context text here.", language="en")
        assert "model" in contract["key_terms"]

    def test_causal_patterns_detected(self, builder: Any) -> None:
        b, mock_nlp = builder
        doc = _make_doc([])
        mock_nlp.return_value = doc

        text = "We chose this approach because it is faster."
        contract = b.build_contract(text, language="en")
        causal_texts = [s["text"].lower() for s in contract["causal_spans"]]
        assert "because" in causal_texts

    def test_importance_map_must_preserve_propn(self, builder: Any) -> None:
        b, mock_nlp = builder
        tok = _make_token("Tesla", "PROPN")
        tok.i = 0
        doc = _make_doc([tok])
        mock_nlp.return_value = doc

        contract = b.build_contract("Tesla.", language="en")
        categories = {e["text"]: e["category"] for e in contract["importance_map"]}
        assert categories.get("Tesla") == "must-preserve"


# ---------------------------------------------------------------------------
# RewriteConstraintLayer NLP tests (mock spacy + sentence-transformer)
# ---------------------------------------------------------------------------


class TestConstraintLayerNLP:
    @pytest.fixture
    def layer(self) -> Any:
        with (
            patch("constraints.rewrite_constraints.spacy.load") as mock_load,
            patch("constraints.rewrite_constraints.SentenceTransformer") as mock_st,
        ):
            mock_nlp = MagicMock()
            mock_load.return_value = mock_nlp

            # Mock sentence transformer to return unit vectors
            import torch
            mock_model = MagicMock()
            mock_st.return_value = mock_model

            from constraints.rewrite_constraints import RewriteConstraintLayer
            cl = RewriteConstraintLayer()
            cl._nlp_en = mock_nlp
            cl._nlp_ru = mock_nlp
            cl._sentence_model = mock_model
            return cl, mock_nlp, mock_model

    def test_pos_constraint_no_violations(self, layer: Any) -> None:
        cl, mock_nlp, _ = layer

        # Both docs have same POS for shared lemma
        tok_orig = _make_token("run", "VERB", lemma="run")
        tok_rewr = _make_token("run", "VERB", lemma="run")

        mock_nlp.side_effect = [
            _make_doc([tok_orig]),
            _make_doc([tok_rewr]),
        ]

        result = cl.check_pos_constraint("We run fast.", "We run quickly.", language="en")
        assert result["valid"] is True
        assert result["violations"] == []

    def test_pos_constraint_violation_detected(self, layer: Any) -> None:
        cl, mock_nlp, _ = layer

        # Original: "run" is VERB; rewritten: "run" becomes NOUN — violation
        tok_orig = _make_token("run", "VERB", lemma="run")
        tok_rewr = _make_token("run", "NOUN", lemma="run")

        mock_nlp.side_effect = [
            _make_doc([tok_orig]),
            _make_doc([tok_rewr]),
        ]

        result = cl.check_pos_constraint("We run.", "A run.", language="en")
        assert result["valid"] is False
        assert len(result["violations"]) == 1
        assert result["violations"][0]["token"] == "run"

    def test_use_similarity_above_threshold(self, layer: Any) -> None:
        import torch
        cl, _, mock_model = layer

        # Return tensors with cosine similarity ≈ 0.95
        v = torch.tensor([1.0, 0.0, 0.0]).unsqueeze(0)
        mock_model.encode.return_value = v

        result = cl.check_use_similarity("Original text.", "Rewritten text.", threshold=0.75)
        assert result["valid"] is True

    def test_use_similarity_below_threshold(self, layer: Any) -> None:
        import torch
        cl, _, mock_model = layer

        # Two orthogonal vectors → similarity = 0.0
        mock_model.encode.side_effect = [
            torch.tensor([[1.0, 0.0, 0.0]]),
            torch.tensor([[0.0, 1.0, 0.0]]),
        ]

        result = cl.check_use_similarity("Original.", "Completely different.", threshold=0.75)
        assert result["valid"] is False
        assert result["min_similarity"] < 0.75

    def test_validate_all_passes_clean_rewrite(self, layer: Any) -> None:
        import torch
        cl, mock_nlp, mock_model = layer

        # POS constraint: no shared lemmas → no violations
        mock_nlp.side_effect = [_make_doc([]), _make_doc([])]
        # USE: identical vectors
        v = torch.tensor([[1.0, 0.0]])
        mock_model.encode.return_value = v

        original = "The quick brown fox jumps over the lazy dog every single day"
        rewritten = "The quick brown fox jumps over the lazy dog every single day"
        contract = {
            "constraints": {"maximum_perturbed_ratio": 0.4, "use_similarity_threshold": 0.75, "pos_constraint_flag": True},
            "protected_entities": [],
            "protected_numbers": [],
        }
        result = cl.validate_all(original, rewritten, contract)
        assert result["valid"] is True
