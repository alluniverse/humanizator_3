"""REST API router for Presets and Admin/Tenant endpoints."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.library import PresetCreate, PresetRead
from infrastructure.db.models import Preset, Project, StyleLibrary
from infrastructure.db.session import get_async_session

router = APIRouter(prefix="/presets", tags=["presets"])


@router.post("", response_model=PresetRead, status_code=status.HTTP_201_CREATED)
async def create_preset(
    data: PresetCreate,
    session: AsyncSession = Depends(get_async_session),
) -> Preset:
    library = await session.get(StyleLibrary, data.library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    preset = Preset(
        name=data.name,
        library_id=data.library_id,
        rewrite_mode=data.rewrite_mode,
        semantic_contract_mode=data.semantic_contract_mode,
        constraints=data.constraints,
        intervention_level=data.intervention_level,
        active_heuristics=data.active_heuristics,
    )
    session.add(preset)
    await session.commit()
    await session.refresh(preset)
    return preset


@router.get("/{preset_id}", response_model=PresetRead)
async def get_preset(
    preset_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> Preset:
    preset = await session.get(Preset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@router.get("/library/{library_id}", response_model=list[PresetRead])
async def list_presets_for_library(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> list[Preset]:
    result = await session.execute(
        select(Preset).where(Preset.library_id == library_id)
    )
    return list(result.scalars().all())


@router.post("/{preset_id}/apply")
async def apply_preset(
    preset_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    preset = await session.get(Preset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return {
        "preset_id": str(preset_id),
        "library_id": str(preset.library_id),
        "rewrite_mode": preset.rewrite_mode.value,
        "semantic_contract_mode": preset.semantic_contract_mode.value,
        "constraints": preset.constraints,
        "intervention_level": preset.intervention_level,
        "active_heuristics": preset.active_heuristics,
    }
