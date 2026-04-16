"""Rate limiting middleware and dependency for FastAPI.

Per-tenant sliding window rate limiting backed by Redis.
Limits: requests/minute, rewrite tasks/hour, tokens/day.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from infrastructure.cache.redis_client import redis_cache

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default quota tiers
# ---------------------------------------------------------------------------

QUOTA_TIERS: dict[str, dict[str, int]] = {
    "free": {
        "requests_per_minute": 10,
        "rewrite_tasks_per_hour": 5,
        "tokens_per_day": 50_000,
    },
    "basic": {
        "requests_per_minute": 60,
        "rewrite_tasks_per_hour": 50,
        "tokens_per_day": 500_000,
    },
    "pro": {
        "requests_per_minute": 300,
        "rewrite_tasks_per_hour": 500,
        "tokens_per_day": 5_000_000,
    },
    "unlimited": {
        "requests_per_minute": 10_000,
        "rewrite_tasks_per_hour": 10_000,
        "tokens_per_day": 100_000_000,
    },
}

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


# ---------------------------------------------------------------------------
# Redis-backed sliding window counter
# ---------------------------------------------------------------------------


async def _increment_counter(key: str, window_seconds: int) -> int:
    """Increment a sliding window counter. Returns current count."""
    try:
        client = redis_cache.client
        pipe = client.pipeline()
        now = int(time.time())
        window_start = now - window_seconds

        # Sorted set: score = timestamp, member = unique per-request nano-id
        member = f"{now}:{id(object())}"
        pipe.zadd(key, {member: now})
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        pipe.expire(key, window_seconds + 10)
        results = await pipe.execute()
        return int(results[2])
    except Exception as exc:
        logger.warning("Rate limiter Redis error: %s", exc)
        return 0  # Fail open


# ---------------------------------------------------------------------------
# Quota helpers
# ---------------------------------------------------------------------------


def _get_tenant_id(request: Request, api_key: str | None) -> str:
    """Derive tenant identifier from API key or IP."""
    if api_key:
        return f"key:{api_key[:16]}"
    forwarded = request.headers.get("X-Forwarded-For")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"ip:{ip}"


async def _get_tenant_quota(tenant_id: str) -> dict[str, int]:
    """Look up quota tier for tenant. Falls back to 'free' tier."""
    try:
        tier_key = f"tenant_tier:{tenant_id}"
        tier = await redis_cache.client.get(tier_key)
        return QUOTA_TIERS.get(tier or "free", QUOTA_TIERS["free"])
    except Exception:
        return QUOTA_TIERS["free"]


# ---------------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------------


async def rate_limit_requests(
    request: Request,
    api_key: str | None = Depends(_api_key_header),
) -> str:
    """Dependency: enforce per-minute request rate limit.

    Raises HTTP 429 if limit exceeded. Returns tenant_id.
    """
    tenant_id = _get_tenant_id(request, api_key)
    quota = await _get_tenant_quota(tenant_id)
    limit = quota["requests_per_minute"]

    key = f"rl:req:{tenant_id}"
    count = await _increment_counter(key, window_seconds=60)

    if count > limit:
        logger.warning("Rate limit exceeded: tenant=%s count=%d limit=%d", tenant_id, count, limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rate_limit_exceeded",
                "limit": limit,
                "window": "1 minute",
                "retry_after": 60,
            },
            headers={"Retry-After": "60"},
        )

    return tenant_id


async def rate_limit_rewrite(
    request: Request,
    api_key: str | None = Depends(_api_key_header),
) -> str:
    """Dependency: enforce per-hour rewrite task quota.

    More restrictive — LLM calls are expensive.
    """
    tenant_id = _get_tenant_id(request, api_key)
    quota = await _get_tenant_quota(tenant_id)
    limit = quota["rewrite_tasks_per_hour"]

    key = f"rl:rewrite:{tenant_id}"
    count = await _increment_counter(key, window_seconds=3600)

    if count > limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "rewrite_quota_exceeded",
                "limit": limit,
                "window": "1 hour",
                "retry_after": 3600,
            },
            headers={"Retry-After": "3600"},
        )

    return tenant_id


# ---------------------------------------------------------------------------
# Admin helpers
# ---------------------------------------------------------------------------


async def set_tenant_tier(tenant_id: str, tier: str) -> None:
    """Set quota tier for a tenant. Persists in Redis for 30 days."""
    if tier not in QUOTA_TIERS:
        raise ValueError(f"Unknown tier: {tier}. Valid: {list(QUOTA_TIERS)}")
    key = f"tenant_tier:{tenant_id}"
    await redis_cache.client.setex(key, 60 * 60 * 24 * 30, tier)


async def get_tenant_usage(tenant_id: str) -> dict[str, Any]:
    """Return current usage counters for a tenant."""
    try:
        req_key = f"rl:req:{tenant_id}"
        rewrite_key = f"rl:rewrite:{tenant_id}"
        req_count = await redis_cache.client.zcard(req_key)
        rewrite_count = await redis_cache.client.zcard(rewrite_key)
        quota = await _get_tenant_quota(tenant_id)
        return {
            "tenant_id": tenant_id,
            "requests_this_minute": req_count,
            "rewrite_tasks_this_hour": rewrite_count,
            "quota": quota,
        }
    except Exception as exc:
        logger.warning("Failed to get usage for tenant %s: %s", tenant_id, exc)
        return {"tenant_id": tenant_id, "error": str(exc)}
