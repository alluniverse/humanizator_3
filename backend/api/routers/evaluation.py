"""REST API router for Evaluation and Human-in-the-Loop support."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from application.services.evaluation_engine import evaluation_engine
from application.services.grammar_layer import grammar_layer
from application.services.holistic_ranker import holistic_ranker
from application.services.structural_polishing import structural_polishing
from application.services.style_guidance import style_guidance_engine
from application.services.word_importance import word_importance_scorer
from constraints.rewrite_constraints import rewrite_constraint_layer
from infrastructure.db.models import RewriteTask, StyleLibrary, StyleProfile
from infrastructure.db.session import get_async_session

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/{task_id}/word-importance")
async def get_word_importance(
    task_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    scores = word_importance_scorer.score_text(task.original_text)
    return {"task_id": str(task_id), "scores": scores}


@router.post("/{task_id}/holistic-rank")
async def get_holistic_rank(
    task_id: uuid.UUID,
    target_index: int,
    candidates: list[str],
    mode: str = "fast",
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    # Simple sentence split for MVP
    sentences = task.original_text.split(". ")
    sentence = sentences[0] if sentences else task.original_text
    ranked = holistic_ranker.rank_substitutions(sentence, target_index, candidates, mode=mode)
    return {"task_id": str(task_id), "ranked": ranked}


@router.post("/{task_id}/validate-constraints")
async def validate_constraints(
    task_id: uuid.UUID,
    rewritten_text: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    from application.services.semantic_contract import semantic_contract_builder
    from infrastructure.db.models import StyleLibrary

    library = await session.get(StyleLibrary, task.library_id)
    contract = semantic_contract_builder.build_contract(
        task.original_text,
        mode=task.semantic_contract_mode.value,
        language=library.language if library else "ru",
    )
    result = rewrite_constraint_layer.validate_all(
        task.original_text,
        rewritten_text,
        contract,
        language=library.language if library else "ru",
    )
    return {"task_id": str(task_id), "validation": result}


@router.post("/{task_id}/style-guidance")
async def run_style_guidance(
    task_id: uuid.UUID,
    variants: list[dict[str, Any]],
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
    style_profile = profile.guidance_signals or {} if profile else {}

    library = await session.get(StyleLibrary, task.library_id)
    ranked = style_guidance_engine.rank_variants(
        variants,
        style_profile,
        task.original_text,
        language=library.language if library else "ru",
    )
    return {"task_id": str(task_id), "ranked_variants": ranked}


@router.post("/{task_id}/polish")
async def polish_text(
    task_id: uuid.UUID,
    text: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    library = await session.get(StyleLibrary, task.library_id)
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
            "guidance_signals": profile.guidance_signals,
        }

    polished = structural_polishing.polish(
        text,
        style_profile=style_profile,
        language=library.language if library else "ru",
    )
    grammar = grammar_layer.check(polished["polished_text"], language=library.language if library else "ru")
    return {
        "task_id": str(task_id),
        "polished": polished,
        "grammar": grammar,
    }


@router.post("/{task_id}/absolute-metrics")
async def get_absolute_metrics(
    task_id: uuid.UUID,
    variant_text: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    library = await session.get(StyleLibrary, task.library_id)
    metrics = evaluation_engine.absolute_metrics(
        task.original_text,
        variant_text,
        language=library.language if library else "ru",
    )
    return {"task_id": str(task_id), "metrics": metrics}


@router.post("/{task_id}/judge-evaluation")
async def get_judge_evaluation(
    task_id: uuid.UUID,
    variant_text: str,
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
            "guidance_signals": profile.guidance_signals,
        }

    result = await evaluation_engine.judge_evaluation(
        task.original_text,
        variant_text,
        style_profile=style_profile,
    )
    return {"task_id": str(task_id), "judge": result}


@router.post("/{task_id}/pairwise")
async def get_pairwise(
    task_id: uuid.UUID,
    variant_a: str,
    variant_b: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    result = await evaluation_engine.pairwise_comparison(
        variant_a,
        variant_b,
        task.original_text,
    )
    return {"task_id": str(task_id), "pairwise": result}
