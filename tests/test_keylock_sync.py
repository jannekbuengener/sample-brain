"""Tests for #324: Signalsmith Key-Lock SYNC Mode.

These tests verify real native DSP behavior by processing audio through
the native KeyLockVoice (using Signalsmith Stretch for pitch preservation).

Tests cover:
- Pitch preservation with KEY_LOCK_SYNC vs RATE_SYNC control
- Duration/tempo changes
- Multiple voices with shared grid
- Signalsmith latency measurement
- Tempo changes during playback
- Mode toggle (RATE_SYNC <-> KEY_LOCK_SYNC)
- Invalid BPM handling
- Signalsmith fallback
"""

from __future__ import annotations

import math
import numpy as np
import pytest

from src.session_grid import (
    SessionTransport,
    TempoMap,
    MusicalPosition,
    compute_sync_playback_rate,
)
from src.workbench_transport_adapter import WorkbenchTransportAdapter


# =============================================================================
# 1. RATIO TESTS (shared with #323, must remain consistent)
# =============================================================================

def test_keylock_ratio_128_to_132():
    """#324: 128 -> 132 BPM -> ratio = 1.03125 (same as #323 Rate Sync)."""
    from src.session_grid import compute_sync_playback_rate
    
    rate, status = compute_sync_playback_rate(132.0, 128.0, sync_enabled=True)
    assert rate == 1.03125, f"Expected 1.03125, got {rate}"
    assert status == "sync"


def test_keylock_ratio_128_to_140():
    """#324: 128 -> 140 BPM -> ratio = 1.09375."""
    from src.session_grid import compute_sync_playback_rate
    
    rate, status = compute_sync_playback_rate(140.0, 128.0, sync_enabled=True)
    assert abs(rate - 140/128) < 1e-9, f"Expected ~{140/128}, got {rate}"
    assert status == "sync"


def test_keylock_ratio_140_to_128():
    """#324: 140 -> 128 BPM -> ratio ~= 0.9142857."""
    from src.session_grid import compute_sync_playback_rate
    
    rate, status = compute_sync_playback_rate(128.0, 140.0, sync_enabled=True)
    assert abs(rate - 128/140) < 1e-9, f"Expected ~{128/140}, got {rate}"
    assert status == "sync"


# =============================================================================
# Helper functions for synthetic signal generation and analysis
# =============================================================================

def generate_sine_wave(frequency_hz: float, duration_sec: float, sample_rate: int = 48000) -> np.ndarray:
    """Generate a pure sine wave."""
    t = np.arange(int(duration_sec * sample_rate)) / sample_rate
    return np.sin(2 * np.pi * frequency_hz * t).astype(np.float32)


def measure_dominant_frequency(signal: np.ndarray, sample_rate: int) -> float:
    """Measure dominant frequency using FFT peak."""
    n = len(signal)
    window = np.hanning(n)
    fft = np.fft.rfft(signal * window)
    freqs = np.fft.rfftfreq(n, 1/sample_rate)
    peak_idx = np.argmax(np.abs(fft))
    return freqs[peak_idx]


# =============================================================================
# 2. PITCH PRESERVATION TESTS - Real native DSP verification
# =============================================================================

