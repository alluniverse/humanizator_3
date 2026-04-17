# Humanizator 3 — Architecture Documentation

## Overview

Humanizator 3 is a modular text rewriting system that transforms AI-generated or formal text into natural, human-sounding prose while preserving semantic fidelity. It supports multiple rewrite modes, style libraries built from reference texts, human-in-the-loop review, and multi-tenant access control.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         API Layer (FastAPI)                       │
│  /libraries  /rewrite  /evaluation  /hitl  /auth  /admin  /hitl  │
└──────────┬──────────────────────────────────────────┬────────────┘
           │                                          │
┌──────────▼──────────┐                 ┌─────────────▼───────────┐
│  Application Layer  │                 │   Infrastructure Layer   │
│  (services)         │                 │                          │
│                     │                 │  PostgreSQL (async)      │
│  RewriteEngine      │◄───────────────►│  Redis (cache + queue)   │
│  EvaluationEngine   │                 │  Celery (async tasks)    │
│  HallucinationDet.  │                 │  Prometheus + Grafana    │
│  StyleConflictDet.  │                 └─────────────────────────┘
│  TokenPrecision     │
│  AdversarialRobust. │                 ┌─────────────────────────┐
│  QualityTiering     │◄───────────────►│  LLM Adapters           │
│  SemanticContract   │                 │  OpenAIProvider (API)    │
└─────────────────────┘                 │  HFPrecisionProvider     │
                                        │  (local HuggingFace)     │
                                        └─────────────────────────┘
```

---

## Directory Structure

```
backend/
├── api/                        # FastAPI routers, schemas, middleware
│   ├── deps/                   # Dependency injection (tenant context)
│   ├── routers/                # HTTP endpoints grouped by domain
│   │   ├── auth.py             # JWT auth, API key management
│   │   ├── libraries.py        # Style libraries + samples + snapshots
│   │   ├── rewrite.py          # Rewrite task creation and management
│   │   ├── evaluation.py       # Evaluation endpoints (metrics, robustness)
│   │   ├── hitl.py             # Human-in-the-Loop review bundle
│   │   ├── profiles.py         # Style profiles
│   │   ├── presets.py          # Rewrite presets
│   │   └── admin.py            # Admin: quotas, tenant management
│   ├── schemas/                # Pydantic request/response models
│   ├── rate_limiter.py         # Redis sliding-window rate limiting
│   └── main.py                 # FastAPI app + lifespan
│
├── adapters/
│   └── llm/
│       ├── base.py             # LLMProvider abstract base
│       ├── openai_provider.py  # OpenAI-compatible API adapter
│       └── hf_precision_provider.py  # HuggingFace local model with logit access
│
├── application/
│   └── services/               # Business logic services
│       ├── evaluation_engine.py        # BERTScore, perplexity, judge eval
│       ├── hallucination_detector.py   # Entity/semantic/structural checks
│       ├── adversarial_robustness.py   # 5-attack adversarial stress test
│       ├── token_precision.py          # Algorithm 1 token-level rewrite
│       ├── quality_tiering.py          # L1/L2/L3 corpus quality tiers
│       ├── semantic_contract.py        # Protected entity extraction
│       ├── style_conflict_detector.py  # Z-score style outlier detection
│       ├── style_guidance.py           # Style profile ranking
│       ├── style_profile.py            # Profile computation
│       ├── holistic_ranker.py          # Holistic lexical substitution scorer
│       ├── structural_polishing.py     # Post-generation polish pass
│       ├── grammar_layer.py            # Grammar checking
│       ├── word_importance.py          # Token-level word salience
│       └── input_analyzer.py          # Pre-rewrite input analysis
│
├── rewrite/
│   ├── guided_rewrite.py       # GuidedRewriteEngine (all modes)
│   └── prompts.py              # Prompt templates per mode
│
├── constraints/
│   └── rewrite_constraints.py  # POS, MPR, USE similarity constraints
│
├── domain/
│   └── enums.py                # Core enums (modes, statuses, tiers)
│
├── infrastructure/
│   ├── auth/jwt.py             # HS256 JWT encode/decode
│   ├── cache/                  # Redis client, cache service, key registry
│   ├── db/                     # SQLAlchemy models, async session
│   ├── config.py               # Pydantic-settings (env vars)
│   ├── logging.py              # Structured logging setup
│   └── llm_cost_tracker.py     # Per-request token cost tracking
│
├── async_tasks/
│   ├── celery_app.py           # Celery configuration
│   ├── rewrite_tasks.py        # Async rewrite pipeline tasks
│   └── library_tasks.py       # Library indexing/quality refresh tasks
│
└── tests/
    ├── unit/                   # Pure logic tests (no DB/model loading)
    ├── integration/            # Tests with mocked NLP + real DB
    └── e2e/                    # End-to-end pipeline tests
