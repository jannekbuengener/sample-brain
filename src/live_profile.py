"""Live performance deconstruction profile (issue #374).

This module defines the *compact, configurable live-performance layout* that a
deconstructed track should expose for live performance. It is intentionally
small and deliberately avoids candidate floods.

The profile consumes the truthful #268 producer-group audio (rendered from real
source stems via #373) and, optionally, the raw technical stems. It never falls
back to a master-low-frequency split or to the master track when a requested
element has no usable source: missing elements are reported as ``no_result``.

Layout contract (see issue #374):

PLAYABLE LOOPS (actively performed, bar-aligned):
    * ``kick_bass``  — the real #268 producer group (kick from drums + full
                       musical bass stem), default 4 bars.
    * ``drums``      — 1 spielbarer drum-loop (``drums_present``), default 4 bars.
    * optional 2nd drum state ``drums_reduced`` — only when musically evidenced
      (a clearly less-dense 4-bar region exists); truthful ``no_result``
      otherwise, never a duplicate.

FULL-LENGTH ARRANGEMENT TRACKS (separately switchable, never chopped):
    * ``vocals``     — full-length vocal (producer group ``vocal`` / ``vocals`` stem)
    * ``melodic``    — full-length melodic/instrument (producer group ``melodic``)
    * ``fx``         — full-length FX/atmos (producer group ``atmos_fx``)
    * ``other``      — full-length other useful material (raw ``other`` stem)

Loop length policy:
    * default 4 bars
    * 8 bars only when the caller explicitly allows it (``allow_8_bars``) and at
      least 8 bars are available
    * 16-bar loops are never selected (enforced by config validation)

Source/provenance truth is preserved on every element: each element records its
exact source kind and reference. No private/local paths are emitted.
"""

from __future__ import annotations

import json

import numpy as np
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional, Sequence

# Stable document identity for the live layout manifest.
LIVE_LAYOUT_DOCUMENT_TYPE = "sample_brain.live_layout"
LIVE_LAYOUT_SCHEMA_VERSION = "1.0.0"

# Allowed loop bar counts (16 is deliberately excluded).
ALLOWED_LOOP_BARS = (4, 8)
DEFAULT_LOOP_BARS = 4

# Element keys used throughout the layout.
ELEM_KICK_BASS = "kick_bass"
ELEM_DRUMS_PRESENT = "drums_present"
ELEM_DRUMS_REDUCED = "drums_reduced"
ELEM_VOCALS = "vocals"
ELEM_MELODIC = "melodic"
ELEM_FX = "fx"
ELEM_OTHER = "other"

ROLE_PLAYABLE_LOOP = "playable_loop"
ROLE_FULL_LENGTH = "full_length_track"

REASON_NO_SOURCE = "NO_USABLE_SOURCE"
REASON_NO_DISTINCT_REDUCED = "NO_DISTINCT_REDUCED_STATE"
REASON_INSUFFICIENT_BARS = "INSUFFICIENT_BARS_FOR_LOOP"


# ---------------------------------------------------------------------------
# Configuration (user-specified before deconstruction)
# ---------------------------------------------------------------------------


@dataclass
class LiveLayoutConfig:
    """Minimal user-specified live-performance layout.

    Every field is a deliberate opt-in; the profile only emits what is
    requested, which keeps the output compact (no candidate flood).
    """

    kick_bass: bool = True
    drums_states: int = 1  # 1 or 2
    vocals_full: bool = True
    melodic_full: bool = True
    fx_full: bool = True
    other_full: bool = False
    default_loop_bars: int = DEFAULT_LOOP_BARS
    allow_8_bars: bool = False

    def __post_init__(self) -> None:
        if self.default_loop_bars not in ALLOWED_LOOP_BARS:
            raise ValueError(
                f"default_loop_bars must be one of {ALLOWED_LOOP_BARS}; "
                f"got {self.default_loop_bars}"
            )
        if self.drums_states not in (1, 2):
            raise ValueError(
                f"drums_states must be 1 or 2; got {self.drums_states}"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "kick_bass": self.kick_bass,
            "drums_states": self.drums_states,
            "vocals_full": self.vocals_full,
            "melodic_full": self.melodic_full,
            "fx_full": self.fx_full,
            "other_full": self.other_full,
            "default_loop_bars": self.default_loop_bars,
            "allow_8_bars": self.allow_8_bars,
        }


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class LiveElement:
    """One live-performance element with full provenance."""

    element: str
    role: str
    status: str  # ok | partial | no_result
    source_kind: Optional[str]  # producer_group | stem | None
    source_ref: Optional[str]
    technical_stems: tuple[str, ...] = ()
    bars: Optional[int] = None
    full_length: bool = False
    audio_ref: Optional[str] = None
    reason_code: Optional[str] = None

    def as_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "element": self.element,
            "role": self.role,
            "status": self.status,
            "full_length": self.full_length,
        }
        if self.source_kind is not None:
            payload["source_kind"] = self.source_kind
            payload["source_ref"] = self.source_ref
            payload["technical_stems"] = list(self.technical_stems)
        if self.role == ROLE_PLAYABLE_LOOP:
            payload["bars"] = self.bars
        if self.audio_ref is not None:
            payload["audio_ref"] = self.audio_ref
        if self.status == "no_result":
            payload["reason_code"] = self.reason_code
        return payload


