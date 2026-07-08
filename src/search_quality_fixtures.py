from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

from .config import ANALYZE_SR

_CLAP_SR = 48_000


def write_kick_transient_wav(
    path: Path,
    *,
    bpm: float = 120.0,
    duration_sec: float = 4.0,
    amplitude: float = 0.8,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    n_total = max(1, int(sr * duration_sec))
    y = np.zeros(n_total, dtype=np.float32)
    interval_sec = 60.0 / bpm
    kick_duration = min(0.15, interval_sec * 0.4)
    kick_samples = max(1, int(kick_duration * sr))
    t_kick = np.linspace(0.0, kick_duration, kick_samples, dtype=np.float32)
    envelope = np.exp(-t_kick * 25.0)
    kick = amplitude * np.sin(2.0 * np.pi * 60.0 * t_kick) * envelope
    num_pulses = int(duration_sec / interval_sec)
    for i in range(num_pulses):
        start = int(i * interval_sec * sr)
        if start + kick_samples <= n_total:
            y[start : start + kick_samples] += kick.astype(np.float32)
    y = np.clip(y, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def write_pulse_train_wav(
    path: Path,
    *,
    bpm: float = 120.0,
    duration_sec: float = 4.0,
    amplitude: float = 0.8,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    n_total = max(1, int(sr * duration_sec))
    y = np.zeros(n_total, dtype=np.float32)
    interval_sec = 60.0 / bpm
    pulse_duration = 0.005
    pulse_samples = max(1, int(pulse_duration * sr))
    t_pulse = np.linspace(0.0, pulse_duration, pulse_samples, dtype=np.float32)
    envelope = np.linspace(1.0, 0.0, pulse_samples, dtype=np.float32) ** 2
    pulse = amplitude * np.sin(2.0 * np.pi * 800.0 * t_pulse) * envelope
    num_pulses = int(duration_sec / interval_sec)
    for i in range(num_pulses):
        start = int(i * interval_sec * sr)
        if start + pulse_samples <= n_total:
            y[start : start + pulse_samples] += pulse.astype(np.float32)
    y = np.clip(y, -1.0, 1.0)
    sf.write(path, y, sr, subtype="PCM_16")
    return path


def write_perc_hit_wav(
    path: Path,
    *,
    duration_sec: float = 0.08,
    amplitude: float = 0.9,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, dtype=np.float32)
    envelope = np.exp(-t * 80.0)
    wave = amplitude * np.sin(2.0 * np.pi * 1200.0 * t) * envelope
    sf.write(path, wave.astype(np.float32), sr, subtype="PCM_16")
    return path


def write_sine_wav(
    path: Path,
    *,
    frequency_hz: float = 220.0,
    duration_sec: float = 4.0,
    amplitude: float = 0.5,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    wave = amplitude * np.sin(2.0 * np.pi * frequency_hz * t)
    sf.write(path, wave.astype(np.float32), sr, subtype="PCM_16")
    return path


def write_chord_pad_wav(
    path: Path,
    *,
    root_hz: float = 220.0,
    duration_sec: float = 4.0,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    freqs = [root_hz, root_hz * 5.0 / 4.0, root_hz * 3.0 / 2.0]
    wave = sum(0.33 * np.sin(2.0 * np.pi * freq * t) for freq in freqs).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def _formant_envelope(freqs: np.ndarray, formants_hz: list[float], bandwidth_q: float) -> np.ndarray:
    envelope = np.full(freqs.shape, 0.01, dtype=np.float32)
    for center_hz in formants_hz:
        bandwidth_hz = max(center_hz / bandwidth_q, 20.0)
        envelope += np.exp(-0.5 * ((freqs - center_hz) / bandwidth_hz) ** 2).astype(np.float32)
    return envelope


def render_formant_tone_waveform(
    *,
    duration_sec: float = 4.0,
    f0_hz: float = 150.0,
    formants_hz: list[float] | None = None,
    bandwidth_q: float = 8.0,
    vibrato_hz: float = 0.0,
    vibrato_depth: float = 0.0,
    amplitude: float = 0.5,
) -> np.ndarray:
    """Deterministic formant-like harmonic source (synthetic vocal proxy, not real speech)."""
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    formants = formants_hz or [700.0, 1220.0, 2600.0]

    if vibrato_hz > 0.0 and vibrato_depth > 0.0:
        f0_inst = f0_hz * (
            1.0 + vibrato_depth * np.sin(2.0 * np.pi * vibrato_hz * t)
        ).astype(np.float32)
        phase = (2.0 * np.pi * np.cumsum(f0_inst) / sr).astype(np.float32)
    else:
        phase = (2.0 * np.pi * f0_hz * t).astype(np.float32)

    source = np.zeros(sample_count, dtype=np.float32)
    for harmonic in range(1, 24):
        if harmonic * f0_hz >= sr / 2.0:
            break
        source += (1.0 / harmonic) * np.sin(harmonic * phase).astype(np.float32)

    spectrum = np.fft.rfft(source)
    freqs = np.fft.rfftfreq(sample_count, 1.0 / sr)
    shaped = np.fft.irfft(spectrum * _formant_envelope(freqs, formants, bandwidth_q), n=sample_count)
    peak = float(np.max(np.abs(shaped)))
    if peak > 0.0:
        shaped = shaped / peak
    return np.clip(amplitude * shaped.astype(np.float32), -1.0, 1.0)


def write_formant_tone_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    f0_hz: float = 150.0,
    formants_hz: list[float] | None = None,
    bandwidth_q: float = 8.0,
    vibrato_hz: float = 0.0,
    vibrato_depth: float = 0.0,
    amplitude: float = 0.5,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = render_formant_tone_waveform(
        duration_sec=duration_sec,
        f0_hz=f0_hz,
        formants_hz=formants_hz,
        bandwidth_q=bandwidth_q,
        vibrato_hz=vibrato_hz,
        vibrato_depth=vibrato_depth,
        amplitude=amplitude,
    )
    sf.write(path, wave, _CLAP_SR, subtype="PCM_16")
    return path


def write_vowel_pad_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    f0_hz: float = 140.0,
    formants_hz: list[float] | None = None,
    bandwidth_q: float = 8.0,
    vibrato_hz: float = 5.5,
    vibrato_depth: float = 0.015,
    attack_sec: float = 0.35,
    amplitude: float = 0.45,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = render_formant_tone_waveform(
        duration_sec=duration_sec,
        f0_hz=f0_hz,
        formants_hz=formants_hz,
        bandwidth_q=bandwidth_q,
        vibrato_hz=vibrato_hz,
        vibrato_depth=vibrato_depth,
        amplitude=1.0,
    )
    sample_count = wave.shape[0]
    attack_samples = max(1, int(attack_sec * _CLAP_SR))
    envelope = np.ones(sample_count, dtype=np.float32)
    envelope[:attack_samples] = np.linspace(0.0, 1.0, attack_samples, dtype=np.float32)
    release_samples = max(1, int(0.25 * _CLAP_SR))
    envelope[-release_samples:] *= np.linspace(1.0, 0.0, release_samples, dtype=np.float32)
    wave = np.clip(amplitude * wave * envelope, -1.0, 1.0).astype(np.float32)
    sf.write(path, wave, _CLAP_SR, subtype="PCM_16")
    return path


def write_texture_noise_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    seed: int = 42,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    rng = np.random.default_rng(seed)
    wave = rng.normal(0.0, 0.25, sample_count).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def _render_fixture_waveform(
    fixture_type: str,
    params: dict[str, Any],
    *,
    duration_sec: float = 4.0,
) -> np.ndarray:
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)

    if fixture_type == "kick_transient":
        bpm = float(params.get("bpm", 120.0))
        y = np.zeros(sample_count, dtype=np.float32)
        interval_sec = 60.0 / bpm
        kick_duration = min(0.15, interval_sec * 0.4)
        kick_samples = max(1, int(kick_duration * sr))
        t_kick = np.linspace(0.0, kick_duration, kick_samples, dtype=np.float32)
        envelope = np.exp(-t_kick * 25.0)
        kick = 0.8 * np.sin(2.0 * np.pi * 60.0 * t_kick) * envelope
        num_pulses = int(duration_sec / interval_sec)
        for i in range(num_pulses):
            start = int(i * interval_sec * sr)
            if start + kick_samples <= sample_count:
                y[start : start + kick_samples] += kick.astype(np.float32)
        return np.clip(y, -1.0, 1.0)

    if fixture_type == "sine_tone":
        frequency_hz = float(params.get("frequency_hz", 220.0))
        return (0.5 * np.sin(2.0 * np.pi * frequency_hz * t)).astype(np.float32)

    if fixture_type == "perc_hit":
        hit_duration = float(params.get("duration_sec", 0.08))
        hit_samples = max(1, int(hit_duration * sr))
        t_hit = np.linspace(0.0, hit_duration, hit_samples, dtype=np.float32)
        envelope = np.exp(-t_hit * 80.0)
        hit = 0.9 * np.sin(2.0 * np.pi * 1200.0 * t_hit) * envelope
        y = np.zeros(sample_count, dtype=np.float32)
        y[:hit_samples] = hit.astype(np.float32)
        return y

    raise ValueError(f"Cannot render waveform for fixture type: {fixture_type}")


def _synthetic_reverb_ir(
    *,
    ir_decay_sec: float,
    seed: int,
) -> np.ndarray:
    sr = _CLAP_SR
    ir_samples = max(1, int(ir_decay_sec * sr))
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 1.0, ir_samples).astype(np.float32)
    decay = np.exp(-np.linspace(0.0, 5.0, ir_samples, dtype=np.float32))
    ir = noise * decay
    peak = float(np.max(np.abs(ir)))
    if peak > 0.0:
        ir = ir / peak
    return ir


def apply_synthetic_reverb(
    dry: np.ndarray,
    *,
    ir_decay_sec: float = 1.5,
    mix: float = 0.65,
    seed: int = 101,
) -> np.ndarray:
    ir = _synthetic_reverb_ir(ir_decay_sec=ir_decay_sec, seed=seed)
    wet_tail = np.fft.irfft(np.fft.rfft(dry) * np.fft.rfft(ir, n=len(dry))).astype(np.float32)
    peak = float(np.max(np.abs(wet_tail)))
    if peak > 0.0:
        wet_tail = wet_tail / peak
    mix = float(np.clip(mix, 0.0, 1.0))
    wet = ((1.0 - mix) * dry + mix * wet_tail).astype(np.float32)
    return np.clip(wet, -1.0, 1.0)


def write_freq_sweep_riser_wav(
    path: Path,
    *,
    duration_sec: float = 3.0,
    start_hz: float = 200.0,
    end_hz: float = 4000.0,
    curve: str = "exponential",
    amplitude: float = 0.6,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    if curve == "linear":
        freq = start_hz + (end_hz - start_hz) * (t / duration_sec)
    else:
        ratio = end_hz / max(start_hz, 1.0)
        freq = start_hz * (ratio ** (t / duration_sec))
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    fade_in = np.minimum(1.0, t / max(duration_sec * 0.15, 0.01)).astype(np.float32)
    wave = (amplitude * np.sin(phase) * fade_in).astype(np.float32)
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def write_impact_hit_wav(
    path: Path,
    *,
    decay_sec: float = 0.5,
    noise_seed: int = 7,
    amplitude: float = 0.9,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sr = _CLAP_SR
    sample_count = max(1, int(sr * decay_sec))
    t = np.linspace(0.0, decay_sec, sample_count, dtype=np.float32)
    rng = np.random.default_rng(noise_seed)
    noise = rng.normal(0.0, 1.0, sample_count).astype(np.float32)
    noise_env = np.exp(-t * 12.0)
    thump_env = np.exp(-t * 35.0)
    thump = np.sin(2.0 * np.pi * 55.0 * t) * thump_env
    wave = amplitude * np.clip(noise * noise_env + 0.7 * thump, -1.0, 1.0)
    sf.write(path, wave.astype(np.float32), sr, subtype="PCM_16")
    return path


def write_wet_reverb_wav(
    path: Path,
    *,
    base_fixture_type: str,
    base_params: dict[str, Any] | None = None,
    duration_sec: float = 4.0,
    ir_decay_sec: float = 1.5,
    mix: float = 0.65,
    seed: int = 101,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    base_params = base_params or {}
    dry = _render_fixture_waveform(
        base_fixture_type,
        base_params,
        duration_sec=duration_sec,
    )
    wet = apply_synthetic_reverb(
        dry,
        ir_decay_sec=ir_decay_sec,
        mix=mix,
        seed=seed,
    )
    sf.write(path, wet, _CLAP_SR, subtype="PCM_16")
    return path


_NOTE_ROOT_HZ: dict[str, float] = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
    "B": 493.88,
}


def generate_search_quality_fixture(
    audio_dir: Path,
    fixture_name: str,
    fixture_type: str,
    params: dict[str, Any] | None = None,
) -> Path:
    params = params or {}
    path = audio_dir / f"{fixture_name}.wav"
    if fixture_type == "kick_transient":
        return write_kick_transient_wav(
            path,
            bpm=float(params.get("bpm", 120.0)),
            duration_sec=float(params.get("duration_sec", 4.0)),
        )
    if fixture_type == "pulse_train":
        return write_pulse_train_wav(
            path,
            bpm=float(params.get("bpm", 120.0)),
            duration_sec=float(params.get("duration_sec", 4.0)),
        )
    if fixture_type == "perc_hit":
        return write_perc_hit_wav(path)
    if fixture_type == "sine_tone":
        return write_sine_wav(
            path,
            frequency_hz=float(params.get("frequency_hz", 220.0)),
            duration_sec=float(params.get("duration_sec", 4.0)),
        )
    if fixture_type == "chord_pad":
        root = str(params.get("root", "A"))
        root_hz = float(params.get("root_hz", _NOTE_ROOT_HZ.get(root, 440.0)))
        return write_chord_pad_wav(path, root_hz=root_hz)
    if fixture_type == "texture_noise":
        return write_texture_noise_wav(
            path,
            seed=int(params.get("seed", 42)),
        )
    if fixture_type == "freq_sweep_riser":
        return write_freq_sweep_riser_wav(
            path,
            duration_sec=float(params.get("duration_sec", 3.0)),
            start_hz=float(params.get("start_hz", 200.0)),
            end_hz=float(params.get("end_hz", 4000.0)),
            curve=str(params.get("curve", "exponential")),
        )
    if fixture_type == "impact_hit":
        return write_impact_hit_wav(
            path,
            decay_sec=float(params.get("decay_sec", 0.5)),
            noise_seed=int(params.get("noise_seed", 7)),
        )
    if fixture_type == "wet_reverb":
        base_params = params.get("base_params") or {}
        if not isinstance(base_params, dict):
            base_params = {}
        return write_wet_reverb_wav(
            path,
            base_fixture_type=str(params.get("base_fixture_type", "sine_tone")),
            base_params=base_params,
            duration_sec=float(params.get("duration_sec", 4.0)),
            ir_decay_sec=float(params.get("ir_decay_sec", 1.5)),
            mix=float(params.get("mix", 0.65)),
            seed=int(params.get("seed", 101)),
        )
    if fixture_type == "formant_tone":
        raw_formants = params.get("formants_hz") or [700.0, 1220.0, 2600.0]
        formants_hz = [float(value) for value in raw_formants]
        return write_formant_tone_wav(
            path,
            duration_sec=float(params.get("duration_sec", 4.0)),
            f0_hz=float(params.get("f0_hz", 150.0)),
            formants_hz=formants_hz,
            bandwidth_q=float(params.get("bandwidth_q", 8.0)),
            vibrato_hz=float(params.get("vibrato_hz", 0.0)),
            vibrato_depth=float(params.get("vibrato_depth", 0.0)),
            amplitude=float(params.get("amplitude", 0.5)),
        )
    if fixture_type == "vowel_pad":
        raw_formants = params.get("formants_hz") or [500.0, 1700.0, 2500.0]
        formants_hz = [float(value) for value in raw_formants]
        return write_vowel_pad_wav(
            path,
            duration_sec=float(params.get("duration_sec", 4.0)),
            f0_hz=float(params.get("f0_hz", 140.0)),
            formants_hz=formants_hz,
            bandwidth_q=float(params.get("bandwidth_q", 8.0)),
            vibrato_hz=float(params.get("vibrato_hz", 5.5)),
            vibrato_depth=float(params.get("vibrato_depth", 0.015)),
            attack_sec=float(params.get("attack_sec", 0.35)),
            amplitude=float(params.get("amplitude", 0.45)),
        )
    raise ValueError(f"Unknown search quality fixture type: {fixture_type}")
