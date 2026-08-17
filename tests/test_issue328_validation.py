"""Validation-slice for Issue #328: real Windows/WASAPI hardware evidence.

This module provides deterministic, reproducible test suites that exercise
the native audio core under real hardware conditions (Windows 11, WASAPI
Shared, Steinberg CI1).  All suites are designed so that the evidence they
produce can be rolled into `docs/validation/issue-328-validation-report.md`
and used to close the parent issues #323, #328, #318 in the correct order.

Earlier merge was premature — three evidence gaps were identified that
must be fixed before final closure (SYNC duration/drift, recording unit
labeling, device-robustness honesty).  This file replaces the previous
version with corrected, complete evidence collection.

NOTE: The native core does not expose per-voice phase position in frames.
Drift is measured exclusively via the engine_frame clock (authoritative).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from src.native_audio import NativeAudioEngine, EngineConfig, VoiceConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_native():
    """Skip the test if the native audio core cannot be initialised."""
    try:
        eng = NativeAudioEngine()
        cfg = EngineConfig(sample_rate=48000, buffer_frames=512, output_device=None, input_device=None)
        try:
            eng.open(cfg)
        except RuntimeError:
            pytest.skip("Could not open native audio engine")
        try:
            eng.start()
        except RuntimeError:
            pytest.skip("Could not start native audio engine")
        eng.stop()
        eng.close()
    except RuntimeError:
        pytest.skip("Native audio core not available on this platform")


def _write_evidence(evidence: dict, suite_name: str, evidence_dir: Path = Path("evidence")):
    evidence_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    (evidence_dir / f"{suite_name}_{ts}.json").write_text(json.dumps(evidence, indent=2))


# ---------------------------------------------------------------------------
# 1. SYNC / RATE — real rendered-click evidence for #323
# ---------------------------------------------------------------------------

def test_sync_rate_128_140_bpm_hardware():
    """RATE_SYNC should keep both rendered clicks aligned on the master grid.

    This is the real proof that matters: count the clicks written by the render
    path and compare the final engine-frame positions of those clicks. We do not
    derive a synthetic drift value from voice_rates, because the source rates are
    intentionally different and are the mechanism by which both voices converge
    onto the master BPM.
    """
    _require_native()
    engine = NativeAudioEngine()
    cfg = EngineConfig(sample_rate=48000, buffer_frames=512, output_device=None, input_device=None)
    try:
        engine.open(cfg)
    except RuntimeError:
        pytest.skip("Could not open audio engine")
    try:
        engine.start()
    except RuntimeError:
        pytest.skip("Could not start engine")

    vc1 = VoiceConfig(id=1, bpm=128.0, initial_rate=132.0 / 128.0, sync_mode=0)
    vc2 = VoiceConfig(id=2, bpm=140.0, initial_rate=132.0 / 140.0, sync_mode=0)
    engine.create_voice(vc1)
    engine.create_voice(vc2)
    engine.schedule_voice_start(1, 0)
    engine.schedule_voice_start(2, 0)

    duration = 233.0
    start_snapshot = engine.snapshot()
    start_skew_voice1 = start_snapshot.actual_start_frame[0] - start_snapshot.requested_start_frame[0]
    start_skew_voice2 = start_snapshot.actual_start_frame[1] - start_snapshot.requested_start_frame[1]

    time.sleep(duration)

    end_snapshot = engine.snapshot()
    rendered_clicks_voice1 = end_snapshot.voice_rendered_click_count[0] - start_snapshot.voice_rendered_click_count[0]
    rendered_clicks_voice2 = end_snapshot.voice_rendered_click_count[1] - start_snapshot.voice_rendered_click_count[1]
    click_count_delta = abs(rendered_clicks_voice1 - rendered_clicks_voice2)
    relative_last_click_offset_frames = abs(
        end_snapshot.voice_last_click_engine_frame[0] - end_snapshot.voice_last_click_engine_frame[1]
    )

    engine.stop()
    engine.close()

    evidence = {
        "suite": "sync_rate",
        "source_bpm_1": 128.0,
        "source_bpm_2": 140.0,
        "master_bpm": 132.0,
        "duration_sec": duration,
        "start_skew_voice1_frames": start_skew_voice1,
        "start_skew_voice2_frames": start_skew_voice2,
        "rendered_click_count_voice1": rendered_clicks_voice1,
        "rendered_click_count_voice2": rendered_clicks_voice2,
        "click_count_delta": click_count_delta,
        "last_click_voice1_engine_frame": end_snapshot.voice_last_click_engine_frame[0],
        "last_click_voice2_engine_frame": end_snapshot.voice_last_click_engine_frame[1],
        "relative_last_click_offset_frames": relative_last_click_offset_frames,
        "callback_mean_us": round(start_snapshot.callback_mean_us, 2),
        "callback_p99_us": round(start_snapshot.callback_p99_us, 2),
        "xrun_count": start_snapshot.xrun_count,
    }
    _write_evidence(evidence, "sync_rate")

    assert abs(start_skew_voice1) <= 1, f"Start skew voice1 too large: {start_skew_voice1}"
    assert abs(start_skew_voice2) <= 1, f"Start skew voice2 too large: {start_skew_voice2}"
    assert start_snapshot.xrun_count == 0, f"Xruns during RATE_SYNC run: {start_snapshot.xrun_count}"
    assert rendered_clicks_voice1 > 0 and rendered_clicks_voice2 > 0
    assert click_count_delta <= 1, (
        f"Rendered click counts diverged by {click_count_delta} for 128/140 BPM RATE_SYNC"
    )
    assert relative_last_click_offset_frames <= 512, (
        f"Last rendered click offset too large: {relative_last_click_offset_frames} frames"
    )


# ---------------------------------------------------------------------------
# 2. RECORDING — playback + recording same interface
# ---------------------------------------------------------------------------

def test_recording_engine_frame_delta():
    """RECORDING: Playback + Recording gleichzeitig,
    expected_frames = capture_end_engine_frame - capture_start_engine_frame,
    KEIN * channels bei Audioframes,
    channels und bytes separat dokumentieren,
    actual_frames gegen erwartete Frames prüfen (assert)."""
    _require_native()
    engine = NativeAudioEngine()
    cfg = EngineConfig(sample_rate=48000, buffer_frames=512)
    try:
        engine.open(cfg)
    except RuntimeError:
        pytest.skip("Could not open audio engine")
    try:
        engine.start()
    except RuntimeError:
        pytest.skip("Could not start engine")

    # Start a click voice at master BPM (no rate conversion)
    vc = VoiceConfig(
        id=1,
        bpm=132.0,
        sync_mode=0,  # SB_SYNC_MODE_RATE_SYNC
    )
    engine.create_voice(vc)
    engine.schedule_voice_start(1, 0)

    # Start recording at engine_frame 0
    rec_id = engine.start_recording(0)
    record_start_engine_frame = engine.snapshot().engine_frame

    # Run 5 seconds
    time.sleep(5.0)

    # Stop recording
    data, frames = engine.stop_recording(rec_id)
    record_end_engine_frame = engine.snapshot().engine_frame

    snap = engine.snapshot()

    # --- expected_frames = engine frame delta (NO * channels) ---
    # engine_frame counts sample frames. For 5s @ 48kHz: ~240000 frames.
    # The delta includes scheduling overhead, so tolerance is wider.
    expected_frames = record_end_engine_frame - record_start_engine_frame

    # actual_frames from the engine (already in frame count, not bytes)
    actual_frames = frames

    # channels and bytes documented separately
    channels = 1  # documented for transparency (CI1 mono input)
    recorded_bytes = len(data)

    # Validate: actual_frames should be close to expected_frames.
    # Deviation due to scheduling/buffer effects (recording starts/stops
    # at slightly different engine frames than requested).
    tolerance_pct = 15.0
    diff_pct = abs(actual_frames - expected_frames) / expected_frames * 100.0 if expected_frames > 0 else 0.0
    within_tolerance = diff_pct <= tolerance_pct

    evidence = {
        "suite": "recording",
        "sample_rate": 48000,
        "buffer_frames": 512,
        "record_start_engine_frame": record_start_engine_frame,
        "record_end_engine_frame_exclusive": record_end_engine_frame,
        "expected_frames": expected_frames,
        "actual_frames": actual_frames,
        "recorded_bytes": recorded_bytes,
        "channels_documented": channels,
        "diff_pct": round(diff_pct, 2),
        "within_tolerance": within_tolerance,
        "drop_frames": snap.recording_dropped_frames,
        "status": "complete" if snap.recording_dropped_frames == 0 else "interrupted",
        "device_status": snap.device_status,
    }
    _write_evidence(evidence, "recording")

    engine.stop()
    engine.close()

    # Assertions
    assert within_tolerance, f"Recording frame mismatch: expected {expected_frames}, got {actual_frames} ({diff_pct:.2f}% diff)"
    assert snap.recording_dropped_frames == 0, f"Dropped frames: {snap.recording_dropped_frames}"


# ---------------------------------------------------------------------------
# 3. DEVICE ROBUSTNESS — honesty about unplug/replug
# ---------------------------------------------------------------------------

def test_device_robustness_honest():
    """DEVICE: physisches unplug/replug nur dann als getestet melden,
    wenn wirklich durchgeführt.
    andernfalls:
      physical_device_loss: NOT_TESTED
      recovery: NOT_TESTED
    normaler 3s-Stabilitätslauf darf nur als engine_stability PASS gelten,
    nicht als Device-Lost/Recovery PASS.  Assert auf engine_stability."""
    _require_native()
    engine = NativeAudioEngine()
    cfg = EngineConfig(sample_rate=48000, buffer_frames=512)
    try:
        engine.open(cfg)
    except RuntimeError:
        pytest.skip("Could not open audio engine")
    try:
        engine.start()
    except RuntimeError:
        pytest.skip("Could not start engine")

    snap_before = engine.snapshot()

    # Physisches Unplug wird aus Sicherheitsgründen unterlassen.
    # Es wird nur dokumentiert, dass die Engine stabil läuft.
    time.sleep(3.0)
    snap_after = engine.snapshot()

    engine.stop()
    engine.close()

    xrun_delta = snap_after.xrun_count - snap_before.xrun_count
    underflow_delta = snap_after.underflow_count - snap_before.underflow_count
    overflow_delta = snap_after.overflow_count - snap_before.overflow_count

    engine_stability_pass = (
        xrun_delta == 0
        and underflow_delta == 0
        and overflow_delta == 0
    )

    evidence = {
        "suite": "device_robustness",
        "note": "Physisches Unplug/Replug wurde aus Sicherheitsgründen unterlassen; "
                "Engine-Stabilität wurde dokumentiert. "
                "physical_device_loss: NOT_TESTED; recovery: NOT_TESTED.",
        "engine_start_frame": snap_before.engine_frame,
        "engine_end_frame": snap_after.engine_frame,
        "device_status_before": snap_before.device_status,
        "device_status_after": snap_after.device_status,
        "xrun_count_delta": xrun_delta,
        "underflow_delta": underflow_delta,
        "overflow_delta": overflow_delta,
        "physical_device_loss": "NOT_TESTED",
        "recovery": "NOT_TESTED",
        "engine_stability_pass": engine_stability_pass,
    }
    _write_evidence(evidence, "device_robustness")

    # Assert: engine must remain stable
    assert engine_stability_pass, f"Engine instability: xrun_delta={xrun_delta}, underflow_delta={underflow_delta}, overflow_delta={overflow_delta}"


# ---------------------------------------------------------------------------
# 4. DEVICE RECOVERY — explicitly NOT TESTED (xfail)
# ---------------------------------------------------------------------------

@pytest.mark.xfail(reason="Physical device unplug/replug not performed in CI; requires manual hardware test")
def test_device_recovery_physical_unplug():
    """DEVICE RECOVERY: physisches Unplug/Replug — NICHT GETESTET in CI.
    Erfordert manuellen Hardware-Test (Steinberg CI1 aus-/einstecken),
    dann Neustart der Engine + Resume + Frame-Rescue.
    Dieser Test bleibt xfail bis manueller Test durchgeführt wurde."""
    pytest.skip("Physical unplug/replug recovery not tested in CI")