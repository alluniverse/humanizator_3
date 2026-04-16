"""Integration tests for Guided Rewrite generation (requires OPENAI_API_KEY)."""

import os

import pytest
from httpx import AsyncClient

from infrastructure.db.models import Project, StyleLibrary, StyleSample, User
from infrastructure.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_generate_variants(async_client: AsyncClient) -> None:
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with AsyncSessionLocal() as session:
        user = User(email=f"test-gen@example.com", full_name="Test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="Gen Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)

        library = StyleLibrary(name="Gen Library", category="news", language="en", project_id=project.id)
        session.add(library)
        await session.commit()
        await session.refresh(library)

        sample = StyleSample(library_id=library.id, content="The morning sun cast long shadows across the empty street.", language="en")
        session.add(sample)
        await session.commit()
        library_id = library.id
        project_id = project.id

    task_payload = {
        "project_id": str(project_id),
        "library_id": str(library_id),
        "original_text": "A quick brown fox jumps over the lazy dog.",
        "rewrite_mode": "balanced",
        "semantic_contract_mode": "balanced",
    }
    resp = await async_client.post("/rewrite", json=task_payload)
    assert resp.status_code == 201
    task_id = resp.json()["id"]

    resp = await async_client.post(f"/rewrite/{task_id}/generate")
    assert resp.status_code == 200
    data = resp.json()
    assert "variants" in data
    assert len(data["variants"]) == 3
    modes = {v["mode"] for v in data["variants"]}
    assert modes == {"conservative", "balanced", "expressive"}
