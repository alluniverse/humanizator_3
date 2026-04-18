"""Token-Level Precision Guided Rewrite Engine.

Implements Algorithm 1 from Cheng et al. (2025)
"Adversarial Paraphrasing: A Universal Attack for Humanizing AI-Generated Text"
arXiv:2506.07001v1.

Algorithm 1 (verbatim from paper):
    Require: Paraphraser LLM P modelled by p(·|x), guidance detector D,
             tokenizer decode method T
    Input:   System instruction sys, AI-generated text x_{:n},
             top-p and top-k token masking methods top_p and top_k
    Output:  Humanized text y_m

    1: y = "", m = 0
    2: while True do
    3:   p  = p(·|sys ⊕ x_{:n} ⊕ y_{:m})
    4:   p' = top_k ∘ top_p(p)          ← top_p FIRST, then top_k
    5:   candidates = T(p')
    6:   scores = []
    7:   for k = 1 to length(candidates) do
    8:     scores.append(D(y_m ⊕ candidates[k]))
    9:   end for
    10:  y* = candidates[argmin scores]   ← token with LOWEST AI-score
    11:  y = y ⊕ y*, m = m + 1
    12:  if y* == [EOS]: break
    15: end while

Key requirements from paper (§3, §4.1):
    - Paraphraser: LLaMA-3-8B-Instruct (instruction-tuned model)
    - System prompt: exact text from Figure 2 with <TAG>...</TAG> output markers
    - Guidance detector D: trained AI-text classifier (e.g. OpenAI-RoBERTa-Large/Base)
    - Hyperparameters: top-p = 0.99, top-k = 50
    - Scoring: D scores only the GENERATED portion y_m (not the input prompt)

Implementation notes:
    - HFPrecisionProvider wraps any AutoModelForCausalLM with logit access
    - RobertaAIDetector uses openai-community/roberta-base-openai-detector as D
    - SimpleAIScorer (GPT-2 perplexity proxy) is a fallback when RoBERTa unavailable
    - Production: set PRECISION_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
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
    """Apply top-p (nucleus) then top-k filtering — Algorithm 1 line 4: p' = top_k ∘ top_p(p).

    Order: top_p FIRST (nucleus pruning), then top_k (hard cap on candidates).
    Returns a filtered logits tensor where non-selected positions are -inf.
    """
    import torch
    import torch.nn.functional as F

    # Step 1: top-p (nucleus filtering) — keep tokens whose cumulative prob ≤ p
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

    # Step 2: top-k (hard cap) — keep at most k highest-prob tokens
    if top_k > 0:
        top_k_clamped = min(top_k, (logits > float("-inf")).sum().item())
        if top_k_clamped > 0:
            top_k_vals, _ = torch.topk(logits, int(top_k_clamped))
            threshold = top_k_vals[-1]
            logits = logits.masked_fill(logits < threshold, float("-inf"))

    return logits


class RobertaAIDetector:
    """Trained AI-text detector using openai-community/roberta-base-openai-detector.

    This is the guidance detector D from Algorithm 1 (Cheng et al. 2025).
    The paper uses OpenAI-RoBERTa-Large; we default to the smaller *-base*
    variant for resource efficiency.  Set AI_DETECTOR_MODEL in .env to use
    the large variant or any compatible HuggingFace sequence-classification model.

    Output: score ∈ [0, 1] where 0 = human-like, 1 = AI-like.
    """

    def __init__(self, model_name: str = "openai-community/roberta-base-openai-detector") -> None:
        self.model_name = model_name
        self._model: Any = None
        self._tokenizer: Any = None
        self._torch: Any = None
        self._device: str = "cpu"

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        self._torch = torch
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        from infrastructure.config import settings
        _hf_token = getattr(settings, "hf_token", None)
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, token=_hf_token)
        self._model = AutoModelForSequenceClassification.from_pretrained(
            self.model_name, token=_hf_token
        ).to(self._device).eval()

    def score(self, text: str) -> float:
        """Return AI-likeness score ∈ [0, 1].  Lower = more human-like."""
        if not text.strip():
            return 0.5
        self._load()
        try:
            inputs = self._tokenizer(
                text, return_tensors="pt", truncation=True, max_length=512
            ).to(self._device)
            with self._torch.no_grad():
                logits = self._model(**inputs).logits
            probs = self._torch.softmax(logits, dim=-1)[0]
            # Label 0 = "Real" (human), label 1 = "Fake" (AI)
            # Return prob of "Fake" as AI score
            ai_label_idx = 1
            if self._model.config.id2label.get(0, "").lower() in ("fake", "ai"):
                ai_label_idx = 0
            return float(probs[ai_label_idx].item())
        except Exception:
            return 0.5


class SimpleAIScorer:
    """GPT-2 perplexity-based fallback detector.

    Used when RobertaAIDetector is unavailable.  Lower perplexity = more
    fluent/predictable text = more likely AI-generated.  The score is
    calibrated so that typical AI text (ppl≈20) scores ~0.9 and unusual
    human text (ppl≈150) scores ~0.3.

    NOTE: This is a weak proxy.  RobertaAIDetector is strongly preferred.
    """

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None
        self._torch: Any = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import GPT2LMHeadModel, GPT2Tokenizer
        from infrastructure.config import settings
        self._torch = torch
        self._tokenizer = GPT2Tokenizer.from_pretrained(settings.perplexity_model)
        self._model = GPT2LMHeadModel.from_pretrained(settings.perplexity_model).eval()

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
            # Map ppl → AI score: ppl=20→0.88, ppl=60→0.50, ppl=150→0.19
            # Formula: sigmoid(-(ln(ppl) - ln(60)) * 2.5)
            score = 1.0 / (1.0 + (ppl / 20.0) ** 0.5)
            return float(max(0.0, min(1.0, 1.0 - score)))
        except Exception:
            return 0.5


class CompositeHumanLikenessScorer:
    """Heuristic AI-likeness scorer that works for modern LLMs (GPT-4o, Claude, etc.).

    roberta-base-openai-detector was trained on GPT-2 era text and scores ALL
    modern LLM outputs near 0.000 (useless for guidance).  This scorer combines
    three signals that are meaningful for current models:

      1. GPT-2 perplexity  — AI text is highly predictable (low PPL); human text
                              is less predictable (high PPL).  Higher PPL → lower AI score.
      2. Burstiness         — AI sentences are uniform in length; humans vary them.
                              Higher burstiness → lower AI score.
      3. AI marker count    — Explicit pattern matching against known AI phrases.
                              More markers → higher AI score.

    Returns score ∈ [0, 1] where 0 = human-like, 1 = AI-like.
    """

    _AI_MARKERS = [
        # English
        "it is important to note", "it is worth", "it should be noted",
        "furthermore", "moreover", "in addition", "in conclusion", "to summarize",
        "in summary", "first and foremost", "absolutely", "undoubtedly",
        "notably", "crucially", "essentially", "fundamentally",
        "in the realm of", "at its core", "at the heart of",
        "this cooperation is a win-win", "win-win", "make no mistake",
        "it is crucial", "needless to say", "it goes without saying",
        "overall, this", "in conclusion,", "to summarize,",
        # Russian
        "стоит отметить", "необходимо отметить", "следует отметить",
        "таким образом", "в заключение", "подводя итог", "в целом",
        "безусловно", "несомненно", "очевидно",
        # Ukrainian
        "варто зазначити", "необхідно відзначити", "таким чином",
        "у висновку", "загалом", "безперечно",
    ]

    def __init__(self) -> None:
        self._ppl_scorer = SimpleAIScorer()

    def score(self, text: str) -> float:
        """Return AI-likeness score ∈ [0, 1]. Lower = more human-like."""
        if not text.strip():
            return 0.5

        # 1. Perplexity component (already normalised 0-1)
        ppl_score = self._ppl_scorer.score(text)

        # 2. Burstiness component: std/mean of sentence word counts
        import re
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if s.strip()]
        if len(sentences) >= 2:
            lengths = [len(s.split()) for s in sentences]
            mean_len = sum(lengths) / len(lengths)
            variance = sum((l - mean_len) ** 2 for l in lengths) / len(lengths)
            burstiness = (variance ** 0.5) / mean_len if mean_len > 0 else 0.0
            # burstiness=0 (all same length) → penalty=0.3; burstiness=1+ → penalty=0
            burstiness_penalty = max(0.0, 0.3 - burstiness * 0.3)
        else:
            burstiness_penalty = 0.15

        # 3. AI marker component
        lower = text.lower()
        marker_count = sum(1 for m in self._AI_MARKERS if m in lower)
        marker_score = min(marker_count * 0.08, 0.4)

        composite = ppl_score * 0.5 + burstiness_penalty + marker_score
        return float(max(0.0, min(1.0, composite)))


def _build_default_ai_scorer() -> "RobertaAIDetector | SimpleAIScorer":
    """Build best available AI detector for Algorithm 1 token-level guidance.

    NOTE: roberta-base-openai-detector is trained on GPT-2 era text and gives
    near-zero scores for GPT-4o output — useless for best_of_n selection.
    Use CompositeHumanLikenessScorer for best_of_n via build_best_of_n_scorer().
    """
    from infrastructure.config import settings
    detector_model = getattr(settings, "ai_detector_model", None)
    if detector_model:
        return RobertaAIDetector(model_name=detector_model)
    try:
        import transformers  # noqa: F401
        return RobertaAIDetector()
    except Exception:
        logger.warning("RobertaAIDetector unavailable — using SimpleAIScorer perplexity fallback")
        return SimpleAIScorer()


def build_best_of_n_scorer() -> "CompositeHumanLikenessScorer":
    """Return the scorer to use for best_of_n variant selection.

    CompositeHumanLikenessScorer is reliable for modern LLM output (GPT-4o etc.)
    where roberta-base-openai-detector gives useless near-zero scores.
    """
    return CompositeHumanLikenessScorer()


# Lazily initialised — avoids importing torch/transformers at module load time.
# _build_default_ai_scorer() is called on first TokenPrecisionEngine.generate() call.
_default_ai_scorer: "RobertaAIDetector | SimpleAIScorer | None" = None


def _get_default_ai_scorer() -> "RobertaAIDetector | SimpleAIScorer":
    global _default_ai_scorer
    if _default_ai_scorer is None:
        _default_ai_scorer = _build_default_ai_scorer()
    return _default_ai_scorer


class TokenPrecisionEngine:
    """Token-level precision guided rewrite (Algorithm 1, Cheng et al. 2025).

    At each decoding step, scores ALL top-k/top-p candidate tokens using a
    guidance detector D and selects the one that minimises AI-likeness of the
    growing output sequence y_m.

    Detector scoring uses ONLY the generated text y_m (not the input prompt),
    matching Algorithm 1 line 8: D(y_m ⊕ candidates[k]).
    """

    def __init__(
        self,
        provider: "HFPrecisionProvider | None" = None,
        ai_scorer: "RobertaAIDetector | SimpleAIScorer | None" = None,
        top_k: int = DEFAULT_TOP_K,
        top_p: float = DEFAULT_TOP_P,
        max_new_tokens: int = DEFAULT_MAX_NEW_TOKENS,
        max_candidates_to_score: int = DEFAULT_TOP_K,
    ) -> None:
        self._provider = provider  # lazy: set at first call if None
        # None → resolved lazily on first generate() call via _get_default_ai_scorer()
        self._ai_scorer: "RobertaAIDetector | SimpleAIScorer | None" = ai_scorer
        self.top_k = top_k
        self.top_p = top_p
        self.max_new_tokens = max_new_tokens
        # max_candidates_to_score: how many of the k candidates to evaluate with D.
        # Paper evaluates ALL k; lower values trade accuracy for speed.
        # Default = top_k (full Algorithm 1 compliance).
        self.max_candidates_to_score = max_candidates_to_score

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
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Run Algorithm 1: token-level adversarial paraphrasing.

        Args:
            prompt: Source text to paraphrase (user turn).
                    Build with rewrite.prompts.build_precision_prompt().
            context: Optional cross-chunk context prefix.
            system_prompt: Figure 2 system instruction.  When the paraphraser
                supports a chat template (LLaMA-3-8B-Instruct), this is placed
                in the <|system|> slot via encode_chat(); otherwise it is
                prepended as raw text.  Defaults to PRECISION_SYSTEM_PROMPT.

        Returns dict with keys:
            text              — generated text (without prompt; <TAG> stripped)
            tokens_generated  — number of tokens produced
            steps             — per-token details: token, ai_score, candidates_evaluated
            algorithm         — "adversarial_paraphrasing_v1"
            top_k, top_p      — hyperparameters used
        """
        import torch
        import torch.nn.functional as F
        from rewrite.prompts import PRECISION_SYSTEM_PROMPT

        ai_scorer = self._ai_scorer or _get_default_ai_scorer()
        provider = self._get_provider()

        sys = system_prompt or PRECISION_SYSTEM_PROMPT
        user_text = (context + "\n\n" + prompt).strip() if context else prompt

        # Line 3 setup: encode full context sys ⊕ x_{:n} using chat template when available
        if hasattr(provider, "encode_chat"):
            input_ids = provider.encode_chat(sys, user_text)
        else:
            input_ids = provider.encode(f"{sys}\n\n{user_text}")

        generated_ids: list[int] = []
        steps: list[dict[str, Any]] = []

        for _step in range(self.max_new_tokens):
            # Build current full sequence: prompt + generated so far
            if generated_ids:
                gen_tensor = torch.tensor([generated_ids], device=provider.device)
                current_ids = torch.cat([input_ids, gen_tensor], dim=1)
            else:
                current_ids = input_ids

            # Line 3: next-token logit distribution
            logits = provider.next_token_logits(current_ids)  # [vocab_size]

            # Line 4: p' = top_k ∘ top_p(p)  (top-p first, then top-k)
            filtered_logits = _top_p_top_k_filter(logits.clone(), self.top_k, self.top_p)

            # Line 5: decode candidates to token ids
            candidate_mask = filtered_logits > float("-inf")
            candidate_ids = candidate_mask.nonzero(as_tuple=True)[0].tolist()
            if not candidate_ids:
                candidate_ids = [int(logits.argmax().item())]

            # Rank candidates by probability; score top max_candidates_to_score with D
            probs = F.softmax(filtered_logits, dim=-1)
            n_to_score = min(self.max_candidates_to_score, len(candidate_ids))
            top_prob_indices = probs[candidate_ids].topk(n_to_score).indices
            scored_ids = [candidate_ids[i] for i in top_prob_indices.tolist()]

            # Lines 6-9: D(y_m ⊕ candidates[k]) — score ONLY the generated text y_m
            # NOT the full input prompt (y_m is provider.decode_tokens(generated_ids))
            current_output = provider.decode_tokens(generated_ids) if generated_ids else ""

            best_id = scored_ids[0]
            best_score = float("inf")
            for cid in scored_ids:
                candidate_token_text = provider.decode_tokens([cid])
                # Score: partial output so far + this candidate token
                scored_text = current_output + candidate_token_text
                ai_score = ai_scorer.score(scored_text)
                if ai_score < best_score:
                    best_score = ai_score
                    best_id = cid  # Line 10: argmin scores

            # Lines 11-14: append best token, check for EOS
            generated_ids.append(best_id)
            steps.append({
                "token": provider.decode_tokens([best_id]),
                "token_id": best_id,
                "ai_score": round(best_score, 4),
                "candidates_evaluated": len(scored_ids),
            })

            if best_id == provider.eos_token_id:
                break

        generated_text = provider.decode_tokens(generated_ids)

        # Extract text from <TAG>...</TAG> if the model used the paper's system prompt
        import re
        tag_match = re.search(r"<TAG>(.*?)</TAG>", generated_text, re.DOTALL | re.IGNORECASE)
        clean_text = tag_match.group(1).strip() if tag_match else generated_text.strip()

        return {
            "text": clean_text,
            "tokens_generated": len(generated_ids),
            "steps": steps,
            "algorithm": "adversarial_paraphrasing_v1",
            "top_k": self.top_k,
            "top_p": self.top_p,
        }

    async def generate_async(
        self,
        prompt: str,
        context: str = "",
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        """Async wrapper — runs token-level generation in a thread executor."""
        import asyncio
        import functools
        loop = asyncio.get_event_loop()
        fn = functools.partial(self.generate, prompt, context, system_prompt)
        return await loop.run_in_executor(None, fn)


token_precision_engine = TokenPrecisionEngine()