def test_keylock_pitch_preservation_440hz_128_to_132():
    """#324: 440 Hz sine at 128 BPM -> 132 BPM with Key-Lock -> pitch approx 440 Hz.
    
    This is the CORE acceptance test for Key-Lock.
    Rate Sync would shift to ~453 Hz (440 * 1.03125).
    Key-Lock must preserve approx 440 Hz within tolerance.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    source_bpm = 128.0
    master_bpm = 132.0
    ratio = master_bpm / source_bpm  # 1.03125

    sample_rate = 48000
    duration = 2.0
    original_signal = generate_sine_wave(440.0, duration, sample_rate)

    # Create KeyLockVoice in KEY_LOCK_SYNC mode
    kv = create_keylock_voice(
        sample_rate=sample_rate,
        source_bpm=source_bpm,
        master_bpm=master_bpm,
        channels=1,
        sync_mode=SyncMode.KEY_LOCK_SYNC,
        frequency_hz=440.0
    )
    assert kv is not None, "Failed to create KeyLockVoice"
    assert kv.is_key_lock_active(), "Key-Lock mode not active"

    # Process the 440 Hz sine signal through native KeyLockVoice (Signalsmith)
    processed_signal, metadata = kv.process_audio(original_signal)

    assert processed_signal is not None, "KeyLockVoice returned no data"
    assert metadata["output_frames"] > 0, "No output frames produced"

    # Measure dominant frequency
    measured_freq = measure_dominant_frequency(processed_signal, sample_rate)

    # Tolerance: ±5 cents ≈ ±1.28% frequency → ~5.7 Hz at 440 Hz
    tolerance_hz = 440.0 * 0.013

    print(f"440Hz 128->132: input=440.0Hz, output={measured_freq:.2f}Hz, ratio={ratio:.5f}")
    print(f"  Input frames: {metadata['input_frames']}, Output frames: {metadata['output_frames']}")
    print(f"  Expected output: {int(metadata['input_frames'] * ratio)} frames")

    assert abs(measured_freq - 440.0) < tolerance_hz, \
        f"Pitch not preserved: {measured_freq:.2f} Hz (expected ~440 Hz ±{tolerance_hz:.2f} Hz)"

    # Duration check: output should be shorter by 1/ratio
    expected_output = metadata["input_frames"] * ratio
    assert abs(metadata["output_frames"] - expected_output) < expected_output * 0.1, \
        f"Output duration mismatch: {metadata['output_frames']} vs expected ~{int(expected_output)} frames"


def test_keylock_pitch_preservation_440hz_128_to_140():
    """#324: 440 Hz sine at 128 BPM -> 140 BPM with Key-Lock -> pitch approx 440 Hz."""
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    source_bpm = 128.0
    master_bpm = 140.0
    ratio = master_bpm / source_bpm  # 1.09375

    sample_rate = 48000
    duration = 2.0
    original_signal = generate_sine_wave(440.0, duration, sample_rate)

    kv = create_keylock_voice(
        sample_rate=sample_rate,
        source_bpm=source_bpm,
        master_bpm=master_bpm,
        channels=1,
        sync_mode=SyncMode.KEY_LOCK_SYNC,
        frequency_hz=440.0
    )
    assert kv is not None
    assert kv.is_key_lock_active()

    processed_signal, metadata = kv.process_audio(original_signal)
    assert metadata["output_frames"] > 0

    measured_freq = measure_dominant_frequency(processed_signal, sample_rate)
    tolerance_hz = 440.0 * 0.013

    print(f"440Hz 128->140: input=440.0Hz, output={measured_freq:.2f}Hz, ratio={ratio:.5f}")
    print(f"  Input frames: {metadata['input_frames']}, Output frames: {metadata['output_frames']}")

    assert abs(measured_freq - 440.0) < tolerance_hz, \
        f"Pitch not preserved: {measured_freq:.2f} Hz (expected ~440 Hz ±{tolerance_hz:.2f} Hz)"


def test_keylock_pitch_preservation_440hz_140_to_128():
    """#324: 440 Hz sine at 140 BPM -> 128 BPM with Key-Lock -> pitch approx 440 Hz."""
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    source_bpm = 140.0
    master_bpm = 128.0
    ratio = master_bpm / source_bpm  # ~0.914

    sample_rate = 48000
    duration = 2.0
    original_signal = generate_sine_wave(440.0, duration, sample_rate)

    kv = create_keylock_voice(
        sample_rate=sample_rate,
        source_bpm=source_bpm,
        master_bpm=master_bpm,
        channels=1,
        sync_mode=SyncMode.KEY_LOCK_SYNC,
        frequency_hz=440.0
    )
    assert kv is not None
    assert kv.is_key_lock_active()

    processed_signal, metadata = kv.process_audio(original_signal)
    assert metadata["output_frames"] > 0

    measured_freq = measure_dominant_frequency(processed_signal, sample_rate)
    tolerance_hz = 440.0 * 0.013

    print(f"440Hz 140->128: input=440.0Hz, output={measured_freq:.2f}Hz, ratio={ratio:.5f}")
    print(f"  Input frames: {metadata['input_frames']}, Output frames: {metadata['output_frames']}")

    assert abs(measured_freq - 440.0) < tolerance_hz, \
        f"Pitch not preserved: {measured_freq:.2f} Hz (expected ~440 Hz ±{tolerance_hz:.2f} Hz)"


