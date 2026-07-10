"""Workbench matching suggestions — controller tests (synthetic data only)."""

from __future__ import annotations

import math

from src.matching import DEFAULT_LIMIT
from src.workbench_controller import (
    MATCHING_NO_SUGGESTIONS_MESSAGE,
    WorkbenchRow,
    format_workbench_suggestion_reason,
    suggest_similar_workbench_rows,
    validate_workbench_matching_reference,
    workbench_row_to_match_candidate,
)


def _row(
    name: str,
    *,
    bpm: float | None = 128.0,
    key: str | None = "Am",
    pred_type: str | None = "kick",
    status: str = "ok",
) -> WorkbenchRow:
    path = f"/synthetic/{name}.wav"
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=path,
        bpm=bpm,
        key=key,
        key_conf=0.8 if key else None,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type=pred_type,
        status=status,
    )


class TestWorkbenchRowToMatchCandidate:
    def test_maps_bpm_key_and_type(self):
        row = _row("kick", bpm=140.0, key="C", pred_type="Kick")
        candidate = workbench_row_to_match_candidate(row, sample_id=42)
        assert candidate.sample_id == 42
        assert candidate.path == row.path
        assert candidate.bpm == 140.0
        assert candidate.key == "C"
        assert candidate.pred_type == "Kick"


class TestValidateWorkbenchMatchingReference:
    def test_none_reference(self):
        message = validate_workbench_matching_reference(None)
        assert message is not None
        assert "ausgewählt" in message.casefold()

    def test_missing_bpm(self):
        message = validate_workbench_matching_reference(_row("ref", bpm=None))
        assert message is not None
        assert "bpm" in message.casefold()

    def test_invalid_bpm(self):
        message = validate_workbench_matching_reference(_row("ref", bpm=0.0))
        assert message is not None

    def test_ok_reference(self):
        assert validate_workbench_matching_reference(_row("ref")) is None


class TestSuggestSimilarWorkbenchRows:
    def test_excludes_reference_and_sorts_by_score(self):
        reference = _row("ref", bpm=128.0, key="Am", pred_type="kick")
        close = _row("close", bpm=128.0, key="Am", pred_type="kick")
        far = _row("far", bpm=100.0, key="C", pred_type="snare")

        suggestions = suggest_similar_workbench_rows(
            reference,
            [reference, close, far],
        )

        assert [item.row.path for item in suggestions] == [close.path]
        assert suggestions[0].total_score > 0
        assert reference.path not in {item.row.path for item in suggestions}

    def test_filters_zero_scores(self):
        reference = _row("ref", bpm=128.0, key="Am", pred_type="kick")
        mismatch = _row("mismatch", bpm=60.0, key="C", pred_type="snare")

        suggestions = suggest_similar_workbench_rows(reference, [reference, mismatch])

        assert suggestions == []

    def test_skips_non_ok_candidates(self):
        reference = _row("ref")
        error_row = _row("bad", status="error")
        match = _row("match")

        suggestions = suggest_similar_workbench_rows(
            reference,
            [reference, error_row, match],
        )

        assert len(suggestions) == 1
        assert suggestions[0].row.path == match.path

    def test_respects_limit(self):
        reference = _row("ref", bpm=128.0)
        others = [_row(f"hit-{index}", bpm=128.0) for index in range(5)]

        suggestions = suggest_similar_workbench_rows(
            reference,
            [reference, *others],
            limit=2,
        )

        assert len(suggestions) == 2

    def test_default_limit_matches_matching_module(self):
        reference = _row("ref", bpm=128.0)
        others = [_row(f"hit-{index}", bpm=128.0) for index in range(DEFAULT_LIMIT + 3)]

        suggestions = suggest_similar_workbench_rows(reference, [reference, *others])

        assert len(suggestions) == DEFAULT_LIMIT

    def test_empty_candidate_pool_status(self):
        reference = _row("ref")
        suggestions, status = suggest_similar_workbench_rows_with_status(
            reference,
            [reference],
        )
        assert suggestions == []
        assert status == MATCHING_NO_SUGGESTIONS_MESSAGE


def suggest_similar_workbench_rows_with_status(reference, candidates, *, limit=10):
    """Test helper mirroring UI entry point."""
    from src.workbench_controller import compute_workbench_similar_suggestions

    return compute_workbench_similar_suggestions(reference, candidates, limit=limit)


class TestFormatWorkbenchSuggestionReason:
    def test_prefers_positive_reasons(self):
        text = format_workbench_suggestion_reason(
            (
                "bpm direct match: 128 vs 128",
                "key mismatch: C vs Am",
                "type match: kick",
            )
        )
        assert "bpm direct match" in text
        assert "type match" in text
        assert "key mismatch" not in text

    def test_falls_back_when_only_neutral_reasons(self):
        text = format_workbench_suggestion_reason(("bpm missing", "key missing"))
        assert "bpm missing" in text


class TestSuggestSimilarEdgeCases:
    def test_nan_bpm_rejected(self):
        reference = _row("ref", bpm=float("nan"))
        message = validate_workbench_matching_reference(reference)
        assert message is not None
        assert not math.isfinite(reference.bpm or 0)
