"""Prepared Fit Variant v1 renderer for VST-independent Core Intelligence.

The renderer consumes explicit transform parameters, uses the existing local
librosa/soundfile stack, and writes regenerable variants to a user-local cache.
It does not score musical fit, touch the catalog DB, or run in an audio thread.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from importlib import metadata
import json
import math
import os
from pathlib import Path
from typing import Any, Literal

import librosa
import numpy as np
import soundfile as sf

from .content_hash import compute_file_hash
from .matching import MatchResult

FIT_VARIANT_DOCUMENT_TYPE = "sample_brain.fit_variant"
FIT_VARIANT_SCHEMA_VERSION = "1.0.0"
FIT_VARIANT_CONTRACT_VERSION = 1
COMPONENT_NAME = "fit_variants"
BACKEND_NAME = "librosa"
CACHE_DIR_ENV = "SAMPLE_BRAIN_FIT_VARIANT_CACHE_DIR"
CACHE_SUBDIR = ("sample-brain", "fit-variants")
OUTPUT_FILE_NAME = "prepared.wav"
MANIFEST_FILE_NAME = "manifest.json"

VariantStatus = Literal["ready", "cached", "no_result", "failed"]

ERR_SOURCE_NOT_FOUND = "SOURCE_NOT_FOUND"
ERR_INVALID_SOURCE_BPM = "INVALID_SOURCE_BPM"
ERR_INVALID_TARGET_BPM = "INVALID_TARGET_BPM"
ERR_SOURCE_BPM_UNAVAILABLE = "SOURCE_BPM_UNAVAILABLE"
ERR_INVALID_TEMPO_MULTIPLIER = "INVALID_TEMPO_MULTIPLIER"
ERR_INVALID_SEMITONE_SHIFT = "INVALID_SEMITONE_SHIFT"
ERR_CACHE_INSIDE_GIT = "CACHE_INSIDE_GIT_REPO"
ERR_AUDIO_READ_FAILED = "AUDIO_READ_FAILED"
ERR_RENDER_FAILED = "RENDER_FAILED"


@dataclass(frozen=True)
class VariantParams:
    """Explicit, serializable transform parameters for one prepared variant."""

    source_bpm: float | None
    target_bpm: float | None
    tempo_multiplier: float = 1.0
    semitone_shift: int = 0


@dataclass(frozen=True)
class FitVariantResult:
    """Status result for one prepare operation.

    ``output_path`` is process-local convenience only. It is deliberately not
    part of the portable manifest and must never be serialized as provenance.
    """

    status: VariantStatus
    variant_id: str | None = None
    manifest: dict[str, Any] | None = None
    output_path: Path | None = None
    error: dict[str, str] | None = None


@dataclass(frozen=True)
class _NormalizedParams:
    source_bpm: float | None
    target_bpm: float | None
    tempo_multiplier: float
    semitone_shift: int
    effective_source_bpm: float | None
    render_rate: float

    def identity_dict(self) -> dict[str, float | int | None]:
        return {
            "source_bpm": self.source_bpm,
            "target_bpm": self.target_bpm,
            "tempo_multiplier": self.tempo_multiplier,
            "semitone_shift": self.semitone_shift,
        }

    def manifest_dict(self) -> dict[str, float | int | None]:
        return {
            **self.identity_dict(),
            "effective_source_bpm": self.effective_source_bpm,
            "render_rate": self.render_rate,
        }


def _package_version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


def get_fit_variant_cache_dir(override: Path | None = None) -> Path:
    """Resolve the regenerable variant cache outside the repository by default."""
    if override is not None:
        return Path(override).expanduser().resolve()
    env_value = os.environ.get(CACHE_DIR_ENV)
    if env_value:
        return Path(env_value).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg) if xdg else Path.home() / ".cache"
    return (base / CACHE_SUBDIR[0] / CACHE_SUBDIR[1]).resolve()


def _is_inside_git_worktree(path: Path) -> bool:
    resolved = Path(path).expanduser().resolve()
    for parent in (resolved, *resolved.parents):
        if (parent / ".git").exists():
            return True
    return False


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _error(status: VariantStatus, code: str, message: str) -> FitVariantResult:
    return FitVariantResult(status=status, error={"code": code, "message": message})


def _finite_positive(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0.0:
        return None
    return number


def _normalize_params(
    params: VariantParams,
) -> tuple[_NormalizedParams | None, FitVariantResult | None]:
    if isinstance(params.semitone_shift, bool) or not isinstance(params.semitone_shift, int):
        return None, _error(
            "failed",
            ERR_INVALID_SEMITONE_SHIFT,
            "semitone_shift must be an integer from -12 to +12",
        )
    if not -12 <= params.semitone_shift <= 12:
        return None, _error(
            "failed",
            ERR_INVALID_SEMITONE_SHIFT,
            "semitone_shift must be in the range -12 to +12",
        )

    tempo_multiplier = _finite_positive(params.tempo_multiplier)
    if tempo_multiplier is None:
        return None, _error(
            "failed",
            ERR_INVALID_TEMPO_MULTIPLIER,
            "tempo_multiplier must be finite and greater than zero",
        )

    source_bpm: float | None = None
    if params.source_bpm is not None:
        source_bpm = _finite_positive(params.source_bpm)
        if source_bpm is None:
            return None, _error(
                "failed",
                ERR_INVALID_SOURCE_BPM,
                "source_bpm must be finite and greater than zero when supplied",
            )

    target_bpm: float | None = None
    if params.target_bpm is not None:
        target_bpm = _finite_positive(params.target_bpm)
        if target_bpm is None:
            return None, _error(
                "failed",
                ERR_INVALID_TARGET_BPM,
                "target_bpm must be finite and greater than zero when supplied",
            )
        if source_bpm is None:
            return None, _error(
                "no_result",
                ERR_SOURCE_BPM_UNAVAILABLE,
                "target_bpm requires known source_bpm",
            )

    effective_source_bpm = (
        source_bpm * tempo_multiplier if source_bpm is not None else None
    )
    render_rate = (
        target_bpm / effective_source_bpm
        if target_bpm is not None and effective_source_bpm is not None
        else 1.0
    )
    if not math.isfinite(render_rate) or render_rate <= 0.0:
        return None, _error(
            "failed",
            ERR_INVALID_TARGET_BPM,
            "derived render rate must be finite and greater than zero",
        )

    return (
        _NormalizedParams(
            source_bpm=source_bpm,
            target_bpm=target_bpm,
            tempo_multiplier=tempo_multiplier,
            semitone_shift=params.semitone_shift,
            effective_source_bpm=effective_source_bpm,
            render_rate=render_rate,
        ),
        None,
    )


def _backend_identity() -> dict[str, str]:
    return {"name": BACKEND_NAME, "version": _package_version("librosa")}


def compute_variant_id(
    source_hash: dict[str, str],
    params: _NormalizedParams,
    *,
    backend: dict[str, str] | None = None,
) -> str:
    """Compute v1 identity from content, normalized params, contract and backend."""
    identity = {
        "contract_version": FIT_VARIANT_CONTRACT_VERSION,
        "source_hash": source_hash,
        "transform": params.identity_dict(),
        "backend": backend or _backend_identity(),
    }
    return hashlib.sha256(_canonical_json(identity).encode("utf-8")).hexdigest()


def variant_params_from_match(
    match: MatchResult,
    *,
    target_bpm: float | None,
) -> VariantParams:
    """Translate #465 machine-readable hints into explicit transform parameters."""
    return VariantParams(
        source_bpm=match.bpm,
        target_bpm=target_bpm,
        tempo_multiplier=match.tempo_multiplier or 1.0,
        semitone_shift=match.semitone_hint or 0,
    )


