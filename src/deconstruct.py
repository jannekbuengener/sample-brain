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
import dataclasses
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
    ("stems", False),
    ("assets", False),
)

SKIPPED_REQUIRED = "SKIPPED_REQUIRED_STEP_FAILED"
SKIPPED_REQUEST = "SKIPPED_BY_REQUEST"
STEMS_NOT_CONFIGURED = "STEMS_NOT_CONFIGURED"
STEMS_NOT_REQUESTED = "STEMS_NOT_REQUESTED"
WEIGHT_IDENTITY_UNAVAILABLE = "WEIGHT_IDENTITY_UNAVAILABLE"
BACKEND_UNAVAILABLE = "BACKEND_UNAVAILABLE"
MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
MISSING_TRACK_MAP_SOURCE = "MISSING_TRACK_MAP_SOURCE"
ARRANGEMENT_UNAVAILABLE = "ARRANGEMENT_UNAVAILABLE"

# Known experimental Demucs baseline filenames (#247) and their released
# checkpoints. These are checkpoint identifiers, NOT cryptographic weight hashes.
_KNOWN_STEM_CHECKPOINTS: dict[str, str] = {
    "htdemucs.yaml": "955717e8",
    "htdemucs_ft.yaml": "f7e0c4bc,d12395a8,92cfc3b6,04573f0d",
}


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
    execution: str | None = None
    cache_key: str | None = None
    track_analysis_cache_status: str | None = None

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
        if self.execution is not None:
            payload["execution"] = self.execution
        if self.cache_key is not None:
            payload["cache_key"] = self.cache_key
        if self.track_analysis_cache_status is not None:
            payload["track_analysis_cache_status"] = self.track_analysis_cache_status
        return payload


@dataclass
class RunResult:
    status: str
    track: dict[str, object]
    pack_root: str
    steps: list[StepResult]
    reason_codes: list[str]
    reused_steps: list[str] = field(default_factory=list)
    computed_steps: list[str] = field(default_factory=list)
    document_type: str = "sample_brain.deconstruct_run"
    schema_version: str = "1.1.0"

    def to_dict(self) -> dict[str, object]:
        return {
            "document_type": self.document_type,
            "schema_version": self.schema_version,
            "status": self.status,
            "track": self.track,
            "pack_root": self.pack_root,
            "steps": [step.to_dict() for step in self.steps],
            "reason_codes": list(self.reason_codes),
            "reused_steps": list(self.reused_steps),
            "computed_steps": list(self.computed_steps),
        }


