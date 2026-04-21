"""Health check endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.db.session import get_async_session
from infrastructure.cache.redis_client import redis_queue

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "humanizator"}


@router.get("/health/db")
async def health_db(session: AsyncSession = Depends(get_async_session)) -> dict:
    try:
        from sqlalchemy import text
        await session.execute(text("SELECT 1"))
        return {"status": "ok", "db": "connected"}
    except Exception as exc:
        return {"status": "error", "db": str(exc)}


@router.get("/health/redis")
async def health_redis() -> dict:
    try:
        await redis_queue.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as exc:
        return {"status": "error", "redis": str(exc)}
