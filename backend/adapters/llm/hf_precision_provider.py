"""HuggingFace LLM provider with token-level logit access.

Required for T5.4 Token-level Precision Guided mode (Algorithm 1 from
Cheng et al. 2025, arXiv:2506.07001).  Standard API providers (OpenAI,
Anthropic) do not expose per-token logit distributions; this provider
runs a local HuggingFace causal LM that does.

Usage:
    provider = HFPrecisionProvider(model_name="gpt2")  # or any CausalLM
    # For token-level precision you typically use TokenPrecisionEngine,
    # not this provider directly.

Graceful fallback:
    When torch or transformers are unavailable the provider raises
    ImportError at instantiation time with a clear message.
"""

from __future__ import annotations

from typing import Any

from adapters.llm.base import LLMProvider


class HFPrecisionProvider(LLMProvider):
    """Local HuggingFace causal-LM provider with next-token logit access.

    Attributes:
        model_name: Any AutoModelForCausalLM compatible checkpoint.
        device: 'cuda' or 'cpu' (auto-detected if None).
        top_k: Number of top token candidates to return from `next_token_logits`.
        top_p: Nucleus probability threshold (for filtering in token-level engine).
    """

    def __init__(
        self,
        model_name: str = "gpt2",
        device: str | None = None,
        top_k: int = 50,
        top_p: float = 0.99,
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise ImportError(
                "HFPrecisionProvider requires torch and transformers. "
                "Install with: pip install torch transformers"
            ) from exc

        import torch as _torch

        self._torch = _torch
        self.model_name = model_name
        self.top_k = top_k
        self.top_p = top_p

        if device is None:
            device = "cuda" if _torch.cuda.is_available() else "cpu"
        self.device = device

        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForCausalLM.from_pretrained(
            model_name, torch_dtype=_torch.float16 if "cuda" in device else _torch.float32
        ).to(device).eval()

        if self._tokenizer.pad_token is None:
            self._tokenizer.pad_token = self._tokenizer.eos_token

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate text via standard greedy/sampling decoding (no logit access)."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._generate_sync, prompt, temperature, max_tokens)

    async def generate_multiple(
        self,
        prompt: str,
        n: int = 3,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 512,
        **kwargs: Any,
    ) -> list[dict[str, Any]]:
        return [await self.generate(prompt, temperature=temperature, max_tokens=max_tokens) for _ in range(n)]

    def _generate_sync(self, prompt: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        torch = self._torch
        inputs = self._tokenizer(prompt, return_tensors="pt").to(self.device)
        with torch.no_grad():
            output_ids = self._model.generate(
                **inputs,
                max_new_tokens=max_tokens,
                temperature=temperature if temperature > 0 else 1.0,
                do_sample=temperature > 0,
                pad_token_id=self._tokenizer.pad_token_id,
            )
        # Decode only the generated tokens (strip prompt)
        prompt_len = inputs["input_ids"].shape[1]
        generated = output_ids[0][prompt_len:]
        text = self._tokenizer.decode(generated, skip_special_tokens=True)
        return {
            "text": text,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": prompt_len,
                "completion_tokens": len(generated),
                "total_tokens": prompt_len + len(generated),
            },
            "model": self.model_name,
        }

    # ------------------------------------------------------------------
    # Token-level logit access (unique to this provider)
    # ------------------------------------------------------------------

    def next_token_logits(
        self,
        input_ids: "Any",
    ) -> "Any":
        """Return raw logits for the next token position.

        Args:
            input_ids: torch.LongTensor of shape [1, seq_len].

        Returns:
            logits: torch.FloatTensor of shape [vocab_size].
        """
        with self._torch.no_grad():
            outputs = self._model(input_ids=input_ids)
        return outputs.logits[0, -1, :]  # [vocab_size]

    def decode_tokens(self, token_ids: list[int]) -> str:
        """Decode a list of token ids to a string."""
        return self._tokenizer.decode(token_ids, skip_special_tokens=True)

    def encode(self, text: str) -> "Any":
        """Encode text to input_ids tensor on the provider's device."""
        return self._tokenizer(text, return_tensors="pt").input_ids.to(self.device)

    @property
    def has_chat_template(self) -> bool:
        """True if the tokenizer has a chat template (e.g. LLaMA-3-8B-Instruct)."""
        return bool(getattr(self._tokenizer, "chat_template", None))

    def encode_chat(self, system: str, user: str) -> "Any":
        """Encode sys+user pair using the tokenizer's chat template.

        Uses apply_chat_template when available (instruction-tuned models like
        LLaMA-3-8B-Instruct).  Falls back to raw concatenation for models without
        a chat template (gpt2, raw base models).

        This is required by Algorithm 1 (Cheng et al. 2025): the Figure 2 system
        prompt must be placed in the <|system|> slot so the instruction-tuned
        paraphraser honours it correctly.
        """
        if self.has_chat_template:
            messages = [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ]
            text = self._tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        else:
            text = f"{system}\n\n{user}"
        return self._tokenizer(text, return_tensors="pt").input_ids.to(self.device)

    @property
    def eos_token_id(self) -> int:
        return self._tokenizer.eos_token_id or 0

    @property
    def vocab_size(self) -> int:
        return self._tokenizer.vocab_size
