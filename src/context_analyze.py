"""DB-free, one-shot Track Map v1 analysis for a local audio file."""

from __future__ import annotations

from importlib import metadata
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import soundfile as sf

from .analyze import Features, extract_features
from .canon_audio import content_hash, probe_audio, render_canonical_wav

SUPPORTED_EXTENSIONS = frozenset({".wav", ".flac"})
REQUESTED_COMPONENTS = ("bpm", "key", "loudness", "brightness")


class ContextAnalyzeError(ValueError):
    """A safe, machine-readable input or runtime failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _package_version() -> str:
    try:
        return metadata.version("sample-brain")
    except metadata.PackageNotFoundError:
        return "unknown"


def _validate_path(path: Path) -> None:
    if not path.exists():
        raise ContextAnalyzeError("FILE_NOT_FOUND", "Audio file does not exist.")
    if not path.is_file():
        raise ContextAnalyzeError("NOT_A_FILE", "Audio path must refer to a file.")
    if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ContextAnalyzeError(
            "UNSUPPORTED_AUDIO_FORMAT", "Supported audio formats are WAV and FLAC."
        )


def _no_result(reason_code: str) -> dict[str, object]:
    return {"status": "no_result", "reason_code": reason_code, "source_ref": "analyze"}


def _not_requested(reason_code: str) -> dict[str, object]:
    return {"status": "not_run", "reason_code": reason_code}


def _base_analysis(
    features: Features, *, bpm_normalization: str
) -> tuple[dict[str, object], list[dict[str, str]]]:
    notes: list[dict[str, str]] = []
    bpm: dict[str, object]
    if features.bpm is None:
        bpm = _no_result("BPM_UNDETECTABLE")
    else:
        bpm = {
            "status": "ok",
            "value": features.bpm,
            "unit": "bpm",
            "normalization": bpm_normalization,
            "source_ref": "analyze",
        }

    key: dict[str, object]
    if features.key is None:
        key = _no_result("KEY_UNDETECTABLE")
    else:
        key = {"status": "ok", "root": features.key, "source_ref": "analyze"}
        if features.key_conf is not None:
            key["key_conf"] = features.key_conf
            key["key_conf_kind"] = "chroma_peak_prominence"

    loudness: dict[str, object]
    if features.loudness is None:
        loudness = _no_result("LOUDNESS_UNDETECTABLE")
    else:
        loudness = {
            "status": "ok",
            "value": features.loudness,
            "unit": "dBFS",
            "method": "global_rms",
            "source_ref": "analyze",
        }

    brightness: dict[str, object]
    if features.brightness is None:
        brightness = _no_result("BRIGHTNESS_UNDETECTABLE")
    else:
        brightness = {
            "status": "ok",
            "value": features.brightness,
            "unit": "Hz",
            "method": "mean_spectral_centroid",
            "source_ref": "analyze",
        }

    if features.quality_note:
        notes.append(
            {
                "code": "SHORT_AUDIO",
                "severity": "warning",
                "path": "/analysis",
                "message": features.quality_note,
            }
        )

    return {
        "musical": {"bpm": bpm, "key": key},
        "audio_summary": {"loudness": loudness, "brightness": brightness},
    }, notes


def _overall_status(analysis: dict[str, object]) -> str:
    components = (
        analysis["musical"]["bpm"],
        analysis["musical"]["key"],
        analysis["audio_summary"]["loudness"],
        analysis["audio_summary"]["brightness"],
    )
    statuses = [component["status"] for component in components]
    if all(status == "ok" for status in statuses):
        return "ok"
    if any(status in {"ok", "partial"} for status in statuses):
        return "partial"
    return "failed"


def analyze_context_file(
    path: Path, *, bpm_normalization: str = "none"
) -> dict[str, object]:
    """Analyze one WAV/FLAC file without initializing or mutating the catalog DB."""
    source_path = Path(path)
    _validate_path(source_path)
    timebase = probe_audio(source_path)
    if timebase is None:
        raise ContextAnalyzeError("AUDIO_LOAD_FAILED", "Audio file could not be read.")
    try:
        info = sf.info(str(source_path))
    except Exception as exc:
        raise ContextAnalyzeError(
            "AUDIO_LOAD_FAILED", "Audio file could not be read."
        ) from exc

    try:
        with TemporaryDirectory(prefix="sample-brain-context-") as temp_dir:
            canonical_path = Path(temp_dir) / "canonical.wav"
            render_canonical_wav(source_path, canonical_path)
            features = extract_features(
                canonical_path,
                timebase.duration_seconds,
                bpm_normalization=bpm_normalization,
            )
    except ContextAnalyzeError:
        raise
    except Exception as exc:
        raise ContextAnalyzeError(
            "AUDIO_LOAD_FAILED", "Audio file could not be analyzed."
        ) from exc
    if features is None:
        raise ContextAnalyzeError(
            "AUDIO_LOAD_FAILED", "Audio file could not be analyzed."
        )

    base_analysis, quality_notes = _base_analysis(
        features, bpm_normalization=bpm_normalization
    )
    timeline = {
        "beats": _not_requested("BEATS_NOT_REQUESTED"),
        "downbeats": _not_requested("DOWNBEATS_NOT_REQUESTED"),
        "energy": _not_requested("ENERGY_NOT_REQUESTED"),
        "sections": _not_requested("SECTIONS_NOT_REQUESTED"),
    }
    analysis: dict[str, Any] = {
        "requested_components": list(REQUESTED_COMPONENTS),
        **base_analysis,
        "timeline": timeline,
    }
    analysis["status"] = _overall_status(analysis)

    package_version = _package_version()
    return {
        "document_type": "sample_brain.track_map",
        "schema_version": "1.0.0",
        "source": {
            "original": {
                "file_name": source_path.name,
                "size_bytes": source_path.stat().st_size,
                "hash": {"algorithm": "sha1", "value": content_hash(source_path)},
                "audio_properties": {
                    "duration_sec": timebase.duration_seconds,
                    "sample_rate_hz": int(info.samplerate),
                    "channels": int(info.channels),
                },
                "source_ref": "context_source",
            }
        },
        "timebase": {
            "audio_ref": "/source/original",
            "unit": "seconds",
            "origin_sec": 0.0,
        },
        "analysis": analysis,
        "provenance": {
            "components": {
                "context_source": {
                    "component": "context_source",
                    "sample_brain_version": package_version,
                    "configuration": {"hash_algorithm": "sha1"},
                },
                "analyze": {
                    "component": "analyze",
                    "sample_brain_version": package_version,
                    "backend": {
                        "name": "librosa",
                        "version": _package_version_for("librosa"),
                    },
                    "configuration": {
                        "bpm_normalization": bpm_normalization,
                        "working_audio": "temporary_canonical_wav",
                        "canonical_sample_rate_hz": 44100,
                        "canonical_channels": 1,
                    },
                },
            }
        },
        "quality": {"notes": quality_notes},
    }


def _package_version_for(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return "unknown"


__all__ = ["ContextAnalyzeError", "analyze_context_file"]
