"""Pytest fixtures."""

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.main import app
from infrastructure.cache.redis_client import redis_cache, redis_queue
from infrastructure.db.session import async_engine
from infrastructure.db.base import Base


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_db():
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    await redis_cache.connect()
    await redis_queue.connect()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await redis_cache.disconnect()
    await redis_queue.disconnect()
