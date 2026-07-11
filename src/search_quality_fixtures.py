from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import yaml

_CLAP_SR = 48_000
CLAP_SAMPLE_RATE = _CLAP_SR

DEFAULT_FIXTURE_RECIPES_PATH = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "search_quality"
    / "fixture_recipes.yaml"
)


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
    wave = sum(0.33 * np.sin(2.0 * np.pi * freq * t) for freq in freqs).astype(
        np.float32
    )
    sf.write(path, wave, sr, subtype="PCM_16")
    return path


def _formant_envelope(
    freqs: np.ndarray, formants_hz: list[float], bandwidth_q: float
) -> np.ndarray:
    envelope = np.full(freqs.shape, 0.01, dtype=np.float32)
    for center_hz in formants_hz:
        bandwidth_hz = max(center_hz / bandwidth_q, 20.0)
        envelope += np.exp(-0.5 * ((freqs - center_hz) / bandwidth_hz) ** 2).astype(
            np.float32
        )
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
    shaped = np.fft.irfft(
        spectrum * _formant_envelope(freqs, formants, bandwidth_q), n=sample_count
    )
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
    envelope[-release_samples:] *= np.linspace(
        1.0, 0.0, release_samples, dtype=np.float32
    )
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
    wet_tail = np.fft.irfft(np.fft.rfft(dry) * np.fft.rfft(ir, n=len(dry))).astype(
        np.float32
    )
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
    if fixture_type == "electronic_scene":
        return write_electronic_scene_wav(
            path,
            duration_sec=float(params.get("duration_sec", 4.0)),
            bpm=float(params.get("bpm", 128.0)),
            variant=str(params.get("variant", "dark")),
            seed=int(params.get("seed", 301)),
        )
    if fixture_type == "ambient_scene":
        return write_ambient_scene_wav(
            path,
            duration_sec=float(params.get("duration_sec", 4.0)),
            root_hz=float(params.get("root_hz", 196.0)),
            seed=int(params.get("seed", 302)),
        )
    if fixture_type == "cinematic_tension_scene":
        return write_cinematic_tension_scene_wav(
            path,
            duration_sec=float(params.get("duration_sec", 4.0)),
            rumble_hz=float(params.get("rumble_hz", 45.0)),
            seed=int(params.get("seed", 303)),
        )
    if fixture_type == "warm_harmonic_scene":
        return write_warm_harmonic_scene_wav(
            path,
            duration_sec=float(params.get("duration_sec", 4.0)),
            root_hz=float(params.get("root_hz", 220.0)),
            bpm=float(params.get("bpm", 90.0)),
            seed=int(params.get("seed", 304)),
        )
    if fixture_type == "aggressive_perc_scene":
        return write_aggressive_perc_scene_wav(
            path,
            duration_sec=float(params.get("duration_sec", 4.0)),
            bpm=float(params.get("bpm", 150.0)),
            seed=int(params.get("seed", 305)),
        )
    raise ValueError(f"Unknown search quality fixture type: {fixture_type}")


def _lowpass_one_pole(
    signal: np.ndarray, cutoff_hz: float, sr: int = _CLAP_SR
) -> np.ndarray:
    """Simple one-pole low-pass for deterministic scene shaping."""
    rc = 1.0 / (2.0 * np.pi * max(cutoff_hz, 20.0))
    alpha = 1.0 / (1.0 + rc * sr)
    out = np.zeros_like(signal, dtype=np.float32)
    state = 0.0
    for index, sample in enumerate(signal.astype(np.float32)):
        state = alpha * sample + (1.0 - alpha) * state
        out[index] = state
    return out