```

---

## Key Architectural Decisions

### 1. Multi-tenant Data Isolation

Every resource (library, task, variant) carries `owner_id` / `user_id`. The `TenantContext` is resolved from:
1. Bearer JWT (HS256, 24h TTL by default)
2. `X-API-Key` header → SHA-256 → Redis lookup
3. Anonymous fallback (read-only subset of endpoints)

Cross-tenant access raises HTTP 403. See `api/deps/tenant.py`.

### 2. Style Library Architecture

Libraries are collections of reference text samples. Each sample is:
- Automatically tiered L1/L2/L3 on ingest (quality_tiering service)
- Analyzed for stylometric features (burstiness, TTR, formality, avg_sent_len)
- Optionally restricted to a single author (`is_single_voice=True`)

Libraries support:
- **Export/Import** (JSON schema v1 with schema_version field)
- **Versioned snapshots** in Redis (90-day TTL, keyed by `snapshot:{lib_id}:{uuid8}`)
- **Conflict detection** via Z-score outlier analysis across stylometric dimensions

### 3. Rewrite Modes

| Mode | Description | Provider |
|------|-------------|----------|
| `conservative` | Adversarial paraphrasing (Cheng et al. 2025 Fig. 2) | OpenAI API |
| `balanced` | Diversifying rewrite with style guidance | OpenAI API |
| `expressive` | Reference-mimicking rewrite | OpenAI API |
| `precision` | Token-level AI-score minimisation (Algorithm 1) | HF local model |

Long texts (>300 words) use chunk-level processing: split at paragraph boundaries, rewrite each chunk with a 1-sentence cross-chunk context prefix, reassemble.

### 4. Semantic Contract

Before rewriting, a semantic contract is extracted from the source text:
- `protected_entities`: named entities (persons, orgs, locations)
- `protected_numbers`: cardinal numbers and dates
- `key_terms`: domain-specific noun phrases

Modes: `strict` (all entities), `balanced` (entities + numbers), `loose` (key terms only).

The contract is used by:
- The rewrite prompt (as constraints)
- `RewriteConstraintLayer` (post-generation validation)
- `HallucinationDetector` (entity drift check)

### 5. Rate Limiting

Redis sliding-window rate limiting with 4 tiers:

| Tier | Requests/min | Rewrites/hour |
|------|-------------|---------------|
| free | 10 | 20 |
| standard | 60 | 200 |
| professional | 300 | 1000 |
| enterprise | 1000 | 5000 |

Tenant tier stored in Redis key `tenant_tier:{user_id}`. Exceeded limits return HTTP 429.

### 6. Evaluation Pipeline

Post-generation evaluation produces:
- **Absolute metrics**: BERTScore F1, perplexity, burstiness, TTR, readability
- **Judge evaluation**: LLM-as-judge scoring (1–5) for style match, semantic preservation, fluency
- **Pairwise comparison**: A vs B preference ranking
- **Hallucination detection**: entity drift, semantic drift, structural artifacts, length ratio
- **Adversarial robustness**: 5-attack stress test with cosine similarity tracking

Results are stored in `EvaluationReport` records linked to `RewriteVariant`.

### 7. Human-in-the-Loop (HITL)

`GET /hitl/{task_id}` returns an aggregated review bundle containing:
- Task metadata + original text
- All variants with stored scores
- Inline hallucination check per variant (optional)
- Existing evaluation reports

`POST /hitl/{task_id}/review` accepts `approve | reject | request_revision` per variant, storing the decision in `variant.is_valid` and `variant.explanation`.

---

## Data Model (key tables)

```
StyleLibrary
  id, name, language, category, quality_tier, version
  is_single_voice, owner_id, project_id

StyleSample
  id, library_id, content, author, quality_tier
  title, source, language

StyleProfile
  id, library_id, guidance_signals (JSON)

RewriteTask
  id, library_id, original_text, rewrite_mode
  semantic_contract_mode, status, user_id, project_id

RewriteVariant
  id, task_id, mode, final_text, is_valid
  style_match_score, semantic_preservation_score
  perplexity_score, burstiness_score, fluency_win_rate

EvaluationReport
  id, task_id, variant_id
  absolute_metrics, judge_scores, contract_violations
  composite_score, warnings
```

---

## Infrastructure

### Database
PostgreSQL with async SQLAlchemy + asyncpg. Migrations via Alembic.

### Cache
Redis (two databases):
- DB 0: task queue (Celery broker)
- DB 1: application cache (rate limits, API keys, tenant tiers, snapshots)

### Background Tasks
Celery workers handle:
- Long rewrite pipelines (post-creation async processing)
- Library quality refresh after bulk sample import

### Monitoring
- Prometheus metrics at `/metrics` (behind `enable_prometheus` flag)
- 6 alert rules: HighErrorRate, SlowResponseTime, RewriteQueueBacklog, HighRateLimitRejections, AppDown, HighMemoryUsage
- Grafana dashboard: 8 panels covering latency, error rate, queue depth, active tenants

### CI/CD
GitHub Actions (`.github/workflows/ci.yml`):
1. **lint-and-unit**: ruff + pytest unit tests (no services required)
2. **integration**: postgres + redis service containers, Alembic migrations, integration + E2E tests
3. **docker-build**: smoke-test docker build (needs lint-and-unit)

Staging deployment via `scripts/deploy.sh` with rolling restart and health poll loop.
