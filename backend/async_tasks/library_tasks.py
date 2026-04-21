"""Celery tasks for Style Library management.

Handles background processing of corpus quality tiering and style profile building.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from sqlalchemy import select

from async_tasks.celery_app import celery_app
from domain.enums import QualityTier

logger = logging.getLogger(__name__)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def build_library_profile(self, library_id: str) -> dict[str, Any]:
    """Background task: tier all samples and rebuild style profile for a library.

    Triggered after bulk sample import or manual profile recalculation.
    """
    logger.info("Building profile for library %s", library_id)
    try:
        return _run_async(_do_build_profile(library_id))
    except Exception as exc:
        logger.exception("Profile build failed for library %s", library_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def tier_sample(self, sample_id: str) -> dict[str, Any]:
    """Background task: classify a single sample into L1/L2/L3."""
    logger.info("Tiering sample %s", sample_id)
    try:
        return _run_async(_do_tier_sample(sample_id))
    except Exception as exc:
        logger.exception("Tiering failed for sample %s", sample_id)
        raise self.retry(exc=exc)


async def _do_tier_sample(sample_id: str) -> dict[str, Any]:
    from application.services.quality_tiering import QualityTieringService
    from infrastructure.db.models import StyleSample
    from infrastructure.db.session import AsyncSessionLocal

    service = QualityTieringService()

    async with AsyncSessionLocal() as session:
        sample = await session.get(StyleSample, sample_id)
        if not sample:
            raise ValueError(f"Sample {sample_id} not found")

        tier = service.tier_sample(sample.content)
        sample.quality_tier = tier
        await session.commit()

    return {"sample_id": sample_id, "tier": tier.value}


async def _do_build_profile(library_id: str) -> dict[str, Any]:
    from application.services.quality_tiering import QualityTieringService
    from application.services.style_profile import StyleProfileEngine
    from infrastructure.db.models import StyleLibrary, StyleProfile, StyleSample
    from infrastructure.db.session import AsyncSessionLocal

    tiering_service = QualityTieringService()
    profile_engine = StyleProfileEngine()

    async with AsyncSessionLocal() as session:
        library = await session.get(StyleLibrary, library_id)
        if not library:
            raise ValueError(f"Library {library_id} not found")

        # Load all samples
        result = await session.execute(
            select(StyleSample).where(StyleSample.library_id == library_id)
        )
        samples = result.scalars().all()

        if not samples:
            return {"library_id": library_id, "status": "no_samples"}

        # Tier any un-tiered samples
        l1_count = l2_count = l3_count = 0
        for sample in samples:
            if sample.quality_tier is None:
                sample.quality_tier = tiering_service.tier_sample(sample.content)
            if sample.quality_tier == QualityTier.L1:
                l1_count += 1
            elif sample.quality_tier == QualityTier.L2:
                l2_count += 1
            else:
                l3_count += 1

        await session.commit()

        # Build profile from L1 only (L2 as fallback if not enough L1)
        profile_samples = [
            {"content": s.content, "quality_tier": s.quality_tier.value}
            for s in samples
            if s.quality_tier in (QualityTier.L1, QualityTier.L2)
        ]
        if not profile_samples:
            profile_samples = [{"content": s.content, "quality_tier": "L3"} for s in samples]

        profile_data = profile_engine.build_profile(
            profile_samples,
            language=library.language,
        )

        # Determine library quality tier
        total = len(samples)
        if total > 0:
            l1_ratio = l1_count / total
            if l1_ratio >= 0.7:
                library_tier = "L1"
            elif l1_ratio >= 0.4:
                library_tier = "L2"
            else:
                library_tier = "L3"
            library.quality_tier = library_tier

        # Save or update style profile (new version)
        existing = await session.execute(
            select(StyleProfile)
            .where(StyleProfile.library_id == library_id)
            .order_by(StyleProfile.created_at.desc())
            .limit(1)
        )
        last_profile = existing.scalar_one_or_none()
        new_version = (last_profile.version + 1) if last_profile else 1

        sp = StyleProfile(
            library_id=library.id,
            version=new_version,
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
        session.add(sp)
        await session.commit()

    return {
        "library_id": library_id,
        "status": "completed",
        "samples_total": total,
        "l1": l1_count,
        "l2": l2_count,
        "l3": l3_count,
        "library_tier": library_tier,
        "profile_version": new_version,
    }