@dataclass
class LiveLayout:
    """The compact live-performance layout for one deconstructed track."""

    config: LiveLayoutConfig
    source_track_ref: Optional[str]
    playable_loops: list[LiveElement] = field(default_factory=list)
    full_length_tracks: list[LiveElement] = field(default_factory=list)

    @property
    def no_result_elements(self) -> list[str]:
        return [e.element for e in self.all_elements if e.status == "no_result"]

    @property
    def all_elements(self) -> list[LiveElement]:
        return list(self.playable_loops) + list(self.full_length_tracks)

    def as_dict(self) -> dict[str, object]:
        return {
            "document_type": LIVE_LAYOUT_DOCUMENT_TYPE,
            "schema_version": LIVE_LAYOUT_SCHEMA_VERSION,
            "profile_config": self.config.as_dict(),
            "source_track_ref": self.source_track_ref,
            "playable_loops": [e.as_dict() for e in self.playable_loops],
            "full_length_tracks": [e.as_dict() for e in self.full_length_tracks],
            "no_result_elements": self.no_result_elements,
        }


# ---------------------------------------------------------------------------
# Source resolution helpers
# ---------------------------------------------------------------------------


def _group_audio(pg) -> tuple[Optional[object], Optional[dict]]:
    """Return (audio, source_dict) from a ProducerGroup, or (None, None)."""
    if pg is None or pg.audio is None:
        return None, None
    src: dict[str, object] = {
        "kind": "producer_group",
        "group_kind": pg.group_kind,
        "group_id": pg.group_id,
        "group_ref": pg.group_ref,
        "technical_stems": list(pg.technical_stems),
    }
    return pg.audio, src


def _resolve_source(
    element_key: str,
    producer_groups: Mapping[str, object],
    stems: Mapping[str, object],
):
    """Resolve the truthful source audio + provenance for an element.

    Returns (audio_or_None, source_dict_or_None). Never fabricates: missing
    sources yield (None, None). No master fallback is ever performed.
    """
    if element_key == ELEM_KICK_BASS:
        audio, src = _group_audio(producer_groups.get("kick_bass"))
        return audio, src
    if element_key in (ELEM_DRUMS_PRESENT, ELEM_DRUMS_REDUCED):
        audio, src = _group_audio(producer_groups.get("drums"))
        return audio, src
    if element_key == ELEM_VOCALS:
        audio, src = _group_audio(producer_groups.get("vocal"))
        if audio is not None:
            return audio, src
        arr = stems.get("vocals")
        if arr is not None:
            return arr, {"kind": "stem", "stem_kind": "vocals",
                         "technical_stems": ["vocals"]}
        return None, None
    if element_key == ELEM_MELODIC:
        audio, src = _group_audio(producer_groups.get("melodic"))
        return audio, src
    if element_key == ELEM_FX:
        audio, src = _group_audio(producer_groups.get("atmos_fx"))
        return audio, src
    if element_key == ELEM_OTHER:
        arr = stems.get("other")
        if arr is not None:
            return arr, {"kind": "stem", "stem_kind": "other",
                         "technical_stems": ["other"]}
        return None, None
    return None, None


