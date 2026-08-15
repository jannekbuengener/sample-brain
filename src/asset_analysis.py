"""Lightweight reanalysis of rendered loop and section assets (issue #254).

This module attaches consistent, portable Sample-Brain metadata to assets that
were already rendered by #253. It is intentionally lightweight and local:

* It reuses :func:`src.analyze.extract_features` (librosa-based, rules-only) and
  :func:`src.classify.rule_type` (rules-only, no kNN/CLAP). It builds no second
  BPM/key analyzer, no second renderer, and no Track Map.
* It performs a strict **source integrity gate** before analysis: the render
  output is verified against the manifest (portable ``file_ref``, existence,
  hash, audio properties). Any mismatch is fail-closed.
* It never invents a generic confidence, a BPM-confidence, or a Dur/Moll mode.
  ``key_root`` is a root pitch class only.
* It records analysis provenance per asset (component, version, backend, config,
  and a reference to the actually analyzed render output).

The analysis block is an **additive** extension of ``ASSET_MANIFEST_V1.md``
that raises the Asset Manifest ``schema_version`` from ``1.0.0`` to ``1.1.0``
(a MINOR bump for new optional fields; see ``docs/ASSET_REANALYSIS_V1.md``).
v1 consumers accept compatible ``1.x`` documents.
"""

from __future__ import annotations

import importlib.metadata
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import soundfile as sf

from .analyze import SHORT_AUDIO_DURATION_SEC, extract_features
from .classify import rule_type
from .key_signature import parse_key_signature
from .utils import file_hash

AnalysisStatus = Literal["ok", "partial", "not_run", "failed", "no_result"]

COMPONENT_KEY = "comp_asset_analyzer"
COMPONENT_NAME = "asset_analyzer"

# Stable fail-closed codes (see docs/ASSET_REANALYSIS_V1.md §5).
ERR_UNSUPPORTED_MANIFEST_VERSION = "UNSUPPORTED_MANIFEST_VERSION"
ERR_INVALID_FILE_REF = "INVALID_ASSET_FILE_REF"
ERR_NOT_FOUND = "RENDERED_ASSET_NOT_FOUND"
ERR_HASH_MISMATCH = "RENDERED_ASSET_HASH_MISMATCH"
ERR_PROPS_MISMATCH = "RENDERED_ASSET_PROPS_MISMATCH"
ERR_LOAD_FAILED = "AUDIO_LOAD_FAILED"

REASON_NOT_RENDERED = "ASSET_NOT_RENDERED"
REASON_NO_RENDERING = "RENDERING_BLOCK_MISSING"
REASON_PARTIAL = "PARTIAL_MISSING_BPM_KEY"
REASON_NO_RESULT = "NO_MEANINGFUL_ANALYSIS"


def _package_version(distribution: str = "sample-brain") -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _backend_version(distribution: str = "librosa") -> str:
    try:
        return importlib.metadata.version(distribution)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def _parse_schema_major(version) -> int | None:
    if not isinstance(version, str) or not version:
        return None
    head = version.split(".")[0]
    try:
        return int(head)
    except (ValueError, TypeError):
        return None


def _is_portable_file_ref(file_ref) -> bool:
    """A portable ``file_ref`` is relative, has no drive/root, and no ``..``."""
    if not isinstance(file_ref, str) or not file_ref:
        return False
    if os.path.isabs(file_ref):
        return False
    normalized = file_ref.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//"):
        return False
    if normalized.startswith("~") or normalized.lower().startswith("file:"):
        return False
    if ".." in normalized.split("/"):
        return False
    return True


@dataclass(frozen=True)
class AssetAnalysisResult:
    status: AnalysisStatus
    analysis: dict[str, object]
    provenance_entry: dict[str, object] | None
    error: dict[str, object] | None = None


def _not_run(reason: str) -> AssetAnalysisResult:
    return AssetAnalysisResult(
        status="not_run",
        analysis={"status": "not_run", "reason_code": reason},
        provenance_entry=None,
        error=None,
    )


def _failed(code: str, message: str) -> AssetAnalysisResult:
    error = {"code": code, "message": message}
    return AssetAnalysisResult(
        status="failed",
        analysis={"status": "failed", "error": error},
        provenance_entry=None,
        error=error,
    )


