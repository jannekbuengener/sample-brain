from __future__ import annotations

import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf

from .config import ANALYZE_SR
from .export_fl import CONF_KEY_MIN, key_to_tag


NOTE_FREQUENCIES: dict[str, float] = {
    "C": 261.63,
    "C#": 277.18,
    "D": 293.66,
    "D#": 311.13,
    "E": 329.63,
    "F": 349.23,
    "F#": 369.99,
    "G": 392.00,
    "G#": 415.30,
    "A": 440.00,
    "A#": 466.16,
    "B": 493.88,
}

BUCKET_LABELS: tuple[str, ...] = ("lt_0.40", "0.40_0.55", "0.55_0.70", "gte_0.70")


def _bucket_for_conf(conf: float) -> str:
    if conf < 0.40:
        return "lt_0.40"
    if conf < 0.55:
        return "0.40_0.55"
    if conf < 0.70:
        return "0.55_0.70"
    return "gte_0.70"


def _write_chord_wav(path: Path, root_hz: float, duration_sec: float = 2.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = ANALYZE_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    freqs = [root_hz, root_hz * 5.0 / 4.0, root_hz * 3.0 / 2.0]
    wave = sum(0.33 * np.sin(2.0 * np.pi * freq * t) for freq in freqs).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def _write_noise_wav(path: Path, duration_sec: float = 2.0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = ANALYZE_SR
    sample_count = max(1, int(sr * duration_sec))
    rng = np.random.default_rng(42)
    wave = rng.normal(0.0, 0.3, sample_count).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


@dataclass(frozen=True)
class KeyConfSampleRecord:
    fixture_name: str
    variant: str
    key: str | None
    key_conf: float | None
    export_tag: str | None
    bucket: str | None

    @property
    def exported(self) -> bool:
        return self.export_tag is not None


@dataclass
class KeyConfEvidenceResult:
    records: list[KeyConfSampleRecord] = field(default_factory=list)
    export_threshold: float = CONF_KEY_MIN

    @property
    def total(self) -> int:
        return len(self.records)

    @property
    def with_conf(self) -> list[KeyConfSampleRecord]:
        return [r for r in self.records if r.key_conf is not None]

    @property
    def conf_values(self) -> list[float]:
        return [float(r.key_conf) for r in self.with_conf if r.key_conf is not None]

    def bucket_counts(self) -> dict[str, int]:
        counts = {label: 0 for label in BUCKET_LABELS}
        for record in self.with_conf:
            if record.bucket is not None:
                counts[record.bucket] += 1
        return counts

    @property
    def export_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return sum(1 for r in self.records if r.exported) / self.total

    @property
    def min_conf(self) -> float | None:
        values = self.conf_values
        return min(values) if values else None

    @property
    def median_conf(self) -> float | None:
        values = self.conf_values
        return float(statistics.median(values)) if values else None

    @property
    def max_conf(self) -> float | None:
        values = self.conf_values
        return max(values) if values else None

    def recommendation(self) -> str:
        buckets = self.bucket_counts()
        with_conf = len(self.with_conf)
        if with_conf == 0:
            return "no_confidence_values -- analyze produced no key_conf on fixtures; check librosa/chroma availability"

        low_share = buckets["lt_0.40"] / with_conf
        mid_share = buckets["0.40_0.55"] / with_conf
        high_share = (buckets["0.55_0.70"] + buckets["gte_0.70"]) / with_conf

        if high_share >= 0.5 and low_share >= 0.2:
            return (
                "bimodal_fixture_set -- pure tones cluster high (~0.87+), "
                "polyphonic/percussive/noise cluster low (<0.40); "
                "keep CONF_KEY_MIN=0.55 for conservative FL export on current analyzer scale"
            )
        if mid_share > 0.3:
            return (
                "review_threshold -- many samples fall in 0.40-0.55 band; "
                "consider lowering CONF_KEY_MIN or adding a low-confidence tag tier"
            )
        return (
            "threshold_ok -- current 0.55 export gate separates high-confidence tonal "
            "fixtures from low-confidence polyphonic/percussive signals on peak/sum scale"
        )


def _generate_fixtures(work_dir: Path) -> list[tuple[Path, str, str]]:
    from tests.audio_fixtures import (
        write_kick_transient_wav,
        write_pulse_train_wav,
        write_sine_wav,
    )

    work_dir.mkdir(parents=True, exist_ok=True)
    fixtures: list[tuple[Path, str, str]] = []

    for note, hz in NOTE_FREQUENCIES.items():
        path = work_dir / f"sine_{note}.wav"
        write_sine_wav(path, duration_sec=2.0, frequency_hz=hz)
        fixtures.append((path, f"sine_{note}", "sine"))

    chord_specs = (("chord_C", 261.63), ("chord_A", 440.00))
    for name, hz in chord_specs:
        path = work_dir / f"{name}.wav"
        _write_chord_wav(path, hz)
        fixtures.append((path, name, "chord"))

    pulse_path = work_dir / "pulse_120.wav"
    write_pulse_train_wav(pulse_path, bpm=120.0, duration_sec=4.0)
    fixtures.append((pulse_path, "pulse_120", "pulse"))

    kick_path = work_dir / "kick_128.wav"
    write_kick_transient_wav(kick_path, bpm=128.0, duration_sec=4.0)
    fixtures.append((kick_path, "kick_128", "kick"))

    noise_path = work_dir / "noise.wav"
    _write_noise_wav(noise_path)
    fixtures.append((noise_path, "noise", "noise"))

    return fixtures


def run_key_conf_evidence(work_dir: Path) -> KeyConfEvidenceResult:
    from .analyze import estimate_key, safe_load

    fixtures = _generate_fixtures(work_dir)
    result = KeyConfEvidenceResult()

    for path, fixture_name, variant in fixtures:
        y, sr = safe_load(path)
        key, key_conf = estimate_key(y, sr) if y is not None and sr is not None else (None, None)
        export_tag = key_to_tag(key, key_conf)
        bucket = _bucket_for_conf(key_conf) if key_conf is not None else None
        result.records.append(
            KeyConfSampleRecord(
                fixture_name=fixture_name,
                variant=variant,
                key=key,
                key_conf=key_conf,
                export_tag=export_tag,
                bucket=bucket,
            )
        )

    return result


def print_key_conf_evidence_report(result: KeyConfEvidenceResult) -> None:
    print()
    print("=" * 72)
    print("Key Confidence Threshold Evidence")
    print("=" * 72)
    print()
    print(f"export_threshold={result.export_threshold}")
    print()
    print(f"{'fixture':>12}  {'variant':>8}  {'key':>4}  {'key_conf':>8}  {'export':>6}  {'tag':>8}")
    print("-" * 60)
    for record in result.records:
        conf_str = f"{record.key_conf:.4f}" if record.key_conf is not None else "None"
        export_str = "yes" if record.exported else "no"
        tag_str = record.export_tag or "-"
        print(
            f"{record.fixture_name:>12}  {record.variant:>8}  "
            f"{(record.key or '-'):>4}  {conf_str:>8}  {export_str:>6}  {tag_str:>8}"
        )

    print()
    print("--- Aggregate Metrics ---")
    print(f"  total:             {result.total}")
    print(f"  with_key_conf:     {len(result.with_conf)}")
    if result.min_conf is not None:
        print(
            f"  min/median/max:    {result.min_conf:.4f} / "
            f"{result.median_conf:.4f} / {result.max_conf:.4f}"
        )
    buckets = result.bucket_counts()
    for label in BUCKET_LABELS:
        print(f"  bucket_{label}:     {buckets[label]:3d}")
    print(f"  export_rate:       {result.export_rate * 100:.1f}%")
    print()
    print(f"  Recommendation: {result.recommendation()}")
    print()
    print("=" * 72)
    print()


def run_cli_key_conf_evidence(work_dir: Path) -> None:
    try:
        result = run_key_conf_evidence(work_dir)
    except ImportError as exc:
        print(f"[WARN] Key confidence evidence skipped (missing dependency): {exc}", file=sys.stderr)
        return
    except Exception as exc:
        print(f"[ERROR] Key confidence evidence failed: {exc}", file=sys.stderr)
        return

    print_key_conf_evidence_report(result)
