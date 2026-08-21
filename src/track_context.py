"""Track Context Profile v1 composition over the existing portable Track Map."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .context_analyze import analyze_context_file_cached

TRACK_CONTEXT_DOCUMENT_TYPE = "sample_brain.track_context_profile"
TRACK_CONTEXT_SCHEMA_VERSION = "1.0.0"

_STATUS_OK = "ok"
_STATUS_PARTIAL = "partial"
_STATUS_NO_RESULT = "no_result"
_STATUS_NOT_RUN = "not_run"
_ALLOWED_STATUSES = {
    _STATUS_OK,
    _STATUS_PARTIAL,
    _STATUS_NO_RESULT,
    _STATUS_NOT_RUN,
    "failed",
}
class TrackContextProfileError(ValueError):
    """Fail-closed Track Context Profile contract error."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _is_absolute_path_text(value: str, *, location: str) -> bool:
    if not value:
        return False
    field_name = location.rsplit(".", 1)[-1].lower()
    if field_name.endswith("ref") and value.startswith("/"):
        return False
    return (
        Path(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
    )


def _portable_copy(value: Any, *, location: str = "root") -> Any:
    """Deep-copy JSON-like evidence while rejecting private absolute paths."""
    if isinstance(value, Mapping):
        return {
            str(key): _portable_copy(value[key], location=f"{location}.{key}")
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, tuple):
        return tuple(_portable_copy(item, location=f"{location}[]") for item in value)
    if isinstance(value, list):
        return [_portable_copy(item, location=f"{location}[]") for item in value]
    if isinstance(value, Path):
        if value.is_absolute():
            raise TrackContextProfileError(
                "NON_PORTABLE_EVIDENCE",
                f"Absolute path evidence is not allowed at {location}.",
            )
        return str(value)
    if isinstance(value, str) and _is_absolute_path_text(value, location=location):
        raise TrackContextProfileError(
            "NON_PORTABLE_EVIDENCE",
            f"Absolute path evidence is not allowed at {location}.",
        )
    return deepcopy(value)


def _no_result(reason_code: str, source_ref: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": _STATUS_NO_RESULT,
        "reason_code": reason_code,
    }
    if source_ref is not None:
        result["source_ref"] = source_ref
    return result


def _require_mapping(value: Any, *, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TrackContextProfileError(
            "INVALID_TRACK_MAP",
            f"Expected mapping at {location}.",
        )
    return value


def _track_map_analysis(track_map: Mapping[str, Any]) -> Mapping[str, Any]:
    analysis = _require_mapping(track_map.get("analysis"), location="analysis")
    musical = _require_mapping(analysis.get("musical"), location="analysis.musical")
    audio_summary = _require_mapping(
        analysis.get("audio_summary"), location="analysis.audio_summary"
    )
    _require_mapping(musical.get("bpm"), location="analysis.musical.bpm")
    _require_mapping(musical.get("key"), location="analysis.musical.key")
    _require_mapping(
        audio_summary.get("loudness"), location="analysis.audio_summary.loudness"
    )
    _require_mapping(
        audio_summary.get("brightness"), location="analysis.audio_summary.brightness"
    )
    return analysis


def _source_projection(track_map: Mapping[str, Any]) -> dict[str, Any]:
    source = _require_mapping(track_map.get("source"), location="source")
    original = _require_mapping(source.get("original"), location="source.original")
    allowed_keys = (
        "file_name",
        "size_bytes",
        "hash",
        "audio_properties",
        "source_ref",
    )
    projected = {
        key: _portable_copy(original[key], location=f"source.original.{key}")
        for key in allowed_keys
        if key in original
    }
    return {"original": projected}


def _status_of(component: Mapping[str, Any]) -> str:
    status = component.get("status")
    if not isinstance(status, str) or status not in _ALLOWED_STATUSES:
        return _STATUS_NO_RESULT
    return status


def _copy_core_component(
    component: Mapping[str, Any], *, source_ref: str
) -> dict[str, Any]:
    copied = _portable_copy(component, location=source_ref)
    if copied.get("status") not in _ALLOWED_STATUSES:
        return _no_result("INVALID_SOURCE_STATUS", source_ref)
    copied["source_ref"] = source_ref
    return copied


def _evidence_metadata(component: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _portable_copy(component[key], location=f"evidence.{key}")
        for key in ("method", "unit")
        if component.get(key) is not None
    }


def _build_energy(loudness: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = "track_map:/analysis/audio_summary/loudness"
    status = _status_of(loudness)
    if status not in {_STATUS_OK, _STATUS_PARTIAL}:
        reason = loudness.get("reason_code")
        return _no_result(
            str(reason) if reason else "ENERGY_EVIDENCE_UNAVAILABLE",
            source_ref,
        )

    value = loudness.get("value")
    if value is None:
        return _no_result("ENERGY_EVIDENCE_UNAVAILABLE", source_ref)
    return {
        "status": _STATUS_PARTIAL,
        "value": {
            "global_loudness_dbfs": _portable_copy(value, location=source_ref)
        },
        "evidence": _evidence_metadata(loudness),
        "source_ref": source_ref,
        "reason_code": "GLOBAL_LOUDNESS_ONLY",
    }


def _build_spectrum(brightness: Mapping[str, Any]) -> dict[str, Any]:
    source_ref = "track_map:/analysis/audio_summary/brightness"
    status = _status_of(brightness)
    if status not in {_STATUS_OK, _STATUS_PARTIAL}:
        reason = brightness.get("reason_code")
        return _no_result(
            str(reason) if reason else "SPECTRUM_EVIDENCE_UNAVAILABLE",
            source_ref,
        )

    value = brightness.get("value")
    if value is None:
        return _no_result("SPECTRUM_EVIDENCE_UNAVAILABLE", source_ref)
    return {
        "status": status,
        "value": {"brightness_hz": _portable_copy(value, location=source_ref)},
        "evidence": _evidence_metadata(brightness),
        "source_ref": source_ref,
    }


def _optional_component(
    name: str,
    optional_evidence: Mapping[str, Any] | None,
    *,
    unavailable_reason: str,
) -> dict[str, Any]:
    if optional_evidence is None or name not in optional_evidence:
        return _no_result(unavailable_reason)

    raw = optional_evidence[name]
    source_ref = f"optional_evidence:{name}"
    if isinstance(raw, Mapping):
        copied = _portable_copy(raw, location=source_ref)
        status = copied.get("status")
        if status is None:
            return {
                "status": _STATUS_OK,
                "evidence": copied,
                "source_ref": source_ref,
            }
        if status not in _ALLOWED_STATUSES:
            return _no_result("INVALID_OPTIONAL_EVIDENCE_STATUS", source_ref)
        copied["source_ref"] = source_ref
        return copied

    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)):
        return {
            "status": _STATUS_OK,
            "value": _portable_copy(list(raw), location=source_ref),
            "source_ref": source_ref,
        }

    return {
        "status": _STATUS_OK,
        "value": _portable_copy(raw, location=source_ref),
        "source_ref": source_ref,
    }


def _overall_status(components: tuple[Mapping[str, Any], ...]) -> str:
    statuses = [_status_of(component) for component in components]
    if all(status == _STATUS_OK for status in statuses):
        return _STATUS_OK
    if any(status in {_STATUS_OK, _STATUS_PARTIAL} for status in statuses):
        return _STATUS_PARTIAL
    return "failed"


def build_track_context_profile(
    track_map: Mapping[str, Any],
    optional_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose Track Context Profile v1 from existing Track Map evidence only."""
    if track_map.get("document_type") != "sample_brain.track_map":
        raise TrackContextProfileError(
            "INVALID_TRACK_MAP",
            "Track Context Profile requires sample_brain.track_map input.",
        )

    analysis = _track_map_analysis(track_map)
    musical = _require_mapping(analysis["musical"], location="analysis.musical")
    audio_summary = _require_mapping(
        analysis["audio_summary"], location="analysis.audio_summary"
    )

    bpm = _copy_core_component(
        _require_mapping(musical["bpm"], location="analysis.musical.bpm"),
        source_ref="track_map:/analysis/musical/bpm",
    )
    key = _copy_core_component(
        _require_mapping(musical["key"], location="analysis.musical.key"),
        source_ref="track_map:/analysis/musical/key",
    )
    energy = _build_energy(
        _require_mapping(
            audio_summary["loudness"], location="analysis.audio_summary.loudness"
        )
    )
    spectrum = _build_spectrum(
        _require_mapping(
            audio_summary["brightness"], location="analysis.audio_summary.brightness"
        )
    )
    groove = _optional_component(
        "groove",
        optional_evidence,
        unavailable_reason="GROOVE_EVIDENCE_UNAVAILABLE",
    )
    arrangement = _optional_component(
        "arrangement",
        optional_evidence,
        unavailable_reason="ARRANGEMENT_EVIDENCE_UNAVAILABLE",
    )
    desired_layers = _optional_component(
        "desired_layers",
        optional_evidence,
        unavailable_reason="DESIRED_LAYER_EVIDENCE_UNAVAILABLE",
    )

    provenance: dict[str, Any] = {
        "component": "track_context_profile",
        "contract_version": TRACK_CONTEXT_SCHEMA_VERSION,
        "source_document": {
            "document_type": track_map.get("document_type"),
            "schema_version": track_map.get("schema_version"),
        },
    }
    if isinstance(track_map.get("provenance"), Mapping):
        provenance["track_map"] = _portable_copy(
            track_map["provenance"], location="provenance.track_map"
        )

    profile = {
        "document_type": TRACK_CONTEXT_DOCUMENT_TYPE,
        "schema_version": TRACK_CONTEXT_SCHEMA_VERSION,
        "source": _source_projection(track_map),
        "status": _overall_status((bpm, key, energy, spectrum)),
        "bpm": bpm,
        "key": key,
        "energy": energy,
        "spectrum": spectrum,
        "groove": groove,
        "arrangement": arrangement,
        "desired_layers": desired_layers,
        "provenance": provenance,
    }
    return _portable_copy(profile, location="profile")


def analyze_track_context(
    path: Path,
    *,
    optional_evidence: Mapping[str, Any] | None = None,
    bpm_normalization: str = "none",
    cache_dir: Path | None = None,
    cache_enabled: bool = True,
) -> dict[str, Any]:
    """Reuse the cached DB-free Context Analyzer, then compose Track Context v1."""
    analysis_result = analyze_context_file_cached(
        Path(path),
        bpm_normalization=bpm_normalization,
        cache_dir=cache_dir,
        enabled=cache_enabled,
    )
    profile = build_track_context_profile(
        analysis_result.track_map,
        optional_evidence=optional_evidence,
    )
    profile["provenance"]["context_analysis_cache"] = {
        "status": analysis_result.cache_status,
        "cache_key": analysis_result.cache_key,
    }
    return _portable_copy(profile, location="profile")
