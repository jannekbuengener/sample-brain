"""AQ7 synthetic structure/role/drop corpus schema and validation (#1024).

Identity constants, fixture GT / manifest validation, and load helpers.
Ground truth is generator-authored; this module never imports StructureV1 /
ArrangementClassifier / SectionSignals.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from src.analysis_eval_artifact import (
    AnalysisEvalArtifactError,
    assert_portable_value,
)

CORPUS_ID = "sample-brain.aq7.structure-role-drop.synthetic.v1"
DOCUMENT_TYPE = "sample-brain.aq7.structure-role-drop-corpus.v1"
CORPUS_VERSION = "1.0.0"
GENERATOR_ID = "sample-brain.aq7.structure-role-drop.generator.v1"
GENERATOR_SEED = 1024001
SAMPLE_RATE = 44100
LABEL_SOURCE = "synthetic_deterministic"
BOUNDARY_MATCH_TOLERANCE_BARS = 1

ROLE_VOCABULARY: tuple[str, ...] = (
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
    "unknown",
)
SPLITS: frozenset[str] = frozenset({"CALIBRATION", "TEST"})
ANNOTATION_STATUSES: frozenset[str] = frozenset(
    {"adjudicated", "single_source", "ambiguous", "unavailable"}
)
BEATGRID_PROVENANCE_STATUSES: frozenset[str] = frozenset(
    {"authored_synthetic", "missing", "insufficient"}
)
PLANE_TOKENS: tuple[str, ...] = ("aq7.boundary", "aq7.role", "aq7.drop_event")
DROP_EVENT_TYPE = "drop_onset"

FIXTURE_ID_RE = re.compile(r"^aq7-synth-[a-z0-9-]+-(cal|test)-\d{3}$")

# Frozen membership for manifest validation (family, fixture_id, split).
FROZEN_FIXTURE_MATRIX: tuple[tuple[str, str, str], ...] = (
    ("simple_clean", "aq7-synth-simple-clean-cal-001", "CALIBRATION"),
    ("repeated_structure", "aq7-synth-repeated-structure-cal-001", "CALIBRATION"),
    ("near_boundary_tolerance", "aq7-synth-near-boundary-tolerance-cal-001", "CALIBRATION"),
    ("role_ambiguity_unknown", "aq7-synth-role-ambiguity-unknown-cal-001", "CALIBRATION"),
    ("annotation_disagreement", "aq7-synth-annotation-disagreement-cal-001", "CALIBRATION"),
    (
        "over_segmentation_challenge",
        "aq7-synth-over-segmentation-challenge-cal-001",
        "CALIBRATION",
    ),
    ("drop_at_boundary", "aq7-synth-drop-at-boundary-test-001", "TEST"),
    ("drop_not_boundary_owner", "aq7-synth-drop-not-boundary-owner-test-001", "TEST"),
    (
        "under_segmentation_challenge",
        "aq7-synth-under-segmentation-challenge-test-001",
        "TEST",
    ),
    ("beatgrid_hold", "aq7-synth-beatgrid-hold-test-001", "TEST"),
)
FAMILY_VOCABULARY: frozenset[str] = frozenset(row[0] for row in FROZEN_FIXTURE_MATRIX)
_EXPECTED_BY_FIXTURE_ID: dict[str, tuple[str, str]] = {
    fixture_id: (family, split) for family, fixture_id, split in FROZEN_FIXTURE_MATRIX
}

# LF-normalized canonical GT sidecar digests for CORPUS_VERSION 1.0.0.
FROZEN_GT_SHA256: dict[str, str] = {
    "aq7-synth-simple-clean-cal-001": "04969cb5a3035a6d271a2c1e5b4d758075b8e6559700db1e30a8891b24568699",
    "aq7-synth-repeated-structure-cal-001": "d138738e7ffb2dbc8487c86de8da2c0fd273d1b3653da99c263319848229ade1",
    "aq7-synth-near-boundary-tolerance-cal-001": "ef8dc9b4df11426dcf657da91db3eb8b68e0a238e13dbebeee7ef175d2a79c94",
    "aq7-synth-role-ambiguity-unknown-cal-001": "b940baa344839a6900c79434675a7c2f348509ba3503a4aafc26c2ac67f6fb4e",
    "aq7-synth-annotation-disagreement-cal-001": "fb5f34df2dd90796a360da907a257fc18cbb2bda1842511cd6c05078f9c73bb2",
    "aq7-synth-over-segmentation-challenge-cal-001": "618249f91ea870970b15598a12bf047486fc2dc8b54f549414bf7c5b578ed25c",
    "aq7-synth-drop-at-boundary-test-001": "16e99d40b861cb58c5a2c5ccbc18577c662299da360fcaa205edf139fdc0c3db",
    "aq7-synth-drop-not-boundary-owner-test-001": "ab27daa782cc1b835845d36cd069654ca503795279729b5fc290a1a76ba7ab1b",
    "aq7-synth-under-segmentation-challenge-test-001": "08fc6e6a5eb387f88dd42731a41cb5b5a634a350eb943cbc85fb678d16a40cf3",
    "aq7-synth-beatgrid-hold-test-001": "87f96624608837923efe0f5278cf41fc5b6b9fc16d38b4eda2b95bb6d2dfa701",
}

_SECTION_BOUNDARY_OWNERSHIP_KEYS = frozenset(
    {
        "boundary_id",
        "bar_index",
        "boundary",
        "boundaries",
        "creates_boundary",
    }
)
_DROP_BOUNDARY_OWNERSHIP_KEYS = frozenset(
    {
        "boundary",
        "boundaries",
        "creates_boundary",
    }
)

_GT_REQUIRED_KEYS = frozenset(
    {
        "document_type",
        "corpus_id",
        "corpus_version",
        "generator_id",
        "generator_seed",
        "fixture_id",
        "sample_rate",
        "split",
        "label_source",
        "family",
        "beatgrid_provenance",
        "boundaries",
        "sections",
        "drop_events",
        "drop_events_complete",
        "plane_status",
        "join_key",
    }
)
_MANIFEST_REQUIRED_KEYS = frozenset(
    {
        "document_type",
        "corpus_id",
        "corpus_version",
        "generator_id",
        "generator_seed",
        "fixtures",
    }
)


def _fail(message: str) -> None:
    raise ValueError(message)


def _require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        _fail(f"{field} must be a mapping")
    return dict(value)


def _require_list(value: Any, field: str) -> list[Any]:
    if not isinstance(value, list):
        _fail(f"{field} must be a list")
    return value


def _require_str(value: Any, field: str) -> str:
    if type(value) is not str or not value.strip():
        _fail(f"{field} must be a non-empty string")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if type(value) is not bool:
        _fail(f"{field} must be a bool")
    return value


def _require_nonneg_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _fail(f"{field} must be a non-negative int")
    return value


def _require_annotation_status(value: Any, field: str) -> str:
    text = _require_str(value, field)
    if text not in ANNOTATION_STATUSES:
        _fail(f"{field} has unsupported annotation status: {text}")
    return text


def _assert_portable(payload: Any, *, field: str) -> None:
    try:
        assert_portable_value(payload, field=field)
    except AnalysisEvalArtifactError as exc:
        # Preserve fail-closed portable rules; normalize wording for callers.
        raise ValueError(str(exc)) from exc


def _validate_identity_fields(payload: Mapping[str, Any], *, context: str) -> None:
    if payload.get("document_type") != DOCUMENT_TYPE:
        _fail(f"{context} document_type mismatch")
    if payload.get("corpus_id") != CORPUS_ID:
        _fail(f"{context} corpus_id mismatch")
    if payload.get("corpus_version") != CORPUS_VERSION:
        _fail(f"{context} corpus_version mismatch")
    if payload.get("generator_id") != GENERATOR_ID:
        _fail(f"{context} generator_id mismatch")
    if payload.get("generator_seed") != GENERATOR_SEED:
        _fail(f"{context} generator_seed mismatch")


def _validate_fixture_id_split(fixture_id: str, split: str, *, field: str) -> None:
    if FIXTURE_ID_RE.fullmatch(fixture_id) is None:
        _fail(f"{field}: malformed fixture_id {fixture_id!r}")
    if split not in SPLITS:
        _fail(f"{field}: unsupported split {split!r}")
    marker = "-cal-" if split == "CALIBRATION" else "-test-"
    other = "-test-" if split == "CALIBRATION" else "-cal-"
    if marker not in fixture_id:
        _fail(f"{field}: fixture/split leak: {fixture_id!r} is not {split}")
    if other in fixture_id:
        _fail(f"{field}: fixture/split leak: {fixture_id!r} conflicts with {split}")


def _validate_beatgrid_provenance(
    prov: Any, *, boundaries: list[dict[str, Any]]
) -> str:
    mapping = _require_mapping(prov, "beatgrid_provenance")
    status = _require_str(mapping.get("status"), "beatgrid_provenance.status")
    if status not in BEATGRID_PROVENANCE_STATUSES:
        _fail(f"unsupported beatgrid provenance status: {status}")
    # Analyzer BeatGrid is never authority; only corpus-authored statuses allowed.
    if status != "authored_synthetic":
        for boundary in boundaries:
            if boundary.get("time_sec") is not None:
                _fail(
                    "beatgrid provenance missing/insufficient forbids boundary time_sec"
                )
    return status


def _validate_boundaries(raw: Any) -> list[dict[str, Any]]:
    items = _require_list(raw, "boundaries")
    seen_ids: set[str] = set()
    seen_bars: set[int] = set()
    boundaries: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        boundary = _require_mapping(item, f"boundaries[{index}]")
        boundary_id = _require_str(boundary.get("boundary_id"), f"boundaries[{index}].boundary_id")
        if boundary_id in seen_ids:
            _fail(f"duplicate boundary_id: {boundary_id}")
        seen_ids.add(boundary_id)
        bar_index = _require_nonneg_int(
            boundary.get("bar_index"), f"boundaries[{index}].bar_index"
        )
        if bar_index == 0:
            _fail("internal boundary bar_index must be > 0 (track start is not scored)")
        if bar_index in seen_bars:
            _fail(f"duplicate boundary bar_index: {bar_index}")
        seen_bars.add(bar_index)
        _require_annotation_status(
            boundary.get("annotation_status"),
            f"boundaries[{index}].annotation_status",
        )
        if "role" in boundary:
            _fail("boundary plane cannot carry role")
        if "event_type" in boundary:
            _fail("boundary plane cannot carry event_type")
        time_sec = boundary.get("time_sec", None)
        if time_sec is not None and (
            isinstance(time_sec, bool) or not isinstance(time_sec, (int, float))
        ):
            _fail(f"boundaries[{index}].time_sec must be null or a number")
        boundaries.append(boundary)
    return boundaries


def _validate_sections(
    raw: Any, *, boundary_bars: set[int]
) -> list[dict[str, Any]]:
    items = _require_list(raw, "sections")
    if not items:
        _fail("sections must be non-empty")
    sections: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(items):
        section = _require_mapping(item, f"sections[{index}]")
        ownership = _SECTION_BOUNDARY_OWNERSHIP_KEYS.intersection(section)
        if ownership:
            _fail(
                "role/section cannot define or own boundary fields: "
                + ", ".join(sorted(ownership))
            )
        section_id = _require_str(section.get("section_id"), f"sections[{index}].section_id")
        if section_id in seen_ids:
            _fail(f"duplicate section_id: {section_id}")
        seen_ids.add(section_id)
        start_bar = _require_nonneg_int(
            section.get("start_bar"), f"sections[{index}].start_bar"
        )
        end_bar = _require_nonneg_int(section.get("end_bar"), f"sections[{index}].end_bar")
        if end_bar <= start_bar:
            _fail(
                f"sections[{index}] must be half-open [start_bar, end_bar) "
                f"with end_bar > start_bar"
            )
        role = _require_str(section.get("role"), f"sections[{index}].role")
        if role not in ROLE_VOCABULARY:
            _fail(f"unsupported role: {role}")
        _require_annotation_status(
            section.get("annotation_status"),
            f"sections[{index}].annotation_status",
        )
        sections.append(section)

    ordered = sorted(sections, key=lambda s: (s["start_bar"], s["end_bar"], s["section_id"]))
    if ordered[0]["start_bar"] != 0:
        _fail("sections must start at bar 0 (track start)")
    for left, right in zip(ordered, ordered[1:]):
        if left["end_bar"] != right["start_bar"]:
            _fail("sections must form a contiguous boundary-derived partition")
        if left["start_bar"] == right["start_bar"]:
            _fail("overlapping or duplicate section extents")

    internal_cuts = {int(s["start_bar"]) for s in ordered if int(s["start_bar"]) > 0}
    if internal_cuts != boundary_bars:
        _fail(
            "section extents must reference existing boundary cuts only "
            f"(section cuts={sorted(internal_cuts)}, "
            f"boundaries={sorted(boundary_bars)})"
        )
    return sections


def _validate_drop_events(
    raw: Any,
    *,
    boundaries_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    items = _require_list(raw, "drop_events")
    seen_ids: set[str] = set()
    seen_boundary_anchors: set[str] = set()
    events: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        event = _require_mapping(item, f"drop_events[{index}]")
        ownership = _DROP_BOUNDARY_OWNERSHIP_KEYS.intersection(event)
        if ownership:
            _fail(
                "drop event cannot add or own boundary fields: "
                + ", ".join(sorted(ownership))
            )
        event_id = _require_str(event.get("event_id"), f"drop_events[{index}].event_id")
        if event_id in seen_ids:
            _fail(f"duplicate drop event_id: {event_id}")
        seen_ids.add(event_id)
        event_type = _require_str(event.get("event_type"), f"drop_events[{index}].event_type")
        if event_type != DROP_EVENT_TYPE:
            _fail(f"drop event_type must be {DROP_EVENT_TYPE}")
        boundary_id = _require_str(
            event.get("boundary_id"), f"drop_events[{index}].boundary_id"
        )
        if boundary_id not in boundaries_by_id:
            _fail(f"drop event references nonexistent boundary: {boundary_id}")
        if boundary_id in seen_boundary_anchors:
            _fail(f"duplicate drop event boundary anchor: {boundary_id}")
        seen_boundary_anchors.add(boundary_id)
        bar_index = _require_nonneg_int(
            event.get("bar_index"), f"drop_events[{index}].bar_index"
        )
        expected_bar = int(boundaries_by_id[boundary_id]["bar_index"])
        if bar_index != expected_bar:
            _fail(
                f"drop event bar_index {bar_index} inconsistent with boundary "
                f"{boundary_id} bar_index {expected_bar}"
            )
        _require_annotation_status(
            event.get("annotation_status"),
            f"drop_events[{index}].annotation_status",
        )
        events.append(event)
    return events


def _validate_plane_status(raw: Any) -> dict[str, str]:
    mapping = _require_mapping(raw, "plane_status")
    if set(mapping) != set(PLANE_TOKENS):
        _fail("plane_status must contain exactly aq7.boundary/role/drop_event")
    out: dict[str, str] = {}
    for plane in PLANE_TOKENS:
        out[plane] = _require_annotation_status(
            mapping.get(plane), f"plane_status.{plane}"
        )
    return out


def _validate_join_key(raw: Any, *, fixture_id: str) -> dict[str, Any]:
    mapping = _require_mapping(raw, "join_key")
    record_id = _require_str(
        mapping.get("analysis_eval_record_id"), "join_key.analysis_eval_record_id"
    )
    if record_id != fixture_id:
        _fail("join_key.analysis_eval_record_id must equal fixture_id")
    return mapping


def validate_aq7_fixture_gt(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a per-fixture AQ7 GT sidecar. Fail-closed; returns a shallow copy."""
    data = _require_mapping(payload, "aq7_fixture_gt")
    missing = sorted(_GT_REQUIRED_KEYS - set(data))
    if missing:
        _fail(f"malformed fixture GT; missing keys: {', '.join(missing)}")

    _assert_portable(data, field="aq7_fixture_gt")
    _validate_identity_fields(data, context="fixture GT")

    fixture_id = _require_str(data.get("fixture_id"), "fixture_id")
    split = _require_str(data.get("split"), "split")
    _validate_fixture_id_split(fixture_id, split, field="fixture GT")

    if data.get("sample_rate") != SAMPLE_RATE:
        _fail(f"sample_rate must be {SAMPLE_RATE}")
    if data.get("label_source") != LABEL_SOURCE:
        _fail(f"label_source must be {LABEL_SOURCE}")
    family = _require_str(data.get("family"), "family")
    if family not in FAMILY_VOCABULARY:
        _fail(f"unsupported family: {family}")
    expected = _EXPECTED_BY_FIXTURE_ID.get(fixture_id)
    if expected is None:
        _fail(f"fixture_id outside frozen corpus membership: {fixture_id}")
    expected_family, expected_split = expected
    if family != expected_family or split != expected_split:
        _fail(
            f"fixture/split/family mismatch for {fixture_id}: "
            f"got family={family} split={split}"
        )

    if data.get("analyzer_source") not in (None,):
        _fail("analyzer_source is forbidden; GT is generator-authored")

    boundaries = _validate_boundaries(data.get("boundaries"))
    _validate_beatgrid_provenance(data.get("beatgrid_provenance"), boundaries=boundaries)
    boundary_bars = {int(b["bar_index"]) for b in boundaries}
    boundaries_by_id = {str(b["boundary_id"]): b for b in boundaries}
    _validate_sections(data.get("sections"), boundary_bars=boundary_bars)
    _validate_drop_events(data.get("drop_events"), boundaries_by_id=boundaries_by_id)

    if data.get("drop_events_complete") is not True:
        _fail("drop_events_complete must be true")
    _validate_plane_status(data.get("plane_status"))
    _validate_join_key(data.get("join_key"), fixture_id=fixture_id)
    return dict(data)


