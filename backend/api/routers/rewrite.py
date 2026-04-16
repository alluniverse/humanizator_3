"""REST API router for Rewrite Tasks."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.rewrite import (
    RewriteTaskCreate,
    RewriteTaskRead,
    SemanticContractRead,
)
from application.services.input_analyzer import input_analyzer
from application.services.semantic_contract import semantic_contract_builder
from domain.enums import RewriteTaskStatus
from infrastructure.db.models import RewriteTask, StyleLibrary, StyleProfile, StyleSample
from infrastructure.db.session import get_async_session
from rewrite.guided_rewrite import guided_rewrite_engine

router = APIRouter(prefix="/rewrite", tags=["rewrite"])


@router.post("", response_model=RewriteTaskRead, status_code=status.HTTP_201_CREATED)
async def create_rewrite_task(
    data: RewriteTaskCreate,
    session: AsyncSession = Depends(get_async_session),
) -> RewriteTask:
    library = await session.get(StyleLibrary, data.library_id)
    if not library:
        raise HTTPException(status_code=404, detail="Library not found")

    task = RewriteTask(
        project_id=data.project_id,
        library_id=data.library_id,
        original_text=data.original_text,
        rewrite_mode=data.rewrite_mode,
        semantic_contract_mode=data.semantic_contract_mode,
        input_constraints=data.input_constraints,
        status=RewriteTaskStatus.CREATED,
        user_id=None,
    )
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return task


@router.get("/{task_id}", response_model=RewriteTaskRead)
async def get_rewrite_task(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> RewriteTask:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


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


@router.post("/{task_id}/generate")
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
