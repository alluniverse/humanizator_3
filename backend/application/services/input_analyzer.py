"""Input Analyzer: pre-rewrite text analysis."""

from __future__ import annotations

import re
from typing import Any

import spacy


class InputAnalyzer:
    """Analyzes input text before rewriting."""

    def __init__(self) -> None:
        self._nlp_en = spacy.load("en_core_web_sm")
        self._nlp_ru = spacy.load("ru_core_news_sm")

    def _get_nlp(self, language: str) -> spacy.Language:
        return self._nlp_ru if language == "ru" else self._nlp_en

    def analyze(
        self,
        text: str,
        language: str = "ru",
        style_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Return technical profile, risk map, and recommendations."""
        nlp = self._get_nlp(language)
        doc = nlp(text)

        sentences = list(doc.sents)
        sent_lengths = [len(sent) for sent in sentences]
        mean_sent = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0.0
        var_sent = (
            sum((x - mean_sent) ** 2 for x in sent_lengths) / len(sent_lengths)
            if sent_lengths
            else 0.0
        )
        burstiness = (var_sent ** 0.5) / mean_sent if mean_sent > 0 else 0.0

        words = [token.text.lower() for token in doc if not token.is_space and not token.is_punct]
        unique_ratio = len(set(words)) / len(words) if words else 0.0

        # Cliché / template detection
        cliché_patterns = [
            r"it is important to note",
            r"in conclusion",
            r"moreover",
            r"furthermore",
            r"напомним",
            r"подведём итоги",
            r"стоит отметить",
        ]
        cliché_count = sum(1 for pat in cliché_patterns if re.search(pat, text, re.IGNORECASE))

        # Fact density (entities + numbers)
        entity_count = len(doc.ents)
        number_count = len(re.findall(r"\b\d+\b", text))
        fact_density = (entity_count + number_count) / len(words) if words else 0.0

        # Risk map
        risk_map: list[dict[str, Any]] = []
        for ent in doc.ents:
            risk_map.append(
                {
                    "start": ent.start_char,
                    "end": ent.end_char,
                    "text": ent.text,
                    "label": ent.label_,
                    "risk": "high" if ent.label_ in {"PERSON", "ORG", "GPE", "DATE", "MONEY"} else "medium",
                    "flexibility": "low",
                }
            )

        # Style flexibility map (generic descriptive sentences)
        flex_map: list[dict[str, Any]] = []
        for sent in sentences:
            if not any(ent.start >= sent.start and ent.end <= sent.end for ent in doc.ents):
                flex_map.append(
                    {
                        "start": sent.start_char,
                        "end": sent.end_char,
                        "risk": "low",
                        "flexibility": "high",
                    }
                )

        # Perplexity gap (placeholder until perplexity engine is integrated)
        perplexity_gap = 0.0
        if style_profile:
            target_min = style_profile.get("target_perplexity_min", 12.0)
            target_max = style_profile.get("target_perplexity_max", 18.0)
            # We'll fill actual current perplexity later; here we just structure the gap
            perplexity_gap = {
                "current_perplexity": None,
                "target_min": target_min,
                "target_max": target_max,
                "gap": None,
            }

        # Recommend rewrite mode
        recommended_mode = self._recommend_mode(
            burstiness=burstiness,
            unique_ratio=unique_ratio,
            cliché_count=cliché_count,
            fact_density=fact_density,
        )

        return {
            "input_profile": {
                "sentence_count": len(sentences),
                "word_count": len(words),
                "mean_sentence_length": round(mean_sent, 1),
                "burstiness": round(burstiness, 3),
                "lexical_diversity": round(unique_ratio, 3),
                "cliché_count": cliché_count,
                "fact_density": round(fact_density, 4),
            },
            "risk_map": risk_map,
            "flexibility_map": flex_map,
            "perplexity_gap": perplexity_gap,
            "recommendations": {
                "rewrite_mode": recommended_mode,
                "notes": [],
            },
        }

    def _recommend_mode(
        self,
        burstiness: float,
        unique_ratio: float,
        cliché_count: int,
        fact_density: float,
    ) -> str:
        if cliché_count > 2 or unique_ratio < 0.4:
            return "expressive"
        if fact_density > 0.15:
            return "conservative"
        return "balanced"


input_analyzer = InputAnalyzer()
