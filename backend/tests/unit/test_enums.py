"""Unit tests: domain enums."""

from domain.enums import (
    LibraryCategory,
    QualityTier,
    RewriteMode,
    RewriteTaskStatus,
    SemanticContractMode,
)


def test_rewrite_task_status_values() -> None:
    assert RewriteTaskStatus.CREATED.value == "created"
    assert RewriteTaskStatus.ANALYZING.value == "analyzing"
    assert RewriteTaskStatus.REWRITING.value == "rewriting"
    assert RewriteTaskStatus.EVALUATING.value == "evaluating"
    assert RewriteTaskStatus.COMPLETED.value == "completed"
    assert RewriteTaskStatus.FAILED.value == "failed"


def test_quality_tier_ordering() -> None:
    tiers = [QualityTier.L1, QualityTier.L2, QualityTier.L3]
    assert all(t.value in {"L1", "L2", "L3"} for t in tiers)
    assert QualityTier.L1.value == "L1"


def test_rewrite_mode_values() -> None:
    assert RewriteMode.CONSERVATIVE.value == "conservative"
    assert RewriteMode.BALANCED.value == "balanced"
    assert RewriteMode.EXPRESSIVE.value == "expressive"


def test_semantic_contract_mode_values() -> None:
    assert SemanticContractMode.STRICT.value == "strict"
    assert SemanticContractMode.BALANCED.value == "balanced"
    assert SemanticContractMode.LOOSE.value == "loose"


def test_library_category_covers_core_categories() -> None:
    actual = {c.value for c in LibraryCategory}
    for required in ("news", "cinema", "marketing", "art"):
        assert required in actual, f"{required!r} missing from LibraryCategory"
