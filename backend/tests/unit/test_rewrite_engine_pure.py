"""Unit tests: GuidedRewriteEngine — pure text processing methods (no LLM)."""

import pytest

from rewrite.guided_rewrite import GuidedRewriteEngine, CHUNK_THRESHOLD_WORDS, CHUNK_TARGET_WORDS
from rewrite.prompts import (
    build_diversifying_prompt,
    build_mimicking_prompt,
    build_adversarial_prompt,
    ADVERSARIAL_SYSTEM_PROMPT,
)


def _engine() -> GuidedRewriteEngine:
    """Create engine without instantiating the LLM provider."""
    obj = object.__new__(GuidedRewriteEngine)
    return obj


class TestChunkSplitting:
    def test_short_text_stays_whole(self) -> None:
        engine = _engine()
        text = "Short text. Just one paragraph."
        chunks = engine._split_into_chunks(text)
        assert chunks == [text]

    def test_paragraphs_merged_when_small(self) -> None:
        engine = _engine()
        # Two small paragraphs should merge
        text = "First paragraph.\n\nSecond paragraph."
        chunks = engine._split_into_chunks(text)
        assert len(chunks) == 1
        assert "First" in chunks[0]
        assert "Second" in chunks[0]

    def test_large_text_splits_into_multiple_chunks(self) -> None:
        engine = _engine()
        # Build a text well over CHUNK_THRESHOLD_WORDS with clear paragraph breaks
        para = "The quick brown fox jumps over the lazy dog. " * 30  # ~240 words
        text = para + "\n\n" + para + "\n\n" + para
        chunks = engine._split_into_chunks(text)
        assert len(chunks) >= 2

    def test_empty_text_returns_list(self) -> None:
        engine = _engine()
        chunks = engine._split_into_chunks("")
        assert isinstance(chunks, list)
        assert len(chunks) >= 1

    def test_single_huge_paragraph_splits(self) -> None:
        engine = _engine()
        # Build one continuous paragraph > CHUNK_TARGET_WORDS with sentences
        sentences = ["This is sentence number {}.".format(i) for i in range(50)]
        text = " ".join(sentences)
        chunks = engine._split_into_chunks(text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.split()) <= CHUNK_TARGET_WORDS + 20  # allow small overflow


class TestContextPrefixHandling:
    def test_no_prefix_for_first_chunk(self) -> None:
        engine = _engine()
        result = engine._add_context_prefix("My chunk.", prev_context=None, idx=0)
        assert result == "My chunk."

    def test_prefix_added_for_subsequent_chunks(self) -> None:
        engine = _engine()
        result = engine._add_context_prefix("New chunk.", prev_context="Previous sentence.", idx=1)
        assert result.startswith("[Previous context: Previous sentence.]")
        assert "New chunk." in result

    def test_strip_echoed_context_prefix(self) -> None:
        engine = _engine()
        text = "[Previous context: Summary.]\n\nActual rewritten content here."
        stripped = engine._strip_context_echo(text, prev_context="Summary.")
        assert not stripped.startswith("[Previous context:")
        assert "Actual rewritten content" in stripped

    def test_strip_noop_when_no_prev_context(self) -> None:
        engine = _engine()
        text = "Normal text without prefix."
        result = engine._strip_context_echo(text, prev_context=None)
        assert result == text


class TestFirstSentence:
    def test_extracts_first_sentence(self) -> None:
        engine = _engine()
        text = "First sentence ends here. Second sentence follows."
        result = engine._first_sentence(text)
        assert result == "First sentence ends here."

    def test_fallback_to_truncation_when_no_period(self) -> None:
        engine = _engine()
        text = "A " * 200
        result = engine._first_sentence(text)
        assert len(result) <= 102  # 100 chars + minor tolerance


class TestReassembleChunks:
    def test_reassemble_joins_with_double_newline(self) -> None:
        engine = _engine()
        chunks = ["Chunk one.", "Chunk two.", "Chunk three."]
        result = engine._reassemble_chunks(chunks)
        assert result == "Chunk one.\n\nChunk two.\n\nChunk three."

    def test_empty_chunks_filtered(self) -> None:
        engine = _engine()
        result = engine._reassemble_chunks(["", "Content.", "   ", "More."])
        assert result == "Content.\n\nMore."

    def test_temperature_for_modes(self) -> None:
        engine = _engine()
        assert engine._temperature_for_mode("conservative") == 0.3
        assert engine._temperature_for_mode("balanced") == 0.6
        assert engine._temperature_for_mode("expressive") == 0.9
        assert engine._temperature_for_mode("unknown") == 0.6


class TestPromptBuilders:
    def test_diversifying_includes_text(self) -> None:
        prompt = build_diversifying_prompt("Test input text")
        assert "Test input text" in prompt

    def test_diversifying_includes_style_profile(self) -> None:
        profile = {
            "guidance_signals": {
                "target_sentence_length": "medium",
                "target_burstiness": "high",
                "target_formality": "formal",
            }
        }
        prompt = build_diversifying_prompt("Input.", style_profile=profile)
        assert "medium" in prompt
        assert "high" in prompt
        assert "formal" in prompt

    def test_diversifying_includes_contract(self) -> None:
        contract = {
            "mode": "balanced",
            "protected_entities": [{"text": "Tesla"}],
            "key_terms": ["electric"],
        }
        prompt = build_diversifying_prompt("Text.", contract=contract)
        assert "Tesla" in prompt
        assert "electric" in prompt

    def test_mimicking_includes_reference(self) -> None:
        prompt = build_mimicking_prompt("Input text.", "Reference style sample.")
        assert "Input text." in prompt
        assert "Reference style sample." in prompt

    def test_adversarial_contains_system_prompt(self) -> None:
        prompt = build_adversarial_prompt("Some text to paraphrase.")
        assert ADVERSARIAL_SYSTEM_PROMPT in prompt
        assert "Some text to paraphrase." in prompt

    def test_adversarial_includes_protected_terms(self) -> None:
        contract = {
            "protected_entities": [{"text": "NASA"}],
            "key_terms": ["orbit", "satellite"],
        }
        prompt = build_adversarial_prompt("Text.", contract=contract)
        assert "NASA" in prompt
        assert "orbit" in prompt