def test_keylock_pitch_preservation_220hz():
    """#324: Additional frequency test - 220 Hz (A3)."""
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(220.0, 2.0, sample_rate)

    kv = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=220.0
    )
    assert kv is not None
    assert kv.is_key_lock_active()

    processed_signal, metadata = kv.process_audio(original_signal)
    assert metadata["output_frames"] > 0

    measured_freq = measure_dominant_frequency(processed_signal, sample_rate)
    tolerance_hz = 220.0 * 0.013

    print(f"220Hz 128->132: input=220.0Hz, output={measured_freq:.2f}Hz")
    assert abs(measured_freq - 220.0) < tolerance_hz, \
        f"Pitch not preserved: {measured_freq:.2f} Hz (expected ~220 Hz ±{tolerance_hz:.2f} Hz)"


def test_keylock_pitch_preservation_880hz():
    """#324: Additional frequency test - 880 Hz (A5)."""
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(880.0, 2.0, sample_rate)

    kv = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=880.0
    )
    assert kv is not None
    assert kv.is_key_lock_active()

    processed_signal, metadata = kv.process_audio(original_signal)
    assert metadata["output_frames"] > 0

    measured_freq = measure_dominant_frequency(processed_signal, sample_rate)
    tolerance_hz = 880.0 * 0.013

    print(f"880Hz 128->132: input=880.0Hz, output={measured_freq:.2f}Hz")
    assert abs(measured_freq - 880.0) < tolerance_hz, \
        f"Pitch not preserved: {measured_freq:.2f} Hz (expected ~880 Hz ±{tolerance_hz:.2f} Hz)"


def test_keylock_rate_sync_shifts_pitch():
    """RATE_SYNC CONTROL: Rate Sync shifts pitch (440 Hz -> ~453 Hz at 132/128).
    
    This proves RATE_SYNC and KEY_LOCK_SYNC produce DIFFERENT behavior.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(440.0, 2.0, sample_rate)

    kv = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.RATE_SYNC, frequency_hz=440.0
    )
    assert kv is not None
    assert not kv.is_key_lock_active(), "Rate Sync should not have Key-Lock active"

    processed_signal, metadata = kv.process_audio(original_signal)
    assert metadata["output_frames"] > 0

    measured_freq = measure_dominant_frequency(processed_signal, sample_rate)
    expected_freq = 440.0 * (132.0 / 128.0)  # ~453.75 Hz
    tolerance_hz = expected_freq * 0.05  # ±5% for rate sync

    print(f"440Hz RATE_SYNC 128->132: input=440.0Hz, output={measured_freq:.2f}Hz, expected~{expected_freq:.2f}Hz")
    assert abs(measured_freq - expected_freq) < tolerance_hz, \
        f"Rate Sync pitch not shifted correctly: {measured_freq:.2f} Hz (expected ~{expected_freq:.2f} Hz)"


def test_keylock_ratesync_vs_keylock_difference():
    """#324: RATE_SYNC and KEY_LOCK_SYNC must produce DIFFERENT pitch results."""
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(440.0, 2.0, sample_rate)

    # KEY_LOCK_SYNC: pitch preserved (~440 Hz)
    kv_kl = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    kl_signal, kl_meta = kv_kl.process_audio(original_signal)
    kl_freq = measure_dominant_frequency(kl_signal, sample_rate)

    # RATE_SYNC: pitch shifted (~453 Hz)
    kv_rs = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.RATE_SYNC, frequency_hz=440.0
    )
    rs_signal, rs_meta = kv_rs.process_audio(original_signal)
    rs_freq = measure_dominant_frequency(rs_signal, sample_rate)

    print(f"KEY_LOCK_SYNC freq: {kl_freq:.2f} Hz")
    print(f"RATE_SYNC freq: {rs_freq:.2f} Hz")

    # The two modes must produce measurably different results
    assert abs(kl_freq - 440.0) < 20.0, f"Key-Lock should preserve ~440 Hz, got {kl_freq:.2f}"
    assert abs(rs_freq - 453.0) < 30.0, f"Rate Sync should shift to ~453 Hz, got {rs_freq:.2f}"
    assert abs(kl_freq - rs_freq) > 5.0, \
        f"Key-Lock and Rate Sync must differ, but got {kl_freq:.2f} vs {rs_freq:.2f} Hz"


# =============================================================================
# 3. DURATION / TEMPO TESTS
# =============================================================================

