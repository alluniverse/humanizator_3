"""REST API router for Style Profiles."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.library import StyleProfileRead
from application.services.style_profile import style_profile_engine
from domain.enums import QualityTier
from infrastructure.db.models import StyleLibrary, StyleProfile, StyleSample
from infrastructure.db.session import get_async_session

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("/{library_id}/build", response_model=StyleProfileRead, status_code=status.HTTP_201_CREATED)
async def build_profile(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> StyleProfile:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    result = await session.execute(
        select(StyleSample).where(
            StyleSample.library_id == library_id,
            StyleSample.quality_tier.in_([QualityTier.L1, QualityTier.L2]),
        )
    )
    samples = result.scalars().all()
    sample_dicts = [{"content": s.content, "quality_tier": s.quality_tier} for s in samples]

    profile_data = style_profile_engine.build_profile(sample_dicts, language=library.language)

    profile = StyleProfile(
        library_id=library_id,
        version=library.version,
        formality=profile_data.get("formality"),
        sentence_length_mean=profile_data.get("sentence_length_mean"),
        sentence_length_variance=profile_data.get("sentence_length_variance"),
        burstiness_index=profile_data.get("burstiness_index"),
        target_perplexity_min=profile_data.get("target_perplexity_min"),
        target_perplexity_max=profile_data.get("target_perplexity_max"),
        rhythm_profile=profile_data.get("rhythm_profile"),
        lexical_signature=profile_data.get("lexical_signature"),
        syntax_patterns=profile_data.get("syntax_patterns"),
        composition_profile=profile_data.get("composition_profile"),
        linguistic_markers=profile_data.get("linguistic_markers"),
        guidance_signals=profile_data.get("guidance_signals"),
    )
    session.add(profile)
    await session.commit()
    await session.refresh(profile)
    return profile


@router.get("/{library_id}/latest", response_model=StyleProfileRead)
async def get_latest_profile(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> StyleProfile:
    result = await session.execute(
        select(StyleProfile)
        .where(StyleProfile.library_id == library_id)
        .order_by(StyleProfile.created_at.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@router.get("/{library_id}/dna")
async def get_style_dna(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    result = await session.execute(
        select(StyleProfile)
        .where(StyleProfile.library_id == library_id)
        .order_by(StyleProfile.created_at.desc())
        .limit(1)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {
        "library_id": str(library_id),
        "formality": profile.formality,
        "sentence_length_mean": profile.sentence_length_mean,
        "burstiness_index": profile.burstiness_index,
        "target_perplexity_range": [profile.target_perplexity_min, profile.target_perplexity_max],
        "lexical_signature": profile.lexical_signature,
        "syntax_patterns": profile.syntax_patterns,
        "guidance_signals": profile.guidance_signals,
    }
