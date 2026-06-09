from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np


DEFAULT_BPM_CANDIDATES: tuple[float, ...] = (
    60, 70, 85, 100, 120, 128, 140, 160, 175,
)

CORRECT_RATIO_MIN = 0.95
CORRECT_RATIO_MAX = 1.05
HALF_RATIO_MIN = 0.45
HALF_RATIO_MAX = 0.55
DOUBLE_RATIO_MIN = 1.90
DOUBLE_RATIO_MAX = 2.10


def classify_bpm_error(actual_bpm: float | None, label_bpm: float) -> str:
    """Classify a BPM estimate against a known ground-truth label.

    Returns one of: correct, half, double, ambiguous, outlier.
    """
    if actual_bpm is None or actual_bpm <= 0:
        return "outlier"
    if label_bpm <= 0:
        return "outlier"

    ratio = actual_bpm / label_bpm

    if CORRECT_RATIO_MIN <= ratio <= CORRECT_RATIO_MAX:
        return "correct"
    if HALF_RATIO_MIN <= ratio <= HALF_RATIO_MAX:
        return "half"
    if DOUBLE_RATIO_MIN <= ratio <= DOUBLE_RATIO_MAX:
        return "double"
    if 0.2 < ratio < 5.0:
        return "ambiguous"
    return "outlier"


@dataclass(frozen=True)
class BpmSampleRecord:
    fixture_path: Path
    variant: str       # "pulse" or "kick"
    label_bpm: float
    actual_bpm: float | None
    error_class: str

    @property
    def ratio(self) -> float | None:
        if self.actual_bpm is not None and self.actual_bpm > 0 and self.label_bpm > 0:
            return self.actual_bpm / self.label_bpm
        return None


@dataclass
class BpmEvidenceResult:
    records: list[BpmSampleRecord] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.records)

    def _count(self, error_class: str) -> int:
        return sum(1 for r in self.records if r.error_class == error_class)

    def _pct(self, error_class: str) -> float:
        if self.total == 0:
            return 0.0
        return self._count(error_class) / self.total * 100.0

    @property
    def correct_pct(self) -> float:
        return self._pct("correct")

    @property
    def half_pct(self) -> float:
        return self._pct("half")

    @property
    def double_pct(self) -> float:
        return self._pct("double")

    @property
    def ambiguous_pct(self) -> float:
        return self._pct("ambiguous")

    @property
    def outlier_pct(self) -> float:
        return self._pct("outlier")

    @property
    def octave_error_pct(self) -> float:
        return self.half_pct + self.double_pct

    @property
    def mean_absolute_error(self) -> float:
        errors = []
        for r in self.records:
            if r.actual_bpm is not None and r.actual_bpm > 0:
                errors.append(abs(r.actual_bpm - r.label_bpm))
        if not errors:
            return 0.0
        return float(np.mean(errors))

    def recommendation(self) -> str:
        if self.octave_error_pct < 10.0:
            return (
                "low_octave_error -- octave errors below 10% on synthetic fixtures; "
                "no normalization may be needed for simple rhythmic signals"
            )
        if self.octave_error_pct < 30.0:
            return (
                "heuristic_clamp -- moderate octave error rate; "
                "a simple heuristic (bpm < 80 -> bpm*2; bpm > 200 -> bpm/2) "
                "may correct most cases without false positives"
            )
        return (
            "profile_or_ensemble -- high octave error rate; "
            "consider a profile-based normalization toggle or ensemble approach "
            "(onset_period + tempogram) before implementing a fixed strategy"
        )


def _generate_fixtures(work_dir: Path, bpm_candidates: tuple[float, ...]) -> list[tuple[Path, float, str]]:
    from tests.audio_fixtures import write_kick_transient_wav, write_pulse_train_wav

    fixtures: list[tuple[Path, float, str]] = []
    work_dir.mkdir(parents=True, exist_ok=True)

    for bpm in bpm_candidates:
        pulse_path = work_dir / f"pulse_{int(bpm)}bpm.wav"
        write_pulse_train_wav(pulse_path, bpm=bpm)
        fixtures.append((pulse_path, bpm, "pulse"))

        kick_path = work_dir / f"kick_{int(bpm)}bpm.wav"
        write_kick_transient_wav(kick_path, bpm=bpm)
        fixtures.append((kick_path, bpm, "kick"))

    return fixtures


