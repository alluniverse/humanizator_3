"""Database models for the humanizator system."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from domain.enums import (
    LibraryCategory,
    QualityTier,
    RewriteMode,
    RewriteTaskStatus,
    SemanticContractMode,
)
from infrastructure.db.base import Base


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), onupdate=func.now(), init=False)

    projects: Mapped[list["Project"]] = relationship(back_populates="owner", lazy="selectin", init=False)
    libraries: Mapped[list["StyleLibrary"]] = relationship(back_populates="owner", lazy="selectin", init=False)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), onupdate=func.now(), init=False)

    owner: Mapped["User"] = relationship(back_populates="projects", init=False)
    libraries: Mapped[list["StyleLibrary"]] = relationship(back_populates="project", lazy="selectin", init=False)
    tasks: Mapped[list["RewriteTask"]] = relationship(back_populates="project", lazy="selectin", init=False)


class StyleLibrary(Base):
    __tablename__ = "style_libraries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[LibraryCategory] = mapped_column(Enum(LibraryCategory, name="library_category"), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, default=None)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True, default=None)
    quality_tier: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)
    language: Mapped[str] = mapped_column(String(10), default="ru")
    status: Mapped[str] = mapped_column(String(50), default="active")
    version: Mapped[int] = mapped_column(default=1)
    is_single_voice: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), onupdate=func.now(), init=False)

    owner: Mapped["User | None"] = relationship(back_populates="libraries", init=False)
    project: Mapped["Project | None"] = relationship(back_populates="libraries", init=False)
    samples: Mapped[list["StyleSample"]] = relationship(back_populates="library", lazy="selectin", init=False, cascade="all, delete-orphan")
    profiles: Mapped[list["StyleProfile"]] = relationship(back_populates="library", lazy="selectin", init=False, cascade="all, delete-orphan")


class StyleSample(Base):
    __tablename__ = "style_samples"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    library_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("style_libraries.id"), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    content_type: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    language: Mapped[str] = mapped_column(String(10), default="ru")
    quality_tier: Mapped[QualityTier | None] = mapped_column(Enum(QualityTier, name="quality_tier"), nullable=True, default=None)
    analysis_result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)

    library: Mapped["StyleLibrary"] = relationship(back_populates="samples", init=False)


class StyleProfile(Base):
    __tablename__ = "style_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    library_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("style_libraries.id"), nullable=False)
    version: Mapped[int] = mapped_column(default=1)
    formality: Mapped[float | None] = mapped_column(nullable=True, default=None)
    sentence_length_mean: Mapped[float | None] = mapped_column(nullable=True, default=None)
    sentence_length_variance: Mapped[float | None] = mapped_column(nullable=True, default=None)
    burstiness_index: Mapped[float | None] = mapped_column(nullable=True, default=None)
    target_perplexity_min: Mapped[float | None] = mapped_column(nullable=True, default=None)
    target_perplexity_max: Mapped[float | None] = mapped_column(nullable=True, default=None)
    rhythm_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    lexical_signature: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    syntax_patterns: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    composition_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    linguistic_markers: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    guidance_signals: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), onupdate=func.now(), init=False)

    library: Mapped["StyleLibrary"] = relationship(back_populates="profiles", init=False)


class Preset(Base):
    __tablename__ = "presets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    library_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("style_libraries.id"), nullable=False)
    rewrite_mode: Mapped[RewriteMode] = mapped_column(Enum(RewriteMode, name="rewrite_mode"), nullable=False)
    semantic_contract_mode: Mapped[SemanticContractMode] = mapped_column(Enum(SemanticContractMode, name="semantic_contract_mode"), nullable=False)
    constraints: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    intervention_level: Mapped[float] = mapped_column(default=0.5)
    active_heuristics: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), onupdate=func.now(), init=False)


class RewriteTask(Base):
    __tablename__ = "rewrite_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"), nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    library_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("style_libraries.id"), nullable=False)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    rewrite_mode: Mapped[RewriteMode] = mapped_column(Enum(RewriteMode, name="rewrite_mode"), nullable=False)
    semantic_contract_mode: Mapped[SemanticContractMode] = mapped_column(Enum(SemanticContractMode, name="semantic_contract_mode"), nullable=False)
    status: Mapped[RewriteTaskStatus] = mapped_column(Enum(RewriteTaskStatus, name="rewrite_task_status"), default=RewriteTaskStatus.CREATED)
    input_constraints: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), onupdate=func.now(), init=False)

    project: Mapped["Project"] = relationship(back_populates="tasks", init=False)
    variants: Mapped[list["RewriteVariant"]] = relationship(back_populates="task", lazy="selectin", init=False, cascade="all, delete-orphan")
    evaluation_reports: Mapped[list["EvaluationReport"]] = relationship(back_populates="task", lazy="selectin", init=False, cascade="all, delete-orphan")


class RewriteVariant(Base):
    __tablename__ = "rewrite_variants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rewrite_tasks.id"), nullable=False)
    mode: Mapped[RewriteMode] = mapped_column(Enum(RewriteMode, name="rewrite_mode_variant"), nullable=False)
    final_text: Mapped[str] = mapped_column(Text, nullable=False)
    intermediate_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    style_match_score: Mapped[float | None] = mapped_column(nullable=True, default=None)
    semantic_preservation_score: Mapped[float | None] = mapped_column(nullable=True, default=None)
    perplexity_score: Mapped[float | None] = mapped_column(nullable=True, default=None)
    burstiness_score: Mapped[float | None] = mapped_column(nullable=True, default=None)
    fluency_win_rate: Mapped[float | None] = mapped_column(nullable=True, default=None)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_valid: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)

    task: Mapped["RewriteTask"] = relationship(back_populates="variants", init=False)


class EvaluationReport(Base):
    __tablename__ = "evaluation_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rewrite_tasks.id"), nullable=False)
    variant_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("rewrite_variants.id"), nullable=True)
    absolute_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    judge_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    pairwise_scores: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    contract_violations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    warnings: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    recommendations: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=None)
    composite_score: Mapped[float | None] = mapped_column(nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)

    task: Mapped["RewriteTask"] = relationship(back_populates="evaluation_reports", init=False)


class LLMProviderConfig(Base):
    __tablename__ = "llm_provider_configs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    provider_name: Mapped[str] = mapped_column(String(100), nullable=False)
    default_model: Mapped[str] = mapped_column(String(100), nullable=False)
    api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    cost_per_input_token: Mapped[float | None] = mapped_column(nullable=True, default=None)
    cost_per_output_token: Mapped[float | None] = mapped_column(nullable=True, default=None)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), onupdate=func.now(), init=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default_factory=uuid.uuid4, init=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), default_factory=_now, server_default=func.now(), init=False)
