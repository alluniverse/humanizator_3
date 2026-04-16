"""Domain enums."""

from enum import Enum


class RewriteTaskStatus(str, Enum):
    """State machine for rewrite tasks."""

    CREATED = "created"
    ANALYZING = "analyzing"
    REWRITING = "rewriting"
    EVALUATING = "evaluating"
    COMPLETED = "completed"
    FAILED = "failed"


class RewriteMode(str, Enum):
    """Rewrite depth modes."""

    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    EXPRESSIVE = "expressive"


class SemanticContractMode(str, Enum):
    """Semantic protection modes."""

    STRICT = "strict"
    BALANCED = "balanced"
    LOOSE = "loose"


class QualityTier(str, Enum):
    """Corpus quality tiers per docs/2501.03437v1."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"


class LibraryCategory(str, Enum):
    """Style library categories."""

    NEWS = "news"
    ART = "art"
    ENTERTAINMENT = "entertainment"
    CINEMA = "cinema"
    MARKETING = "marketing"
    PERSONAL = "personal"