# ---------------------------------------------------------------------------
# Loop region selection (bar-aligned, no 16-bar default)
# ---------------------------------------------------------------------------


def _loop_bar_count(config: LiveLayoutConfig, n_bars_available: int) -> int:
    """Decide the loop length; never 16 bars."""
    if config.allow_8_bars and config.default_loop_bars == 8 and n_bars_available >= 9:
        return 8
    return 4


def _per_bar_rms(audio: object, bars: Sequence[int]) -> list[float]:
    import numpy as np

    a = np.asarray(audio, dtype=np.float64)
    out: list[float] = []
    for i in range(len(bars) - 1):
        seg = a[bars[i] : bars[i + 1]]
        if seg.size == 0:
            out.append(0.0)
        else:
            out.append(float(np.sqrt(np.mean(np.square(seg)))))
    return out


def _find_reduced_drum_window(
    drums_audio: object, bars: Sequence[int], reduced_ratio: float = 0.66
) -> Optional[int]:
    """Find the start bar of a clearly less-dense 4-bar drum region.

    Evidence rule: a 4-bar window whose mean RMS is at or below ``reduced_ratio``
    of the global mean AND a clearly denser region exists. Returns the start bar
    index, or ``None`` when no distinct reduced state is evidenced.
    """
    import numpy as np

    if len(bars) < 5:
        return None
    rms = _per_bar_rms(drums_audio, bars)
    if not rms:
        return None
    rms_arr = np.asarray(rms, dtype=float)
    global_mean = float(np.mean(rms_arr))
    if global_mean <= 0.0:
        return None
    # Candidate reduced windows: every 4-bar window.
    best_start: Optional[int] = None
    best_mean = float("inf")
    for start in range(0, len(rms) - 3):
        window = rms_arr[start : start + 4]
        wmean = float(np.mean(window))
        if wmean <= reduced_ratio * global_mean and wmean < best_mean:
            best_mean = wmean
            best_start = start
    if best_start is None:
        return None
    # There must be a clearly denser region elsewhere for a real contrast.
    max_mean = float(np.max(rms_arr))
    if max_mean < global_mean * 1.05:
        return None
    return best_start


def _slice_loop(
    audio: object, bars: Sequence[int], bar_count: int, start_bar: int = 0
) -> Optional[tuple[int, int, int]]:
    """Return (start_sample, end_sample, n_samples) for a bar-aligned loop.

    Returns ``None`` when the requested window cannot be formed (too few bars).
    """
    if bars is None or len(bars) < bar_count + 1:
        return None
    start = bars[start_bar]
    end = bars[start_bar + bar_count]
    if end <= start:
        return None
    return start, end, end - start


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


def build_live_layout(
    producer_groups: Mapping[str, object],
    stems: Mapping[str, object],
    config: LiveLayoutConfig,
    *,
    bars: Optional[Sequence[int]] = None,
    pack_root: Optional[Path] = None,
    sample_rate: int = 44100,
    source_track_ref: Optional[str] = None,
) -> LiveLayout:
    """Build the compact live-performance layout.

    ``producer_groups`` are the truthful #268 groups (kick_bass, drums, vocal,
    melodic, atmos_fx). ``stems`` are the raw technical stems (drums, bass,
    vocals, other). ``bars`` are bar-boundary sample indices used to slice
    bar-aligned loops. ``pack_root`` (when given) receives deterministic WAV
    files under ``live/`` and the audio references are set.
    """
    if bars is not None:
        bars = [int(b) for b in bars]

    n_bars = len(bars) - 1 if bars else 0
    loop_bars = _loop_bar_count(config, n_bars)

    layout = LiveLayout(
        config=config, source_track_ref=source_track_ref
    )

    # --- playable loops ---
    if config.kick_bass:
        layout.playable_loops.append(
            _build_loop_element(
                ELEM_KICK_BASS, producer_groups, stems, bars, loop_bars,
                pack_root, sample_rate, source_track_ref,
            )
        )

    if config.drums_states >= 1:
        layout.playable_loops.append(
            _build_loop_element(
                ELEM_DRUMS_PRESENT, producer_groups, stems, bars, loop_bars,
                pack_root, sample_rate, source_track_ref,
            )
        )

    if config.drums_states >= 2:
        layout.playable_loops.append(
            _build_drums_reduced(
                producer_groups, stems, bars, loop_bars, pack_root,
                sample_rate, source_track_ref,
            )
        )

    # --- full-length arrangement tracks ---
    if config.vocals_full:
        layout.full_length_tracks.append(
            _build_full_length_element(
                ELEM_VOCALS, producer_groups, stems, pack_root, sample_rate,
                source_track_ref,
            )
        )
    if config.melodic_full:
        layout.full_length_tracks.append(
            _build_full_length_element(
                ELEM_MELODIC, producer_groups, stems, pack_root, sample_rate,
                source_track_ref,
            )
        )
    if config.fx_full:
        layout.full_length_tracks.append(
            _build_full_length_element(
                ELEM_FX, producer_groups, stems, pack_root, sample_rate,
                source_track_ref,
            )
        )
    if config.other_full:
        layout.full_length_tracks.append(
            _build_full_length_element(
                ELEM_OTHER, producer_groups, stems, pack_root, sample_rate,
                source_track_ref,
            )
        )

    return layout


