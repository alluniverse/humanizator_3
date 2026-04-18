"""TenantContext FastAPI dependency.

Resolution order:
  1. Authorization: Bearer <JWT>  → decode sub/pid claims
  2. X-API-Key header             → Redis lookup key→user_id
  3. Anonymous                    → user_id=None (dev/open access)

TenantContext is passed to routers to scope all DB queries.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.auth.jwt import decode_access_token
from infrastructure.cache.redis_client import redis_cache
from infrastructure.db.models import User
from infrastructure.db.session import get_async_session

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Redis key prefix for API key → user_id mapping
_API_KEY_PREFIX = "apikey:"


@dataclass
class TenantContext:
    """Resolved identity for the current request."""

    user_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    # Resolved tier (used for audit / rate limiting cross-reference)
    is_authenticated: bool = False
    is_admin: bool = False

    @property
    def user_id_or_raise(self) -> uuid.UUID:
        if self.user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        return self.user_id


async def _resolve_api_key(api_key: str) -> dict[str, Any] | None:
    """Look up API key in Redis.  Returns {user_id, project_id} or None.

    Keys are stored by SHA-256 hash of the raw key value.
    """
    import hashlib
    import json

    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    try:
        raw = await redis_cache.client.get(f"{_API_KEY_PREFIX}{key_hash}")
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:
        logger.warning("API key lookup failed: %s", exc)
        return None


async def get_current_tenant(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    api_key: str | None = Depends(_api_key_header),
) -> TenantContext:
    """Resolve tenant from Bearer JWT or X-API-Key.

    Falls back to anonymous TenantContext (user_id=None) when neither
    credential is present — allows unauthenticated dev access.
    Raise HTTP 401 in route handlers via ctx.user_id_or_raise when needed.
    """
    # 1. JWT Bearer
    if credentials is not None:
        try:
            payload = decode_access_token(credentials.credentials)
            user_id = uuid.UUID(payload["sub"])
            project_id = uuid.UUID(payload["pid"]) if "pid" in payload else None
            return TenantContext(user_id=user_id, project_id=project_id, is_authenticated=True)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {exc}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    # 2. API Key
    if api_key:
        data = await _resolve_api_key(api_key)
        if data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )
        user_id = uuid.UUID(data["user_id"]) if "user_id" in data else None
        project_id = uuid.UUID(data["project_id"]) if "project_id" in data else None
        return TenantContext(user_id=user_id, project_id=project_id, is_authenticated=True)

    # 3. Anonymous fallback
    return TenantContext()


async def require_tenant(
    ctx: TenantContext = Depends(get_current_tenant),
) -> TenantContext:
    """Strict variant — raises 401 if not authenticated."""
    ctx.user_id_or_raise  # raises if anonymous
    return ctx


async def require_existing_user(
    ctx: TenantContext = Depends(get_current_tenant),
    session: AsyncSession = Depends(get_async_session),
) -> TenantContext:
    """Verify that the authenticated user exists in the DB.

    Raises 401 (not 500) when a valid JWT references a user that was
    deleted or belongs to a wiped database — the frontend interceptor
    then clears localStorage and redirects to /login.
    """
    if ctx.user_id is None:
        return ctx
    user = await session.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found — please log in again",
            headers={"WWW-Authenticate": "Bearer"},
        )
    ctx.is_admin = user.is_admin
    return ctx
