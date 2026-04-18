"""REST API router for Style Libraries and Samples."""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.tenant import TenantContext, get_current_tenant, require_existing_user
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
from infrastructure.cache.redis_client import redis_cache
from infrastructure.db.models import StyleLibrary, StyleSample
from infrastructure.db.session import get_async_session

_SNAPSHOT_TTL = 60 * 60 * 24 * 90  # 90 days

router = APIRouter(prefix="/libraries", tags=["libraries"])


def _check_library_access(library: StyleLibrary, ctx: TenantContext) -> None:
    """Raise 403 if the tenant doesn't own this library."""
    if ctx.user_id is not None and library.owner_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("", response_model=StyleLibraryRead, status_code=status.HTTP_201_CREATED)
async def create_library(
    data: StyleLibraryCreate,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(require_existing_user),
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
    ctx: TenantContext = Depends(require_existing_user),
) -> list[StyleLibraryRead]:
    query = (
        select(StyleLibrary, func.count(StyleSample.id).label("sample_count"))
        .outerjoin(StyleSample, StyleSample.library_id == StyleLibrary.id)
        .where(StyleLibrary.status == "active")
        .group_by(StyleLibrary.id)
    )
    if ctx.user_id is not None and not ctx.is_admin:
        query = query.where(StyleLibrary.owner_id == ctx.user_id)
    rows = (await session.execute(query)).all()
    result = []
    for lib, count in rows:
        obj = StyleLibraryRead.model_validate(lib)
        obj.sample_count = count
        result.append(obj)
    return result


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

    # Single-voice enforcement
    existing_result = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    existing_authors = {s.author for s in existing_result.scalars().all() if s.author}
    _check_single_voice(library, data.author, existing_authors)

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


@router.get("/{library_id}/samples", response_model=list[StyleSampleRead])
async def list_samples(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[StyleSample]:
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)
    result = await session.execute(
        select(StyleSample)
        .where(StyleSample.library_id == library_id)
        .order_by(StyleSample.created_at.desc())
    )
    return list(result.scalars().all())


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

    # Single-voice enforcement for bulk import
    if library.is_single_voice:
        existing_result = await session.execute(
            select(StyleSample).where(StyleSample.library_id == library_id)
        )
        existing_authors = {s.author for s in existing_result.scalars().all() if s.author}
        for item in data.samples:
            _check_single_voice(library, item.author, existing_authors)
            if item.author:
                existing_authors.add(item.author)

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


class ScrapeUrlRequest(BaseModel):
    url: str
    split_paragraphs: bool = True  # add each paragraph as a separate sample


