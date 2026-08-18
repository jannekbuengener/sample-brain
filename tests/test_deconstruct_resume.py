"""Tests for pack-local resume + cache reuse (#262).

These tests target ``src.deconstruct_resume`` and the resume integration in
``src.deconstruct.run_deconstruct``. They use synthetic WAVs and injected
adapters only (no real audio pipeline, no private data).

Red-gate expectation: before ``src.deconstruct_resume`` exists, the imports fail
and every test errors. After implementation the suite must pass.
"""

import json
import hashlib
from pathlib import Path

import pytest

from src.deconstruct import (
    STEP_ORDER,
    DeconstructAdapters,
    RunResult,
    StepContext,
    StepResult,
    run_deconstruct,
)
from tests.audio_fixtures import write_kick_transient_wav
from src.deconstruct_resume import (
    CACHEABLE_STATUSES,
    CONTRACT_VERSIONS,
    RESUME_DOC_TYPE,
    RESUME_SCHEMA_VERSION,
    build_output_inventory,
    compute_step_cache_key,
    load_resume_state,
    save_resume_state,
    snapshot_arrangement,
    source_content_hash_sha256,
    step_is_reusable,
    verify_output_inventory,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_wav(path: Path, seconds: float = 0.5, sr: int = 44100) -> None:
    import numpy as np
    import soundfile as sf

    path.parent.mkdir(parents=True, exist_ok=True)
    n = int(seconds * sr)
    data = np.zeros((n,), dtype=np.float32)
    sf.write(str(path), data, sr)


def _write_text(pack_root: Path, ref: str, content: str = "{}") -> None:
    p = pack_root / ref
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def _real_arrangement_payload(pack_root: Path) -> dict:
    from src.arrangement_classifier import (
        ArrangementEvidence,
        ArrangementResult,
        AutomaticResult,
        EffectiveValue,
        SectionClassification,
    )
    from src.beat_grid import BeatGridResult, BeatGridSeries, BeatGridSource
    from src.canon_audio import AudioTimebase
    from src.structure_v1 import (
        StructureBoundary,
        StructureSection,
        StructureV1Result,
        StructureV1Source,
    )

    tb = AudioTimebase(sample_rate=44100, n_samples=44100)
    series = BeatGridSeries(
        status="ok", sample_indices=(0, 44100), times_sec=(0.0, 1.0)
    )
    bg = BeatGridResult(
        status="ok",
        bpm=120.0,
        beats=series,
        downbeats=series,
        source=BeatGridSource(
            component="beat_grid",
            backend="librosa",
            backend_version="0",
            checkpoint=None,
            config={},
        ),
    )
    structure = StructureV1Result(
        status="ok",
        boundaries=(
            StructureBoundary(
                sample_index=0,
                time_sec=0.0,
                bar_index=0,
                downbeat_index=0,
                score=0.5,
                contributing_signals=(),
            ),
        ),
        sections=(
            StructureSection(
                id="s1",
                start_sample=0,
                end_sample=44100,
                start_sec=0.0,
                end_sec=1.0,
                start_bar=0,
                end_bar=1,
            ),
        ),
        feature_status={},
        notes=(),
        source=StructureV1Source(backend="structure_v1", backend_version="0", config={}),
        bar_features={},
    )
    arr = ArrangementResult(
        sections=(
            SectionClassification(
                section_id="s1",
                start_sec=0.0,
                end_sec=1.0,
                start_bar=0,
                end_bar=1,
                automatic_result=AutomaticResult(
                    role="groove",
                    event=None,
                    status="available",
                    evidence=ArrangementEvidence(),
                    provenance={},
                ),
                manual_override=None,
                effective_value=EffectiveValue(role="groove", event=None, source="automatic"),
            ),
        ),
        events=(),
        status="available",
        provenance={},
    )
    return {
        "structure_result": structure,
        "arrangement_result": arr,
        "beat_grid": bg,
        "timebase": tb,
        "canonical_audio_path": pack_root / "analysis" / "working_audio.wav",
    }


def _recording_adapter(
    step_id: str,
    *,
    required: bool,
    status: str = "ok",
    output_refs: tuple[str, ...] = (),
    calls: list[str],
    writes_wav: bool = False,
    payload_factory=None,
):
    """Injected adapter that records calls and writes declared outputs."""

    def adapter(ctx: StepContext):
        calls.append(step_id)
        for ref in output_refs:
            _write_text(ctx.pack_root, ref)
        if writes_wav:
            wav = ctx.pack_root / "analysis" / "working_audio.wav"
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(b"WAVDATA")
        payload = payload_factory(ctx) if payload_factory is not None else None
        return (
            StepResult(
                step_id=step_id,
                required=required,
                status=status,
                output_refs=output_refs,
                adapter="mock",
            ),
            payload,
        )

    return adapter


def _adapters_reuse_all(pack_root, calls):
    return DeconstructAdapters(
        track_map=_recording_adapter(
            "track_map",
            required=True,
            output_refs=("analysis/track_map.json",),
            calls=calls,
        ),
        arrangement=_recording_adapter(
            "arrangement",
            required=False,
            output_refs=("analysis/arrangement_map.json",),
            writes_wav=True,
            calls=calls,
            payload_factory=lambda ctx: _real_arrangement_payload(ctx.pack_root),
        ),
        assets=_recording_adapter(
            "assets",
            required=False,
            output_refs=("loops/loop_a.json",),
            calls=calls,
        ),
        stems=_recording_adapter(
            "stems", required=False, status="not_run", calls=calls
        ),
    )


# ---------------------------------------------------------------------------
# Cache key
# ---------------------------------------------------------------------------


def test_compute_step_cache_key_deterministic():
    a = compute_step_cache_key(
        "track_map",
        source_content_hash="abc",
        config={"bpm_normalization": "none"},
        upstream_cache_keys={},
    )
    b = compute_step_cache_key(
        "track_map",
        source_content_hash="abc",
        config={"bpm_normalization": "none"},
        upstream_cache_keys={},
    )
    assert a == b
    assert len(a) == 64


def test_compute_step_cache_key_changes_with_config():
    base = compute_step_cache_key(
        "arrangement",
        source_content_hash="abc",
        config={"beat_backend": "auto", "bpm_normalization": "none"},
        upstream_cache_keys={"track_map": "k1"},
    )
    changed = compute_step_cache_key(
        "arrangement",
        source_content_hash="abc",
        config={"beat_backend": "librosa", "bpm_normalization": "none"},
        upstream_cache_keys={"track_map": "k1"},
    )
    assert base != changed


def test_compute_step_cache_key_changes_with_upstream():
    base = compute_step_cache_key(
        "assets",
        source_content_hash="abc",
        config={},
        upstream_cache_keys={"arrangement": "k1"},
    )
    changed = compute_step_cache_key(
        "assets",
        source_content_hash="abc",
        config={},
        upstream_cache_keys={"arrangement": "k2"},
    )
    assert base != changed


def test_compute_step_cache_key_changes_with_source():
    base = compute_step_cache_key(
        "track_map",
        source_content_hash="aaa",
        config={"bpm_normalization": "none"},
        upstream_cache_keys={},
    )
    changed = compute_step_cache_key(
        "track_map",
        source_content_hash="bbb",
        config={"bpm_normalization": "none"},
        upstream_cache_keys={},
    )
    assert base != changed


def test_source_hash_deterministic_and_distinct(tmp_path):
    f1 = tmp_path / "a.wav"
    f2 = tmp_path / "b.wav"
    _make_wav(f1, seconds=0.5)
    _make_wav(f2, seconds=0.7)
    assert source_content_hash_sha256(f1) == source_content_hash_sha256(f1)
    assert source_content_hash_sha256(f1) != source_content_hash_sha256(f2)


# ---------------------------------------------------------------------------
# State load/save (atomic)
# ---------------------------------------------------------------------------


def test_save_load_resume_state_roundtrip(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    state = {
        "document_type": RESUME_DOC_TYPE,
        "schema_version": RESUME_SCHEMA_VERSION,
        "source": {"content_hash_sha256": "x"},
        "contract_versions": dict(CONTRACT_VERSIONS),
        "steps": {},
    }
    save_resume_state(pack, state)
    loaded = load_resume_state(pack)
    assert loaded is not None
    assert loaded["document_type"] == RESUME_DOC_TYPE
    assert loaded["steps"] == {}


def test_load_resume_state_missing_returns_none(tmp_path):
    assert load_resume_state(tmp_path / "nope") is None


def test_load_resume_state_corrupt_returns_none(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "deconstruct_resume.json").write_text("{not json", encoding="utf-8")
    assert load_resume_state(pack) is None


def test_load_resume_state_wrong_doctype_returns_none(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "deconstruct_resume.json").write_text(
        json.dumps({"document_type": "other"}), encoding="utf-8"
    )
    assert load_resume_state(pack) is None


# ---------------------------------------------------------------------------
# Output inventory + integrity
# ---------------------------------------------------------------------------


def test_build_output_inventory_includes_wav_for_arrangement(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write_text(pack, "analysis/arrangement_map.json")
    wav = pack / "analysis" / "working_audio.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"WAVDATA")
    inv = build_output_inventory(
        pack, "arrangement", ("analysis/arrangement_map.json",)
    )
    refs = {entry["ref"] for entry in inv}
    assert "analysis/arrangement_map.json" in refs
    assert "analysis/working_audio.wav" in refs
    for entry in inv:
        assert "sha256" in entry


def test_verify_output_inventory_missing_file_fails(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    inv = [{"ref": "analysis/missing.json", "sha1": "deadbeef"}]
    assert verify_output_inventory(pack, inv) is False


def test_verify_output_inventory_sha_mismatch_fails(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write_text(pack, "analysis/x.json", "hello")
    inv = [{"ref": "analysis/x.json", "sha1": "wrong"}]
    assert verify_output_inventory(pack, inv) is False


def test_verify_output_inventory_ok(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write_text(pack, "analysis/x.json", "hello")
    sha = hashlib.sha1(b"hello").hexdigest()
    inv = [{"ref": "analysis/x.json", "sha1": sha}]
    assert verify_output_inventory(pack, inv) is True


# ---------------------------------------------------------------------------
# Reusability
# ---------------------------------------------------------------------------


def _prior_ok(step_id, cache_key, inventory):
    return {
        "document_type": RESUME_DOC_TYPE,
        "schema_version": RESUME_SCHEMA_VERSION,
        "source": {"content_hash_sha256": "x"},
        "contract_versions": dict(CONTRACT_VERSIONS),
        "steps": {
            step_id: {
                "status": "ok",
                "cache_key": cache_key,
                "output_inventory": inventory,
            }
        },
    }


def test_step_is_reusable_true(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write_text(pack, "analysis/track_map.json", "data")
    sha = hashlib.sha1(b"data").hexdigest()
    prior = _prior_ok(
        "track_map", "k1", [{"ref": "analysis/track_map.json", "sha1": sha}]
    )
    assert step_is_reusable(prior, "track_map", cache_key="k1", pack_root=pack) is True


def test_step_is_reusable_false_status_failed(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    prior = _prior_ok("track_map", "k1", [])
    prior["steps"]["track_map"]["status"] = "failed"
    assert step_is_reusable(prior, "track_map", cache_key="k1", pack_root=pack) is False


def test_step_is_reusable_false_not_run(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    prior = _prior_ok("stems", "k1", [])
    prior["steps"]["stems"]["status"] = "not_run"
    assert step_is_reusable(prior, "stems", cache_key="k1", pack_root=pack) is False


def test_step_is_reusable_false_cache_key_mismatch(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write_text(pack, "analysis/track_map.json", "data")
    sha = hashlib.sha1(b"data").hexdigest()
    prior = _prior_ok(
        "track_map", "k1", [{"ref": "analysis/track_map.json", "sha1": sha}]
    )
    assert step_is_reusable(prior, "track_map", cache_key="k2", pack_root=pack) is False


def test_step_is_reusable_false_missing_output(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    prior = _prior_ok(
        "track_map", "k1", [{"ref": "analysis/track_map.json", "sha1": "x"}]
    )
    assert step_is_reusable(prior, "track_map", cache_key="k1", pack_root=pack) is False


def test_cacheable_statuses_constant():
    assert set(CACHEABLE_STATUSES) == {"ok", "partial"}


# ---------------------------------------------------------------------------
# Arrangement snapshot round-trip
# ---------------------------------------------------------------------------


def test_arrangement_snapshot_roundtrip(tmp_path):
    from src.deconstruct_resume import resume_arrangement

    pack = tmp_path / "pack"
    pack.mkdir()
    payload = _real_arrangement_payload(pack)
    snap = snapshot_arrangement(payload)
    assert isinstance(snap, dict)
    assert snap["canonical_audio_path"] == "analysis/working_audio.wav"
    restored = resume_arrangement(snap, pack)
    assert restored["canonical_audio_path"] == pack / "analysis" / "working_audio.wav"
    assert restored["structure_result"] == payload["structure_result"]
    assert restored["arrangement_result"] == payload["arrangement_result"]
    assert restored["beat_grid"] == payload["beat_grid"]
    assert restored["timebase"] == payload["timebase"]


def test_arrangement_snapshot_portable_no_absolute(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    payload = _real_arrangement_payload(pack)
    snap = snapshot_arrangement(payload)
    text = json.dumps(snap)
    assert ":\\\\" not in text
    assert ":\\" not in text


# ---------------------------------------------------------------------------
# Orchestrator resume integration
# ---------------------------------------------------------------------------


def test_orchestrator_reuses_all_steps(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    track = tmp_path / "track.wav"
    _make_wav(track)

    calls1: list[str] = []
    run1 = run_deconstruct(
        track, pack, adapters=_adapters_reuse_all(pack, calls1), resume=True
    )
    assert set(calls1) == {"track_map", "arrangement", "assets", "stems"}
    assert all(s.execution == "computed" for s in run1.steps)

    calls2: list[str] = []
    run2 = run_deconstruct(
        track, pack, adapters=_adapters_reuse_all(pack, calls2), resume=True
    )
    # stems is not_run (not cacheable by design) so it always recomputes;
    # track_map/arrangement/assets must be reused without invoking adapters.
    assert "track_map" not in calls2
    assert "arrangement" not in calls2
    assert "assets" not in calls2
    assert calls2 == ["stems"]
    assert all(
        s.execution == "reused" for s in run2.steps if s.step_id != "stems"
    )
    assert set(run2.reused_steps) == {"track_map", "arrangement", "assets"}
    assert run2.computed_steps == ["stems"]


def test_orchestrator_no_resume_recomputes_all(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    track = tmp_path / "track.wav"
    _make_wav(track)

    run_deconstruct(track, pack, adapters=_adapters_reuse_all(pack, []), resume=True)
    calls2: list[str] = []
    run2 = run_deconstruct(
        track, pack, adapters=_adapters_reuse_all(pack, calls2), resume=False
    )
    assert set(calls2) == {"track_map", "arrangement", "assets", "stems"}
    assert all(s.execution == "computed" for s in run2.steps)


def test_orchestrator_recomputes_on_config_change(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    track = tmp_path / "track.wav"
    _make_wav(track)

    run_deconstruct(
        track,
        pack,
        adapters=_adapters_reuse_all(pack, []),
        resume=True,
        beat_backend="auto",
    )
    calls2: list[str] = []
    run_deconstruct(
        track,
        pack,
        adapters=_adapters_reuse_all(pack, calls2),
        resume=True,
        beat_backend="librosa",
    )
    assert "arrangement" in calls2
    assert "assets" in calls2
    assert "track_map" not in calls2


def test_orchestrator_recomputes_when_output_deleted(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    track = tmp_path / "track.wav"
    _make_wav(track)

    run_deconstruct(track, pack, adapters=_adapters_reuse_all(pack, []), resume=True)
    (pack / "loops" / "loop_a.json").unlink()
    calls2: list[str] = []
    run_deconstruct(track, pack, adapters=_adapters_reuse_all(pack, calls2), resume=True)
    assert "assets" in calls2
    assert "track_map" not in calls2
    assert "arrangement" not in calls2


def test_orchestrator_resume_after_partial_state(tmp_path):
    from src.deconstruct_resume import snapshot_arrangement

    pack = tmp_path / "pack"
    pack.mkdir()
    track = tmp_path / "track.wav"
    _make_wav(track)

    _write_text(pack, "analysis/arrangement_map.json")
    wav = pack / "analysis" / "working_audio.wav"
    wav.parent.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(b"WAVDATA")
    wav_sha = hashlib.sha1(b"WAVDATA").hexdigest()
    snap = snapshot_arrangement(_real_arrangement_payload(pack))

    src_hash = source_content_hash_sha256(track)
    upstream = {
        "track_map": compute_step_cache_key(
            "track_map",
            source_content_hash=src_hash,
            config={"bpm_normalization": "none"},
            upstream_cache_keys={},
        )
    }
    arr_key = compute_step_cache_key(
        "arrangement",
        source_content_hash=src_hash,
        config={"beat_backend": "auto", "bpm_normalization": "none"},
        upstream_cache_keys=upstream,
    )
    prior = {
        "document_type": RESUME_DOC_TYPE,
        "schema_version": RESUME_SCHEMA_VERSION,
        "source": {"content_hash_sha256": src_hash, "pack_root_portable": "."},
        "contract_versions": dict(CONTRACT_VERSIONS),
        "steps": {
            "track_map": {
                "status": "ok",
                "cache_key": upstream["track_map"],
                "output_inventory": [
                    {"ref": "analysis/track_map.json", "sha1": "ignored"}
                ],
            },
            "arrangement": {
                "status": "ok",
                "cache_key": arr_key,
                "output_inventory": [
                    {"ref": "analysis/arrangement_map.json", "sha1": "ignored"},
                    {"ref": "analysis/working_audio.wav", "sha1": wav_sha},
                ],
                "snapshot": snap,
            },
        },
    }
    _write_text(pack, "analysis/track_map.json", "tm")
    prior["steps"]["track_map"]["output_inventory"][0]["sha1"] = hashlib.sha1(
        b"tm"
    ).hexdigest()
    # arrangement_map.json content is "{}" (default _write_text)
    prior["steps"]["arrangement"]["output_inventory"][0]["sha1"] = hashlib.sha1(
        b"{}"
    ).hexdigest()
    save_resume_state(pack, prior)

    calls: list[str] = []
    run = run_deconstruct(
        track, pack, adapters=_adapters_reuse_all(pack, calls), resume=True
    )
    assert "arrangement" not in calls
    assert "track_map" not in calls
    assert "assets" in calls
    assert "stems" in calls
    reused_ids = {s.step_id for s in run.steps if s.execution == "reused"}
    assert reused_ids == {"track_map", "arrangement"}


def test_orchestrator_run_evidence_1_1_0(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    track = tmp_path / "track.wav"
    _make_wav(track)

    run = run_deconstruct(
        track, pack, adapters=_adapters_reuse_all(pack, []), resume=True
    )
    assert isinstance(run, RunResult)
    d = run.to_dict()
    assert d["schema_version"] == "1.1.0"
    assert "reused_steps" in d
    assert "computed_steps" in d
    for s in d["steps"]:
        assert "execution" in s
        assert "cache_key" in s


def test_orchestrator_corrupt_state_triggers_recompute(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    track = tmp_path / "track.wav"
    _make_wav(track)
    (pack / "deconstruct_resume.json").write_text("{corrupt", encoding="utf-8")

    calls: list[str] = []
    run_deconstruct(track, pack, adapters=_adapters_reuse_all(pack, calls), resume=True)
    assert set(calls) == {"track_map", "arrangement", "assets", "stems"}


def test_real_orchestrator_resume_reuses_and_regenerates_assets(tmp_path):
    """End-to-end with REAL production adapters: resume must reuse cacheable
    steps (track_map is always cacheable; arrangement/assets when their run1
    status is ok/partial) and never leak absolute paths."""
    track = write_kick_transient_wav(tmp_path / "track.wav", bpm=120.0, duration_sec=4.0)
    pack = tmp_path / "pack"

    run1 = run_deconstruct(track, pack, beat_backend="librosa", skip={"stems"}, resume=True)
    assert run1.status in ("complete", "partial", "failed")
    # Canonical working WAV is always produced by the arrangement step.
    assert (pack / "analysis" / "working_audio.wav").exists()

    run2 = run_deconstruct(track, pack, beat_backend="librosa", skip={"stems"}, resume=True)
    assert run2.status in ("complete", "partial", "failed")

    run1_status = {s.step_id: s.status for s in run1.steps}
    cacheable_run1 = all(
        run1_status.get(s) in CACHEABLE_STATUSES for s in ("arrangement", "assets")
    )
    reused = {s.step_id for s in run2.steps if s.execution == "reused"}
    # track_map is always cacheable for a real source track.
    assert "track_map" in reused
    if cacheable_run1:
        assert {"arrangement", "assets"}.issubset(reused)

    # No absolute paths leaked into the serialized resume/run state.
    state_text = (pack / "deconstruct_resume.json").read_text(encoding="utf-8")
    assert ":\\" not in state_text and ":/" not in state_text
    run_text = json.dumps(run2.to_dict(), default=str)
    assert ":\\" not in run_text and ":/" not in run_text
