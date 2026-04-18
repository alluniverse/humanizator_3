"""Prompt templates for Guided Rewrite Engine."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# AI marker elimination instructions (injected into every system prompt)
# ---------------------------------------------------------------------------

_AI_MARKER_BLOCK = (
    "PRIORITY 1 — ELIMINATE ALL AI MARKERS. Before anything else, scan the output for every pattern "
    "typical of AI-generated text and remove it. This is non-negotiable.\n\n"

    "ENGLISH AI patterns to eliminate:\n"
    "• Hedging openers: 'It is important to note', 'It is worth mentioning', 'It should be noted', "
    "'It is crucial to understand', 'Notably', 'Crucially', 'Fundamentally', 'Essentially', "
    "'It goes without saying', 'Needless to say'\n"
    "• Theatrical openers: 'In the realm of', 'In the tapestry of', 'In a world where', "
    "'Picture this', 'Imagine a world', 'At its core', 'At the heart of'\n"
    "• Filler transitions: 'Furthermore', 'Moreover', 'In addition', 'In conclusion', "
    "'To summarize', 'In summary', 'Overall', 'Lastly', 'First and foremost', "
    "'It is worth noting that', 'One might argue'\n"
    "• Hollow intensifiers: 'Absolutely', 'Definitely', 'Certainly', 'Undeniably', "
    "'Without a doubt', 'Undoubtedly', 'Incredibly', 'Remarkably'\n"
    "• Sycophantic phrases: 'Great question', 'Excellent point', 'Of course', 'Certainly'\n\n"

    "RUSSIAN AI patterns to eliminate:\n"
    "• Hedging: 'Стоит отметить', 'Необходимо отметить', 'Следует отметить', "
    "'Важно понимать', 'Нельзя не отметить', 'Не менее важно', 'Прежде всего стоит'\n"
    "• Fillers: 'Таким образом', 'В заключение', 'Подводя итог', 'В целом', "
    "'Как было отмечено выше', 'Исходя из вышесказанного', 'В данном контексте'\n"
    "• Overused intensifiers: 'Безусловно', 'Несомненно', 'Очевидно', 'Действительно', "
    "'Безусловно', 'Совершенно очевидно', 'Не вызывает сомнений'\n"
    "• AI structure tells: numbered lists of obvious points, perfect symmetrical paragraphs, "
    "every paragraph exactly the same length, ending with a tidy summary\n\n"

    "MAKE THE TEXT HUMAN:\n"
    "• Mix very short sentences (3-5 words) with longer ones (15-25 words) unpredictably\n"
    "• Allow slight informality — a contraction, a colloquial phrase, a dash instead of semicolon\n"
    "• Do NOT start every sentence with a noun phrase — use variety: verbs, adverbs, subordinates\n"
    "• Avoid bullet points and numbered lists unless the original had them\n"
    "• Do not end with a conclusion paragraph summarising what was just said\n"
    "• Some slight redundancy or a tangential thought is acceptable — humans do this\n"
    "Replace all AI patterns with direct, natural, varied, slightly imperfect human language."
)


# ---------------------------------------------------------------------------
# System prompts — define the transformation goal for each mode
# ---------------------------------------------------------------------------

SYSTEM_CONSERVATIVE = (
    f"{_AI_MARKER_BLOCK}\n\n"
    "You are an expert editor. Paraphrase the given text: change sentence structure, reorder clauses, "
    "and substitute vocabulary with synonyms. "
    "Preserve ALL factual content, named entities, dates, and numbers exactly. "
    "The output must be clearly distinct from the input at the phrase level without altering meaning. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_BALANCED = (
    f"{_AI_MARKER_BLOCK}\n\n"
    "You are a professional rewriter. Substantially rewrite the given text: "
    "restructure sentences, deliberately mix short and long sentences, reorder ideas within paragraphs, "
    "and use varied vocabulary. "
    "Preserve all key facts, entities, and arguments — but the surface form must read as a distinctly different text. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_EXPRESSIVE = (
    f"{_AI_MARKER_BLOCK}\n\n"
    "You are a skilled author rewriting in a vivid, engaging style. "
    "Transform the text significantly: vary rhythm and sentence length, use expressive and specific vocabulary, "
    "restructure paragraphs. The result must feel stylistically fresh and natural while retaining all factual content. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_MIMICKING = (
    f"{_AI_MARKER_BLOCK}\n\n"
    "You are a style adaptor. Rewrite the given text so it matches the tone, rhythm, "
    "sentence structure, and vocabulary style of the provided reference text. "
    "Preserve all factual content from the original text. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)


def _contract_note(contract: dict[str, Any] | None) -> str:
    if not contract:
        return ""
    protected = [e["text"] for e in contract.get("protected_entities", [])]
    numbers = [e["text"] for e in contract.get("protected_numbers", [])]
    key_terms = contract.get("key_terms", [])[:10]
    parts: list[str] = []
    if protected:
        parts.append(f"Keep these entities unchanged: {', '.join(protected[:15])}.")
    if numbers:
        parts.append(f"Keep these numbers/dates unchanged: {', '.join(numbers[:10])}.")
    if key_terms:
        parts.append(f"Key terms to preserve: {', '.join(key_terms)}.")
    return "\n".join(parts)


def _style_note(style_profile: dict[str, Any] | None) -> str:
    """Build a concise style instruction block from guidance_signals for the LLM prompt."""
    if not style_profile:
        return ""
    g = style_profile.get("guidance_signals", {})
    if not g:
        return ""

    lines: list[str] = ["Style instructions (match the reference author's style):"]

    # Sentence length & rhythm
    if g.get("target_sentence_length"):
        lines.append(f"- Average sentence length: ~{g['target_sentence_length']:.0f} words.")
    if g.get("rhythm_instruction"):
        lines.append(f"- Rhythm: {g['rhythm_instruction']}.")

    # Sentence openings
    if g.get("sentence_opening_instruction"):
        lines.append(f"- Sentence openings: {g['sentence_opening_instruction']}.")

    # Passive voice
    if g.get("passive_voice_instruction"):
        lines.append(f"- Voice: {g['passive_voice_instruction']}.")

    # Perspective (1st vs 3rd person)
    if g.get("perspective_instruction"):
        lines.append(f"- Perspective: {g['perspective_instruction']}.")

    # Formality
    if g.get("target_formality") is not None:
        f_val = g["target_formality"]
        label = "formal" if f_val > 0.65 else "informal/conversational" if f_val < 0.45 else "neutral"
        lines.append(f"- Register: {label} (formality index: {f_val:.2f}).")

    # Hedging
    if g.get("hedging_instruction"):
        lines.append(f"- Hedging: {g['hedging_instruction']}.")

    # Rhetorical questions
    if g.get("question_instruction"):
        lines.append(f"- Rhetorical questions: {g['question_instruction']}.")

    # Sentence complexity
    if g.get("complexity_instruction"):
        lines.append(f"- Sentence complexity: {g['complexity_instruction']}.")

    # Vocabulary
    if g.get("vocabulary_instruction"):
        lines.append(f"- Vocabulary: {g['vocabulary_instruction']}.")

    # Characteristic phrases — embed actual phrases from the style corpus
    phrases = g.get("characteristic_phrases", [])
    if phrases:
        lines.append(
            f"- Characteristic phrase patterns from the style corpus "
            f"(use naturally where appropriate): {', '.join(phrases[:6])}."
        )

    return "\n".join(lines)


def build_user_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    reference_sample: str | None = None,
    is_chunk: bool = False,
    chunk_idx: int = 0,
    total_chunks: int = 1,
    prev_context: str | None = None,
    user_instruction: str | None = None,
) -> str:
    """Build the user-turn content: context + constraints + text."""
    lines: list[str] = []

    if is_chunk and total_chunks > 1:
        lines.append(f"[Part {chunk_idx + 1} of {total_chunks}]")
    if prev_context:
        lines.append(f"[Preceding context: {prev_context}]")

    contract_note = _contract_note(contract)
    if contract_note:
        lines.append(contract_note)

    style_note = _style_note(style_profile)
    if style_note:
        lines.append(style_note)

    if user_instruction:
        lines.append(f"Additional requirement: {user_instruction}")

    if reference_sample:
        lines.append(f"Reference style:\n{reference_sample[:600]}")

    lines.append(f"Text to rewrite:\n{input_text}")
    return "\n\n".join(lines)


_TRANSLATION_LANG_NAMES: dict[str, str] = {
    "uk": "Ukrainian",
    "pl": "Polish",
    "de": "German",
    "fr": "French",
}


def get_translation_system_prompt(target_lang: str) -> str:
    lang_name = _TRANSLATION_LANG_NAMES.get(target_lang, target_lang)
    return (
        f"You are a professional translator. Translate the following text accurately into {lang_name}. "
        "Preserve the meaning, tone, and style exactly. "
        "Return ONLY the translated text — no explanations, no preamble."
    )


def get_adaptation_system_prompt(target_lang: str) -> str:
    lang_name = _TRANSLATION_LANG_NAMES.get(target_lang, target_lang)
    return (
        f"{_AI_MARKER_BLOCK}\n\n"
        f"You are a professional editor working in {lang_name}. "
        f"Revise the given text to sound completely natural and human-written in {lang_name}. "
        "Apply all the AI marker elimination rules above. "
        "Make the text flow naturally as if written by a native speaker. "
        "Return ONLY the revised text — no explanations, no tags, no preamble."
    )


SYSTEM_REFINEMENT = (
    f"{_AI_MARKER_BLOCK}\n\n"
    "You are a final-pass editor. The text below was rewritten but still contains AI-sounding patterns. "
    "Your sole job: hunt down every remaining AI marker listed above and replace it with natural human phrasing. "
    "Also break up any paragraph where every sentence is similar in length — vary the rhythm aggressively. "
    "Do NOT add new content. Do NOT change facts. Return ONLY the revised text."
)


def get_refinement_system_prompt() -> str:
    return SYSTEM_REFINEMENT


def get_system_prompt(
    mode: str,
    reference_sample: str | None = None,
) -> str:
    if reference_sample:
        return SYSTEM_MIMICKING
    return {
        "conservative": SYSTEM_CONSERVATIVE,
        "balanced": SYSTEM_BALANCED,
        "expressive": SYSTEM_EXPRESSIVE,
    }.get(mode, SYSTEM_BALANCED)


# Keep legacy functions for any external callers
def build_adversarial_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> str:
    return build_user_prompt(input_text, style_profile, contract)


def build_diversifying_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    mode: str = "balanced",
) -> str:
    return build_user_prompt(input_text, style_profile, contract)


def build_mimicking_prompt(
    input_text: str,
    reference_sample: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    mode: str = "balanced",
) -> str:
    return build_user_prompt(input_text, style_profile, contract, reference_sample)


def build_precision_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> str:
    """System prompt from Figure 2 of Cheng et al. 2025 (arXiv:2506.07001v1).

    The paraphraser LLM is instructed to wrap output in <TAG>...</TAG> so
    the engine can cleanly extract the rewritten text from the full response.
    """
    return (
        "You are a rephraser. Given any input text, you are supposed to rephrase the text "
        "without changing its meaning and content, while maintaining the text quality. "
        "Also, it is important for you to output a rephrased text that has a different style "
        "from the input text. The input is not just to make a few changes to the input text. "
        "The input text is given below. "
        "Print your rephrased output text between tags <TAG> and </TAG>.\n\n"
        f"{input_text}"
    )
