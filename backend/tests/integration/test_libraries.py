"""Integration tests for Style Library API."""

import uuid

import pytest
from httpx import AsyncClient

from domain.enums import LibraryCategory, QualityTier


@pytest.mark.asyncio
async def test_create_and_get_library(async_client: AsyncClient) -> None:
    payload = {
        "name": "Test Library",
        "description": "A test library",
        "category": "news",
        "language": "ru",
        "is_single_voice": False,
    }
    resp = await async_client.post("/libraries", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Test Library"
    assert data["category"] == "news"
    library_id = data["id"]

    resp = await async_client.get(f"/libraries/{library_id}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "Test Library"


@pytest.mark.asyncio
async def test_add_sample_and_diagnostics(async_client: AsyncClient) -> None:
    payload = {
        "name": "Diagnostics Library",
        "category": "cinema",
        "language": "ru",
    }
    resp = await async_client.post("/libraries", json=payload)
    library_id = resp.json()["id"]

    sample_payload = {
        "title": "Review",
        "content": (
            "This film is a breathtaking masterpiece of visual storytelling that captivates "
            "audiences from the very first frame. Every single shot feels meticulously "
            "deliberate and purposeful, while the deliberate pacing consistently rewards "
            "patient and attentive viewers with profound emotional depth and resonance."
        ),
        "language": "en",
    }
    resp = await async_client.post(f"/libraries/{library_id}/samples", json=sample_payload)
    assert resp.status_code == 201
    assert resp.json()["quality_tier"] == QualityTier.L1.value

    # Add a weak sample
    weak_payload = {
        "title": "Weak",
        "content": "Short text. Bad. [citation needed]",
    }
    resp = await async_client.post(f"/libraries/{library_id}/samples", json=weak_payload)
    assert resp.status_code == 201
    assert resp.json()["quality_tier"] == QualityTier.L3.value

    resp = await async_client.get(f"/libraries/{library_id}/diagnostics")
    assert resp.status_code == 200
    diag = resp.json()
    assert diag["total_samples"] == 2
    assert diag["l3_count"] == 1
    assert diag["is_valid_for_profiling"] is True  # 1 L1 out of 2 = 50%


@pytest.mark.asyncio
async def test_bulk_import_samples(async_client: AsyncClient) -> None:
    payload = {"name": "Bulk Library", "category": "marketing", "language": "ru"}
    resp = await async_client.post("/libraries", json=payload)
    library_id = resp.json()["id"]

    bulk = {
        "samples": [
            {
                "title": "A",
                "content": (
                    "High quality sample with diverse vocabulary and exceptionally clear structure. "
                    "The author demonstrates remarkable command of language through vivid metaphors, "
                    "precise descriptions, and carefully constructed arguments that engage readers deeply."
                ),
            },
            {
                "title": "B",
                "content": (
                    "Another strong piece of writing that demonstrates consistent tone throughout every paragraph. "
                    "The narrative voice remains authentic and compelling while exploring complex "
                    "themes with nuance, subtlety, and genuine emotional intelligence on every page."
                ),
            },
        ]
    }
    resp = await async_client.post(f"/libraries/{library_id}/samples/bulk", json=bulk)
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 2

    resp = await async_client.get(f"/libraries/{library_id}")
    assert resp.json()["quality_tier"] == "strong"


@pytest.mark.asyncio
async def test_archive_library(async_client: AsyncClient) -> None:
    payload = {"name": "To Archive", "category": "art", "language": "ru"}
    resp = await async_client.post("/libraries", json=payload)
    library_id = resp.json()["id"]

    resp = await async_client.delete(f"/libraries/{library_id}")
    assert resp.status_code == 204

    resp = await async_client.get(f"/libraries/{library_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"