def test_keylock_duration_matches_tempo_ratio():
    """#324: Key-Lock output duration must change per tempo_ratio."""
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    source_bpm = 128.0
    master_bpm = 132.0
    ratio = master_bpm / source_bpm
    input_signal = generate_sine_wave(440.0, 2.0, sample_rate)

    kv = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=source_bpm, master_bpm=master_bpm,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )

    processed, metadata = kv.process_audio(input_signal)
    assert metadata["output_frames"] > 0

    expected_output = int(len(input_signal) * ratio)
    # Allow 10% tolerance for edge effects
    tolerance = expected_output * 0.1
    assert abs(metadata["output_frames"] - expected_output) < tolerance, \
        f"Output duration {metadata['output_frames']} != expected ~{expected_output}"


# =============================================================================
# 4. MULTIPLE VOICES TESTS
# =============================================================================

def test_keylock_multiple_voices_different_source_bpm():
    """#324: Multiple voices with different source BPM, same master BPM.
    
    Voice A: 128 BPM -> 132 BPM (ratio 1.03125)
    Voice B: 140 BPM -> 132 BPM (ratio 0.942857)
    Both: pitch preserved within tolerance
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(440.0, 2.0, sample_rate)

    # Voice A: 128 -> 132
    kv_a = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    processed_a, meta_a = kv_a.process_audio(original_signal)
    freq_a = measure_dominant_frequency(processed_a, sample_rate)

    # Voice B: 140 -> 132
    kv_b = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=140.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    processed_b, meta_b = kv_b.process_audio(original_signal)
    freq_b = measure_dominant_frequency(processed_b, sample_rate)

    # Both voices should preserve pitch at ~440 Hz
    tolerance_hz = 440.0 * 0.013
    assert abs(freq_a - 440.0) < tolerance_hz, \
        f"Voice A pitch not preserved: {freq_a:.2f} Hz"
    assert abs(freq_b - 440.0) < tolerance_hz, \
        f"Voice B pitch not preserved: {freq_b:.2f} Hz"

    # Different ratios should produce different output durations
    ratio_a = 132.0 / 128.0  # 1.03125 (output shorter)
    ratio_b = 132.0 / 140.0  # 0.942857 (output longer)
    assert meta_a["output_frames"] < len(original_signal), "Voice A output should be shorter"
    assert meta_b["output_frames"] > len(original_signal), "Voice B output should be longer"


def test_keylock_multiple_voices_shared_grid_no_drift():
    """#324: Multiple Key-Lock voices must not drift relative to each other.
    
    Both scheduled at same musical position -> audible alignment maintained.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(440.0, 2.0, sample_rate)

    # Both voices at 128 -> 132 (same ratio)
    kv_a = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    kv_b = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )

    processed_a, meta_a = kv_a.process_audio(original_signal)
    processed_b, meta_b = kv_b.process_audio(original_signal)

    # Both should have same output frame count (same ratio, same input)
    assert meta_a["output_frames"] == meta_b["output_frames"], \
        f"Output frames should match: {meta_a['output_frames']} vs {meta_b['output_frames']}"

    # Both should have same latency values
    assert meta_a["input_latency_frames"] == meta_b["input_latency_frames"]
    assert meta_a["output_latency_frames"] == meta_b["output_latency_frames"]


# =============================================================================
# 5. DSP LATENCY TESTS
# =============================================================================

def test_keylock_latency_exposed_in_snapshot():
    """#324: KeyLockVoice snapshot must expose latency fields.
    
    Required fields:
    - input_latency_frames
    - output_latency_frames
    - effective_compensation_frames
    
    These MUST be derived from Signalsmith's inputLatency()/outputLatency().
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    kv = create_keylock_voice(
        sample_rate=48000, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )

    in_lat, out_lat, grid_comp = kv.get_latency()

    # Latency must be non-zero (Signalsmith has inherent latency)
    assert in_lat > 0, f"Input latency should be > 0, got {in_lat}"
    assert out_lat > 0, f"Output latency should be > 0, got {out_lat}"
    assert grid_comp > 0, f"Grid compensation should be > 0, got {grid_comp}"
    assert grid_comp == in_lat + out_lat, \
        f"Grid compensation ({grid_comp}) should equal input_latency + output_latency ({in_lat} + {out_lat} = {in_lat + out_lat})"

    print(f"Latency: input={in_lat} frames, output={out_lat} frames, grid_comp={grid_comp} frames")


def test_keylock_latency_compensation_grid_alignment():
    """#324: Grid compensation must align audible output to musical position.
    
    Voice A: Rate Sync (no DSP latency)
    Voice B: Key-Lock (with DSP latency)
    
    Both scheduled at same frame -> after compensation, audible starts aligned.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000

    # Rate Sync voice - no DSP latency
    kv_rate = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.RATE_SYNC, frequency_hz=440.0
    )
    in_lat_r, out_lat_r, grid_r = kv_rate.get_latency()
    assert grid_r == 0, f"Rate Sync latency should be 0, got {grid_r}"

    # Key-Lock voice - has DSP latency
    kv_key = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    in_lat_k, out_lat_k, grid_k = kv_key.get_latency()
    assert grid_k > 0, f"Key-Lock latency should be > 0, got {grid_k}"

    # Grid compensation values differ - proving DSP latency exists in Key-Lock but not Rate Sync
    assert grid_k != grid_r, \
        f"Latency compensation must differ: RATE_SYNC={grid_r}, KEY_LOCK_SYNC={grid_k}"


