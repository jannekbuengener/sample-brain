"""Local regenerable stem cache with exact model provenance (issue #248).

Design mirrors the established cache principles used elsewhere in Sample Brain
(canonical deterministic JSON, SHA-256 based keys/fingerprints, explicit contract
version, explicit > env > platform-default cache path, cache outside the repo,
atomic writes, malformed/corrupt entry => MISS, structural + expected-value
validation, no absolute private paths in entries, no SQLite, no new dependency).

This module is intentionally a *specialized* cache, not a generic cache framework.

Hard constraints honored:
* Never imports ``audio_separator`` / ``torch`` / ``onnxruntime`` so importing
  sample-brain core stays lightweight.
* Incomplete model identity (missing real weight hash) can NEVER produce a
  reusable cache hit.
* ``track_ref`` (original track identity) and ``working_audio_hash`` (actual
  separation input content hash) are kept as separate concepts.
* Output files are hash-validated on every cache hit; corrupt/missing/mutated
  outputs degrade to a MISS instead of a fake hit.
* ``failed`` / ``not_run`` / ``no_result`` results are never reused as success.
* ``partial`` may only be reused explicitly as ``partial``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from .model_readiness import WEIGHT_LICENSE_UNKNOWN_UNVERIFIED

# ---------------------------------------------------------------------------
# Contract constants
# ---------------------------------------------------------------------------

STEM_CACHE_CONTRACT_VERSION = 1
STEM_CACHE_DOCUMENT_TYPE = "sample_brain.stem_cache_entry"
STEM_CACHE_SCHEMA_VERSION = "1.0.0"

SAMPLE_BRAIN_VERSION = "0.1.0"

CACHE_ENV_VAR = "SAMPLE_BRAIN_STEM_CACHE_DIR"

# #423 corrects the current legal/readiness evidence to UNKNOWN_UNVERIFIED.
# The legacy string remains only as a v1 fingerprint-compatibility token so a
# metadata clarification does not invalidate otherwise identical stem caches.
LEGACY_DEMUCS_V1_FINGERPRINT_LICENSE_TOKEN = (
    "RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED"
)
# Backward-compatible import alias for older callers/tests. New provenance must
# use WEIGHT_LICENSE_UNKNOWN_UNVERIFIED instead.
WEIGHT_USAGE_RESEARCH_ONLY = LEGACY_DEMUCS_V1_FINGERPRINT_LICENSE_TOKEN

# Weight-hash algorithm labels (documented semantics).
WEIGHT_HASH_ALGO_SINGLE = "sha256"
WEIGHT_HASH_ALGO_SET = "sha256-set-v1"

# Cache key algorithm.
CACHE_KEY_ALGO = "sha256"

# Allowed aggregate / per-stem statuses (#244 vocabulary).
REUSABLE_STATUSES = ("ok", "partial")
NON_REUSABLE_STATUSES = ("not_run", "no_result", "failed")


# ---------------------------------------------------------------------------
# Model identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StemModelIdentity:
    """Explicit, traceable separation model identity.

    ``checkpoint`` is a short released checkpoint/source identifier (e.g. the
    htdemucs released sig ``955717e8`` or the htdemucs_ft four-source bag). It is
    NOT a cryptographic weight hash. ``weight_hash`` must be the actual
    cryptographic identity of the loaded weight file/set, derived at runtime.
    """

    family: str
    name: str
    checkpoint: str
    weight_hash: Optional[dict]  # {"algorithm": str, "value": str} or None
    code_license: str
    weight_license: str

    def is_complete(self) -> bool:
        """A complete identity carries a real, non-empty weight hash."""
        wh = self.weight_hash
        return (
            isinstance(wh, dict) and bool(wh.get("algorithm")) and bool(wh.get("value"))
        )

    def to_provenance(self) -> dict:
        return {
            "family": self.family,
            "name": self.name,
            "checkpoint": self.checkpoint,
            "weight_hash": self.weight_hash,
            "code_license": self.code_license,
            "weight_license": self.weight_license,
        }


def known_htdemucs_identity(*, weight_hash: Optional[dict] = None) -> StemModelIdentity:
    """Declared identity for ``htdemucs`` (single released checkpoint).

    The checkpoint identifier ``955717e8`` is a released model signature, NOT a
    full local weight hash. ``weight_hash`` must be supplied explicitly from the
    actual loaded weight file/set. Commercial readiness is deliberately kept
    separate from this technical identity; current weight-license evidence is
    ``UNKNOWN_UNVERIFIED``.
    """
    return StemModelIdentity(
        family="htdemucs",
        name="htdemucs",
        checkpoint="955717e8",
        weight_hash=weight_hash,
        code_license="MIT",
        weight_license=WEIGHT_LICENSE_UNKNOWN_UNVERIFIED,
    )


def known_htdemucs_ft_identity(
    *, weight_hash: Optional[dict] = None
) -> StemModelIdentity:
    """Declared identity for ``htdemucs_ft`` (bag of four released checkpoints).

    The checkpoint representation is the canonical, stable bag of the four
    released source signatures:
        f7e0c4bc,d12395a8,92cfc3b6,04573f0d
    These are checkpoint identifiers, NOT a full local weight hash. Commercial
    readiness remains separate and fail-closed while weight-license evidence is
    ``UNKNOWN_UNVERIFIED``.
    """
    return StemModelIdentity(
        family="htdemucs",
        name="htdemucs_ft",
        checkpoint="f7e0c4bc,d12395a8,92cfc3b6,04573f0d",
        weight_hash=weight_hash,
        code_license="MIT",
        weight_license=WEIGHT_LICENSE_UNKNOWN_UNVERIFIED,
    )


# ---------------------------------------------------------------------------
# Canonical JSON / hashing helpers
# ---------------------------------------------------------------------------


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha1_of_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_single_weight_file(path: Path) -> str:
    """SHA-256 over the actual bytes of a single weight file."""
    return _sha256_of_file(Path(path))


def hash_weight_set(*, checkpoint: str, component_hashes: dict) -> dict:
    """Deterministic aggregate SHA-256 over a set of weight files.

    ``component_hashes`` maps a stable component name (e.g. source/stem name or
    file name) to its SHA-256 hex. The aggregate is computed over canonical JSON
    of the checkpoint identity plus the sorted component hashes so the result is
    independent of dict ordering.

    Algorithm label: ``sha256-set-v1``.
    """
    components = sorted((str(k), str(v)) for k, v in component_hashes.items())
    canonical = _canonical_json({"checkpoint": checkpoint, "components": components})
    digest = _sha256_of_bytes(canonical.encode("utf-8"))
    return {"algorithm": WEIGHT_HASH_ALGO_SET, "value": digest}


# ---------------------------------------------------------------------------
# Cache location
# ---------------------------------------------------------------------------


def resolve_cache_dir(
    *, explicit: Optional[Any] = None, env_var: str = CACHE_ENV_VAR
) -> Path:
    """Resolve the stem cache root.

    Precedence: explicit argument > environment variable > platform default.
    The result is always returned as a Path but is NEVER serialized into
    portable entries/manifests.
    """
    if explicit is not None:
        return Path(explicit)
    env = os.environ.get(env_var)
    if env:
        return Path(env)
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return base / "sample-brain" / "stems"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "sample-brain" / "stems"


# ---------------------------------------------------------------------------
# Fingerprint + cache key
# ---------------------------------------------------------------------------


def _canonical_configuration(configuration: Optional[dict]) -> dict:
    """Only output-affecting parameters enter the fingerprint.

    Callers must already exclude non-affecting values (output dir, model cache
    dir, timeout, temp dir, absolute input path, timestamps).
    """
    if not configuration:
        return {}
    return {k: configuration[k] for k in sorted(configuration)}


def _fingerprint_model_provenance(model_identity: StemModelIdentity) -> dict:
    """Return v1-compatible model provenance for separation fingerprints.

    #423 corrects the current Demucs weight-license evidence from the historical
    over-strong label to UNKNOWN_UNVERIFIED. The label is not output-affecting,
    and changing it alone must not invalidate existing v1 cache keys. Therefore
    only the two known Demucs identities normalize the corrected value back to
    the historical token inside the v1 fingerprint. Emitted provenance remains
    truthful via ``StemModelIdentity.to_provenance()``.
    """
    provenance = model_identity.to_provenance()
    if (
        model_identity.name in {"htdemucs", "htdemucs_ft"}
        and provenance.get("weight_license") == WEIGHT_LICENSE_UNKNOWN_UNVERIFIED
    ):
        provenance = dict(provenance)
        provenance["weight_license"] = LEGACY_DEMUCS_V1_FINGERPRINT_LICENSE_TOKEN
    return provenance


def build_separation_fingerprint(
    *,
    backend_name: str,
    backend_version: str,
    model_identity: StemModelIdentity,
    configuration: Optional[dict] = None,
    sample_brain_version: str = SAMPLE_BRAIN_VERSION,
    contract_version: int = STEM_CACHE_CONTRACT_VERSION,
) -> str:
    """Deterministic parameter/model fingerprint (no source audio)."""
    fp = {
        "component": "stem_separator",
        "stem_cache_contract_version": contract_version,
        "sample_brain_version": sample_brain_version,
        "backend": {"name": backend_name, "version": backend_version},
        "model": _fingerprint_model_provenance(model_identity),
        "configuration": _canonical_configuration(configuration),
    }
    return _canonical_json(fp)


def build_cache_key(
    *,
    track_ref: str,
    working_audio_hash: str,
    separation_fingerprint: str,
) -> str:
    """SHA-256 cache key over canonical JSON of the three cache inputs.

    No random UUID, no timestamp.
    """
    payload = {
        "track_ref": track_ref,
        "working_audio_hash": working_audio_hash,
        "separation_fingerprint": separation_fingerprint,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Entry construction
# ---------------------------------------------------------------------------


def build_entry_dict(
    *,
    cache_key: str,
    track_ref: str,
    working_audio_hash: str,
    separation_fingerprint: str,
    backend: dict,
    model_identity: StemModelIdentity,
    configuration: Optional[dict],
    aggregate_status: str,
    stems: list,
    reason_code: Optional[str] = None,
    error: Optional[dict] = None,
) -> dict:
    """Build a portable cache entry dict (no absolute private paths).

    ``reason_code`` / ``error`` preserve the truthful optional-step failure
    reason from the executor so #249 can report it without re-deriving it.
    """
    entry: dict = {
        "document_type": STEM_CACHE_DOCUMENT_TYPE,
        "schema_version": STEM_CACHE_SCHEMA_VERSION,
        "cache_key": cache_key,
        "cache_contract_version": STEM_CACHE_CONTRACT_VERSION,
        "track_ref": track_ref,
        "working_audio_hash": working_audio_hash,
        "separation_fingerprint": separation_fingerprint,
        "backend": backend,
        "model": model_identity.to_provenance(),
        "configuration": _canonical_configuration(configuration),
        "aggregate_status": aggregate_status,
        "stems": stems,
    }
    if reason_code is not None:
        entry["reason_code"] = reason_code
    if error is not None:
        entry["error"] = error
    return entry


# ---------------------------------------------------------------------------
# Atomic writes
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_canonical_json(data))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _safe_rel_name(name: str) -> str:
    """Reject traversal and absolute components in a stored relative name."""
    if not name or ".." in Path(name).parts:
        raise ValueError(f"unsafe relative name: {name!r}")
    return name


def publish_entry(
    *,
    cache_root: Any,
    entry_dict: dict,
    outputs: dict,
    manifests: Optional[dict] = None,
) -> Path:
    """Atomically publish a complete cache entry.

    ``outputs`` / ``manifests`` map a stem kind to ``(relative_name, source_path)``.
    Everything is staged under a temporary staging dir in ``cache_root`` and only
    published (moved) after all files + metadata are written and validated.
    A half-written entry is never accepted as a hit.
    """
    cache_root = Path(cache_root)
    cache_root.mkdir(parents=True, exist_ok=True)
    key = _safe_rel_name(entry_dict["cache_key"])
    final_dir = cache_root / key
    staging = cache_root / f".staging-{key}"

    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    if final_dir.exists():
        shutil.rmtree(final_dir, ignore_errors=True)

    out_dir = staging / "outputs"
    man_dir = staging / "manifests"
    out_dir.mkdir(parents=True, exist_ok=True)
    man_dir.mkdir(parents=True, exist_ok=True)

    for kind, (rel_name, src) in (outputs or {}).items():
        rel_name = _safe_rel_name(rel_name)
        dest = out_dir / rel_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(src), dest)

    for kind, (rel_name, src) in (manifests or {}).items():
        rel_name = _safe_rel_name(rel_name)
        dest = man_dir / rel_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(src), dest)

    _atomic_write_json(staging / "entry.json", entry_dict)

    # Publish: move the fully-written staging dir into place.
    shutil.move(str(staging), str(final_dir))
    leftover = cache_root / f".staging-{key}"
    if leftover.exists():
        shutil.rmtree(leftover, ignore_errors=True)
    return final_dir


# ---------------------------------------------------------------------------
# Read / validate (fail-soft MISS)
# ---------------------------------------------------------------------------


def _validate_stem_output(entry_dir: Path, stem: Any) -> bool:
    if not isinstance(stem, dict):
        return False
    status = stem.get("status")
    # Only output-bearing reusable stems are validated for reuse.
    if status not in REUSABLE_STATUSES:
        return True
    file_ref = stem.get("file_ref")
    if not isinstance(file_ref, str) or not file_ref:
        return False
    if ".." in Path(file_ref).parts:
        return False
    out_dir = entry_dir / "outputs"
    target = out_dir / file_ref
    try:
        if not target.is_file():
            return False
        # Ensure the resolved path stays inside the outputs directory.
        target.resolve().relative_to(out_dir.resolve())
    except (OSError, ValueError):
        return False

    expected_hash = stem.get("hash")
    if not isinstance(expected_hash, dict) or not expected_hash.get("value"):
        return False
    algo = expected_hash.get("algorithm")
    try:
        if algo == "sha256":
            actual = _sha256_of_file(target)
        elif algo == "sha1":
            actual = _sha1_of_file(target)
        else:
            return False
    except OSError:
        return False
    if actual != expected_hash["value"]:
        return False

    manifest_ref = stem.get("manifest_ref")
    if manifest_ref:
        if ".." in Path(manifest_ref).parts:
            return False
        mpath = entry_dir / "manifests" / manifest_ref
        try:
            if not mpath.is_file():
                return False
            json.loads(mpath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False
    return True


def load_validated_entry(
    *,
    cache_root: Any,
    expected_key: str,
    expected_track_ref: str,
    expected_working_audio_hash: str,
    expected_fingerprint: str,
) -> Optional[dict]:
    """Return a validated cache entry, or ``None`` (MISS) on any defect.

    Defects handled fail-soft (never raise):
    * missing entry dir / entry.json
    * malformed JSON
    * wrong document_type / schema major / cache_key / contract version
    * track_ref / working_audio_hash / fingerprint mismatch
    * corrupt / missing / mutated output file
    * missing / unparseable manifest
    """
    cache_root = Path(cache_root)
    entry_dir = cache_root / expected_key
    entry_path = entry_dir / "entry.json"
    if not entry_path.is_file():
        return None
    try:
        with open(entry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return None

    if not isinstance(data, dict):
        return None
    if data.get("document_type") != STEM_CACHE_DOCUMENT_TYPE:
        return None

    schema_version = data.get("schema_version", "")
    try:
        major = int(str(schema_version).split(".")[0])
    except (ValueError, IndexError, AttributeError):
        return None
    if major != 1:
        return None

    if data.get("cache_key") != expected_key:
        return None
    if data.get("cache_contract_version") != STEM_CACHE_CONTRACT_VERSION:
        return None
    if data.get("track_ref") != expected_track_ref:
        return None
    if data.get("working_audio_hash") != expected_working_audio_hash:
        return None
    if data.get("separation_fingerprint") != expected_fingerprint:
        return None

    stems = data.get("stems")
    if not isinstance(stems, list):
        return None
    for stem in stems:
        if not _validate_stem_output(entry_dir, stem):
            return None

    # Only reusable results (ok / partial) can become a cache hit. A cached
    # failed / not_run / no_result entry must never be reused as a successful
    # hit (it may remain as execution evidence only).
    if data.get("aggregate_status") not in REUSABLE_STATUSES:
        return None

    return data


# ---------------------------------------------------------------------------
# Wrapper-level cache API (consumed by #249 later)
# ---------------------------------------------------------------------------


def _copy_cached_outputs(entry_dir: Path, output_dir: Path, entry: dict) -> None:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stems_dir = output_dir / "stems"
    for stem in entry.get("stems", []):
        if stem.get("status") not in REUSABLE_STATUSES:
            continue
        src = entry_dir / "outputs" / stem["file_ref"]
        if src.is_file():
            dst = output_dir / stem["file_ref"]
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
        manifest_ref = stem.get("manifest_ref")
        if manifest_ref:
            msrc = entry_dir / "manifests" / manifest_ref
            if msrc.is_file():
                stems_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(msrc, stems_dir / manifest_ref)


# Executor contract:
#   callable(*, input_path, track_ref, working_audio_hash, model_identity,
#            configuration, output_dir) -> dict with keys:
#       status: str (ok|partial|not_run|no_result|failed)
#       backend: {"name": str, "version": str}
#       stems: list of {
#           stem_kind: str,
#           file_path: str (absolute path of produced output),
#           hash: {"algorithm": str, "value": str},
#           status: str,
#           manifest_path: Optional[str],
#       }
def separate_with_cache(
    *,
    input_path: Any,
    track_ref: str,
    working_audio_hash: str,
    model_identity: StemModelIdentity,
    configuration: Optional[dict] = None,
    output_dir: Any,
    cache_dir: Any = None,
    cache_enabled: bool = True,
    backend_name: str = "unknown",
    backend_version: str = "unknown",
    executor: Optional[Callable] = None,
) -> dict:
    """Run separation with local cache reuse.

    ``cache_status`` is one of: ``hit`` | ``miss`` | ``disabled``.

    On HIT: validated cached stem outputs are copied into ``output_dir``.
    On MISS: the injected ``executor`` runs, the result is validated, and the
    entry is published only when the model identity is complete and the result
    is reusable. Incomplete model identity never yields a cache hit (and is not
    published).
    """
    cache_root = resolve_cache_dir(explicit=cache_dir)

    if not cache_enabled:
        return _run_executor(
            cache_root=cache_root,
            input_path=input_path,
            track_ref=track_ref,
            working_audio_hash=working_audio_hash,
            model_identity=model_identity,
            configuration=configuration,
            output_dir=output_dir,
            executor=executor,
            cache_status="disabled",
            publish=False,
            key=None,
            fingerprint=None,
        )

    # Incomplete model identity => cannot truthfully cache.
    if not model_identity.is_complete():
        return _run_executor(
            cache_root=cache_root,
            input_path=input_path,
            track_ref=track_ref,
            working_audio_hash=working_audio_hash,
            model_identity=model_identity,
            configuration=configuration,
            output_dir=output_dir,
            executor=executor,
            cache_status="miss",
            publish=False,
            key=None,
            fingerprint=None,
            backend_name=backend_name,
            backend_version=backend_version,
        )

    fingerprint = build_separation_fingerprint(
        backend_name=backend_name,
        backend_version=backend_version,
        model_identity=model_identity,
        configuration=configuration,
    )
    key = build_cache_key(
        track_ref=track_ref,
        working_audio_hash=working_audio_hash,
        separation_fingerprint=fingerprint,
    )

    cached = load_validated_entry(
        cache_root=cache_root,
        expected_key=key,
        expected_track_ref=track_ref,
        expected_working_audio_hash=working_audio_hash,
        expected_fingerprint=fingerprint,
    )
    if cached is not None:
        _copy_cached_outputs(cache_root / key, output_dir, cached)
        return {
            "cache_status": "hit",
            "cache_key": key,
            "status": cached.get("aggregate_status"),
            "stems": cached.get("stems"),
            "backend": cached.get("backend"),
            "provenance": cached.get("model"),
            "reused": True,
            "reason_code": cached.get("reason_code"),
            "error": cached.get("error"),
        }

    return _run_executor(
        cache_root=cache_root,
        input_path=input_path,
        track_ref=track_ref,
        working_audio_hash=working_audio_hash,
        model_identity=model_identity,
        configuration=configuration,
        output_dir=output_dir,
        executor=executor,
        cache_status="miss",
        publish=True,
        key=key,
        fingerprint=fingerprint,
    )


def _run_executor(
    *,
    cache_root: Path,
    input_path: Any,
    track_ref: str,
    working_audio_hash: str,
    model_identity: StemModelIdentity,
    configuration: Optional[dict],
    output_dir: Any,
    executor: Optional[Callable],
    cache_status: str,
    publish: bool,
    key: Optional[str],
    fingerprint: Optional[str],
    backend_name: str = "unknown",
    backend_version: str = "unknown",
) -> dict:
    if executor is None:
        raise ValueError(
            "separate_with_cache requires an executor to perform separation"
        )

    result = executor(
        input_path=Path(input_path),
        track_ref=track_ref,
        working_audio_hash=working_audio_hash,
        model_identity=model_identity,
        configuration=configuration or {},
        output_dir=Path(output_dir),
    )
    if not isinstance(result, dict):
        raise TypeError("executor must return a dict")

    status = result.get("status")
    backend = result.get("backend") or {"name": "unknown", "version": "unknown"}
    raw_stems = result.get("stems", [])

    entry_stems = []
    for st in raw_stems:
        rel = st.get("file_ref") or Path(st["file_path"]).name
        entry_stems.append(
            {
                "stem_kind": st["stem_kind"],
                "file_ref": rel,
                "hash": st["hash"],
                "status": st["status"],
                "manifest_ref": st.get("manifest_ref")
                or (
                    Path(st["manifest_path"]).name if st.get("manifest_path") else None
                ),
                "reason_code": st.get("reason_code"),
                "error": st.get("error"),
            }
        )

    if publish and key is not None and status in REUSABLE_STATUSES:
        outputs = {}
        manifests = {}
        for st in raw_stems:
            rel = st.get("file_ref") or Path(st["file_path"]).name
            outputs[st["stem_kind"]] = (rel, Path(st["file_path"]))
            if st.get("manifest_path"):
                mrel = st.get("manifest_ref") or Path(st["manifest_path"]).name
                manifests[st["stem_kind"]] = (mrel, Path(st["manifest_path"]))
        entry = build_entry_dict(
            cache_key=key,
            track_ref=track_ref,
            working_audio_hash=working_audio_hash,
            separation_fingerprint=fingerprint,
            backend=backend,
            model_identity=model_identity,
            configuration=configuration,
            aggregate_status=status,
            stems=entry_stems,
            reason_code=result.get("reason_code"),
            error=result.get("error"),
        )
        publish_entry(
            cache_root=cache_root,
            entry_dict=entry,
            outputs=outputs,
            manifests=manifests,
        )

    return {
        "cache_status": cache_status,
        "cache_key": key,
        "status": status,
        "stems": entry_stems,
        "backend": backend,
        "provenance": model_identity.to_provenance(),
        "reused": False,
        "reason_code": result.get("reason_code"),
        "error": result.get("error"),
    }


__all__ = [
    "STEM_CACHE_CONTRACT_VERSION",
    "STEM_CACHE_DOCUMENT_TYPE",
    "WEIGHT_USAGE_RESEARCH_ONLY",
    "LEGACY_DEMUCS_V1_FINGERPRINT_LICENSE_TOKEN",
    "WEIGHT_LICENSE_UNKNOWN_UNVERIFIED",
    "WEIGHT_HASH_ALGO_SET",
    "StemModelIdentity",
    "known_htdemucs_identity",
    "known_htdemucs_ft_identity",
    "hash_single_weight_file",
    "hash_weight_set",
    "resolve_cache_dir",
    "build_separation_fingerprint",
    "build_cache_key",
    "build_entry_dict",
    "publish_entry",
    "load_validated_entry",
    "separate_with_cache",
]
