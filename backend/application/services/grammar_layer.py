"""Grammar Layer: final language polishing without sterilization."""

from __future__ import annotations

from typing import Any

from language_tool_python import LanguageTool


class GrammarLayer:
    """Applies lightweight grammar and typographic corrections."""

    def __init__(self) -> None:
        self._lt_en = LanguageTool("en-US")
        self._lt_ru = LanguageTool("ru-RU")

    def check(self, text: str, language: str = "ru") -> dict[str, Any]:
        """Run grammar check and return suggestions."""
        lt = self._lt_ru if language == "ru" else self._lt_en
        matches = lt.check(text)

        corrections: list[dict[str, Any]] = []
        for m in matches:
            # Skip style-only rules to avoid over-sterilization
            if m.rule_issue_type == "style":
                continue
            corrections.append(
                {
                    "message": m.message,
                    "context": m.context,
                    "replacements": m.replacements[:3],
                    "offset": m.offset,
                    "length": m.error_length,
                    "rule_id": m.rule_id,
                }
            )

        # Auto-apply safe corrections (spelling, basic grammar)
        corrected = lt.correct(text)

        return {
            "original_text": text,
            "corrected_text": corrected,
            "corrections": corrections,
            "correction_count": len(corrections),
        }


grammar_layer = GrammarLayer()
