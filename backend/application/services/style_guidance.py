"""Style Guidance Engine: scores and ranks rewrite candidates."""

from __future__ import annotations

from typing import Any

import spacy


class StyleGuidanceEngine:
    """Scores rewrite candidates against a target style profile."""

    def __init__(self) -> None:
        self._nlp_en = spacy.load("en_core_web_sm")
        self._nlp_ru = spacy.load("ru_core_news_sm")

    def _get_nlp(self, language: str) -> spacy.Language:
        return self._nlp_ru if language == "ru" else self._nlp_en

    def score_variant(
        self,
        variant_text: str,
        style_profile: dict[str, Any],
        original_text: str,
        language: str = "ru",
    ) -> dict[str, Any]:
        """Score a single variant against style, semantic safety, and editorial quality."""
        nlp = self._get_nlp(language)
        doc = nlp(variant_text)

        sent_lengths = [len(sent) for sent in doc.sents]
        mean_sent = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0.0

        target_mean = style_profile.get("guidance_signals", {}).get("target_sentence_length", mean_sent)
        target_burstiness = style_profile.get("guidance_signals", {}).get("target_burstiness", 0.5)
        target_formality = style_profile.get("guidance_signals", {}).get("target_formality", 0.5)

        # Style match components
        length_match = 1.0 - min(abs(mean_sent - target_mean) / max(target_mean, 1), 1.0)

        var_sent = (
            sum((x - mean_sent) ** 2 for x in sent_lengths) / len(sent_lengths)
            if sent_lengths
            else 0.0
        )
        burstiness = (var_sent ** 0.5) / mean_sent if mean_sent > 0 else 0.0
        burstiness_match = 1.0 - min(abs(burstiness - target_burstiness), 1.0)

        # Formality proxy
        formal = sum(1 for token in doc if token.pos_ in {"NOUN", "ADJ"})
        informal = sum(1 for token in doc if token.pos_ in {"PRON", "INTJ"})
        formality = formal / (formal + informal) if (formal + informal) else 0.5
        formality_match = 1.0 - min(abs(formality - target_formality), 1.0)

        style_score = (length_match + burstiness_match + formality_match) / 3.0

        # Semantic preservation (simple token overlap)
        orig_tokens = set(t.lemma_.lower() for t in nlp(original_text) if not t.is_space and not t.is_punct)
        var_tokens = set(t.lemma_.lower() for t in doc if not t.is_space and not t.is_punct)
        overlap = len(orig_tokens & var_tokens) / max(len(orig_tokens), 1)
        semantic_score = overlap

        # Penalties
        penalties = 0.0
        avoid_markers = style_profile.get("lexical_signature", {}).get("avoid_markers", [])
        for marker in avoid_markers:
            if marker.lower() in variant_text.lower():
                penalties += 0.1

        composite = 0.4 * semantic_score + 0.4 * style_score + 0.2 * (1.0 - penalties)

        return {
            "style_match": round(style_score, 3),
            "semantic_preservation": round(semantic_score, 3),
            "length_match": round(length_match, 3),
            "burstiness_match": round(burstiness_match, 3),
            "formality_match": round(formality_match, 3),
            "penalties": round(penalties, 3),
            "composite_score": round(composite, 3),
        }

    def rank_variants(
        self,
        variants: list[dict[str, Any]],
        style_profile: dict[str, Any],
        original_text: str,
        language: str = "ru",
    ) -> list[dict[str, Any]]:
        """Rank variants by composite score."""
        scored: list[dict[str, Any]] = []
        for variant in variants:
            text = variant.get("text", "")
            scores = self.score_variant(text, style_profile, original_text, language)
            scored.append({**variant, "scores": scores})
        scored.sort(key=lambda x: -x["scores"]["composite_score"])
        return scored


style_guidance_engine = StyleGuidanceEngine()
