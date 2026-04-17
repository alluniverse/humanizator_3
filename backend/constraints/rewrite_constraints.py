"""Rewrite Constraint Layer: POS, MPR, USE similarity constraints."""

from __future__ import annotations

import re
from typing import Any

from infrastructure.config import settings


class RewriteConstraintLayer:
    """Enforces rewrite constraints based on docs/2404.01907v1 (HMGC)."""

    def __init__(self) -> None:
        self._nlp_en: Any = None
        self._nlp_ru: Any = None
        self._sentence_model: Any = None

    def _get_nlp(self, language: str) -> Any:
        import spacy
        if language == "ru":
            if self._nlp_ru is None:
                self._nlp_ru = spacy.load("ru_core_news_sm")
            return self._nlp_ru
        if self._nlp_en is None:
            self._nlp_en = spacy.load("en_core_web_sm")
        return self._nlp_en

    def _get_sentence_model(self) -> Any:
        if self._sentence_model is None:
            from sentence_transformers import SentenceTransformer
            self._sentence_model = SentenceTransformer(settings.sentence_transformer_model)
        return self._sentence_model

    def check_pos_constraint(
        self,
        original: str,
        rewritten: str,
        language: str = "ru",
        allowed_exceptions: set[str] | None = None,
    ) -> dict[str, Any]:
        """Check that rewritten tokens maintain POS alignment where required."""
        nlp = self._get_nlp(language)
        doc_orig = nlp(original)
        doc_rewr = nlp(rewritten)

        allowed = allowed_exceptions or set()
        violations: list[dict[str, Any]] = []

        # Simple word-level alignment by lowercase lemma
        orig_map = {t.lemma_.lower(): t.pos_ for t in doc_orig if not t.is_space and not t.is_punct}
        for token in doc_rewr:
            if token.is_space or token.is_punct:
                continue
            lemma = token.lemma_.lower()
            if lemma in orig_map and orig_map[lemma] != token.pos_:
                if f"{orig_map[lemma]}->{token.pos_}" not in allowed:
                    violations.append(
                        {
                            "token": token.text,
                            "original_pos": orig_map[lemma],
                            "rewritten_pos": token.pos_,
                        }
                    )

        return {
            "valid": len(violations) == 0,
            "violations": violations,
        }

    def check_mpr_constraint(
        self,
        original: str,
        rewritten: str,
        max_ratio: float = 0.4,
    ) -> dict[str, Any]:
        """Check Maximum Perturbed Ratio at sentence and text level."""
        orig_words = original.split()
        rewr_words = rewritten.split()
        orig_len = len(orig_words)
        rewr_len = len(rewr_words)

        # Token-level change estimate via simple diff
        changed = sum(1 for a, b in zip(orig_words, rewr_words) if a != b)
        changed += abs(orig_len - rewr_len)
        ratio = changed / orig_len if orig_len else 0.0

        return {
            "valid": ratio <= max_ratio,
            "original_tokens": orig_len,
            "rewritten_tokens": rewr_len,
            "changed_tokens": changed,
            "ratio": round(ratio, 3),
            "max_ratio": max_ratio,
        }

    def check_use_similarity(
        self,
        original: str,
        rewritten: str,
        threshold: float = 0.75,
        window_tokens: int = 50,
    ) -> dict[str, Any]:
        """Check Universal Sentence Encoder (proxy) similarity between original and rewritten."""
        # Chunk into windows if needed
        orig_chunks = self._chunk_text(original, window_tokens)
        rewr_chunks = self._chunk_text(rewritten, window_tokens)

        from sentence_transformers import util
        model = self._get_sentence_model()
        embeddings_orig = model.encode(orig_chunks, convert_to_tensor=True)
        embeddings_rewr = model.encode(rewr_chunks, convert_to_tensor=True)

        # Pairwise min similarity across aligned chunks
        min_sim = 1.0
        similarities: list[float] = []
        for i in range(min(len(embeddings_orig), len(embeddings_rewr))):
            sim = util.pytorch_cos_sim(embeddings_orig[i], embeddings_rewr[i]).item()
            similarities.append(sim)
            min_sim = min(min_sim, sim)

        return {
            "valid": min_sim >= threshold,
            "min_similarity": round(min_sim, 3),
            "threshold": threshold,
            "chunk_similarities": [round(s, 3) for s in similarities],
        }

    def check_protected_spans(
        self,
        rewritten: str,
        protected_spans: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Ensure protected spans from semantic contract are preserved."""
        violations = []
        for span in protected_spans:
            text = span.get("text", "")
            if text and text not in rewritten:
                violations.append({"missing": text})
        return {
            "valid": len(violations) == 0,
            "violations": violations,
        }

    def validate_all(
        self,
        original: str,
        rewritten: str,
        contract: dict[str, Any],
        language: str = "ru",
    ) -> dict[str, Any]:
        """Run all constraints and return aggregated result."""
        constraints_config = contract.get("constraints", {})
        mpr = constraints_config.get("maximum_perturbed_ratio", 0.4)
        use_threshold = constraints_config.get("use_similarity_threshold", 0.75)
        pos_flag = constraints_config.get("pos_constraint_flag", True)

        protected_spans = contract.get("protected_entities", []) + contract.get("protected_numbers", [])

        results: dict[str, Any] = {}
        if pos_flag:
            results["pos"] = self.check_pos_constraint(original, rewritten, language)
        results["mpr"] = self.check_mpr_constraint(original, rewritten, max_ratio=mpr)
        results["use_similarity"] = self.check_use_similarity(original, rewritten, threshold=use_threshold)
        results["protected_spans"] = self.check_protected_spans(rewritten, protected_spans)

        all_valid = all(r.get("valid", True) for r in results.values())
        return {
            "valid": all_valid,
            "details": results,
        }

    def _chunk_text(self, text: str, max_tokens: int) -> list[str]:
        words = text.split()
        if len(words) <= max_tokens:
            return [text]
        chunks: list[str] = []
        for i in range(0, len(words), max_tokens):
            chunks.append(" ".join(words[i : i + max_tokens]))
        return chunks


rewrite_constraint_layer = RewriteConstraintLayer()
