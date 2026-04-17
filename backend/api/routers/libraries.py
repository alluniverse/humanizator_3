"""REST API router for Style Libraries and Samples."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.tenant import TenantContext, get_current_tenant
from api.schemas.library import (
    BulkSampleImport,
    LibraryDiagnostics,
    StyleLibraryCreate,
    StyleLibraryDetailRead,
    StyleLibraryRead,
    StyleLibraryUpdate,
    StyleSampleCreate,
    StyleSampleRead,
    StyleSampleUpdate,
)
from application.services.quality_tiering import quality_tiering_service
from application.services.style_conflict_detector import style_conflict_detector
from domain.enums import QualityTier
from infrastructure.db.models import StyleLibrary, StyleSample
from infrastructure.db.session import get_async_session

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _check_library_access(library: StyleLibrary, ctx: TenantContext) -> None:
    """Raise 403 if the tenant doesn't own this library."""
    if ctx.user_id is not None and library.owner_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("", response_model=StyleLibraryRead, status_code=status.HTTP_201_CREATED)
async def create_library(
    data: StyleLibraryCreate,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> StyleLibrary:
    library = StyleLibrary(
        name=data.name,
        description=data.description,
        category=data.category,
        language=data.language,
        project_id=data.project_id or ctx.project_id,
        owner_id=ctx.user_id,
        is_single_voice=data.is_single_voice,
    )
    session.add(library)
    await session.commit()
    await session.refresh(library)
    return library


@router.get("", response_model=list[StyleLibraryRead])
async def list_libraries(
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[StyleLibrary]:
    query = select(StyleLibrary).where(StyleLibrary.status == "active")
    if ctx.user_id is not None:
        query = query.where(StyleLibrary.owner_id == ctx.user_id)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{library_id}", response_model=StyleLibraryDetailRead)
async def get_library(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> StyleLibrary:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)
    return library


@router.patch("/{library_id}", response_model=StyleLibraryRead)
async def update_library(
    library_id: uuid.UUID,
    data: StyleLibraryUpdate,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> StyleLibrary:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(library, field, value)
    await session.commit()
    await session.refresh(library)
    return library


@router.delete("/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_library(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> None:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)
    library.status = "archived"
    await session.commit()


@router.post("/{library_id}/samples", response_model=StyleSampleRead, status_code=status.HTTP_201_CREATED)
async def add_sample(
    library_id: uuid.UUID,
    data: StyleSampleCreate,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> StyleSample:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    tier = quality_tiering_service.tier_sample(data.content)
    sample = StyleSample(
        library_id=library_id,
        title=data.title,
        content=data.content,
        source=data.source,
        content_type=data.content_type,
        author=data.author,
        language=data.language,
        quality_tier=tier,
    )
    session.add(sample)
    await session.commit()
    await session.refresh(sample)

    # Update library quality diagnostics
    await _refresh_library_quality(library_id, session)
    return sample


@router.post("/{library_id}/samples/bulk", response_model=list[StyleSampleRead], status_code=status.HTTP_201_CREATED)
async def bulk_add_samples(
    library_id: uuid.UUID,
    data: BulkSampleImport,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[StyleSample]:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    samples: list[StyleSample] = []
    for item in data.samples:
        tier = quality_tiering_service.tier_sample(item.content)
        samples.append(
            StyleSample(
                library_id=library_id,
                title=item.title,
                content=item.content,
                source=item.source,
                content_type=item.content_type,
                author=item.author,
                language=item.language,
                quality_tier=tier,
            )
        )
    session.add_all(samples)
    await session.commit()
    for s in samples:
        await session.refresh(s)

    await _refresh_library_quality(library_id, session)
    return samples


@router.get("/{library_id}/samples/{sample_id}", response_model=StyleSampleRead)
async def get_sample(
    library_id: uuid.UUID,
    sample_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> StyleSample:
    sample = await session.get(StyleSample, sample_id)
    if not sample or sample.library_id != library_id:
        raise HTTPException(status_code=404, detail="Sample not found")
    return sample


@router.patch("/{library_id}/samples/{sample_id}", response_model=StyleSampleRead)
async def update_sample(
    library_id: uuid.UUID,
    sample_id: uuid.UUID,
    data: StyleSampleUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> StyleSample:
    sample = await session.get(StyleSample, sample_id)
    if not sample or sample.library_id != library_id:
        raise HTTPException(status_code=404, detail="Sample not found")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(sample, field, value)
    if "content" in updates:
        sample.quality_tier = quality_tiering_service.tier_sample(sample.content)
    await session.commit()
    await session.refresh(sample)
    await _refresh_library_quality(library_id, session)
    return sample


@router.delete("/{library_id}/samples/{sample_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sample(
    library_id: uuid.UUID,
    sample_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    sample = await session.get(StyleSample, sample_id)
    if not sample or sample.library_id != library_id:
        raise HTTPException(status_code=404, detail="Sample not found")
    await session.delete(sample)
    await session.commit()
    await _refresh_library_quality(library_id, session)


@router.get("/{library_id}/diagnostics", response_model=LibraryDiagnostics)
async def get_library_diagnostics(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> LibraryDiagnostics:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    result = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    samples = result.scalars().all()
    diag = quality_tiering_service.diagnose_library(
        [{"quality_tier": s.quality_tier} for s in samples]
    )
    return LibraryDiagnostics(**diag)


@router.get("/{library_id}/style-conflicts")
async def get_style_conflicts(
    library_id: uuid.UUID,
    outlier_threshold: float = 2.0,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Detect stylistically conflicting samples in the library.

    Returns outlier samples whose stylometric features (burstiness, sentence
    length, TTR, formality) deviate significantly from the library median.
    """
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    result = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    samples = result.scalars().all()
    sample_dicts = [{"id": str(s.id), "content": s.content} for s in samples]
    return style_conflict_detector.detect_conflicts(sample_dicts, outlier_threshold=outlier_threshold)


async def _refresh_library_quality(library_id: uuid.UUID, session: AsyncSession) -> None:
    result = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    samples = result.scalars().all()
    diag = quality_tiering_service.diagnose_library(
        [{"quality_tier": s.quality_tier} for s in samples]
    )
    library = await session.get(StyleLibrary, library_id)
    if library:
        library.quality_tier = "strong" if diag["is_valid_for_profiling"] else "weak"
        await session.commit()
