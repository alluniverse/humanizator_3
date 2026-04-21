"""Ukrainian phrase and style extractor.

Extracts concrete linguistic elements from human-written Ukrainian texts
for injection into LLM prompts. No spaCy Ukrainian model required —
uses regex + frequency analysis on raw text.

Extracted elements injected into the LLM prompt as explicit examples,
not abstract guidance signals. This is the Bao et al. mimicking approach
applied at the phrase level: give the model actual phrases to reuse.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# Ukrainian stopwords (common words to exclude from collocation extraction)
_UK_STOPWORDS = {
    "і", "й", "та", "але", "або", "що", "як", "це", "він", "вона", "вони",
    "ми", "ви", "я", "не", "на", "в", "у", "з", "до", "для", "від", "за",
    "по", "при", "про", "під", "над", "між", "через", "без", "після",
    "того", "тому", "який", "яка", "яке", "які", "який", "де", "коли",
    "якщо", "щоб", "хоч", "хоча", "адже", "бо", "тобто", "також",
    "вже", "ще", "лише", "тільки", "навіть", "саме", "дуже", "більш",
    "менш", "так", "ні", "є", "був", "була", "було", "були", "буде",
    "може", "можна", "треба", "потрібно", "слід", "має", "мають",
    "цей", "ця", "це", "ці", "той", "та", "те", "ті", "свій", "своя",
    "своє", "свої", "інший", "інша", "інше", "інші", "весь", "вся",
    "все", "всі", "кожен", "кожна", "кожне", "будь", "ніхто", "ніщо",
}

# Natural Ukrainian sentence starters / connectors that humans actually use
# (distinct from AI-generated ones like "Варто зазначити", "Таким чином")
_HUMAN_UK_CONNECTORS = [
    "Річ у тому,", "Справа в тому,", "Але є нюанс.", "І все ж,",
    "Ось тут і", "Але якщо", "Питання в тому,", "Насправді,",
    "Ось що цікаво:", "А от", "Тут важливо", "І це не випадково.",
    "Але проблема в тому,", "Що ж до", "Тим часом,", "Але тут",
]


def extract_style_elements(texts: list[str]) -> dict[str, Any]:
    """Extract concrete style elements from Ukrainian human-written samples.

    Returns a dict with:
    - sentence_openers: list[str] — most common first 3-4 words of sentences
    - short_sentences: list[str] — sentences ≤8 words (punchy examples)
    - collocations: list[str] — frequent 2-3-word content phrases
    - characteristic_words: list[str] — author-specific vocabulary
    - connector_phrases: list[str] — natural transition phrases found in texts
    - sample_excerpt: str — first ~400 chars of best/longest sample
    """
    if not texts:
        return _empty()

    all_sentences = _extract_sentences(texts)
    if not all_sentences:
        return _empty()

    return {
        "sentence_openers": _extract_openers(all_sentences),
        "short_sentences": _extract_short_sentences(all_sentences),
        "collocations": _extract_collocations(texts),
        "characteristic_words": _extract_characteristic_words(texts),
        "connector_phrases": _extract_connectors(texts),
        "sample_excerpt": _best_excerpt(texts),
    }


def build_style_injection(elements: dict[str, Any], max_chars: int = 800) -> str:
    """Build a prompt block from extracted style elements.

    This block is injected directly into the Ukrainian adaptation prompt
    so the LLM knows exactly what phrases, openers, and vocabulary to use.
    """
    if not elements or not any(elements.values()):
        return ""

    parts: list[str] = ["СТИЛЬ БІБЛІОТЕКИ (реальні зразки від людини — використовуй їх):"]

    openers = elements.get("sentence_openers", [])
    if openers:
        parts.append(f"• Зачини речень: {' / '.join(openers[:8])}")

    short = elements.get("short_sentences", [])
    if short:
        parts.append(f"• Короткі ударні речення з бібліотеки: {' | '.join(short[:5])}")

    collocations = elements.get("collocations", [])
    if collocations:
        parts.append(f"• Характерні словосполучення: {', '.join(collocations[:12])}")

    words = elements.get("characteristic_words", [])
    if words:
        parts.append(f"• Лексика автора: {', '.join(words[:15])}")

    connectors = elements.get("connector_phrases", [])
    if connectors:
        parts.append(f"• Природні переходи (НЕ AI-кліше): {' / '.join(connectors[:6])}")

    excerpt = elements.get("sample_excerpt", "")
    if excerpt:
        parts.append(f"• Зразок стилю:\n{excerpt}")

    result = "\n".join(parts)
    return result[:max_chars]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_sentences(texts: list[str]) -> list[str]:
    """Split all texts into individual sentences."""
    sentences: list[str] = []
    for text in texts:
        # Split on .!? followed by space + capital letter or end of string
        raw = re.split(r'(?<=[.!?])\s+(?=[А-ЯЇІЄA-Z])', text.strip())
        for s in raw:
            s = s.strip()
            if len(s) > 10:
                sentences.append(s)
    return sentences


def _extract_openers(sentences: list[str]) -> list[str]:
    """Extract most common 2-4 word sentence starters."""
    openers: Counter = Counter()
    for sent in sentences:
        words = sent.split()
        if len(words) >= 3:
            # 2-word opener
            openers[" ".join(words[:2])] += 1
            # 3-word opener
            if len(words) >= 4:
                openers[" ".join(words[:3])] += 1

    # Filter: must appear ≥2 times, not all stopwords, not too generic
    result = []
    for phrase, count in openers.most_common(40):
        words = phrase.lower().split()
        content_words = [w for w in words if w.rstrip(".,!?:;") not in _UK_STOPWORDS]
        if count >= 2 and content_words:
            result.append(phrase)
        if len(result) >= 10:
            break
    return result


def _extract_short_sentences(sentences: list[str]) -> list[str]:
    """Extract short punchy sentences (5-9 words) — style examples."""
    short = []
    for sent in sentences:
        words = sent.split()
        if 5 <= len(words) <= 9:
            # Must end with punctuation and not be a list item
            if sent[-1] in ".!?":
                short.append(sent)
    # Deduplicate and return diverse examples
    seen: set[str] = set()
    result = []
    for s in short:
        key = s[:30].lower()
        if key not in seen:
            seen.add(key)
            result.append(s)
        if len(result) >= 8:
            break
    return result


def _extract_collocations(texts: list[str]) -> list[str]:
    """Extract frequent 2-3-word content collocations."""
    bigrams: Counter = Counter()
    trigrams: Counter = Counter()

    for text in texts:
        # Tokenize: split on spaces, strip punctuation
        words = [re.sub(r'[^а-яА-ЯїЇієІЄа-яa-zA-Z\'-]', '', w).lower()
                 for w in text.split()]
        words = [w for w in words if w and w not in _UK_STOPWORDS and len(w) > 3]

        for a, b in zip(words, words[1:]):
            bigrams[f"{a} {b}"] += 1
        for a, b, c in zip(words, words[1:], words[2:]):
            trigrams[f"{a} {b} {c}"] += 1

    result = []
    # Prefer trigrams (more specific), then bigrams
    for phrase, count in trigrams.most_common(20):
        if count >= 2:
            result.append(phrase)
    for phrase, count in bigrams.most_common(20):
        if count >= 2 and phrase not in result:
            result.append(phrase)
        if len(result) >= 20:
            break
    return result[:20]


def _extract_characteristic_words(texts: list[str]) -> list[str]:
    """Extract vocabulary characteristic of this author (not stopwords, ≥6 chars, ≥2 uses)."""
    word_freq: Counter = Counter()
    for text in texts:
        words = re.findall(r'[а-яА-ЯїЇієІЄ]{6,}', text.lower())
        for w in words:
            if w not in _UK_STOPWORDS:
                word_freq[w] += 1

    # Words used ≥2 times, sorted by frequency
    result = [w for w, c in word_freq.most_common(50) if c >= 2]
    return result[:20]


def _extract_connectors(texts: list[str]) -> list[str]:
    """Find which human connector phrases actually appear in the texts."""
    combined = " ".join(texts).lower()
    found = [c for c in _HUMAN_UK_CONNECTORS if c.lower().rstrip(",.") in combined]
    # Also extract short phrases starting sentences that look like connectors
    sentences = _extract_sentences(texts)
    for sent in sentences:
        words = sent.split()
        if len(words) >= 2:
            opener = " ".join(words[:3])
            # 2-5 word phrases with a comma or colon — typical connectors
            if "," in opener or ":" in opener:
                if opener not in found and len(found) < 12:
                    found.append(opener)
    return found[:10]


def _best_excerpt(texts: list[str]) -> str:
    """Return the first ~350 chars of the longest/best sample."""
    if not texts:
        return ""
    best = max(texts, key=len)
    # Take first 2 paragraphs or 350 chars
    paras = [p.strip() for p in best.split("\n\n") if p.strip()]
    excerpt = "\n\n".join(paras[:2])
    return excerpt[:350]


def _empty() -> dict[str, Any]:
    return {
        "sentence_openers": [],
        "short_sentences": [],
        "collocations": [],
        "characteristic_words": [],
        "connector_phrases": [],
        "sample_excerpt": "",
    }