def render_electronic_scene_waveform(
    *,
    duration_sec: float = 4.0,
    bpm: float = 128.0,
    variant: str = "dark",
    seed: int = 301,
    amplitude: float = 0.55,
) -> np.ndarray:
    """Deterministic mini electronic loop (dark or bright evaluation hypothesis)."""
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    y = np.zeros(sample_count, dtype=np.float32)
    rng = np.random.default_rng(seed)
    interval_sec = 60.0 / bpm
    kick_duration = min(0.12, interval_sec * 0.35)
    kick_samples = max(1, int(kick_duration * sr))
    t_kick = np.linspace(0.0, kick_duration, kick_samples, dtype=np.float32)
    kick_env = np.exp(-t_kick * 30.0)
    kick_freq = 55.0 if variant == "dark" else 70.0
    kick = np.sin(2.0 * np.pi * kick_freq * t_kick) * kick_env
    num_beats = int(duration_sec / interval_sec)
    for beat in range(num_beats):
        start = int(beat * interval_sec * sr)
        if start + kick_samples <= sample_count:
            y[start : start + kick_samples] += (0.85 * kick).astype(np.float32)
        if beat % 2 == 1:
            hat_start = start + int(0.02 * sr)
            hat_len = max(1, int(0.015 * sr))
            if hat_start + hat_len <= sample_count:
                hat = rng.normal(0.0, 0.35, hat_len).astype(np.float32)
                hat *= np.linspace(1.0, 0.0, hat_len, dtype=np.float32)
                y[hat_start : hat_start + hat_len] += hat

    stab_interval = int(max(1, round(interval_sec * 2.0 * sr)))
    stab_freqs = (
        [110.0, 130.81, 164.81] if variant == "dark" else [220.0, 277.18, 329.63]
    )
    stab_len = max(1, int(0.18 * sr))
    t_stab = np.linspace(0.0, 0.18, stab_len, dtype=np.float32)
    stab_env = np.exp(-t_stab * 10.0)
    for stab_start in range(0, sample_count, stab_interval):
        stab = sum(
            0.25 * np.sin(2.0 * np.pi * freq * t_stab) for freq in stab_freqs
        ).astype(np.float32)
        end = min(sample_count, stab_start + stab_len)
        length = end - stab_start
        y[stab_start:end] += (0.35 * stab_env[:length] * stab[:length]).astype(
            np.float32
        )

    cutoff = 900.0 if variant == "dark" else 4500.0
    shaped = _lowpass_one_pole(y, cutoff, sr)
    peak = float(np.max(np.abs(shaped)))
    if peak > 0.0:
        shaped = shaped / peak
    return np.clip(amplitude * shaped, -1.0, 1.0).astype(np.float32)


def write_electronic_scene_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    bpm: float = 128.0,
    variant: str = "dark",
    seed: int = 301,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = render_electronic_scene_waveform(
        duration_sec=duration_sec,
        bpm=bpm,
        variant=variant,
        seed=seed,
    )
    sf.write(path, wave, _CLAP_SR, subtype="PCM_16")
    return path


def render_ambient_scene_waveform(
    *,
    duration_sec: float = 4.0,
    root_hz: float = 196.0,
    seed: int = 302,
    amplitude: float = 0.35,
) -> np.ndarray:
    """Slow evolving ambient pad scene."""
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    freqs = [root_hz, root_hz * 1.01, root_hz * 1.5, root_hz * 1.505]
    wave = sum(0.22 * np.sin(2.0 * np.pi * freq * t) for freq in freqs).astype(
        np.float32
    )
    lfo = 0.5 + 0.5 * np.sin(2.0 * np.pi * 0.08 * t)
    attack = np.minimum(1.0, t / max(duration_sec * 0.4, 0.05)).astype(np.float32)
    rng = np.random.default_rng(seed)
    shimmer = rng.normal(0.0, 0.015, sample_count).astype(np.float32)
    shimmer = _lowpass_one_pole(shimmer, 800.0, sr)
    combined = (wave * lfo * attack + shimmer).astype(np.float32)
    peak = float(np.max(np.abs(combined)))
    if peak > 0.0:
        combined = combined / peak
    return np.clip(amplitude * combined, -1.0, 1.0).astype(np.float32)


def write_ambient_scene_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    root_hz: float = 196.0,
    seed: int = 302,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = render_ambient_scene_waveform(
        duration_sec=duration_sec,
        root_hz=root_hz,
        seed=seed,
    )
    sf.write(path, wave, _CLAP_SR, subtype="PCM_16")
    return path


