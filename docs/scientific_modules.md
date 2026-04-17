# Humanizator 3 — Scientific Module Documentation

This document covers the theoretical foundations and implementation details of the algorithm-heavy modules.  Each section cites the primary paper and describes how the theory maps to code.

---

## 1. Token-Level Precision Guided Rewrite

**Paper**: Cheng et al. (2025). *arXiv:2506.07001v1* — "Adversarial Paraphrasing and Token-Level Guidance"

**File**: `backend/application/services/token_precision.py`  
**Provider**: `backend/adapters/llm/hf_precision_provider.py`

### Algorithm 1 (paper § 3)

```
Input:  source x,  paraphraser LLM P,  style detector D,  prompt builder f
Output: human-like text y

y = []   (output token sequence)
m = 0
h = f(x)  (prompt including source + constraints)

while y[m] ≠ [EOS]:
    logits = P(y_<m | h)               # next-token distribution
    C = top_p_top_k(logits, p=0.99, k=50)   # filter candidates
    decoded = { T(c) for c in C }      # decode each candidate
    scores = { D(y_<m · d) for d in decoded }   # AI-likeness per suffix
    y[m] = argmin_{c ∈ C} scores[c]    # most human-like token
    m += 1

return detokenize(y)
```

### Implementation Notes

- **`_top_p_top_k_filter`**: applies top-k first, then nucleus (top-p) filtering.  Candidates at positions where `filtered_logits = -inf` are excluded.
- **Scoring**: to bound latency, only the top-5 candidates by softmax probability are scored per step (not the full top-50 set).
- **AI scorer (`SimpleAIScorer`)**: uses GPT-2 perplexity as a proxy for AI-likeness. Score = σ(−ppl/100 + 3); lower = more human-like. A production deployment would replace this with a dedicated detector (RADAR, GLTR, or fine-tuned classifier).
- **Fallback**: if the HuggingFace provider is unavailable (no local model), `GuidedRewriteEngine._rewrite_precision` catches the exception and falls back to standard `balanced` mode.
- **`precision_model` setting**: configurable via `PRECISION_MODEL` env variable (default: `gpt2`); in production set to a larger instruction-tuned model.

---

## 2. Corpus Quality Tiering

**Paper**: Masrour et al. (2025). *arXiv:2501.03437v1* — "Corpus Quality Assessment"

**File**: `backend/application/services/quality_tiering.py`

### Tier Definitions

| Tier | Criteria | Use |
|------|----------|-----|
| L1 | ≥ 500 words, ≥ 5 unique paragraphs, no repeated paragraphs | High-quality reference corpus |
| L2 | ≥ 50 words, ≥ 2 sentences, not flagged as short fragment | Acceptable for style training |
| L3 | < 50 words OR < 2 sentences OR very short (< 15 words) | Filtered out or low-weight |

### Implementation: `_detect_l3` → `_detect_l2` → else L1

```python
def tier_sample(text: str) -> QualityTier:
    if _detect_l3(text):   return QualityTier.L3
    if not _detect_l2(text): return QualityTier.L1
    return QualityTier.L2
```

- **L3 detection**: `len(sentences) < 2 AND len(words) < 15`
- **L2 detection**: `len(words) < 50 OR len(sentences) < 2 OR not_paragraph_structured`
- **`diagnose_library`**: returns per-tier counts, dominant tier, and actionable recommendation

---

## 3. Holistic Lexical Substitution Ranker

**Paper**: Referenced in project spec — Holistic Score formulation

**File**: `backend/application/services/holistic_ranker.py`

### Scoring Formula

```
Score(s, s') = Σᵢ wᵢ · cos(f(xᵢ), f(x'ᵢ))
```

Where:
- `s` = original sentence, `s'` = candidate substitution
- `f(xᵢ)` = contextual embedding of token i
- `wᵢ` = token importance weight

**Two scoring modes**:

| Mode | Weight computation | Speed |
|------|--------------------|-------|
| `fast` | Attention weights from transformer | ~10ms/sentence |
| `precision` | Integrated Gradients (5-step Riemann sum) | ~100ms/sentence |

### Integrated Gradients (precision mode)

```
IG(xᵢ) = (xᵢ − x̄ᵢ) · ∫₀¹ ∂F(x̄ + α(x−x̄))/∂xᵢ dα
       ≈ (xᵢ − x̄ᵢ) · Σₖ₌₁⁵ ∂F(x̄ + (k/5)(x−x̄))/∂xᵢ · (1/5)
```

Approximated with 5 interpolation points along the straight-line path from baseline (zero embedding) to the actual input embedding.

---

## 4. Adversarial Paraphrasing Robustness

**Paper**: Cheng et al. (2025). *arXiv:2506.07001v1* — Figure 2, system prompt

**File**: `backend/application/services/adversarial_robustness.py`

### Attack Suite

Five attack types are applied independently to the rewritten text:

| Attack | Method | Rationale |
|--------|--------|-----------|
| `char_substitution` | Replace Latin chars with visually identical Cyrillic (homoglyphs) | Tests OCR/normalisation robustness |
| `word_deletion` | Drop 10% of non-stopword tokens (seeded random) | Tests completeness under partial input |
| `sentence_shuffle` | Random reorder of sentence boundaries | Tests coherence-encoding stability |
| `tag_injection` | Wrap capitalised multi-word sequences in `<TAG>...</TAG>` | From Cheng et al. 2025 Fig. 2 |
| `negation_flip` | Insert NOT after first auxiliary/modal | Tests semantic encoding stability |

