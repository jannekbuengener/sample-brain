"""Producer-oriented stem grouping and kick+bassline reconstruction (issue #268).

This module defines the *deterministic derivation contract* that turns the
technical stems produced by #244/#249 (``drums``, ``bass``, ``vocals``,
``other``) into musically usable **producer groups** for loops and sections:

    kick_bass, drums, melodic, vocal, atmos_fx

Hard contract rules (see ``docs/PRODUCER_GROUP_V1.md``):
* ``kick_bass`` is the kick attack/body (extracted from the ``drums`` stem) PLUS
  the actual musical bassline (the ``bass`` stem). It is explicitly NOT
  ``drums + bass``.
* Low-frequency content alone is NEVER promoted to a bassline. If no usable
  ``bass`` stem exists, ``kick_bass`` is reported as ``no_result`` (the kick
  envelope may be inspected internally but is NOT emitted as a finished group).
* Every group carries its technical stems, components, masks/selection rules,
  summation, processing and a status (``ok`` | ``partial`` | ``no_result``).
* ``no_result`` is a first-class, valid outcome.

This is NOT a new stem-separation model. It only applies documented,
deterministic DSP helpers (onset-gated kick envelope on the drums low band, and
a standard harmonic/percussive split of ``other`` for best-effort melodic/atmos
proxies). The bassline is the separated ``bass`` stem, never a low-pass of the
drums' low end.

All outputs stay on the shared #234 sample timebase (``AudioTimebase``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

import numpy as np

from .canon_audio import CANONICAL_SAMPLE_RATE, AudioTimebase

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

PRODUCER_GROUP_DOCUMENT_TYPE = "sample_brain.producer_group"
PRODUCER_GROUP_SCHEMA_VERSION = "1.0.0"

GROUP_KINDS = {"kick_bass", "drums", "melodic", "vocal", "atmos_fx"}
# Technical stems this contract consumes (vocabulary from #244/#249).
TECHNICAL_STEM_KINDS = {"drums", "bass", "vocals", "other"}

ALLOWED_STATUS = {"ok", "partial", "no_result"}

# Stable reason codes for ``no_result``.
REASON_MISSING_STEM = "MISSING_SOURCE_STEM"
REASON_MISSING_BASSLINE = "MISSING_BASSLINE"
REASON_SILENT_INPUT = "SILENT_INPUT_SKIPPED"


@dataclass(frozen=True)
class ProducerGroupParams:
    """Tunable, deterministic derivation parameters (no randomness)."""

    sample_rate: int = CANONICAL_SAMPLE_RATE
    # Kick detection band (low-pass cutoff applied to the drums stem).
    kick_low_hz: float = 160.0
    kick_lp_order: int = 2
    # Envelope smoothing window (seconds) for the kick detection band.
    kick_env_win_sec: float = 0.004
    # Adaptive threshold window (seconds): local median * threshold_factor.
    kick_median_win_sec: float = 0.18
    kick_threshold_factor: float = 1.6
    # Gain decay after a kick onset (seconds, exp time constant).
    kick_decay_sec: float = 0.11
    # Minimum RMS (linear) for a stem to count as "present / audible".
    min_rms: float = 1e-4
    # librosa HPSS margin for the melodic/atmos_fx proxy of ``other``.
    hpss_margin: float = 1.0


# ---------------------------------------------------------------------------
# Producer group result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProducerGroup:
    """One derived producer group with full traceability.

    ``audio`` is ``None`` when ``status == "no_result"`` (nothing is fabricated).
    """

    group_kind: str
    group_id: str
    group_ref: str
    status: str
    timebase: AudioTimebase
    technical_stems: tuple[str, ...] = field(default_factory=tuple)
    components: tuple[dict, ...] = field(default_factory=tuple)
    masks: str = ""
    summation: str = ""
    processing: tuple[str, ...] = field(default_factory=tuple)
    reason_code: Optional[str] = None
    audio: Optional[np.ndarray] = None
    track_ref: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        """Compact, portable identity block for #250/#255 source traceability."""
        return {
            "source_kind": "producer_group",
            "producer_group_id": self.group_id,
            "producer_group_ref": self.group_ref,
            "group_kind": self.group_kind,
            "technical_stems": list(self.technical_stems),
        }


def _safe_group_ref(group_kind: str) -> str:
    return f"producergroup_{group_kind}"


