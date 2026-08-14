"""Deterministic, lossless rendering of loop and section assets (issue #253).

This module renders previously selected loop and section candidates to
verlustfreie WAV assets. It consumes **authoritative integer sample boundaries**
only; it never re-derives, re-approximates, or re-scores candidates.

Design contract
---------------
* Local-only, deterministic, reproducible. No network, no model, no database.
* The render range is exactly ``source_audio[start_sample:end_sample_exclusive]``
  on the shared #234 timebase. No rounding, no seconds->sample recomputation,
  no BPM math, no automatic boundary sliding.
* Lossless WAV output by default: the source subtype is preserved, channels are
  preserved, sample values are copied verbatim when no opt-in DSP is enabled.
* Default path changes no edges: ``fade_in_samples = 0``, ``fade_out_samples = 0``.
  Crossfade is intentionally out of scope for v1 (no automatic seam repair).
* No time-stretch, no pitch-shift, no hidden normalization, no mono coercion,
  no resampling.
* The original source file is never mutated. Rendering is always written to a
  distinct output path.
* The renderer invents no quality decision. Eligibility (selected / rejected)
  is decided upstream by scoring/selection (#252 / #267); the renderer only
  honors an explicit ``renderable`` flag and enforces hard fail-closed boundary
  validation.
* Source identity (``master`` / ``stem`` / ``producer_group``) is preserved and
  recorded in the manifest rendering + provenance blocks.
"""

from __future__ import annotations

import importlib.metadata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import numpy as np
import soundfile as sf

from .loop_candidates import LoopCandidate
from .section_candidates import (
    SectionCandidate,
)
from .utils import file_hash

AssetKind = Literal["loop", "section"]
RenderSourceKind = Literal["master", "stem", "producer_group"]
RenderStatus = Literal["rendered", "not_rendered", "failed"]

COMPONENT_NAME = "asset_renderer"
PROVENANCE_KEY = "comp_asset_renderer"
ASSETS_DIR_NAME = "assets"

# Map a WAV subtype to the NumPy dtype that round-trips losslessly through
# soundfile's read/write path.
_SUBTYPE_DTYPE: dict[str, str] = {
    "PCM_16": "int16",
    "PCM_24": "int32",
    "PCM_32": "int32",
    "FLOAT": "float32",
    "DOUBLE": "float64",
}

# Stable codes for status-based error evidence.
ERR_INVALID_START = "INVALID_START_SAMPLE"
ERR_INVALID_RANGE = "INVALID_RANGE"
ERR_OUT_OF_BOUNDS = "RANGE_BEYOND_SOURCE"
ERR_SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
ERR_FORMAT_UNSUPPORTED = "UNSUPPORTED_SUBTYPE"


def _package_version(distribution: str = "sample-brain") -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _safe_file_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)
    return cleaned or "asset"


@dataclass(frozen=True)
class RenderConfig:
    """Render configuration. All DSP is opt-in and defaults to off.

    ``subtype=None`` preserves the source subtype (lossless by default).
    ``fade_in_samples`` / ``fade_out_samples`` are opt-in linear ramps; they
    default to 0 and never change the default path. Crossfade is deliberately
    unsupported in v1.
    """

    format: str = "WAV"
    subtype: str | None = None
    fade_in_samples: int = 0
    fade_out_samples: int = 0
    normalize: bool = False

    def __post_init__(self) -> None:
        if self.fade_in_samples < 0:
            raise ValueError("fade_in_samples must be non-negative")
        if self.fade_out_samples < 0:
            raise ValueError("fade_out_samples must be non-negative")
        if self.format.upper() != "WAV":
            raise ValueError("only WAV output is supported in v1")


@dataclass(frozen=True)
class RenderRequest:
    """Small common render contract shared by loop and section candidates.

    All boundary fields are authoritative and consumed verbatim. The renderer
    never recomputes them.
    """

    asset_kind: AssetKind
    asset_id: str
    source_kind: RenderSourceKind
    start_sample: int
    end_sample_exclusive: int
    source_audio_path: Path
    renderable: bool = True
    source_identity: dict[str, object] | None = None

    def __post_init__(self) -> None:
        # Boundary validity is the renderer's fail-closed responsibility
        # (status-based error), not constructor validation, so invalid ranges
        # reach render_asset and are reported rather than raising here.
        if self.asset_kind not in ("loop", "section"):
            raise ValueError("asset_kind must be 'loop' or 'section'")
        if self.source_kind not in ("master", "stem", "producer_group"):
            raise ValueError("source_kind must be master/stem/producer_group")
        object.__setattr__(self, "source_audio_path", Path(self.source_audio_path))

    @property
    def n_samples(self) -> int:
        return self.end_sample_exclusive - self.start_sample

    @property
    def file_name(self) -> str:
        return f"{self.asset_kind}_{_safe_file_name(self.asset_id)}.wav"


