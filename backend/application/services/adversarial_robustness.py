"""Adversarial Robustness Evaluator.

Evaluates how robust a rewrite variant is against adversarial perturbations,
inspired by Cheng et al. (2025) "Adversarial Paraphrasing" (arXiv:2506.07001).

Key idea: a robust humanized text should maintain semantic integrity even when
subjected to adversarial character-level, word-level, and sentence-level attacks.

Attack types:
  - char_substitution: homoglyph/typo injection
  - word_deletion: drop low-salience words
  - sentence_shuffle: reorder sentences
  - tag_injection: insert <TAG>...</TAG> wrappers (as per 2506.07001)
  - negation_flip: insert negation (stress-test semantic preservation)
"""

from __future__ import annotations

import math
import random
import re
from typing import Any

import torch


def _cosine_sim(a: "torch.Tensor", b: "torch.Tensor") -> float:
    a_n = a / (a.norm() + 1e-9)
    b_n = b / (b.norm() + 1e-9)
    return float(torch.dot(a_n, b_n).clamp(-1, 1))


# ---------------------------------------------------------------------------
# Attack implementations (deterministic seed for reproducibility)
# ---------------------------------------------------------------------------

_HOMOGLYPHS: dict[str, str] = {
    "a": "а",  # Cyrillic а looks like Latin a
    "e": "е",  # Cyrillic е
    "o": "о",  # Cyrillic о
    "p": "р",  # Cyrillic р
    "c": "с",  # Cyrillic с
    "x": "х",  # Cyrillic х
}


def _attack_char_substitution(text: str, rate: float = 0.05, seed: int = 42) -> str:
    """Replace a fraction of Latin letters with visually identical Cyrillic ones."""
    rng = random.Random(seed)
    chars = list(text)
    candidates = [i for i, ch in enumerate(chars) if ch in _HOMOGLYPHS]
    n = max(1, int(len(candidates) * rate))
    for i in rng.sample(candidates, min(n, len(candidates))):
        chars[i] = _HOMOGLYPHS[chars[i]]
    return "".join(chars)


def _attack_word_deletion(text: str, rate: float = 0.10, seed: int = 42) -> str:
    """Delete a random fraction of non-stopword tokens."""
    rng = random.Random(seed)
    words = text.split()
    stopwords = {"the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "of",
                 "и", "в", "на", "по", "за", "с", "к", "у", "до", "из", "без"}
    candidates = [i for i, w in enumerate(words) if w.lower().strip(".,;:!?") not in stopwords]
    n = max(1, int(len(candidates) * rate))
    drop = set(rng.sample(candidates, min(n, len(candidates))))
    return " ".join(w for i, w in enumerate(words) if i not in drop)


def _attack_sentence_shuffle(text: str, seed: int = 42) -> str:
    """Randomly reorder sentences."""
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    if len(sents) <= 1:
        return text
    rng = random.Random(seed)
    rng.shuffle(sents)
    return " ".join(sents)


def _attack_tag_injection(text: str) -> str:
    """Wrap key noun phrases in adversarial <TAG>...</TAG> markers (Cheng et al. 2025)."""
    # Simple heuristic: wrap capitalised multi-word sequences
    return re.sub(r"([A-ZА-Я][a-zа-яёА-ЯЁ]+(?:\s+[A-ZА-Я][a-zа-яёА-ЯЁ]+)+)", r"<TAG>\1</TAG>", text)


def _attack_negation_flip(text: str) -> str:
    """Insert 'NOT' after first auxiliary/modal as a semantic stress test."""
    return re.sub(
        r"\b(is|are|was|were|will|would|can|could|should|shall|may|might|must)\b",
        r"\1 NOT",
        text,
        count=1,
        flags=re.IGNORECASE,
    )


ATTACK_REGISTRY: dict[str, Any] = {
    "char_substitution": _attack_char_substitution,
    "word_deletion": _attack_word_deletion,
    "sentence_shuffle": _attack_sentence_shuffle,
    "tag_injection": _attack_tag_injection,
    "negation_flip": _attack_negation_flip,
}


# ---------------------------------------------------------------------------
# Robustness evaluator
# ---------------------------------------------------------------------------


class AdversarialRobustnessEvaluator:
    """Evaluates semantic robustness of a rewrite under adversarial perturbations.

    For each attack type, computes the cosine similarity between the sentence
    embeddings of the original rewrite and the perturbed rewrite.  A high mean
    similarity (≥ semantic_threshold) indicates the text is robust — its
    embedding is not easily moved by surface-level adversarial edits.
    """

    def __init__(self) -> None:
        self._model: Any = None  # lazy-loaded on first use

    def _get_model(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            from infrastructure.config import settings
            self._model = SentenceTransformer(settings.sentence_transformer_model)
        return self._model

    def _embed(self, text: str) -> "torch.Tensor":
        emb = self._get_model().encode(text, convert_to_tensor=True)
        return emb  # type: ignore[return-value]

    def evaluate(
        self,
        rewritten_text: str,
        attacks: list[str] | None = None,
        semantic_threshold: float = 0.75,
    ) -> dict[str, Any]:
        """Run adversarial attacks and measure semantic stability.

        Args:
            rewritten_text: The humanized rewrite to stress-test.
            attacks: List of attack names; defaults to all registered attacks.
            semantic_threshold: Minimum mean similarity to pass.

        Returns:
            {
              "passed": bool,
              "mean_similarity": float,
              "threshold": float,
              "attack_results": {attack_name: {"perturbed": str, "similarity": float}},
              "fragile_attacks": [list of attacks that dropped below threshold],
            }
        """
        if attacks is None:
            attacks = list(ATTACK_REGISTRY.keys())

        original_emb = self._embed(rewritten_text)
        attack_results: dict[str, Any] = {}
        similarities: list[float] = []

        for attack_name in attacks:
            fn = ATTACK_REGISTRY.get(attack_name)
            if fn is None:
                continue
            try:
                perturbed = fn(rewritten_text)
                perturbed_emb = self._embed(perturbed)
                sim = _cosine_sim(original_emb, perturbed_emb)
            except Exception as exc:
                attack_results[attack_name] = {"error": str(exc)}
                continue

            attack_results[attack_name] = {
                "perturbed": perturbed[:300],  # truncate for payload size
                "similarity": round(sim, 4),
            }
            similarities.append(sim)

        mean_sim = sum(similarities) / len(similarities) if similarities else 0.0
        fragile = [
            name
            for name, res in attack_results.items()
            if isinstance(res.get("similarity"), float) and res["similarity"] < semantic_threshold
        ]

        return {
            "passed": mean_sim >= semantic_threshold and len(fragile) == 0,
            "mean_similarity": round(mean_sim, 4),
            "threshold": semantic_threshold,
            "attack_results": attack_results,
            "fragile_attacks": fragile,
        }


adversarial_robustness_evaluator = AdversarialRobustnessEvaluator()
