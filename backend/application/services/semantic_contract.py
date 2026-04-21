"""Semantic Contract Builder: extracts and protects meaning."""

from __future__ import annotations

import re
from typing import Any

import spacy


class SemanticContractBuilder:
    """Builds a semantic contract that protects meaning during rewrite."""

    def __init__(self) -> None:
        self._nlp_en = spacy.load("en_core_web_sm")
        self._nlp_ru = spacy.load("ru_core_news_sm")

    def _get_nlp(self, language: str) -> spacy.Language:
        return self._nlp_ru if language == "ru" else self._nlp_en

    def build_contract(
        self,
        text: str,
        mode: str = "balanced",
        language: str = "ru",
    ) -> dict[str, Any]:
        """Build a semantic contract for the given text."""
        nlp = self._get_nlp(language)
        doc = nlp(text)

        # Entities
        protected_entities = []
        for ent in doc.ents:
            protected_entities.append(
                {
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                }
            )

        # Numbers and dates
        numbers = [
            {"text": m.group(), "start": m.start(), "end": m.end()}
            for m in re.finditer(r"\b\d+[\d\s.,:/-]*\b", text)
        ]

        # Terminology (nouns that appear multiple times)
        noun_freq: dict[str, int] = {}
        for token in doc:
            if token.pos_ == "NOUN" and len(token.text) > 3:
                lemma = token.lemma_.lower()
                noun_freq[lemma] = noun_freq.get(lemma, 0) + 1
        key_terms = [n for n, c in noun_freq.items() if c >= 2]

        # Causal connectors
        causal_patterns = [
            "because", "since", "therefore", "thus", "as a result",
            "потому что", "так как", "поэтому", "в результате", "следовательно",
        ]
        causal_spans = []
        for pat in causal_patterns:
            for m in re.finditer(re.escape(pat), text, re.IGNORECASE):
                causal_spans.append({"text": m.group(), "start": m.start(), "end": m.end()})

        # Importance map
        importance_map = self._build_importance_map(doc, mode)

        # Rewrite constraints per mode
        mpr = {"strict": 0.2, "balanced": 0.4, "expressive": 0.6}.get(mode, 0.4)
        use_threshold = 0.75
        pos_constraint_flag = mode != "loose"

        return {
            "mode": mode,
            "protected_entities": protected_entities,
            "protected_numbers": numbers,
            "key_terms": key_terms,
            "causal_spans": causal_spans,
            "importance_map": importance_map,
            "constraints": {
                "maximum_perturbed_ratio": mpr,
                "use_similarity_threshold": use_threshold,
                "pos_constraint_flag": pos_constraint_flag,
            },
        }

    def _build_importance_map(self, doc: spacy.tokens.Doc, mode: str) -> list[dict[str, Any]]:
        """Classify tokens into must-preserve / high-risk / replaceable / style-flex."""
        mapping: list[dict[str, Any]] = []
        ent_spans = {(e.start, e.end): e.label_ for e in doc.ents}

        for token in doc:
            if token.is_space or token.is_punct:
                continue

            key = (token.i, token.i + 1)
            if key in ent_spans:
                category = "must-preserve"
            elif token.pos_ in {"NUM", "PROPN"}:
                category = "must-preserve"
            elif token.pos_ in {"NOUN", "VERB"} and mode == "strict":
                category = "high-risk"
            elif token.pos_ in {"ADJ", "ADV"}:
                category = "style-flex"
            else:
                category = "replaceable"

            mapping.append(
                {
                    "text": token.text,
                    "lemma": token.lemma_,
                    "pos": token.pos_,
                    "idx": token.i,
                    "category": category,
                }
            )

        return mapping


semantic_contract_builder = SemanticContractBuilder()
