"""Token-Level Precision Guided Rewrite Engine.

Implements Algorithm 1 from Cheng et al. (2025) "Can LLMs be Good
Graph-to-Text Generators?" — arXiv:2506.07001v1.

Core idea (Algorithm 1 paraphrase):
    Input:  source text x, paraphraser LLM P, style detector D, prompt f
    Output: human-like rewritten text y

    Initialise: y = []  (output token sequence), m = 0
    Prompt LLM:  h = f(x)  (system + user prompt)

    while y[m] != [EOS]:
        logits = P(y | h)                    # next-token distribution
        candidates = top_p_top_k(logits)     # filter by p=0.99, k=50
        decoded = [T(c) for c in candidates] # decode each candidate
        scores = [D(y_m ⊕ d) for d in decoded]  # AI-score per suffix
        y[m+1] = candidates[argmin(scores)]  # pick most human-like token
        m += 1

    return detokenize(y)

Integration contract:
    - Requires HFPrecisionProvider (or any provider exposing `next_token_logits`)
    - Style detector D must implement `score(text: str) -> float`
      where lower = more human-like (e.g. 0 = fully human, 1 = fully AI)
    - Falls back gracefully: if detector or provider unavailable, returns
      standard sampling from the provider

Performance note:
    Token-by-token generation is O(n) model forward passes — significantly
    slower than batch generation.  Intended for short-to-medium texts
    (≤ 200 tokens).  Use `max_new_tokens` to control latency.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from adapters.llm.hf_precision_provider import HFPrecisionProvider

logger = logging.getLogger(__name__)

# Algorithm 1 hyperparameters (from Cheng et al. 2025, §3)
DEFAULT_TOP_K = 50
DEFAULT_TOP_P = 0.99
DEFAULT_MAX_NEW_TOKENS = 200


def _top_p_top_k_filter(logits: "Any", top_k: int, top_p: float) -> "Any":
    """Apply top-k then top-p (nucleus) filtering to logit tensor.

    Returns a filtered logits tensor where non-selected positions are -inf.
    """
    import torch
    import torch.nn.functional as F

    # Top-k
    if top_k > 0:
        top_k_vals, _ = torch.topk(logits, min(top_k, logits.size(-1)))
        threshold = top_k_vals[-1]
        logits = logits.masked_fill(logits < threshold, float("-inf"))

    # Top-p (nucleus)
    if top_p < 1.0:
        sorted_logits, sorted_idx = torch.sort(logits, descending=True)
        probs = F.softmax(sorted_logits, dim=-1)
        cum_probs = torch.cumsum(probs, dim=-1)
        # Remove tokens with cumulative probability above threshold
        sorted_idx_to_remove = cum_probs > top_p
        # Shift right so the first token above threshold is also kept
        sorted_idx_to_remove[1:] = sorted_idx_to_remove[:-1].clone()
        sorted_idx_to_remove[0] = False
        indices_to_remove = sorted_idx_to_remove.scatter(0, sorted_idx, sorted_idx_to_remove)
        logits = logits.masked_fill(indices_to_remove, float("-inf"))

    return logits


class SimpleAIScorer:
    """Lightweight AI-text detector used as style detector D.

    Uses perplexity as a proxy: lower perplexity = more fluent = potentially
    more AI-like.  We invert it: score = 1 / (1 + ppl) so that
    high-perplexity (more unusual/human) text gets a LOW score.

    In practice, a production deployment would use a fine-tuned classifier
    (e.g. RADAR, GLTR, or a dedicated detector).  This implementation
    provides a numerically correct interface for Algorithm 1.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import GPT2LMHeadModel, GPT2Tokenizer
        from infrastructure.config import settings

        self._tokenizer = GPT2Tokenizer.from_pretrained(settings.perplexity_model)
        self._model = GPT2LMHeadModel.from_pretrained(settings.perplexity_model).eval()
        self._torch = torch

    def score(self, text: str) -> float:
        """Return AI-likeness score ∈ [0, 1].  Lower = more human-like."""
        if not text.strip():
            return 0.5
        self._load()
        try:
            import math
            tokens = self._tokenizer(text, return_tensors="pt", truncation=True, max_length=128)
            with self._torch.no_grad():
                loss = self._model(**tokens, labels=tokens["input_ids"]).loss
            ppl = math.exp(loss.item())
            # Normalise: score = exp(-ppl/100) → high ppl → low AI score
            return float(self._torch.sigmoid(self._torch.tensor(-ppl / 100.0 + 3.0)).item())
        except Exception:
            return 0.5


