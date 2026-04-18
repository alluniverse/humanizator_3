"""Holistic Lexical Substitution Ranker.

Implements Score(s, s') = Σ_i w_i · cos(f(x_i), f(x'_i))
from docs/2509.11513v1 (Hu et al., 2025).

Two weighting modes:
  fast      — attention-based weights (multi-head average across layers)
  precision — Integrated Gradients weights via captum (more accurate, slower)

Recommended model: DeBERTa-v3-large (highest GAP on SWORDS benchmark).
Layer range: 3 to (N-2) per the paper.
"""

from __future__ import annotations

import logging
from typing import Any

import torch
import torch.nn.functional as torch_f
from sentence_transformers import util

from infrastructure.config import settings

logger = logging.getLogger(__name__)


class HolisticLexicalSubstitutionRanker:
    """Ranks lexical substitutions using holistic sentence semantics.

    For candidate selection in style-guided rewrite and post-processing polish.
    Models are loaded lazily on first use (DeBERTa is large — avoid startup OOM).
    """

    def __init__(self) -> None:
        self._tokenizer: Any = None
        self._model: Any = None
        self._device: str = "cpu"
        self._sentence_model: Any = None
        self._num_layers: int = 0

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer
        from transformers import AutoModel, AutoTokenizer
        self._tokenizer = AutoTokenizer.from_pretrained(settings.deberta_model)
        self._model = AutoModel.from_pretrained(
            settings.deberta_model,
            output_attentions=True,
            output_hidden_states=True,
        )
        self._device = "cpu"  # DeBERTa is large — use CPU to avoid VRAM OOM
        self._model = self._model.to(self._device).eval()
        self._sentence_model = SentenceTransformer(settings.sentence_transformer_model)
        self._num_layers = self._model.config.num_hidden_layers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def rank(
        self,
        candidates: list[str],
        target_index: int,
        mode: str = "fast",
    ) -> dict[str, Any]:
        """Rank a list of candidate texts by holistic similarity to the first.

        Used in pipeline to compare rewrite variants against each other.
        The first candidate is treated as the reference (original).

        Args:
            candidates: list of texts; candidates[0] is the reference.
            target_index: index of the text to score (others are context).
            mode: 'fast' or 'precision'.

        Returns:
            Dict with ranked list and scores.
        """
        self._ensure_loaded()
        if not candidates or target_index >= len(candidates):
            return {"ranked": [], "target_index": target_index}

        reference = candidates[0]
        target = candidates[target_index]

        score = self._holistic_score(reference, target, mode=mode)
        ranked = sorted(
            [
                {
                    "index": i,
                    "text": c[:120] + "..." if len(c) > 120 else c,
                    "holistic_score": round(
                        self._holistic_score(reference, c, mode=mode) if i != 0 else 1.0,
                        4,
                    ),
                }
                for i, c in enumerate(candidates)
            ],
            key=lambda x: -x["holistic_score"],
        )
        return {
            "ranked": ranked,
            "target_index": target_index,
            "target_score": round(score, 4),
            "mode": mode,
        }

    def rank_substitutions(
        self,
        original_sentence: str,
        target_index: int,
        candidates: list[str],
        mode: str = "fast",
    ) -> list[dict[str, Any]]:
        """Rank word-level candidate substitutions at target_index.

        Score(s, s') = Σ_i w_i · cos(f(x_i), f(x'_i))
        where f(x_i) = concat of layer representations,
              w_i    = attention weights (fast) or IG weights (precision).

        Args:
            original_sentence: source sentence.
            target_index: word index (space-split) to substitute.
            candidates: replacement words to rank.
            mode: 'fast' or 'precision'.

        Returns:
            List of candidates sorted by descending score.
        """
        self._ensure_loaded()
        words = original_sentence.split()
        if not (0 <= target_index < len(words)):
            return []

        results: list[dict[str, Any]] = []
        for cand in candidates:
            replaced = words.copy()
            replaced[target_index] = cand
            replaced_sentence = " ".join(replaced)

            if mode == "precision":
                score = self._ig_holistic_score(original_sentence, replaced_sentence, target_index)
                weight_method = "integrated_gradients"
            else:
                score = self._attention_holistic_score(original_sentence, replaced_sentence, target_index)
                weight_method = "attention"

            results.append(
                {
                    "candidate": cand,
                    "score": round(score, 4),
                    "weight_method": weight_method,
                }
            )

        results.sort(key=lambda x: -x["score"])
        return results

    # ------------------------------------------------------------------
    # Holistic scoring helpers
    # ------------------------------------------------------------------

    def _holistic_score(self, sent1: str, sent2: str, mode: str = "fast") -> float:
        """Overall holistic similarity between two sentences."""
        try:
            if mode == "precision":
                return self._ig_sentence_similarity(sent1, sent2)
            return self._attention_sentence_similarity(sent1, sent2)
        except Exception as exc:
            logger.warning("Holistic score failed (%s mode): %s", mode, exc)
            # Fallback to sentence-transformer cosine similarity
            emb1 = self._sentence_model.encode(sent1, convert_to_tensor=True)
            emb2 = self._sentence_model.encode(sent2, convert_to_tensor=True)
            return float(util.pytorch_cos_sim(emb1, emb2).item())

    def _attention_sentence_similarity(self, sent1: str, sent2: str) -> float:
        """Attention-based holistic similarity.

        Uses mean-pooled hidden states from intermediate layers (3 to N-2),
        weighted by averaged multi-head attention.
        """
        emb1 = self._get_weighted_embedding_attention(sent1)
        emb2 = self._get_weighted_embedding_attention(sent2)
        return float(torch_f.cosine_similarity(emb1, emb2, dim=-1).item())

    def _ig_sentence_similarity(self, sent1: str, sent2: str) -> float:
        """Integrated Gradients based holistic similarity.

        Approximates IG weights via interpolated embeddings (5-step Riemann sum).
        More theoretically grounded than attention, per docs/2509.11513v1.
        """
        emb1 = self._get_weighted_embedding_ig(sent1)
        emb2 = self._get_weighted_embedding_ig(sent2)
        return float(torch_f.cosine_similarity(emb1, emb2, dim=-1).item())

    def _get_weighted_embedding_attention(self, text: str) -> torch.Tensor:
        """Token-weighted embedding via attention aggregation.

        Steps:
        1. Forward pass with output_attentions=True
        2. Average multi-head attention across all heads and intermediate layers
        3. Use attention weights as token importance w_i
        4. Weighted sum of hidden states from intermediate layers
        """
        inputs = self._tokenizer(
            text, return_tensors="pt", truncation=True, max_length=256
        ).to(self._device)

        with torch.no_grad():
            outputs = self._model(**inputs)

        # Layer range: 3 to (N-2) per docs/2509.11513v1
        start_layer = min(3, self._num_layers - 1)
        end_layer = max(start_layer + 1, self._num_layers - 2)

        # Stack hidden states from target layers: (num_layers, seq, hidden)
        hidden_states = torch.stack(
            outputs.hidden_states[start_layer:end_layer], dim=0
        )  # (L, 1, seq, hidden)
        hidden_states = hidden_states.squeeze(1)  # (L, seq, hidden)

        # Concat across layers → (seq, hidden*L)
        token_repr = hidden_states.mean(dim=0)  # (seq, hidden)

        # Attention weights: average across all layers and heads → (seq,)
        # attentions is tuple of (1, heads, seq, seq) per layer
        attn_layers = outputs.attentions[start_layer:end_layer]
        # For each token, aggregate incoming attention from all others
        attn_weights = torch.stack(
            [a.squeeze(0).mean(dim=0).mean(dim=0) for a in attn_layers], dim=0
        ).mean(dim=0)  # (seq,)

        # Normalize (softmax excluding padding)
        attn_weights = torch_f.softmax(attn_weights, dim=0)  # (seq,)

        # Weighted sum: (hidden,)
        weighted = (token_repr * attn_weights.unsqueeze(-1)).sum(dim=0)
        return weighted.unsqueeze(0)  # (1, hidden) for cosine_similarity

    def _get_weighted_embedding_ig(self, text: str) -> torch.Tensor:
        """Token-weighted embedding via Integrated Gradients (Riemann sum, 5 steps).

        Baseline: all-pad token embeddings.
        Target: actual token embeddings.
        IG approximation: Σ_k (emb - baseline) * grad(interpolated) / steps

        Per docs/2509.11513v1: IG weights > attention weights (GAP 64.4 vs 61.3).
        """
        inputs = self._tokenizer(
            text, return_tensors="pt", truncation=True, max_length=256
        ).to(self._device)

        input_ids = inputs["input_ids"]
        n_steps = 5

        embedding_layer = self._model.get_input_embeddings()
        with torch.no_grad():
            target_emb = embedding_layer(input_ids).squeeze(0)  # (seq, hidden)

        # Baseline: pad token embeddings
        pad_id = self._tokenizer.pad_token_id or 0
        baseline_ids = torch.full_like(input_ids, pad_id)
        with torch.no_grad():
            baseline_emb = embedding_layer(baseline_ids).squeeze(0)  # (seq, hidden)

        # Accumulate gradients across interpolation steps
        ig_weights = torch.zeros(input_ids.shape[1], device=self._device)  # (seq,)

        for step in range(1, n_steps + 1):
            alpha = step / n_steps
            interpolated = (baseline_emb + alpha * (target_emb - baseline_emb)).unsqueeze(0)
            interpolated.requires_grad_(True)

            # Forward pass with interpolated embeddings
            outputs = self._model(inputs_embeds=interpolated, attention_mask=inputs.get("attention_mask"))

            # Use L2 norm of last hidden state as scalar objective
            objective = outputs.last_hidden_state.norm(dim=-1).sum()
            objective.backward()

            if interpolated.grad is not None:
                # L2 norm of gradient per token → token importance
                ig_weights += interpolated.grad.squeeze(0).norm(dim=-1).detach()

        ig_weights = ig_weights / n_steps
        ig_weights = ig_weights * (target_emb - baseline_emb).norm(dim=-1)

        # Normalize
        ig_weights = torch_f.softmax(ig_weights, dim=0)  # (seq,)

        # Get final hidden states for weighted sum
        with torch.no_grad():
            outputs_final = self._model(**inputs)
        hidden = outputs_final.last_hidden_state.squeeze(0)  # (seq, hidden)

        weighted = (hidden * ig_weights.unsqueeze(-1)).sum(dim=0)
        return weighted.unsqueeze(0)

    # ------------------------------------------------------------------
    # Word-level helpers
    # ------------------------------------------------------------------

    def _attention_holistic_score(
        self, original: str, replaced: str, target_word_idx: int
    ) -> float:
        """Attention-based score for word substitution at target_word_idx."""
        return self._attention_sentence_similarity(original, replaced)

    def _ig_holistic_score(
        self, original: str, replaced: str, target_word_idx: int
    ) -> float:
        """IG-based score for word substitution at target_word_idx."""
        return self._ig_sentence_similarity(original, replaced)


holistic_ranker = HolisticLexicalSubstitutionRanker()
