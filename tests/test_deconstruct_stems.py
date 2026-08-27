from __future__ import annotations

import sys
import json
import hashlib
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tests.audio_fixtures import write_sine_wav
from tests.test_stem_manifest_contract import validate_stem_manifest

from src.deconstruct import (
    STEP_ORDER,
    STEMS_NOT_REQUESTED,
    WEIGHT_IDENTITY_UNAVAILABLE,
    StepResult,
    _default_stems_adapter,
    run_deconstruct,
)
from src.stem_cache import (
    known_htdemucs_ft_identity,
    known_htdemucs_identity,
    separate_with_cache,
)
from tools.stem_separator_spike import (
    WEIGHT_USAGE_RESEARCH_ONLY,
    map_stem_to_manifest,
)

TRACK_REF = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
STEM_KINDS = ["drums", "bass", "vocals", "other"]
BACKEND_VERSION = "0.44.5"


@pytest.fixture
def track_file(tmp_path):
    return write_sine_wav(tmp_path / "t.wav", duration_sec=1.0, frequency_hz=220)


def _sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_silent_wav(path: Path, seconds: float = 0.2, sr: int = 44100) -> str:
    data = np.zeros((int(seconds * sr), 2), dtype=np.float32)
    sf.write(path, data, sr)
    return _sha256_of_file(path)


def _abs_pattern(text: str) -> bool:
    if "file://" in text:
        return True
    for token in text.split('"'):
        t = token.strip()
        # The portable source-reference scheme (/source/original, /source/working_audio)
        # is allowed; a real absolute path starts with a drive letter.
        if t.startswith("/") and not t.startswith("/source/"):
            return True
        if len(t) >= 3 and t[1] == ":" and t[2] in ("/", "\\"):
            return True
    return False


def _make_fake_executor(capture: dict | None = None):
    """Executor that writes 4 stem WAVs + signed manifests into output_dir/stems."""

    captured = capture if capture is not None else {}

    def executor(
        *,
        input_path,
        track_ref,
        working_audio_hash,
        model_identity,
        configuration,
        output_dir,
    ):
        captured["model_identity"] = model_identity
        captured["working_audio_hash"] = working_audio_hash
        captured["track_ref"] = track_ref
        out = Path(output_dir) / "stems"
        out.mkdir(parents=True, exist_ok=True)
        prov = model_identity.to_provenance()
        stems = []
        for kind in STEM_KINDS:
            wav = out / f"{kind}.wav"
            out_hash = _write_silent_wav(wav)
            stem_id = f"stem_{kind}_{track_ref[:8]}_{working_audio_hash[:8]}"
            manifest = map_stem_to_manifest(
                stem_id=stem_id,
                stem_kind=kind,
                track_ref=track_ref,
                source_hash=working_audio_hash,
                source_properties={
                    "sample_rate_hz": 44100,
                    "channels": 2,
                    "n_samples": 8820,
                    "duration_sec": 0.2,
                },
                file_ref=f"{kind}.wav",
                output_hash=out_hash,
                output_properties={
                    "sample_rate_hz": 44100,
                    "channels": 2,
                    "n_samples": 8820,
                    "duration_sec": 0.2,
                },
                model_identity=prov,
                backend_version=BACKEND_VERSION,
                audio_ref="/source/working_audio",
            )
            manifest_ref = f"{stem_id}.json"
            (out / manifest_ref).write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            stems.append(
                {
                    "stem_kind": kind,
                    "file_path": str(wav),
                    "hash": {"algorithm": "sha256", "value": out_hash},
                    "status": "ok",
                    "manifest_path": str(out / manifest_ref),
                    "file_ref": f"stems/{kind}.wav",
                    "manifest_ref": manifest_ref,
                }
            )
        return {
            "status": "ok",
            "stems": stems,
            "backend": {"name": "python-audio-separator", "version": BACKEND_VERSION},
        }

    return executor


def _fake_adapters(stems_adapter=_default_stems_adapter):
    def track_map(ctx):
        return (
            StepResult(step_id="track_map", required=True, status="ok"),
            {"source": {"original": {"hash": {"value": TRACK_REF}}}},
        )

    def arrangement(ctx):
        return (
            StepResult(step_id="arrangement", required=False, status="ok"),
            {"snapshot": {}},
        )

    def assets(ctx):
        return (
            StepResult(step_id="assets", required=False, status="ok"),
            {"manifest_refs": []},
        )

    return {
        "track_map": track_map,
        "arrangement": arrangement,
        "assets": assets,
        "stems": stems_adapter,
    }


