"""Semantic analyzer determinism projection and comparison (#959).

Owns decision-relevant equality for registered analyzer result shapes.
Does not change analyzer algorithms or rebuild the track analysis cache.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping

CONTRACT_ID = "sample-brain.analyzer-semantic-determinism.v1"
CONTRACT_VERSION = "1"

SHAPE_TRACK_ANALYSIS = "track_analysis.v1"
SHAPE_RANKED_RETRIEVAL = "ranked_retrieval.v1"

SUPPORTED_SHAPES: frozenset[str] = frozenset(
    {
        SHAPE_TRACK_ANALYSIS,
        SHAPE_RANKED_RETRIEVAL,
    }
)

# Explicit volatile operational keys. Not a heuristic "strip unknowns" policy.
VOLATILE_FIELD_KEYS: frozenset[str] = frozenset(
    {
        "timestamp",
        "created_at",
        "updated_at",
        "analyzed_at",
        "wall_clock",
        "run_id",
        "attempt",
        "attempt_count",
        "transient_id",
        "duration_ms",
        "runtime_ms",
        "elapsed_ms",
        "elapsed_sec",
        "source_path",
        "absolute_path",
        "host_path",
        "local_path",
        "file_path",
        "username",
        "hostname",
        "user_home",
        "cache_dir",
        "work_dir",
        "tmp_path",
        "temp_dir",
        "cache_status",
        "cache_key",
    }
)

_TRACK_COMPONENT_OPTIONAL_KEYS: tuple[str, ...] = (
    "value",
    "unit",
    "normalization",
    "method",
    "source_ref",
    "reason_code",
    "root",
    "mode",
    "key_conf",
    "key_conf_kind",
    "mode_evidence",
    "root_evidence",
)


class InvalidSemanticValueError(ValueError):
    """Projection aborted because a value is non-finite or unsupported."""


class UnknownShapeError(ValueError):
    """Requested shape is not registered by this contract."""


@dataclass(frozen=True)
class SemanticMismatch:
    path: str
    left: Any
    right: Any


@dataclass(frozen=True)
class SemanticCompareResult:
    outcome: str  # equal | mismatch | incompatible | invalid
    shape: str
    reason: str | None = None
    mismatches: tuple[SemanticMismatch, ...] = ()
    left_projection: dict[str, Any] | None = None
    right_projection: dict[str, Any] | None = None


def describe_capabilities() -> dict[str, Any]:
    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "shapes": sorted(SUPPORTED_SHAPES),
        "volatile_fields": sorted(VOLATILE_FIELD_KEYS),
    }


def project_semantic(result: Mapping[str, Any], *, shape: str) -> dict[str, Any]:
    """Project a result onto the decision-relevant semantic surface for ``shape``."""
    if shape not in SUPPORTED_SHAPES:
        raise UnknownShapeError(f"unsupported semantic shape: {shape!r}")
    if not isinstance(result, Mapping):
        raise InvalidSemanticValueError("result must be a mapping")

    if shape == SHAPE_TRACK_ANALYSIS:
        return _project_track_analysis(result)
    return _project_ranked_retrieval(result)


def compare_semantic(
    left: Mapping[str, Any],
    right: Mapping[str, Any],
    *,
    shape: str,
) -> SemanticCompareResult:
    """Compare two analyzer results under the registered semantic shape."""
    try:
        left_proj = project_semantic(left, shape=shape)
        right_proj = project_semantic(right, shape=shape)
    except (InvalidSemanticValueError, UnknownShapeError, TypeError, KeyError) as exc:
        return SemanticCompareResult(
            outcome="invalid",
            shape=shape,
            reason=str(exc),
        )

    left_fp = _context_fingerprint(left_proj)
    right_fp = _context_fingerprint(right_proj)
    if left_fp != right_fp:
        return SemanticCompareResult(
            outcome="incompatible",
            shape=shape,
            reason="analyzer context fingerprints differ",
            left_projection=left_proj,
            right_projection=right_proj,
        )

    mismatches = tuple(_diff_values(left_proj, right_proj, path=""))
    if not mismatches:
        return SemanticCompareResult(
            outcome="equal",
            shape=shape,
            left_projection=left_proj,
            right_projection=right_proj,
        )
    return SemanticCompareResult(
        outcome="mismatch",
        shape=shape,
        reason="decision-relevant semantic fields differ",
        mismatches=mismatches,
        left_projection=left_proj,
        right_projection=right_proj,
    )


def _context_fingerprint(projection: Mapping[str, Any]) -> Any:
    context = projection.get("analyzer_context")
    if not isinstance(context, Mapping):
        return None
    return context.get("analysis_fingerprint")


def _unwrap_track_analysis_source(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """Accept bare analysis, wrapper, or track_map.analysis nesting."""
    if "musical" in result and "audio_summary" in result:
        return result
    track_map = result.get("track_map")
    if isinstance(track_map, Mapping):
        nested = track_map.get("analysis")
        if isinstance(nested, Mapping) and "musical" in nested:
            return nested
        # Some callers store musical blocks directly under track_map.
        if "musical" in track_map and "audio_summary" in track_map:
            return track_map
    analysis = result.get("analysis")
    if isinstance(analysis, Mapping) and "musical" in analysis:
        return analysis
    raise InvalidSemanticValueError(
        "track_analysis.v1 requires musical/audio_summary analysis blocks"
    )


def _project_track_analysis(result: Mapping[str, Any]) -> dict[str, Any]:
    source = _unwrap_track_analysis_source(result)
    fingerprint = _resolve_fingerprint(result, source)

    # Real Track Map (`analyze_context_file`) stores aggregate status at
    # analysis["status"]. Synthetic / wrapper payloads may use overall_status.
    overall_status = source.get("status")
    if overall_status is None:
        overall_status = source.get("overall_status", result.get("overall_status"))
    if overall_status is None:
        raise InvalidSemanticValueError(
            "track_analysis.v1 missing status/overall_status"
        )
    overall_status = _require_str("overall_status", overall_status)

    musical = source.get("musical")
    audio_summary = source.get("audio_summary")
    if not isinstance(musical, Mapping):
        raise InvalidSemanticValueError("track_analysis.v1 missing musical")
    if not isinstance(audio_summary, Mapping):
        raise InvalidSemanticValueError("track_analysis.v1 missing audio_summary")

    # Real Track Map: quality.notes on the wrapper; synthetic: quality_notes.
    quality_notes_raw: Any = None
    for candidate in (result, result.get("track_map")):
        if isinstance(candidate, Mapping):
            quality = candidate.get("quality")
            if isinstance(quality, Mapping) and "notes" in quality:
                quality_notes_raw = quality.get("notes")
                break
    if quality_notes_raw is None:
        quality_notes_raw = source.get("quality_notes", result.get("quality_notes", []))
    if quality_notes_raw is None:
        quality_notes_raw = []
    if not isinstance(quality_notes_raw, list):
        raise InvalidSemanticValueError("quality_notes must be a list")

    projection = {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "shape": SHAPE_TRACK_ANALYSIS,
        "analyzer_context": {"analysis_fingerprint": fingerprint},
        "overall_status": overall_status,
        "musical": {
            "bpm": _project_track_component("musical.bpm", musical.get("bpm")),
            "key": _project_track_component("musical.key", musical.get("key")),
        },
        "audio_summary": {
            "loudness": _project_track_component(
                "audio_summary.loudness", audio_summary.get("loudness")
            ),
            "brightness": _project_track_component(
                "audio_summary.brightness", audio_summary.get("brightness")
            ),
        },
        "quality_notes": [
            _project_quality_note(index, note)
            for index, note in enumerate(quality_notes_raw)
        ],
    }
    return projection


def _resolve_fingerprint(
    wrapper: Mapping[str, Any], source: Mapping[str, Any]
) -> str | None:
    for candidate in (
        wrapper.get("analyzer_context"),
        source.get("analyzer_context"),
        wrapper.get("provenance"),
    ):
        if isinstance(candidate, Mapping):
            fp = candidate.get("analysis_fingerprint")
            if fp is not None:
                return _require_str("analysis_fingerprint", fp)
            # provenance.components.analyze.configuration.parameter_fingerprint
            components = candidate.get("components")
            if isinstance(components, Mapping):
                analyze = components.get("analyze")
                if isinstance(analyze, Mapping):
                    configuration = analyze.get("configuration")
                    if isinstance(configuration, Mapping):
                        nested = configuration.get("parameter_fingerprint")
                        if nested is not None:
                            return _require_str("analysis_fingerprint", nested)
    direct = wrapper.get("analysis_fingerprint")
    if direct is not None:
        return _require_str("analysis_fingerprint", direct)
    nested = source.get("analysis_fingerprint")
    if nested is not None:
        return _require_str("analysis_fingerprint", nested)
    return None


def _project_track_component(path: str, component: Any) -> dict[str, Any]:
    if component is None:
        raise InvalidSemanticValueError(f"{path} is required")
    if not isinstance(component, Mapping):
        raise InvalidSemanticValueError(f"{path} must be a mapping")
    if "status" not in component:
        raise InvalidSemanticValueError(f"{path}.status is required")

    projected: dict[str, Any] = {
        "status": _require_str(f"{path}.status", component["status"]),
    }
    for key in _TRACK_COMPONENT_OPTIONAL_KEYS:
        if key not in component:
            continue
        projected[key] = _canonicalize_value(f"{path}.{key}", component[key])
    return projected


def _project_quality_note(index: int, note: Any) -> dict[str, Any]:
    path = f"quality_notes[{index}]"
    if not isinstance(note, Mapping):
        raise InvalidSemanticValueError(f"{path} must be a mapping")
    projected: dict[str, Any] = {}
    for key in ("code", "severity", "path", "message"):
        if key not in note:
            raise InvalidSemanticValueError(f"{path}.{key} is required")
        projected[key] = _require_str(f"{path}.{key}", note[key])
    return projected


def _project_ranked_retrieval(result: Mapping[str, Any]) -> dict[str, Any]:
    status = result.get("status")
    if status is None:
        raise InvalidSemanticValueError("ranked_retrieval.v1 missing status")
    status = _require_str("status", status)

    rankings_raw = result.get("rankings")
    if not isinstance(rankings_raw, list):
        raise InvalidSemanticValueError("ranked_retrieval.v1 rankings must be a list")

    fingerprint = None
    context = result.get("analyzer_context")
    if isinstance(context, Mapping) and "analysis_fingerprint" in context:
        fingerprint = _require_str(
            "analysis_fingerprint", context["analysis_fingerprint"]
        )
    elif "analysis_fingerprint" in result:
        fingerprint = _require_str(
            "analysis_fingerprint", result["analysis_fingerprint"]
        )

    rankings: list[dict[str, Any]] = []
    for index, block in enumerate(rankings_raw):
        block_path = f"rankings[{index}]"
        if not isinstance(block, Mapping):
            raise InvalidSemanticValueError(f"{block_path} must be a mapping")
        if "cluster_id" not in block:
            raise InvalidSemanticValueError(f"{block_path}.cluster_id is required")
        if "ranked" not in block or not isinstance(block["ranked"], list):
            raise InvalidSemanticValueError(f"{block_path}.ranked must be a list")

        ranked_hits: list[dict[str, Any]] = []
        for hit_index, hit in enumerate(block["ranked"]):
            hit_path = f"{block_path}.ranked[{hit_index}]"
            if not isinstance(hit, Mapping):
                raise InvalidSemanticValueError(f"{hit_path} must be a mapping")
            for required in ("sample_id", "distance", "rank"):
                if required not in hit:
                    raise InvalidSemanticValueError(f"{hit_path}.{required} is required")
            ranked_hits.append(
                {
                    "sample_id": _require_str(f"{hit_path}.sample_id", hit["sample_id"]),
                    "distance": _require_finite_number(
                        f"{hit_path}.distance", hit["distance"]
                    ),
                    "rank": _require_int(f"{hit_path}.rank", hit["rank"]),
                }
            )

        rankings.append(
            {
                "cluster_id": _require_int(f"{block_path}.cluster_id", block["cluster_id"]),
                "ranked": ranked_hits,
            }
        )

    return {
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "shape": SHAPE_RANKED_RETRIEVAL,
        "analyzer_context": {"analysis_fingerprint": fingerprint},
        "status": status,
        "rankings": rankings,
    }


def _canonicalize_value(path: str, value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        return _require_finite_number(path, value)
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _canonicalize_value(f"{path}.{key}", item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _canonicalize_value(f"{path}[{index}]", item)
            for index, item in enumerate(value)
        ]
    raise InvalidSemanticValueError(f"{path} has unsupported type {type(value).__name__}")


def _require_str(path: str, value: Any) -> str:
    if not isinstance(value, str):
        raise InvalidSemanticValueError(f"{path} must be a string")
    return value


def _require_int(path: str, value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidSemanticValueError(f"{path} must be an integer")
    return value


def _require_finite_number(path: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSemanticValueError(f"{path} must be a finite number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise InvalidSemanticValueError(f"{path} must be a finite number") from exc
    if not math.isfinite(number):
        raise InvalidSemanticValueError(f"{path} must be finite")
    return number


def _diff_values(left: Any, right: Any, *, path: str) -> list[SemanticMismatch]:
    # Exact representation equality: int vs float and -0.0 vs 0.0 are mismatches.
    if type(left) is not type(right):
        return [SemanticMismatch(path=path or "$", left=left, right=right)]

    if isinstance(left, Mapping) and isinstance(right, Mapping):
        mismatches: list[SemanticMismatch] = []
        keys = sorted(set(left.keys()) | set(right.keys()))
        for key in keys:
            child = f"{path}.{key}" if path else str(key)
            if key not in left:
                mismatches.append(
                    SemanticMismatch(path=child, left=None, right=right[key])
                )
                continue
            if key not in right:
                mismatches.append(
                    SemanticMismatch(path=child, left=left[key], right=None)
                )
                continue
            mismatches.extend(_diff_values(left[key], right[key], path=child))
        return mismatches

    if isinstance(left, list) and isinstance(right, list):
        mismatches = []
        max_len = max(len(left), len(right))
        for index in range(max_len):
            child = f"{path}[{index}]" if path else f"[{index}]"
            if index >= len(left):
                mismatches.append(
                    SemanticMismatch(path=child, left=None, right=right[index])
                )
                continue
            if index >= len(right):
                mismatches.append(
                    SemanticMismatch(path=child, left=left[index], right=None)
                )
                continue
            mismatches.extend(_diff_values(left[index], right[index], path=child))
        return mismatches

    if isinstance(left, float) and isinstance(right, float):
        if left != right or math.copysign(1.0, left) != math.copysign(1.0, right):
            return [SemanticMismatch(path=path or "$", left=left, right=right)]
        return []

    if left != right:
        return [SemanticMismatch(path=path or "$", left=left, right=right)]
    return []
