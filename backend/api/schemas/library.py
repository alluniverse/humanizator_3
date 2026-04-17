"""Pydantic schemas for Style Library and Style Sample APIs."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from domain.enums import LibraryCategory, QualityTier, RewriteMode, SemanticContractMode


class StyleSampleCreate(BaseModel):
    title: str | None = None
    content: str
    source: str | None = None
    content_type: str | None = None
    author: str | None = None
    language: str = "ru"


class StyleSampleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    library_id: uuid.UUID
    title: str | None
    content: str
    source: str | None
    content_type: str | None
    author: str | None
    language: str
    quality_tier: QualityTier | None
    analysis_result: dict[str, Any] | None
    created_at: datetime.datetime


class StyleSampleUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    source: str | None = None
    content_type: str | None = None
    author: str | None = None
    language: str | None = None


class StyleLibraryCreate(BaseModel):
    name: str
    description: str | None = None
    category: LibraryCategory
    language: str = "ru"
    project_id: uuid.UUID | None = None
    is_single_voice: bool = False


class StyleLibraryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    category: LibraryCategory
    language: str
    owner_id: uuid.UUID | None
    project_id: uuid.UUID | None
    status: str
    version: int
    quality_tier: str | None
    is_single_voice: bool
    created_at: datetime.datetime
    updated_at: datetime.datetime
    sample_count: int = 0


class StyleLibraryDetailRead(StyleLibraryRead):
    samples: list[StyleSampleRead] = []


class StyleLibraryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    category: LibraryCategory | None = None
    language: str | None = None
    status: str | None = None
    is_single_voice: bool | None = None


class LibraryDiagnostics(BaseModel):
    total_samples: int
    l1_count: int
    l2_count: int
    l3_count: int
    l1_ratio: float
    l2_ratio: float
    l3_ratio: float
    is_valid_for_profiling: bool
    warnings: list[str]
    recommendations: list[str]


class BulkSampleImport(BaseModel):
    samples: list[StyleSampleCreate]


class PresetCreate(BaseModel):
    name: str
    library_id: uuid.UUID
    rewrite_mode: RewriteMode = RewriteMode.BALANCED
    semantic_contract_mode: SemanticContractMode = SemanticContractMode.BALANCED
    constraints: dict[str, Any] | None = None
    intervention_level: float = Field(0.5, ge=0.0, le=1.0)
    active_heuristics: list[str] | None = None


class PresetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    library_id: uuid.UUID
    rewrite_mode: RewriteMode
    semantic_contract_mode: SemanticContractMode
    constraints: dict[str, Any] | None
    intervention_level: float
    active_heuristics: list[str] | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class StyleProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    library_id: uuid.UUID
    version: int
    formality: float | None
    sentence_length_mean: float | None
    sentence_length_variance: float | None
    burstiness_index: float | None
    target_perplexity_min: float | None
    target_perplexity_max: float | None
    rhythm_profile: dict[str, Any] | None
    lexical_signature: dict[str, Any] | None
    syntax_patterns: list[str] | None
    composition_profile: dict[str, Any] | None
    linguistic_markers: dict[str, Any] | None
    guidance_signals: dict[str, Any] | None
    created_at: datetime.datetime
    updated_at: datetime.datetime
