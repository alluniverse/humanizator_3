"""Celery tasks for the rewrite pipeline.

State machine: created → analyzing → rewriting → evaluating → completed/failed

Each stage is a separate Celery task, chained via Celery canvas.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import chain
from sqlalchemy import select

from async_tasks.celery_app import celery_app
from domain.enums import QualityTier, RewriteTaskStatus

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async coroutine in a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        try:
            from infrastructure.db.session import async_engine

            loop.run_until_complete(async_engine.dispose())
        except Exception:
            logger.debug("Failed to dispose async engine after Celery task", exc_info=True)
        loop.close()


async def _run_stage(coro, task_id: str, stage: str) -> dict[str, Any]:
    try:
        return await coro
    except Exception as exc:
        await _mark_failed(task_id, f"{stage}: {exc}")
        raise


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_rewrite_task(self, task_id: str) -> dict[str, Any]:
    """Orchestrate the full rewrite pipeline via Celery chain."""
    logger.info("Starting rewrite pipeline for task %s", task_id)
    try:
        pipeline = chain(
            stage_analyze.s(task_id),
            stage_rewrite.s(),
            stage_evaluate.s(),
            stage_complete.s(),
        )
        result = pipeline.apply_async()
        return {"task_id": task_id, "pipeline_id": str(result.id)}
    except Exception as exc:
        logger.exception("Failed to start pipeline for task %s", task_id)
        _run_async(_mark_failed(task_id, str(exc)))
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=5)
def stage_analyze(self, task_id: str) -> dict[str, Any]:
    """Stage 1: Analyze input + build semantic contract."""
    logger.info("[analyze] task=%s", task_id)
    try:
        return _run_async(_run_stage(_do_analyze(task_id), task_id, "analyze"))
    except Exception as exc:
        logger.exception("[analyze] failed task=%s", task_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=15)
def stage_rewrite(self, context: dict[str, Any]) -> dict[str, Any]:
    """Stage 2: Generate rewrite variants."""
    task_id = context["task_id"]
    logger.info("[rewrite] task=%s", task_id)
    try:
        return _run_async(_run_stage(_do_rewrite(context), task_id, "rewrite"))
    except Exception as exc:
        logger.exception("[rewrite] failed task=%s", task_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=10)
def stage_evaluate(self, context: dict[str, Any]) -> dict[str, Any]:
    """Stage 3: Evaluate and rank variants."""
    task_id = context["task_id"]
    logger.info("[evaluate] task=%s", task_id)
    try:
        return _run_async(_run_stage(_do_evaluate(context), task_id, "evaluate"))
    except Exception as exc:
        logger.exception("[evaluate] failed task=%s", task_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def stage_complete(self, context: dict[str, Any]) -> dict[str, Any]:
    """Stage 4: Persist variants and mark task completed."""
    task_id = context["task_id"]
    logger.info("[complete] task=%s", task_id)
    try:
        return _run_async(_run_stage(_do_complete(context), task_id, "complete"))
    except Exception as exc:
        logger.exception("[complete] failed task=%s", task_id)
        raise


# ---------------------------------------------------------------------------
# Async implementation helpers
# ---------------------------------------------------------------------------


async def _mark_failed(task_id: str, reason: str) -> None:
    from infrastructure.db.models import RewriteTask
    from infrastructure.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if task:
            task.status = RewriteTaskStatus.FAILED
            task.error_message = reason[:1000]
            await session.commit()


async def _do_analyze(task_id: str) -> dict[str, Any]:
    from application.services.input_analyzer import input_analyzer
    from application.services.semantic_contract import semantic_contract_builder
    from application.services.word_importance import WordImportanceScorer
    from infrastructure.db.models import RewriteTask, StyleLibrary, StyleProfile
    from infrastructure.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = RewriteTaskStatus.ANALYZING
        await session.commit()

        library = await session.get(StyleLibrary, task.library_id)
        language = library.language if library else "ru"

        profile_result = await session.execute(
            select(StyleProfile)
            .where(StyleProfile.library_id == task.library_id)
            .order_by(StyleProfile.created_at.desc())
            .limit(1)
        )
        profile = profile_result.scalar_one_or_none()
        style_profile_dict: dict[str, Any] | None = None
        if profile:
            style_profile_dict = {
                "target_perplexity_min": profile.target_perplexity_min,
                "target_perplexity_max": profile.target_perplexity_max,
                "guidance_signals": profile.guidance_signals,
                "lexical_signature": profile.lexical_signature,
                "burstiness_index": profile.burstiness_index,
            }

        original_text = task.original_text
        contract_mode = task.semantic_contract_mode.value
        rewrite_mode = task.rewrite_mode.value
        user_instruction = (task.input_constraints or {}).get("user_instruction")

    input_analysis = input_analyzer.analyze(
        original_text,
        language=language,
        style_profile=style_profile_dict,
    )

    contract = semantic_contract_builder.build_contract(
        original_text,
        mode=contract_mode,
        language=language,
    )

    try:
        scorer = WordImportanceScorer()
        importance_scores = scorer.score_text(original_text)
    except Exception as exc:
        logger.warning("Word importance scoring failed: %s", exc)
        importance_scores = []

    return {
        "task_id": task_id,
        "language": language,
        "style_profile": style_profile_dict,
        "input_analysis": input_analysis,
        "contract": contract,
        "importance_scores": importance_scores,
        "original_text": original_text,
        "rewrite_mode": rewrite_mode,
        "user_instruction": user_instruction,
    }


async def _do_rewrite(context: dict[str, Any]) -> dict[str, Any]:
    from application.services.style_guidance import style_guidance_engine
    from constraints.rewrite_constraints import RewriteConstraintLayer
    from infrastructure.db.models import RewriteTask, StyleSample
    from infrastructure.db.session import AsyncSessionLocal
    from rewrite.guided_rewrite import guided_rewrite_engine

    task_id = context["task_id"]
    language = context["language"]
    style_profile = context.get("style_profile")
    contract = context["contract"]
    original_text = context["original_text"]
    user_instruction = context.get("user_instruction")

    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        task.status = RewriteTaskStatus.REWRITING
        await session.commit()

        # Load L1 reference samples for Mimicking mode
        sample_result = await session.execute(
            select(StyleSample)
            .where(StyleSample.library_id == task.library_id)
            .where(StyleSample.quality_tier == QualityTier.L1)
            .limit(3)
        )
        l1_samples = [s.content for s in sample_result.scalars().all()]
        if not l1_samples:
            fallback = await session.execute(
                select(StyleSample)
                .where(StyleSample.library_id == task.library_id)
                .limit(3)
            )
            l1_samples = [s.content for s in fallback.scalars().all()]

    mode = context.get("rewrite_mode", "balanced")
    raw_variants = [
        await guided_rewrite_engine.rewrite(
            original_text,
            mode=mode,
            style_profile=style_profile,
            contract=contract,
            reference_samples=l1_samples or None,
            user_instruction=user_instruction,
        )
    ]

    # Validate constraints (POS + MPR + USE)
    constraint_layer = RewriteConstraintLayer()
    validated_variants: list[dict[str, Any]] = []
    for variant in raw_variants:
        validation = constraint_layer.validate_all(
            original=original_text,
            rewritten=variant["text"],
            contract=contract,
            language=language,
        )
        variant["constraint_validation"] = validation
        validated_variants.append(variant)

    # Score by style guidance
    if style_profile:
        for v in validated_variants:
            try:
                score = style_guidance_engine.score_variant(
                    v["text"],
                    style_profile=style_profile,
                    original_text=original_text,
                    language=language,
                )
                v["guidance_score"] = score
            except Exception as exc:
                logger.warning("Style guidance scoring failed: %s", exc)
                v["guidance_score"] = {}

    return {**context, "variants": validated_variants}


async def _do_evaluate(context: dict[str, Any]) -> dict[str, Any]:
    from application.services.evaluation_engine import evaluation_engine
    from application.services.holistic_ranker import holistic_ranker
    from infrastructure.db.models import RewriteTask
    from infrastructure.db.session import AsyncSessionLocal

    task_id = context["task_id"]
    language = context["language"]
    original_text = context["original_text"]
    variants = context.get("variants", [])

    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.status = RewriteTaskStatus.EVALUATING
        await session.commit()

    variant_texts = [v["text"] for v in variants]
    evaluated: list[dict[str, Any]] = []

    for i, variant in enumerate(variants):
        try:
            metrics = evaluation_engine.absolute_metrics(
                original_text,
                variant["text"],
                language=language,
            )
        except Exception as exc:
            logger.warning("Evaluation metrics failed: %s", exc)
            metrics = {}

        try:
            ranking = holistic_ranker.rank(
                candidates=variant_texts,
                target_index=i,
                mode="fast",
            )
        except Exception as exc:
            logger.warning("Holistic ranking failed: %s", exc)
            ranking = {}

        evaluated.append({
            **variant,
            "metrics": metrics,
            "holistic_ranking": ranking,
        })

    return {**context, "variants": evaluated}


async def _do_complete(context: dict[str, Any]) -> dict[str, Any]:
    from infrastructure.db.models import EvaluationReport, RewriteTask, RewriteVariant
    from infrastructure.db.session import AsyncSessionLocal

    task_id = context["task_id"]
    variants = context.get("variants", [])

    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")

        saved_variant_ids: list[str] = []
        for v in variants:
            metrics = v.get("metrics", {})
            rv = RewriteVariant(
                task_id=task.id,
                mode=v["mode"],
                final_text=v["text"],
                style_match_score=v.get("guidance_score", {}).get("style_match"),
                semantic_preservation_score=metrics.get("bertscore_f1"),
                perplexity_score=metrics.get("perplexity"),
                burstiness_score=metrics.get("burstiness"),
                explanation=str(v.get("guidance_score", {})),
                intermediate_scores={
                    "constraint_validation": v.get("constraint_validation", {}),
                    "holistic_ranking": v.get("holistic_ranking", {}),
                    "usage": v.get("usage", {}),
                },
                is_valid=v.get("constraint_validation", {}).get("valid", True),
            )
            session.add(rv)
            await session.flush()
            saved_variant_ids.append(str(rv.id))

        if saved_variant_ids:
            all_metrics = [v.get("metrics", {}) for v in variants]
            valid_bertscore = [m.get("bertscore_f1", 0.0) for m in all_metrics if m.get("bertscore_f1")]
            avg_bertscore = sum(valid_bertscore) / len(valid_bertscore) if valid_bertscore else 0.0

            report = EvaluationReport(
                task_id=task.id,
                absolute_metrics={
                    "avg_bertscore_f1": round(avg_bertscore, 3),
                    "variants_count": len(variants),
                    "variants_valid": sum(
                        1 for v in variants
                        if v.get("constraint_validation", {}).get("valid", True)
                    ),
                },
                composite_score=round(avg_bertscore, 3),
                warnings=_collect_warnings(variants),
                recommendations=_collect_recommendations(variants),
            )
            session.add(report)

        task.status = RewriteTaskStatus.COMPLETED
        await session.commit()

    return {
        "task_id": task_id,
        "status": "completed",
        "variants_saved": len(saved_variant_ids),
    }


def _collect_warnings(variants: list[dict[str, Any]]) -> list[str]:
    warnings: list[str] = []
    for v in variants:
        validation = v.get("constraint_validation", {})
        if not validation.get("valid", True):
            for viol in validation.get("violations", []):
                warnings.append(f"[{v['mode']}] {viol}")
    return warnings


def _collect_recommendations(variants: list[dict[str, Any]]) -> list[str]:
    recs: list[str] = []
    for v in variants:
        metrics = v.get("metrics", {})
        ppl = metrics.get("perplexity", 0)
        if 0 < ppl < 10:
            recs.append(
                f"[{v['mode']}] Perplexity {ppl:.1f} < 10 — текст слишком предсказуемый, "
                "увеличьте burstiness или глубину трансформации."
            )
        bertscore = metrics.get("bertscore_f1", 1.0)
        if 0 < bertscore < 0.85:
            recs.append(
                f"[{v['mode']}] BERTScore F1 {bertscore:.3f} < 0.85 — возможна потеря смысла, "
                "попробуйте strict semantic contract."
            )
    return recs
