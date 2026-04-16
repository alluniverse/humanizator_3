"""Integration tests for full Evaluation API."""

import uuid

import pytest
from httpx import AsyncClient

from infrastructure.db.models import Project, RewriteTask, StyleLibrary, StyleProfile, User
from infrastructure.db.session import AsyncSessionLocal


async def _setup_task_with_profile(async_client: AsyncClient) -> str:
    async with AsyncSessionLocal() as session:
        user = User(email=f"test-{uuid.uuid4()}@example.com", full_name="Test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="EvalFull Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        library = StyleLibrary(name="EvalFull Library", category="news", language="en", project_id=project.id)
        session.add(library)
        await session.commit()
        await session.refresh(library)

        profile = StyleProfile(
            library_id=library.id,
            guidance_signals={
                "target_sentence_length": 15.0,
                "target_burstiness": 0.5,
                "target_formality": 0.5,
            },
            lexical_signature={"avoid_markers": ["moreover"]},
        )
        session.add(profile)
        await session.commit()

        task = RewriteTask(
            project_id=project.id,
            library_id=library.id,
            original_text="The quick brown fox jumps over the lazy dog.",
            rewrite_mode="balanced",
            semantic_contract_mode="balanced",
            user_id=None,
        )
        session.add(task)
        await session.commit()
        await session.refresh(task)
        return str(task.id)


@pytest.mark.asyncio
async def test_style_guidance(async_client: AsyncClient) -> None:
    task_id = await _setup_task_with_profile(async_client)
    variants = [
        {"text": "The quick brown fox jumps over the lazy dog.", "mode": "conservative"},
        {"text": "A swift brown fox leaps across the sleepy dog.", "mode": "balanced"},
    ]
    resp = await async_client.post(
        f"/evaluation/{task_id}/style-guidance",
        json=variants,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "ranked_variants" in data
    assert len(data["ranked_variants"]) == 2


@pytest.mark.asyncio
async def test_polish_and_grammar(async_client: AsyncClient) -> None:
    task_id = await _setup_task_with_profile(async_client)
    resp = await async_client.post(
        f"/evaluation/{task_id}/polish",
        params={"text": "The quick brown fox jumps over the lazy dog. Moreover, it is fast."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "polished" in data
    assert "grammar" in data


@pytest.mark.asyncio
async def test_absolute_metrics(async_client: AsyncClient) -> None:
    task_id = await _setup_task_with_profile(async_client)
    resp = await async_client.post(
        f"/evaluation/{task_id}/absolute-metrics",
        params={"variant_text": "The quick brown fox jumps over the lazy dog."},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data
    assert "bertscore_f1" in data["metrics"]


@pytest.mark.asyncio
async def test_pairwise(async_client: AsyncClient) -> None:
    task_id = await _setup_task_with_profile(async_client)
    resp = await async_client.post(
        f"/evaluation/{task_id}/pairwise",
        params={
            "variant_a": "The quick brown fox jumps over the lazy dog.",
            "variant_b": "A swift brown fox leaps across the sleepy dog.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "pairwise" in data
    assert data["pairwise"]["winner"] in {"A", "B", "tie"}