def _build_loop_element(
    element_key: str,
    producer_groups,
    stems,
    bars,
    loop_bars,
    pack_root,
    sample_rate,
    source_track_ref,
) -> LiveElement:
    audio, src = _resolve_source(element_key, producer_groups, stems)
    if audio is None or src is None:
        return LiveElement(
            element=element_key,
            role=ROLE_PLAYABLE_LOOP,
            status="no_result",
            source_kind=None,
            source_ref=None,
            bars=loop_bars,
            full_length=False,
            audio_ref=None,
            reason_code=REASON_NO_SOURCE,
        )
    region = _slice_loop(audio, bars, loop_bars)
    if region is None:
        return LiveElement(
            element=element_key,
            role=ROLE_PLAYABLE_LOOP,
            status="no_result",
            source_kind=src["kind"],
            source_ref=src.get("group_ref") or src.get("stem_kind"),
            technical_stems=tuple(src.get("technical_stems", [])),
            bars=loop_bars,
            full_length=False,
            audio_ref=None,
            reason_code=REASON_INSUFFICIENT_BARS,
        )
    start, end, _ = region
    import numpy as np

    loop_audio = np.asarray(audio, dtype=np.float32)[start:end]
    audio_ref = _write_audio(pack_root, element_key, loop_audio, sample_rate)
    return LiveElement(
        element=element_key,
        role=ROLE_PLAYABLE_LOOP,
        status="ok",
        source_kind=src["kind"],
        source_ref=src.get("group_ref") or src.get("stem_kind"),
        technical_stems=tuple(src.get("technical_stems", [])),
        bars=loop_bars,
        full_length=False,
        audio_ref=audio_ref,
    )


def _build_drums_reduced(
    producer_groups,
    stems,
    bars,
    loop_bars,
    pack_root,
    sample_rate,
    source_track_ref,
) -> LiveElement:
    audio, src = _resolve_source(ELEM_DRUMS_REDUCED, producer_groups, stems)
    if audio is None or src is None:
        return LiveElement(
            element=ELEM_DRUMS_REDUCED,
            role=ROLE_PLAYABLE_LOOP,
            status="no_result",
            source_kind=None,
            source_ref=None,
            bars=loop_bars,
            full_length=False,
            audio_ref=None,
            reason_code=REASON_NO_SOURCE,
        )
    start_bar = _find_reduced_drum_window(audio, bars) if bars else None
    if start_bar is None:
        return LiveElement(
            element=ELEM_DRUMS_REDUCED,
            role=ROLE_PLAYABLE_LOOP,
            status="no_result",
            source_kind=src["kind"],
            source_ref=src.get("group_ref") or src.get("stem_kind"),
            technical_stems=tuple(src.get("technical_stems", [])),
            bars=loop_bars,
            full_length=False,
            audio_ref=None,
            reason_code=REASON_NO_DISTINCT_REDUCED,
        )
    region = _slice_loop(audio, bars, loop_bars, start_bar=start_bar)
    if region is None:
        return LiveElement(
            element=ELEM_DRUMS_REDUCED,
            role=ROLE_PLAYABLE_LOOP,
            status="no_result",
            source_kind=src["kind"],
            source_ref=src.get("group_ref") or src.get("stem_kind"),
            technical_stems=tuple(src.get("technical_stems", [])),
            bars=loop_bars,
            full_length=False,
            audio_ref=None,
            reason_code=REASON_INSUFFICIENT_BARS,
        )
    start, end, _ = region
    import numpy as np

    loop_audio = np.asarray(audio, dtype=np.float32)[start:end]
    audio_ref = _write_audio(pack_root, ELEM_DRUMS_REDUCED, loop_audio, sample_rate)
    return LiveElement(
        element=ELEM_DRUMS_REDUCED,
        role=ROLE_PLAYABLE_LOOP,
        status="ok",
        source_kind=src["kind"],
        source_ref=src.get("group_ref") or src.get("stem_kind"),
        technical_stems=tuple(src.get("technical_stems", [])),
        bars=loop_bars,
        full_length=False,
        audio_ref=audio_ref,
    )