def _extract_bpm(path: Path) -> float | None:
    from .analyze import safe_load

    y, sr = safe_load(path)
    if y is None or sr is None:
        return None

    try:
        import librosa
        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        if tempo is not None and np.ndim(tempo) == 0:
            scalar = float(tempo)
        elif hasattr(tempo, "item"):
            scalar = float(tempo.item())
        else:
            scalar = float(tempo)
        if scalar > 0:
            return scalar
    except Exception:
        pass
    return None


def run_bpm_evidence(
    work_dir: Path,
    bpm_candidates: tuple[float, ...] | None = None,
) -> BpmEvidenceResult:
    if bpm_candidates is None:
        bpm_candidates = DEFAULT_BPM_CANDIDATES

    fixtures = _generate_fixtures(work_dir, bpm_candidates)
    result = BpmEvidenceResult()

    for path, label_bpm, variant in fixtures:
        actual = _extract_bpm(path)
        error_class = classify_bpm_error(actual, label_bpm)
        result.records.append(
            BpmSampleRecord(
                fixture_path=path,
                variant=variant,
                label_bpm=label_bpm,
                actual_bpm=actual,
                error_class=error_class,
            )
        )

    return result


def print_bpm_evidence_report(result: BpmEvidenceResult) -> None:
    print()
    print("=" * 72)
    print("BPM Half/Double Detection Evidence")
    print("=" * 72)
    print()

    print(f"{'label_bpm':>10}  {'actual_bpm':>10}  {'variant':>6}  {'ratio':>8}  {'class':>10}")
    print("-" * 60)
    for r in result.records:
        actual_str = f"{r.actual_bpm:.1f}" if r.actual_bpm is not None else "None"
        ratio_str = f"{r.ratio:.3f}" if r.ratio is not None else "-"
        print(f"{r.label_bpm:10.0f}  {actual_str:>10}  {r.variant:>6}  {ratio_str:>8}  {r.error_class:>10}")

    print()
    print("--- Aggregate Metrics ---")
    print(f"  total:             {result.total}")
    print(f"  correct:           {result._count('correct'):3d}  ({result.correct_pct:5.1f}%)")
    print(f"  half:              {result._count('half'):3d}  ({result.half_pct:5.1f}%)")
    print(f"  double:            {result._count('double'):3d}  ({result.double_pct:5.1f}%)")
    print(f"  ambiguous:         {result._count('ambiguous'):3d}  ({result.ambiguous_pct:5.1f}%)")
    print(f"  outlier:           {result._count('outlier'):3d}  ({result.outlier_pct:5.1f}%)")
    print(f"  octave_error:      {result._count('half') + result._count('double'):3d}  ({result.octave_error_pct:5.1f}%)")
    print(f"  mean_abs_error:    {result.mean_absolute_error:.1f} BPM")
    print()
    print(f"  Recommendation: {result.recommendation()}")
    print()

    if result.octave_error_pct == 0.0:
        print(
            "[NOTE] Synthetic pulse/kick fixtures showed no octave errors. "
            "Real-world samples with ghost kicks, layering, or sparse rhythms "
            "may produce a higher error rate. This evidence represents a lower bound."
        )
        print()

    print("=" * 72)
    print()


def run_cli_bpm_evidence(work_dir: Path, bpm_candidates: tuple[float, ...] | None = None) -> None:
    try:
        result = run_bpm_evidence(work_dir, bpm_candidates=bpm_candidates)
    except ImportError as e:
        print(f"[WARN] BPM evidence skipped (missing dependency): {e}", file=sys.stderr)
        return
    except Exception as e:
        print(f"[ERROR] BPM evidence failed: {e}", file=sys.stderr)
        return

    print_bpm_evidence_report(result)
