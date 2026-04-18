"""Pydantic schemas for Rewrite API."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict

from domain.enums import RewriteMode, RewriteTaskStatus, SemanticContractMode


class RewriteTaskCreate(BaseModel):
    project_id: uuid.UUID | None = None
    library_id: uuid.UUID
    original_text: str
    rewrite_mode: RewriteMode = RewriteMode.BALANCED
    semantic_contract_mode: SemanticContractMode = SemanticContractMode.BALANCED
    input_constraints: dict[str, Any] | None = None


class RewriteRunRequest(BaseModel):
    user_instruction: str | None = None


class RewriteTaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None
    user_id: uuid.UUID | None
    library_id: uuid.UUID
    original_text: str
    rewrite_mode: RewriteMode
    semantic_contract_mode: SemanticContractMode
    status: RewriteTaskStatus
    input_constraints: dict[str, Any] | None
    error_message: str | None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class RewriteVariantRead(BaseModel):
    id: uuid.UUID
    mode: RewriteMode
    rewritten_text: str
    variant_index: int
    review_status: str
    scores: dict[str, Any]
    is_valid: bool
    is_translation: bool = False
    translation_target: str | None = None
    created_at: datetime.datetime


class SemanticContractRead(BaseModel):
    mode: str
    protected_entities: list[dict[str, Any]]
    protected_numbers: list[dict[str, Any]]
    key_terms: list[str]
    causal_spans: list[dict[str, Any]]
    importance_map: list[dict[str, Any]]
    constraints: dict[str, Any]
