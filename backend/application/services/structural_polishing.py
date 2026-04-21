"""Rule-Based Structural Polishing: post-rewrite stabilization."""

from __future__ import annotations

import re
from typing import Any

import spacy


class StructuralPolishing:
    """Applies rule-based structural corrections to rewritten text."""

    def __init__(self) -> None:
        self._nlp_en = spacy.load("en_core_web_sm")
        self._nlp_ru = spacy.load("ru_core_news_sm")

    def _get_nlp(self, language: str) -> spacy.Language:
        return self._nlp_ru if language == "ru" else self._nlp_en

    def polish(
        self,
        text: str,
        style_profile: dict[str, Any] | None = None,
        language: str = "ru",
    ) -> dict[str, Any]:
        """Apply structural polishing rules."""
        nlp = self._get_nlp(language)
        doc = nlp(text)

        # Remove cliché transitions
        clichés = {
            "en": ["in conclusion", "moreover", "it is important to note", "furthermore"],
            "ru": ["подведём итоги", "стоит отметить", "напомним", "следует отметить"],
        }
        lang = "ru" if language == "ru" else "en"
        result = text
        for phrase in clichés.get(lang, []):
            result = re.sub(re.escape(phrase), "", result, flags=re.IGNORECASE)

        # Normalize whitespace
        result = re.sub(r"\s+", " ", result).strip()

        # Burstiness correction heuristic
        if style_profile:
            target_mean = style_profile.get("guidance_signals", {}).get("target_sentence_length")
            if target_mean:
                result = self._correct_sentence_lengths(result, target_mean, nlp)

        return {
            "polished_text": result,
            "changes": ["removed_clichés", "normalized_whitespace"],
        }

    def _correct_sentence_lengths(
        self,
        text: str,
        target_mean: float,
        nlp: spacy.Language,
    ) -> str:
        """Gentle sentence length correction (MVP: no deep restructuring)."""
        doc = nlp(text)
        sentences = [sent.text.strip() for sent in doc.sents]
        if not sentences:
            return text

        # If average is far off target, signal that deeper rewrite is needed
        avg = sum(len(s.split()) for s in sentences) / len(sentences)
        if abs(avg - target_mean) > target_mean * 0.3:
            # Append a subtle hint for downstream (not modifying text deeply in MVP)
            pass
        return text


structural_polishing = StructuralPolishing()