@router.post("/{library_id}/samples/from-url", status_code=status.HTTP_201_CREATED)
async def add_samples_from_url(
    library_id: uuid.UUID,
    data: ScrapeUrlRequest,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict:
    """Scrape an article URL and add its content as sample(s) to the library."""
    from application.services.article_scraper import scrape_article

    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    try:
        article = scrape_article(data.url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to fetch URL: {exc}") from exc

    samples: list[StyleSample] = []

    if data.split_paragraphs:
        for para in article.paragraphs:
            tier = quality_tiering_service.tier_sample(para)
            samples.append(
                StyleSample(
                    library_id=library_id,
                    title=article.title,
                    content=para,
                    source=data.url,
                    author=article.domain,
                    language=library.language,
                    quality_tier=tier,
                )
            )
    else:
        tier = quality_tiering_service.tier_sample(article.text)
        samples.append(
            StyleSample(
                library_id=library_id,
                title=article.title,
                content=article.text,
                source=data.url,
                author=article.domain,
                language=library.language,
                quality_tier=tier,
            )
        )

    session.add_all(samples)
    await session.commit()
    for s in samples:
        await session.refresh(s)

    await _refresh_library_quality(library_id, session)

    return {
        "added": len(samples),
        "title": article.title,
        "word_count": article.word_count,
        "domain": article.domain,
        "samples": [{"id": str(s.id), "quality_tier": s.quality_tier} for s in samples],
    }


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


# ---------------------------------------------------------------------------
# T2.4 — Import / Export
# ---------------------------------------------------------------------------


@router.get("/{library_id}/export")
async def export_library(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Export a library and all its samples as a JSON-serialisable dict."""
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    result = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    samples = result.scalars().all()

    return {
        "schema_version": "1.0",
        "exported_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "library": {
            "name": library.name,
            "description": library.description,
            "category": library.category.value,
            "language": library.language,
            "is_single_voice": library.is_single_voice,
            "version": library.version,
        },
        "samples": [
            {
                "title": s.title,
                "content": s.content,
                "source": s.source,
                "content_type": s.content_type,
                "author": s.author,
                "language": s.language,
                "quality_tier": s.quality_tier.value if s.quality_tier else None,
            }
            for s in samples
        ],
    }


class LibraryImportPayload(BaseModel):
    name: str | None = None  # overrides library.name if provided
    data: dict[str, Any]  # the exported JSON dict


@router.post("/import", status_code=status.HTTP_201_CREATED)
async def import_library(
    payload: LibraryImportPayload,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Import a library from an exported JSON dict. Creates a new library."""
    data = payload.data
    lib_data = data.get("library", {})

    from domain.enums import LibraryCategory
    try:
        category = LibraryCategory(lib_data.get("category", "other"))
    except ValueError:
        category = LibraryCategory.OTHER if hasattr(LibraryCategory, "OTHER") else list(LibraryCategory)[0]

    library = StyleLibrary(
        name=payload.name or lib_data.get("name", "Imported Library"),
        description=lib_data.get("description"),
        category=category,
        language=lib_data.get("language", "ru"),
        is_single_voice=lib_data.get("is_single_voice", False),
        owner_id=ctx.user_id,
        project_id=ctx.project_id,
    )
    session.add(library)
    await session.flush()  # get library.id

    samples_data = data.get("samples", [])
    imported_count = 0
    for s in samples_data:
        content = s.get("content", "")
        if not content:
            continue
        tier = quality_tiering_service.tier_sample(content)
        sample = StyleSample(
            library_id=library.id,
            title=s.get("title"),
            content=content,
            source=s.get("source"),
            content_type=s.get("content_type"),
            author=s.get("author"),
            language=s.get("language", library.language),
            quality_tier=tier,
        )
        session.add(sample)
        imported_count += 1

    await session.commit()
    await session.refresh(library)
    await _refresh_library_quality(library.id, session)

    return {
        "library_id": str(library.id),
        "name": library.name,
        "imported_samples": imported_count,
    }


# ---------------------------------------------------------------------------
# T2.5 — Single-voice enforcement
# ---------------------------------------------------------------------------


def _check_single_voice(library: StyleLibrary, new_author: str | None, existing_authors: set[str]) -> None:
    """For single-voice libraries: enforce one unique author across all samples."""
    if not library.is_single_voice:
        return
    if new_author and existing_authors and new_author not in existing_authors:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Single-voice library only allows samples from one author. "
                f"Existing author(s): {existing_authors}. Got: '{new_author}'."
            ),
        )


@router.get("/{library_id}/voice-info")
async def get_voice_info(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Return voice/authorship metadata for the library."""
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    result = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    samples = result.scalars().all()
    authors = {s.author for s in samples if s.author}
    return {
        "is_single_voice": library.is_single_voice,
        "unique_authors": sorted(authors),
        "author_count": len(authors),
        "is_coherent": len(authors) <= 1 if library.is_single_voice else True,
    }


# ---------------------------------------------------------------------------
# T2.6 — Versioning and snapshots (Redis-backed)
# ---------------------------------------------------------------------------


def _snapshot_key(library_id: uuid.UUID, snapshot_id: str) -> str:
    return f"snapshot:{library_id}:{snapshot_id}"


def _snapshot_index_key(library_id: uuid.UUID) -> str:
    return f"snapshot_index:{library_id}"


@router.post("/{library_id}/snapshots", status_code=status.HTTP_201_CREATED)
async def create_snapshot(
    library_id: uuid.UUID,
    label: str | None = None,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Save the current library state as a versioned snapshot in Redis."""
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    result = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    samples = result.scalars().all()

    snapshot_id = str(uuid.uuid4())[:8]
    now = datetime.datetime.now(datetime.UTC).isoformat()

    snapshot = {
        "snapshot_id": snapshot_id,
        "library_version": library.version,
        "label": label or f"v{library.version} — {now[:10]}",
        "created_at": now,
        "library": {
            "name": library.name,
            "description": library.description,
            "category": library.category.value,
            "language": library.language,
            "is_single_voice": library.is_single_voice,
            "quality_tier": library.quality_tier,
        },
        "samples": [
            {
                "title": s.title,
                "content": s.content,
                "author": s.author,
                "language": s.language,
                "quality_tier": s.quality_tier.value if s.quality_tier else None,
            }
            for s in samples
        ],
        "sample_count": len(samples),
    }

    # Store snapshot + update index
    client = redis_cache.client
    await client.setex(_snapshot_key(library_id, snapshot_id), _SNAPSHOT_TTL, json.dumps(snapshot))

    index_raw = await client.get(_snapshot_index_key(library_id))
    index: list[dict[str, Any]] = json.loads(index_raw) if index_raw else []
    index.append({
        "snapshot_id": snapshot_id,
        "label": snapshot["label"],
        "library_version": library.version,
        "sample_count": len(samples),
        "created_at": now,
    })
    await client.setex(_snapshot_index_key(library_id), _SNAPSHOT_TTL, json.dumps(index))

    return {"snapshot_id": snapshot_id, "label": snapshot["label"], "sample_count": len(samples)}


@router.get("/{library_id}/snapshots")
async def list_snapshots(
    library_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[dict[str, Any]]:
    """List all saved snapshots for a library."""
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    index_raw = await redis_cache.client.get(_snapshot_index_key(library_id))
    return json.loads(index_raw) if index_raw else []


@router.post("/{library_id}/snapshots/{snapshot_id}/restore")
async def restore_snapshot(
    library_id: uuid.UUID,
    snapshot_id: str,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Restore library samples from a snapshot.

    Deletes all current samples and replaces them with the snapshot contents.
    Library metadata (name, language) is updated to match the snapshot.
    The library version is incremented.
    """
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    raw = await redis_cache.client.get(_snapshot_key(library_id, snapshot_id))
    if not raw:
        raise HTTPException(status_code=404, detail="Snapshot not found or expired")

    snapshot = json.loads(raw)

    # Delete existing samples
    existing = await session.execute(
        select(StyleSample).where(StyleSample.library_id == library_id)
    )
    for s in existing.scalars().all():
        await session.delete(s)

    # Restore samples from snapshot
    restored = 0
    for s in snapshot.get("samples", []):
        content = s.get("content", "")
        if not content:
            continue
        tier = quality_tiering_service.tier_sample(content)
        session.add(StyleSample(
            library_id=library_id,
            title=s.get("title"),
            content=content,
            author=s.get("author"),
            language=s.get("language", library.language),
            quality_tier=tier,
        ))
        restored += 1

    # Bump version
    library.version = library.version + 1
    await session.commit()
    await _refresh_library_quality(library_id, session)

    return {
        "library_id": str(library_id),
        "restored_from": snapshot_id,
        "restored_samples": restored,
        "new_version": library.version,
    }


# ---------------------------------------------------------------------------
# T2.3 — Fluency Win Rate
# ---------------------------------------------------------------------------


@router.get("/{library_id}/fluency-win-rate")
async def get_fluency_win_rate(
    library_id: uuid.UUID,
    max_samples: int = 20,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Compute fluency win rate for a library.

    Win rate = fraction of pairwise comparisons where the library sample has
    lower perplexity (higher fluency) than a randomly shuffled version of itself.

    A well-formed library should have win_rate ≥ 0.6 (samples are more fluent
    than their shuffled counterparts, indicating natural sentence order and
    coherent language).

    This is a lightweight proxy for the full LLM-judge pairwise comparison
    (which is reserved for individual variant evaluation).
    """
    library = await session.get(StyleLibrary, library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    _check_library_access(library, ctx)

    result = await session.execute(
        select(StyleSample)
        .where(StyleSample.library_id == library_id)
        .limit(max_samples)
    )
    samples = result.scalars().all()

    if not samples:
        return {
            "library_id": str(library_id),
            "win_rate": None,
            "sample_count": 0,
            "detail": "No samples available",
        }

    try:
        import math
        import random

        import torch
        from transformers import GPT2LMHeadModel, GPT2Tokenizer

        from infrastructure.config import settings

        tokenizer = GPT2Tokenizer.from_pretrained(settings.perplexity_model)
        model = GPT2LMHeadModel.from_pretrained(settings.perplexity_model)
        model.eval()

        def _perplexity(text: str) -> float:
            tokens = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
            with torch.no_grad():
                loss = model(**tokens, labels=tokens["input_ids"]).loss
            return math.exp(loss.item())

        def _shuffle_sentences(text: str) -> str:
            import re
            sents = re.split(r"(?<=[.!?])\s+", text.strip())
            if len(sents) <= 1:
                return text
            random.Random(0).shuffle(sents)
            return " ".join(sents)

        wins = 0
        total = 0
        details: list[dict[str, Any]] = []

        for s in samples:
            if not s.content or len(s.content.split()) < 5:
                continue
            try:
                ppl_orig = _perplexity(s.content)
                ppl_shuffled = _perplexity(_shuffle_sentences(s.content))
                won = ppl_orig < ppl_shuffled
                wins += int(won)
                total += 1
                details.append({
                    "sample_id": str(s.id),
                    "perplexity_original": round(ppl_orig, 2),
                    "perplexity_shuffled": round(ppl_shuffled, 2),
                    "won": won,
                })
            except Exception:
                continue

        win_rate = wins / total if total > 0 else None
        return {
            "library_id": str(library_id),
            "win_rate": round(win_rate, 4) if win_rate is not None else None,
            "wins": wins,
            "total_compared": total,
            "sample_count": len(samples),
            "details": details,
        }
    except Exception as exc:
        return {
            "library_id": str(library_id),
            "win_rate": None,
            "error": str(exc),
        }
