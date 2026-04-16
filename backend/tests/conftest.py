"""Pytest fixtures."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app
from infrastructure.cache.redis_client import redis_cache, redis_queue


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    await redis_cache.connect()
    await redis_queue.connect()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await redis_cache.disconnect()
    await redis_queue.disconnect()
