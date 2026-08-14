"""Headless Track Deconstruction orchestrator (issue #259).

This module coordinates existing Sample-Brain building blocks in a fixed order
and forwards partial results and errors status-based. It is pure control flow:
it does not reimplement BPM / arrangement / candidate / scoring / rendering /
analysis logic. Those live in their own modules and are called here.

Scope boundary (see docs/TRACK_DECONSTRUCTION_ORCHESTRATOR_V1.md):
* coordinates but does NOT assemble the final Performance Pack manifest (#260)
* coordinates but does NOT perform stem separation / stem pack integration (#261)
* writes an intermediate Orchestrator Run Evidence (``deconstruct_run.json``),
  never a fake final ``manifest.json``.

No DB, no network, no model download, no new dependencies. The original track
is never mutated; a canonical working WAV is rendered into the pack root.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------

# Step statuses: ok | partial | not_run | no_result | failed
# Run statuses:  complete | partial | failed

STEP_ORDER: tuple[tuple[str, bool], ...] = (
    ("track_map", True),
    ("arrangement", False),
    ("assets", False),
    ("stems", False),
)

SKIPPED_REQUIRED = "SKIPPED_REQUIRED_STEP_FAILED"
SKIPPED_REQUEST = "SKIPPED_BY_REQUEST"
STEMS_NOT_CONFIGURED = "STEMS_NOT_CONFIGURED"
ARRANGEMENT_UNAVAILABLE = "ARRANGEMENT_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class StepResult:
    step_id: str
    required: bool
    status: str
    output_refs: tuple[str, ...] = ()
    reason_code: str | None = None
    error: dict[str, str] | None = None
    adapter: str | None = None
    provenance: dict | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "step_id": self.step_id,
            "required": self.required,
            "status": self.status,
            "output_refs": list(self.output_refs),
        }
        if self.reason_code is not None:
            payload["reason_code"] = self.reason_code
        if self.error is not None:
            payload["error"] = self.error
        if self.adapter is not None:
            payload["adapter"] = self.adapter
        if self.provenance is not None:
            payload["provenance"] = self.provenance
        return payload


@dataclass
class RunResult:
    status: str
    track: dict[str, object]
    pack_root: str
    steps: list[StepResult]
    reason_codes: list[str]
    document_type: str = "sample_brain.deconstruct_run"
    schema_version: str = "1.0.0"

    def to_dict(self) -> dict[str, object]:
        return {
            "document_type": self.document_type,
            "schema_version": self.schema_version,
            "status": self.status,
            "track": self.track,
            "pack_root": self.pack_root,
            "steps": [step.to_dict() for step in self.steps],
            "reason_codes": list(self.reason_codes),
        }


@dataclass
class StepContext:
    track_path: Path
    pack_root: Path
    bpm_normalization: str
    beat_backend: str
    artifacts: dict[str, object]


StepAdapter = Callable[[StepContext], tuple[StepResult, object]]


@dataclass
class DeconstructAdapters:
    track_map: StepAdapter | None = None
    arrangement: StepAdapter | None = None
    assets: StepAdapter | None = None
    stems: StepAdapter | None = None

    def get(self, step_id: str) -> StepAdapter | None:
        return getattr(self, step_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _portable_path(path: Path) -> str:
    """Return a relative, portable string (no drive/root) for serialization."""
    try:
        rel = os.path.relpath(str(path), os.getcwd())
    except Exception:
        rel = "."
    rel = rel.replace("\\", "/")
    if rel.startswith("/") or (len(rel) >= 2 and rel[1] == ":"):
        return "."
    return rel


def _rel_ref(pack_root: Path, path: Path) -> str:
    return Path(path).relative_to(pack_root).as_posix()


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in value)
    return cleaned or "asset"


def _track_identity(track_path: Path) -> dict[str, object]:
    from .canon_audio import probe_audio
    from .utils import file_hash

    track_path = Path(track_path)
    ident: dict[str, object] = {
        "file_name": track_path.name,
        "exists": track_path.exists(),
    }
    if track_path.exists():
        try:
            ident["size_bytes"] = track_path.stat().st_size
            ident["hash"] = {"algorithm": "sha1", "value": file_hash(track_path)}
        except Exception:
            pass
        try:
            tb = probe_audio(track_path)
            if tb is not None:
                ident["audio_properties"] = {
                    "sample_rate_hz": tb.sample_rate,
                    "duration_sec": tb.duration_seconds,
                }
        except Exception:
            pass
    return ident


def _overall_status(steps: list[StepResult]) -> str:
    if any(s.required and s.status in ("failed", "no_result") for s in steps):
        return "failed"
    if any(s.status == "failed" for s in steps):
        return "partial"
    if any(s.status in ("partial", "no_result") for s in steps):
        return "partial"
    return "complete"


# ---------------------------------------------------------------------------
# Default (production) adapters — delegate to existing components only
# ---------------------------------------------------------------------------


def _default_track_map_adapter(ctx: StepContext) -> tuple[StepResult, object]:
    from .context_analyze import ContextAnalyzeError, analyze_context_file

    try:
        track_map = analyze_context_file(
            ctx.track_path, bpm_normalization=ctx.bpm_normalization
        )
    except ContextAnalyzeError as exc:
        return (
            StepResult(
                step_id="track_map",
                required=True,
                status="failed",
                error={"code": exc.code, "message": exc.message},
                adapter="context_analyze.analyze_context_file",
            ),
            None,
        )
    except Exception as exc:  # pragma: no cover - defensive
        return (
            StepResult(
                step_id="track_map",
                required=True,
                status="failed",
                error={"code": "TRACK_MAP_ERROR", "message": str(exc)[:500]},
                adapter="context_analyze.analyze_context_file",
            ),
            None,
        )

    out_dir = ctx.pack_root / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "track_map.json"
    out_path.write_text(
        json.dumps(track_map, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )

    analysis_status = track_map.get("analysis", {}).get("status", "partial")
    if analysis_status == "failed":
        step_status = "failed"
    elif analysis_status == "no_result":
        step_status = "no_result"
    elif analysis_status in ("ok", "partial"):
        step_status = analysis_status
    else:
        step_status = "partial"

    return (
        StepResult(
            step_id="track_map",
            required=True,
            status=step_status,
            output_refs=("analysis/track_map.json",),
            adapter="context_analyze.analyze_context_file",
            provenance=track_map.get("provenance"),
        ),
        track_map,
    )


def _default_arrangement_adapter(ctx: StepContext) -> tuple[StepResult, object]:
    from .beat_grid import BeatGridAdapter
    from .canon_audio import render_canonical_wav
    from .section_signals import build_arrangement_map
    from .structure_v1 import StructureV1Analyzer

    work = ctx.pack_root / "analysis"
    work.mkdir(parents=True, exist_ok=True)
    canon = work / "working_audio.wav"

    try:
        timebase = render_canonical_wav(ctx.track_path, canon)
    except Exception as exc:
        return (
            StepResult(
                step_id="arrangement",
                required=False,
                status="failed",
                error={"code": "CANONICAL_RENDER_FAILED", "message": str(exc)[:500]},
                adapter="canon_audio.render_canonical_wav",
            ),
            None,
        )

    try:
        beat_grid = BeatGridAdapter(backend=ctx.beat_backend).analyze(canon, timebase)
    except Exception as exc:
        return (
            StepResult(
                step_id="arrangement",
                required=False,
                status="failed",
                error={"code": "BEAT_GRID_FAILED", "message": str(exc)[:500]},
                adapter="beat_grid.BeatGridAdapter",
            ),
            None,
        )

    try:
        import numpy as np
        import soundfile as sf

        samples = np.asarray(
            sf.read(str(canon), dtype="float32", always_2d=False), dtype=np.float32
        ).reshape(-1)
    except Exception as exc:
        return (
            StepResult(
                step_id="arrangement",
                required=False,
                status="failed",
                error={"code": "AUDIO_READ_FAILED", "message": str(exc)[:500]},
                adapter="soundfile",
            ),
            None,
        )

    try:
        structure = StructureV1Analyzer().analyze(samples, timebase, beat_grid)
        arrangement = build_arrangement_map(structure)
    except Exception as exc:
        return (
            StepResult(
                step_id="arrangement",
                required=False,
                status="failed",
                error={"code": "ARRANGEMENT_FAILED", "message": str(exc)[:500]},
                adapter="structure_v1+arrangement_classifier",
            ),
            None,
        )

    out_path = work / "arrangement_map.json"
    arrangement_dict = arrangement.to_arrangement_map()
    arrangement_dict["document_type"] = "sample_brain.arrangement_map"
    arrangement_dict["schema_version"] = "0.1.0-draft"
    out_path.write_text(
        json.dumps(arrangement_dict, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )

    if arrangement.status == "failed":
        step_status = "failed"
    elif arrangement.status == "unavailable":
        step_status = "no_result"
        reason = ARRANGEMENT_UNAVAILABLE
    else:
        step_status = "ok"
        reason = None

    payload = {
        "structure_result": structure,
        "arrangement_result": arrangement,
        "beat_grid": beat_grid,
        "canonical_audio_path": canon,
        "timebase": timebase,
    }
    return (
        StepResult(
            step_id="arrangement",
            required=False,
            status=step_status,
            reason_code=reason,
            output_refs=("analysis/arrangement_map.json",),
            adapter="structure_v1+arrangement_classifier",
        ),
        payload,
    )


def _default_assets_adapter(ctx: StepContext) -> tuple[StepResult, object]:
    from .asset_analysis import attach_rendered_asset_analysis
    from .asset_renderer import (
        render_asset,
        render_request_from_loop_candidate,
        render_request_from_section_candidate,
    )
    from .loop_candidates import LoopSourceIdentity, generate_loop_candidates
    from .loop_scoring import default_loop_scoring_config, score_loop_candidate
    from .section_candidates import (
        SectionSourceIdentity,
        generate_section_candidates,
    )
    from .section_scoring import (
        default_section_scoring_config,
        score_section_candidate,
    )
    import numpy as np
    import soundfile as sf

    arrangement_payload = ctx.artifacts.get("arrangement")
    if not isinstance(arrangement_payload, dict) or "structure_result" not in (
        arrangement_payload or {}
    ):
        return (
            StepResult(
                step_id="assets",
                required=False,
                status="no_result",
                reason_code=ARRANGEMENT_UNAVAILABLE,
                adapter="loop_candidates+section_candidates",
            ),
            None,
        )

    structure = arrangement_payload["structure_result"]
    arrangement = arrangement_payload.get("arrangement_result")
    beat_grid = arrangement_payload.get("beat_grid")
    canon = arrangement_payload.get("canonical_audio_path")
    timebase = arrangement_payload.get("timebase")
    if structure is None or canon is None or timebase is None:
        return (
            StepResult(
                step_id="assets",
                required=False,
                status="no_result",
                reason_code=ARRANGEMENT_UNAVAILABLE,
                adapter="loop_candidates+section_candidates",
            ),
            None,
        )

    # Get authoritative track ID from Track Map content hash, not file name
    track = ctx.artifacts.get("track_map")
    if not isinstance(track, dict) or "source" not in track or "original" not in track["source"]:
        return (
            StepResult(
                step_id="assets",
                required=False,
                status="failed",
                reason_code="MISSING_TRACK_MAP_SOURCE",
                adapter="loop_candidates+section_candidates",
            ),
            None,
        )

    hash_info = track["source"]["original"].get("hash", {})
    if not hash_info or not hash_info.get("value"):
        return (
            StepResult(
                step_id="assets",
                required=False,
                status="failed",
                reason_code="MISSING_TRACK_HASH",
                adapter="loop_candidates+section_candidates",
            ),
            None,
        )

    track_ref = hash_info["value"]

    loops_dir = ctx.pack_root / "loops"
    sections_dir = ctx.pack_root / "sections"
    loops_dir.mkdir(parents=True, exist_ok=True)
    sections_dir.mkdir(parents=True, exist_ok=True)

    loop_src = LoopSourceIdentity(
        source_kind="master", track_audio_ref="/source/working_audio"
    )
    loop_batch = generate_loop_candidates(
        loop_src, beat_grid=beat_grid, structure=structure
    )
    section_src = SectionSourceIdentity(
        source_kind="master", track_audio_ref="/source/working_audio"
    )
    section_batch = generate_section_candidates(
        structure, arrangement, source=section_src, track_ref=track_ref
    )

    manifest_refs: list[str] = []
    bar_features = getattr(structure, "bar_features", {})

    def _read_slice(start: int, n: int):
        with sf.SoundFile(str(canon)) as f:
            f.seek(start)
            return np.asarray(
                f.read(frames=n, dtype="float32", always_2d=False), dtype=np.float32
            ).reshape(-1)

    # --- loops ---
    if loop_batch.status != "failed":
        for cand in loop_batch.candidates:
            try:
                req = render_request_from_loop_candidate(cand, canon)
                res = render_asset(req, loops_dir)
                manifest = {
                    "document_type": "sample_brain.asset_manifest",
                    "schema_version": "1.1.0",
                    "asset_id": req.asset_id,
                    "asset_kind": "loop",
                    "track_ref": track_ref,
                    **cand.as_manifest_dict(),
                }
                try:
                    wave = _read_slice(cand.start_sample, cand.n_samples)
                    score = score_loop_candidate(
                        cand,
                        wave,
                        sample_rate=timebase.sample_rate,
                        source_kind="master",
                        config=default_loop_scoring_config(),
                    )
                    manifest["candidate"] = score.as_candidate_dict()
                except Exception:
                    score = None
                manifest["rendering"] = res.as_manifest_rendering()
                if res.status == "rendered":
                    manifest = attach_rendered_asset_analysis(
                        manifest, audio_root=loops_dir
                    )
                fname = f"loop_{_safe_name(req.asset_id)}.json"
                (loops_dir / fname).write_text(
                    json.dumps(manifest, indent=2, sort_keys=True, default=str),
                    encoding="utf-8",
                )
                manifest_refs.append(f"loops/{fname}")
            except Exception:
                continue

    # --- sections ---
    if section_batch.status != "failed":
        for cand in section_batch.candidates:
            try:
                req = render_request_from_section_candidate(cand, canon)
                res = render_asset(req, sections_dir)
                manifest = {
                    "document_type": "sample_brain.asset_manifest",
                    "schema_version": "1.1.0",
                    "asset_id": cand.asset_id,
                    "asset_kind": "section",
                    **cand.as_manifest_dict(),
                }
                try:
                    wave = _read_slice(cand.start_sample, cand.n_samples)
                    score = score_section_candidate(
                        cand,
                        bar_features=bar_features,
                        config=default_section_scoring_config(),
                    )
                    manifest["candidate"] = score.as_candidate_dict()
                except Exception:
                    score = None
                manifest["rendering"] = res.as_manifest_rendering()
                if res.status == "rendered":
                    manifest = attach_rendered_asset_analysis(
                        manifest, audio_root=sections_dir
                    )
                fname = f"section_{_safe_name(cand.asset_id)}.json"
                (sections_dir / fname).write_text(
                    json.dumps(manifest, indent=2, sort_keys=True, default=str),
                    encoding="utf-8",
                )
                manifest_refs.append(f"sections/{fname}")
            except Exception:
                continue

    if manifest_refs:
        step_status = "ok"
        reason = None
    elif loop_batch.status == "failed" or section_batch.status == "failed":
        step_status = "partial"
        reason = "ASSET_GENERATION_PARTIAL"
    else:
        step_status = "no_result"
        reason = "NO_ASSET_CANDIDATES"

    return (
        StepResult(
            step_id="assets",
            required=False,
            status=step_status,
            reason_code=reason,
            output_refs=tuple(manifest_refs),
            adapter="loop_candidates+section_candidates+asset_renderer",
        ),
        {"manifest_refs": manifest_refs},
    )


def _default_stems_adapter(ctx: StepContext) -> tuple[StepResult, object]:
    del ctx
    return (
        StepResult(
            step_id="stems",
            required=False,
            status="not_run",
            reason_code=STEMS_NOT_CONFIGURED,
            adapter="none",
        ),
        None,
    )


_DEFAULT_ADAPTERS: dict[str, StepAdapter] = {
    "track_map": _default_track_map_adapter,
    "arrangement": _default_arrangement_adapter,
    "assets": _default_assets_adapter,
    "stems": _default_stems_adapter,
}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def run_deconstruct(
    track_path: Path,
    pack_root: Path,
    *,
    bpm_normalization: str = "none",
    beat_backend: str = "auto",
    adapters: DeconstructAdapters | None = None,
    skip: set[str] | None = None,
) -> RunResult:
    """Run the headless Track Deconstruction pipeline.

    ``track_path`` is a local audio file. ``pack_root`` is the (possibly new)
    Performance Pack output directory. Adapters may be injected for testing;
    otherwise the production adapters delegate to existing components.
    """
    track_path = Path(track_path)
    pack_root = Path(pack_root)
    skip = set(skip or set())
    adapters = adapters or DeconstructAdapters()

    track = _track_identity(track_path)
    steps: list[StepResult] = []
    reason_codes: list[str] = []
    artifacts: dict[str, object] = {}
    aborted = False

    for step_id, required in STEP_ORDER:
        if aborted:
            steps.append(
                StepResult(
                    step_id=step_id,
                    required=required,
                    status="not_run",
                    reason_code=SKIPPED_REQUIRED,
                )
            )
            continue

        if step_id in skip:
            steps.append(
                StepResult(
                    step_id=step_id,
                    required=required,
                    status="not_run",
                    reason_code=SKIPPED_REQUEST,
                )
            )
            continue

        adapter = adapters.get(step_id) or _DEFAULT_ADAPTERS[step_id]
        ctx = StepContext(
            track_path=track_path,
            pack_root=pack_root,
            bpm_normalization=bpm_normalization,
            beat_backend=beat_backend,
            artifacts=artifacts,
        )

        try:
            result, payload = adapter(ctx)
        except Exception as exc:  # pragma: no cover - defensive
            result = StepResult(
                step_id=step_id,
                required=required,
                status="failed",
                error={
                    "code": "ADAPTER_UNEXPECTED_ERROR",
                    "message": str(exc)[:500],
                },
            )
            payload = None

        if not isinstance(result, StepResult):
            result = StepResult(
                step_id=step_id,
                required=required,
                status="failed",
                error={"code": "BAD_ADAPTER_RESULT", "message": "no StepResult"},
            )
            payload = None

        if result.adapter is None:
            result.adapter = getattr(adapter, "__name__", "injected")

        steps.append(result)
        if payload is not None:
            artifacts[step_id] = payload
        if result.reason_code:
            reason_codes.append(f"{step_id}:{result.reason_code}")
        if result.error:
            reason_codes.append(f"{step_id}:{result.error.get('code')}")

        if required and result.status in ("failed", "no_result"):
            aborted = True

    return RunResult(
        status=_overall_status(steps),
        track=track,
        pack_root=_portable_path(pack_root),
        steps=steps,
        reason_codes=reason_codes,
    )


__all__ = [
    "STEP_ORDER",
    "DeconstructAdapters",
    "RunResult",
    "StepContext",
    "StepResult",
    "run_deconstruct",
]