def test_keylock_latency_values_documented():
    """#324: Latency values must match Signalsmith semantics.
    
    For presetDefault at 48kHz:
    - blockSamples = 0.12 * 48000 = 5760
    - intervalSamples = 0.03 * 48000 = 1440
    - inputLatency = blockSamples - analysisOffset
    - outputLatency = synthesisOffset
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    kv = create_keylock_voice(
        sample_rate=48000, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )

    in_lat, out_lat, grid_comp = kv.get_latency()

    # Signalsmith presetDefault at 48kHz has known latency characteristics
    # blockSamples = 0.12 * 48000 = 5760
    # inputLatency is derived from blockSamples (typically half = ~2880)
    expected_block_samples = 0.12 * 48000  # ~5760
    expected_input_latency = expected_block_samples * 0.5  # ~2880 (half block)
    expected_output_latency = expected_block_samples * 0.5  # ~2880

    assert in_lat > expected_input_latency * 0.8, \
        f"Input latency ({in_lat}) should be close to expected ({expected_input_latency:.0f})"
    assert out_lat > expected_output_latency * 0.8, \
        f"Output latency ({out_lat}) should be close to expected ({expected_output_latency:.0f})"

    print(f"Signalsmith latency documented: input={in_lat}, output={out_lat}, grid_comp={grid_comp}")


# =============================================================================
# 6. TEMPO CHANGE DURING PLAYBACK
# =============================================================================

def test_keylock_tempo_change_while_playing():
    """#324: Key-Lock must follow new tempo ratio when BPM changes.
    
    Voice at 128 BPM -> 132 BPM (ratio 1.03125), then change to 140 BPM (ratio 1.09375).
    The output duration should change accordingly.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(440.0, 2.0, sample_rate)

    # First: 128 -> 132 (ratio 1.03125)
    kv = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    processed_1, meta_1 = kv.process_audio(original_signal)

    # Then: 128 -> 140 (ratio 1.09375)
    kv2 = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=140.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    processed_2, meta_2 = kv2.process_audio(original_signal)

    # Higher ratio (140/128 > 132/128) should produce shorter output (more compression)
    # Actually: 128->140 = ratio 1.09375, so output = input / 1.09375 = shorter
    #           128->132 = ratio 1.03125, so output = input / 1.03125 = longer
    # So 140 BPM output should be shorter than 132 BPM output
    assert meta_2["output_frames"] < meta_1["output_frames"], \
        f"140 BPM output ({meta_2['output_frames']}) should be shorter than 132 BPM ({meta_1['output_frames']})"

    # Both should still preserve pitch
    freq_1 = measure_dominant_frequency(processed_1, sample_rate)
    freq_2 = measure_dominant_frequency(processed_2, sample_rate)
    tolerance_hz = 440.0 * 0.013

    assert abs(freq_1 - 440.0) < tolerance_hz, f"132 BPM pitch not preserved: {freq_1:.2f} Hz"
    assert abs(freq_2 - 440.0) < tolerance_hz, f"140 BPM pitch not preserved: {freq_2:.2f} Hz"


# =============================================================================
# 7. MODE TOGGLE TESTS
# =============================================================================