@dataclass(frozen=True)
class RenderResult:
    status: RenderStatus
    request: RenderRequest
    renderer: dict[str, object]
    output: dict[str, object] | None = None
    error: dict[str, object] | None = None

    def as_manifest_rendering(self) -> dict[str, object]:
        """Map to the Asset Manifest v1 ``rendering`` block (#250 §11)."""
        if self.status == "rendered" and self.output is not None:
            return {
                "status": "rendered",
                "renderer": self.renderer,
                "output": self.output,
            }
        if self.status == "failed" and self.error is not None:
            return {
                "status": "failed",
                "renderer": self.renderer,
                "error": self.error,
            }
        return {"status": "not_rendered"}


# --- adapter builders -------------------------------------------------------


def render_request_from_loop_candidate(
    candidate: LoopCandidate,
    source_audio_path: Path,
    *,
    renderable: bool = True,
    asset_id: str | None = None,
) -> RenderRequest:
    """Build a :class:`RenderRequest` from an authoritative loop candidate."""
    if asset_id is None:
        asset_id = (
            f"{candidate.bar_count}bar_"
            f"{candidate.start_sample}_{candidate.end_sample_exclusive}"
        )
    return RenderRequest(
        asset_kind="loop",
        asset_id=asset_id,
        source_kind=candidate.source.source_kind,
        start_sample=candidate.start_sample,
        end_sample_exclusive=candidate.end_sample_exclusive,
        source_audio_path=source_audio_path,
        renderable=renderable,
        source_identity=candidate.source.as_dict(),
    )


def render_request_from_section_candidate(
    candidate: SectionCandidate,
    source_audio_path: Path,
    *,
    renderable: bool = True,
) -> RenderRequest:
    """Build a :class:`RenderRequest` from an authoritative section candidate."""
    return RenderRequest(
        asset_kind="section",
        asset_id=candidate.asset_id,
        source_kind=candidate.source.source_kind,
        start_sample=candidate.start_sample,
        end_sample_exclusive=candidate.end_sample_exclusive,
        source_audio_path=source_audio_path,
        renderable=renderable,
        source_identity=candidate.source.as_dict(),
    )


# --- core rendering ---------------------------------------------------------


def _provenance_component(
    config: RenderConfig, source_subtype: str | None
) -> dict[str, object]:
    configuration: dict[str, object] = {
        "format": config.format,
        "subtype": config.subtype or source_subtype or "PCM_16",
        "subtype_preserved": config.subtype is None,
        "fade_in_samples": config.fade_in_samples,
        "fade_out_samples": config.fade_out_samples,
        "normalize": config.normalize,
        "crossfade_samples": 0,
        "time_stretch": False,
        "pitch_shift": False,
    }
    return {
        "component": COMPONENT_NAME,
        "sample_brain_version": _package_version(),
        "configuration": configuration,
    }


def _read_lossless(
    path: Path, start: int, n_samples: int
) -> tuple[np.ndarray, int, str, str]:
    """Read ``[start, start+n_samples)`` frames preserving channels + subtype."""
    with sf.SoundFile(str(path)) as f:
        sr = f.samplerate
        subtype = f.subtype or "PCM_16"
        total = len(f)
        dtype = _SUBTYPE_DTYPE.get(subtype, "int16")
        if start < 0 or n_samples <= 0 or start + n_samples > total:
            raise ValueError(ERR_OUT_OF_BOUNDS)
        f.seek(start)
        data = f.read(frames=n_samples, dtype=dtype, always_2d=True)
        return data, sr, subtype, dtype


def _apply_opt_in_fades(data: np.ndarray, config: RenderConfig) -> np.ndarray:
    if config.fade_in_samples <= 0 and config.fade_out_samples <= 0:
        return data
    out = data.astype(np.float64, copy=True)
    n = out.shape[0]
    fi = min(config.fade_in_samples, n)
    fo = min(config.fade_out_samples, n)
    if fi > 0:
        ramp = np.linspace(0.0, 1.0, fi, dtype=np.float64).reshape(-1, 1)
        out[:fi] = out[:fi] * ramp
    if fo > 0:
        ramp = np.linspace(1.0, 0.0, fo, dtype=np.float64).reshape(-1, 1)
        out[-fo:] = out[-fo:] * ramp
    if data.dtype == np.int16:
        return np.clip(np.round(out), -32768, 32767).astype(np.int16)
    if data.dtype == np.int32:
        return np.clip(np.round(out), -(2**31), 2**31 - 1).astype(np.int32)
    return out.astype(data.dtype)