def _safe_group_id(group_kind: str, track_ref: Optional[str]) -> str:
    if track_ref:
        return f"pg_{track_ref}_{group_kind}"
    return f"pg_{group_kind}"


# ---------------------------------------------------------------------------
# Kick envelope (deterministic helper, not a separation model)
# ---------------------------------------------------------------------------


def extract_kick_envelope(
    drums: np.ndarray, params: ProducerGroupParams
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return ``(gain, kick_component, drums_residual)``.

    ``gain`` is an onset-gated envelope over the drums low band: it jumps to 1.0
    at each detected kick onset and decays exponentially afterwards, so the
    actual kick attack/body is kept while the rest of the drums is suppressed.
    ``kick_component = drums * gain`` and ``drums_residual = drums * (1 - gain)``.

    This isolates the *kick* from the drum stem. It deliberately does NOT turn
    any low-frequency content into a bassline.
    """
    from scipy.signal import butter, filtfilt
    from scipy.ndimage import median_filter

    d = np.asarray(drums, dtype=np.float32)
    n = d.shape[0]
    sr = float(params.sample_rate)
    if n == 0:
        z = np.zeros(0, dtype=np.float32)
        return z, z, z

    nyq = sr / 2.0
    cutoff = min(params.kick_low_hz, nyq - 1.0)
    if cutoff <= 0.0:
        cutoff = nyq / 2.0
    b, a = butter(params.kick_lp_order, cutoff / nyq, btype="low")
    low = filtfilt(b, a, d.astype(np.float64)).astype(np.float32)

    env_win = max(1, int(params.kick_env_win_sec * sr))
    # Simple moving-average envelope (deterministic, symmetric).
    kernel = np.ones(env_win, dtype=np.float64) / env_win
    env = np.convolve(np.abs(low.astype(np.float64)), kernel, mode="same").astype(
        np.float32
    )

    median_win = max(3, int(params.kick_median_win_sec * sr))
    med = median_filter(env.astype(np.float64), size=median_win).astype(np.float32)
    thresh = (med * params.kick_threshold_factor).astype(np.float32)
    # Never gate on pure numerical noise.
    floor = float(np.max(np.abs(d)) * 1e-3) if d.size else 0.0
    active = (env > thresh) & (env > floor)

    decay_per_sample = float(np.exp(-1.0 / max(1e-6, (params.kick_decay_sec * sr))))
    gain = np.zeros(n, dtype=np.float32)
    active_i = np.flatnonzero(active)
    if active_i.size:
        # First active sample in each contiguous run is the onset.
        onset = np.zeros(n, dtype=bool)
        onset[active_i[np.concatenate(([True], np.diff(active_i) > 1))]] = True
        # Per-sample gate: 1 at onset, decaying until the next onset resets it.
        seg_id = np.cumsum(onset)
        onset_idx = np.where(onset)[0]
        seg_start = onset_idx[np.clip(seg_id - 1, 0, onset_idx.size - 1)]
        dist_from_onset = np.clip(np.arange(n, dtype=np.int64) - seg_start, 0, None)
        gain = np.power(decay_per_sample, dist_from_onset).astype(np.float32)
        # Keep active samples at least at the decay floor so the kick body holds.
        gain = np.where(active, np.maximum(gain, decay_per_sample), gain)
        # Onset sample is exactly 1.0.
        gain = np.where(onset, 1.0, gain)
    else:
        gain = np.zeros(n, dtype=np.float32)

    kick_component = (d * gain).astype(np.float32)
    drums_residual = (d - kick_component).astype(np.float32)
    return gain, kick_component, drums_residual


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------


def _rms(x: Optional[np.ndarray]) -> float:
    if x is None or x.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(x.astype(np.float64)))))


def _hpss_split(other: np.ndarray, margin: float) -> tuple[np.ndarray, np.ndarray]:
    """Deterministic harmonic/percussive split (librosa) of the ``other`` stem.

    Returns ``(harmonic, percussive)``. This is a standard DSP helper, not a
    trained stem-separation model. Used only as a best-effort proxy.
    """
    from librosa.effects import hpss

    y = np.asarray(other, dtype=np.float32)
    if y.size == 0:
        return y, y
    harmonic, percussive = hpss(y.astype(np.float64), margin=margin)
    return harmonic.astype(np.float32), percussive.astype(np.float32)


def _build_timebase(
    stems: Mapping[str, np.ndarray], params: ProducerGroupParams
) -> AudioTimebase:
    n_samples = 0
    for arr in stems.values():
        a = np.asarray(arr)
        if a.shape[0] > n_samples:
            n_samples = a.shape[0]
    return AudioTimebase(sample_rate=params.sample_rate, n_samples=n_samples)


def derive_producer_groups(
    stems: Mapping[str, np.ndarray],
    *,
    timebase: Optional[AudioTimebase] = None,
    track_ref: Optional[str] = None,
    params: Optional[ProducerGroupParams] = None,
) -> dict[str, ProducerGroup]:
    """Derive all five producer groups from technical stems.

    ``stems`` maps ``stem_kind`` -> mono float32 (or float64) array, all on the
    same sample timebase. Missing stems are treated as absent (never fabricated).
    """
    params = params or ProducerGroupParams()
    tb = timebase or _build_timebase(stems, params)

    def _get(kind: str) -> Optional[np.ndarray]:
        arr = stems.get(kind)
        if arr is None:
            return None
        a = np.asarray(arr, dtype=np.float32)
        if a.shape[0] == 0 or _rms(a) < params.min_rms:
            return None
        return a

    drums = _get("drums")
    bass = _get("bass")
    vocals = _get("vocals")
    other = _get("other")

    groups: dict[str, ProducerGroup] = {}

    # --- kick_bass ---
    if drums is not None and bass is not None:
        _, kick_component, _ = extract_kick_envelope(drums, params)
        kb_audio = (kick_component + bass).astype(np.float32)
        groups["kick_bass"] = ProducerGroup(
            group_kind="kick_bass",
            group_id=_safe_group_id("kick_bass", track_ref),
            group_ref=_safe_group_ref("kick_bass"),
            status="ok",
            timebase=tb,
            technical_stems=("drums", "bass"),
            components=(
                {
                    "stem_kind": "drums",
                    "role": "kick_attack_body",
                    "mask": "onset-gated kick envelope on drums low band",
                },
                {
                    "stem_kind": "bass",
                    "role": "musical_bassline",
                    "mask": "identity (separated bass stem)",
                },
            ),
            masks=(
                "kick = drums * onset_gated_lowband_envelope; "
                "bassline = bass stem (not a low-pass of drums)"
            ),
            summation="kick_component + bass_stem",
            processing=(
                "deterministic onset-gated kick envelope on drums low band",
                "sum kick_component with bass stem",
            ),
            audio=kb_audio,
            track_ref=track_ref,
        )
    else:
        # Hard rule: no usable bass stem => no kick_bass group is emitted.
        # The kick envelope may exist internally but is NOT a finished group.
        # Only actually-usable stems are recorded (a silent/absent bass is not
        # counted as a component).
        reason = REASON_MISSING_BASSLINE if drums is not None else REASON_MISSING_STEM
        present: list[str] = []
        if drums is not None:
            present.append("drums")
        if bass is not None:
            present.append("bass")
        groups["kick_bass"] = ProducerGroup(
            group_kind="kick_bass",
            group_id=_safe_group_id("kick_bass", track_ref),
            group_ref=_safe_group_ref("kick_bass"),
            status="no_result",
            timebase=tb,
            technical_stems=tuple(present),
            components=(),
            masks="kick_bass requires both a drums stem (for the kick) and a usable bass stem (for the musical bassline)",
            summation="",
            processing=(),
            reason_code=reason,
            audio=None,
            track_ref=track_ref,
        )

    # --- drums (non-kick residual) ---
    if drums is not None:
        _, _, drums_residual = extract_kick_envelope(drums, params)
        groups["drums"] = ProducerGroup(
            group_kind="drums",
            group_id=_safe_group_id("drums", track_ref),
            group_ref=_safe_group_ref("drums"),
            status="ok",
            timebase=tb,
            technical_stems=("drums",),
            components=(
                {
                    "stem_kind": "drums",
                    "role": "non_kick_percussion",
                    "mask": "1 - onset_gated_kick_envelope",
                },
            ),
            masks="drums_residual = drums * (1 - kick_gate)",
            summation="drums * (1 - kick_gate)",
            processing=("deterministic onset-gated kick envelope complement",),
            audio=drums_residual,
            track_ref=track_ref,
        )
    else:
        groups["drums"] = ProducerGroup(
            group_kind="drums",
            group_id=_safe_group_id("drums", track_ref),
            group_ref=_safe_group_ref("drums"),
            status="no_result",
            timebase=tb,
            technical_stems=(),
            components=(),
            masks="drums group requires a drums stem",
            summation="",
            processing=(),
            reason_code=REASON_MISSING_STEM,
            audio=None,
            track_ref=track_ref,
        )

    # --- vocal (identity) ---
    if vocals is not None:
        groups["vocal"] = ProducerGroup(
            group_kind="vocal",
            group_id=_safe_group_id("vocal", track_ref),
            group_ref=_safe_group_ref("vocal"),
            status="ok",
            timebase=tb,
            technical_stems=("vocals",),
            components=(
                {"stem_kind": "vocals", "role": "vocal", "mask": "identity"},
            ),
            masks="vocal = vocals stem",
            summation="vocals",
            processing=(),
            audio=vocals,
            track_ref=track_ref,
        )
    else:
        groups["vocal"] = ProducerGroup(
            group_kind="vocal",
            group_id=_safe_group_id("vocal", track_ref),
            group_ref=_safe_group_ref("vocal"),
            status="no_result",
            timebase=tb,
            technical_stems=(),
            components=(),
            masks="vocal group requires a vocals stem",
            summation="",
            processing=(),
            reason_code=REASON_MISSING_STEM,
            audio=None,
            track_ref=track_ref,
        )

    # --- melodic / atmos_fx (best-effort proxy from 'other' via HPSS) ---
    if other is not None:
        harmonic, percussive = _hpss_split(other, params.hpss_margin)
        groups["melodic"] = ProducerGroup(
            group_kind="melodic",
            group_id=_safe_group_id("melodic", track_ref),
            group_ref=_safe_group_ref("melodic"),
            status="partial",
            timebase=tb,
            technical_stems=("other",),
            components=(
                {
                    "stem_kind": "other",
                    "role": "melodic_harmonic_proxy",
                    "mask": "hpss harmonic",
                },
            ),
            masks="melodic = harmonic component of 'other' (HPSS); best-effort proxy, NOT a guaranteed lead/synth split",
            summation="hpss_harmonic(other)",
            processing=("librosa hpss harmonic component",),
            audio=harmonic,
            track_ref=track_ref,
        )
        groups["atmos_fx"] = ProducerGroup(
            group_kind="atmos_fx",
            group_id=_safe_group_id("atmos_fx", track_ref),
            group_ref=_safe_group_ref("atmos_fx"),
            status="partial",
            timebase=tb,
            technical_stems=("other",),
            components=(
                {
                    "stem_kind": "other",
                    "role": "atmos_fx_percussive_proxy",
                    "mask": "hpss percussive",
                },
            ),
            masks="atmos_fx = percussive component of 'other' (HPSS); best-effort proxy, NOT a guaranteed atmos/fx split",
            summation="hpss_percussive(other)",
            processing=("librosa hpss percussive component",),
            audio=percussive,
            track_ref=track_ref,
        )
    else:
        for kind in ("melodic", "atmos_fx"):
            groups[kind] = ProducerGroup(
                group_kind=kind,
                group_id=_safe_group_id(kind, track_ref),
                group_ref=_safe_group_ref(kind),
                status="no_result",
                timebase=tb,
                technical_stems=(),
                components=(),
                masks=f"{kind} group requires an 'other' stem",
                summation="",
                processing=(),
                reason_code=REASON_MISSING_STEM,
                audio=None,
                track_ref=track_ref,
            )

    return groups


# ---------------------------------------------------------------------------
# Manifest contract (validatable, mirrors STEM_MANIFEST_V1 validation style)
# ---------------------------------------------------------------------------


def build_producer_group_manifest(group: ProducerGroup) -> dict:
    """Build a portable Producer Group Manifest v1 dict from a result."""
    manifest: dict[str, object] = {
        "document_type": PRODUCER_GROUP_DOCUMENT_TYPE,
        "schema_version": PRODUCER_GROUP_SCHEMA_VERSION,
        "group_kind": group.group_kind,
        "group_id": group.group_id,
        "group_ref": group.group_ref,
        "status": group.status,
        "timebase": {
            "sample_rate_hz": group.timebase.sample_rate,
            "n_samples": group.timebase.n_samples,
        },
        "technical_stems": list(group.technical_stems),
        "components": [dict(c) for c in group.components],
        "masks": group.masks,
        "summation": group.summation,
        "processing": list(group.processing),
    }
    if group.track_ref is not None:
        manifest["track_ref"] = group.track_ref
    if group.status == "no_result":
        manifest["reason_code"] = group.reason_code
    return manifest


def validate_producer_group_manifest(manifest: dict) -> list[str]:
    """Return a list of contract violations (empty list == valid)."""
    errors: list[str] = []

    if manifest.get("document_type") != PRODUCER_GROUP_DOCUMENT_TYPE:
        errors.append(f"document_type must be {PRODUCER_GROUP_DOCUMENT_TYPE!r}")
    if manifest.get("schema_version") != PRODUCER_GROUP_SCHEMA_VERSION:
        errors.append(f"schema_version must be {PRODUCER_GROUP_SCHEMA_VERSION!r}")

    kind = manifest.get("group_kind")
    if kind not in GROUP_KINDS:
        errors.append(f"group_kind must be one of {GROUP_KINDS}, got {kind!r}")

    status = manifest.get("status")
    if status not in ALLOWED_STATUS:
        errors.append(f"status must be one of {ALLOWED_STATUS}, got {status!r}")

    for field_name in ("group_id", "group_ref", "masks"):
        if not isinstance(manifest.get(field_name), str) or not manifest.get(field_name):
            errors.append(f"{field_name} must be a non-empty string")
    # summation is meaningful only when audio is actually produced.
    if status != "no_result":
        if not isinstance(manifest.get("summation"), str) or not manifest.get("summation"):
            errors.append("summation must be a non-empty string")

    tb = manifest.get("timebase")
    if not isinstance(tb, dict):
        errors.append("timebase must be an object")
    else:
        for f in ("sample_rate_hz", "n_samples"):
            v = tb.get(f)
            if not isinstance(v, int) or (f == "sample_rate_hz" and v <= 0) or (
                f == "n_samples" and v < 0
            ):
                errors.append(f"timebase.{f} must be a non-negative integer")

    if not isinstance(manifest.get("technical_stems"), list):
        errors.append("technical_stems must be a list")
    else:
        for s in manifest["technical_stems"]:
            if s not in TECHNICAL_STEM_KINDS:
                errors.append(f"technical_stems entry must be one of {TECHNICAL_STEM_KINDS}, got {s!r}")

    if status == "no_result":
        rc = manifest.get("reason_code")
        if not isinstance(rc, str) or not rc:
            errors.append("reason_code must be a non-empty string when status is no_result")
    else:
        if not isinstance(manifest.get("components"), list) or not manifest.get("components"):
            errors.append("components must be a non-empty list when status is ok/partial")
        if not isinstance(manifest.get("processing"), list):
            errors.append("processing must be a list")

    return errors


def write_producer_group_audio(group: ProducerGroup, out_dir) -> Optional[str]:
    """Render the reconstructed group audio to a deterministic WAV (pilot use).

    Returns the relative ``file_ref`` or ``None`` when the group has no audio
    (``no_result``). Not used by the deterministic contract tests.
    """
    import soundfile as sf
    from pathlib import Path

    if group.audio is None:
        return None
    out_dir = Path(out_dir)
    assets_dir = out_dir / "producer_groups"
    assets_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{group.group_kind}.wav"
    path = assets_dir / fname
    sf.write(
        str(path),
        group.audio,
        group.timebase.sample_rate,
        subtype="PCM_16",
        format="WAV",
    )
    return f"producer_groups/{fname}"


__all__ = [
    "PRODUCER_GROUP_DOCUMENT_TYPE",
    "PRODUCER_GROUP_SCHEMA_VERSION",
    "GROUP_KINDS",
    "TECHNICAL_STEM_KINDS",
    "ALLOWED_STATUS",
    "REASON_MISSING_STEM",
    "REASON_MISSING_BASSLINE",
    "REASON_SILENT_INPUT",
    "ProducerGroupParams",
    "ProducerGroup",
    "extract_kick_envelope",
    "derive_producer_groups",
    "build_producer_group_manifest",
    "validate_producer_group_manifest",
    "write_producer_group_audio",
]
