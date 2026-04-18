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
        g = style_profile.get("guidance_signals", {})

        sent_lengths = [len(sent) for sent in doc.sents]
        mean_sent = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0.0
        total_tokens = sum(1 for t in doc if not t.is_space and not t.is_punct)

        # ── Core style components ──────────────────────────────────────────
        target_mean = g.get("target_sentence_length", mean_sent)
        target_burstiness = g.get("target_burstiness", 0.5)
        target_formality = g.get("target_formality", 0.5)

        length_match = 1.0 - min(abs(mean_sent - target_mean) / max(target_mean, 1), 1.0)

        var_sent = (
            sum((x - mean_sent) ** 2 for x in sent_lengths) / len(sent_lengths)
            if sent_lengths else 0.0
        )
        burstiness = (var_sent ** 0.5) / mean_sent if mean_sent > 0 else 0.0
        burstiness_match = 1.0 - min(abs(burstiness - target_burstiness), 1.0)

        formal = sum(1 for token in doc if token.pos_ in {"NOUN", "ADJ"})
        informal = sum(1 for token in doc if token.pos_ in {"PRON", "INTJ"})
        formality = formal / (formal + informal) if (formal + informal) else 0.5
        formality_match = 1.0 - min(abs(formality - target_formality), 1.0)

        # ── NEW: Passive voice match ───────────────────────────────────────
        passive_sents = sum(
            1 for sent in doc.sents
            if {t.dep_ for t in sent} & {"nsubjpass", "auxpass", "nsubj:pass", "aux:pass"}
        )
        passive_ratio = passive_sents / len(sent_lengths) if sent_lengths else 0.0
        target_passive = g.get("passive_voice_ratio", passive_ratio)
        passive_match = 1.0 - min(abs(passive_ratio - target_passive) / 0.3, 1.0)

        # ── NEW: Subordination match ───────────────────────────────────────
        sub_deps = {"advcl", "relcl", "csubj", "acl", "ccomp", "xcomp"}
        sub_count = sum(1 for t in doc if t.dep_ in sub_deps)
        subord_ratio = sub_count / len(sent_lengths) if sent_lengths else 0.0
        target_subord = g.get("subordination_ratio", subord_ratio)
        subord_match = 1.0 - min(abs(subord_ratio - target_subord) / 0.5, 1.0)

        # ── NEW: Hedging penalty ───────────────────────────────────────────
        from application.services.style_profile import _HEDGES_EN, _HEDGES_RU
        hedges = _HEDGES_RU if language == "ru" else _HEDGES_EN
        text_lower = variant_text.lower()
        hedging_penalty = min(sum(0.05 for ph in hedges if ph in text_lower), 0.3)

        # ── Style score (extended) ─────────────────────────────────────────
        style_score = (
            length_match * 0.25
            + burstiness_match * 0.20
            + formality_match * 0.20
            + passive_match * 0.15
            + subord_match * 0.10
            + (1.0 - hedging_penalty / 0.3) * 0.10
        )

        # ── Semantic preservation ─────────────────────────────────────────
        orig_tokens = set(
            t.lemma_.lower() for t in nlp(original_text)
            if not t.is_space and not t.is_punct
        )
        var_tokens = set(
            t.lemma_.lower() for t in doc if not t.is_space and not t.is_punct
        )
        overlap = len(orig_tokens & var_tokens) / max(len(orig_tokens), 1)

        # ── Avoid-marker penalty ──────────────────────────────────────────
        avoid_markers = style_profile.get("lexical_signature", {}).get("avoid_markers", [])
        avoid_penalty = min(
            sum(0.1 for marker in avoid_markers if marker.lower() in text_lower), 0.3
        )

        composite = (
            0.35 * overlap
            + 0.45 * style_score
            + 0.20 * (1.0 - (avoid_penalty + hedging_penalty) / 2)
        )

        return {
            "style_match": round(style_score, 3),
            "semantic_preservation": round(overlap, 3),
            "length_match": round(length_match, 3),
            "burstiness_match": round(burstiness_match, 3),
            "formality_match": round(formality_match, 3),
            "passive_match": round(passive_match, 3),
            "subord_match": round(subord_match, 3),
            "hedging_penalty": round(hedging_penalty, 3),
            "avoid_penalty": round(avoid_penalty, 3),
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