def _build_full_length_element(
    element_key: str,
    producer_groups,
    stems,
    pack_root,
    sample_rate,
    source_track_ref,
) -> LiveElement:
    audio, src = _resolve_source(element_key, producer_groups, stems)
    if audio is None or src is None:
        return LiveElement(
            element=element_key,
            role=ROLE_FULL_LENGTH,
            status="no_result",
            source_kind=None,
            source_ref=None,
            full_length=True,
            audio_ref=None,
            reason_code=REASON_NO_SOURCE,
        )
    import numpy as np

    full_audio = np.asarray(audio, dtype=np.float32)
    audio_ref = _write_audio(pack_root, element_key, full_audio, sample_rate)
    return LiveElement(
        element=element_key,
        role=ROLE_FULL_LENGTH,
        status="ok",
        source_kind=src["kind"],
        source_ref=src.get("group_ref") or src.get("stem_kind"),
        technical_stems=tuple(src.get("technical_stems", [])),
        full_length=True,
        audio_ref=audio_ref,
    )


def _write_audio(
    pack_root: Optional[Path], element_key: str, audio, sample_rate: int
) -> Optional[str]:
    if pack_root is None:
        return None
    import soundfile as sf

    out_dir = Path(pack_root) / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{element_key}.wav"
    sf.write(
        str(out_dir / fname),
        np.asarray(audio, dtype=np.float32),
        int(sample_rate),
        subtype="PCM_16",
        format="WAV",
    )
    return f"live/{fname}"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def write_live_layout(layout: LiveLayout, pack_root: Path) -> str:
    """Write ``live/live_layout.json`` and return its portable reference."""
    pack_root = Path(pack_root)
    out_dir = pack_root / "live"
    out_dir.mkdir(parents=True, exist_ok=True)
    ref = "live/live_layout.json"
    (out_dir / "live_layout.json").write_text(
        json.dumps(layout.as_dict(), indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    return ref


def read_live_layout(path: Path) -> dict:
    """Read a ``live/live_layout.json`` file back into a dict."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def find_live_layout(pack_root: Path) -> Optional[dict]:
    """Return the parsed live layout if present inside ``pack_root``."""
    p = Path(pack_root) / "live" / "live_layout.json"
    if not p.is_file():
        return None
    return read_live_layout(p)


__all__ = [
    "LIVE_LAYOUT_DOCUMENT_TYPE",
    "LIVE_LAYOUT_SCHEMA_VERSION",
    "ALLOWED_LOOP_BARS",
    "DEFAULT_LOOP_BARS",
    "ELEM_KICK_BASS",
    "ELEM_DRUMS_PRESENT",
    "ELEM_DRUMS_REDUCED",
    "ELEM_VOCALS",
    "ELEM_MELODIC",
    "ELEM_FX",
    "ELEM_OTHER",
    "ROLE_PLAYABLE_LOOP",
    "ROLE_FULL_LENGTH",
    "REASON_NO_SOURCE",
    "REASON_NO_DISTINCT_REDUCED",
    "REASON_INSUFFICIENT_BARS",
    "LiveLayoutConfig",
    "LiveElement",
    "LiveLayout",
    "build_live_layout",
    "write_live_layout",
    "read_live_layout",
    "find_live_layout",
    "_find_reduced_drum_window",
]
