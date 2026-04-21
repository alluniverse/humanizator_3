"""Async Redis client wrapper."""

from redis.asyncio import Redis

from infrastructure.config import settings


class RedisCache:
    """Simple async Redis cache wrapper."""

    def __init__(self, url: str) -> None:
        self._url = url
        self._client: Redis | None = None

    async def connect(self) -> None:
        self._client = Redis.from_url(self._url, decode_responses=True)

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def ping(self) -> bool:
        if not self._client:
            return False
        return await self._client.ping()

    @property
    def client(self) -> Redis:
        if self._client is None:
            raise RuntimeError("Redis client is not connected")
        return self._client


redis_cache = RedisCache(str(settings.redis_cache_url))
redis_queue = RedisCache(str(settings.redis_url))
