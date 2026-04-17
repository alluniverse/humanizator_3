"""Backend-for-Frontend: Human-in-the-Loop review endpoint.

Single aggregated endpoint that bundles everything a human reviewer needs:
  - task metadata + original text
  - all rewrite variants
  - hallucination check per variant
  - absolute quality metrics (from stored evaluation reports or inline)
  - style conflict summary (library health)
  - reviewer action: approve / reject / request_revision
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.tenant import TenantContext, get_current_tenant
from application.services.hallucination_detector import hallucination_detector
from infrastructure.db.models import (
    EvaluationReport,
    RewriteTask,
    RewriteVariant,
    StyleLibrary,
)
from infrastructure.db.session import get_async_session

router = APIRouter(prefix="/hitl", tags=["hitl"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ReviewAction(BaseModel):
    variant_id: uuid.UUID
    action: str  # "approve" | "reject" | "request_revision"
    comment: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/{task_id}")
async def get_review_bundle(
    task_id: uuid.UUID,
    run_hallucination_check: bool = True,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Return the full review bundle for a rewrite task.

    Aggregates: task metadata, original text, all variants with stored scores,
    hallucination checks per variant, and existing evaluation reports.
    """
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if ctx.user_id is not None and task.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    library = await session.get(StyleLibrary, task.library_id)

    # Load variants
    variants_result = await session.execute(
        select(RewriteVariant).where(RewriteVariant.task_id == task_id)
    )
    variants = variants_result.scalars().all()

    # Load evaluation reports (keyed by variant_id)
    reports_result = await session.execute(
        select(EvaluationReport).where(EvaluationReport.task_id == task_id)
    )
    reports = {str(r.variant_id): r for r in reports_result.scalars().all()}

    # Build variant bundles
    variant_bundles: list[dict[str, Any]] = []
    for v in variants:
        bundle: dict[str, Any] = {
            "id": str(v.id),
            "mode": v.mode.value,
            "text": v.final_text,
            "is_valid": v.is_valid,
            "scores": {
                "style_match": v.style_match_score,
                "semantic_preservation": v.semantic_preservation_score,
                "perplexity": v.perplexity_score,
                "burstiness": v.burstiness_score,
                "fluency_win_rate": v.fluency_win_rate,
            },
        }

        # Attach evaluation report if available
        report = reports.get(str(v.id))
        if report:
            bundle["evaluation"] = {
                "absolute_metrics": report.absolute_metrics,
                "judge_scores": report.judge_scores,
                "contract_violations": report.contract_violations,
                "warnings": report.warnings,
                "composite_score": report.composite_score,
            }

        # Run inline hallucination check if requested
        if run_hallucination_check and v.final_text:
            try:
                bundle["hallucination_check"] = hallucination_detector.detect(
                    original=task.original_text,
                    rewritten=v.final_text,
                )
            except Exception as exc:
                bundle["hallucination_check"] = {"error": str(exc)}

        variant_bundles.append(bundle)

    return {
        "task": {
            "id": str(task.id),
            "status": task.status.value,
            "rewrite_mode": task.rewrite_mode.value,
            "semantic_contract_mode": task.semantic_contract_mode.value,
            "created_at": task.created_at.isoformat(),
            "updated_at": task.updated_at.isoformat(),
        },
        "original_text": task.original_text,
        "library": {
            "id": str(library.id) if library else None,
            "name": library.name if library else None,
            "language": library.language if library else None,
            "quality_tier": library.quality_tier if library else None,
        },
        "variants": variant_bundles,
        "variants_count": len(variant_bundles),
    }


@router.post("/{task_id}/review")
async def submit_review(
    task_id: uuid.UUID,
    action: ReviewAction,
    session: AsyncSession = Depends(get_async_session),
    ctx: TenantContext = Depends(get_current_tenant),
) -> dict[str, Any]:
    """Submit a reviewer decision for a specific variant.

    Marks the variant as approved/rejected and stores the comment in explanation.
    """
    task = await session.get(RewriteTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if ctx.user_id is not None and task.user_id != ctx.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    variant = await session.get(RewriteVariant, action.variant_id)
    if not variant or variant.task_id != task_id:
        raise HTTPException(status_code=404, detail="Variant not found")

    allowed = {"approve", "reject", "request_revision"}
    if action.action not in allowed:
        raise HTTPException(status_code=422, detail=f"action must be one of {allowed}")

    variant.is_valid = action.action == "approve"
    if action.comment:
        variant.explanation = f"[{action.action.upper()}] {action.comment}"
    await session.commit()

    return {
        "task_id": str(task_id),
        "variant_id": str(action.variant_id),
        "action": action.action,
        "is_valid": variant.is_valid,
    }