def validate_aq7_manifest(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an AQ7 corpus manifest. Fail-closed; returns a shallow copy."""
    data = _require_mapping(payload, "aq7_manifest")
    missing = sorted(_MANIFEST_REQUIRED_KEYS - set(data))
    if missing:
        _fail(f"malformed manifest; missing keys: {', '.join(missing)}")

    _assert_portable(data, field="aq7_manifest")
    _validate_identity_fields(data, context="manifest")

    fixtures_raw = _require_list(data.get("fixtures"), "fixtures")
    if len(fixtures_raw) != len(FROZEN_FIXTURE_MATRIX):
        _fail(
            f"manifest fixture count must be {len(FROZEN_FIXTURE_MATRIX)} "
            f"(6 CALIBRATION + 4 TEST); got {len(fixtures_raw)}"
        )

    seen_ids: set[str] = set()
    split_counts = {"CALIBRATION": 0, "TEST": 0}
    for index, item in enumerate(fixtures_raw):
        fixture = _require_mapping(item, f"fixtures[{index}]")
        fixture_id = _require_str(fixture.get("fixture_id"), f"fixtures[{index}].fixture_id")
        family = _require_str(fixture.get("family"), f"fixtures[{index}].family")
        split = _require_str(fixture.get("split"), f"fixtures[{index}].split")
        if fixture_id in seen_ids:
            _fail(f"duplicate manifest fixture_id: {fixture_id}")
        seen_ids.add(fixture_id)
        _validate_fixture_id_split(fixture_id, split, field=f"fixtures[{index}]")
        expected = _EXPECTED_BY_FIXTURE_ID.get(fixture_id)
        if expected is None:
            _fail(f"unknown manifest fixture_id: {fixture_id}")
        expected_family, expected_split = expected
        if family != expected_family or split != expected_split:
            _fail(
                f"manifest fixture/split/family leak for {fixture_id}: "
                f"got family={family} split={split}"
            )
        join_key = _require_mapping(fixture.get("join_key"), f"fixtures[{index}].join_key")
        record_id = _require_str(
            join_key.get("analysis_eval_record_id"),
            f"fixtures[{index}].join_key.analysis_eval_record_id",
        )
        if record_id != fixture_id:
            _fail(
                f"fixtures[{index}].join_key.analysis_eval_record_id must equal fixture_id"
            )
        split_counts[split] += 1

    if seen_ids != set(_EXPECTED_BY_FIXTURE_ID):
        _fail("manifest fixture set does not match frozen corpus membership")
    if split_counts["CALIBRATION"] != 6 or split_counts["TEST"] != 4:
        _fail("manifest split membership must be 6 CALIBRATION + 4 TEST")

    support = data.get("support_counts")
    if support is not None:
        support_map = _require_mapping(support, "support_counts")
        split_support = _require_mapping(support_map.get("split"), "support_counts.split")
        if int(split_support.get("CALIBRATION", -1)) != 6 or int(
            split_support.get("TEST", -1)
        ) != 4:
            _fail("support_counts.split must report CALIBRATION=6 and TEST=4")
        plane_support = _require_mapping(support_map.get("plane"), "support_counts.plane")
        for plane in PLANE_TOKENS:
            if int(plane_support.get(plane, -1)) != len(FROZEN_FIXTURE_MATRIX):
                _fail(f"support_counts.plane.{plane} must equal fixture count")

    return dict(data)


def load_aq7_corpus_manifest(path: str | Path) -> dict[str, Any]:
    """Load and validate ``manifest.json`` from a corpus work directory."""
    manifest_path = Path(path)
    try:
        raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"unable to read AQ7 manifest: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed AQ7 manifest JSON: {manifest_path}") from exc
    return validate_aq7_manifest(raw)


def load_aq7_fixture_gt(path: str | Path) -> dict[str, Any]:
    """Load and validate a per-fixture GT sidecar JSON document."""
    gt_path = Path(path)
    try:
        text = gt_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"unable to read AQ7 fixture GT: {gt_path}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"malformed AQ7 fixture GT JSON: {gt_path}") from exc
    validated = validate_aq7_fixture_gt(raw)
    fixture_id = str(validated["fixture_id"])
    expected = FROZEN_GT_SHA256.get(fixture_id)
    if expected is not None:
        normalized = text.replace("\r\n", "\n")
        if not normalized.endswith("\n"):
            normalized += "\n"
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        if digest != expected:
            _fail(
                f"frozen GT digest mismatch for {fixture_id}: "
                f"got {digest}, expected {expected}"
            )
    return validated


__all__ = [
    "ANNOTATION_STATUSES",
    "BEATGRID_PROVENANCE_STATUSES",
    "BOUNDARY_MATCH_TOLERANCE_BARS",
    "CORPUS_ID",
    "CORPUS_VERSION",
    "DOCUMENT_TYPE",
    "DROP_EVENT_TYPE",
    "FAMILY_VOCABULARY",
    "FIXTURE_ID_RE",
    "FROZEN_FIXTURE_MATRIX",
    "FROZEN_GT_SHA256",
    "GENERATOR_ID",
    "GENERATOR_SEED",
    "LABEL_SOURCE",
    "PLANE_TOKENS",
    "ROLE_VOCABULARY",
    "SAMPLE_RATE",
    "SPLITS",
    "load_aq7_corpus_manifest",
    "load_aq7_fixture_gt",
    "validate_aq7_fixture_gt",
    "validate_aq7_manifest",
]