def test_stems_default_core_path_is_not_run_and_isolated(track_file, tmp_path):
    # No heavy deps may be loaded by the core modules.
    for mod in [m for m in sys.modules if "audio_separator" in m or "torch" in m]:
        sys.modules.pop(mod, None)
    import src.deconstruct  # noqa: F401
    import src.cli  # noqa: F401

    loaded = [m for m in sys.modules if "audio_separator" in m or "torch" in m]
    assert not loaded, f"Heavy deps loaded by core: {loaded}"

    # Default run (no --stems) must leave stems as a no-op.
    run = run_deconstruct(
        track_file,
        tmp_path / "pack",
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems = {s.step_id: s for s in run.steps}["stems"]
    assert stems.status == "not_run"
    assert stems.reason_code == STEMS_NOT_REQUESTED
    assert run.status == "complete"
    # Nothing written under pack_root/stems.
    assert not (tmp_path / "pack" / "stems").exists()


def test_stems_opt_in_success_writes_manifests_and_truthful_provenance(
    track_file, tmp_path
):
    capture: dict = {}
    run = run_deconstruct(
        track_file,
        tmp_path / "pack",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=_make_fake_executor(capture),
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems = {s.step_id: s for s in run.steps}["stems"]
    assert stems.status == "ok"
    assert len(stems.output_refs) == 4

    # Provenance: explicit truthful model + research-only license boundary.
    prov = stems.provenance
    assert prov["component"] == "stem_separator"
    assert prov["experimental"] is True
    assert prov["production_default"] == "NO_GO"
    assert prov["model"]["family"] == "htdemucs"
    assert prov["model"]["checkpoint"] == "955717e8"
    assert prov["model"]["weight_license"] == WEIGHT_USAGE_RESEARCH_ONLY
    assert prov["track_ref"] == TRACK_REF

    # On-disk manifests validate and contain no absolute paths.
    stem_dir = tmp_path / "pack" / "stems"
    for ref in stems.output_refs:
        manifest_path = tmp_path / "pack" / ref
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        errors = validate_stem_manifest(manifest)
        assert errors == [], f"{ref} invalid: {errors}"
        assert not _abs_pattern(json.dumps(manifest)), f"{ref} leaks absolute path"
    for kind in STEM_KINDS:
        assert (stem_dir / f"{kind}.wav").exists()


def test_stems_failure_isolation_backend_unavailable(track_file, tmp_path):
    def executor(**kwargs):
        return {
            "status": "not_run",
            "reason_code": "BACKEND_UNAVAILABLE",
            "stems": [],
            "backend": {"name": "python-audio-separator", "version": BACKEND_VERSION},
        }

    run = run_deconstruct(
        track_file,
        tmp_path / "pack",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=executor,
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems = {s.step_id: s for s in run.steps}["stems"]
    assert stems.status == "not_run"
    assert stems.reason_code == "BACKEND_UNAVAILABLE"
    # Optional-step failure must NOT abort the overall deconstruction.
    assert run.status == "complete"


def test_stems_failure_isolation_failed_yields_partial_not_aborted(
    track_file, tmp_path
):
    def executor(**kwargs):
        return {
            "status": "failed",
            "error": {"code": "SUBPROCESS_ERROR", "message": "boom"},
            "stems": [],
            "backend": {"name": "python-audio-separator", "version": BACKEND_VERSION},
        }

    run = run_deconstruct(
        track_file,
        tmp_path / "pack",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=executor,
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems = {s.step_id: s for s in run.steps}["stems"]
    assert stems.status == "failed"
    assert stems.error["code"] == "SUBPROCESS_ERROR"
    assert run.status == "partial"  # optional failure => partial, never aborted


def test_stems_unknown_runtime_status_has_stable_error_code(track_file, tmp_path):
    def executor(**kwargs):
        return {
            "status": "unexpected_runtime_status",
            "stems": [],
            "backend": {"name": "python-audio-separator", "version": BACKEND_VERSION},
        }

    run = run_deconstruct(
        track_file,
        tmp_path / "pack",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=executor,
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems = {s.step_id: s for s in run.steps}["stems"]
    assert stems.status == "failed"
    assert stems.error["code"] == "STEM_RUNTIME_UNKNOWN_STATUS"
    assert run.status == "partial"


def test_stems_partial_status_propagates(track_file, tmp_path):
    def executor(**kwargs):
        stems = []
        for i, kind in enumerate(STEM_KINDS):
            ok = i < 3
            stems.append(
                {
                    "stem_kind": kind,
                    "file_path": f"/tmp/{kind}.wav",
                    "hash": {"algorithm": "sha256", "value": "a" * 64},
                    "status": "ok" if ok else "failed",
                    "manifest_path": f"/tmp/{kind}.json",
                    "file_ref": f"stems/{kind}.wav",
                    "manifest_ref": f"stem_{kind}.json",
                }
            )
        return {
            "status": "partial",
            "stems": stems,
            "backend": {"name": "python-audio-separator", "version": BACKEND_VERSION},
        }

    run = run_deconstruct(
        track_file,
        tmp_path / "pack",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=executor,
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems = {s.step_id: s for s in run.steps}["stems"]
    assert stems.status == "partial"
    assert run.status == "partial"


def test_stems_weight_algo_mismatch_for_ft_is_rejected(track_file, tmp_path):
    calls: list = []
    run = run_deconstruct(
        track_file,
        tmp_path / "pack",
        stems_enabled=True,
        stem_model="htdemucs_ft.yaml",
        # ft requires sha256-set-v1, not the supplied sha256 default.
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=lambda **k: calls.append(k) or {
            "status": "ok",
            "stems": [],
            "backend": {"name": "x", "version": "0"},
        },
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems = {s.step_id: s for s in run.steps}["stems"]
    assert stems.status == "not_run"
    assert stems.reason_code == WEIGHT_IDENTITY_UNAVAILABLE
    assert calls == []  # executor must not run with a rejected weight identity


def test_stems_separation_input_is_canonical_working_audio(track_file, tmp_path):
    capture: dict = {}
    run_deconstruct(
        track_file,
        tmp_path / "pack",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=_make_fake_executor(capture),
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    working = tmp_path / "pack" / "analysis" / "working_audio.wav"
    assert working.exists()
    # The exact bytes handed to the separator are the canonical working audio.
    assert capture["working_audio_hash"] == _sha256_of_file(working)


# ---------------------------------------------------------------------------
# #248 global cache layers (A: miss, B: hit, C simulated via disabled)
# ---------------------------------------------------------------------------


def _cache_executor_identity():
    return known_htdemucs_identity(weight_hash={"algorithm": "sha256", "value": "a" * 64})


def test_stem_cache_miss_then_hit_copies_outputs(tmp_path):
    calls: list = []

    def executor(*, input_path, track_ref, working_audio_hash, model_identity, configuration, output_dir):
        calls.append(track_ref)
        out = Path(output_dir) / "stems"
        out.mkdir(parents=True, exist_ok=True)
        wav = out / "drums.wav"
        out_hash = _write_silent_wav(wav)
        manifest = map_stem_to_manifest(
            stem_id="stem_drums_x",
            stem_kind="drums",
            track_ref=track_ref,
            source_hash=working_audio_hash,
            source_properties={"sample_rate_hz": 44100, "channels": 2, "n_samples": 8820},
            file_ref="drums.wav",
            output_hash=out_hash,
            output_properties={"sample_rate_hz": 44100, "channels": 2, "n_samples": 8820},
            model_identity=model_identity.to_provenance(),
            backend_version=BACKEND_VERSION,
            audio_ref="/source/working_audio",
        )
        (out / "stem_drums_x.json").write_text(json.dumps(manifest), encoding="utf-8")
        return {
            "status": "ok",
            "stems": [
                {
                    "stem_kind": "drums",
                    "file_path": str(wav),
                    "hash": {"algorithm": "sha256", "value": out_hash},
                    "status": "ok",
                    "manifest_path": str(out / "stem_drums_x.json"),
                    "file_ref": "stems/drums.wav",
                    "manifest_ref": "stem_drums_x.json",
                }
            ],
            "backend": {"name": "python-audio-separator", "version": BACKEND_VERSION},
        }

    cache = tmp_path / "cache"
    common = dict(
        input_path=tmp_path / "track.wav",
        track_ref=TRACK_REF,
        working_audio_hash="b" * 64,
        model_identity=_cache_executor_identity(),
        configuration={},
        backend_name="python-audio-separator",
        backend_version=BACKEND_VERSION,
        executor=executor,
        cache_dir=cache,
        cache_enabled=True,
    )
    r1 = separate_with_cache(output_dir=tmp_path / "pack1", **common)
    assert r1["cache_status"] == "miss"

    r2 = separate_with_cache(output_dir=tmp_path / "pack2", **common)
    assert r2["cache_status"] == "hit"
    assert len(calls) == 1  # executor ran only once
    # HIT copied outputs into the new output dir without re-running separation.
    assert (tmp_path / "pack2" / "stems" / "drums.wav").exists()
    assert (tmp_path / "pack2" / "stems" / "stem_drums_x.json").exists()


def test_stem_cache_disabled_invokes_executor_each_time(tmp_path):
    calls: list = []

    def executor(*, input_path, track_ref, working_audio_hash, model_identity, configuration, output_dir):
        calls.append(1)
        out = Path(output_dir) / "stems"
        out.mkdir(parents=True, exist_ok=True)
        wav = out / "drums.wav"
        out_hash = _write_silent_wav(wav)
        return {
            "status": "ok",
            "stems": [
                {
                    "stem_kind": "drums",
                    "file_path": str(wav),
                    "hash": {"algorithm": "sha256", "value": out_hash},
                    "status": "ok",
                    "manifest_path": str(out / "m.json"),
                    "file_ref": "stems/drums.wav",
                    "manifest_ref": "m.json",
                }
            ],
            "backend": {"name": "python-audio-separator", "version": BACKEND_VERSION},
        }

    common = dict(
        input_path=tmp_path / "track.wav",
        track_ref=TRACK_REF,
        working_audio_hash="b" * 64,
        model_identity=_cache_executor_identity(),
        configuration={},
        backend_name="python-audio-separator",
        backend_version=BACKEND_VERSION,
        executor=executor,
        cache_dir=tmp_path / "cache",
        cache_enabled=False,
    )
    separate_with_cache(output_dir=tmp_path / "p1", **common)
    separate_with_cache(output_dir=tmp_path / "p2", **common)
    assert len(calls) == 2


def test_stem_cache_fingerprint_changes_with_weight_identity(tmp_path):
    from src.stem_cache import build_separation_fingerprint

    base = _cache_executor_identity()
    fp_a = build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version=BACKEND_VERSION,
        model_identity=base,
        configuration={},
    )
    fp_b = build_separation_fingerprint(
        backend_name="python-audio-separator",
        backend_version=BACKEND_VERSION,
        model_identity=known_htdemucs_identity(
            weight_hash={"algorithm": "sha256", "value": "f" * 64}
        ),
        configuration={},
    )
    assert fp_a != fp_b  # different weight identity => different separation identity


# ---------------------------------------------------------------------------
# #262 pack-local resume: missing stem WAV forces recompute (layer C)
# ---------------------------------------------------------------------------


def test_stem_resume_recomputes_when_manifest_missing(track_file, tmp_path):
    pack = tmp_path / "pack"
    first = run_deconstruct(
        track_file,
        pack,
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=_make_fake_executor(),
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    assert {s.step_id: s for s in first.steps}["stems"].execution == "computed"

    # Delete one stem manifest to simulate a broken pack -> resume must recompute.
    stem_manifests = list((pack / "stems").glob("*.json"))
    assert stem_manifests
    stem_manifests[0].unlink()

    second_capture: dict = {}
    second = run_deconstruct(
        track_file,
        pack,
        resume=True,
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=_make_fake_executor(second_capture),
        stem_cache_enabled=False,
        adapters=_fake_adapters(),
    )
    stems2 = {s.step_id: s for s in second.steps}["stems"]
    assert stems2.execution == "computed"
    assert stems2.status == "ok"
    assert second_capture.get("track_ref") == TRACK_REF
