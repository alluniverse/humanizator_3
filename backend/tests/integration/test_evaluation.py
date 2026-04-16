"""Integration tests for Evaluation API."""

import uuid

import pytest
from httpx import AsyncClient

from infrastructure.db.models import Project, RewriteTask, StyleLibrary, User
from infrastructure.db.session import AsyncSessionLocal


async def _setup_task(async_client: AsyncClient) -> str:
    async with AsyncSessionLocal() as session:
        user = User(email=f"test-{uuid.uuid4()}@example.com", full_name="Test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="Eval Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        library = StyleLibrary(name="Eval Library", category="news", language="en", project_id=project.id)
        session.add(library)
        await session.commit()
        await session.refresh(library)
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
async def test_word_importance(async_client: AsyncClient) -> None:
    task_id = await _setup_task(async_client)
    resp = await async_client.post(f"/evaluation/{task_id}/word-importance")
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data
    assert len(data["scores"]) > 0


@pytest.mark.asyncio
async def test_holistic_rank(async_client: AsyncClient) -> None:
    task_id = await _setup_task(async_client)
    resp = await async_client.post(
        f"/evaluation/{task_id}/holistic-rank?target_index=1&mode=fast",
        json=["fast", "slow", "clever"],
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "ranked" in data
    assert len(data["ranked"]) == 3


@pytest.mark.asyncio
async def test_validate_constraints(async_client: AsyncClient) -> None:
    task_id = await _setup_task(async_client)
    rewritten = "The quick brown fox jumps over the lazy dog."
    resp = await async_client.post(
        f"/evaluation/{task_id}/validate-constraints",
        params={"rewritten_text": rewritten},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "validation" in data
    assert data["validation"]["valid"] is True