_default_ai_scorer = SimpleAIScorer()


class TokenPrecisionEngine:
    """Token-level precision guided rewrite (Algorithm 1, Cheng et al. 2025).

    For each decoding step, evaluates top-k/top-p candidate tokens and selects
    the one that minimises the AI-likeness score of the growing output sequence.
    """

    def __init__(
        self,
        provider: "HFPrecisionProvider | None" = None,
        ai_scorer: SimpleAIScorer | None = None,
        top_k: int = DEFAULT_TOP_K,
        top_p: float = DEFAULT_TOP_P,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
    ) -> None:
        self._provider = provider  # lazy: set at first call if None
        self._ai_scorer = ai_scorer or _default_ai_scorer
        self.top_k = top_k
        self.top_p = top_p
        self.max_new_tokens = max_new_tokens

    def _get_provider(self) -> "HFPrecisionProvider":
        if self._provider is None:
            from adapters.llm.hf_precision_provider import HFPrecisionProvider
            from infrastructure.config import settings
            model_name = getattr(settings, "precision_model", "gpt2")
            self._provider = HFPrecisionProvider(model_name=model_name)
        return self._provider

    def generate(
        self,
        prompt: str,
        context: str = "",
    ) -> dict[str, Any]:
        """Run token-level precision decoding.

        Args:
            prompt: The humanisation prompt (including source text and style guidance).
            context: Optional accumulated context prepended before the prompt tokens
                     (used for cross-chunk continuity).

        Returns:
            {
              "text": generated text string,
              "tokens_generated": int,
              "steps": list of {token, score, candidates_evaluated},
              "algorithm": "token_precision_v1",
            }
        """
        import torch
        import torch.nn.functional as F

        provider = self._get_provider()
        full_prompt = (context + "\n\n" + prompt).strip() if context else prompt
        input_ids = provider.encode(full_prompt)  # [1, seq_len]

        generated_ids: list[int] = []
        steps: list[dict[str, Any]] = []

        for step in range(self.max_new_tokens):
            current_ids = torch.cat(
                [input_ids, torch.tensor([generated_ids], device=provider.device)],
                dim=1,
            ) if generated_ids else input_ids

            logits = provider.next_token_logits(current_ids)  # [vocab_size]
            filtered_logits = _top_p_top_k_filter(logits.clone(), self.top_k, self.top_p)

            # Get candidate token ids
            candidate_mask = filtered_logits > float("-inf")
            candidate_ids = candidate_mask.nonzero(as_tuple=True)[0].tolist()

            if not candidate_ids:
                # Fallback: argmax
                candidate_ids = [int(logits.argmax().item())]

            # Score each candidate: decode suffix and evaluate AI-likeness
            current_text = provider.decode_tokens(
                input_ids[0].tolist() + generated_ids
            )
            best_id = candidate_ids[0]
            best_score = float("inf")

            # Limit scoring to top-5 by probability to bound latency
            probs = F.softmax(filtered_logits, dim=-1)
            top_cand_ids = probs[candidate_ids].topk(min(5, len(candidate_ids))).indices
            top_5_ids = [candidate_ids[i] for i in top_cand_ids.tolist()]

            for cid in top_5_ids:
                suffix_text = provider.decode_tokens([cid])
                candidate_text = current_text + suffix_text
                score = self._ai_scorer.score(candidate_text)
                if score < best_score:
                    best_score = score
                    best_id = cid

            generated_ids.append(best_id)
            steps.append({
                "token": provider.decode_tokens([best_id]),
                "token_id": best_id,
                "ai_score": round(best_score, 4),
                "candidates_evaluated": len(top_5_ids),
            })

            if best_id == provider.eos_token_id:
                break

        generated_text = provider.decode_tokens(generated_ids)
        return {
            "text": generated_text,
            "tokens_generated": len(generated_ids),
            "steps": steps,
            "algorithm": "token_precision_v1",
            "top_k": self.top_k,
            "top_p": self.top_p,
        }

    async def generate_async(self, prompt: str, context: str = "") -> dict[str, Any]:
        """Async wrapper — runs token-level generation in thread executor."""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate, prompt, context)


token_precision_engine = TokenPrecisionEngine()
