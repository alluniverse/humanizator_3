"""REST API router for Rewrite Tasks."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.tenant import TenantContext, get_current_tenant, require_existing_user
from api.rate_limiter import rate_limit_requests, rate_limit_rewrite
from api.schemas.rewrite import (
    RewriteTaskCreate,
    RewriteTaskRead,
    RewriteVariantRead,
    SemanticContractRead,
)
from application.services.input_analyzer import input_analyzer
from application.services.semantic_contract import semantic_contract_builder
from async_tasks.rewrite_tasks import process_rewrite_task
from domain.enums import RewriteTaskStatus
from infrastructure.db.models import Project, RewriteTask, RewriteVariant, StyleLibrary, StyleProfile, StyleSample
from infrastructure.db.session import get_async_session
from rewrite.guided_rewrite import guided_rewrite_engine

router = APIRouter(prefix="/rewrite", tags=["rewrite"])


async def _get_or_create_default_project(user_id: uuid.UUID, session: AsyncSession) -> uuid.UUID:
    """Return the user's default project, creating it on first use."""
    result = await session.execute(
        select(Project).where(Project.owner_id == user_id).limit(1)
    )
    project = result.scalar_one_or_none()
    if project is None:
        project = Project(name="Default", owner_id=user_id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
    return project.id


@router.post(
    "",
    response_model=RewriteTaskRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_requests), Depends(rate_limit_rewrite)],
)
async def create_rewrite_task(
    data: RewriteTaskCreate,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(require_existing_user),
) -> RewriteTask:
    library = await session.get(StyleLibrary, data.library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")
    # Verify tenant owns the library (if authenticated)
    if ctx.user_id is not None and library.owner_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    project_id = data.project_id or ctx.project_id
    if project_id is None and ctx.user_id is not None:
        project_id = await _get_or_create_default_project(ctx.user_id, session)

    task = RewriteTask(
        project_id=project_id,
        library_id=data.library_id,
        original_text=data.original_text,
        rewrite_mode=data.rewrite_mode,
        semantic_contract_mode=data.semantic_contract_mode,
        input_constraints=data.input_constraints,
        status=RewriteTaskStatus.CREATED,
        user_id=ctx.user_id,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("", response_model=list[RewriteTaskRead])
async def list_rewrite_tasks(
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[RewriteTask]:
    query = select(RewriteTask).order_by(RewriteTask.created_at.desc())
    if ctx.user_id is not None:
        query = query.where(RewriteTask.user_id == ctx.user_id)
    result = await session.execute(query)
    return list(result.scalars().all())


@router.get("/{task_id}", response_model=RewriteTaskRead)
async def get_rewrite_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> RewriteTask:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if ctx.user_id is not None and task.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    return task


@router.post("/{task_id}/run", dependencies=[Depends(rate_limit_requests), Depends(rate_limit_rewrite)])
async def run_rewrite_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if ctx.user_id is not None and task.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    if task.status in {
        RewriteTaskStatus.ANALYZING,
        RewriteTaskStatus.REWRITING,
        RewriteTaskStatus.EVALUATING,
    }:
        return {"task_id": str(task.id), "status": task.status.value, "queued": False}

    task.status = RewriteTaskStatus.ANALYZING
    task.error_message = None
    await session.commit()

    try:
        result = process_rewrite_task.delay(str(task.id))
    except Exception as exc:
        task.status = RewriteTaskStatus.FAILED
        task.error_message = f"Failed to enqueue rewrite pipeline: {exc}"[:1000]
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rewrite worker is unavailable. Start Redis and Celery worker, then retry.",
        ) from exc

    return {
        "task_id": str(task.id),
        "status": task.status.value,
        "queued": True,
        "celery_task_id": str(result.id),
    }


@router.get("/{task_id}/variants", response_model=list[RewriteVariantRead])
async def list_rewrite_variants(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> list[RewriteVariantRead]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if ctx.user_id is not None and task.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    result = await session.execute(
        select(RewriteVariant)
        .where(RewriteVariant.task_id == task_id)
        .order_by(RewriteVariant.created_at.asc())
    )
    variants = result.scalars().all()
    return [
        RewriteVariantRead(
            id=variant.id,
            mode=variant.mode,
            rewritten_text=variant.final_text,
            variant_index=index,
            review_status="approved" if variant.is_valid else "rejected",
            scores={
                "style_match": variant.style_match_score,
                "semantic_similarity": variant.semantic_preservation_score,
                "perplexity": variant.perplexity_score,
                "burstiness": variant.burstiness_score,
                "fluency": variant.fluency_win_rate,
            },
            is_valid=variant.is_valid,
            created_at=variant.created_at,
        )
        for index, variant in enumerate(variants, start=1)
    ]


@router.post("/{task_id}/analyze-input")
async def analyze_input(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    profile_result = await session.execute(
        select(StyleProfile)
        .where(StyleProfile.library_id == task.library_id)
        .order_by(StyleProfile.created_at.desc())
        .limit(1)
    )
    profile = profile_result.scalar_one_or_none()
    style_profile = None
    if profile:
        style_profile = {
            "target_perplexity_min": profile.target_perplexity_min,
            "target_perplexity_max": profile.target_perplexity_max,
        }

    library = await session.get(StyleLibrary, task.library_id)
    analysis = input_analyzer.analyze(
        task.original_text,
        language=library.language if library else "ru",
        style_profile=style_profile,
    )
    return analysis


@router.post("/{task_id}/semantic-contract", response_model=SemanticContractRead)
async def build_semantic_contract(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> SemanticContractRead:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    library = await session.get(StyleLibrary, task.library_id)
    contract = semantic_contract_builder.build_contract(
        task.original_text,
        mode=task.semantic_contract_mode.value,
        language=library.language if library else "ru",
    )
    return SemanticContractRead(**contract)


@router.post("/{task_id}/generate", dependencies=[Depends(rate_limit_requests), Depends(rate_limit_rewrite)])
async def generate_variants(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    library = await session.get(StyleLibrary, task.library_id)
    language = library.language if library else "ru"

    # Load latest style profile
    profile_result = await session.execute(
        select(StyleProfile)
        .where(StyleProfile.library_id == task.library_id)
        .order_by(StyleProfile.created_at.desc())
        .limit(1)
    )
    profile = profile_result.scalar_one_or_none()
    style_profile: dict[str, Any] | None = None
    if profile:
        style_profile = {
            "guidance_signals": profile.guidance_signals,
            "target_perplexity_min": profile.target_perplexity_min,
            "target_perplexity_max": profile.target_perplexity_max,
            "lexical_signature": profile.lexical_signature,
        }

    # Build contract
    contract = semantic_contract_builder.build_contract(
        task.original_text,
        mode=task.semantic_contract_mode.value,
        language=language,
    )

    # Pick reference samples (L1)
    sample_result = await session.execute(
        select(StyleSample)
        .where(StyleSample.library_id == task.library_id)
        .limit(3)
    )
    reference_samples = [s.content for s in sample_result.scalars().all()]

    variants = await guided_rewrite_engine.rewrite_all_modes(
        task.original_text,
        style_profile=style_profile,
        contract=contract,
        reference_samples=reference_samples or None,
    )

    task.status = RewriteTaskStatus.REWRITING
    await session.commit()

    return {
        "task_id": str(task_id),
        "variants": variants,
    }
