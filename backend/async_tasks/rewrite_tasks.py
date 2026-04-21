"""Celery tasks for the rewrite pipeline.

State machine: created → analyzing → rewriting → evaluating → completed/failed

Each stage is a separate Celery task, chained via Celery canvas.
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
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


def _strip_hidden_chars(text: str) -> str:
    """Remove hidden/steganographic Unicode characters used for AI watermarking."""
    # NFKC normalization: converts math bold/italic Unicode variants → ASCII,
    # smart quotes → straight quotes, ligatures → base chars, etc.
    # This defeats watermarks embedded via Unicode compatibility equivalents.
    text = unicodedata.normalize('NFKC', text)
    # BOM + zero-width / directional markers
    text = re.sub(
        r'[\u200b\u200c\u200d\u200e\u200f\u00ad\ufeff\u2028\u2029'
        r'\u2060\u2061\u2062\u2063\u2064'   # word joiners, invisible operators
        r'\u180b\u180c\u180d'               # Mongolian free variation selectors
        r'\ufe00-\ufe0f]',                  # variation selectors VS1-VS16
        '', text,
    )
    # Tag characters block U+E0000-U+E007F (used for steganographic watermarking)
    text = re.sub(r'[\U000e0000-\U000e007f]', '', text)
    text = text.replace('\u00a0', ' ')
    # Strip all remaining Unicode control characters except normal whitespace
    text = ''.join(ch for ch in text if unicodedata.category(ch)[0] != 'C' or ch in '\n\t\r')
    return text


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def process_rewrite_task(self, task_id: str) -> dict[str, Any]:
    """Orchestrate the full rewrite pipeline via Celery chain."""
    logger.info("Starting rewrite pipeline for task %s", task_id)
    try:
        pipeline = chain(
            stage_analyze.s(task_id),
            stage_rewrite.s(),
            stage_evaluate.s(),
            stage_translate.s(),
            stage_adapt.s(),
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
    """Stage 2: Generate rewrite variants.

    Skipped for same-language humanization (e.g. UK→UK): the input is already
    in the target language so English rewrite stages add no value.
    """
    task_id = context["task_id"]
    if context.get("same_lang_mode"):
        logger.info("[rewrite] skipped — same_lang_mode task=%s", task_id)
        return context
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
    if context.get("same_lang_mode"):
        logger.info("[evaluate] skipped — same_lang_mode task=%s", task_id)
        return context
    logger.info("[evaluate] task=%s", task_id)
    try:
        return _run_async(_run_stage(_do_evaluate(context), task_id, "evaluate"))
    except Exception as exc:
        logger.exception("[evaluate] failed task=%s", task_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=15)
def stage_translate(self, context: dict[str, Any]) -> dict[str, Any]:
    """Stage 4a (optional): Translate rewritten text to target language."""
    task_id = context["task_id"]
    if not context.get("translation_target") and not context.get("same_lang_mode"):
        return context
    if context.get("same_lang_mode"):
        logger.info("[translate] skipped — same_lang_mode task=%s", task_id)
        return context
    logger.info("[translate] task=%s target=%s", task_id, context["translation_target"])
    try:
        return _run_async(_run_stage(_do_translate(context), task_id, "translate"))
    except Exception as exc:
        logger.exception("[translate] failed task=%s", task_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=15)
def stage_adapt(self, context: dict[str, Any]) -> dict[str, Any]:
    """Stage 4b: Direct rewrite to target language, or same-language humanization."""
    task_id = context["task_id"]
    if context.get("same_lang_mode"):
        logger.info("[adapt] same_lang_mode task=%s", task_id)
        try:
            return _run_async(_run_stage(_do_humanize_same_lang(context), task_id, "adapt"))
        except Exception as exc:
            logger.exception("[adapt] same_lang failed task=%s", task_id)
            raise self.retry(exc=exc)
    if not context.get("translation_target"):
        return context
    # translation_result may be absent if stage_translate was skipped —
    # _do_direct_rewrite handles this by working from the EN variants directly.
    logger.info("[adapt] task=%s", task_id)
    try:
        return _run_async(_run_stage(_do_direct_rewrite(context), task_id, "adapt"))
    except Exception as exc:
        logger.exception("[adapt] failed task=%s", task_id)
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=1)
def stage_complete(self, context: dict[str, Any]) -> dict[str, Any]:
    """Stage 5: Persist variants and mark task completed."""
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

        original_text = _strip_hidden_chars(task.original_text)
        contract_mode = task.semantic_contract_mode.value
        rewrite_mode = task.rewrite_mode.value
        constraints = task.input_constraints or {}
        user_instruction = constraints.get("user_instruction")
        translation_target = constraints.get("translation_target") or None

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

    # same_lang_mode: input is already in the library/target language (e.g. UK→UK).
    # Skip EN rewrite stages and go straight to humanization in that language.
    same_lang_mode = (not translation_target) and (language not in ("en", "ru"))

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
        "translation_target": translation_target,
        "same_lang_mode": same_lang_mode,
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


async def _do_translate(context: dict[str, Any]) -> dict[str, Any]:
    """Legacy: kept for pipeline compatibility — direct rewrite now handled in stage_adapt."""
    return context


def _protect_proper_nouns(text: str) -> tuple[str, dict[str, str]]:
    """Replace proper nouns and named entities with stable placeholders.

    Protects: English words/phrases in Ukrainian text, sequences of Title-case
    words, known brand/org patterns. Returns (protected_text, placeholder_map).
    """
    placeholders: dict[str, str] = {}
    counter = [0]

    def _ph() -> str:
        token = f"⟨P{counter[0]}⟩"
        counter[0] += 1
        return token

    # English words / mixed Latin sequences (e.g. "Castle Mills", "York BID")
    def _replace_latin(m: re.Match) -> str:
        val = m.group(0)
        ph = _ph()
        placeholders[ph] = val
        return ph

    protected = re.sub(r'[A-Za-z][A-Za-z0-9\s\-&\']*[A-Za-z0-9](?:\s+[A-Za-z][A-Za-z0-9\-&\']*)*', _replace_latin, text)

    # Ukrainian Title-Case sequences (≥2 consecutive capitalised words not at sentence start)
    # e.g. "Роб Стотерт", "Йорк BID"
    def _replace_uk_proper(m: re.Match) -> str:
        val = m.group(0)
        ph = _ph()
        placeholders[ph] = val
        return ph

    # Two or more Ukrainian capitalised tokens in a row
    protected = re.sub(
        r'(?<![.!?\n])\b([А-ЯЇІЄІ][а-яїієі\']+(?:\s+[А-ЯЇІЄІ][а-яїієі\']+)+)',
        _replace_uk_proper,
        protected,
    )

    return protected, placeholders


def _restore_proper_nouns(text: str, placeholders: dict[str, str]) -> str:
    """Restore placeholders back to original proper nouns."""
    for ph, val in placeholders.items():
        text = text.replace(ph, val)
    # Clean up any leftover malformed placeholders
    text = re.sub(r'⟨P\d+⟩', '', text)
    return text


async def _do_humanize_same_lang(context: dict[str, Any]) -> dict[str, Any]:
    """Humanize text that is already in the target language (e.g. UK→UK).

    Steps:
      1. Load library samples + extract style elements.
      2. Protect proper nouns with placeholders.
      3. lang→zh-CN→lang chain to break LLM statistical patterns.
      4. Restore proper nouns.
      5. LLM polish pass with style injection — fix remaining AI markers,
         inject human-like phrasing from the library.
      6. Cleanup pass for chain artifacts.
    """
    from adapters.llm import get_default_provider
    from application.services.ukrainian_extractor import build_style_injection, extract_style_elements
    from infrastructure.db.models import RewriteTask, StyleSample
    from infrastructure.db.session import AsyncSessionLocal
    from rewrite.multilingual_chain import apply_chain
    from rewrite.prompts import _AI_MARKER_BLOCK_UK, _RESTRUCTURE_BLOCK

    task_id = context["task_id"]
    lang = context["language"]  # "uk", "pl", etc.
    original_text = context["original_text"]

    lang_name = {"uk": "Ukrainian", "pl": "Polish", "de": "German", "fr": "French"}.get(lang, lang)

    # ── 1. Load library samples ───────────────────────────────────────────
    library_samples: list[str] = []
    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if task and task.library_id:
            sample_result = await session.execute(
                select(StyleSample)
                .where(StyleSample.library_id == task.library_id)
                .where(StyleSample.quality_tier == QualityTier.L1)
                .limit(5)
            )
            samples = sample_result.scalars().all()
            if not samples:
                fb = await session.execute(
                    select(StyleSample).where(StyleSample.library_id == task.library_id).limit(5)
                )
                samples = fb.scalars().all()
            library_samples = [s.content for s in samples if s.content]

    style_elements = extract_style_elements(library_samples) if library_samples else {}
    style_injection = build_style_injection(style_elements) if style_elements else ""
    best_reference = library_samples[0][:600] if library_samples else ""

    # ── 2. Protect proper nouns, then chain ──────────────────────────────
    protected_text, placeholders = _protect_proper_nouns(original_text)
    chained_text = original_text
    try:
        chained_protected = await apply_chain(protected_text, ["zh-CN", lang], source_lang=lang)
        if chained_protected and chained_protected.strip():
            restored = _restore_proper_nouns(chained_protected, placeholders)
            logger.info("[humanize] chain applied+restored: %d→%d words", len(original_text.split()), len(restored.split()))
            chained_text = restored
    except Exception as exc:
        logger.warning("[humanize] chain failed: %s — using original", exc)

    # ── 3. LLM polish with style injection ───────────────────────────────
    provider = get_default_provider()

    marker_block = _AI_MARKER_BLOCK_UK if lang == "uk" else ""
    system = (
        f"{marker_block}\n\n{_RESTRUCTURE_BLOCK}\n\n"
        f"You are a native {lang_name} journalist and editor. "
        f"The text below was written by AI and passed through machine translation — it may have awkward phrasing. "
        f"Rewrite it so it reads as natural, human-written {lang_name}. "
        f"Preserve all facts, names, dates, and numbers exactly. "
        f"STRICT RULES:\n"
        f"- Do NOT add sentences, questions, or commentary that were not in the original text.\n"
        f"- Do NOT add rhetorical questions at the end.\n"
        f"- Do NOT add 'engaging' conclusions — end where the original ended.\n"
        f"- Preserve proper nouns (place names, personal names, brand names) exactly as given.\n"
        f"Return ONLY the rewritten {lang_name} text."
    )

    user_parts: list[str] = []
    if style_injection:
        user_parts.append(style_injection)
    if best_reference:
        user_parts.append(
            f"Rewrite using the same language style and tone as this reference "
            f"(human-written {lang_name}):\n{chained_text}\n\n# Reference Text:\n{best_reference}"
        )
    else:
        user_parts.append(f"Text to humanize in {lang_name}:\n{chained_text}")

    user_prompt = "\n\n".join(user_parts)

    try:
        response = await provider.generate(user_prompt, system_prompt=system, temperature=0.85, max_tokens=2048)
        humanized = response["text"]
        if not humanized.strip():
            raise ValueError("empty response")
    except Exception as exc:
        logger.warning("[humanize] LLM failed: %s — using chained text", exc)
        humanized = chained_text

    # ── 4. Cleanup pass ───────────────────────────────────────────────────
    cleanup_system = (
        f"You are a proofreader for {lang_name}. Fix ONLY:\n"
        f"1. Machine translation artifacts (isolated conjunctions, awkward calques).\n"
        f"2. Grammar errors (gender/number agreement).\n"
        f"3. Broken or mistranslated proper nouns — restore them to match the ORIGINAL text:\n{original_text[:400]}\n"
        f"Do NOT add new sentences. Do NOT add rhetorical questions. Return ONLY the fixed text."
    )
    try:
        cleanup = await provider.generate(humanized, system_prompt=cleanup_system, temperature=0.15, max_tokens=2048)
        if cleanup.get("text", "").strip():
            humanized = cleanup["text"]
    except Exception as exc:
        logger.warning("[humanize] cleanup failed: %s", exc)

    return {**context, "translation_result": original_text, "translation_adapted_text": humanized}


async def _do_direct_rewrite(context: dict[str, Any]) -> dict[str, Any]:
    """Single-pass direct rewrite to target language using library style elements.

    Replaces the old translate→adapt two-step pipeline.
    Steps:
      1. Load L1 library samples + extract Ukrainian style elements.
      2. One LLM call: rewrite the chain-processed EN text directly in Ukrainian,
         using extracted phrases/openers as concrete style guidance.
      3. uk→zh-CN→uk chain to break LLM statistical patterns.
      4. Cleanup pass to fix chain artifacts.
    """
    from adapters.llm import get_default_provider
    from application.services.ukrainian_extractor import extract_style_elements, build_style_injection
    from infrastructure.db.models import RewriteTask, StyleSample
    from infrastructure.db.session import AsyncSessionLocal
    from rewrite.multilingual_chain import apply_chain
    from rewrite.prompts import _AI_MARKER_BLOCK_UK, _RESTRUCTURE_BLOCK

    translation_target = context["translation_target"]
    variants = context.get("variants", [])
    if not variants:
        return context

    source_text = variants[0]["text"]  # EN chain-processed text
    task_id = context["task_id"]
    lang_name = {"uk": "Ukrainian", "pl": "Polish", "de": "German", "fr": "French"}.get(
        translation_target, translation_target
    )

    # ── 1. Load library samples and extract style ──────────────────────────
    library_samples: list[str] = []
    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if task and task.library_id:
            from sqlalchemy import select
            sample_result = await session.execute(
                select(StyleSample)
                .where(StyleSample.library_id == task.library_id)
                .where(StyleSample.quality_tier == QualityTier.L1)
                .limit(5)
            )
            samples = sample_result.scalars().all()
            if not samples:
                fb = await session.execute(
                    select(StyleSample).where(StyleSample.library_id == task.library_id).limit(5)
                )
                samples = fb.scalars().all()
            library_samples = [s.content for s in samples if s.content]

    style_elements = extract_style_elements(library_samples) if library_samples else {}
    style_injection = build_style_injection(style_elements) if style_elements else ""

    best_reference = library_samples[0][:600] if library_samples else ""

    # ── 2. Direct rewrite in target language ──────────────────────────────
    provider = get_default_provider()

    system = (
        f"{_AI_MARKER_BLOCK_UK if translation_target == 'uk' else ''}\n\n"
        f"{_RESTRUCTURE_BLOCK}\n\n"
        f"You are a native {lang_name} writer and journalist. "
        f"Rewrite the following text DIRECTLY in {lang_name} — do not translate word-for-word. "
        f"Write as a human {lang_name} analyst would write from scratch, capturing the meaning "
        f"and all key facts but using natural {lang_name} phrasing, rhythm, and vocabulary.\n"
        f"Preserve all factual content, names, dates, and numbers.\n"
        f"Return ONLY the {lang_name} text — no explanations, no English."
    )

    user_parts: list[str] = []
    if style_injection:
        user_parts.append(style_injection)
    if best_reference:
        user_parts.append(
            f"Rewrite using the same language style, tone, and expression as this reference "
            f"(human-written {lang_name}):\n{source_text}\n\n# Reference Text:\n{best_reference}"
        )
    else:
        user_parts.append(f"Text to rewrite in {lang_name}:\n{source_text}")

    user_prompt = "\n\n".join(user_parts)

    try:
        response = await provider.generate(
            user_prompt,
            system_prompt=system,
            temperature=0.90,
            max_tokens=2048,
        )
        adapted = response["text"]
        if not adapted.strip():
            raise ValueError("empty response")
    except Exception as exc:
        logger.warning("[adapt] direct rewrite failed: %s — using source text", exc)
        return {**context, "translation_result": source_text, "translation_adapted_text": source_text}

    # ── 3. uk→zh-CN→uk chain ──────────────────────────────────────────────
    lang_code = {"uk": "uk", "pl": "pl", "de": "de", "fr": "fr"}.get(translation_target, translation_target)
    try:
        chained = await apply_chain(adapted, ["zh-CN", lang_code], source_lang=lang_code)
        if chained and chained.strip():
            logger.info("uk chain applied: %d→%d words", len(adapted.split()), len(chained.split()))
            adapted = chained
    except Exception as exc:
        logger.warning("uk chain failed: %s", exc)

    # ── 4. Cleanup pass (fix chain artifacts) ─────────────────────────────
    cleanup_system = (
        f"You are a proofreader for {lang_name}. Fix ONLY machine translation artifacts: "
        f"isolated conjunctions as their own sentences, broken proper nouns, awkward calques. "
        f"Do NOT rewrite or paraphrase. Return ONLY the fixed text."
    )
    try:
        cleanup = await provider.generate(adapted, system_prompt=cleanup_system, temperature=0.2, max_tokens=2048)
        if cleanup.get("text", "").strip():
            adapted = cleanup["text"]
    except Exception as exc:
        logger.warning("[adapt] cleanup failed: %s", exc)

    return {**context, "translation_result": source_text, "translation_adapted_text": adapted}


async def _do_adapt(context: dict[str, Any]) -> dict[str, Any]:
    from adapters.llm import get_default_provider
    from infrastructure.db.models import RewriteTask, StyleSample
    from infrastructure.db.session import AsyncSessionLocal
    from rewrite.prompts import (
        build_adaptation_user_prompt,
        get_adaptation_system_prompt,
        get_refinement_system_prompt,
    )

    translation_target = context["translation_target"]
    translated_text = context["translation_result"]
    style_profile = context.get("style_profile")
    task_id = context["task_id"]

    # Load L1 library samples so the LLM can match human style
    reference_sample: str | None = None
    async with AsyncSessionLocal() as session:
        task = await session.get(RewriteTask, task_id)
        if task:
            sample_result = await session.execute(
                select(StyleSample)
                .where(StyleSample.library_id == task.library_id)
                .where(StyleSample.quality_tier == QualityTier.L1)
                .limit(1)
            )
            sample = sample_result.scalar_one_or_none()
            if not sample:
                fallback = await session.execute(
                    select(StyleSample)
                    .where(StyleSample.library_id == task.library_id)
                    .limit(1)
                )
                sample = fallback.scalar_one_or_none()
            if sample:
                reference_sample = sample.content

    provider = get_default_provider()
    system = get_adaptation_system_prompt(translation_target, style_profile, reference_sample)
    user = build_adaptation_user_prompt(translated_text, style_profile, reference_sample)

    _uk_markers = [
        "варто зазначити", "необхідно відзначити", "слід зазначити",
        "важливо розуміти", "таким чином", "у висновку", "підбиваючи підсумок",
        "загалом", "безперечно", "безсумнівно", "очевидно",
        "безумовно", "крім того", "більш того",
        # GPTZero specifically flags these as AI-artificial in Ukrainian
        "дійсно,", "справді,", "ось у чому проблема", "ось у чому питання",
        "що стосується", "необхідно підкреслити", "важливо підкреслити",
        # Russian/English markers that survive translation
        "стоит отметить", "таким образом", "furthermore", "moreover", "in conclusion",
    ]

    def _has_markers(text: str) -> bool:
        lower = text.lower()
        return any(m in lower for m in _uk_markers)

    try:
        response = await provider.generate(
            user,
            system_prompt=system,
            temperature=0.90,
            max_tokens=2048,
        )
        adapted = response["text"]

        # Refinement pass if AI markers still present
        if _has_markers(adapted):
            ref2 = await provider.generate(
                f"Text to refine:\n{adapted}",
                system_prompt=get_refinement_system_prompt(),
                temperature=0.90,
                max_tokens=2048,
            )
            if ref2.get("text", "").strip():
                adapted = ref2["text"]

        # Contraction pass for Ukrainian output — same logic as EN:
        # AI produces ~0 contractions; human Ukrainian uses скорочення природно.
        # Ukrainian contractions: "це є"→"це", "не є"→"немає" are different;
        # focus on informal short forms that survived from the EN translation.
        def _contraction_ratio_uk(text: str) -> float:
            words = text.split()
            if not words:
                return 0.0
            # Count apostrophe forms like "не'зрозуміло" (Ukrainian soft contractions)
            count = sum(1 for w in words if "'" in w and len(w) > 2)
            return count / len(words) * 100

        if translation_target == "uk" and _contraction_ratio_uk(adapted) < 0.2:
            pass  # Ukrainian doesn't use English-style contractions — skip
        elif translation_target != "uk":
            words = adapted.split()
            contraction_count = sum(1 for w in words if "'" in w and len(w) > 2)
            if len(words) > 40 and contraction_count == 0:
                cont_resp = await provider.generate(
                    adapted,
                    system_prompt=(
                        "Add natural contractions to this text: replace 'do not'→'don't', "
                        "'does not'→'doesn't', 'it is'→'it's', 'cannot'→'can't', "
                        "'will not'→'won't', 'would not'→'wouldn't', 'could not'→'couldn't', "
                        "'should not'→'shouldn't', 'have not'→'haven't', 'has not'→'hasn't'. "
                        "Make NO other changes. Return ONLY the modified text."
                    ),
                    temperature=0.3,
                    max_tokens=2048,
                )
                if cont_resp.get("text", "").strip():
                    adapted = cont_resp["text"]

        # Multilingual chain for target language:
        # uk→zh-CN→uk breaks the GPT-style Ukrainian patterns the same way
        # EN→ZH→EN breaks English ones. Chinese grammar is equally foreign to Ukrainian.
        adapted = await _chain_target_lang(adapted, translation_target)

        # Post-chain cleanup: the ZH round-trip sometimes leaves translation
        # artifacts (one-word sentence fragments like "але.", broken names,
        # awkward calques). A focused LLM pass fixes these without re-introducing
        # AI patterns — it only repairs, does not rewrite.
        lang_name = {"uk": "Ukrainian", "pl": "Polish", "de": "German", "fr": "French"}.get(
            translation_target, translation_target
        )
        cleanup_system = (
            f"You are a proofreader for {lang_name} text. The text below was produced by a "
            f"machine translation round-trip and may contain artifacts: "
            f"isolated conjunctions as their own sentences (e.g. 'але.' or 'і.' alone), "
            f"broken proper nouns, awkward word-for-word calques from Chinese or Japanese. "
            f"Fix ONLY these translation artifacts. Do NOT rewrite, paraphrase, or change "
            f"the meaning or structure of any sentence. Do NOT add new content. "
            f"Do NOT make the text more formal or polished. Return ONLY the fixed text."
        )
        try:
            cleanup_resp = await provider.generate(
                adapted,
                system_prompt=cleanup_system,
                temperature=0.2,
                max_tokens=2048,
            )
            if cleanup_resp.get("text", "").strip():
                adapted = cleanup_resp["text"]
        except Exception as exc:
            logger.warning("[adapt] cleanup pass failed: %s", exc)

        return {**context, "translation_adapted_text": adapted}
    except Exception as exc:
        logger.warning("[adapt] LLM call failed: %s — using raw translation", exc)
        return {**context, "translation_adapted_text": translated_text}


async def _chain_target_lang(text: str, lang: str) -> str:
    """Apply target_lang → zh-CN → target_lang chain to break AI patterns."""
    from rewrite.multilingual_chain import apply_chain
    # Map to Google Translate language codes
    lang_code = {"uk": "uk", "pl": "pl", "de": "de", "fr": "fr"}.get(lang, lang)
    chain = [f"zh-CN", lang_code]
    try:
        result = await apply_chain(text, chain, source_lang=lang_code)
        if result and result.strip():
            logger.info("chain %s→zh→%s applied: %d→%d words", lang, lang, len(text.split()), len(result.split()))
            return result
    except Exception as exc:
        logger.warning("chain %s→zh→%s failed: %s — using pre-chain text", lang, lang, exc)
    return text


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

        translation_adapted = context.get("translation_adapted_text")
        if translation_adapted:
            from domain.enums import RewriteMode
            tv = RewriteVariant(
                task_id=task.id,
                mode=RewriteMode.BALANCED,
                final_text=translation_adapted,
                intermediate_scores={
                    "is_translation": True,
                    "translation_target": context.get("translation_target"),
                    "translation_raw": context.get("translation_result", ""),
                },
                is_valid=True,
            )
            session.add(tv)
            await session.flush()
            saved_variant_ids.append(str(tv.id))

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
