"""AQ7 synthetic structure/role/drop ground-truth corpus (#1024).

Generates deterministic WAV fixtures and canonical three-plane GT sidecars at
runtime under an external work directory. Committed audio binaries are
forbidden. Ground truth is generator-authored fixture specs only — never
derived from StructureV1 / ArrangementClassifier / SectionSignals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf

CORPUS_ID = "sample-brain.aq7.structure-role-drop.synthetic.v1"
DOCUMENT_TYPE = "sample-brain.aq7.structure-role-drop-corpus.v1"
CORPUS_VERSION = "1.0.0"
GENERATOR_ID = "sample-brain.aq7.structure-role-drop.generator.v1"
GENERATOR_SEED = 1024001
SAMPLE_RATE = 44100
LABEL_SOURCE = "synthetic_deterministic"
DEFAULT_BPM = 120.0

SPLITS: frozenset[str] = frozenset({"CALIBRATION", "TEST"})
ROLE_VOCABULARY: tuple[str, ...] = (
    "intro",
    "groove",
    "build",
    "drop",
    "breakdown",
    "outro",
    "unknown",
)
PLANE_TOKENS: tuple[str, ...] = ("aq7.boundary", "aq7.role", "aq7.drop_event")
BEATGRID_PROVENANCE_STATUSES: frozenset[str] = frozenset(
    {"authored_synthetic", "missing", "insufficient"}
)
ANNOTATION_STATUSES: frozenset[str] = frozenset(
    {"adjudicated", "single_source", "ambiguous", "unavailable"}
)

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class _BoundarySpec:
    boundary_id: str
    bar_index: int
    annotation_status: str = "single_source"


@dataclass(frozen=True)
class _SectionSpec:
    section_id: str
    start_bar: int
    end_bar: int
    role: str
    annotation_status: str = "single_source"


@dataclass(frozen=True)
class _DropEventSpec:
    event_id: str
    boundary_id: str
    bar_index: int
    annotation_status: str = "single_source"
    event_type: str = "drop_onset"


@dataclass(frozen=True)
class _FixtureSpec:
    fixture_id: str
    family: str
    split: str
    track_end_bar: int
    bpm: float
    boundaries: tuple[_BoundarySpec, ...]
    sections: tuple[_SectionSpec, ...]
    drop_events: tuple[_DropEventSpec, ...]
    plane_status: tuple[tuple[str, str], ...]
    beatgrid_status: str
    beatgrid_note: str
    # Distinct render knobs so WAV bytes stay unique across fixtures.
    pulse_hz: float
    tone_hz: float
    energy_scale: float
    # Non-reference audio distractor accents (not GT boundaries).
    distractor_bars: tuple[int, ...] = ()


def _fixture_id(family: str, split_token: str, nnn: int = 1) -> str:
    family_token = family.replace("_", "-")
    return f"aq7-synth-{family_token}-{split_token}-{nnn:03d}"


def _plane(
    boundary: str = "single_source",
    role: str = "single_source",
    drop: str = "single_source",
) -> tuple[tuple[str, str], ...]:
    return (
        ("aq7.boundary", boundary),
        ("aq7.role", role),
        ("aq7.drop_event", drop),
    )


def _authored_note() -> str:
    return "generator-authored synthetic grid; analyzer BeatGrid is never GT"


# Frozen fixture pack — exactly 10 families / IDs from the corpus contract.
_FIXTURE_SPECS: tuple[_FixtureSpec, ...] = (
    _FixtureSpec(
        fixture_id=_fixture_id("simple_clean", "cal"),
        family="simple_clean",
        split="CALIBRATION",
        track_end_bar=48,
        bpm=120.0,
        boundaries=(
            _BoundarySpec("b1", 16),
            _BoundarySpec("b2", 32),
        ),
        sections=(
            _SectionSpec("s0", 0, 16, "intro"),
            _SectionSpec("s1", 16, 32, "groove"),
            _SectionSpec("s2", 32, 48, "outro"),
        ),
        drop_events=(),
        plane_status=_plane(),
        beatgrid_status="authored_synthetic",
        beatgrid_note=_authored_note(),
        pulse_hz=880.0,
        tone_hz=110.0,
        energy_scale=0.72,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("repeated_structure", "cal"),
        family="repeated_structure",
        split="CALIBRATION",
        track_end_bar=64,
        bpm=124.0,
        boundaries=(
            _BoundarySpec("b1", 8),
            _BoundarySpec("b2", 24),
            _BoundarySpec("b3", 32),
            _BoundarySpec("b4", 48),
        ),
        sections=(
            _SectionSpec("s0", 0, 8, "intro"),
            _SectionSpec("s1", 8, 24, "groove"),
            _SectionSpec("s2", 24, 32, "build"),
            _SectionSpec("s3", 32, 48, "groove"),
            _SectionSpec("s4", 48, 64, "outro"),
        ),
        drop_events=(),
        plane_status=_plane(boundary="adjudicated", role="adjudicated"),
        beatgrid_status="authored_synthetic",
        beatgrid_note=_authored_note(),
        pulse_hz=660.0,
        tone_hz=98.0,
        energy_scale=0.68,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("near_boundary_tolerance", "cal"),
        family="near_boundary_tolerance",
        split="CALIBRATION",
        track_end_bar=40,
        bpm=118.0,
        boundaries=(
            # Canonical cut; ±1-bar tolerance exercise for later matchers.
            _BoundarySpec("b1", 16, annotation_status="adjudicated"),
            _BoundarySpec("b2", 32, annotation_status="single_source"),
        ),
        sections=(
            _SectionSpec("s0", 0, 16, "intro", annotation_status="adjudicated"),
            _SectionSpec("s1", 16, 32, "build", annotation_status="adjudicated"),
            _SectionSpec("s2", 32, 40, "outro"),
        ),
        drop_events=(),
        plane_status=_plane(boundary="adjudicated"),
        beatgrid_status="authored_synthetic",
        beatgrid_note=(
            "generator-authored synthetic grid; near-boundary ±1-bar tolerance case; "
            "analyzer BeatGrid is never GT"
        ),
        pulse_hz=740.0,
        tone_hz=130.0,
        energy_scale=0.70,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("role_ambiguity_unknown", "cal"),
        family="role_ambiguity_unknown",
        split="CALIBRATION",
        track_end_bar=40,
        bpm=122.0,
        boundaries=(
            _BoundarySpec("b1", 12),
            _BoundarySpec("b2", 28),
        ),
        sections=(
            _SectionSpec("s0", 0, 12, "intro"),
            # Semantic unknown — not annotation disagreement.
            _SectionSpec("s1", 12, 28, "unknown"),
            _SectionSpec("s2", 28, 40, "outro"),
        ),
        drop_events=(),
        plane_status=_plane(role="single_source"),
        beatgrid_status="authored_synthetic",
        beatgrid_note=_authored_note(),
        pulse_hz=520.0,
        tone_hz=165.0,
        energy_scale=0.55,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("annotation_disagreement", "cal"),
        family="annotation_disagreement",
        split="CALIBRATION",
        track_end_bar=36,
        bpm=120.0,
        boundaries=(
            _BoundarySpec("b1", 16, annotation_status="ambiguous"),
        ),
        sections=(
            _SectionSpec("s0", 0, 16, "groove", annotation_status="ambiguous"),
            _SectionSpec("s1", 16, 36, "breakdown", annotation_status="single_source"),
        ),
        drop_events=(),
        plane_status=_plane(boundary="ambiguous", role="ambiguous"),
        beatgrid_status="authored_synthetic",
        beatgrid_note=(
            "generator-authored synthetic grid; ambiguous loci for ignore-mask; "
            "analyzer BeatGrid is never GT"
        ),
        pulse_hz=910.0,
        tone_hz=78.0,
        energy_scale=0.63,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("over_segmentation_challenge", "cal"),
        family="over_segmentation_challenge",
        split="CALIBRATION",
        track_end_bar=48,
        bpm=128.0,
        # Coarse reference + denser non-reference distractor cues in audio.
        boundaries=(
            _BoundarySpec("b1", 12),
            _BoundarySpec("b2", 28),
            _BoundarySpec("b3", 36),
        ),
        sections=(
            _SectionSpec("s0", 0, 12, "intro"),
            _SectionSpec("s1", 12, 28, "build"),
            _SectionSpec("s2", 28, 36, "drop"),
            _SectionSpec("s3", 36, 48, "outro"),
        ),
        drop_events=(
            _DropEventSpec("e1", "b2", 28),
        ),
        plane_status=_plane(),
        beatgrid_status="authored_synthetic",
        beatgrid_note=_authored_note(),
        pulse_hz=1000.0,
        tone_hz=55.0,
        energy_scale=0.78,
        distractor_bars=(4, 8, 20),
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("drop_at_boundary", "test"),
        family="drop_at_boundary",
        split="TEST",
        track_end_bar=56,
        bpm=126.0,
        boundaries=(
            _BoundarySpec("b1", 16),
            _BoundarySpec("b2", 32),
            _BoundarySpec("b3", 48),
        ),
        sections=(
            _SectionSpec("s0", 0, 16, "intro"),
            _SectionSpec("s1", 16, 32, "build"),
            _SectionSpec("s2", 32, 48, "drop"),
            _SectionSpec("s3", 48, 56, "outro"),
        ),
        drop_events=(
            _DropEventSpec("e1", "b2", 32, annotation_status="adjudicated"),
        ),
        plane_status=_plane(drop="adjudicated"),
        beatgrid_status="authored_synthetic",
        beatgrid_note=_authored_note(),
        pulse_hz=480.0,
        tone_hz=220.0,
        energy_scale=0.80,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("drop_not_boundary_owner", "test"),
        family="drop_not_boundary_owner",
        split="TEST",
        track_end_bar=44,
        bpm=121.0,
        # Boundaries are owned by the boundary plane only; drop refs them.
        boundaries=(
            _BoundarySpec("b1", 12),
            _BoundarySpec("b2", 28),
        ),
        sections=(
            _SectionSpec("s0", 0, 12, "intro"),
            _SectionSpec("s1", 12, 28, "groove"),
            _SectionSpec("s2", 28, 44, "outro"),
        ),
        drop_events=(
            # Anchored to existing b2; must not invent a mid-section cut.
            _DropEventSpec("e1", "b2", 28),
        ),
        plane_status=_plane(),
        beatgrid_status="authored_synthetic",
        beatgrid_note=_authored_note(),
        pulse_hz=350.0,
        tone_hz=146.0,
        energy_scale=0.66,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("under_segmentation_challenge", "test"),
        family="under_segmentation_challenge",
        split="TEST",
        track_end_bar=64,
        bpm=116.0,
        # Dense reference cuts: a coarse one-/two-cut prediction under-segments.
        boundaries=(
            _BoundarySpec("b1", 8),
            _BoundarySpec("b2", 16),
            _BoundarySpec("b3", 32),
            _BoundarySpec("b4", 48),
        ),
        sections=(
            _SectionSpec("s0", 0, 8, "intro"),
            _SectionSpec("s1", 8, 16, "groove"),
            _SectionSpec("s2", 16, 32, "build"),
            _SectionSpec("s3", 32, 48, "drop"),
            _SectionSpec("s4", 48, 64, "outro"),
        ),
        drop_events=(),
        plane_status=_plane(),
        beatgrid_status="authored_synthetic",
        beatgrid_note=_authored_note(),
        pulse_hz=290.0,
        tone_hz=82.0,
        energy_scale=0.60,
    ),
    _FixtureSpec(
        fixture_id=_fixture_id("beatgrid_hold", "test"),
        family="beatgrid_hold",
        split="TEST",
        track_end_bar=32,
        bpm=120.0,
        boundaries=(
            _BoundarySpec("b1", 16, annotation_status="unavailable"),
        ),
        sections=(
            _SectionSpec("s0", 0, 16, "intro", annotation_status="unavailable"),
            _SectionSpec("s1", 16, 32, "groove", annotation_status="unavailable"),
        ),
        drop_events=(),
        plane_status=_plane(
            boundary="unavailable",
            role="unavailable",
            drop="unavailable",
        ),
        # Explicit HOLD path — no trustworthy seconds mapping.
        beatgrid_status="missing",
        beatgrid_note=(
            "BeatGrid provenance missing for HOLD path; analyzer BeatGrid is never GT; "
            "time_sec intentionally null"
        ),
        pulse_hz=410.0,
        tone_hz=190.0,
        energy_scale=0.50,
    ),
)

FIXTURE_MATRIX: tuple[dict[str, str], ...] = tuple(
    {
        "fixture_id": spec.fixture_id,
        "family": spec.family,
        "split": spec.split,
    }
    for spec in _FIXTURE_SPECS
)


def assert_work_dir_outside_repo(work_dir: Path, repo_root: Path) -> None:
    """Reject corpus material writes inside the repository tree."""
    target = work_dir.resolve()
    root = repo_root.resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return
    raise ValueError(f"work_dir must be outside repo: {target}")


def _seconds_per_bar(bpm: float) -> float:
    return (4.0 * 60.0) / float(bpm)


def _bar_to_time_sec(bar_index: int, bpm: float, *, provenance: str) -> float | None:
    if provenance != "authored_synthetic":
        return None
    return float(bar_index) * _seconds_per_bar(bpm)


def _ms_to_samples(ms: float, sample_rate: int = SAMPLE_RATE) -> int:
    return max(1, int(round((ms / 1000.0) * sample_rate)))


_ROLE_GAIN: dict[str, float] = {
    "intro": 0.35,
    "groove": 0.55,
    "build": 0.75,
    "drop": 0.95,
    "breakdown": 0.40,
    "outro": 0.30,
    "unknown": 0.45,
}
_ROLE_TONE_OFFSET_HZ: dict[str, float] = {
    "intro": 0.0,
    "groove": 12.0,
    "build": 24.0,
    "drop": 36.0,
    "breakdown": 8.0,
    "outro": 4.0,
    "unknown": 18.0,
}


def _role_gain(role: str) -> float:
    return _ROLE_GAIN.get(role, 0.50)


def _render_fixture(spec: _FixtureSpec, *, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    """Simple distinguishable energy/pulse/tonal layers — not a mini-DAW."""
    duration_sec = spec.track_end_bar * _seconds_per_bar(spec.bpm)
    n_total = max(1, int(round(duration_sec * sample_rate)))
    y = np.zeros(n_total, dtype=np.float32)
    t = np.arange(n_total, dtype=np.float32) / float(sample_rate)
    spb = _seconds_per_bar(spec.bpm)

    # Low tonal bed.
    bed = (
        spec.energy_scale
        * 0.22
        * np.sin(2.0 * np.pi * spec.tone_hz * t)
    ).astype(np.float32)
    y += bed

    # Section energy layers.
    for section in spec.sections:
        start = int(round(section.start_bar * spb * sample_rate))
        end = int(round(section.end_bar * spb * sample_rate))
        start = max(0, min(n_total, start))
        end = max(start, min(n_total, end))
        if end <= start:
            continue
        seg_t = t[start:end] - t[start]
        gain = _role_gain(section.role) * spec.energy_scale
        # Role-colored mid layer.
        mid_hz = spec.tone_hz * 2.0 + _ROLE_TONE_OFFSET_HZ.get(section.role, 0.0)
        mid = (gain * 0.35 * np.sin(2.0 * np.pi * mid_hz * seg_t)).astype(np.float32)
        if section.role == "build":
            ramp = np.linspace(0.4, 1.0, end - start, dtype=np.float32)
            mid *= ramp
        elif section.role == "drop":
            mid *= 1.15
            # Transient burst at section open.
            burst_n = min(end - start, _ms_to_samples(40.0, sample_rate))
            burst_env = np.exp(
                -np.arange(burst_n, dtype=np.float32) / float(sample_rate) * 60.0
            )
            y[start : start + burst_n] += (
                spec.energy_scale * 0.55 * burst_env
            ).astype(np.float32)
        y[start:end] += mid

    # Pulse grid (bar-locked clicks) for structure cues.
    pulse_n = max(1, _ms_to_samples(6.0, sample_rate))
    pulse_t = np.arange(pulse_n, dtype=np.float32) / float(sample_rate)
    pulse = (
        spec.energy_scale
        * 0.45
        * np.sin(2.0 * np.pi * spec.pulse_hz * pulse_t)
        * np.exp(-pulse_t * 800.0)
    ).astype(np.float32)
    bar_samples = max(1, int(round(spb * sample_rate)))
    for bar in range(spec.track_end_bar):
        start = bar * bar_samples
        if start >= n_total:
            break
        end = min(n_total, start + pulse_n)
        amp = 1.0 if bar % 4 == 0 else 0.55
        y[start:end] += (amp * pulse[: end - start]).astype(np.float32)

    # Boundary accents (neutral structure markers, not analyzer labels).
    for boundary in spec.boundaries:
        start = int(round(boundary.bar_index * spb * sample_rate))
        if start < 0 or start >= n_total:
            continue
        end = min(n_total, start + _ms_to_samples(12.0, sample_rate))
        accent_n = end - start
        accent_t = np.arange(accent_n, dtype=np.float32) / float(sample_rate)
        accent = (
            spec.energy_scale
            * 0.65
            * np.sin(2.0 * np.pi * (spec.pulse_hz * 1.5) * accent_t)
            * np.exp(-accent_t * 500.0)
        ).astype(np.float32)
        y[start:end] += accent

    # Non-reference distractor accents (over-segmentation challenge cues).
    ref_bars = {int(b.bar_index) for b in spec.boundaries}
    for bar in spec.distractor_bars:
        if int(bar) in ref_bars:
            continue
        start = int(round(int(bar) * spb * sample_rate))
        if start < 0 or start >= n_total:
            continue
        end = min(n_total, start + _ms_to_samples(12.0, sample_rate))
        accent_n = end - start
        accent_t = np.arange(accent_n, dtype=np.float32) / float(sample_rate)
        accent = (
            spec.energy_scale
            * 0.55
            * np.sin(2.0 * np.pi * (spec.pulse_hz * 1.35) * accent_t)
            * np.exp(-accent_t * 520.0)
        ).astype(np.float32)
        y[start:end] += accent

    # Drop-event accents at referenced boundary times (audio cue only).
    for event in spec.drop_events:
        start = int(round(event.bar_index * spb * sample_rate))
        if start < 0 or start >= n_total:
            continue
        end = min(n_total, start + _ms_to_samples(80.0, sample_rate))
        n = end - start
        env = np.linspace(1.0, 0.2, n, dtype=np.float32)
        noise = (np.sin(2.0 * np.pi * 40.0 * np.arange(n, dtype=np.float32) / sample_rate)).astype(
            np.float32
        )
        y[start:end] += (spec.energy_scale * 0.5 * env * noise).astype(np.float32)

    # Fixture-unique deterministic dither so WAV bytes never collide.
    seed = GENERATOR_SEED + sum(ord(c) for c in spec.fixture_id) * 17
    rng = np.random.default_rng(seed)
    y = y + (rng.standard_normal(n_total).astype(np.float32) * 1e-5)
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _fixture_gt_payload(spec: _FixtureSpec) -> dict[str, Any]:
    provenance = {
        "status": spec.beatgrid_status,
        "note": spec.beatgrid_note,
    }
    boundaries = [
        {
            "boundary_id": b.boundary_id,
            "bar_index": b.bar_index,
            "time_sec": _bar_to_time_sec(
                b.bar_index, spec.bpm, provenance=spec.beatgrid_status
            ),
            "annotation_status": b.annotation_status,
        }
        for b in spec.boundaries
    ]
    sections = [
        {
            "section_id": s.section_id,
            "start_bar": s.start_bar,
            "end_bar": s.end_bar,
            "role": s.role,
            "annotation_status": s.annotation_status,
        }
        for s in spec.sections
    ]
    drop_events = [
        {
            "event_id": e.event_id,
            "event_type": e.event_type,
            "boundary_id": e.boundary_id,
            "bar_index": e.bar_index,
            "annotation_status": e.annotation_status,
        }
        for e in spec.drop_events
    ]
    return {
        "document_type": DOCUMENT_TYPE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_id": GENERATOR_ID,
        "generator_seed": GENERATOR_SEED,
        "fixture_id": spec.fixture_id,
        "sample_rate": SAMPLE_RATE,
        "split": spec.split,
        "label_source": LABEL_SOURCE,
        "family": spec.family,
        "beatgrid_provenance": provenance,
        "boundaries": boundaries,
        "sections": sections,
        "drop_events": drop_events,
        "drop_events_complete": True,
        "plane_status": dict(spec.plane_status),
        "join_key": {
            "analysis_eval_record_id": spec.fixture_id,
            "note": "fixture_id is the portable #956 record_id join key; no host paths",
        },
    }


def _manifest_fixture_row(spec: _FixtureSpec) -> dict[str, Any]:
    return {
        "fixture_id": spec.fixture_id,
        "family": spec.family,
        "split": spec.split,
        "join_key": {"analysis_eval_record_id": spec.fixture_id},
    }


def _support_counts(fixture_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    split_counts = {"CALIBRATION": 0, "TEST": 0}
    for row in fixture_rows:
        split_counts[str(row["split"])] = split_counts.get(str(row["split"]), 0) + 1
    n = len(fixture_rows)
    return {
        "split": split_counts,
        "plane": {token: n for token in PLANE_TOKENS},
    }


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _schema_validators() -> (
    tuple[Callable[[dict[str, Any]], Any], Callable[[dict[str, Any]], Any]]
):
    """Consume Task-3 schema validators; do not duplicate schema logic here."""
    from src.aq7_structure_role_drop_schema import (  # noqa: PLC0415
        validate_aq7_fixture_gt,
        validate_aq7_manifest,
    )

    return validate_aq7_fixture_gt, validate_aq7_manifest


def _validate_fixture_specs() -> None:
    ids = [s.fixture_id for s in _FIXTURE_SPECS]
    if len(ids) != 10 or len(set(ids)) != 10:
        raise ValueError("FIXTURE_MATRIX must contain exactly 10 unique fixture ids")
    cal = [s for s in _FIXTURE_SPECS if s.split == "CALIBRATION"]
    test = [s for s in _FIXTURE_SPECS if s.split == "TEST"]
    if len(cal) != 6 or len(test) != 4:
        raise ValueError("split membership must be 6 CALIBRATION + 4 TEST")
    cal_ids = {s.fixture_id for s in cal}
    test_ids = {s.fixture_id for s in test}
    if not cal_ids.isdisjoint(test_ids):
        raise ValueError("fixture leakage across CALIBRATION/TEST")
    for spec in _FIXTURE_SPECS:
        if spec.split not in SPLITS:
            raise ValueError(f"invalid split for {spec.fixture_id}: {spec.split}")
        if spec.beatgrid_status not in BEATGRID_PROVENANCE_STATUSES:
            raise ValueError(
                f"invalid beatgrid provenance for {spec.fixture_id}: "
                f"{spec.beatgrid_status}"
            )
        boundary_ids = {b.boundary_id for b in spec.boundaries}
        bars = [b.bar_index for b in spec.boundaries]
        if bars != sorted(bars) or len(set(bars)) != len(bars):
            raise ValueError(f"boundaries must be unique ascending for {spec.fixture_id}")
        for section in spec.sections:
            if section.role not in ROLE_VOCABULARY:
                raise ValueError(
                    f"invalid role for {spec.fixture_id}/{section.section_id}: "
                    f"{section.role}"
                )
            if section.end_bar <= section.start_bar:
                raise ValueError(
                    f"invalid section span for {spec.fixture_id}/{section.section_id}"
                )
        for event in spec.drop_events:
            if event.boundary_id not in boundary_ids:
                raise ValueError(
                    f"drop event refs missing boundary in {spec.fixture_id}: "
                    f"{event.boundary_id}"
                )
            match = next(b for b in spec.boundaries if b.boundary_id == event.boundary_id)
            if match.bar_index != event.bar_index:
                raise ValueError(
                    f"drop bar mismatch for {spec.fixture_id}/{event.event_id}"
                )


def generate_aq7_structure_role_drop_corpus(
    work_dir: Path | str,
    *,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Write synthetic WAVs + GT sidecars under *work_dir* (must be outside repo)."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    target = Path(work_dir)
    assert_work_dir_outside_repo(target, root)
    _validate_fixture_specs()

    # Seed pinned for identity; waveforms are fully specified by fixture specs.
    np.random.default_rng(GENERATOR_SEED)

    audio_dir = target / "audio"
    gt_dir = target / "gt"
    audio_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    validate_gt, validate_manifest = _schema_validators()
    fixture_rows: list[dict[str, Any]] = []
    for spec in _FIXTURE_SPECS:
        wave = _render_fixture(spec)
        sf.write(
            audio_dir / f"{spec.fixture_id}.wav",
            wave,
            SAMPLE_RATE,
            subtype="PCM_16",
        )
        gt_payload = _fixture_gt_payload(spec)
        validate_gt(gt_payload)
        (gt_dir / f"{spec.fixture_id}.json").write_text(
            _canonical_json(gt_payload),
            encoding="utf-8",
        )
        fixture_rows.append(_manifest_fixture_row(spec))

    manifest: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_id": GENERATOR_ID,
        "generator_seed": GENERATOR_SEED,
        "fixtures": fixture_rows,
        "support_counts": _support_counts(fixture_rows),
    }
    validate_manifest(manifest)
    (target / "manifest.json").write_text(_canonical_json(manifest), encoding="utf-8")
    return manifest


__all__ = [
    "ANNOTATION_STATUSES",
    "BEATGRID_PROVENANCE_STATUSES",
    "CORPUS_ID",
    "CORPUS_VERSION",
    "DOCUMENT_TYPE",
    "FIXTURE_MATRIX",
    "GENERATOR_ID",
    "GENERATOR_SEED",
    "LABEL_SOURCE",
    "PLANE_TOKENS",
    "ROLE_VOCABULARY",
    "SAMPLE_RATE",
    "SPLITS",
    "assert_work_dir_outside_repo",
    "generate_aq7_structure_role_drop_corpus",
]