@dataclass
class StepContext:
    track_path: Path
    pack_root: Path
    bpm_normalization: str
    beat_backend: str
    artifacts: dict[str, object]
    track_cache_dir: Path | None = None
    track_cache_enabled: bool = True
    # Optional stem separation config (issue #249). All optional; the stems step
    # stays a no-op unless `stems_enabled` is set.
    stems_enabled: bool = False
    stem_model: str | None = None
    stem_weight_hash: dict | None = None
    stem_cache_dir: Path | None = None
    stem_cache_enabled: bool = True
    stem_model_cache_dir: Path | None = None
    stem_separation_config: dict | None = None
    stem_executor: object | None = None
    stem_backend_version: str | None = None
    # Optional #374 live-performance layout config. When set, the assets step
    # emits a compact live layout (live/live_layout.json) instead of only the
    # generic loop/section candidate flood.
    live_profile_config: object | None = None


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
    from .content_hash import compute_file_hash

    track_path = Path(track_path)
    ident: dict[str, object] = {
        "file_name": track_path.name,
        "exists": track_path.exists(),
    }
    if track_path.exists():
        try:
            ident["size_bytes"] = track_path.stat().st_size
            ident["hash"] = compute_file_hash(track_path)
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
    from .context_analyze import (
        ContextAnalyzeError,
        TrackAnalysisCacheResult,
        analyze_context_file_cached,
    )

    try:
        result = analyze_context_file_cached(
            ctx.track_path,
            bpm_normalization=ctx.bpm_normalization,
            cache_dir=ctx.track_cache_dir,
            enabled=ctx.track_cache_enabled,
        )
    except ContextAnalyzeError as exc:
        return (
            StepResult(
                step_id="track_map",
                required=True,
                status="failed",
                error={"code": exc.code, "message": exc.message},
                adapter="context_analyze.analyze_context_file_cached",
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
                adapter="context_analyze.analyze_context_file_cached",
            ),
            None,
        )

    track_map = result.track_map

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
            adapter="context_analyze.analyze_context_file_cached",
            provenance=track_map.get("provenance"),
            track_analysis_cache_status=result.cache_status,
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

        _audio_data, _ = sf.read(str(canon), dtype="float32", always_2d=False)
        samples = np.asarray(_audio_data, dtype=np.float32).reshape(-1)
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
    structure = None
    arrangement = None
    beat_grid = None
    canon = None
    timebase = None
    if isinstance(arrangement_payload, dict) and "structure_result" in arrangement_payload:
        structure = arrangement_payload.get("structure_result")
        arrangement = arrangement_payload.get("arrangement_result")
        beat_grid = arrangement_payload.get("beat_grid")
        canon = arrangement_payload.get("canonical_audio_path")
        timebase = arrangement_payload.get("timebase")
    # A valid arrangement enables loop/section generation. The #374 live
    # performance layout does NOT depend on this: full-length tracks come from
    # stems directly and kick_bass from the #268 producer-group path, both with
    # or without an arrangement.
    have_arrangement = (
        structure is not None and canon is not None and timebase is not None
    )

    # Authoritative track ID from Track Map content hash (not file name).
    track = ctx.artifacts.get("track_map")
    track_ref: str | None = None
    if isinstance(track, dict):
        hash_info = (
            track.get("source", {}).get("original", {}).get("hash", {})
        )
        if hash_info.get("value"):
            track_ref = hash_info["value"]

    # --- stems / producer groups (independent of the arrangement step) ---
    # The producer-group derivation (#268) is the authoritative kick_bass source
    # and the basis for full-length melodic/atmos tracks. It only needs stems,
    # never the arrangement result.
    stems_payload = ctx.artifacts.get("stems")
    pg_groups: dict[str, object] = {}
    stem_dicts: dict[str, object] = {}
    pg_audio_paths: dict[str, Path] = {}
    stem_audio_paths: dict[str, Path] = {}
    if stems_payload is not None and isinstance(stems_payload, dict):
        stems_list = stems_payload.get("stems") or []
        track_ref_artifacts = stems_payload.get("track_ref")
        from src.producer_groups import (
            ProducerGroupParams,
            derive_producer_groups,
            write_producer_group_audio,
        )

        for s in stems_list:
            kind = s.get("stem_kind")
            arr = s.get("audio")
            if arr is None:
                arr = s.get("output", {}).get("data")
            # If still no audio data, try to load from the stem WAV on disk.
            if arr is None:
                file_ref = s.get("file_ref")
                if file_ref:
                    stem_path = ctx.pack_root / file_ref
                    if stem_path.exists():
                        try:
                            arr, _ = sf.read(
                                str(stem_path), dtype="float32", always_2d=False
                            )
                            arr = np.asarray(arr, dtype=np.float32)
                        except Exception:
                            arr = None
            if arr is not None and kind in ("drums", "bass", "vocals", "other"):
                arr = np.asarray(arr, dtype=np.float32)
                if arr.ndim == 2:
                    arr = arr.mean(axis=1)
                stem_dicts[kind] = arr

        for s in stems_list:
            kind = s.get("stem_kind")
            file_ref = s.get("file_ref")
            if kind and file_ref and kind in ("drums", "bass", "vocals", "other"):
                stem_audio_paths[kind] = ctx.pack_root / file_ref

        if stem_dicts:
            params = ProducerGroupParams()
            pg_groups = derive_producer_groups(
                stem_dicts,
                params=params,
                track_ref=track_ref_artifacts or "/source/working_audio",
            )
            pg_dir = ctx.pack_root / "producer_groups"
            pg_dir.mkdir(parents=True, exist_ok=True)
            for g in pg_groups.values():
                if g.status in ("ok", "partial") and g.audio is not None:
                    rel = write_producer_group_audio(g, ctx.pack_root)
                    if rel:
                        pg_audio_paths[g.group_kind] = ctx.pack_root / rel

    # --- optional #374 live performance layout (independent of arrangement) ---
    live_layout_ref: str | None = None
    if ctx.live_profile_config is not None:
        from . import live_profile as _lp

        # Bar/beat grid is optional evidence for playable-loop slicing. Without a
        # valid grid, loops are reported as truthful no_result (never invented).
        _bars: list[int] | None = None
        if beat_grid is not None and getattr(beat_grid, "downbeats", None) is not None:
            _bs = getattr(beat_grid.downbeats, "sample_indices", ())
            if _bs:
                _bars = [int(b) for b in _bs]

        _sr = 44100
        if pg_groups:
            _sr = next(iter(pg_groups.values())).timebase.sample_rate
        elif timebase is not None:
            _sr = timebase.sample_rate

        _layout = _lp.build_live_layout(
            pg_groups,
            stem_dicts,
            ctx.live_profile_config,
            bars=_bars,
            pack_root=ctx.pack_root,
            sample_rate=_sr,
            source_track_ref=track_ref,
        )
        live_layout_ref = _lp.write_live_layout(_layout, ctx.pack_root)

    # --- loop/section candidate generation (requires a valid arrangement) ---
    manifest_refs: list[str] = []
    if have_arrangement and track_ref is not None:
        loops_dir = ctx.pack_root / "loops"
        sections_dir = ctx.pack_root / "sections"
        loops_dir.mkdir(parents=True, exist_ok=True)
        sections_dir.mkdir(parents=True, exist_ok=True)

        # --- master source (always available) ---
        loop_src_master = LoopSourceIdentity(
            source_kind="master", track_audio_ref="/source/working_audio"
        )
        loop_batch_master = generate_loop_candidates(
            loop_src_master, beat_grid=beat_grid, structure=structure
        )
        section_src_master = SectionSourceIdentity(
            source_kind="master", track_audio_ref="/source/working_audio"
        )
        section_batch_master = generate_section_candidates(
            structure, arrangement, source=section_src_master, track_ref=track_ref
        )

        # --- producer group / stem sources (optional; if stems are available) ---
        loop_src_producer_groups: LoopSourceIdentity | None = None
        loop_batch_producer_groups: LoopCandidateBatch | None = None
        section_src_producer_groups: SectionSourceIdentity | None = None
        section_batch_producer_groups: SectionCandidateBatch | None = None
        loop_src_stems: LoopSourceIdentity | None = None
        loop_batch_stems: LoopCandidateBatch | None = None
        section_src_stems: SectionSourceIdentity | None = None
        section_batch_stems: SectionCandidateBatch | None = None

        if "kick_bass" in pg_groups and pg_groups["kick_bass"].status in (
            "ok",
            "partial",
        ):
            loop_src_producer_groups = LoopSourceIdentity(
                source_kind="producer_group",
                producer_group_id=pg_groups["kick_bass"].group_id,
                producer_group_ref=pg_groups["kick_bass"].group_ref,
            )
            loop_batch_producer_groups = generate_loop_candidates(
                loop_src_producer_groups, beat_grid=beat_grid, structure=structure
            )
            section_src_producer_groups = SectionSourceIdentity(
                source_kind="producer_group",
                producer_group_id=pg_groups["kick_bass"].group_id,
                producer_group_ref=pg_groups["kick_bass"].group_ref,
            )
            section_batch_producer_groups = generate_section_candidates(
                structure,
                arrangement,
                source=section_src_producer_groups,
                track_ref=track_ref_artifacts or "/source/working_audio",
            )

        # Generate stem-based loop/section candidates for one technical stem.
        for stem_kind in ("drums", "bass", "vocals", "other"):
            if stem_kind in stem_dicts and stem_kind not in [
                g.group_kind for g in pg_groups.values()
            ]:
                stem_id = f"stem_{stem_kind}"
                stem_ref = f"stemmanifest_{stem_kind}"
                loop_src_stems = LoopSourceIdentity(
                    source_kind="stem", stem_id=stem_id, stem_ref=stem_ref
                )
                loop_batch_stems = generate_loop_candidates(
                    loop_src_stems, beat_grid=beat_grid, structure=structure
                )
                section_src_stems = SectionSourceIdentity(
                    source_kind="stem", stem_id=stem_id, stem_ref=stem_ref
                )
                section_batch_stems = generate_section_candidates(
                    structure,
                    arrangement,
                    source=section_src_stems,
                    track_ref=track_ref_artifacts or "/source/working_audio",
                )
                break

        all_loop_batches: list[LoopCandidateBatch] = [loop_batch_master]
        all_section_batches: list[SectionCandidateBatch] = [section_batch_master]

        if (
            loop_batch_producer_groups is not None
            and loop_batch_producer_groups.status != "no_result"
        ):
            all_loop_batches.append(loop_batch_producer_groups)
        if loop_batch_stems is not None and loop_batch_stems.status != "no_result":
            all_loop_batches.append(loop_batch_stems)

        if (
            section_batch_producer_groups is not None
            and section_batch_producer_groups.status != "no_result"
        ):
            all_section_batches.append(section_batch_producer_groups)
        if (
            section_batch_stems is not None
            and section_batch_stems.status != "no_result"
        ):
            all_section_batches.append(section_batch_stems)

        merged_loop_candidates: list[LoopCandidate] = []
        for batch in all_loop_batches:
            merged_loop_candidates.extend(batch.candidates)

        merged_section_candidates: list[SectionCandidate] = []
        for batch in all_section_batches:
            merged_section_candidates.extend(batch.candidates)

        bar_features = getattr(structure, "bar_features", {})

        def _read_slice_from(path: Path, start: int, n: int):
            with sf.SoundFile(str(path)) as f:
                f.seek(start)
                return np.asarray(
                    f.read(frames=n, dtype="float32", always_2d=False),
                    dtype=np.float32,
                ).reshape(-1)

        def _get_source_audio_path(cand) -> Path | None:
            src_kind = cand.source.source_kind
            if src_kind == "master":
                return canon
            elif src_kind == "stem":
                stem_id = cand.source.stem_id or ""
                if stem_id.startswith("stem_"):
                    return stem_audio_paths.get(stem_id[5:])
                return None
            elif src_kind == "producer_group":
                pg_ref = cand.source.producer_group_ref or ""
                if pg_ref.startswith("producergroup_"):
                    return pg_audio_paths.get(pg_ref[14:])
                return None
            return None

        def _get_source_kind(cand) -> str:
            return cand.source.source_kind

        if loop_batch_master.status != "failed":
            for cand in merged_loop_candidates:
                try:
                    aid = getattr(
                        cand,
                        "asset_id",
                        f"{cand.bar_count}bar_{cand.start_sample}_{cand.end_sample_exclusive}",
                    )
                    unique_asset_id = f"{cand.source.source_kind}_{aid}"
                    src_path = _get_source_audio_path(cand)
                    if src_path is None or not src_path.exists():
                        continue
                    req = render_request_from_loop_candidate(
                        cand, src_path, asset_id=unique_asset_id
                    )
                    res = render_asset(req, ctx.pack_root)
                    manifest = {
                        "document_type": "sample_brain.asset_manifest",
                        "schema_version": "1.1.0",
                        "asset_id": req.asset_id,
                        "asset_kind": "loop",
                        "track_ref": track_ref,
                        **cand.as_manifest_dict(),
                    }
                    try:
                        wave = _read_slice_from(
                            src_path, cand.start_sample, cand.n_samples
                        )
                        score = score_loop_candidate(
                            cand,
                            wave,
                            sample_rate=timebase.sample_rate,
                            source_kind=_get_source_kind(cand),
                            config=default_loop_scoring_config(),
                        )
                        manifest["candidate"] = score.as_candidate_dict()
                    except Exception:
                        score = None
                    manifest["rendering"] = res.as_manifest_rendering()
                    if res.status == "rendered":
                        manifest = attach_rendered_asset_analysis(
                            manifest, audio_root=ctx.pack_root
                        )
                    fname = f"loop_{_safe_name(req.asset_id)}.json"
                    (loops_dir / fname).write_text(
                        json.dumps(manifest, indent=2, sort_keys=True, default=str),
                        encoding="utf-8",
                    )
                    manifest_refs.append(f"loops/{fname}")
                except Exception:
                    continue

        if section_batch_master.status != "failed":
            for cand in merged_section_candidates:
                try:
                    aid = getattr(cand, "asset_id", f"section_{cand.section_ref}")
                    unique_asset_id = f"{cand.source.source_kind}_{aid}"
                    src_path = _get_source_audio_path(cand)
                    if src_path is None or not src_path.exists():
                        continue
                    req = render_request_from_section_candidate(
                        cand, src_path, asset_id=unique_asset_id
                    )
                    res = render_asset(req, ctx.pack_root)
                    manifest = {
                        "document_type": "sample_brain.asset_manifest",
                        "schema_version": "1.1.0",
                        "asset_id": cand.asset_id,
                        "asset_kind": "section",
                        **cand.as_manifest_dict(),
                    }
                    try:
                        wave = _read_slice_from(
                            src_path, cand.start_sample, cand.n_samples
                        )
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
                            manifest, audio_root=ctx.pack_root
                        )
                    fname = f"section_{_safe_name(unique_asset_id)}.json"
                    (sections_dir / fname).write_text(
                        json.dumps(manifest, indent=2, sort_keys=True, default=str),
                        encoding="utf-8",
                    )
                    manifest_refs.append(f"sections/{fname}")
                except Exception:
                    continue

    if live_layout_ref is not None:
        manifest_refs.append(live_layout_ref)

    # Determine step status. A produced live layout is a valid, complete asset
    # output even when no loop/section candidates could be generated.
    if manifest_refs:
        step_status = "ok"
        reason = None
    elif have_arrangement:
        step_status = "no_result"
        reason = "NO_ASSET_CANDIDATES"
    else:
        step_status = "no_result"
        reason = ARRANGEMENT_UNAVAILABLE

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
    """Optional stem separation step (issue #249).

    Opt-in only: when ``ctx.stems_enabled`` is False the step reports
    ``not_run`` with ``STEMS_NOT_REQUESTED`` and nothing is launched (no heavy
    dependency import, no subprocess). When enabled, truthful model/weight
    provenance is required, the canonical working audio is used as the exact
    separation input, and #248 ``separate_with_cache`` is consulted (pack-local
    resume is checked earlier by the orchestrator). Stems remain optional: a
    failure here never fails the whole Track Deconstruction.
    """
    if not ctx.stems_enabled:
        return (
            StepResult(
                step_id="stems",
                required=False,
                status="not_run",
                reason_code=STEMS_NOT_REQUESTED,
                adapter="none",
            ),
            None,
        )

    # Authoritative portable track identity from the completed Track Map.
    track_ref = _stem_track_ref(ctx.artifacts.get("track_map"))
    if track_ref is None:
        return (
            _not_run_stems(MISSING_TRACK_MAP_SOURCE, adapter="stems.track_identity"),
            None,
        )

    # Model + weight identity (truthful provenance, no fabrication).
    if not ctx.stem_model:
        return (_not_run_stems(WEIGHT_IDENTITY_UNAVAILABLE), None)
    expected_algo = _KNOWN_STEM_CHECKPOINTS and _stem_expected_weight_algo(ctx.stem_model)
    if expected_algo is None:
        return (_not_run_stems(MODEL_UNAVAILABLE), None)
    if not isinstance(ctx.stem_weight_hash, dict) or not ctx.stem_weight_hash.get("value"):
        return (_not_run_stems(WEIGHT_IDENTITY_UNAVAILABLE), None)
    supplied_algo = ctx.stem_weight_hash.get("algorithm")
    if supplied_algo and supplied_algo != expected_algo:
        # Algorithm must match the selected known model (#247/#248).
        return (_not_run_stems(WEIGHT_IDENTITY_UNAVAILABLE), None)
    weight_hash = {"algorithm": expected_algo, "value": ctx.stem_weight_hash["value"]}

    # Exact bytes sent to the separator: prefer the canonical working audio.
    sep_input = _stem_separation_input(ctx)
    working_audio_hash = _sha256_of_file(sep_input)

    from .stem_cache import (
        known_htdemucs_ft_identity,
        known_htdemucs_identity,
    )

    if ctx.stem_model == "htdemucs.yaml":
        model_identity = known_htdemucs_identity(weight_hash=weight_hash)
    elif ctx.stem_model == "htdemucs_ft.yaml":
        model_identity = known_htdemucs_ft_identity(weight_hash=weight_hash)
    else:
        return (_not_run_stems(MODEL_UNAVAILABLE), None)

    configuration = dict(ctx.stem_separation_config or {})
    backend_name = "python-audio-separator"
    backend_version = ctx.stem_backend_version or _resolve_stem_backend_version()

    executor = ctx.stem_executor
    if executor is None:
        from .stem_runtime import build_subprocess_executor

        executor = build_subprocess_executor(
            model_cache_dir=ctx.stem_model_cache_dir,
            backend_version=ctx.stem_backend_version,
        )

    from .stem_cache import separate_with_cache

    result = separate_with_cache(
        input_path=sep_input,
        track_ref=track_ref,
        working_audio_hash=working_audio_hash,
        model_identity=model_identity,
        configuration=configuration,
        output_dir=ctx.pack_root,
        cache_dir=ctx.stem_cache_dir,
        cache_enabled=ctx.stem_cache_enabled,
        backend_name=backend_name,
        backend_version=backend_version,
        executor=executor,
    )

    return _stem_result_from_cache(
        result,
        track_ref=track_ref,
        working_audio_hash=working_audio_hash,
        model_identity=model_identity,
        backend_name=backend_name,
        backend_version=backend_version,
    )