def render_asset(
    request: RenderRequest,
    output_dir: Path,
    config: RenderConfig | None = None,
) -> RenderResult:
    config = config or RenderConfig()
    output_dir = Path(output_dir)
    source_subtype: str | None = None

    renderer_block: dict[str, object] = {
        "component": COMPONENT_NAME,
        "sample_brain_version": _package_version(),
        "configuration": _provenance_component(config, None)["configuration"],
        "source_ref": PROVENANCE_KEY,
    }

    # Status-based: not renderable candidates are never silently rendered.
    if not request.renderable:
        renderer_block["configuration"] = _provenance_component(config, None)[
            "configuration"
        ]
        return RenderResult(
            status="not_rendered",
            request=request,
            renderer=renderer_block,
            error={
                "code": "NOT_RENDERABLE",
                "message": (
                    "Candidate was not marked renderable by upstream "
                    "selection/scoring; no asset was written."
                ),
            },
        )

    # Hard fail-closed boundary validation.
    if request.start_sample < 0:
        return RenderResult(
            status="failed",
            request=request,
            renderer=renderer_block,
            error={
                "code": ERR_INVALID_START,
                "message": "start_sample must be non-negative",
            },
        )
    if request.end_sample_exclusive <= request.start_sample:
        return RenderResult(
            status="failed",
            request=request,
            renderer=renderer_block,
            error={
                "code": ERR_INVALID_RANGE,
                "message": "end_sample_exclusive must exceed start_sample",
            },
        )

    source_path = request.source_audio_path
    if not source_path.exists():
        return RenderResult(
            status="failed",
            request=request,
            renderer=renderer_block,
            error={
                "code": ERR_SOURCE_NOT_FOUND,
                "message": f"source audio not found: {source_path.name}",
            },
        )

    try:
        data, sr, source_subtype, _ = _read_lossless(
            source_path, request.start_sample, request.n_samples
        )
    except ValueError as exc:
        code = ERR_OUT_OF_BOUNDS if str(exc) == ERR_OUT_OF_BOUNDS else ERR_INVALID_RANGE
        return RenderResult(
            status="failed",
            request=request,
            renderer=renderer_block,
            error={"code": code, "message": str(exc)},
        )
    except sf.LibsndfileError as exc:
        return RenderResult(
            status="failed",
            request=request,
            renderer=renderer_block,
            error={"code": ERR_SOURCE_NOT_FOUND, "message": str(exc)},
        )

    out_subtype = config.subtype or source_subtype or "PCM_16"
    if out_subtype not in _SUBTYPE_DTYPE:
        return RenderResult(
            status="failed",
            request=request,
            renderer=renderer_block,
            error={
                "code": ERR_FORMAT_UNSUPPORTED,
                "message": f"unsupported output subtype: {out_subtype}",
            },
        )

    # Opt-in DSP only (default leaves samples verbatim).
    rendered = _apply_opt_in_fades(data, config)
    if config.normalize and rendered.size:
        peak = float(np.max(np.abs(rendered.astype(np.float64))))
        if peak > 0.0:
            rendered = (rendered.astype(np.float64) / peak).astype(rendered.dtype)

    assets_dir = output_dir / ASSETS_DIR_NAME
    assets_dir.mkdir(parents=True, exist_ok=True)
    out_path = assets_dir / request.file_name
    sf.write(str(out_path), rendered, sr, subtype=out_subtype, format=config.format)

    # Capture output audio properties from the actually written file.
    with sf.SoundFile(str(out_path)) as f:
        out_sr = f.samplerate
        out_channels = f.channels
        out_frames = len(f)

    output_block: dict[str, object] = {
        "file_ref": f"{ASSETS_DIR_NAME}/{request.file_name}",
        "file_name": request.file_name,
        "hash": {"algorithm": "sha1", "value": file_hash(out_path)},
        "audio_properties": {
            "sample_rate_hz": int(out_sr),
            "channels": int(out_channels),
            "n_samples": int(out_frames),
        },
        "format": f"{config.format.lower()}/{out_subtype.lower()}",
    }

    renderer_block["configuration"] = _provenance_component(config, source_subtype)[
        "configuration"
    ]

    return RenderResult(
        status="rendered",
        request=request,
        renderer=renderer_block,
        output=output_block,
    )


__all__ = [
    "ASSETS_DIR_NAME",
    "COMPONENT_NAME",
    "PROVENANCE_KEY",
    "AssetKind",
    "RenderConfig",
    "RenderRequest",
    "RenderResult",
    "RenderSourceKind",
    "RenderStatus",
    "render_asset",
    "render_request_from_loop_candidate",
    "render_request_from_section_candidate",
]
