"""AQ4 synthetic classification ground-truth corpus (#1021).

Generates deterministic WAV fixtures and canonical GT JSON sidecars at runtime
under an external work directory. Committed audio binaries are forbidden.

``sample_class`` and ``pred_type`` remain separate taxonomies in every GT row.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

CORPUS_ID = "sample-brain.aq4.classification.synthetic.v1"
DOCUMENT_TYPE = "sample-brain.aq4.classification-corpus.v1"
CORPUS_VERSION = "1.0.0"
GENERATOR_SEED = 1021001
SAMPLE_RATE = 44100
LABEL_SOURCE = "synthetic_deterministic"

SAMPLE_CLASS_LABELS: tuple[str, ...] = (
    "oneshot",
    "loop",
    "ambiguous",
    "unknown",
)
PRED_TYPE_LABELS: tuple[str, ...] = (
    "Kick",
    "Snare",
    "HiHat-Closed",
    "Impact",
    "Drone",
    "Pad",
    "Loop",
    "OneShot",
    "Drum Loop",
    "FX",
    "unknown",
)
SPLITS: frozenset[str] = frozenset({"CALIBRATION", "TEST"})

_REPO_ROOT_DEFAULT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class _ClipSpec:
    clip_id: str
    split: str
    sample_class: str
    pred_type: str
    label_status: str
    duration_ms: float
    kind: str
    frequency_hz: float


# Thin deterministic coverage: both taxonomies, both splits, ambiguous/unknown
# retained as explicit labels (not forced into clear classes).
_CLIP_SPECS: tuple[_ClipSpec, ...] = (
    _ClipSpec(
        clip_id="aq4-synth-kick-oneshot-cal-001",
        split="CALIBRATION",
        sample_class="oneshot",
        pred_type="Kick",
        label_status="clear",
        duration_ms=200.0,
        kind="decaying_tone",
        frequency_hz=60.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-snare-oneshot-cal-001",
        split="CALIBRATION",
        sample_class="oneshot",
        pred_type="Snare",
        label_status="clear",
        duration_ms=450.0,
        kind="decaying_tone",
        frequency_hz=220.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-drum-loop-cal-001",
        split="CALIBRATION",
        sample_class="loop",
        pred_type="Drum Loop",
        label_status="clear",
        duration_ms=2000.0,
        kind="pulse_train",
        frequency_hz=800.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-pad-loop-cal-001",
        split="CALIBRATION",
        sample_class="loop",
        pred_type="Pad",
        label_status="clear",
        duration_ms=3000.0,
        kind="sustained_tone",
        frequency_hz=196.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-ambiguous-boundary-cal-001",
        split="CALIBRATION",
        sample_class="ambiguous",
        pred_type="OneShot",
        label_status="ambiguous",
        duration_ms=1200.0,
        kind="decaying_tone",
        frequency_hz=330.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-hihat-oneshot-test-001",
        split="TEST",
        sample_class="oneshot",
        pred_type="HiHat-Closed",
        label_status="clear",
        duration_ms=150.0,
        kind="decaying_tone",
        frequency_hz=6000.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-impact-oneshot-test-001",
        split="TEST",
        sample_class="oneshot",
        pred_type="Impact",
        label_status="clear",
        duration_ms=900.0,
        kind="decaying_tone",
        frequency_hz=110.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-loop-test-001",
        split="TEST",
        sample_class="loop",
        pred_type="Loop",
        label_status="clear",
        duration_ms=1800.0,
        kind="pulse_train",
        frequency_hz=440.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-drone-loop-test-001",
        split="TEST",
        sample_class="loop",
        pred_type="Drone",
        label_status="clear",
        duration_ms=3500.0,
        kind="sustained_tone",
        frequency_hz=55.0,
    ),
    _ClipSpec(
        clip_id="aq4-synth-unknown-test-001",
        split="TEST",
        sample_class="unknown",
        pred_type="unknown",
        label_status="unknown",
        duration_ms=500.0,
        kind="decaying_tone",
        frequency_hz=1000.0,
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
    return max(1, int(round((ms / 1000.0) * sample_rate)))


def _decaying_tone(
    n_total: int,
    *,
    frequency_hz: float,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.75,
) -> np.ndarray:
    t = np.arange(n_total, dtype=np.float32) / float(sample_rate)
    decay = np.exp(-t * 8.0).astype(np.float32)
    y = (amplitude * np.sin(2.0 * np.pi * frequency_hz * t) * decay).astype(np.float32)
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _sustained_tone(
    n_total: int,
    *,
    frequency_hz: float,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.35,
) -> np.ndarray:
    t = np.arange(n_total, dtype=np.float32) / float(sample_rate)
    fade = min(n_total, _ms_to_samples(20.0, sample_rate))
    env = np.ones(n_total, dtype=np.float32)
    if fade > 1:
        ramp = np.linspace(0.0, 1.0, fade, dtype=np.float32)
        env[:fade] = ramp
        env[-fade:] = ramp[::-1]
    y = (amplitude * env * np.sin(2.0 * np.pi * frequency_hz * t)).astype(np.float32)
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _pulse_train(
    n_total: int,
    *,
    frequency_hz: float,
    sample_rate: int = SAMPLE_RATE,
    amplitude: float = 0.7,
    interval_ms: float = 250.0,
    pulse_ms: float = 8.0,
) -> np.ndarray:
    y = np.zeros(n_total, dtype=np.float32)
    pulse_n = max(1, _ms_to_samples(pulse_ms, sample_rate))
    interval_n = max(pulse_n + 1, _ms_to_samples(interval_ms, sample_rate))
    t = np.arange(pulse_n, dtype=np.float32) / float(sample_rate)
    envelope = np.exp(-t * 700.0).astype(np.float32)
    pulse = (amplitude * np.sin(2.0 * np.pi * frequency_hz * t) * envelope).astype(
        np.float32
    )
    start = 0
    while start < n_total:
        end = min(n_total, start + pulse_n)
        y[start:end] += pulse[: end - start]
        start += interval_n
    return np.clip(y, -1.0, 1.0).astype(np.float32)


def _render_clip(spec: _ClipSpec, *, sample_rate: int = SAMPLE_RATE) -> np.ndarray:
    n_total = _ms_to_samples(spec.duration_ms, sample_rate)
    if spec.kind == "sustained_tone":
        return _sustained_tone(
            n_total, frequency_hz=spec.frequency_hz, sample_rate=sample_rate
        )
    if spec.kind == "pulse_train":
        return _pulse_train(
            n_total, frequency_hz=spec.frequency_hz, sample_rate=sample_rate
        )
    return _decaying_tone(
        n_total, frequency_hz=spec.frequency_hz, sample_rate=sample_rate
    )


def _clip_gt_payload(spec: _ClipSpec) -> dict[str, Any]:
    return {
        "document_type": DOCUMENT_TYPE,
        "corpus_id": CORPUS_ID,
        "corpus_version": CORPUS_VERSION,
        "generator_seed": GENERATOR_SEED,
        "clip_id": spec.clip_id,
        "sample_rate": SAMPLE_RATE,
        "duration_ms": spec.duration_ms,
        "sample_class": spec.sample_class,
        "pred_type": spec.pred_type,
        "label_status": spec.label_status,
        "split": spec.split,
        "label_source": LABEL_SOURCE,
        "join_key": {
            "analysis_eval_record_id": spec.clip_id,
            "note": "clip_id is the portable #956 record_id join key; no host paths",
        },
    }


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def _support_counts(clip_rows: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    return {
        "sample_class": dict(Counter(c["sample_class"] for c in clip_rows)),
        "pred_type": dict(Counter(c["pred_type"] for c in clip_rows)),
        "split": dict(Counter(c["split"] for c in clip_rows)),
    }


def generate_aq4_classification_corpus(
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

    seen_ids: set[str] = set()
    clip_rows: list[dict[str, Any]] = []
    for spec in _CLIP_SPECS:
        if spec.split not in SPLITS:
            raise ValueError(f"invalid split for {spec.clip_id}: {spec.split}")
        if spec.sample_class not in SAMPLE_CLASS_LABELS:
            raise ValueError(
                f"invalid sample_class for {spec.clip_id}: {spec.sample_class}"
            )
        if spec.pred_type not in PRED_TYPE_LABELS:
            raise ValueError(f"invalid pred_type for {spec.clip_id}: {spec.pred_type}")
        if spec.clip_id in seen_ids:
            raise ValueError(f"duplicate clip_id (partition leakage): {spec.clip_id}")
        seen_ids.add(spec.clip_id)

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
                "sample_class": spec.sample_class,
                "pred_type": spec.pred_type,
                "label_status": spec.label_status,
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
        "sample_class_labels": list(SAMPLE_CLASS_LABELS),
        "pred_type_labels": list(PRED_TYPE_LABELS),
        "label_source": LABEL_SOURCE,
        "support_counts": _support_counts(clip_rows),
        "hold_notes": [
            "human_labeled_public_sanitized_corpus_HOLD",
            "descriptor_multilabel_gt_HOLD",
        ],
        "clips": clip_rows,
    }
    (target / "manifest.json").write_text(_canonical_json(manifest), encoding="utf-8")
    return manifest


__all__ = [
    "CORPUS_ID",
    "CORPUS_VERSION",
    "DOCUMENT_TYPE",
    "GENERATOR_SEED",
    "LABEL_SOURCE",
    "PRED_TYPE_LABELS",
    "SAMPLE_CLASS_LABELS",
    "SAMPLE_RATE",
    "SPLITS",
    "assert_work_dir_outside_repo",
    "generate_aq4_classification_corpus",
]
