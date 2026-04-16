"""Evaluation Engine: absolute metrics, judge evaluation, pairwise comparison."""

from __future__ import annotations

import math
from typing import Any

import spacy
import torch
from bert_score import score as bert_score
from transformers import GPT2LMHeadModel, GPT2Tokenizer

from adapters.llm import OpenAIProvider
from infrastructure.config import settings


class EvaluationEngine:
    """Computes multi-layer evaluation metrics for rewrite variants."""

    def __init__(self) -> None:
        self._nlp_en = spacy.load("en_core_web_sm")
        self._nlp_ru = spacy.load("ru_core_news_sm")
        self._tokenizer = GPT2Tokenizer.from_pretrained(settings.perplexity_model)
        self._ppl_model = GPT2LMHeadModel.from_pretrained(settings.perplexity_model)
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._ppl_model = self._ppl_model.to(device).eval()
        self._device = device
        self._llm = OpenAIProvider()

    def _get_nlp(self, language: str) -> spacy.Language:
        return self._nlp_ru if language == "ru" else self._nlp_en

    def absolute_metrics(
        self,
        original: str,
        variant: str,
        language: str = "ru",
    ) -> dict[str, Any]:
        """Compute absolute metrics: semantic, style, readability, perplexity, burstiness."""
        nlp = self._get_nlp(language)
        doc_orig = nlp(original)
        doc_var = nlp(variant)

        # BERTScore
        try:
            P, R, F1 = bert_score([variant], [original], lang=language, verbose=False, device=self._device)
            bertscore_f1 = F1.item()
        except Exception:
            bertscore_f1 = 0.0

        # Perplexity
        ppl = self._compute_perplexity(variant)

        # Burstiness
        sent_lengths = [len(sent) for sent in doc_var.sents]
        mean_sent = sum(sent_lengths) / len(sent_lengths) if sent_lengths else 0.0
        var_sent = (
            sum((x - mean_sent) ** 2 for x in sent_lengths) / len(sent_lengths)
            if sent_lengths
            else 0.0
        )
        burstiness = (var_sent ** 0.5) / mean_sent if mean_sent > 0 else 0.0

        # Readability proxy (avg sentence length)
        readability = mean_sent

        # Lexical diversity
        words = [t.text.lower() for t in doc_var if not t.is_space and not t.is_punct]
        ttr = len(set(words)) / len(words) if words else 0.0

        # Repetition / cliché
        clichés = ["in conclusion", "moreover", "it is important to note", "furthermore"]
        cliché_count = sum(1 for c in clichés if c in variant.lower())

        return {
            "bertscore_f1": round(bertscore_f1, 3),
            "perplexity": round(ppl, 2),
            "burstiness": round(burstiness, 3),
            "readability": round(readability, 1),
            "lexical_diversity_ttr": round(ttr, 3),
            "cliché_count": cliché_count,
        }

    async def judge_evaluation(
        self,
        original: str,
        variant: str,
        style_profile: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """LLM-as-judge Likert-scale evaluation."""
        prompt = f"""You are an expert editor. Evaluate the rewritten text against the original on a 1-5 Likert scale for:
1. Semantic equivalence (5 = identical meaning, 1 = unrelated)
2. Style appropriateness (5 = perfectly matches target style, 1 = completely mismatched)
3. Fluency and naturalness (5 = perfectly natural, 1 = unreadable)

Original:
{original}

Rewritten:
{variant}

Respond ONLY in JSON format:
{{"semantic_score": int, "style_score": int, "fluency_score": int, "overall_comment": str}}
"""
        try:
            response = await self._llm.generate(prompt, temperature=0.2, max_tokens=256)
            import json

            result = json.loads(response["text"])
        except Exception:
            result = {
                "semantic_score": 3,
                "style_score": 3,
                "fluency_score": 3,
                "overall_comment": "Judge evaluation failed.",
            }
        return result

    async def pairwise_comparison(
        self,
        variant_a: str,
        variant_b: str,
        original: str,
    ) -> dict[str, Any]:
        """Ask LLM judge to pick the better variant."""
        prompt = f"""You are an expert editor. Compare Variant A and Variant B against the Original. Choose the better variant considering meaning preservation, style, and fluency. Respond ONLY with "A", "B", or "tie", followed by a one-sentence reason.

Original:
{original}

Variant A:
{variant_a}

Variant B:
{variant_b}
"""
        try:
            response = await self._llm.generate(prompt, temperature=0.2, max_tokens=128)
            text = response["text"].strip()
            winner = "tie"
            if text.startswith("A"):
                winner = "A"
            elif text.startswith("B"):
                winner = "B"
            reason = text.split("\n")[0]
        except Exception:
            winner = "tie"
            reason = "Comparison failed."
        return {"winner": winner, "reason": reason}

    def _compute_perplexity(self, text: str) -> float:
        inputs = self._tokenizer(text, return_tensors="pt").to(self._device)
        with torch.no_grad():
            outputs = self._ppl_model(inputs["input_ids"], labels=inputs["input_ids"])
            return torch.exp(outputs.loss).item()


evaluation_engine = EvaluationEngine()