def _not_run_stems(reason_code: str, *, adapter: str = "stems.separate_with_cache") -> StepResult:
    return StepResult(
        step_id="stems",
        required=False,
        status="not_run",
        reason_code=reason_code,
        adapter=adapter,
    )


def _stem_track_ref(track_map: object) -> str | None:
    """Authoritative portable track identity from the completed Track Map.

    Uses ``track_map.source.original.hash.value``. Returns None if missing so the
    step fails/not_runs safely (no filename/path/UUID fallback).
    """
    if not isinstance(track_map, dict):
        return None
    src = track_map.get("source")
    if not isinstance(src, dict):
        return None
    original = src.get("original")
    if not isinstance(original, dict):
        return None
    h = original.get("hash")
    if not isinstance(h, dict):
        return None
    value = h.get("value")
    if not isinstance(value, str) or not value:
        return None
    return value


def _stem_separation_input(ctx: StepContext) -> Path:
    """Return the exact audio bytes sent to the separator.

    Prefers the canonical working audio already produced by the arrangement
    step; otherwise renders it with the existing #234 ``canon_audio`` helpers so
    no separate conversion path is invented.
    """
    from .canon_audio import render_canonical_wav

    working = ctx.pack_root / "analysis" / "working_audio.wav"
    if not working.exists():
        render_canonical_wav(ctx.track_path, working)
    return working


