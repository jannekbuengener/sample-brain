"""Production-facing stdlib bridge for isolated stem separation (issue #249).

This module prepares and translates the isolated subprocess worker
(``tools/stem_separator_spike.py``) into the #248 ``separate_with_cache``
executor contract. It MUST NOT import ``audio_separator`` / ``torch`` /
``onnxruntime``; the heavy separation happens only inside the subprocess.

Contract (per the merge-GO corrections):
* ``separate_with_cache`` is called with ``output_dir = pack_root``.
* The executor runs the worker into ``pack_root / "stems"``.
* Executor stem records use cache-relative refs: ``file_ref = "stems/drums.wav"``,
  ``manifest_ref = "stem_<id>.json"``.
* The Stem Manifest itself keeps ``output.file_ref = "drums.wav"`` (sibling of
  the manifest inside ``pack_root/stems``).
* No post-copy move/normalize step. The same layout holds for fresh runs,
  global #248 cache hits, and pack-local resume.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Optional

from .stem_cache import StemModelIdentity, build_separation_fingerprint

# The spike module imports heavy deps lazily (inside functions), so importing it
# at module level keeps the core import lightweight.
from tools.stem_separator_spike import StemSeparatorProcessWrapper  # noqa: E402


def resolve_backend_version() -> str:
    """Resolve the audio-separator backend version without importing it eagerly."""
    try:
        import importlib.metadata as md

        return md.version("audio-separator")
    except Exception:
        return "unknown"


def expected_weight_hash_algo(model_filename: str) -> Optional[str]:
    """Return the mandatory weight-hash algorithm for a known model filename."""
    if model_filename == "htdemucs.yaml":
        return "sha256"
    if model_filename == "htdemucs_ft.yaml":
        return "sha256-set-v1"
    return None


def build_subprocess_executor(
    *,
    script_path: Optional[Any] = None,
    model_cache_dir: Optional[Any] = None,
    timeout: float = 600.0,
    backend_version: Optional[str] = None,
) -> Callable:
    """Return an executor matching the ``separate_with_cache`` contract.

    The executor launches the isolated spike subprocess with exact provenance
    (``track_ref``, ``working_audio_hash``, model + weight hash) so no ambiguous
    single hash is reused. It translates the spike JSON result into the executor
    result format expected by ``src.stem_cache``.
    """
    wrapper = StemSeparatorProcessWrapper(script_path)

    def executor(
        *,
        input_path: Path,
        track_ref: str,
        working_audio_hash: str,
        model_identity: StemModelIdentity,
        configuration: Optional[dict],
        output_dir: Path,
    ) -> dict:
        output_dir = Path(output_dir)
        worker_output_dir = output_dir / "stems"
        model_filename = f"{model_identity.name}.yaml"
        weight_hash = model_identity.weight_hash or {}
        bv = backend_version or resolve_backend_version()
        fp = build_separation_fingerprint(
            backend_name="python-audio-separator",
            backend_version=bv,
            model_identity=model_identity,
            configuration=configuration,
        )
        res = wrapper.separate_via_subprocess(
            input_path=Path(input_path),
            track_ref=track_ref,
            working_audio_hash=working_audio_hash,
            model_filename=model_filename,
            output_dir=worker_output_dir,
            weight_hash=weight_hash.get("value") if weight_hash else None,
            weight_hash_algo=weight_hash.get("algorithm") if weight_hash else None,
            separation_fingerprint=fp,
            model_cache_dir=model_cache_dir,
            timeout=timeout,
        )
        return _translate_spike_result(res, worker_output_dir, backend_version=bv)

    return executor


def _translate_spike_result(
    res: dict, worker_output_dir: Path, *, backend_version: str
) -> dict:
    """Translate the spike subprocess JSON into the #248 executor result format."""
    status = res.get("status")
    backend = {
        "name": "python-audio-separator",
        "version": res.get("backend_version") or backend_version,
    }

    if status in ("ok", "partial"):
        stems: list[dict] = []
        for kind, info in (res.get("stems") or {}).items():
            if not isinstance(info, dict):
                continue
            manifest_ref = info.get("manifest_ref")
            audio_ref = info.get("audio_ref")
            if not audio_ref:
                continue
            manifest_content = info.get("manifest_content") or {}
            out_hash = (manifest_content.get("output") or {}).get("hash")
            stems.append(
                {
                    "stem_kind": kind,
                    "file_ref": f"stems/{audio_ref}",
                    "manifest_ref": manifest_ref,
                    "file_path": str(worker_output_dir / audio_ref),
                    "manifest_path": str(worker_output_dir / manifest_ref)
                    if manifest_ref
                    else None,
                    "hash": out_hash,
                    "status": info.get("status", "ok"),
                    "reason_code": info.get("reason_code"),
                    "error": info.get("error"),
                }
            )
        return {"status": status, "backend": backend, "stems": stems}

    # not_run / failed / no_result -> pass the truthful reason/error through.
    return {
        "status": status,
        "backend": backend,
        "stems": [],
        "reason_code": res.get("reason_code"),
        "error": res.get("error"),
    }


def fingerprint_seed(separation_fingerprint: str) -> str:
    """Short deterministic portable seed derived from a separation fingerprint."""
    return hashlib.sha256(separation_fingerprint.encode("utf-8")).hexdigest()[:8]


__all__ = [
    "resolve_backend_version",
    "expected_weight_hash_algo",
    "build_subprocess_executor",
    "fingerprint_seed",
]
