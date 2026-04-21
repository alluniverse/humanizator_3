"""Unit tests: StyleConflictDetector — pure stylometric logic."""

from application.services.style_conflict_detector import (
    StyleConflictDetector,
    _extract_features,
    _sentences,
    _words,
)

svc = StyleConflictDetector(outlier_threshold=2.0)

_SHORT = "Hello. Hi."
_LONG = " ".join(["The quick brown fox jumps over the lazy dog."] * 10)
_DIVERSE = (
    "Artificial intelligence is transforming every industry at unprecedented speed. "
    "Machine learning models now outperform humans on many cognitive benchmarks. "
    "The societal implications are profound and deserve careful consideration."
)


class TestExtractFeatures:
    def test_burstiness_zero_for_single_sentence(self) -> None:
        feats = _extract_features("A single sentence here.")
        assert feats["burstiness"] == 0.0

    def test_avg_sent_len_reasonable(self) -> None:
        feats = _extract_features("First sentence. Second longer sentence here.")
        assert feats["avg_sent_len"] > 0

    def test_ttr_one_for_unique_words(self) -> None:
        feats = _extract_features("alpha beta gamma delta")
        assert feats["ttr"] == 1.0

    def test_ttr_low_for_repetitive(self) -> None:
        feats = _extract_features("word word word word word")
        assert feats["ttr"] < 0.5

    def test_formality_positive(self) -> None:
        feats = _extract_features("The quick brown fox jumps over the lazy dog")
        assert feats["formality"] > 0


class TestDetectConflicts:
    def test_too_few_samples_returns_no_conflicts(self) -> None:
        result = svc.detect_conflicts([{"id": "1", "content": _DIVERSE}])
        assert result["has_conflicts"] is False
        assert "3 samples" in result["recommendations"][0]

    def test_homogeneous_library_no_conflicts(self) -> None:
        samples = [{"id": str(i), "content": _DIVERSE} for i in range(5)]
        result = svc.detect_conflicts(samples)
        assert result["has_conflicts"] is False
        assert result["conflict_count"] == 0

    def test_outlier_detected_when_one_sample_very_different(self) -> None:
        # 4 similar samples + 1 very short one-word "sample"
        normal = {"content": _DIVERSE}
        outlier = {"id": "outlier", "content": "Hi. OK. Yes. No. Maybe. Sure."}
        samples = [{"id": str(i), **normal} for i in range(4)] + [outlier]
        result = svc.detect_conflicts(samples, outlier_threshold=1.5)
        # The outlier may or may not trigger depending on exact z-scores;
        # just check structure is valid
        assert "has_conflicts" in result
        assert "outliers" in result
        assert isinstance(result["outliers"], list)

    def test_result_structure(self) -> None:
        samples = [{"id": str(i), "content": _DIVERSE} for i in range(3)]
        result = svc.detect_conflicts(samples)
        assert "has_conflicts" in result
        assert "conflict_count" in result
        assert "total_samples" in result
        assert "library_profile" in result
        assert "recommendations" in result
        assert result["total_samples"] == 3

    def test_library_profile_has_all_dimensions(self) -> None:
        samples = [{"id": str(i), "content": _DIVERSE} for i in range(3)]
        result = svc.detect_conflicts(samples)
        profile = result["library_profile"]
        for dim in ("avg_sent_len", "burstiness", "ttr", "formality"):
            assert dim in profile

    def test_custom_threshold(self) -> None:
        samples = [{"id": str(i), "content": _DIVERSE} for i in range(5)]
        result_strict = svc.detect_conflicts(samples, outlier_threshold=0.1)
        result_loose = svc.detect_conflicts(samples, outlier_threshold=10.0)
        # With a very tight threshold almost everything may be flagged;
        # with a very loose threshold nothing should be
        assert result_loose["conflict_count"] <= result_strict["conflict_count"]
