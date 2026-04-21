"""Style Profile Engine: computes Style DNA from a reference library."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

import spacy
from domain.enums import QualityTier


# Hedging phrases by language
_HEDGES_EN = [
    "it is important to note", "it should be noted", "it is worth noting",
    "it is worth mentioning", "one might argue", "it could be said",
    "it seems", "it appears", "arguably", "perhaps", "possibly",
    "it is generally", "in some ways", "to some extent", "relatively speaking",
]
_HEDGES_RU = [
    "стоит отметить", "необходимо отметить", "следует отметить",
    "можно сказать", "по всей видимости", "по-видимому", "вероятно",
    "возможно", "пожалуй", "как правило", "в некотором роде",
    "в определённой степени", "так или иначе", "нельзя не отметить",
]

# First-person pronouns by language
_FIRST_PERSON_EN = {"i", "me", "my", "mine", "myself", "we", "us", "our", "ours", "ourselves"}
_FIRST_PERSON_RU = {"я", "меня", "мне", "мной", "мы", "нас", "нам", "нами", "наш", "наша", "наше", "наши"}

# Common vocabulary threshold: words shorter than this are "common"
_RARE_WORD_MIN_LEN = 9


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

        # ── Sentence-level stats ───────────────────────────────────────────
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
            if sent_lengths else 0.0
        )
        burstiness = math.sqrt(var_sent) / mean_sent if mean_sent > 0 else 0.0

        # ── Lexical signature ──────────────────────────────────────────────
        all_tokens: list[str] = []
        pos_counts: dict[str, int] = {}
        transition_markers: list[str] = []
        for doc in docs:
            for token in doc:
                if not token.is_space and not token.is_punct:
                    all_tokens.append(token.lemma_.lower())
                    pos_counts[token.pos_] = pos_counts.get(token.pos_, 0) + 1
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

        freq: dict[str, int] = {}
        for t in all_tokens:
            freq[t] = freq.get(t, 0) + 1
        preferred = [w for w, c in sorted(freq.items(), key=lambda x: -x[1])[:20]]
        avoid = ["in conclusion", "moreover", "it is important to note",
                 "в заключение", "кроме того", "стоит отметить"]

        pos_total = sum(pos_counts.values())
        pos_ratios = {k: round(v / pos_total, 3) for k, v in pos_counts.items()} if pos_total else {}

        # ── Formality ─────────────────────────────────────────────────────
        formal_markers = sum(
            1 for doc in docs for token in doc if token.pos_ in {"NOUN", "ADJ"}
        )
        informal_markers = sum(
            1 for doc in docs for token in doc if token.pos_ in {"PRON", "INTJ"}
        )
        formality = (
            formal_markers / (formal_markers + informal_markers)
            if (formal_markers + informal_markers) else 0.5
        )

        # ── Imagery level ──────────────────────────────────────────────────
        imagery_tokens = sum(
            1 for doc in docs for token in doc if token.pos_ in {"ADJ", "ADV"}
        )
        imagery_level = imagery_tokens / total_tokens if total_tokens else 0.0

        # ── NEW: Passive voice ratio ───────────────────────────────────────
        passive_voice_ratio = self._passive_voice_ratio(docs)

        # ── NEW: Sentence opening distribution ────────────────────────────
        sentence_opening_dist = self._sentence_opening_distribution(docs)

        # ── NEW: Bigram signature ─────────────────────────────────────────
        bigram_signature = self._bigram_signature(docs, top_n=15)

        # ── NEW: Hedging ratio ─────────────────────────────────────────────
        hedging_ratio = self._hedging_ratio(texts, language, total_tokens)

        # ── NEW: Question frequency (per 1000 words) ──────────────────────
        question_frequency = self._question_frequency(docs, total_tokens)

        # ── NEW: Subordination ratio ──────────────────────────────────────
        subordination_ratio = self._subordination_ratio(docs, sent_lengths)

        # ── NEW: Perspective ratio (1st vs 3rd person) ────────────────────
        perspective = self._perspective_ratio(docs, language)

        # ── NEW: Rare word ratio ──────────────────────────────────────────
        rare_word_ratio = self._rare_word_ratio(all_tokens, freq, total_tokens)

        # ── NEW: Sentence alternation pattern ────────────────────────────
        alternation_pattern = self._sentence_alternation_pattern(sent_lengths, mean_sent)

        # ── NEW: Paragraph structure ─────────────────────────────────────
        paragraph_structure = self._paragraph_structure(para_lengths)

        # ── Linguistic markers (extended) ─────────────────────────────────
        linguistic_markers = {
            "flesch_reading_ease": self._flesch_reading_ease(
                mean_sent, self._avg_word_length(all_tokens)
            ),
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
            # New markers
            "passive_voice_ratio": passive_voice_ratio,
            "hedging_ratio": hedging_ratio,
            "question_frequency": question_frequency,
            "subordination_ratio": subordination_ratio,
            "rare_word_ratio": rare_word_ratio,
            "first_person_ratio": perspective["first_person_ratio"],
        }

        target_perplexity_min = 12.0
        target_perplexity_max = 18.0

        # ── Guidance signals (what flows into LLM prompts) ─────────────────
        guidance_signals = self._build_guidance_signals(
            mean_sent=mean_sent,
            burstiness=burstiness,
            formality=formality,
            passive_voice_ratio=passive_voice_ratio,
            sentence_opening_dist=sentence_opening_dist,
            bigram_signature=bigram_signature,
            hedging_ratio=hedging_ratio,
            question_frequency=question_frequency,
            subordination_ratio=subordination_ratio,
            perspective=perspective,
            rare_word_ratio=rare_word_ratio,
            alternation_pattern=alternation_pattern,
            paragraph_structure=paragraph_structure,
        )

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
                "bigram_signature": bigram_signature,
            },
            "syntax_patterns": self._syntax_patterns(sent_lengths),
            "composition_profile": {
                "avg_paragraph_words": round(
                    sum(para_lengths) / len(para_lengths), 1
                ) if para_lengths else 0.0,
                **paragraph_structure,
            },
            "rhythm_profile": {
                "transition_markers": list(set(transition_markers))[:10],
                "sentence_alternation_pattern": alternation_pattern,
                "sentence_opening_distribution": sentence_opening_dist,
            },
            "linguistic_markers": linguistic_markers,
            "guidance_signals": guidance_signals,
        }

    # ── Guidance signal builder ────────────────────────────────────────────

    def _build_guidance_signals(
        self,
        mean_sent: float,
        burstiness: float,
        formality: float,
        passive_voice_ratio: float,
        sentence_opening_dist: dict[str, float],
        bigram_signature: list[str],
        hedging_ratio: float,
        question_frequency: float,
        subordination_ratio: float,
        perspective: dict[str, Any],
        rare_word_ratio: float,
        alternation_pattern: str,
        paragraph_structure: dict[str, Any],
    ) -> dict[str, Any]:
        """Build actionable signals for LLM prompt construction."""
        signals: dict[str, Any] = {
            # Existing signals
            "target_sentence_length": round(mean_sent, 1),
            "target_burstiness": round(burstiness, 3),
            "target_formality": round(formality, 3),

            # Passive voice instruction
            "passive_voice_ratio": round(passive_voice_ratio, 3),
            "passive_voice_instruction": (
                "avoid passive voice — use active constructions"
                if passive_voice_ratio < 0.10 else
                "use passive voice moderately"
                if passive_voice_ratio < 0.25 else
                "passive constructions are acceptable in this style"
            ),

            # Sentence opening instruction
            "dominant_opening": max(sentence_opening_dist, key=sentence_opening_dist.get),
            "sentence_opening_instruction": self._opening_instruction(sentence_opening_dist),

            # Bigram phrases characteristic of the style
            "characteristic_phrases": bigram_signature[:8],

            # Hedging
            "hedging_ratio": round(hedging_ratio, 4),
            "hedging_instruction": (
                "avoid all hedging phrases (it is worth noting, one might argue, etc.)"
                if hedging_ratio < 0.002 else
                "use hedging sparingly"
                if hedging_ratio < 0.005 else
                "moderate hedging is acceptable in this style"
            ),

            # Questions
            "question_frequency": round(question_frequency, 2),
            "question_instruction": (
                "do not use rhetorical questions"
                if question_frequency < 5 else
                "rhetorical questions are acceptable (target: ~{:.0f} per 1000 words)".format(
                    question_frequency
                )
            ),

            # Sentence structure complexity
            "subordination_ratio": round(subordination_ratio, 3),
            "complexity_instruction": (
                "prefer short, direct sentences with minimal subordinate clauses"
                if subordination_ratio < 0.2 else
                "use complex sentences with subordinate clauses moderately"
                if subordination_ratio < 0.4 else
                "complex sentence structures with multiple clauses are characteristic of this style"
            ),

            # Voice/perspective
            "perspective": perspective["dominant"],
            "perspective_instruction": (
                "write in first person (я/мы or I/we)"
                if perspective["dominant"] == "first_person" else
                "write in third person — avoid I/we/my"
            ),

            # Vocabulary richness
            "rare_word_ratio": round(rare_word_ratio, 3),
            "vocabulary_instruction": (
                "use common everyday vocabulary — avoid rare or complex words"
                if rare_word_ratio < 0.05 else
                "use varied vocabulary including some less common words"
                if rare_word_ratio < 0.15 else
                "rich vocabulary with specialized terms is expected"
            ),

            # Rhythm
            "sentence_rhythm": alternation_pattern,
            "rhythm_instruction": (
                "deliberately alternate short and long sentences to create rhythm"
                if alternation_pattern == "alternating" else
                "vary sentence length significantly — avoid monotone uniform length"
                if alternation_pattern == "monotone" else
                "use bursts of short sentences for emphasis"
            ),
        }
        return signals

    def _opening_instruction(self, dist: dict[str, float]) -> str:
        dominant = max(dist, key=dist.get)
        ratio = dist[dominant]
        desc = {
            "nominal": "start most sentences with a noun or noun phrase",
            "verbal": "start sentences with verbs or participles for a dynamic feel",
            "adverbial": "use adverbial/prepositional openers for context (yesterday, in this case, etc.)",
            "pronoun": "personal pronoun openings (I, we, they) are common in this style",
            "other": "varied sentence openings",
        }
        return f"{desc.get(dominant, 'varied openings')} ({ratio:.0%} of sentences)"

    # ── New metric extractors ──────────────────────────────────────────────

    def _passive_voice_ratio(self, docs: list[spacy.tokens.Doc]) -> float:
        total_sents = 0
        passive_sents = 0
        for doc in docs:
            for sent in doc.sents:
                total_sents += 1
                deps = {token.dep_ for token in sent}
                # English: nsubjpass / auxpass; Universal: nsubj:pass / aux:pass
                if deps & {"nsubjpass", "auxpass", "nsubj:pass", "aux:pass"}:
                    passive_sents += 1
        return round(passive_sents / total_sents, 4) if total_sents else 0.0

    def _sentence_opening_distribution(
        self, docs: list[spacy.tokens.Doc]
    ) -> dict[str, float]:
        counts: dict[str, int] = {
            "nominal": 0, "verbal": 0, "adverbial": 0, "pronoun": 0, "other": 0
        }
        total = 0
        for doc in docs:
            for sent in doc.sents:
                # Find first non-punct/space token
                first = next(
                    (t for t in sent if not t.is_space and not t.is_punct), None
                )
                if first is None:
                    continue
                total += 1
                pos = first.pos_
                if pos == "PRON":
                    counts["pronoun"] += 1
                elif pos in {"NOUN", "PROPN", "NUM"}:
                    counts["nominal"] += 1
                elif pos in {"VERB", "AUX", "PART"}:
                    counts["verbal"] += 1
                elif pos in {"ADV", "ADP", "SCONJ", "CCONJ"}:
                    counts["adverbial"] += 1
                else:
                    counts["other"] += 1
        if total == 0:
            return {k: 0.0 for k in counts}
        return {k: round(v / total, 3) for k, v in counts.items()}

    def _bigram_signature(
        self, docs: list[spacy.tokens.Doc], top_n: int = 15
    ) -> list[str]:
        # Count by lemma-key but store representative surface form for readability
        lemma_to_surface: dict[tuple[str, str], str] = {}
        bigrams: Counter = Counter()
        for doc in docs:
            tokens = [
                t for t in doc
                if not t.is_space and not t.is_punct and not t.is_stop and len(t.text) > 2
            ]
            for a, b in zip(tokens, tokens[1:]):
                key = (a.lemma_.lower(), b.lemma_.lower())
                bigrams[key] += 1
                if key not in lemma_to_surface:
                    lemma_to_surface[key] = f"{a.text.lower()} {b.text.lower()}"
        return [lemma_to_surface[key] for key, _ in bigrams.most_common(top_n)]

    def _hedging_ratio(
        self, texts: list[str], language: str, total_tokens: int
    ) -> float:
        phrases = _HEDGES_RU if language == "ru" else _HEDGES_EN
        combined = " ".join(texts).lower()
        count = sum(combined.count(ph) for ph in phrases)
        return round(count / (total_tokens / 1000), 4) if total_tokens else 0.0

    def _question_frequency(
        self, docs: list[spacy.tokens.Doc], total_tokens: int
    ) -> float:
        questions = sum(
            1 for doc in docs for sent in doc.sents
            if sent.text.rstrip().endswith("?")
        )
        return round(questions / (total_tokens / 1000), 2) if total_tokens else 0.0

    def _subordination_ratio(
        self, docs: list[spacy.tokens.Doc], sent_lengths: list[int]
    ) -> float:
        sub_deps = {"advcl", "relcl", "csubj", "acl", "ccomp", "xcomp"}
        sub_count = sum(
            1 for doc in docs for token in doc if token.dep_ in sub_deps
        )
        total_sents = len(sent_lengths)
        return round(sub_count / total_sents, 3) if total_sents else 0.0

    def _perspective_ratio(
        self, docs: list[spacy.tokens.Doc], language: str
    ) -> dict[str, Any]:
        first_set = _FIRST_PERSON_RU if language == "ru" else _FIRST_PERSON_EN
        first_count = 0
        total_pron = 0
        for doc in docs:
            for token in doc:
                if token.pos_ == "PRON":
                    total_pron += 1
                    if token.lemma_.lower() in first_set:
                        first_count += 1
        ratio = first_count / total_pron if total_pron else 0.0
        return {
            "first_person_ratio": round(ratio, 3),
            "dominant": "first_person" if ratio > 0.4 else "third_person",
        }

    def _rare_word_ratio(
        self, all_tokens: list[str], freq: dict[str, int], total_tokens: int
    ) -> float:
        if not total_tokens:
            return 0.0
        # Words that appear only once (hapax legomena) AND are long — likely rare/specialized
        hapax = sum(1 for t, c in freq.items() if c == 1 and len(t) >= _RARE_WORD_MIN_LEN)
        return round(hapax / total_tokens, 4)

    def _sentence_alternation_pattern(
        self, sent_lengths: list[int], mean: float
    ) -> str:
        if len(sent_lengths) < 4:
            return "insufficient_data"
        threshold = mean * 0.4
        # Count direction changes: short→long or long→short
        changes = 0
        for i in range(1, len(sent_lengths)):
            prev_long = sent_lengths[i - 1] > mean
            curr_long = sent_lengths[i] > mean
            if prev_long != curr_long:
                changes += 1
        change_rate = changes / (len(sent_lengths) - 1)
        std = math.sqrt(
            sum((x - mean) ** 2 for x in sent_lengths) / len(sent_lengths)
        )
        if change_rate > 0.45:
            return "alternating"    # журналистский / авторский стиль
        elif std / mean < 0.3:
            return "monotone"       # корпоративный / академический
        else:
            return "burst"          # несколько длинных + короткие паузы

    def _paragraph_structure(self, para_lengths: list[int]) -> dict[str, Any]:
        if not para_lengths:
            return {
                "short_paragraph_ratio": 0.0,
                "long_paragraph_ratio": 0.0,
                "avg_paragraph_sentences": 0.0,
            }
        short = sum(1 for p in para_lengths if p < 40)
        long_ = sum(1 for p in para_lengths if p > 120)
        total = len(para_lengths)
        return {
            "short_paragraph_ratio": round(short / total, 3),
            "long_paragraph_ratio": round(long_ / total, 3),
            "avg_paragraph_words": round(sum(para_lengths) / total, 1),
        }

    # ── Existing helper methods ────────────────────────────────────────────

    def _empty_profile(self) -> dict[str, Any]:
        return {
            "sentence_length_mean": 0.0,
            "sentence_length_variance": 0.0,
            "burstiness_index": 0.0,
            "target_perplexity_min": 12.0,
            "target_perplexity_max": 18.0,
            "formality": 0.5,
            "imagery_level": 0.0,
            "lexical_signature": {
                "preferred_markers": [],
                "avoid_markers": [],
                "bigram_signature": [],
            },
            "syntax_patterns": [],
            "composition_profile": {
                "avg_paragraph_words": 0.0,
                "short_paragraph_ratio": 0.0,
                "long_paragraph_ratio": 0.0,
            },
            "rhythm_profile": {
                "transition_markers": [],
                "sentence_alternation_pattern": "insufficient_data",
                "sentence_opening_distribution": {},
            },
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

    def _flesch_reading_ease(
        self, avg_sentence_length: float, avg_syllables_per_word: float
    ) -> float:
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