def _provenance_entry(config: dict[str, object], version: str | None) -> dict[str, object]:
    return {
        "component": COMPONENT_NAME,
        "sample_brain_version": version or _package_version(),
        "backend": {"name": "librosa", "version": _backend_version("librosa")},
        "configuration": dict(config),
    }


def reanalyze_rendered_output(
    output: dict[str, object],
    audio_root: Path,
    *,
    sample_brain_version: str | None = None,
    bpm_normalization: str = "none",
) -> AssetAnalysisResult:
    """Verify a ``rendering.output`` block against disk and produce analysis.

    Runs the source integrity gate (portable ``file_ref``, existence, hash,
    audio properties, load). Any failure is fail-closed (``failed``).
    """
    audio_root = Path(audio_root)

    file_ref = output.get("file_ref") if isinstance(output, dict) else None
    if not _is_portable_file_ref(file_ref):
        return _failed(
            ERR_INVALID_FILE_REF,
            "rendering.output.file_ref must be a portable relative path (no drive, root, or '..')",
        )

    out_path = audio_root / file_ref
    if not out_path.exists():
        return _failed(ERR_NOT_FOUND, f"rendered asset not found: {file_ref}")

    try:
        actual_hash = file_hash(out_path)
    except Exception:
        return _failed(ERR_NOT_FOUND, f"cannot hash rendered asset: {file_ref}")

    expected_hash = None
    if isinstance(output.get("hash"), dict):
        expected_hash = output["hash"].get("value")  # type: ignore[index]
    if expected_hash is not None and actual_hash != expected_hash:
        return _failed(
            ERR_HASH_MISMATCH,
            "rendered asset hash does not match rendering.output.hash",
        )

    try:
        with sf.SoundFile(str(out_path)) as f:
            act_sr = int(f.samplerate)
            act_channels = int(f.channels)
            act_frames = int(len(f))
    except Exception:
        return _failed(ERR_LOAD_FAILED, "cannot read rendered audio for verification")

    props = output.get("audio_properties") if isinstance(output.get("audio_properties"), dict) else {}
    exp_sr = props.get("sample_rate_hz") if isinstance(props, dict) else None  # type: ignore[union-attr]
    exp_ch = props.get("channels") if isinstance(props, dict) else None  # type: ignore[union-attr]
    exp_n = props.get("n_samples") if isinstance(props, dict) else None  # type: ignore[union-attr]
    if (
        (exp_sr is not None and act_sr != int(exp_sr))
        or (exp_ch is not None and act_channels != int(exp_ch))
        or (exp_n is not None and act_frames != int(exp_n))
    ):
        return _failed(
            ERR_PROPS_MISMATCH,
            "rendered audio properties do not match rendering.output.audio_properties",
        )

    duration = (act_frames / float(act_sr)) if act_sr else None
    feats = extract_features(out_path, duration, bpm_normalization=bpm_normalization)
    if feats is None:
        return _failed(ERR_LOAD_FAILED, "feature extraction failed for rendered asset")

    clazz = "oneshot" if (duration is not None and duration <= 1.2) else "loop"
    sample_type: str | None = None
    try:
        tags = rule_type(duration, feats.loudness, feats.brightness, None, clazz)
        if tags:
            sample_type = tags[0]
    except Exception:
        sample_type = None

    short_clip = duration is not None and duration < SHORT_AUDIO_DURATION_SEC

    analysis_fields: dict[str, object] = {}
    if feats.bpm is not None:
        analysis_fields["bpm"] = feats.bpm
    if feats.key is not None:
        # Asset reanalysis (#254) records the ROOT pitch class only. It must not
        # invent or store a Dur/Moll mode, even if the analyzer now emits one.
        analysis_fields["key_root"] = asset_key_root(feats)

    if sample_type is not None:
        analysis_fields["sample_type"] = sample_type
    if feats.loudness is not None:
        analysis_fields["loudness"] = feats.loudness
    if feats.brightness is not None:
        analysis_fields["brightness"] = feats.brightness

    analyzed_output = {
        "file_ref": file_ref,
        "hash": {
            "algorithm": (
                output.get("hash", {}).get("algorithm", "sha1")  # type: ignore[union-attr]
                if isinstance(output.get("hash"), dict)
                else "sha1"
            ),
            "value": actual_hash,
        },
        "audio_properties": {
            "sample_rate_hz": act_sr,
            "channels": act_channels,
            "n_samples": act_frames,
        },
    }
    config: dict[str, object] = {
        "bpm_normalization": bpm_normalization,
        "short_clip": bool(short_clip),
        "duration_sec": duration,
    }

    values = [feats.bpm, feats.key, sample_type, feats.loudness, feats.brightness]
    any_present = any(v is not None for v in values)
    all_present = all(v is not None for v in values)

    if not any_present:
        status: AnalysisStatus = "no_result"
        reason: str | None = REASON_NO_RESULT
    elif not all_present:
        status = "partial"
        reason = REASON_PARTIAL
    else:
        status = "ok"
        reason = None

    analysis: dict[str, object] = {
        "status": status,
        "components": [COMPONENT_KEY],
        "source_ref": COMPONENT_KEY,
        "analyzed_output": analyzed_output,
        "config": config,
    }
    analysis.update(analysis_fields)
    if reason is not None:
        analysis["reason_code"] = reason

    return AssetAnalysisResult(
        status=status,
        analysis=analysis,
        provenance_entry=_provenance_entry(config, sample_brain_version),
        error=None,
    )


