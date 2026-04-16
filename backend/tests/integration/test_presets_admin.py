"""Integration tests for Presets and Admin API."""

import uuid

import pytest
from httpx import AsyncClient

from infrastructure.db.models import Project, User
from infrastructure.db.session import AsyncSessionLocal


@pytest.mark.asyncio
async def test_preset_crud(async_client: AsyncClient) -> None:
    async with AsyncSessionLocal() as session:
        user = User(email=f"test-{uuid.uuid4()}@example.com", full_name="Test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="Preset Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)

        from infrastructure.db.models import StyleLibrary
        library = StyleLibrary(name="Preset Lib", category="news", language="en", project_id=project.id)
        session.add(library)
        await session.commit()
        await session.refresh(library)
        library_id = library.id

    payload = {
        "name": "My Preset",
        "library_id": str(library_id),
        "rewrite_mode": "balanced",
        "semantic_contract_mode": "strict",
        "intervention_level": 0.7,
    }
    resp = await async_client.post("/presets", json=payload)
    assert resp.status_code == 201
    preset_id = resp.json()["id"]

    resp = await async_client.get(f"/presets/{preset_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "My Preset"

    resp = await async_client.post(f"/presets/{preset_id}/apply")
    assert resp.status_code == 200
    assert resp.json()["rewrite_mode"] == "balanced"


@pytest.mark.asyncio
async def test_admin_link_library(async_client: AsyncClient) -> None:
    async with AsyncSessionLocal() as session:
        user = User(email=f"test-{uuid.uuid4()}@example.com", full_name="Test")
        session.add(user)
        await session.commit()
        await session.refresh(user)
        project = Project(name="Admin Project", owner_id=user.id)
        session.add(project)
        await session.commit()
        await session.refresh(project)

        from infrastructure.db.models import StyleLibrary
        library = StyleLibrary(name="Admin Lib", category="art", language="en")
        session.add(library)
        await session.commit()
        await session.refresh(library)
        project_id = project.id
        library_id = library.id

    resp = await async_client.post(f"/admin/projects/{project_id}/libraries/{library_id}/link")
    assert resp.status_code == 200
    assert resp.json()["linked"] is True

    resp = await async_client.get(f"/admin/projects/{project_id}/libraries")
    assert resp.status_code == 200
    assert any(lib["id"] == str(library_id) for lib in resp.json())