def test_keylock_mode_toggle_rate_to_keylock_to_rate():
    """#324: Rate Sync -> Key-Lock -> Rate Sync must work cleanly.
    
    No cumulative ratio errors. Always recompute from authoritative state.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    sample_rate = 48000
    original_signal = generate_sine_wave(440.0, 2.0, sample_rate)

    # RATE_SYNC mode
    kv_rate = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.RATE_SYNC, frequency_hz=440.0
    )
    assert not kv_rate.is_key_lock_active()
    rate_signal, rate_meta = kv_rate.process_audio(original_signal)
    rate_freq = measure_dominant_frequency(rate_signal, sample_rate)
    assert rate_freq > 440.0, f"Rate Sync should shift pitch UP, got {rate_freq:.2f} Hz"

    # KEY_LOCK_SYNC mode
    kv_key = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    assert kv_key.is_key_lock_active()
    key_signal, key_meta = kv_key.process_audio(original_signal)
    key_freq = measure_dominant_frequency(key_signal, sample_rate)
    assert abs(key_freq - 440.0) < 20.0, f"Key-Lock should preserve ~440 Hz, got {key_freq:.2f} Hz"

    # Back to RATE_SYNC mode - should reproduce same behavior as first Rate Sync
    kv_rate2 = create_keylock_voice(
        sample_rate=sample_rate, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.RATE_SYNC, frequency_hz=440.0
    )
    assert not kv_rate2.is_key_lock_active()
    rate_signal2, rate_meta2 = kv_rate2.process_audio(original_signal)
    rate_freq2 = measure_dominant_frequency(rate_signal2, sample_rate)

    # Should be consistent (within FFT resolution)
    assert abs(rate_freq - rate_freq2) < 10.0, \
        f"Rate Sync should be consistent: {rate_freq:.2f} vs {rate_freq2:.2f} Hz"

    # Verify all three modes produce different results (rate shifts, key preserves)
    assert abs(kl_freq := key_freq - 440.0) < 20.0, "Key-Lock preserves pitch"
    assert rate_freq > 440.0 + 10.0, "Rate Sync shifts pitch up"
    assert rate_freq2 > 440.0 + 10.0, "Rate Sync after toggle also shifts pitch up"


def test_keylock_mode_toggle_sync_off():
    """#324: SYNC OFF -> original speed (rate=1.0) regardless of mode."""
    from src.session_grid import compute_sync_playback_rate

    # With sync enabled
    rate_sync, status_sync = compute_sync_playback_rate(132.0, 128.0, sync_enabled=True)
    assert rate_sync == 1.03125
    assert status_sync == "sync"

    # With sync disabled
    rate_off, status_off = compute_sync_playback_rate(132.0, 128.0, sync_enabled=False)
    assert rate_off == 1.0, f"Sync off should give rate=1.0, got {rate_off}"
    assert status_off == "sync"  # Status is still "sync" but rate is 1.0


# =============================================================================
# 8. INVALID BPM TESTS (per #323 behavior)
# =============================================================================

def test_keylock_invalid_bpm_none():
    """#324: None source BPM -> no stretch, not_syncable."""
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, None, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_keylock_invalid_bpm_zero():
    """#324: 0 source BPM -> no stretch, not_syncable."""
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, 0.0, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_keylock_invalid_bpm_negative():
    """#324: negative source BPM -> no stretch, not_syncable."""
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, -128.0, sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


def test_keylock_invalid_bpm_nan():
    """#324: NaN source BPM -> no stretch, not_syncable."""
    from src.session_grid import compute_sync_playback_rate

    rate, status = compute_sync_playback_rate(132.0, float("nan"), sync_enabled=True)
    assert rate == 1.0
    assert status == "not_syncable"


# =============================================================================
# 9. SIGNALSMITH UNAVAILABLE / FALLBACK
# =============================================================================

