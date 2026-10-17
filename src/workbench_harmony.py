"""Workbench adapters and state over the neutral harmony owner."""
from __future__ import annotations

import time
from dataclasses import replace
from typing import Callable, Optional, Sequence, Tuple

from . import harmony
from .harmony import (
    HarmonyInput,
    HarmonyRelation,
    HarmonySuggestion,
    determine_relation as determine_relation,
)
from .key_signature import parse_key_signature
from .workbench_controller import (
    WorkbenchKeyAnalysisClaim,
    WorkbenchRow,
    validate_workbench_matching_reference,
)


def is_harmonic_match_claim_eligible(
    claim: WorkbenchKeyAnalysisClaim | None,
) -> bool:
    """True when a validated modeful V2 claim may be used as a Harmonic Match key.

    Fail closed. Does not consult ``matching_eligible``, ``key_conf``, or
    evidence blobs. Does not mutate ``claim``.
    """
    if claim is None:
        return False
    if not claim.valid:
        return False
    if claim.contract_version != 2:
        return False
    if claim.mode not in {"maj", "min"}:
        return False
    parsed = parse_key_signature(claim.key)
    if parsed is None or parsed.mode is None:
        return False
    return claim.mode == parsed.mode


def harmonic_match_key_for_row(row: WorkbenchRow) -> str | None:
    """Resolve a Harmonic Match key string from a Workbench row.

    Prefer an eligible V2 claim key. Otherwise fall back to the existing
    product ``row.key`` (V1/legacy). Pure: no DB access or mutation.
    """
    claim = row.key_analysis_claim
    if claim is not None and is_harmonic_match_claim_eligible(claim):
        return claim.key
    return row.key


def _harmony_input_for_row(row: WorkbenchRow) -> HarmonyInput:
    """Resolve Product key authority before crossing the neutral boundary."""
    return HarmonyInput(
        display_name=row.display_name,
        relative_path=row.relative_path,
        path=row.path,
        bpm=row.bpm,
        key=harmonic_match_key_for_row(row),
        pred_type=row.pred_type,
    )


def rate_harmony(
    reference: WorkbenchRow,
    candidate: WorkbenchRow,
    key_override: Optional[str] = None,
) -> HarmonySuggestion[WorkbenchRow]:
    """Delegate neutral rating and retain the original Product candidate."""
    suggestion = harmony.rate_harmony(
        _harmony_input_for_row(reference),
        _harmony_input_for_row(candidate),
        key_override=key_override,
    )
    return replace(suggestion, row=candidate)


def find_harmony_matches(
    reference: WorkbenchRow,
    candidates: list[WorkbenchRow],
    *,
    query: str = "",
    key_override: Optional[str] = None,
    limit: Optional[int] = None,
) -> Tuple[list[HarmonySuggestion[WorkbenchRow]], Optional[str]]:
    """Delegate ranking and map each projected object to its original row."""
    projected = [_harmony_input_for_row(row) for row in candidates]
    originals = {id(item): row for item, row in zip(projected, candidates, strict=True)}
    suggestions, error = harmony.find_harmony_matches(
        _harmony_input_for_row(reference),
        projected,
        query=query,
        key_override=key_override,
        limit=limit,
    )
    return [replace(suggestion, row=originals[id(suggestion.row)]) for suggestion in suggestions], error


class HarmonicMatchLibraryController:
    """Own an explicit Screen-1 harmony anchor and its match-only results."""

    def __init__(
        self,
        *,
        finder: Callable[..., Tuple[list[HarmonySuggestion], Optional[str]]] = find_harmony_matches,
        on_query_finished: Callable[..., None] | None = None,
    ) -> None:
        self._finder = finder
        self._on_query_finished = on_query_finished
        self.anchor: WorkbenchRow | None = None
        self.results: tuple[HarmonySuggestion, ...] = ()
        self.status = "Harmonic Match ist ausgeschaltet."

    def set_anchor(
        self, anchor: WorkbenchRow, candidates: Sequence[WorkbenchRow]
    ) -> None:
        """Promote one explicit anchor and refresh exactly once."""
        self.anchor = anchor
        self.results = ()
        matching_error = validate_workbench_matching_reference(anchor)
        if matching_error is not None:
            self.status = matching_error
            return
        anchor_key = harmonic_match_key_for_row(anchor)
        parsed_key = parse_key_signature(anchor_key) if anchor_key else None
        if parsed_key is None or parsed_key.mode is None:
            self.status = "Harmonic Match benötigt einen auswertbaren Referenz-Key."
            return

        eligible = [row for row in candidates if row.path != anchor.path]
        started = time.perf_counter()
        suggestions, finder_status = self._finder(anchor, eligible)
        visible = tuple(
            suggestion
            for suggestion in suggestions
            if suggestion.row.path != anchor.path
            and suggestion.relation is not HarmonyRelation.UNCERTAIN
            and not (
                suggestion.relation is HarmonyRelation.TRANSPOSE
                and (
                    suggestion.pitch_shift_semitones is None
                    or abs(suggestion.pitch_shift_semitones) > 3
                )
            )
        )
        wall_ms = max(0, int((time.perf_counter() - started) * 1000))
        self.results = visible
        if visible:
            self.status = f"{len(visible)} sichere Harmonic Matches."
        else:
            self.status = finder_status or "Keine sicheren Harmonic Matches gefunden."
        if self._on_query_finished is not None:
            try:
                self._on_query_finished(
                    wall_ms=wall_ms,
                    result_count=len(visible),
                    status="ok",
                )
            except Exception:
                pass

    def observe_selection(self, _row: WorkbenchRow) -> None:
        """Ordinary selection intentionally leaves the explicit anchor untouched."""

    def observe_audition(self, _row: WorkbenchRow) -> None:
        """Ordinary audition intentionally leaves the explicit anchor untouched."""
