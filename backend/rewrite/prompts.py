"""Prompt templates for Guided Rewrite Engine."""

from __future__ import annotations

from typing import Any


DIVERSIFYING_PROMPT = """Revise the text to enrich its language diversity, employing varied sentence structures, synonyms, and stylistic nuances, while preserving the original meaning:

{input_text}
"""

# Adversarial system prompt — from docs/2506.07001v1, Figure 2
ADVERSARIAL_SYSTEM_PROMPT = (
    "You are a rephraser. Given any input text, you are supposed to rephrase the text "
    "without changing its meaning and content, while maintaining the text quality. "
    "Also, it is important for you to rephrase a text that has a different style from "
    "the input text. You can not just make a few changes to the input text. "
    "Print your rephrased output text between tags <TAG> and </TAG>."
)

MIMICKING_PROMPT = """Rewrite the text using the same language style, tone, and expression as the reference text. Focus on capturing the unique vocabulary, sentence structure, and stylistic elements evident in the reference:

{input_text}

# Reference Text:
{reference_sample}
"""


def build_diversifying_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    mode: str = "balanced",
) -> str:
    """Build a Diversifying prompt with style and contract guidance."""
    sections: list[str] = [DIVERSIFYING_PROMPT.format(input_text=input_text)]
    if style_profile:
        guidance = style_profile.get("guidance_signals", {})
        sections.append(
            f"# Style Guidance\n"
            f"Target sentence length: {guidance.get('target_sentence_length', 'varied')}. "
            f"Target burstiness: {guidance.get('target_burstiness', 'moderate')}. "
            f"Target formality: {guidance.get('target_formality', 'balanced')}."
        )
    if contract:
        sections.append(
            f"# Semantic Protection ({contract.get('mode', 'balanced')})\n"
            f"Protected entities: {[e['text'] for e in contract.get('protected_entities', [])]}. "
            f"Key terms: {contract.get('key_terms', [])}."
        )
    sections.append(f"# Mode\n{mode.capitalize()}")
    return "\n\n".join(sections)


def build_mimicking_prompt(
    input_text: str,
    reference_sample: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    mode: str = "balanced",
) -> str:
    """Build a Mimicking (reference-driven) prompt."""
    sections: list[str] = [
        MIMICKING_PROMPT.format(
            input_text=input_text,
            reference_sample=reference_sample,
        )
    ]
    if style_profile:
        guidance = style_profile.get("guidance_signals", {})
        sections.append(
            f"# Style Guidance\n"
            f"Target sentence length: {guidance.get('target_sentence_length', 'varied')}. "
            f"Target burstiness: {guidance.get('target_burstiness', 'moderate')}. "
            f"Target formality: {guidance.get('target_formality', 'balanced')}."
        )
    if contract:
        sections.append(
            f"# Semantic Protection ({contract.get('mode', 'balanced')})\n"
            f"Protected entities: {[e['text'] for e in contract.get('protected_entities', [])]}. "
            f"Key terms: {contract.get('key_terms', [])}."
        )
    sections.append(f"# Mode\n{mode.capitalize()}")
    return "\n\n".join(sections)


def build_adversarial_prompt(
    input_text: str,
    style_profile: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
) -> str:
    """Build adversarial paraphrasing prompt (docs/2506.07001v1, Figure 2)."""
    sections: list[str] = [
        ADVERSARIAL_SYSTEM_PROMPT,
        f"Input text:\n{input_text}",
    ]
    if contract:
        protected = [e["text"] for e in contract.get("protected_entities", [])]
        key_terms = contract.get("key_terms", [])
        if protected or key_terms:
            sections.append(
                f"# Semantic Protection\nDo NOT change: {protected + key_terms}."
            )
    if style_profile:
        guidance = style_profile.get("guidance_signals", {})
        if guidance:
            sections.append(
                f"# Style Guidance\n"
                f"Target burstiness: {guidance.get('target_burstiness', 'moderate')}. "
                f"Target formality: {guidance.get('target_formality', 'balanced')}."
            )
    return "\n\n".join(sections)
