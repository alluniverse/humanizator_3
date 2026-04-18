"""Prompt templates for Guided Rewrite Engine."""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# System prompts — define the transformation goal for each mode
# ---------------------------------------------------------------------------

SYSTEM_CONSERVATIVE = (
    "You are an expert editor. Your task is to paraphrase the given text. "
    "Change sentence structure, reorder clauses, and substitute vocabulary with synonyms. "
    "The rewritten text must preserve ALL factual content, named entities, dates, and numbers exactly. "
    "Make the output clearly distinct from the input at the phrase level, but do not alter the meaning. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_BALANCED = (
    "You are a professional rewriter. Substantially rewrite the given text. "
    "Restructure sentences, vary sentence length (mix short and long), change the order of ideas within paragraphs, "
    "and use different vocabulary where possible. "
    "Preserve all key facts, entities, and arguments — but the surface form should read as a distinctly different text. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_EXPRESSIVE = (
    "You are a skilled author rewriting a text in a vivid, engaging style. "
    "Transform the text significantly: vary rhythm, use expressive vocabulary, restructure paragraphs. "
    "The result should feel stylistically fresh and natural while retaining all factual content. "
    "Return ONLY the rewritten text — no explanations, no tags, no preamble."
)

SYSTEM_MIMICKING = (
    "You are a style adaptor. Rewrite the given text so that it matches the tone, rhythm, "
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
    if not style_profile:
        return ""
    g = style_profile.get("guidance_signals", {})
    parts: list[str] = []
    if g.get("target_sentence_length"):
        parts.append(f"Target sentence length: {g['target_sentence_length']}.")
    if g.get("target_burstiness"):
        parts.append(f"Sentence length variety: {g['target_burstiness']}.")
    if g.get("target_formality"):
        parts.append(f"Formality level: {g['target_formality']}.")
    return " ".join(parts)


def build_user_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    reference_sample: str | None = None,
    is_chunk: bool = False,
    chunk_idx: int = 0,
    total_chunks: int = 1,
    prev_context: str | None = None,
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

    if reference_sample:
        lines.append(f"Reference style:\n{reference_sample[:600]}")

    lines.append(f"Text to rewrite:\n{input_text}")
    return "\n\n".join(lines)


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
    return (
        "Rephrase the following text to sound natural and human-written. "
        "Preserve the original meaning. Vary sentence length and vocabulary.\n\n"
        f"Text:\n{input_text}\n\nRephrased:"
    )
