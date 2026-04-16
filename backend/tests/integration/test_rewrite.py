"""Integration tests for Rewrite API."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_and_get_rewrite_task(async_client: AsyncClient) -> None:
    # Create library first
    lib_payload = {"name": "Rewrite Test Lib", "category": "art", "language": "en"}
    resp = await async_client.post("/libraries", json=lib_payload)
    library_id = resp.json()["id"]

    # Create a project first
    import uuid
    from infrastructure.db.models import Project, User
    from infrastructure.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        user = User(email=f"test-{uuid.uuid4()}@example.com", full_name="Test User")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="Test Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        project_id = project.id

    task_payload = {
        "project_id": str(project_id),
        "library_id": library_id,
        "original_text": "The quick brown fox jumps over the lazy dog.",
        "rewrite_mode": "balanced",
        "semantic_contract_mode": "strict",
    }
    resp = await async_client.post("/rewrite", json=task_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["original_text"] == task_payload["original_text"]
    task_id = data["id"]

    resp = await async_client.get(f"/rewrite/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == task_id


@pytest.mark.asyncio
async def test_analyze_input(async_client: AsyncClient) -> None:
    lib_payload = {"name": "Analyzer Test Lib", "category": "news", "language": "en"}
    resp = await async_client.post("/libraries", json=lib_payload)
    library_id = resp.json()["id"]

    import uuid
    from infrastructure.db.models import Project, User
    from infrastructure.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        user = User(email=f"test-{uuid.uuid4()}@example.com", full_name="Test User")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="Analyzer Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        project_id = project.id

    task_payload = {
        "project_id": str(project_id),
        "library_id": library_id,
        "original_text": "John Doe founded Acme Corp in 1999. It became a giant.",
    }
    resp = await async_client.post("/rewrite", json=task_payload)
    task_id = resp.json()["id"]

    resp = await async_client.post(f"/rewrite/{task_id}/analyze-input")
    assert resp.status_code == 200
    data = resp.json()
    assert "input_profile" in data
    assert "risk_map" in data


@pytest.mark.asyncio
async def test_semantic_contract(async_client: AsyncClient) -> None:
    lib_payload = {"name": "Contract Test Lib", "category": "marketing", "language": "en"}
    resp = await async_client.post("/libraries", json=lib_payload)
    library_id = resp.json()["id"]

    import uuid
    from infrastructure.db.models import Project, User
    from infrastructure.db.session import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        user = User(email=f"test-{uuid.uuid4()}@example.com", full_name="Test User")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="Contract Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)
        project_id = project.id

    task_payload = {
        "project_id": str(project_id),
        "library_id": library_id,
        "original_text": "Apple Inc. released the iPhone in 2007. It changed everything.",
        "semantic_contract_mode": "strict",
    }
    resp = await async_client.post("/rewrite", json=task_payload)
    task_id = resp.json()["id"]

    resp = await async_client.post(f"/rewrite/{task_id}/semantic-contract")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "strict"
    assert len(data["protected_entities"]) > 0
    assert "constraints" in data
