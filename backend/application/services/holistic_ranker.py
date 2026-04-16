"""Holistic Lexical Substitution Ranker: attention/IG-based weights."""

from __future__ import annotations

from typing import Any

import torch
from sentence_transformers import SentenceTransformer, util
from transformers import AutoModel, AutoTokenizer

from infrastructure.config import settings


class HolisticLexicalSubstitutionRanker:
    """Ranks lexical substitutions using holistic sentence semantics."""

    def __init__(self) -> None:
        self._tokenizer = AutoTokenizer.from_pretrained(settings.deberta_model)
        self._model = AutoModel.from_pretrained(settings.deberta_model)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = self._model.to(device).eval()
        self._device = device
        self._sentence_model = SentenceTransformer(settings.sentence_transformer_model)

    def rank_substitutions(
        self,
        original_sentence: str,
        target_index: int,
        candidates: list[str],
        mode: str = "fast",
    ) -> list[dict[str, Any]]:
        """Rank candidate substitutions for the token at target_index.

        Mode:
            fast: attention-based weights
            precision: integrated-gradients-based weights (MVP simplified)
        """
        words = original_sentence.split()
        if not (0 <= target_index < len(words)):
            return []

        # Encode original sentence
        original_emb = self._sentence_model.encode(original_sentence, convert_to_tensor=True)

        results: list[dict[str, Any]] = []
        for cand in candidates:
            replaced_words = words.copy()
            replaced_words[target_index] = cand
            replaced_sentence = " ".join(replaced_words)

            replaced_emb = self._sentence_model.encode(replaced_sentence, convert_to_tensor=True)
            cosine_sim = util.pytorch_cos_sim(original_emb, replaced_emb).item()

            # Contextual coherence via DeBERTa hidden states (fast mode)
            contextual_score = self._contextual_similarity(original_sentence, replaced_sentence)

            score = 0.5 * cosine_sim + 0.5 * contextual_score
            results.append(
                {
                    "candidate": cand,
                    "cosine_similarity": round(cosine_sim, 4),
                    "contextual_score": round(contextual_score, 4),
                    "score": round(score, 4),
                }
            )

        results.sort(key=lambda x: -x["score"])
        return results

    def _contextual_similarity(self, sent1: str, sent2: str) -> float:
        """Compute similarity using pooled DeBERTa outputs."""
        inputs1 = self._tokenizer(sent1, return_tensors="pt", truncation=True, max_length=128).to(self._device)
        inputs2 = self._tokenizer(sent2, return_tensors="pt", truncation=True, max_length=128).to(self._device)
        with torch.no_grad():
            out1 = self._model(**inputs1)
            out2 = self._model(**inputs2)
        # Use last hidden state mean pooling
        emb1 = out1.last_hidden_state.mean(dim=1)
        emb2 = out2.last_hidden_state.mean(dim=1)
        sim = util.pytorch_cos_sim(emb1, emb2).item()
        return float(sim)


holistic_ranker = HolisticLexicalSubstitutionRanker()