### Robustness Score

For each attack, cosine similarity between the original rewrite embedding and the perturbed embedding is computed.  Mean similarity ≥ `semantic_threshold` (default 0.75) AND no individual attack drops below threshold → `passed=True`.

A robust text's embedding is not easily displaced by surface-level edits.

---

## 5. Hallucination Detection

**File**: `backend/application/services/hallucination_detector.py`

### Four-layer Detection

| Check | Method | Weight |
|-------|--------|--------|
| `entity_drift` | Verify protected_entities, protected_numbers, key_terms appear in rewrite | 0.35 |
| `semantic_drift` | Cosine similarity between sentence embeddings ≥ threshold | 0.35 |
| `structural` | Detect truncation markers, repeated 5-grams (≥3×), short output (<10 words) | 0.20 |
| `length` | Rewrite word count / original word count ∈ [0.5, 2.0] | 0.10 |

**Composite score** = weighted sum of passed checks.

**`passed` flag** = `entity_drift.passed AND semantic_drift.passed` (the two critical checks).

Entity drift uses the semantic contract if provided; without a contract the check always passes.

---

## 6. Style Conflict Detection

**File**: `backend/application/services/style_conflict_detector.py`

### Stylometric Features (4 dimensions)

| Feature | Formula | Interpretation |
|---------|---------|----------------|
| `avg_sent_len` | mean word count per sentence | formality / complexity proxy |
| `burstiness` | σ(sent_lengths) / μ(sent_lengths) | sentence length variation |
| `ttr` | unique_words / total_words | lexical richness |
| `formality` | noun+adj+prep count / total tokens | syntactic formality |

### Outlier Detection

For each sample `i` and dimension `d`:
```
z_{i,d} = (x_{i,d} − μ_d) / σ_d
```

A sample is flagged as an outlier if it has `z ≥ outlier_threshold` (default 2.0) in ≥ 2 dimensions simultaneously.

Library profile = per-dimension mean ± std across all samples.

Minimum 3 samples required; with fewer, the check returns no conflicts and a warning.

---

## 7. Rewrite Constraint Layer

**File**: `backend/constraints/rewrite_constraints.py`

### Three constraint types

1. **POS constraints**: noun/verb/adjective counts in rewrite must not deviate more than ±40% from original (configurable MPR — Maximum Permissible Ratio).

2. **Protected spans**: all entities identified in the semantic contract must appear verbatim in the rewrite output.

3. **USE similarity**: Universal Sentence Encoder (via sentence-transformers) cosine similarity between original and rewrite ≥ 0.75 (configurable).

### Validation result

```json
{
  "passed": true,
  "checks": {
    "pos": {"passed": true, "deviations": {}},
    "protected_spans": {"passed": true, "missing": []},
    "semantic": {"passed": true, "similarity": 0.91}
  }
}
```

---

## 8. Semantic Contract

**File**: `backend/application/services/semantic_contract.py`

Three extraction modes driven by `SemanticContractMode` enum:

| Mode | Extracts |
|------|---------|
| `strict` | Named entities (PERSON, ORG, GPE, LOC) + cardinal numbers + dates |
| `balanced` | Entities + numbers only (no key terms) |
| `loose` | Key noun phrases from text (no NER dependency) |

Named entity extraction uses spaCy (`en_core_web_sm` / `ru_core_news_sm`).  Key terms use noun chunk extraction from the dependency parse.

---

## 9. Evaluation Engine

**File**: `backend/application/services/evaluation_engine.py`

### Absolute Metrics

| Metric | Method |
|--------|--------|
| `bertscore_f1` | BERTScore F1 (Recall-precision harmonic mean via `bert_score` library) |
| `perplexity` | GPT-2 cross-entropy loss: ppl = exp(loss) |
| `burstiness` | σ(sentence_lengths) / μ(sentence_lengths) |
| `readability` | Mean sentence length (word count) |
| `lexical_diversity_ttr` | type/token ratio |
| `cliche_count` | Hard-coded cliché phrase list |

### Judge Evaluation (LLM-as-judge)

GPT-4-class model evaluates rewrite on 3 dimensions (1–5 each):
- Style match to the reference library
- Semantic preservation vs original
- Fluency / naturalness

### Pairwise Comparison

Prompt asks the judge to pick variant A or B as "more human-like", returning `winner: "A" | "B" | "tie"` plus justification.

---

## 10. Input Analyzer

**File**: `backend/application/services/input_analyzer.py`

Pre-rewrite analysis step returning:
- `word_count`, `sentence_count`, `avg_sentence_length`
- `language_detected` (via langdetect)
- `formality_score` (noun + adj proportion)
- `complexity_score` (avg word length proxy)
- `recommended_mode` — suggested rewrite mode based on text characteristics

---

## 11. Structural Polishing

**File**: `backend/application/services/structural_polishing.py`

Post-generation polish pass:
1. Normalise whitespace and punctuation
2. Apply style-profile–driven sentence length targets (split overly long sentences)
3. Remove clichéd openers ("In conclusion", "It is important to note")
4. Ensure paragraph coherence (topic sentence detection)

Grammar checking (`grammar_layer.py`) runs after polishing and returns a list of rule violations with positions.
