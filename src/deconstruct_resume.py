"""Pack-local resume + cache reuse for Track Deconstruction (issue #262).

This module implements a *pack-local* resume/cache layer for
``src.deconstruct.run_deconstruct``. It does NOT assemble the final Performance
Pack (#260) and performs NO stem separation (#261). All state is stored under
``<pack-root>/deconstruct_resume.json``; no global cache (#237), no SQLite.

Design rules (see docs/PERFORMANCE_PACK_RESUME_V1.md):
* Cache keys are SHA-256 over canonical JSON (sorted keys, stable separators,
  no timestamps, no absolute paths, no random IDs).
* The resume state is a *regenerable index*: it stores step status, cache keys,
  an output inventory (pack-relative refs + SHA-1) and a portable arrangement
  snapshot. It never stores results themselves.
* ``canonical_audio_path`` is stored ONLY as the portable ref
  ``analysis/working_audio.wav`` and rehydrated against ``pack_root``.
* State writes are atomic (temp file + ``os.replace``).
* No absolute paths are ever serialized.

No new dependencies: stdlib only.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, is_dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from .utils import file_hash

RESUME_DOC_TYPE = "sample_brain.deconstruct_resume"
RESUME_SCHEMA_VERSION = "1.0.0"
RESUME_FILENAME = "deconstruct_resume.json"

# Per-step cache contract versions. Bumping one invalidates that step + downstream.
CONTRACT_VERSIONS: dict[str, int] = {
    "track_map": 1,
    "arrangement": 1,
    "assets": 1,
    "stems": 2,
}

# Statuses that may be reused on resume.
CACHEABLE_STATUSES: tuple[str, ...] = ("ok", "partial")

# Step dependency order for upstream cache-key chaining.
# NOTE (#249): the technical stem result is not semantically derived from the
# produced assets; its identity is based on the original source content, the
# actual separation input, and the stem config/model identity. The artificial
# ``assets`` dependency is therefore removed so an unrelated asset change does
# not force a stem recomputation unless the stem input actually changed.
_UPSTREAM: dict[str, tuple[str, ...]] = {
    "track_map": (),
    "arrangement": ("track_map",),
    "assets": ("arrangement",),
    "stems": (),
}

# Config fields (subset) that influence each step's output.
# For stems, only output-affecting separation config enters the fingerprint
# (no cache dir / model cache dir / temp dir / absolute paths / timestamps).
_CONFIG_FIELDS: dict[str, tuple[str, ...]] = {
    "track_map": ("bpm_normalization",),
    "arrangement": ("beat_backend", "bpm_normalization"),
    "assets": (),
    "stems": (
        "enabled",
        "model",
        "checkpoint",
        "weight_hash",
        "weight_hash_algo",
        "separation",
    ),
}


# ---------------------------------------------------------------------------
# Hashing helpers
# ---------------------------------------------------------------------------


def source_content_hash_sha256(track_path: Path) -> str:
    """SHA-256 over the track file bytes (content identity, not sha1 inventory)."""
    track_path = Path(track_path)
    h = hashlib.sha256()
    with track_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def compute_step_cache_key(
    step_id: str,
    *,
    source_content_hash: str,
    config: Mapping[str, Any],
    upstream_cache_keys: Mapping[str, str],
) -> str:
    """Deterministic SHA-256 cache key for one step.

    Includes: step_id, contract version, source content hash, the step's
    relevant config subset, and the upstream steps' cache keys (chained).
    """
    relevant = {k: config.get(k) for k in _CONFIG_FIELDS.get(step_id, ())}
    payload: dict[str, Any] = {
        "step_id": step_id,
        "contract_version": CONTRACT_VERSIONS[step_id],
        "source_content_hash": source_content_hash,
        "config": relevant,
        "upstream": {
            k: upstream_cache_keys[k]
            for k in _UPSTREAM.get(step_id, ())
            if k in upstream_cache_keys
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _relevant_config(
    step_id: str,
    bpm_normalization: str,
    beat_backend: str,
    stem_options: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "bpm_normalization" in _CONFIG_FIELDS.get(step_id, ()):
        out["bpm_normalization"] = bpm_normalization
    if "beat_backend" in _CONFIG_FIELDS.get(step_id, ()):
        out["beat_backend"] = beat_backend
    if step_id == "stems" and stem_options:
        for field in _CONFIG_FIELDS.get("stems", ()):
            if field in stem_options:
                out[field] = stem_options[field]
    return out


# ---------------------------------------------------------------------------
# Output inventory + integrity
# ---------------------------------------------------------------------------


def build_output_inventory(
    pack_root: Path, step_id: str, output_refs: Sequence[str]
) -> list[dict[str, str]]:
    """Build a pack-relative output inventory with content hash for a step's outputs.

    New inventory items write SHA-256 (`sha256`).
    For ``arrangement`` the canonical working WAV is added if present.
    For ``assets`` each manifest JSON's referenced WAV is added (resolved
    relative to the manifest's directory).
    """
    pack_root = Path(pack_root)
    inventory: list[dict[str, str]] = []

    def _add(ref: str) -> None:
        p = pack_root / ref
        if p.exists():
            inventory.append({"ref": ref, "sha256": file_hash(p, algorithm="sha256")})

    for ref in output_refs:
        _add(ref)
        if step_id == "assets" and ref.endswith(".json"):
            _add_asset_wav(pack_root, ref, inventory)
        # A stem manifest JSON alone is not enough: the referenced stem WAV must
        # also be present and intact for pack-local resume to be valid (#249).
        if step_id == "stems" and ref.endswith(".json"):
            _add_stem_wav(pack_root, ref, inventory)

    if step_id == "arrangement":
        _add("analysis/working_audio.wav")

    return inventory


def _add_asset_wav(
    pack_root: Path, manifest_ref: str, inventory: list[dict[str, str]]
) -> None:
    manifest_path = pack_root / manifest_ref
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return
    rendering = data.get("rendering") or {}
    output = rendering.get("output") or {}
    file_ref = output.get("file_ref")
    if not file_ref:
        return
    # file_ref is relative to the manifest's directory; make it pack-root-relative.
    wav_path = (manifest_path.parent / file_ref).resolve()
    try:
        rel = wav_path.relative_to(pack_root.resolve()).as_posix()
    except Exception:
        return
    if wav_path.exists():
        inventory.append({"ref": rel, "sha256": file_hash(wav_path, algorithm="sha256")})


def _add_stem_wav(
    pack_root: Path, manifest_ref: str, inventory: list[dict[str, str]]
) -> None:
    manifest_path = pack_root / manifest_ref
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return
    output = data.get("output") or {}
    file_ref = output.get("file_ref")
    if not file_ref:
        return
    # Stem Manifest output.file_ref is relative to the manifest's directory
    # (which is <pack_root>/stems/); make it pack-root-relative.
    wav_path = (manifest_path.parent / file_ref).resolve()
    try:
        rel = wav_path.relative_to(pack_root.resolve()).as_posix()
    except Exception:
        return
    if wav_path.exists():
        inventory.append({"ref": rel, "sha1": file_hash(wav_path)})


def verify_output_inventory(
    pack_root: Path, inventory: Sequence[dict[str, str]]
) -> bool:
    """Return True iff every inventory entry exists and matches its declared hash."""
    pack_root = Path(pack_root)
    for entry in inventory:
        ref = entry.get("ref")
        if not ref:
            return False
        p = pack_root / ref
        if not p.exists():
            return False
        if "sha256" in entry:
            expected = entry["sha256"]
            if file_hash(p, algorithm="sha256") != expected:
                return False
        elif "sha1" in entry:
            expected = entry["sha1"]
            if file_hash(p, algorithm="sha1") != expected:
                return False
        else:
            return False
    return True


# ---------------------------------------------------------------------------
# Resume state load / save (atomic)
# ---------------------------------------------------------------------------


def resume_state_path(pack_root: Path) -> Path:
    return Path(pack_root) / RESUME_FILENAME


def load_resume_state(pack_root: Path) -> dict | None:
    """Load and validate the resume state. Returns None if absent/corrupt/wrong type."""
    path = resume_state_path(pack_root)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict) or data.get("document_type") != RESUME_DOC_TYPE:
        return None
    return data


def save_resume_state(pack_root: Path, state: dict) -> None:
    """Atomically write the resume state (temp file + os.replace)."""
    pack_root = Path(pack_root)
    pack_root.mkdir(parents=True, exist_ok=True)
    path = resume_state_path(pack_root)
    payload = json.dumps(state, indent=2, sort_keys=True, default=str)
    fd, tmp_name = tempfile.mkstemp(dir=str(pack_root), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Reusability check
# ---------------------------------------------------------------------------


def step_is_reusable(
    prior_state: dict,
    step_id: str,
    *,
    cache_key: str,
    pack_root: Path,
) -> bool:
    """True iff a stored step result can be safely reused."""
    steps = prior_state.get("steps", {})
    entry = steps.get(step_id)
    if not isinstance(entry, dict):
        return False
    if entry.get("status") not in CACHEABLE_STATUSES:
        return False
    if entry.get("cache_key") != cache_key:
        return False
    # A cacheable step must have produced at least one output; an empty
    # inventory is never reusable (guards against resuming from a state that
    # recorded success without real artifacts, e.g. mock/incomplete runs).
    inventory = entry.get("output_inventory") or []
    if not inventory:
        return False
    if not verify_output_inventory(pack_root, inventory):
        return False
    return True


# ---------------------------------------------------------------------------
# Arrangement snapshot (portable round-trip of runtime objects)
# ---------------------------------------------------------------------------


# Registry of frozen dataclasses that may appear in an arrangement snapshot.
def _build_registry() -> dict[str, type]:
    from .arrangement_classifier import (
        ArrangementEvidence,
        ArrangementResult,
        AutomaticResult,
        BoundaryEventClassification,
        EffectiveValue,
        ManualOverride,
        SectionClassification,
    )
    from .beat_grid import BeatGridError, BeatGridResult, BeatGridSeries, BeatGridSource
    from .canon_audio import AudioTimebase
    from .structure_v1 import (
        StructureBoundary,
        StructureSection,
        StructureV1Result,
        StructureV1Source,
    )

    classes = (
        BeatGridError,
        BeatGridResult,
        BeatGridSeries,
        BeatGridSource,
        StructureV1Result,
        StructureBoundary,
        StructureSection,
        StructureV1Source,
        ArrangementResult,
        SectionClassification,
        AutomaticResult,
        ManualOverride,
        EffectiveValue,
        ArrangementEvidence,
        BoundaryEventClassification,
        AudioTimebase,
    )
    return {cls.__name__: cls for cls in classes}


_REGISTRY: dict[str, type] | None = None


def _registry() -> dict[str, type]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = _build_registry()
    return _REGISTRY


def _to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    try:
        import numpy as np

        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return [_to_jsonable(x) for x in obj.tolist()]
    except Exception:
        pass
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(x) for x in obj]
    if isinstance(obj, Mapping):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if is_dataclass(obj):
        return {
            "__cls__": type(obj).__name__,
            "fields": {
                f.name: _to_jsonable(getattr(obj, f.name))
                for f in dataclasses.fields(obj)
            },
        }
    return str(obj)


def _from_jsonable(obj: Any) -> Any:
    if isinstance(obj, list):
        # These frozen dataclasses type their sequences as tuples; restore them
        # so reconstructed objects are equal to the originals.
        return tuple(_from_jsonable(x) for x in obj)
    if isinstance(obj, dict):
        if "__cls__" in obj:
            cls = _registry()[obj["__cls__"]]
            kwargs = {k: _from_jsonable(v) for k, v in obj["fields"].items()}
            return cls(**kwargs)
        return {k: _from_jsonable(v) for k, v in obj.items()}
    return obj


def snapshot_arrangement(payload: dict) -> dict | None:
    """Serialize the arrangement runtime payload to a portable snapshot.

    ``payload`` is the dict produced by the arrangement adapter:
    ``structure_result``, ``arrangement_result``, ``beat_grid``, ``timebase``,
    ``canonical_audio_path``. The canonical audio path is stored ONLY as the
    portable ref ``analysis/working_audio.wav``.
    """
    if not isinstance(payload, dict):
        return None
    canon = payload.get("canonical_audio_path")
    portable_canon = "analysis/working_audio.wav"
    if canon is not None:
        # Normalize whatever path form we got into the portable pack-relative ref.
        try:
            name = Path(canon).name
            portable_canon = (
                "analysis/working_audio.wav" if name == "working_audio.wav" else "analysis/working_audio.wav"
            )
        except Exception:
            portable_canon = "analysis/working_audio.wav"
    return {
        "structure_result": _to_jsonable(payload.get("structure_result")),
        "arrangement_result": _to_jsonable(payload.get("arrangement_result")),
        "beat_grid": _to_jsonable(payload.get("beat_grid")),
        "timebase": _to_jsonable(payload.get("timebase")),
        "canonical_audio_path": portable_canon,
    }


def resume_arrangement(snapshot: dict, pack_root: Path) -> dict:
    """Reconstruct the arrangement runtime payload from a portable snapshot."""
    pack_root = Path(pack_root)
    return {
        "structure_result": _from_jsonable(snapshot.get("structure_result")),
        "arrangement_result": _from_jsonable(snapshot.get("arrangement_result")),
        "beat_grid": _from_jsonable(snapshot.get("beat_grid")),
        "timebase": _from_jsonable(snapshot.get("timebase")),
        "canonical_audio_path": pack_root / "analysis" / "working_audio.wav",
    }


__all__ = [
    "RESUME_DOC_TYPE",
    "RESUME_SCHEMA_VERSION",
    "CONTRACT_VERSIONS",
    "CACHEABLE_STATUSES",
    "build_output_inventory",
    "compute_step_cache_key",
    "load_resume_state",
    "resume_arrangement",
    "resume_state_path",
    "save_resume_state",
    "snapshot_arrangement",
    "source_content_hash_sha256",
    "step_is_reusable",
    "verify_output_inventory",
]