def _render_audio(
    data: np.ndarray,
    *,
    sample_rate: int,
    render_rate: float,
    semitone_shift: int,
) -> np.ndarray:
    """Apply deterministic v1 DSP in the required tempo -> pitch order."""
    channels_first = np.asarray(data, dtype=np.float32).T
    rendered = channels_first
    if not math.isclose(render_rate, 1.0, rel_tol=0.0, abs_tol=1e-12):
        rendered = librosa.effects.time_stretch(rendered, rate=render_rate)
    if semitone_shift != 0:
        rendered = librosa.effects.pitch_shift(
            rendered,
            sr=sample_rate,
            n_steps=semitone_shift,
        )
    return np.asarray(rendered.T, dtype=np.float32)


def _variant_dir(cache_dir: Path, variant_id: str) -> Path:
    return cache_dir / variant_id


def _manifest_path(cache_dir: Path, variant_id: str) -> Path:
    return _variant_dir(cache_dir, variant_id) / MANIFEST_FILE_NAME


def _output_path(cache_dir: Path, variant_id: str) -> Path:
    return _variant_dir(cache_dir, variant_id) / OUTPUT_FILE_NAME


def _read_manifest(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _cache_hit_valid(
    *,
    manifest: dict[str, Any] | None,
    variant_id: str,
    source_hash: dict[str, str],
    params: _NormalizedParams,
    backend: dict[str, str],
    output_path: Path,
) -> bool:
    if manifest is None or not output_path.is_file():
        return False
    if manifest.get("document_type") != FIT_VARIANT_DOCUMENT_TYPE:
        return False
    if manifest.get("schema_version") != FIT_VARIANT_SCHEMA_VERSION:
        return False
    if manifest.get("variant_id") != variant_id:
        return False
    if manifest.get("source_hash") != source_hash:
        return False
    if manifest.get("transform") != params.manifest_dict():
        return False
    if manifest.get("backend") != backend:
        return False
    output = manifest.get("output")
    if not isinstance(output, dict):
        return False
    expected_hash = output.get("hash")
    if not isinstance(expected_hash, dict):
        return False
    try:
        return compute_file_hash(output_path) == expected_hash
    except OSError:
        return False


def _build_manifest(
    *,
    variant_id: str,
    source_hash: dict[str, str],
    params: _NormalizedParams,
    backend: dict[str, str],
    output_hash: dict[str, str],
    sample_rate: int,
    channels: int,
    frames: int,
) -> dict[str, Any]:
    return {
        "document_type": FIT_VARIANT_DOCUMENT_TYPE,
        "schema_version": FIT_VARIANT_SCHEMA_VERSION,
        "variant_id": variant_id,
        "status": "ready",
        "source_hash": source_hash,
        "transform": params.manifest_dict(),
        "backend": backend,
        "audio_properties": {
            "sample_rate_hz": int(sample_rate),
            "channels": int(channels),
            "n_samples": int(frames),
        },
        "output": {
            "file_ref": OUTPUT_FILE_NAME,
            "format": "wav/float32",
            "hash": output_hash,
        },
        "provenance": {
            "component": COMPONENT_NAME,
            "contract_version": FIT_VARIANT_CONTRACT_VERSION,
            "dsp_order": ["tempo_adaptation", "pitch_shift"],
        },
    }


def _write_manifest_atomic(path: Path, manifest: dict[str, Any]) -> None:
    temp_path = path.with_suffix(".json.tmp")
    temp_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temp_path.replace(path)


def prepare_fit_variant(
    source_path: Path,
    params: VariantParams,
    *,
    cache_dir: Path | None = None,
) -> FitVariantResult:
    """Prepare or reuse one deterministic local audio variant."""
    source_path = Path(source_path)
    if not source_path.is_file():
        return _error("failed", ERR_SOURCE_NOT_FOUND, "source audio file not found")

    normalized, validation_error = _normalize_params(params)
    if validation_error is not None or normalized is None:
        return validation_error or _error("failed", ERR_RENDER_FAILED, "invalid params")

    resolved_cache_dir = get_fit_variant_cache_dir(cache_dir)
    if _is_inside_git_worktree(resolved_cache_dir):
        return _error(
            "failed",
            ERR_CACHE_INSIDE_GIT,
            "fit variant cache must remain outside a Git worktree",
        )

    try:
        source_hash = compute_file_hash(source_path)
    except OSError:
        return _error("failed", ERR_SOURCE_NOT_FOUND, "source audio file not found")

    backend = _backend_identity()
    variant_id = compute_variant_id(source_hash, normalized, backend=backend)
    manifest_path = _manifest_path(resolved_cache_dir, variant_id)
    output_path = _output_path(resolved_cache_dir, variant_id)

    cached_manifest = _read_manifest(manifest_path)
    if _cache_hit_valid(
        manifest=cached_manifest,
        variant_id=variant_id,
        source_hash=source_hash,
        params=normalized,
        backend=backend,
        output_path=output_path,
    ):
        cached_manifest = dict(cached_manifest or {})
        cached_manifest["status"] = "cached"
        return FitVariantResult(
            status="cached",
            variant_id=variant_id,
            manifest=cached_manifest,
            output_path=output_path,
        )

    try:
        data, sample_rate = sf.read(
            str(source_path),
            dtype="float32",
            always_2d=True,
        )
    except (OSError, RuntimeError, sf.LibsndfileError) as exc:
        return FitVariantResult(
            status="failed",
            variant_id=variant_id,
            error={"code": ERR_AUDIO_READ_FAILED, "message": str(exc)},
        )

    if data.ndim != 2 or sample_rate <= 0:
        return FitVariantResult(
            status="failed",
            variant_id=variant_id,
            error={"code": ERR_AUDIO_READ_FAILED, "message": "invalid audio shape"},
        )

    try:
        rendered = _render_audio(
            data,
            sample_rate=int(sample_rate),
            render_rate=normalized.render_rate,
            semitone_shift=normalized.semitone_shift,
        )
        variant_dir = _variant_dir(resolved_cache_dir, variant_id)
        variant_dir.mkdir(parents=True, exist_ok=True)
        temp_output = variant_dir / "prepared.tmp.wav"
        sf.write(
            str(temp_output),
            rendered,
            int(sample_rate),
            format="WAV",
            subtype="FLOAT",
        )
        temp_output.replace(output_path)
        output_hash = compute_file_hash(output_path)
        info = sf.info(str(output_path))
        manifest = _build_manifest(
            variant_id=variant_id,
            source_hash=source_hash,
            params=normalized,
            backend=backend,
            output_hash=output_hash,
            sample_rate=int(info.samplerate),
            channels=int(info.channels),
            frames=int(info.frames),
        )
        _write_manifest_atomic(manifest_path, manifest)
    except (OSError, RuntimeError, ValueError, sf.LibsndfileError) as exc:
        return FitVariantResult(
            status="failed",
            variant_id=variant_id,
            error={"code": ERR_RENDER_FAILED, "message": str(exc)},
        )

    return FitVariantResult(
        status="ready",
        variant_id=variant_id,
        manifest=manifest,
        output_path=output_path,
    )


def prepare_fit_variant_from_match(
    source_path: Path,
    match: MatchResult,
    *,
    target_bpm: float | None,
    cache_dir: Path | None = None,
) -> FitVariantResult:
    """Prove the #465 MatchResult -> #466 prepared-variant boundary."""
    return prepare_fit_variant(
        source_path,
        variant_params_from_match(match, target_bpm=target_bpm),
        cache_dir=cache_dir,
    )


__all__ = [
    "BACKEND_NAME",
    "CACHE_DIR_ENV",
    "FIT_VARIANT_DOCUMENT_TYPE",
    "FIT_VARIANT_SCHEMA_VERSION",
    "FitVariantResult",
    "VariantParams",
    "compute_variant_id",
    "get_fit_variant_cache_dir",
    "prepare_fit_variant",
    "prepare_fit_variant_from_match",
    "variant_params_from_match",
]
