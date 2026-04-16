"""REST API router for Admin / Tenant operations."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.rate_limiter import QUOTA_TIERS, get_tenant_usage, set_tenant_tier
from infrastructure.db.models import LLMProviderConfig, Project, StyleLibrary, User
from infrastructure.db.session import get_async_session

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/projects/{project_id}/libraries/{library_id}/link")
async def link_library_to_project(
    project_id: uuid.UUID,
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    project = await session.get(Project, project_id)
    library = await session.get(StyleLibrary, library_id)
    if not project or not library:
        raise HTTPException(status_code=404, detail="Project or library not found")
    library.project_id = project_id
    await session.commit()
    return {"project_id": str(project_id), "library_id": str(library_id), "linked": True}


@router.get("/projects/{project_id}/libraries")
async def list_project_libraries(
    project_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> list[dict[str, Any]]:
    result = await session.execute(
        select(StyleLibrary).where(StyleLibrary.project_id == project_id)
    )
    libraries = result.scalars().all()
    return [
        {
            "id": str(lib.id),
            "name": lib.name,
            "category": lib.category.value,
            "language": lib.language,
        }
        for lib in libraries
    ]


@router.post("/llm-providers")
async def create_llm_provider(
    provider_name: str,
    default_model: str,
    api_key_encrypted: str | None = None,
    base_url: str | None = None,
    project_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    config = LLMProviderConfig(
        provider_name=provider_name,
        default_model=default_model,
        api_key_encrypted=api_key_encrypted,
        base_url=base_url,
        project_id=project_id,
    )
    session.add(config)
    await session.commit()
    await session.refresh(config)
    return {
        "id": str(config.id),
        "provider_name": config.provider_name,
        "default_model": config.default_model,
        "project_id": str(config.project_id) if config.project_id else None,
    }


@router.get("/llm-providers")
async def list_llm_providers(
    session: AsyncSession = Depends(get_async_session),
) -> list[dict[str, Any]]:
    result = await session.execute(select(LLMProviderConfig))
    configs = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "provider_name": c.provider_name,
            "default_model": c.default_model,
            "is_active": c.is_active,
        }
        for c in configs
    ]


# ---------------------------------------------------------------------------
# Tenant quota management
# ---------------------------------------------------------------------------


@router.post("/tenants/{tenant_id}/tier")
async def set_quota_tier(
    tenant_id: str,
    tier: str,
) -> dict[str, Any]:
    """Set quota tier for a tenant. Valid tiers: free, basic, pro, unlimited."""
    if tier not in QUOTA_TIERS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid tier '{tier}'. Valid: {list(QUOTA_TIERS)}",
        )
    await set_tenant_tier(tenant_id, tier)
    return {"tenant_id": tenant_id, "tier": tier, "quota": QUOTA_TIERS[tier]}


@router.get("/tenants/{tenant_id}/usage")
async def get_quota_usage(tenant_id: str) -> dict[str, Any]:
    """Return current rate-limit usage counters for a tenant."""
    return await get_tenant_usage(tenant_id)
