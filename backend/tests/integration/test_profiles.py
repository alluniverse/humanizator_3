"""Integration tests for Style Profile API."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_build_and_get_profile(async_client: AsyncClient) -> None:
    # Create library
    payload = {"name": "Profile Test Library", "category": "news", "language": "en"}
    resp = await async_client.post("/libraries", json=payload)
    assert resp.status_code == 201
    library_id = resp.json()["id"]

    # Add L1 sample
    sample = {
        "title": "Sample",
        "content": (
            "The morning sun cast long shadows across the empty street. "
            "A solitary figure walked slowly, hands buried deep in coat pockets. "
            "Autumn leaves crunched underfoot, each step a quiet reminder of passing time."
        ),
        "language": "en",
    }
    resp = await async_client.post(f"/libraries/{library_id}/samples", json=sample)
    assert resp.status_code == 201

    # Build profile
    resp = await async_client.post(f"/profiles/{library_id}/build")
    assert resp.status_code == 201
    data = resp.json()
    assert data["library_id"] == library_id
    assert data["sentence_length_mean"] is not None

    # Get latest profile
    resp = await async_client.get(f"/profiles/{library_id}/latest")
    assert resp.status_code == 200
    assert resp.json()["id"] == data["id"]

    # Get DNA
    resp = await async_client.get(f"/profiles/{library_id}/dna")
    assert resp.status_code == 200
    dna = resp.json()
    assert "formality" in dna
    assert "burstiness_index" in dna
