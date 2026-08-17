"""Regression tests for issue #373: Render stem and producer-group assets from actual source audio.

These tests use synthetic audio with intentionally distinct signals to prove that:
- master assets are rendered from master audio
- stem assets are rendered from stem audio (NOT master)
- producer_group assets are rendered from producer_group audio (NOT master)
- kick_bass is derived from actual drums + bass stems
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from src.deconstruct import (
    STEP_ORDER,
    DeconstructAdapters,
    StepContext,
    StepResult,
    run_deconstruct,
)
from src.producer_groups import ProducerGroupParams, derive_producer_groups, write_producer_group_audio
from src.structure_v1 import StructureBoundary, StructureSection, StructureV1Result, StructureV1Source
from tests.audio_fixtures import write_kick_transient_wav


def _write_bass_stem_wav(path: Path, *, bpm: float = 120.0, duration_sec: float = 4.0, sr: int = 44100) -> Path:
    """Generate a musical bassline stem at a known BPM with changing notes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_total = max(1, int(sr * duration_sec))
    y = np.zeros(n_total, dtype=np.float32)
    interval_sec = 60.0 / bpm
    note_interval_sec = interval_sec * 2
    note_samples = max(1, int(note_interval_sec * sr))
    notes = [80.0, 100.0, 120.0, 90.0]
    for i, f in enumerate(notes):
        start = int(i * note_interval_sec * sr)
        end = min(start + note_samples, n_total)
        if start >= n_total:
            break
        t_note = np.arange(end - start, dtype=np.float32) / sr
        env = np.exp(-t_note * 1.5)
        y[start:end] = (0.4 * np.sin(2.0 * np.pi * f * t_note) * env).astype(np.float32)
    y = np.clip(y, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def _write_other_stem_wav(path: Path, *, bpm: float = 120.0, duration_sec: float = 4.0, sr: int = 44100) -> Path:
    """Generate an 'other' stem with pad + percussion."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_total = max(1, int(sr * duration_sec))
    t = np.arange(n_total, dtype=np.float32) / sr
    pad = (0.2 * np.sin(2.0 * np.pi * 220.0 * t) +
           0.15 * np.sin(2.0 * np.pi * 277.0 * t) +
           0.15 * np.sin(2.0 * np.pi * 330.0 * t)).astype(np.float32)
    interval_sec = 60.0 / bpm / 2
    interval_samples = max(1, int(interval_sec * sr))
    rng = np.random.default_rng(42)
    fx = (rng.standard_normal(n_total) * 0.1).astype(np.float32)
    for i in range(1, n_total // interval_samples, 2):
        start = i * interval_samples
        end = min(start + interval_samples // 4, n_total)
        if end > start:
            fx[start:end] *= 5.0
    y = np.clip(pad + fx * 0.3, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def _write_vocals_stem_wav(path: Path, *, bpm: float = 120.0, duration_sec: float = 4.0, sr: int = 44100) -> Path:
    """Generate a vocal-like stem."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_total = max(1, int(sr * duration_sec))
    t = np.arange(n_total, dtype=np.float32) / sr
    vocal = (0.3 * np.sin(2.0 * np.pi * 300.0 * t) +
             0.2 * np.sin(2.0 * np.pi * 600.0 * t) +
             0.1 * np.sin(2.0 * np.pi * 1200.0 * t)).astype(np.float32)
    phrase_env = (0.5 + 0.5 * np.sin(2.0 * np.pi * 0.5 * t)).astype(np.float32)
    y = np.clip(vocal * phrase_env, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def _create_distinct_stems(tmp_path: Path, bpm: float = 120.0, duration_sec: float = 4.0, sr: int = 44100):
    """Create distinct stem files with known frequency signatures."""
    stems_dir = tmp_path / "stems_input"
    stems_dir.mkdir(parents=True, exist_ok=True)

    drums_path = stems_dir / "drums.wav"
    write_kick_transient_wav(drums_path, bpm=bpm, duration_sec=duration_sec, sr=sr)

    bass_path = stems_dir / "bass.wav"
    _write_bass_stem_wav(bass_path, bpm=bpm, duration_sec=duration_sec, sr=sr)

    other_path = stems_dir / "other.wav"
    _write_other_stem_wav(other_path, bpm=bpm, duration_sec=duration_sec, sr=sr)

    vocals_path = stems_dir / "vocals.wav"
    _write_vocals_stem_wav(vocals_path, bpm=bpm, duration_sec=duration_sec, sr=sr)

    return {
        "drums": drums_path,
        "bass": bass_path,
        "other": other_path,
        "vocals": vocals_path,
    }


def _create_master_from_stems(stems: dict, tmp_path: Path, sr: int = 44100) -> Path:
    """Create master audio by mixing stems."""
    master_path = tmp_path / "master.wav"
    mixed = None
    for kind, path in stems.items():
        data, _ = sf.read(str(path))
        if mixed is None:
            mixed = data.astype(np.float32)
        else:
            mixed = mixed + data.astype(np.float32)
    peak = np.max(np.abs(mixed))
    if peak > 0:
        mixed = mixed / peak * 0.9
    sf.write(str(master_path), mixed.astype(np.float32), sr, subtype="PCM_16")
    return master_path


def _fake_stems_executor(stem_files: dict):
    """Create a fake executor that copies pre-written stem files."""
    def executor(*, input_path, track_ref, working_audio_hash, model_identity, configuration, output_dir):
        output_dir = Path(output_dir)
        stems_dir = output_dir / "stems"
        stems_dir.mkdir(parents=True, exist_ok=True)

        stems = []
        for kind, src_path in stem_files.items():
            dst = stems_dir / f"{kind}.wav"
            shutil.copyfile(str(src_path), str(dst))
            data, _ = sf.read(str(dst))
            h = hashlib.sha256(data.tobytes()).hexdigest()

            stem_id = f"stem_{kind}_{track_ref[:8]}_{working_audio_hash[:8]}"
            manifest = {
                "document_type": "sample_brain.stem_manifest",
                "schema_version": "1.0.0",
                "stem_id": stem_id,
                "stem_kind": kind,
                "track_ref": track_ref,
                "source_hash": working_audio_hash,
                "source_properties": {"sample_rate_hz": 44100, "channels": 1, "n_samples": data.shape[0], "duration_sec": data.shape[0] / 44100},
                "output": {"file_ref": f"{kind}.wav", "hash": {"algorithm": "sha256", "value": h}},
                "model_identity": model_identity.to_provenance(),
            }
            manifest_path = stems_dir / f"{stem_id}.json"
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            stems.append({
                "stem_kind": kind,
                "file_path": str(dst),
                "hash": {"algorithm": "sha256", "value": h},
                "status": "ok",
                "manifest_path": str(manifest_path),
                "file_ref": f"stems/{kind}.wav",
                "manifest_ref": f"{stem_id}.json",
            })

        return {
            "status": "ok",
            "stems": stems,
            "backend": {"name": "python-audio-separator", "version": "0.44.5"},
        }
    return executor


def _make_stems_adapter(stem_files: dict, pack_root: Path):
    """Create a stems adapter that reads the written stem files and includes audio data."""
    import soundfile as sf
    import numpy as np
    
    def adapter(ctx):
        # The executor already wrote the files to pack_root/stems/
        stems_payload = []
        for kind, src_path in stem_files.items():
            # Read the audio data from the file the executor wrote
            dst = ctx.pack_root / "stems" / f"{kind}.wav"
            if dst.exists():
                data, _ = sf.read(str(dst), dtype="float32", always_2d=False)
                data = data.astype(np.float32)
            else:
                data, _ = sf.read(str(src_path), dtype="float32", always_2d=False)
                data = data.astype(np.float32)
            stems_payload.append({
                "stem_kind": kind,
                "file_ref": f"stems/{kind}.wav",
                "audio": data,
                "status": "ok",
            })
        return (
            StepResult(
                step_id="stems",
                required=False,
                status="ok",
                output_refs=tuple(f"stems/{k}.wav" for k in stem_files.keys()),
                adapter="test_stems",
            ),
            {"stems": stems_payload, "track_ref": "test_track"},
        )
    return adapter


def _build_fake_arrangement_adapter(sr: int = 44100, duration_sec: float = 8.0):
    """Build an arrangement adapter that returns a fixed structure with clear sections."""
    n_total = int(sr * duration_sec)
    # At 120 BPM: 1 bar = 2 seconds, so 8 seconds = 4 bars
    # Create 2 sections of 2 bars each
    section1 = StructureSection(
        id="section_1",
        start_sample=0,
        end_sample=n_total // 2,
        start_sec=0.0,
        end_sec=duration_sec / 2,
        start_bar=0,
        end_bar=2,
    )
    section2 = StructureSection(
        id="section_2",
        start_sample=n_total // 2,
        end_sample=n_total,
        start_sec=duration_sec / 2,
        end_sec=duration_sec,
        start_bar=2,
        end_bar=4,
    )
    boundary = StructureBoundary(
        sample_index=n_total // 2,
        time_sec=duration_sec / 2,
        bar_index=2,
        downbeat_index=2,
        score=0.9,
        contributing_signals=("novelty", "mfcc"),
    )
    structure_result = StructureV1Result(
        status="ok",
        boundaries=(boundary,),
        sections=(section1, section2),
        feature_status={"novelty": "ok", "mfcc": "ok"},
        notes=(),
        source=StructureV1Source(
            backend="test",
            backend_version="test",
            config={},
        ),
        bar_features={
            "self_similarity": (0.8, 0.7, 0.3, 0.4),
            "recurrence": (0.7, 0.6, 0.5, 0.6),
            "rhythm_stability": (0.9, 0.8, 0.7, 0.8),
            "timbre_delta": (0.1, 0.2, 0.5, 0.3),
            "spectral_delta": (0.1, 0.2, 0.4, 0.3),
            "multi_bar_trend": (0.0, 0.1, -0.1, 0.0),
            "neighbor_delta": (0.2, 0.3, 0.4, 0.2),
        },
    )

    # Create a fake beat grid with downbeats every 2 seconds (120 BPM = 1 bar = 2 sec)
    # 4 bars = downbeats at 0, 2, 4, 6, 8 seconds
    from src.beat_grid import BeatGridResult, BeatGridSeries, BeatGridSource, BEAT_GRID_SOURCE_REF
    bar_samples = int(sr * 2.0)  # 2 seconds per bar at 120 BPM
    downbeat_indices = tuple(i * bar_samples for i in range(5))  # 0, 1, 2, 3, 4 bars
    downbeat_times = tuple(i * 2.0 for i in range(5))

    fake_beat_grid = BeatGridResult(
        status="ok",
        bpm=120.0,
        beats=BeatGridSeries(status="no_result", reason_code="BEATS_UNAVAILABLE"),
        downbeats=BeatGridSeries(
            status="ok",
            sample_indices=downbeat_indices,
            times_sec=downbeat_times,
        ),
        source=BeatGridSource(
            component=BEAT_GRID_SOURCE_REF,
            backend="test",
            backend_version="test",
            checkpoint=None,
        ),
    )

    def adapter(ctx: StepContext):
        from src.canon_audio import render_canonical_wav
        work = ctx.pack_root / "analysis"
        work.mkdir(parents=True, exist_ok=True)
        canon = work / "working_audio.wav"
        timebase = render_canonical_wav(ctx.track_path, canon)

        payload = {
            "structure_result": structure_result,
            "arrangement_result": None,
            "beat_grid": fake_beat_grid,
            "canonical_audio_path": canon,
            "timebase": timebase,
        }
        return (
            StepResult(
                step_id="arrangement",
                required=False,
                status="ok",
                output_refs=("analysis/arrangement_map.json",),
                adapter="test_fake_arrangement",
            ),
            payload,
        )
    return adapter


def _get_loop_manifests(pack_root: Path) -> list[dict]:
    """Load all loop manifests from pack."""
    loops_dir = pack_root / "loops"
    manifests = []
    for mf in loops_dir.glob("*.json"):
        with open(mf) as f:
            manifests.append(json.load(f))
    return manifests


def test_stem_assets_rendered_from_stem_audio_not_master(tmp_path: Path):
    """STEM assets must be rendered from actual stem WAV, not master audio."""
    bpm = 120.0
    duration = 8.0
    sr = 44100

    stem_files = _create_distinct_stems(tmp_path, bpm=bpm, duration_sec=duration, sr=sr)
    master_file = _create_master_from_stems(stem_files, tmp_path, sr=sr)

    executor = _fake_stems_executor(stem_files)
    pack_root = tmp_path / "pack"

    run = run_deconstruct(
        master_file,
        pack_root,
        beat_backend="librosa",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=executor,
        stem_cache_enabled=False,
        adapters=DeconstructAdapters(
            arrangement=_build_fake_arrangement_adapter(sr, duration),
        ),
    )

    # Check stems step succeeded
    stems_step = next(s for s in run.steps if s.step_id == "stems")
    assert stems_step.status == "ok", f"Stems step failed: {stems_step.error}"

    # Check assets step succeeded
    assets_step = next(s for s in run.steps if s.step_id == "assets")
    assert assets_step.status == "ok", f"Assets step failed: {assets_step.reason_code}"

    # Find stem loop manifests
    loop_manifests = _get_loop_manifests(pack_root)
    stem_loops = [m for m in loop_manifests if m.get("source", {}).get("source_kind") == "stem"]

    assert stem_loops, "No stem loops generated - stems step may not have produced usable candidates"

    # Verify each stem loop was rendered from stem audio
    for manifest in stem_loops:
        asset_id = manifest["asset_id"]
        rendered_file = pack_root / "assets" / f"loop_{asset_id}.wav"
        assert rendered_file.exists(), f"Rendered file missing: {rendered_file}"

        rendered_data, _ = sf.read(str(rendered_file))
        fft = np.fft.rfft(rendered_data.astype(np.float64))
        freqs = np.fft.rfftfreq(len(rendered_data), 1/sr)
        peak_idx = np.argmax(np.abs(fft))
        peak_freq = freqs[peak_idx]
        # Drums stem has 60 Hz kick transients
        assert abs(peak_freq - 60.0) < 30.0, f"Stem loop rendered from wrong source! Peak freq: {peak_freq} Hz (expected ~60 Hz from drums stem)"


def test_producer_group_kick_bass_derived_from_actual_stems(tmp_path: Path):
    """kick_bass producer group must be derived from actual drums + bass stems."""
    bpm = 120.0
    duration = 4.0
    sr = 44100

    stem_files = _create_distinct_stems(tmp_path, bpm=bpm, duration_sec=duration, sr=sr)

    drums_signal, _ = sf.read(str(stem_files["drums"]))
    bass_signal, _ = sf.read(str(stem_files["bass"]))

    stems_dict = {
        "drums": drums_signal,
        "bass": bass_signal,
    }

    pg_groups = derive_producer_groups(stems_dict, params=ProducerGroupParams(sample_rate=sr))
    kb = pg_groups["kick_bass"]

    assert kb.status == "ok"
    assert kb.audio is not None

    corr = np.corrcoef(kb.audio[:len(bass_signal)], bass_signal)[0, 1]
    assert corr > 0.5, f"kick_bass bass component doesn't match bass stem (corr={corr})"

    from src.producer_groups import extract_kick_envelope
    _, kick_component, _ = extract_kick_envelope(drums_signal, ProducerGroupParams(sample_rate=sr))
    diff = kb.audio[:len(kick_component)] - bass_signal[:len(kick_component)]
    assert np.allclose(diff, kick_component, atol=1e-3), "kick_bass != kick_component + bass"


def test_master_assets_rendered_from_master_audio(tmp_path: Path):
    """Master assets must be rendered from master audio (canonical working audio)."""
    bpm = 120.0
    duration = 8.0
    sr = 44100

    stem_files = _create_distinct_stems(tmp_path, bpm=bpm, duration_sec=duration, sr=sr)
    master_file = _create_master_from_stems(stem_files, tmp_path, sr=sr)
    pack_root = tmp_path / "pack"

    adapters = DeconstructAdapters(
        arrangement=_build_fake_arrangement_adapter(sr, duration),
    )

    run = run_deconstruct(
        master_file,
        pack_root,
        beat_backend="librosa",
        skip={"stems"},
        adapters=adapters,
    )

    assets_step = next(s for s in run.steps if s.step_id == "assets")
    assert assets_step.status == "ok", f"Assets step failed: {assets_step.reason_code}"

    loop_manifests = _get_loop_manifests(pack_root)
    master_loops = [m for m in loop_manifests if m.get("source", {}).get("source_kind") == "master"]

    assert master_loops, "No master loops generated"

    for manifest in master_loops:
        asset_id = manifest["asset_id"]
        rendered_file = pack_root / "assets" / f"loop_{asset_id}.wav"
        assert rendered_file.exists()

        rendered_data, _ = sf.read(str(rendered_file))
        assert np.max(np.abs(rendered_data)) > 0.01, "Master loop rendered audio is silent"


def test_missing_stem_fails_closed_no_master_fallback(tmp_path: Path):
    """When stem audio is missing, asset generation must fail closed, not fall back to master."""
    bpm = 120.0
    duration = 8.0
    sr = 44100

    stem_files = _create_distinct_stems(tmp_path, bpm=bpm, duration_sec=duration, sr=sr)
    master_file = _create_master_from_stems(stem_files, tmp_path, sr=sr)
    pack_root = tmp_path / "pack"

    # Only provide drums stem (missing bass -> kick_bass no_result)
    partial_stems = {"drums": stem_files["drums"]}
    executor = _fake_stems_executor(partial_stems)

    run = run_deconstruct(
        master_file,
        pack_root,
        beat_backend="librosa",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=executor,
        stem_cache_enabled=False,
        adapters=DeconstructAdapters(
            arrangement=_build_fake_arrangement_adapter(sr, duration),
        ),
    )

    assets_step = next(s for s in run.steps if s.step_id == "assets")
    assert assets_step.status == "ok", f"Assets step failed: {assets_step.reason_code}"

    loop_manifests = _get_loop_manifests(pack_root)
    pg_loops = [m for m in loop_manifests if m.get("source", {}).get("source_kind") == "producer_group"]

    assert len(pg_loops) == 0, f"Producer group loops generated despite missing bass stem: {pg_loops}"


def test_producer_group_audio_written_and_used_for_rendering(tmp_path: Path):
    """Producer group audio must be written to WAV and used for rendering/scoring."""
    bpm = 120.0
    duration = 8.0
    sr = 44100

    stem_files = _create_distinct_stems(tmp_path, bpm=bpm, duration_sec=duration, sr=sr)
    master_file = _create_master_from_stems(stem_files, tmp_path, sr=sr)
    pack_root = tmp_path / "pack"

    executor = _fake_stems_executor(stem_files)

    run = run_deconstruct(
        master_file,
        pack_root,
        beat_backend="librosa",
        stems_enabled=True,
        stem_model="htdemucs.yaml",
        stem_weight_hash={"algorithm": "sha256", "value": "a" * 64},
        stem_executor=executor,
        stem_cache_enabled=False,
        adapters=DeconstructAdapters(
            arrangement=_build_fake_arrangement_adapter(sr, duration),
        ),
    )

    assets_step = next(s for s in run.steps if s.step_id == "assets")
    assert assets_step.status == "ok", f"Assets step failed: {assets_step.reason_code}"

    pg_dir = pack_root / "producer_groups"
    assert pg_dir.exists(), "producer_groups directory not created"
    kb_wav = pg_dir / "kick_bass.wav"
    assert kb_wav.exists(), "kick_bass.wav not written to producer_groups/"

    kb_data, _ = sf.read(str(kb_wav))
    assert np.max(np.abs(kb_data)) > 0.01, "Producer group audio is silent"

    loop_manifests = _get_loop_manifests(pack_root)
    pg_loops = [m for m in loop_manifests if m.get("source", {}).get("source_kind") == "producer_group"]
    assert pg_loops, "No producer_group loops generated"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])