def render_cinematic_tension_scene_waveform(
    *,
    duration_sec: float = 4.0,
    rumble_hz: float = 45.0,
    seed: int = 303,
    amplitude: float = 0.5,
) -> np.ndarray:
    """Low rumble with sparse high-frequency swells."""
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    rumble = 0.55 * np.sin(2.0 * np.pi * rumble_hz * t).astype(np.float32)
    rumble += 0.25 * np.sin(2.0 * np.pi * (rumble_hz * 1.5) * t).astype(np.float32)
    rng = np.random.default_rng(seed)
    swell = np.zeros(sample_count, dtype=np.float32)
    swell_interval = int(0.9 * sr)
    swell_len = max(1, int(0.35 * sr))
    for start in range(0, sample_count, swell_interval):
        end = min(sample_count, start + swell_len)
        length = end - start
        burst = rng.normal(0.0, 0.4, length).astype(np.float32)
        env = np.linspace(0.0, 1.0, length // 2 or 1, dtype=np.float32)
        env = np.concatenate(
            [env, np.linspace(1.0, 0.0, length - len(env), dtype=np.float32)]
        )
        swell[start:end] += burst * env[:length]
    swell = _lowpass_one_pole(swell, 6000.0, sr)
    combined = (rumble + 0.45 * swell).astype(np.float32)
    peak = float(np.max(np.abs(combined)))
    if peak > 0.0:
        combined = combined / peak
    return np.clip(amplitude * combined, -1.0, 1.0).astype(np.float32)


def write_cinematic_tension_scene_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    rumble_hz: float = 45.0,
    seed: int = 303,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = render_cinematic_tension_scene_waveform(
        duration_sec=duration_sec,
        rumble_hz=rumble_hz,
        seed=seed,
    )
    sf.write(path, wave, _CLAP_SR, subtype="PCM_16")
    return path


def render_warm_harmonic_scene_waveform(
    *,
    duration_sec: float = 4.0,
    root_hz: float = 220.0,
    bpm: float = 90.0,
    seed: int = 304,
    amplitude: float = 0.42,
) -> np.ndarray:
    """Warm major chord with gentle pulse."""
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    t = np.linspace(0.0, duration_sec, sample_count, endpoint=False, dtype=np.float32)
    major = [root_hz, root_hz * 5.0 / 4.0, root_hz * 3.0 / 2.0, root_hz * 2.0]
    pad = sum(0.2 * np.sin(2.0 * np.pi * freq * t) for freq in major).astype(np.float32)
    interval_sec = 60.0 / bpm
    pulse = np.zeros(sample_count, dtype=np.float32)
    pulse_len = max(1, int(0.06 * sr))
    t_pulse = np.linspace(0.0, 0.06, pulse_len, dtype=np.float32)
    click = np.sin(2.0 * np.pi * 180.0 * t_pulse) * np.exp(-t_pulse * 40.0)
    for beat in range(int(duration_sec / interval_sec)):
        start = int(beat * interval_sec * sr)
        end = min(sample_count, start + pulse_len)
        pulse[start:end] += click[: end - start].astype(np.float32)
    rng = np.random.default_rng(seed)
    warmth = _lowpass_one_pole(
        rng.normal(0.0, 0.02, sample_count).astype(np.float32), 400.0, sr
    )
    combined = (pad + 0.12 * pulse + warmth).astype(np.float32)
    peak = float(np.max(np.abs(combined)))
    if peak > 0.0:
        combined = combined / peak
    return np.clip(amplitude * combined, -1.0, 1.0).astype(np.float32)


def write_warm_harmonic_scene_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    root_hz: float = 220.0,
    bpm: float = 90.0,
    seed: int = 304,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = render_warm_harmonic_scene_waveform(
        duration_sec=duration_sec,
        root_hz=root_hz,
        bpm=bpm,
        seed=seed,
    )
    sf.write(path, wave, _CLAP_SR, subtype="PCM_16")
    return path


def render_aggressive_perc_scene_waveform(
    *,
    duration_sec: float = 4.0,
    bpm: float = 150.0,
    seed: int = 305,
    amplitude: float = 0.6,
) -> np.ndarray:
    """Fast noise/percussion rhythmic scene."""
    sr = _CLAP_SR
    sample_count = max(1, int(sr * duration_sec))
    y = np.zeros(sample_count, dtype=np.float32)
    rng = np.random.default_rng(seed)
    interval_sec = 60.0 / bpm
    kick_len = max(1, int(0.08 * sr))
    t_kick = np.linspace(0.0, 0.08, kick_len, dtype=np.float32)
    kick = np.sin(2.0 * np.pi * 80.0 * t_kick) * np.exp(-t_kick * 35.0)
    for beat in range(int(duration_sec / interval_sec)):
        start = int(beat * interval_sec * sr)
        if start + kick_len <= sample_count:
            y[start : start + kick_len] += (0.9 * kick).astype(np.float32)
        for offset in (0.25, 0.5, 0.75):
            hit_start = start + int(offset * interval_sec * sr)
            hit_len = max(1, int(0.02 * sr))
            if hit_start + hit_len <= sample_count:
                hit = rng.normal(0.0, 0.5, hit_len).astype(np.float32)
                hit *= np.linspace(1.0, 0.0, hit_len, dtype=np.float32)
                y[hit_start : hit_start + hit_len] += hit
    peak = float(np.max(np.abs(y)))
    if peak > 0.0:
        y = y / peak
    return np.clip(amplitude * y, -1.0, 1.0).astype(np.float32)


def write_aggressive_perc_scene_wav(
    path: Path,
    *,
    duration_sec: float = 4.0,
    bpm: float = 150.0,
    seed: int = 305,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    wave = render_aggressive_perc_scene_waveform(
        duration_sec=duration_sec,
        bpm=bpm,
        seed=seed,
    )
    sf.write(path, wave, _CLAP_SR, subtype="PCM_16")
    return path


@dataclass(frozen=True)
class FixtureGenerationReportRow:
    fixture_id: str
    relative_filename: str
    byte_size: int
    duration_sec: float
    sample_rate: int
    channels: int
    peak_abs: float
    sha256: str


def _assert_safe_output_dir(audio_dir: Path) -> None:
    if audio_dir.exists() and not audio_dir.is_dir():
        raise ValueError(f"Output path is not a directory: {audio_dir}")
    try:
        audio_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(f"Invalid output directory: {audio_dir}") from exc


def load_fixture_recipes(path: Path | None = None) -> dict[str, Any]:
    recipes_path = path or DEFAULT_FIXTURE_RECIPES_PATH
    with recipes_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid fixture recipes file: {recipes_path}")
    recipes = data.get("recipes") or {}
    if not isinstance(recipes, dict) or not recipes:
        raise ValueError(
            f"fixture recipes must contain a non-empty recipes mapping: {recipes_path}"
        )
    return data


def list_tier_b_recipe_fixture_ids(
    *,
    query_class: str | None = None,
    recipes_path: Path | None = None,
) -> list[str]:
    data = load_fixture_recipes(recipes_path)
    recipes = data["recipes"]
    fixture_ids = []
    for fixture_id, recipe in recipes.items():
        if query_class and recipe.get("query_class") != query_class:
            continue
        fixture_ids.append(str(fixture_id))
    return sorted(fixture_ids)


def generate_fixture_from_recipe(
    audio_dir: Path,
    fixture_id: str,
    *,
    recipes_path: Path | None = None,
    overwrite: bool = True,
) -> Path:
    _assert_safe_output_dir(audio_dir)
    data = load_fixture_recipes(recipes_path)
    recipes = data["recipes"]
    if fixture_id not in recipes:
        raise ValueError(f"Unknown fixture_id: {fixture_id}")
    recipe = recipes[fixture_id]
    fixture_type = str(recipe["fixture_type"])
    params = dict(recipe.get("fixture_params") or {})
    params.setdefault("duration_sec", float(recipe.get("duration_sec", 4.0)))
    if "seed" in recipe:
        params.setdefault("seed", int(recipe["seed"]))
    path = audio_dir / str(recipe.get("expected_filename", f"{fixture_id}.wav"))
    if path.exists() and not overwrite:
        raise FileExistsError(f"Fixture already exists (overwrite=False): {path}")
    return generate_search_quality_fixture(
        audio_dir,
        fixture_id,
        fixture_type,
        params,
    )


def generate_all_recipe_fixtures(
    audio_dir: Path,
    *,
    recipes_path: Path | None = None,
    overwrite: bool = True,
) -> list[FixtureGenerationReportRow]:
    _assert_safe_output_dir(audio_dir)
    data = load_fixture_recipes(recipes_path)
    recipes = data["recipes"]
    rows: list[FixtureGenerationReportRow] = []
    for fixture_id in sorted(recipes):
        wav_path = generate_fixture_from_recipe(
            audio_dir,
            fixture_id,
            recipes_path=recipes_path,
            overwrite=overwrite,
        )
        rows.append(
            build_fixture_generation_report_row(fixture_id, wav_path, audio_dir)
        )
    return rows


def generate_catalog_fixtures(
    audio_dir: Path,
    suite: dict[str, Any],
    *,
    overwrite: bool = True,
) -> dict[str, Path]:
    """Generate all catalog fixtures declared in a golden suite YAML dict."""
    _assert_safe_output_dir(audio_dir)
    catalog = suite.get("catalog") or {}
    samples = catalog.get("samples") or []
    paths: dict[str, Path] = {}
    for sample in samples:
        fixture_name = str(sample["fixture_name"])
        if fixture_name in paths:
            continue
        fixture_type = str(sample["fixture_type"])
        fixture_params = sample.get("fixture_params") or {}
        wav_path = audio_dir / f"{fixture_name}.wav"
        if wav_path.exists() and not overwrite:
            raise FileExistsError(
                f"Fixture already exists (overwrite=False): {wav_path}"
            )
        paths[fixture_name] = generate_search_quality_fixture(
            audio_dir,
            fixture_name,
            fixture_type,
            fixture_params,
        )
    return paths


def build_fixture_generation_report_row(
    fixture_id: str,
    wav_path: Path,
    base_dir: Path,
) -> FixtureGenerationReportRow:
    payload = wav_path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    info = sf.info(wav_path)
    data, _sr = sf.read(wav_path, dtype="float32", always_2d=True)
    peak = float(np.max(np.abs(data)))
    try:
        relative = wav_path.relative_to(base_dir).as_posix()
    except ValueError:
        relative = wav_path.name
    duration_sec = (
        float(info.frames) / float(info.samplerate) if info.samplerate else 0.0
    )
    return FixtureGenerationReportRow(
        fixture_id=fixture_id,
        relative_filename=relative,
        byte_size=len(payload),
        duration_sec=duration_sec,
        sample_rate=int(info.samplerate),
        channels=int(info.channels),
        peak_abs=peak,
        sha256=digest,
    )
