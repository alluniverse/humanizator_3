"""JWT encode/decode utilities using PyJWT (HS256).

Tokens carry:
  sub  — user_id (UUID string)
  pid  — optional project_id (UUID string)
  exp  — expiry timestamp
  iat  — issued-at timestamp
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from infrastructure.config import settings

_ALGORITHM = "HS256"
_DEFAULT_TTL_MINUTES = 60 * 24  # 24 hours


def create_access_token(
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None,
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
) -> str:
    """Return a signed JWT for the given user (and optional project)."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    if project_id is not None:
        payload["pid"] = str(project_id)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT.  Raises jwt.InvalidTokenError on failure."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[_ALGORITHM])
