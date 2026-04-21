"""High-level cache service.

Wraps Redis with typed get/set helpers, serialisation, and invalidation logic.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from infrastructure.cache.redis_client import redis_cache

logger = logging.getLogger(__name__)


class CacheService:
    """Typed cache helpers with JSON serialisation."""

    async def get(self, key: str) -> Any | None:
        try:
            raw = await redis_cache.client.get(key)
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("Cache GET failed for key=%s: %s", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        try:
            await redis_cache.client.setex(key, ttl, json.dumps(value, default=str))
        except Exception as exc:
            logger.warning("Cache SET failed for key=%s: %s", key, exc)

    async def delete(self, key: str) -> None:
        try:
            await redis_cache.client.delete(key)
        except Exception as exc:
            logger.warning("Cache DELETE failed for key=%s: %s", key, exc)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching a glob pattern. Returns count deleted."""
        try:
            keys = await redis_cache.client.keys(pattern)
            if keys:
                return await redis_cache.client.delete(*keys)
            return 0
        except Exception as exc:
            logger.warning("Cache DELETE pattern=%s failed: %s", pattern, exc)
            return 0

    # ------------------------------------------------------------------
    # Invalidation helpers
    # ------------------------------------------------------------------

    async def invalidate_library(self, library_id: str) -> None:
        """Invalidate all cache entries related to a library.

        Called when samples are added/removed or profile is recalculated.
        """
        from infrastructure.cache.cache_keys import (
            library_tier_key,
            style_profile_key,
        )
        await self.delete(style_profile_key(library_id))
        await self.delete(library_tier_key(library_id))
        logger.debug("Cache invalidated for library %s", library_id)

    async def invalidate_task(self, task_id: str) -> None:
        """Invalidate task status cache."""
        from infrastructure.cache.cache_keys import task_status_key
        await self.delete(task_status_key(task_id))

    # ------------------------------------------------------------------
    # Text hashing helpers
    # ------------------------------------------------------------------

    @staticmethod
    def hash_text(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:32]

    @staticmethod
    def hash_prompt(prompt: str, model: str) -> str:
        combined = f"{model}:{prompt}"
        return hashlib.sha256(combined.encode()).hexdigest()[:32]


cache_service = CacheService()
