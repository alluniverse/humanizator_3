"""LLM Cost Tracker.

Tracks token usage and estimated cost for LLM calls, aggregated per project/tenant.
Stores summaries in Redis (fast, ephemeral) and writes to AuditLog for durability.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default cost table (USD per 1K tokens)
# Overridden per-project via LLMProviderConfig in DB
# ---------------------------------------------------------------------------
DEFAULT_COST_TABLE: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}


def estimate_cost(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost_per_input_token: float | None = None,
    cost_per_output_token: float | None = None,
) -> float:
    """Return estimated USD cost for a single LLM call."""
    if cost_per_input_token is not None and cost_per_output_token is not None:
        input_cost = prompt_tokens * cost_per_input_token
        output_cost = completion_tokens * cost_per_output_token
    else:
        rates = DEFAULT_COST_TABLE.get(model, {"input": 0.001, "output": 0.002})
        input_cost = (prompt_tokens / 1000) * rates["input"]
        output_cost = (completion_tokens / 1000) * rates["output"]
    return round(input_cost + output_cost, 6)


class LLMCostTracker:
    """Aggregates LLM usage and persists to Redis + AuditLog."""

    # Redis hash keys: llm_cost:{project_id} → {model: json}
    _KEY_PREFIX = "llm_cost"
    _TTL = 60 * 60 * 24 * 7  # 7 days in Redis

    async def record(
        self,
        *,
        project_id: str | None,
        model: str,
        usage: dict[str, Any],
        cost_per_input_token: float | None = None,
        cost_per_output_token: float | None = None,
        task_id: str | None = None,
    ) -> float:
        """Record a single LLM call, return estimated cost."""
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        cost = estimate_cost(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_per_input_token=cost_per_input_token,
            cost_per_output_token=cost_per_output_token,
        )

        await self._update_redis(project_id, model, prompt_tokens, completion_tokens, cost)
        await self._write_audit_log(project_id, model, total_tokens, cost, task_id)
        return cost

    async def get_project_summary(self, project_id: str) -> dict[str, Any]:
        """Return usage summary for a project (from Redis)."""
        from infrastructure.cache.redis_client import redis_cache

        key = f"{self._KEY_PREFIX}:{project_id}"
        try:
            raw = await redis_cache.client.hgetall(key)
            import json
            summary: dict[str, Any] = {}
            total_cost = 0.0
            for model_name, json_data in raw.items():
                data = json.loads(json_data)
                summary[model_name] = data
                total_cost += data.get("cost_usd", 0.0)
            return {"project_id": project_id, "models": summary, "total_cost_usd": round(total_cost, 4)}
        except Exception as exc:
            logger.warning("Failed to get cost summary for project %s: %s", project_id, exc)
            return {"project_id": project_id, "models": {}, "total_cost_usd": 0.0}

    async def _update_redis(
        self,
        project_id: str | None,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost: float,
    ) -> None:
        from infrastructure.cache.redis_client import redis_cache
        import json

        scope = project_id or "global"
        key = f"{self._KEY_PREFIX}:{scope}"
        try:
            existing_raw = await redis_cache.client.hget(key, model)
            if existing_raw:
                existing = json.loads(existing_raw)
            else:
                existing = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}

            existing["calls"] += 1
            existing["prompt_tokens"] += prompt_tokens
            existing["completion_tokens"] += completion_tokens
            existing["cost_usd"] = round(existing["cost_usd"] + cost, 6)

            await redis_cache.client.hset(key, model, json.dumps(existing))
            await redis_cache.client.expire(key, self._TTL)
        except Exception as exc:
            logger.warning("Failed to update cost Redis for project=%s: %s", project_id, exc)

    async def _write_audit_log(
        self,
        project_id: str | None,
        model: str,
        total_tokens: int,
        cost: float,
        task_id: str | None,
    ) -> None:
        from infrastructure.db.models import AuditLog
        from infrastructure.db.session import AsyncSessionLocal
        import uuid

        try:
            async with AsyncSessionLocal() as session:
                log = AuditLog(
                    project_id=uuid.UUID(project_id) if project_id else None,
                    action="llm_call",
                    entity_type="rewrite_task",
                    entity_id=task_id,
                    details={
                        "model": model,
                        "total_tokens": total_tokens,
                        "cost_usd": cost,
                    },
                )
                session.add(log)
                await session.commit()
        except Exception as exc:
            logger.warning("Failed to write audit log for LLM cost: %s", exc)


llm_cost_tracker = LLMCostTracker()
