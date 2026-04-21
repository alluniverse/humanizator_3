"""Cache key builders and TTL constants.

Centralised definitions for all Redis cache keys used in the system.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# TTL constants (seconds)
# ---------------------------------------------------------------------------

# Style profiles change only when samples are added/removed → long TTL
TTL_STYLE_PROFILE = 60 * 60 * 24  # 24 h

# Word importance depends on the text only → long TTL (keyed on text hash)
TTL_WORD_IMPORTANCE = 60 * 60 * 12  # 12 h

# USE / sentence embeddings are deterministic → very long TTL
TTL_USE_EMBEDDING = 60 * 60 * 48  # 48 h

# LLM response cache: only for identical prompts (rare hit rate) → short TTL
TTL_LLM_RESPONSE = 60 * 30  # 30 min

# Rewrite task status (polled by API consumers) → short TTL
TTL_TASK_STATUS = 60 * 5  # 5 min

# Library quality tier summary
TTL_LIBRARY_TIER = 60 * 60 * 6  # 6 h


# ---------------------------------------------------------------------------
# Key builders
# ---------------------------------------------------------------------------


def style_profile_key(library_id: str) -> str:
    """Cache key for the latest style profile of a library."""
    return f"style_profile:{library_id}"


def word_importance_key(text_hash: str) -> str:
    """Cache key for word importance scores (keyed on SHA256 of text)."""
    return f"word_importance:{text_hash}"


def use_embedding_key(text_hash: str) -> str:
    """Cache key for USE/sentence-transformer embeddings."""
    return f"use_embed:{text_hash}"


def llm_response_key(prompt_hash: str, model: str) -> str:
    """Cache key for deterministic LLM responses."""
    return f"llm:{model}:{prompt_hash}"


def task_status_key(task_id: str) -> str:
    """Cache key for real-time task status (supplements DB polling)."""
    return f"task_status:{task_id}"


def library_tier_key(library_id: str) -> str:
    """Cache key for library quality tier summary."""
    return f"library_tier:{library_id}"