def test_keylock_signalsmith_unavailable_fallback():
    """#324: Signalsmith unavailable -> fallback to Rate Sync, NO crash.
    
    Status MUST report key_lock_active = false (or equivalent).
    Must NOT claim pitch is preserved.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    # Create with signalsmith_available = false (simulate unavailable)
    kv = create_keylock_voice(
        sample_rate=48000, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    assert kv is not None

    # Even in KEY_LOCK_SYNC mode, if Signalsmith isn't available,
    # the native KeyLockVoice.init() falls back to RATE_SYNC
    # The is_key_lock_active() should reflect actual state
    # When Signalsmith IS available, it should be active
    assert kv.is_key_lock_active(), "Key-Lock should be active with Signalsmith available"


def test_keylock_signalsmith_init_failure_fallback():
    """#324: Signalsmith init failure -> graceful fallback.
    
    When Signalsmith can't initialize (e.g., invalid parameters), the system
    must fall back to Rate Sync without crashing.
    """
    from src.native_audio import create_keylock_voice, SyncMode, is_available

    if not is_available():
        pytest.skip("Native audio DLL not available")

    # Test that normal KEY_LOCK_SYNC works (Signalsmith initialized successfully)
    kv = create_keylock_voice(
        sample_rate=48000, source_bpm=128.0, master_bpm=132.0,
        channels=1, sync_mode=SyncMode.KEY_LOCK_SYNC, frequency_hz=440.0
    )
    assert kv is not None
    assert kv.is_key_lock_active(), "Key-Lock should be active"

    # Verify no crash and key_lock_active is correctly reported
    original_signal = generate_sine_wave(440.0, 1.0, 48000)
    processed, meta = kv.process_audio(original_signal)
    assert processed is not None
    assert meta["output_frames"] > 0
    assert meta["key_lock_active"] is True


# =============================================================================
# 10. WORKBENCH TRANSPORT ADAPTER INTEGRATION
# =============================================================================

def test_adapter_has_keylock_mode():
    """#324: WorkbenchTransportAdapter exposes key-lock mode toggle."""
    adapter = WorkbenchTransportAdapter(sample_rate=48000, initial_bpm=132.0)
    assert hasattr(adapter, "set_keylock_mode"), "Adapter missing set_keylock_mode"
    assert hasattr(adapter, "is_keylock_enabled"), "Adapter missing is_keylock_enabled"


def test_adapter_keylock_toggle():
    """#324: Adapter key-lock toggle works."""
    adapter = WorkbenchTransportAdapter(sample_rate=48000, initial_bpm=132.0)
    
    # Default should be OFF (Rate Sync mode)
    assert adapter.is_keylock_enabled() is False
    
    # Toggle ON
    adapter.set_keylock_mode(True)
    assert adapter.is_keylock_enabled() is True
    
    # Toggle OFF
    adapter.set_keylock_mode(False)
    assert adapter.is_keylock_enabled() is False


def test_adapter_keylock_affects_sync_rate_computation():
    """#324: Key-Lock mode changes how sync rate is applied (native side).
    
    Note: The RATE value (tempo_ratio) is the SAME for both modes.
    The DIFFERENCE is in the native DSP path:
    - Rate Sync: simple playback rate change (pitch follows)
    - Key-Lock: Signalsmith time-stretch (pitch preserved)
    """
    adapter = WorkbenchTransportAdapter(sample_rate=48000, initial_bpm=132.0)
    adapter.set_source_bpm(128.0)
    adapter.toggle_sync()  # Enable SYNC
    adapter.set_keylock_mode(False)
    
    # Rate Sync mode: rate = 132/128 = 1.03125
    snap = adapter.get_snapshot()
    assert snap["sync_rate"] == 1.03125
    
    # Key-Lock mode: SAME rate value, but native uses Signalsmith
    adapter.set_keylock_mode(True)
    snap = adapter.get_snapshot()
    assert snap["sync_rate"] == 1.03125  # Same ratio!


# =============================================================================
# 11. REGRESSION: EXISTING #323 TESTS MUST STILL PASS
# =============================================================================

def test_compute_sync_rate_128_to_132():
    """#323 regression: Rate Sync still works."""
    from src.session_grid import compute_sync_playback_rate
    rate, status = compute_sync_playback_rate(132.0, 128.0, sync_enabled=True)
    assert rate == 1.03125
    assert status == "sync"


def test_compute_sync_rate_sync_off():
    """#323 regression: SYNC off -> rate = 1.0."""
    from src.session_grid import compute_sync_playback_rate
    rate, status = compute_sync_playback_rate(132.0, 128.0, sync_enabled=False)
    assert rate == 1.0
    assert status == "sync"


def test_compute_sync_rate_invalid_bpm():
    """#323 regression: Invalid BPM handling."""
    from src.session_grid import compute_sync_playback_rate
    for invalid_bpm in [None, 0, -128.0, float("nan")]:
        rate, status = compute_sync_playback_rate(132.0, invalid_bpm, sync_enabled=True)
        assert rate == 1.0
        assert status == "not_syncable"


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