def asset_key_root(feats: "Features | None") -> "str | None":
    """Extract the pure root pitch class from analyzer features for an asset.

    The analyzer may emit ``<ROOT>maj`` / ``<ROOT>min`` / ``<ROOT>``; the asset
    manifest intentionally keeps only the root and never a Dur/Moll mode.
    """
    if feats is None or feats.key is None:
        return None
    parsed = parse_key_signature(feats.key)
    return parsed.root if parsed is not None else feats.key


def analyze_rendered_asset(
    manifest: dict[str, object],
    audio_root: Path,
    *,
    sample_brain_version: str | None = None,
    bpm_normalization: str = "none",
) -> AssetAnalysisResult:
    """Validate the Asset Manifest, then reanalyze its rendered output.

    Returns ``not_run`` when the asset is not rendered, and ``failed`` when the
    manifest version is unsupported.
    """
    if not isinstance(manifest, dict):
        return _not_run(REASON_NO_RENDERING)

    major = _parse_schema_major(manifest.get("schema_version"))
    if major != 1:
        return _failed(
            ERR_UNSUPPORTED_MANIFEST_VERSION,
            f"unsupported asset manifest schema_version major: {manifest.get('schema_version')!r}",
        )

    rendering = manifest.get("rendering")
    if not isinstance(rendering, dict):
        return _not_run(REASON_NO_RENDERING)
    if rendering.get("status") != "rendered":
        return _not_run(REASON_NOT_RENDERED)

    output = rendering.get("output")
    if not isinstance(output, dict):
        return _not_run(REASON_NOT_RENDERED)

    return reanalyze_rendered_output(
        output,
        audio_root,
        sample_brain_version=sample_brain_version,
        bpm_normalization=bpm_normalization,
    )


def attach_rendered_asset_analysis(
    manifest: dict[str, object],
    audio_root: Path,
    *,
    sample_brain_version: str | None = None,
    bpm_normalization: str = "none",
) -> dict[str, object]:
    """Return a new manifest dict with the analysis block and provenance merged.

    Unrelated blocks (``source``, ``range``, ``loop``/``section``, ``boundary``,
    ``candidate``, ``rendering``, ``track_ref``) are preserved unchanged.
    """
    result = analyze_rendered_asset(
        manifest,
        audio_root,
        sample_brain_version=sample_brain_version,
        bpm_normalization=bpm_normalization,
    )
    new_manifest = dict(manifest)
    new_manifest["analysis"] = result.analysis
    if result.provenance_entry is not None:
        prov = dict(new_manifest.get("provenance", {}) or {})
        components = dict(prov.get("components", {}) or {})
        components[COMPONENT_KEY] = result.provenance_entry
        prov["components"] = components
        new_manifest["provenance"] = prov
    return new_manifest


__all__ = [
    "COMPONENT_KEY",
    "COMPONENT_NAME",
    "AnalysisStatus",
    "AssetAnalysisResult",
    "analyze_rendered_asset",
    "attach_rendered_asset_analysis",
    "reanalyze_rendered_output",
]
