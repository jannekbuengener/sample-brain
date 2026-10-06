"""AQ3 synthetic onset/attack timing ground-truth corpus (#993).

Generates deterministic WAV fixtures and canonical GT JSON sidecars at runtime
under an external work directory. Committed audio binaries are forbidden.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

CORPUS_ID = "sample-brain.aq3.timing.synthetic.v1"
DOCUMENT_TYPE = "sample-brain.aq3.timing-corpus.v1"
CORPUS_VERSION = "1.0.0"
GENERATOR_SEED = 993001
SAMPLE_RATE = 44100
LABEL_SOURCE = "synthetic_deterministic"

TOLERANCE_CANDIDATES_MS: tuple[int, ...] = (20, 50)

ACTIVE_BUCKETS: tuple[str, ...] = (
    "soft_attack",
    "silence_leading",
    "short_clip",
    "simple_multi_onset",
)
HOLD_BUCKETS: tuple[str, ...] = (
    "layered_transient_dense",
    "noisy",
)
SPLITS: frozenset[str] = frozenset({"CALIBRATION", "TEST"})

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class _ClipSpec:
    clip_id: str
    split: str
    buckets: tuple[str, ...]
    duration_ms: float
    onset_times_ms: tuple[float, ...]
    attack_marker_ms: float | None
    kind: str


# Thin deterministic coverage: each active bucket ≥1 clip; both splits present.
_CLIP_SPECS: tuple[_ClipSpec, ...] = (
    _ClipSpec(
        clip_id="aq3-synth-soft-attack-cal-001",
        split="CALIBRATION",
        buckets=("soft_attack",),
        duration_ms=800.0,
        onset_times_ms=(200.0,),
        attack_marker_ms=200.0,
        kind="soft_attack",
    ),
    _ClipSpec(
        clip_id="aq3-synth-silence-leading-cal-001",
        split="CALIBRATION",
        buckets=("silence_leading",),
        duration_ms=1000.0,
        onset_times_ms=(250.0,),
        attack_marker_ms=250.0,
        kind="hard_click",
    ),
    _ClipSpec(
        clip_id="aq3-synth-short-clip-test-001",
        split="TEST",
        buckets=("short_clip",),
        duration_ms=60.0,
        onset_times_ms=(10.0,),
        attack_marker_ms=10.0,
        kind="hard_click",
    ),
    _ClipSpec(
        clip_id="aq3-synth-multi-onset-test-001",
        split="TEST",
        buckets=("simple_multi_onset",),
        duration_ms=900.0,
        onset_times_ms=(100.0, 300.0, 550.0),
        attack_marker_ms=None,
        kind="hard_click",
    ),
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


def _ms_to_samples(ms: float, sample_rate: int = SAMPLE_RATE) -> int:
    return int(round((ms / 1000.0) * sample_rate))


def _hard_click(
    n_total: int,
    onset_times_ms: tuple[float, ...],
    *,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.85,
    click_ms: float = 4.0,
) -> np.ndarray:
    y = np.zeros(n_total, dtype=np.float32)
    click_n = max(1, _ms_to_samples(click_ms, sample_rate))
    t = np.arange(click_n, dtype=np.float32) / float(sample_rate)
    envelope = np.exp(-t * 900.0).astype(np.float32)
    pulse = (amplitude * np.sin(2.0 * np.pi * 1200.0 * t) * envelope).astype(np.float32)
    for onset_ms in onset_times_ms:
        start = _ms_to_samples(onset_ms, sample_rate)
        end = min(n_total, start + click_n)
        if start >= n_total or start < 0:
            continue
        y[start:end] += pulse[: end - start]
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _soft_attack(
    n_total: int,
    attack_ms: float,
    *,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.55,
) -> np.ndarray:
    """Gradual energy rise centered on the labeled attack/onset time."""
    t = np.arange(n_total, dtype=np.float32) / float(sample_rate)
    attack_sec = attack_ms / 1000.0
    # Logistic-like rise so GT attack_ms is the designed mid-rise reference.
    rise = 1.0 / (1.0 + np.exp(-40.0 * (t - attack_sec)))
    carrier = np.sin(2.0 * np.pi * 220.0 * t)
    y = (amplitude * rise * carrier).astype(np.float32)
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _render_clip(spec: _ClipSpec, *, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n_total = max(1, _ms_to_samples(spec.duration_ms, sample_rate))
    if spec.kind == "soft_attack":
        attack = spec.attack_marker_ms if spec.attack_marker_ms is not None else spec.onset_times_ms[0]
        return _soft_attack(n_total, attack, sample_rate=sample_rate)
    return _hard_click(n_total, spec.onset_times_ms, sample_rate=sample_rate)


def _clip_gt_payload(spec: _ClipSpec) -> dict[str, Any]:
    return {
        "document_type": DOCUMENT_TYPE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_seed": GENERATOR_SEED,
        "clip_id": spec.clip_id,
        "sample_rate": SAMPLE_RATE,
        "duration_ms": spec.duration_ms,
        "onset_times_ms": list(spec.onset_times_ms),
        "attack_marker_ms": spec.attack_marker_ms,
        "buckets": list(spec.buckets),
        "split": spec.split,
        "label_source": LABEL_SOURCE,
        "join_key": {
            "analysis_eval_record_id": spec.clip_id,
            "note": "clip_id is the portable #956 record_id join key; no host paths",
        },
    }


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def generate_aq3_timing_corpus(
    work_dir: Path | str,
    *,
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Write synthetic WAVs + GT sidecars under *work_dir* (must be outside repo)."""
    root = Path(repo_root) if repo_root is not None else _REPO_ROOT_DEFAULT
    target = Path(work_dir)
    assert_work_dir_outside_repo(target, root)

    # Seed is pinned for identity/reproducibility of any RNG use; waveforms are
    # fully specified by clip specs (no stochastic draws in v1).
    np.random.default_rng(GENERATOR_SEED)

    audio_dir = target / "audio"
    gt_dir = target / "gt"
    audio_dir.mkdir(parents=True, exist_ok=True)
    gt_dir.mkdir(parents=True, exist_ok=True)

    clip_rows: list[dict[str, Any]] = []
    for spec in _CLIP_SPECS:
        if spec.split not in SPLITS:
            raise ValueError(f"invalid split for {spec.clip_id}: {spec.split}")
        wave = _render_clip(spec)
        wav_path = audio_dir / f"{spec.clip_id}.wav"
        sf.write(wav_path, wave, SAMPLE_RATE, subtype="PCM_16")

        gt_payload = _clip_gt_payload(spec)
        (gt_dir / f"{spec.clip_id}.json").write_text(
            _canonical_json(gt_payload),
            encoding="utf-8",
        )
        clip_rows.append(
            {
                "clip_id": spec.clip_id,
                "sample_rate": SAMPLE_RATE,
                "duration_ms": spec.duration_ms,
                "onset_times_ms": list(spec.onset_times_ms),
                "attack_marker_ms": spec.attack_marker_ms,
                "buckets": list(spec.buckets),
                "split": spec.split,
                "label_source": LABEL_SOURCE,
                "join_key": {
                    "analysis_eval_record_id": spec.clip_id,
                    "note": "clip_id is the portable #956 record_id join key; no host paths",
                },
            }
        )

    manifest: dict[str, Any] = {
        "document_type": DOCUMENT_TYPE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_seed": GENERATOR_SEED,
        "sample_rate": SAMPLE_RATE,
        "tolerance_candidates_ms": list(TOLERANCE_CANDIDATES_MS),
        "active_buckets": list(ACTIVE_BUCKETS),
        "hold_buckets": list(HOLD_BUCKETS),
        "label_source": LABEL_SOURCE,
        "clips": clip_rows,
    }
    (target / "manifest.json").write_text(_canonical_json(manifest), encoding="utf-8")
    return manifest


__all__ = [
    "ACTIVE_BUCKETS",
    "CORPUS_ID",
    "CORPUS_VERSION",
    "DOCUMENT_TYPE",
    "GENERATOR_SEED",
    "HOLD_BUCKETS",
    "LABEL_SOURCE",
    "SAMPLE_RATE",
    "SPLITS",
    "TOLERANCE_CANDIDATES_MS",
    "assert_work_dir_outside_repo",
    "generate_aq3_timing_corpus",
]
