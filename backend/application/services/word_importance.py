"""Word Importance Scorer: gradient-based + perplexity-based importance."""

from __future__ import annotations

from typing import Any

import torch
from transformers import GPT2LMHeadModel, GPT2Tokenizer

from infrastructure.config import settings


class WordImportanceScorer:
    """Dual-aspect word importance scoring."""

    def __init__(self) -> None:
        self._tokenizer = GPT2Tokenizer.from_pretrained(settings.perplexity_model)
        self._model = GPT2LMHeadModel.from_pretrained(settings.perplexity_model)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = self._model.to(device).eval()
        self._device = device

    def score_text(
        self,
        text: str,
        alpha: float = 0.2,
    ) -> list[dict[str, Any]]:
        """Return importance score for each token in the text.

        I_wi = (1 - alpha) * I^g_wi + alpha * I^p_wi
        For MVP we implement perplexity-based importance only,
        gradient-based requires a surrogate classifier which is optional.
        """
        tokens = self._tokenizer.tokenize(text)
        token_ids = self._tokenizer.encode(text, return_tensors="pt").to(self._device)

        # Baseline perplexity
        baseline_ppl = self._compute_perplexity(token_ids)

        scores: list[dict[str, Any]] = []
        for i, tok in enumerate(tokens):
            # Remove token i by rebuilding sequence without it
            reduced_ids = torch.cat([token_ids[:, : i + 1], token_ids[:, i + 2 :]], dim=1)
            reduced_ppl = self._compute_perplexity(reduced_ids)
            ip = reduced_ppl - baseline_ppl

            # Gradient component placeholder (would need surrogate model)
            ig = 0.0

            importance = (1 - alpha) * ig + alpha * ip
            scores.append(
                {
                    "token": tok,
                    "index": i,
                    "perplexity_importance": round(ip, 4),
                    "gradient_importance": round(ig, 4),
                    "importance": round(importance, 4),
                }
            )

        return scores

    def _compute_perplexity(self, token_ids: torch.Tensor) -> float:
        with torch.no_grad():
            outputs = self._model(token_ids, labels=token_ids)
            return torch.exp(outputs.loss).item()


word_importance_scorer = WordImportanceScorer()
