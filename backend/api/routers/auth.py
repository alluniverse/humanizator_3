"""Auth router: register, login (issue JWT), API-key management."""

from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.tenant import TenantContext, require_tenant
from infrastructure.auth.jwt import create_access_token
from infrastructure.cache.redis_client import redis_cache
from infrastructure.config import settings
from infrastructure.db.models import User
from infrastructure.db.session import get_async_session

router = APIRouter(prefix="/auth", tags=["auth"])

_API_KEY_PREFIX = "apikey:"
_API_KEY_TTL = 60 * 60 * 24 * 365  # 1 year


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    full_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str


class ApiKeyResponse(BaseModel):
    api_key: str
    user_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    data: RegisterRequest,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Create a new user account and return an access token."""
    existing = await session.execute(select(User).where(User.email == data.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    user = User(email=data.email, full_name=data.full_name)
    session.add(user)
    await session.commit()
    await session.refresh(user)

    token = create_access_token(user.id, ttl_minutes=settings.jwt_ttl_minutes)
    return TokenResponse(access_token=token, user_id=str(user.id))


@router.post("/token", response_model=TokenResponse)
async def issue_token(
    email: str,
    project_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> TokenResponse:
    """Issue a JWT for an existing user (development/admin use).

    Production systems should add password/OAuth verification here.
    """
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    token = create_access_token(user.id, project_id=project_id, ttl_minutes=settings.jwt_ttl_minutes)
    return TokenResponse(access_token=token, user_id=str(user.id))


@router.post("/api-keys", response_model=ApiKeyResponse)
async def create_api_key(
    ctx: TenantContext = Depends(require_tenant),
) -> ApiKeyResponse:
    """Generate a new API key for the authenticated user.

    The key is stored in Redis (hashed) with user_id payload.
    """
    user_id = ctx.user_id_or_raise
    raw_key = f"hum_{secrets.token_urlsafe(32)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    payload = json.dumps({"user_id": str(user_id)})
    await redis_cache.client.setex(f"{_API_KEY_PREFIX}{key_hash}", _API_KEY_TTL, payload)
    # Also store the raw key index so we can revoke by prefix
    await redis_cache.client.setex(f"{_API_KEY_PREFIX}raw:{raw_key[:16]}", _API_KEY_TTL, key_hash)
    return ApiKeyResponse(api_key=raw_key, user_id=str(user_id))


@router.delete("/api-keys/{key_prefix}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_prefix: str,
    ctx: TenantContext = Depends(require_tenant),
) -> None:
    """Revoke an API key by its first 16 characters."""
    hash_val = await redis_cache.client.get(f"{_API_KEY_PREFIX}raw:{key_prefix}")
    if hash_val is None:
        raise HTTPException(status_code=404, detail="API key not found")
    await redis_cache.client.delete(f"{_API_KEY_PREFIX}{hash_val}")
    await redis_cache.client.delete(f"{_API_KEY_PREFIX}raw:{key_prefix}")
