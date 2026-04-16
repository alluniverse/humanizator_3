"""FastAPI application entrypoint."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.health import router as health_router
from api.metrics import metrics_endpoint, PrometheusMiddleware
from api.routers.libraries import router as libraries_router
from infrastructure.cache.redis_client import redis_cache, redis_queue
from infrastructure.config import settings
from infrastructure.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    await redis_cache.connect()
    await redis_queue.connect()
    yield
    await redis_cache.disconnect()
    await redis_queue.disconnect()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

if settings.enable_prometheus:
    app.add_middleware(PrometheusMiddleware)
    app.add_api_route("/metrics", metrics_endpoint)

app.include_router(health_router)
app.include_router(libraries_router)
