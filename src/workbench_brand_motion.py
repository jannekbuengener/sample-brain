"""#786 Brand / Analysis Motion contract (Python Core).

Resolves Owner-approved brand reference slots and projects real
AnalysisUiState evidence into motion presentation hints.

Does not own appearance persistence, analysis execution, or QML chrome.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping

from .workbench_display_preferences import (
    MOTION_OFF,
    MOTION_ON,
    MOTION_REDUCED,
    normalize_motion_mode,
)
from .workbench_qml_analysis import AnalysisUiState

BRAND_CLAIM = "Sample Brain — Frech aber im Flow."

SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING = False

_PRIMARY_BRAIN_RELATIVE = (
    "docs/assets/portfolio/references/brand/sample_brain_logo_primary.png"
)
_SPLASH_TYPOGRAPHY_RELATIVE = (
    "docs/assets/portfolio/references/brand/sample_brain_splash_typography.png"
)
_PRIMARY_BRAIN_SHA256 = (
    "6e8ba304d216e8f1ba0e819603388dc37ff18491fe1a3e22b985513258882605"
)
_SPLASH_TYPOGRAPHY_SHA256 = (
    "eb130874c65ce8c1e36500b56e3cb1328318d6ac439fd13305547949994a83f6"
)

ProgressKind = Literal["none", "indeterminate", "determinate"]


@dataclass(frozen=True)
class BrandAssetSlot:
    slot_id: str
    relative_path: str
    path: Path
    sha256: str
    surfaces: tuple[str, ...]


@dataclass(frozen=True)
class AnalysisMotionProjection:
    phase: str
    progress_kind: ProgressKind
    progress_ratio: float | None
    sample_name: str
    motion_mode: str
    motion_active: bool
    reduced_motion: bool
    static_fallback: bool
    job_token: int | None
    stale: bool


def _repo_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def resolve_brand_slots(*, repo_root: Path | None = None) -> Mapping[str, BrandAssetSlot]:
    """Resolve Owner-approved portfolio brand references only (no generated assets)."""
    root = _repo_root(repo_root)
    brain = BrandAssetSlot(
        slot_id="brain_symbol",
        relative_path=_PRIMARY_BRAIN_RELATIVE,
        path=(root / _PRIMARY_BRAIN_RELATIVE).resolve(),
        sha256=_PRIMARY_BRAIN_SHA256,
        surfaces=("splash", "loading", "analysis", "external"),
    )
    splash = BrandAssetSlot(
        slot_id="splash_typography",
        relative_path=_SPLASH_TYPOGRAPHY_RELATIVE,
        path=(root / _SPLASH_TYPOGRAPHY_RELATIVE).resolve(),
        sha256=_SPLASH_TYPOGRAPHY_SHA256,
        surfaces=("splash", "external"),
    )
    return {
        "brain_symbol": brain,
        "splash_typography": splash,
    }


def _clamp01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def project_analysis_motion(
    state: AnalysisUiState,
    motion_mode: Any,
    *,
    expected_token: int | None = None,
) -> AnalysisMotionProjection:
    """Project analysis UI evidence into brand-layer motion hints.

    Consumes only phase/current/total/display_name (plus token for stale checks).
    Does not invent percentages or own a second progress clock.
    """
    mode = normalize_motion_mode(motion_mode)
    reduced = mode == MOTION_REDUCED
    static = mode == MOTION_OFF
    active = mode in {MOTION_ON, MOTION_REDUCED}

    stale = expected_token is not None and state.token != expected_token
    if stale:
        return AnalysisMotionProjection(
            phase=state.phase,
            progress_kind="none",
            progress_ratio=None,
            sample_name="",
            motion_mode=mode,
            motion_active=False,
            reduced_motion=reduced,
            static_fallback=True,
            job_token=state.token,
            stale=True,
        )

    total = int(state.total)
    current = int(state.current)
    if total <= 0:
        progress_kind: ProgressKind = "indeterminate"
        progress_ratio: float | None = None
    else:
        progress_kind = "determinate"
        progress_ratio = _clamp01(float(current) / float(total))

    sample_name = str(state.display_name or "")

    return AnalysisMotionProjection(
        phase=state.phase,
        progress_kind=progress_kind,
        progress_ratio=progress_ratio,
        sample_name=sample_name,
        motion_mode=mode,
        motion_active=active,
        reduced_motion=reduced,
        static_fallback=static,
        job_token=state.token,
        stale=False,
    )


def brand_runtime_payload(
    state: AnalysisUiState,
    motion_mode: Any,
    *,
    expected_token: int | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """QML-facing projection dict. Presentation only — no analysis authority."""
    projection = project_analysis_motion(
        state,
        motion_mode,
        expected_token=expected_token,
    )
    slots = resolve_brand_slots(repo_root=repo_root)
    brain = slots["brain_symbol"]
    ratio = (
        float(projection.progress_ratio)
        if projection.progress_ratio is not None
        else -1.0
    )
    return {
        "phase": projection.phase,
        "progressKind": projection.progress_kind,
        "progressRatio": ratio,
        "sampleName": projection.sample_name,
        "motionMode": projection.motion_mode,
        "motionActive": projection.motion_active,
        "reducedMotion": projection.reduced_motion,
        "staticFallback": projection.static_fallback,
        "jobToken": projection.job_token if projection.job_token is not None else -1,
        "stale": projection.stale,
        "brainUrl": brain.path.as_uri(),
        "headerPermitsPermanentBranding": SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING,
        "claim": BRAND_CLAIM,
    }


__all__ = (
    "AnalysisMotionProjection",
    "BRAND_CLAIM",
    "BrandAssetSlot",
    "SCREEN1_HEADER_PERMITS_PERMANENT_BRANDING",
    "brand_runtime_payload",
    "project_analysis_motion",
    "resolve_brand_slots",
)
