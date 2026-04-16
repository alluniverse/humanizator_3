"""Style Profile Engine: computes Style DNA from a reference library."""

from __future__ import annotations

import math
import re
from typing import Any

import spacy
from domain.enums import QualityTier


class StyleProfileEngine:
    """Builds machine-readable style profiles from reference libraries."""

    def __init__(self) -> None:
        self._nlp_en = spacy.load("en_core_web_sm")
        self._nlp_ru = spacy.load("ru_core_news_sm")

    def _get_nlp(self, language: str) -> spacy.Language:
        return self._nlp_ru if language == "ru" else self._nlp_en

    def build_profile(
        self,
        samples: list[dict[str, Any]],
        language: str = "ru",
    ) -> dict[str, Any]:
        """Compute a Style DNA profile from a list of samples.

        Only L1 (and optionally L2) samples should be passed in.
        """
        texts = [s["content"] for s in samples if s.get("content")]
        if not texts:
            return self._empty_profile()

        nlp = self._get_nlp(language)
        docs = list(nlp.pipe(texts))

        # Sentence-level stats
        sent_lengths: list[int] = []
        para_lengths: list[int] = []
        for doc, text in zip(docs, texts):
            for sent in doc.sents:
                sent_lengths.append(len(sent))
            paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
            para_lengths.extend(len(p.split()) for p in paragraphs)

        mean_sent = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0.0
        var_sent = (
            sum((x - mean_sent) ** 2 for x in sent_lengths) / len(sent_lengths)
            if sent_lengths
            else 0.0
        )
        burstiness = math.sqrt(var_sent) / mean_sent if mean_sent > 0 else 0.0

        # Lexical signature
        all_tokens: list[str] = []
        pos_counts: dict[str, int] = {}
        transition_markers: list[str] = []
        for doc in docs:
            for token in doc:
                if not token.is_space and not token.is_punct:
                    all_tokens.append(token.lemma_.lower())
                    pos_counts[token.pos_] = pos_counts.get(token.pos_, 0) + 1
            # Simple transition detection
            text_lower = doc.text.lower()
            for marker in ("however", "therefore", "moreover", "but", "and", "so", "thus"):
                if marker in text_lower:
                    transition_markers.append(marker)
            for marker in ("однако", "поэтому", "кроме того", "но", "и", "таким образом"):
                if marker in text_lower:
                    transition_markers.append(marker)

        total_tokens = len(all_tokens)
        unique_tokens = len(set(all_tokens))
        ttr = unique_tokens / total_tokens if total_tokens else 0.0

        # Preferred / avoid markers (heuristic)
        freq: dict[str, int] = {}
        for t in all_tokens:
            freq[t] = freq.get(t, 0) + 1
        preferred = [w for w, c in sorted(freq.items(), key=lambda x: -x[1])[:20]]
        avoid = ["in conclusion", "moreover", "it is important to note"]

        # POS proportions
        pos_total = sum(pos_counts.values())
        pos_ratios = {k: round(v / pos_total, 3) for k, v in pos_counts.items()} if pos_total else {}

        # Formality heuristic
        formal_markers = sum(
            1
            for doc in docs
            for token in doc
            if token.pos_ in {"NOUN", "ADJ"}
        )
        informal_markers = sum(
            1
            for doc in docs
            for token in doc
            if token.pos_ in {"PRON", "INTJ"}
        )
        formality = (
            formal_markers / (formal_markers + informal_markers)
            if (formal_markers + informal_markers)
            else 0.5
        )

        # Imagery level (adjectives + adverbs density)
        imagery_tokens = sum(
            1 for doc in docs for token in doc if token.pos_ in {"ADJ", "ADV"}
        )
        imagery_level = imagery_tokens / total_tokens if total_tokens else 0.0

        # Linguistic markers (11 markers taxonomy)
        linguistic_markers = {
            "flesch_reading_ease": self._flesch_reading_ease(mean_sent, self._avg_word_length(all_tokens)),
            "avg_word_length": self._avg_word_length(all_tokens),
            "lexical_diversity_ttr": round(ttr, 3),
            "contraction_ratio": self._contraction_ratio(texts),
            "punctuation_pattern": self._punctuation_profile(docs),
            "noun_ratio": pos_ratios.get("NOUN", 0.0),
            "verb_ratio": pos_ratios.get("VERB", 0.0),
            "adj_ratio": pos_ratios.get("ADJ", 0.0),
            "compound_sentence_ratio": self._compound_sentence_ratio(docs),
            "avg_parse_depth": self._avg_parse_depth(docs),
            "personal_pronoun_ratio": self._personal_pronoun_ratio(docs),
        }

        # Target perplexity range (heuristic based on human texts ~15 PPL)
        target_perplexity_min = 12.0
        target_perplexity_max = 18.0

        return {
            "sentence_length_mean": round(mean_sent, 2),
            "sentence_length_variance": round(var_sent, 2),
            "burstiness_index": round(burstiness, 3),
            "target_perplexity_min": target_perplexity_min,
            "target_perplexity_max": target_perplexity_max,
            "formality": round(formality, 3),
            "imagery_level": round(imagery_level, 3),
            "lexical_signature": {
                "preferred_markers": preferred[:10],
                "avoid_markers": avoid,
            },
            "syntax_patterns": self._syntax_patterns(sent_lengths),
            "composition_profile": {
                "avg_paragraph_words": round(sum(para_lengths) / len(para_lengths), 1) if para_lengths else 0.0,
            },
            "rhythm_profile": {
                "transition_markers": list(set(transition_markers))[:10],
            },
            "linguistic_markers": linguistic_markers,
            "guidance_signals": {
                "target_sentence_length": round(mean_sent, 1),
                "target_burstiness": round(burstiness, 3),
                "target_formality": round(formality, 3),
            },
        }

    def _empty_profile(self) -> dict[str, Any]:
        return {
            "sentence_length_mean": 0.0,
            "sentence_length_variance": 0.0,
            "burstiness_index": 0.0,
            "target_perplexity_min": 12.0,
            "target_perplexity_max": 18.0,
            "formality": 0.5,
            "imagery_level": 0.0,
            "lexical_signature": {"preferred_markers": [], "avoid_markers": []},
            "syntax_patterns": [],
            "composition_profile": {"avg_paragraph_words": 0.0},
            "rhythm_profile": {"transition_markers": []},
            "linguistic_markers": {},
            "guidance_signals": {},
        }

    def _avg_word_length(self, tokens: list[str]) -> float:
        if not tokens:
            return 0.0
        return round(sum(len(t) for t in tokens) / len(tokens), 2)

    def _contraction_ratio(self, texts: list[str]) -> float:
        total_words = sum(len(t.split()) for t in texts)
        contractions = sum(len(re.findall(r"\w+'\w+", t)) for t in texts)
        return round(contractions / total_words, 4) if total_words else 0.0

    def _punctuation_profile(self, docs: list[spacy.tokens.Doc]) -> dict[str, float]:
        counts: dict[str, int] = {}
        total = 0
        for doc in docs:
            for token in doc:
                if token.is_punct:
                    counts[token.text] = counts.get(token.text, 0) + 1
                    total += 1
        return {k: round(v / total, 3) for k, v in counts.items()} if total else {}

    def _compound_sentence_ratio(self, docs: list[spacy.tokens.Doc]) -> float:
        total = 0
        compounds = 0
        for doc in docs:
            for sent in doc.sents:
                total += 1
                # Heuristic: multiple roots or cc/conj markers
                deps = [token.dep_ for token in sent]
                if "conj" in deps or "cc" in deps:
                    compounds += 1
        return round(compounds / total, 3) if total else 0.0

    def _avg_parse_depth(self, docs: list[spacy.tokens.Doc]) -> float:
        depths: list[int] = []
        for doc in docs:
            for sent in doc.sents:
                depths.append(max((token.head.i - token.i) for token in sent) + 1)
        return round(sum(depths) / len(depths), 1) if depths else 0.0

    def _personal_pronoun_ratio(self, docs: list[spacy.tokens.Doc]) -> float:
        total = 0
        pron = 0
        for doc in docs:
            for token in doc:
                if token.pos_ == "PRON" and token.lemma_.lower() in {
                    "i", "you", "he", "she", "we", "they",
                    "я", "ты", "он", "она", "мы", "они",
                }:
                    pron += 1
                total += 1
        return round(pron / total, 4) if total else 0.0

    def _flesch_reading_ease(self, avg_sentence_length: float, avg_syllables_per_word: float) -> float:
        # Approximation using word length as proxy for syllables
        return round(206.835 - 1.015 * avg_sentence_length - 84.6 * avg_syllables_per_word, 2)

    def _syntax_patterns(self, sent_lengths: list[int]) -> list[str]:
        patterns: list[str] = []
        if not sent_lengths:
            return patterns
        mean = sum(sent_lengths) / len(sent_lengths)
        short = sum(1 for s in sent_lengths if s < mean * 0.7)
        long = sum(1 for s in sent_lengths if s > mean * 1.3)
        if short / len(sent_lengths) > 0.3:
            patterns.append("short opening sentence")
        if long / len(sent_lengths) > 0.3:
            patterns.append("mid-length analysis")
        if short and long:
            patterns.append("occasional contrast turn")
        return patterns


style_profile_engine = StyleProfileEngine()