def _sha256_of_file(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _stem_expected_weight_algo(model_filename: str) -> str | None:
    if model_filename == "htdemucs.yaml":
        return "sha256"
    if model_filename == "htdemucs_ft.yaml":
        return "sha256-set-v1"
    return None


def _resolve_stem_backend_version() -> str:
    from .stem_runtime import resolve_backend_version

    return resolve_backend_version()


def _stem_result_from_cache(
    result: dict,
    *,
    track_ref: str,
    working_audio_hash: str,
    model_identity: object,
    backend_name: str,
    backend_version: str,
) -> tuple[StepResult, object]:
    """Translate a #248 ``separate_with_cache`` result into a stems StepResult."""
    status = result.get("status")
    reason_code = result.get("reason_code")
    error = result.get("error")
    cache_status = result.get("cache_status")
    stems = result.get("stems") or []

    output_refs = tuple(
        f"stems/{st['manifest_ref']}" for st in stems if st.get("manifest_ref")
    )

    provenance = {
        "component": "stem_separator",
        "experimental": True,
        "production_default": "NO_GO",
        "backend": {"name": backend_name, "version": backend_version},
        "model": model_identity.to_provenance(),
        "stem_cache_status": cache_status,
        "track_ref": track_ref,
        "working_audio_hash": working_audio_hash,
    }

    allowed_statuses = ("ok", "partial", "failed", "not_run", "no_result")
    step_status = status if status in allowed_statuses else "failed"
    if status not in allowed_statuses:
        error = {
            "code": "STEM_RUNTIME_UNKNOWN_STATUS",
            "message": "Stem runtime returned an unknown status.",
        }
    return (
        StepResult(
            step_id="stems",
            required=False,
            status=step_status,
            output_refs=output_refs,
            reason_code=reason_code if step_status in ("not_run", "no_result") else None,
            error=error if step_status == "failed" else None,
            adapter="stems.separate_with_cache",
            provenance=provenance,
        ),
        {"stems": stems, "track_ref": track_ref},
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
    resume: bool = True,
    track_cache_dir: Path | None = None,
    track_cache_enabled: bool = True,
    stems_enabled: bool = False,
    stem_model: str | None = None,
    stem_weight_hash: dict | None = None,
    stem_cache_dir: Path | None = None,
    stem_cache_enabled: bool = True,
    stem_model_cache_dir: Path | None = None,
    stem_separation_config: dict | None = None,
    stem_executor: object | None = None,
    stem_backend_version: str | None = None,
    live_profile_config: object | None = None,
) -> RunResult:
    """Run the headless Track Deconstruction pipeline.

    ``track_path`` is a local audio file. ``pack_root`` is the (possibly new)
    Performance Pack output directory. Adapters may be injected for testing;
    otherwise the production adapters delegate to existing components.

    When ``resume`` is True (default) and a compatible pack-local resume state
    exists, valid step results are reused and only affected steps recomputed;
    see ``src.deconstruct_resume`` and ``docs/PERFORMANCE_PACK_RESUME_V1.md``.
    """
    from . import deconstruct_resume as _resume

    track_path = Path(track_path)
    pack_root = Path(pack_root)
    skip = set(skip or set())
    adapters = adapters or DeconstructAdapters()

    # Stem resume fingerprint fields (output-affecting config only).
    stem_options: dict[str, object] = (
        {
            "enabled": True,
            "model": stem_model,
            "checkpoint": _KNOWN_STEM_CHECKPOINTS.get(stem_model) if stem_model else None,
            "weight_hash": stem_weight_hash.get("value")
            if isinstance(stem_weight_hash, dict)
            else None,
            "weight_hash_algo": stem_weight_hash.get("algorithm")
            if isinstance(stem_weight_hash, dict)
            else None,
            "separation": dict(stem_separation_config or {}),
        }
        if stems_enabled
        else {"enabled": False}
    )

    source_hash = _resume.source_content_hash_sha256(track_path)
    prior = _resume.load_resume_state(pack_root) if resume else None
    # Source content changed -> discard entire prior state (full recompute).
    if prior is not None and prior.get("source", {}).get("content_hash_sha256") != source_hash:
        prior = None

    track = _track_identity(track_path)
    steps: list[StepResult] = []
    reason_codes: list[str] = []
    artifacts: dict[str, object] = {}
    aborted = False
    upstream_cache_keys: dict[str, str] = {}
    reused_ids: list[str] = []
    computed_ids: list[str] = []

    state: dict[str, object] = {
        "document_type": _resume.RESUME_DOC_TYPE,
        "schema_version": _resume.RESUME_SCHEMA_VERSION,
        "source": {
            "id": track.get("file_name"),
            "content_hash_sha256": source_hash,
            "pack_root_portable": ".",
        },
        "contract_versions": dict(_resume.CONTRACT_VERSIONS),
        "steps": {},
    }

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

        cache_key = _resume.compute_step_cache_key(
            step_id,
            source_content_hash=source_hash,
            config=_resume._relevant_config(
                step_id, bpm_normalization, beat_backend, stem_options=stem_options
            ),
            upstream_cache_keys=upstream_cache_keys,
        )

        reusable = False
        if prior is not None and step_id not in skip:
            reusable = _resume.step_is_reusable(
                prior, step_id, cache_key=cache_key, pack_root=pack_root
            )
            if step_id == "arrangement" and not (prior.get("steps", {}).get(step_id, {}) or {}).get("snapshot"):
                reusable = False

        if reusable:
            entry = prior["steps"][step_id]  # type: ignore[index]
            output_refs = tuple(entry.get("output_refs", []))
            result = StepResult(
                step_id=step_id,
                required=required,
                status=entry.get("status", "ok"),
                output_refs=output_refs,
                reason_code=entry.get("reason_code"),
                adapter=entry.get("adapter"),
                provenance=entry.get("provenance"),
                execution="reused",
                cache_key=cache_key,
            )
            payload = _reuse_payload(step_id, entry, pack_root)
            # carry the stored step record forward verbatim
            state["steps"][step_id] = dict(entry)  # type: ignore[arg-type]
            reused_ids.append(step_id)
        else:
            # Best-effort cleanup: drop this step's prior inventoried files so a
            # recompute does not leave stale outputs behind (Cleanup-Regel).
            if prior is not None:
                prior_entry = prior.get("steps", {}).get(step_id)
                if isinstance(prior_entry, dict):
                    for inv in prior_entry.get("output_inventory", []):
                        ref = inv.get("ref")
                        if ref:
                            try:
                                (pack_root / ref).unlink(missing_ok=True)
                            except OSError:
                                pass
            adapter = adapters.get(step_id) or _DEFAULT_ADAPTERS[step_id]
            ctx = StepContext(
                track_path=track_path,
                pack_root=pack_root,
                bpm_normalization=bpm_normalization,
                beat_backend=beat_backend,
                artifacts=artifacts,
                track_cache_dir=track_cache_dir,
                track_cache_enabled=track_cache_enabled,
                stems_enabled=stems_enabled,
                stem_model=stem_model,
                stem_weight_hash=stem_weight_hash,
                stem_cache_dir=stem_cache_dir,
                stem_cache_enabled=stem_cache_enabled,
                stem_model_cache_dir=stem_model_cache_dir,
                stem_separation_config=stem_separation_config,
                stem_executor=stem_executor,
                stem_backend_version=stem_backend_version,
                live_profile_config=live_profile_config,
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

            result = dataclasses.replace(result, execution="computed", cache_key=cache_key)

            inventory = _resume.build_output_inventory(
                pack_root, step_id, result.output_refs
            )
            snapshot = (
                _resume.snapshot_arrangement(payload)
                if step_id == "arrangement" and isinstance(payload, dict)
                else None
            )
            entry = {
                "status": result.status,
                "cache_key": cache_key,
                "output_refs": list(result.output_refs),
                "output_inventory": inventory,
            }
            if result.reason_code is not None:
                entry["reason_code"] = result.reason_code
            if result.adapter is not None:
                entry["adapter"] = result.adapter
            if snapshot is not None:
                entry["snapshot"] = snapshot
            if result.provenance is not None:
                entry["provenance"] = result.provenance
            state["steps"][step_id] = entry
            computed_ids.append(step_id)

        steps.append(result)
        if payload is not None:
            artifacts[step_id] = payload
        if result.reason_code:
            reason_codes.append(f"{step_id}:{result.reason_code}")
        if result.error:
            reason_codes.append(f"{step_id}:{result.error.get('code')}")

        upstream_cache_keys[step_id] = cache_key

        # Atomic, per-step persist for crash safety (resume after interruption).
        _resume.save_resume_state(pack_root, state)

        if required and result.status in ("failed", "no_result"):
            aborted = True

    return RunResult(
        status=_overall_status(steps),
        track=track,
        pack_root=_portable_path(pack_root),
        steps=steps,
        reason_codes=reason_codes,
        reused_steps=reused_ids,
        computed_steps=computed_ids,
    )


def _reuse_payload(step_id: str, entry: dict, pack_root: Path) -> object:
    """Reconstruct the artifacts payload for a reused step."""
    from . import deconstruct_resume as _resume

    if step_id == "track_map":
        try:
            return json.loads((pack_root / "analysis" / "track_map.json").read_text(encoding="utf-8"))
        except Exception:
            return None
    if step_id == "arrangement":
        return _resume.resume_arrangement(entry.get("snapshot") or {}, pack_root)
    if step_id == "assets":
        return {"manifest_refs": list(entry.get("output_refs", []))}
    if step_id == "stems":
        stems_list: list[dict] = []
        track_ref: str | None = None
        for ref in entry.get("output_refs", []):
            try:
                meta = json.loads((pack_root / ref).read_text(encoding="utf-8"))
                kind = meta.get("stem_kind")
                file_ref = meta.get("output", {}).get("file_ref")
                if kind and file_ref:
                    stem_path = pack_root / "stems" / file_ref
                    if stem_path.exists():
                        arr, _ = sf.read(
                            str(stem_path), dtype="float32", always_2d=False
                        )
                        stems_list.append({
                            "stem_kind": kind,
                            "file_ref": f"stems/{file_ref}",
                            "audio": np.asarray(arr, dtype=np.float32),
                        })
                if not track_ref:
                    track_ref = meta.get("track_ref")
            except Exception:
                continue
        if stems_list:
            return {"stems": stems_list, "track_ref": track_ref or ""}
    return None


__all__ = [
    "STEP_ORDER",
    "DeconstructAdapters",
    "RunResult",
    "StepContext",
    "StepResult",
    "run_deconstruct",
]
