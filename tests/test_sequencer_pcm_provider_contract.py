"""TEST_GATE / TEST_FREEZE — Production Sequencer PCM cache/decode provider (#676).

Canonical authority:
- docs/PRODUCT_WORKFLOW_CANON.md (build-order step 4 — cached PCM voice)
- docs/SEQUENCER_PLAYBACK_CONTRACT.md
- src/sequencer_playback.py (``pcm_for_path`` injection seam)
- src/channel_rack.py (``play_channel_rack_once``)
- src/native_audio.py (``PcmBufferConfig`` / create_voice validation)
- src/workbench_transport_ui.py (``_load_native_pcm`` audition decode to extract/reuse)

Architecture frozen here (must not couple audition owner to polyphonic sequencer):

1. Shared offline decode lives in ``src.native_pcm_decode.decode_native_pcm`` —
   pure path→PCM, no TransportAwarePreview / QML ownership.
2. ``src.sequencer_pcm.SequencerPcmProvider`` owns path+sample_rate cache and
   fail-soft wrapping; callable as ``pcm_for_path``.
3. ``sequencer_playback`` remains scheduler only (no file decode).
4. Screen-1 audition may *call* the shared decode; it must not *own* the
   sequencer cache.
5. No Screen-2 QML / preview dependency in the provider.

Expected baseline on current main: intentional RED until IMPLEMENTATION_GATE.

v1 cache policy frozen here:
- key = (normalized path, provider sample_rate)
- identical path + sample_rate → cache hit (no re-decode)
- different sample_rate → no false hit
- failed loads are NOT cached (retry can succeed)
- bounded LRU eviction (``max_entries``, default 64)
"""

from __future__ import annotations

import ast
import importlib
import inspect
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Callable
from unittest.mock import MagicMock

import numpy as np
import pytest
import soundfile as sf

from src.native_audio import SB_MAX_VOICES, SB_VOICE_IDLE, PcmBufferConfig
from src.session_grid import TempoMap
from src.workbench_controller import WorkbenchRow
from src.workbench_live_kit import LiveKitState


def _lifecycle_mock_engine() -> MagicMock:
    """MagicMock engine that exposes snapshot/remove for PatternPassPlayer."""
    engine = MagicMock(name="native_engine")
    voices: dict[int, int] = {}

    def create_voice(cfg):
        voices[cfg.id] = SB_VOICE_IDLE
        return cfg.id

    def remove_voice(voice_id: int) -> None:
        voices.pop(int(voice_id), None)

    def get_snapshot():
        ids = list(voices.keys())
        states = [voices[vid] for vid in ids]
        pad = max(0, SB_MAX_VOICES - len(ids))
        return SimpleNamespace(
            total_voice_count=len(voices),
            voice_ids=ids + [0] * pad,
            voice_states=states + [SB_VOICE_IDLE] * pad,
            engine_frame=0,
        )

    engine.create_voice.side_effect = create_voice
    engine.remove_voice.side_effect = remove_voice
    engine.stop_voice.side_effect = lambda _vid: None
    engine.schedule_voice_start.side_effect = lambda _vid, _frame: None
    engine.get_snapshot.side_effect = get_snapshot
    return engine


REQUIRED_DECODE_SYMBOLS = ("decode_native_pcm",)
REQUIRED_PROVIDER_SYMBOLS = ("SequencerPcmProvider",)

FORBIDDEN_PROVIDER_SURFACE_TOKENS = (
    "TransportAwarePreview",
    "WorkbenchPreviewPlayer",
    "workbench_qml",
    "PySide6",
    "QtQuick",
    "Screen2",
    "arrangement",
    "piano_roll",
    "mixer",
    "steal_voice",
    "voice_steal",
)

ENGINE_SR = 48_000
SOURCE_SR = 44_100


def _decode_or_fail():
    try:
        return importlib.import_module("src.native_pcm_decode")
    except ModuleNotFoundError as exc:
        if exc.name in {"src.native_pcm_decode", "native_pcm_decode"} or (
            exc.name is not None and exc.name.endswith("native_pcm_decode")
        ):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.native_pcm_decode "
                "(shared offline PCM decode not implemented — expected RED until "
                "IMPLEMENTATION_GATE for #676)"
            )
        raise


def _provider_module_or_fail():
    try:
        return importlib.import_module("src.sequencer_pcm")
    except ModuleNotFoundError as exc:
        if exc.name in {"src.sequencer_pcm", "sequencer_pcm"} or (
            exc.name is not None and exc.name.endswith("sequencer_pcm")
        ):
            pytest.fail(
                "MISSING_PRODUCTION_SURFACE: src.sequencer_pcm "
                "(SequencerPcmProvider not implemented — expected RED until "
                "IMPLEMENTATION_GATE for #676)"
            )
        raise


def _require_symbol(module, name: str):
    value = getattr(module, name, None)
    if value is None:
        pytest.fail(f"MISSING_PRODUCTION_SURFACE: {module.__name__}.{name}")
    return value


def _write_mono_wav(path: Path, *, sr: int = SOURCE_SR, frames: int = 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, 1.0, frames, endpoint=False, dtype=np.float32)
    wave = (0.25 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
    sf.write(str(path), wave, sr, subtype="PCM_16")
    return path


def _write_stereo_wav(path: Path, *, sr: int = SOURCE_SR, frames: int = 64) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.linspace(0.0, 1.0, frames, endpoint=False, dtype=np.float32)
    left = (0.25 * np.sin(2.0 * np.pi * 220.0 * t)).astype(np.float32)
    right = (0.25 * np.sin(2.0 * np.pi * 330.0 * t)).astype(np.float32)
    sf.write(str(path), np.column_stack((left, right)), sr, subtype="PCM_16")
    return path


def _write_quad_wav(path: Path, *, sr: int = SOURCE_SR, frames: int = 32) -> Path:
    """Four-channel fixture — shared decode must collapse to mono/stereo safely."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.full((frames, 4), 0.1, dtype=np.float32)
    sf.write(str(path), data, sr, subtype="PCM_16")
    return path


def _synthetic_row(path: Path) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=path.name,
        relative_path=path.name,
        path=str(path),
        bpm=120.0,
        key="Cmaj",
        key_conf=0.9,
        loudness=-18.0,
        brightness=2400.0,
        sample_class="oneshot",
        pred_type="Kick",
        status="ok",
        details={"source": "synthetic"},
    )


def _rack_state_with_single_kick_step(rack, live_kit: LiveKitState, *, step: int = 0):
    """DEFAULT_ON (#677) seeds 16 steps; keep only one active for PCM seam fixtures."""
    state = rack.build_channel_rack_state(live_kit)
    for index in range(state.step_count):
        if index != step:
            state = rack.toggle_step(state, "ch_kick", index)
    return state


def _voice_id_allocator(start: int = 1) -> Callable[[], int]:
    state = {"v": int(start)}

    def allocate() -> int:
        value = state["v"]
        state["v"] = value + 1
        return value

    return allocate


def _assert_valid_pcm(pcm: PcmBufferConfig) -> None:
    assert isinstance(pcm, PcmBufferConfig)
    assert pcm.channels in (1, 2)
    samples = np.asarray(pcm.samples, dtype=np.float32)
    assert samples.size > 0
    assert np.isfinite(samples).all()
    flat = samples.reshape(-1)
    assert flat.size % int(pcm.channels) == 0


# --- Public surface ---------------------------------------------------------


def test_shared_decode_public_surface_exists():
    module = _decode_or_fail()
    for name in REQUIRED_DECODE_SYMBOLS:
        _require_symbol(module, name)
    assert "decode_native_pcm" in getattr(module, "__all__", (name for name in REQUIRED_DECODE_SYMBOLS))


def test_sequencer_pcm_provider_public_surface_exists():
    module = _provider_module_or_fail()
    for name in REQUIRED_PROVIDER_SYMBOLS:
        _require_symbol(module, name)
    provider_cls = _require_symbol(module, "SequencerPcmProvider")
    assert callable(provider_cls)
    assert "SequencerPcmProvider" in getattr(
        module, "__all__", REQUIRED_PROVIDER_SYMBOLS
    )


# --- Shared decode (offline, reusable) --------------------------------------


def test_decode_native_pcm_mono_returns_finite_float32(tmp_path: Path):
    decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
    wav = _write_mono_wav(tmp_path / "mono.wav", sr=ENGINE_SR, frames=48)
    pcm, channels = decode(wav, sample_rate=ENGINE_SR, start_ms=0)
    assert channels == 1
    arr = np.asarray(pcm, dtype=np.float32)
    assert arr.ndim == 2
    assert arr.shape[1] == 1
    assert arr.size > 0
    assert np.isfinite(arr).all()


def test_decode_native_pcm_stereo_preserves_two_channels(tmp_path: Path):
    decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
    wav = _write_stereo_wav(tmp_path / "stereo.wav", sr=ENGINE_SR, frames=48)
    pcm, channels = decode(wav, sample_rate=ENGINE_SR, start_ms=0)
    assert channels == 2
    arr = np.asarray(pcm, dtype=np.float32)
    assert arr.ndim == 2
    assert arr.shape[1] == 2
    assert np.isfinite(arr).all()


def test_decode_native_pcm_resamples_to_engine_rate(tmp_path: Path):
    decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
    wav = _write_mono_wav(tmp_path / "src.wav", sr=SOURCE_SR, frames=SOURCE_SR // 10)
    pcm, channels = decode(wav, sample_rate=ENGINE_SR, start_ms=0)
    assert channels == 1
    arr = np.asarray(pcm, dtype=np.float32)
    # ~0.1s at 48k ≈ 4800 frames (±resample padding)
    assert 4000 <= arr.shape[0] <= 5600


def test_decode_native_pcm_gt2_channels_collapses_safely(tmp_path: Path):
    decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
    wav = _write_quad_wav(tmp_path / "quad.wav", sr=ENGINE_SR)
    pcm, channels = decode(wav, sample_rate=ENGINE_SR, start_ms=0)
    assert channels in (1, 2)
    arr = np.asarray(pcm, dtype=np.float32)
    assert arr.ndim == 2
    assert arr.shape[1] == channels
    assert np.isfinite(arr).all()


def test_audition_load_native_pcm_delegates_to_shared_decode():
    """Reuse without coupling: audition calls shared decode; does not own cache."""
    transport_ui = importlib.import_module("src.workbench_transport_ui")
    source = Path(inspect.getsourcefile(transport_ui) or "").read_text(encoding="utf-8")
    assert "decode_native_pcm" in source
    assert "native_pcm_decode" in source
    load_fn = getattr(transport_ui, "_load_native_pcm", None)
    assert callable(load_fn)
    load_src = inspect.getsource(load_fn)
    assert "decode_native_pcm" in load_src


def test_shared_decode_module_has_no_audition_or_qml_coupling():
    module = _decode_or_fail()
    source = Path(inspect.getsourcefile(module) or "").read_text(encoding="utf-8")
    for token in (
        "TransportAwarePreview",
        "WorkbenchPreviewPlayer",
        "workbench_qml",
        "PySide6",
        "sequencer_pcm",
        "SequencerPcmProvider",
    ):
        assert token not in source, f"shared decode must stay free of {token}"


# --- Provider cache + fail-soft ---------------------------------------------


def test_provider_cache_miss_decode_returns_pcm_buffer_config(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    wav = _write_mono_wav(tmp_path / "kick.wav", sr=ENGINE_SR)
    decode_calls: list[str] = []

    def counting_decode(path, *, sample_rate: int, start_ms: int = 0):
        decode_calls.append(str(path))
        decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
        return decode(path, sample_rate=sample_rate, start_ms=start_ms)

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=counting_decode)
    pcm = provider.pcm_for_path(str(wav))
    assert pcm is not None
    _assert_valid_pcm(pcm)
    assert len(decode_calls) == 1


def test_provider_second_access_is_cache_hit_no_redecode(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    wav = _write_mono_wav(tmp_path / "hat.wav", sr=ENGINE_SR)
    decode_calls: list[str] = []

    def counting_decode(path, *, sample_rate: int, start_ms: int = 0):
        decode_calls.append(str(path))
        decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
        return decode(path, sample_rate=sample_rate, start_ms=start_ms)

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=counting_decode)
    first = provider(str(wav))
    second = provider(str(wav))
    assert first is not None and second is not None
    assert len(decode_calls) == 1
    assert first is second or (
        np.array_equal(np.asarray(first.samples), np.asarray(second.samples))
        and first.channels == second.channels
    )


def test_provider_mono_and_stereo(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    mono = _write_mono_wav(tmp_path / "m.wav", sr=ENGINE_SR)
    stereo = _write_stereo_wav(tmp_path / "s.wav", sr=ENGINE_SR)
    provider = provider_cls(sample_rate=ENGINE_SR)
    mono_pcm = provider.pcm_for_path(str(mono))
    stereo_pcm = provider.pcm_for_path(str(stereo))
    assert mono_pcm is not None and mono_pcm.channels == 1
    assert stereo_pcm is not None and stereo_pcm.channels == 2
    _assert_valid_pcm(mono_pcm)
    _assert_valid_pcm(stereo_pcm)


def test_provider_resampling_matches_engine_sample_rate(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    wav = _write_mono_wav(tmp_path / "src.wav", sr=SOURCE_SR, frames=SOURCE_SR // 10)
    provider = provider_cls(sample_rate=ENGINE_SR)
    pcm = provider.pcm_for_path(str(wav))
    assert pcm is not None
    _assert_valid_pcm(pcm)
    frames = np.asarray(pcm.samples).reshape(-1, pcm.channels).shape[0]
    assert 4000 <= frames <= 5600


def test_provider_different_sample_rates_do_not_share_cache(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    wav = _write_mono_wav(tmp_path / "tone.wav", sr=SOURCE_SR, frames=2048)
    decode_calls: list[tuple[str, int]] = []

    def counting_decode(path, *, sample_rate: int, start_ms: int = 0):
        decode_calls.append((str(path), int(sample_rate)))
        decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
        return decode(path, sample_rate=sample_rate, start_ms=start_ms)

    p48 = provider_cls(sample_rate=48_000, decode_fn=counting_decode)
    p44 = provider_cls(sample_rate=44_100, decode_fn=counting_decode)
    a = p48.pcm_for_path(str(wav))
    b = p44.pcm_for_path(str(wav))
    assert a is not None and b is not None
    assert len(decode_calls) == 2
    assert {rate for _, rate in decode_calls} == {48_000, 44_100}


def test_provider_missing_file_fails_soft(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    provider = provider_cls(sample_rate=ENGINE_SR)
    assert provider.pcm_for_path(str(tmp_path / "missing.wav")) is None


def test_provider_decoder_error_fails_soft(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    bad = tmp_path / "corrupt.wav"
    bad.write_bytes(b"not-a-wav-file")
    provider = provider_cls(sample_rate=ENGINE_SR)
    assert provider.pcm_for_path(str(bad)) is None


def test_provider_empty_pcm_fails_soft_and_is_not_cached(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    calls = {"n": 0}

    def empty_decode(path, *, sample_rate: int, start_ms: int = 0):
        calls["n"] += 1
        return np.zeros((0, 1), dtype=np.float32), 1

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=empty_decode)
    path = str(tmp_path / "empty.wav")
    assert provider.pcm_for_path(path) is None
    assert provider.pcm_for_path(path) is None
    assert calls["n"] == 2, "failed/empty loads must not poison the cache"


def test_provider_non_finite_pcm_fails_soft_and_is_not_cached(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    calls = {"n": 0}

    def nan_decode(path, *, sample_rate: int, start_ms: int = 0):
        calls["n"] += 1
        return np.array([[np.nan], [0.1]], dtype=np.float32), 1

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=nan_decode)
    path = str(tmp_path / "nan.wav")
    assert provider.pcm_for_path(path) is None
    assert provider.pcm_for_path(path) is None
    assert calls["n"] == 2


def test_provider_unexpected_channel_count_fails_soft(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")

    def bad_channels_decode(path, *, sample_rate: int, start_ms: int = 0):
        return np.zeros((8, 3), dtype=np.float32), 3

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=bad_channels_decode)
    assert provider.pcm_for_path(str(tmp_path / "wide.wav")) is None


def test_provider_malformed_decoder_buffer_fails_soft(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")

    def ragged_decode(path, *, sample_rate: int, start_ms: int = 0):
        return [object(), object()], 1

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=ragged_decode)
    assert provider.pcm_for_path(str(tmp_path / "ragged.wav")) is None


def test_provider_failed_load_does_not_poison_later_success(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    target = tmp_path / "late.wav"
    provider = provider_cls(sample_rate=ENGINE_SR)
    assert provider.pcm_for_path(str(target)) is None
    _write_mono_wav(target, sr=ENGINE_SR)
    pcm = provider.pcm_for_path(str(target))
    assert pcm is not None
    _assert_valid_pcm(pcm)


def test_provider_lru_eviction_is_bounded(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    decode_calls: list[str] = []

    def counting_decode(path, *, sample_rate: int, start_ms: int = 0):
        decode_calls.append(Path(path).name)
        decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
        return decode(path, sample_rate=sample_rate, start_ms=start_ms)

    provider = provider_cls(
        sample_rate=ENGINE_SR, max_entries=2, decode_fn=counting_decode
    )
    a = _write_mono_wav(tmp_path / "a.wav", sr=ENGINE_SR)
    b = _write_mono_wav(tmp_path / "b.wav", sr=ENGINE_SR)
    c = _write_mono_wav(tmp_path / "c.wav", sr=ENGINE_SR)
    assert provider.pcm_for_path(str(a)) is not None
    assert provider.pcm_for_path(str(b)) is not None
    assert provider.pcm_for_path(str(c)) is not None
    decode_calls.clear()
    # a should have been evicted under LRU max_entries=2
    assert provider.pcm_for_path(str(a)) is not None
    assert "a.wav" in decode_calls


def test_provider_preserves_trailing_whitespace_in_sample_paths(tmp_path: Path):
    """Do not strip meaningful trailing spaces before decode / cache keying."""
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    seen: list[str] = []

    def capturing_decode(path, *, sample_rate: int, start_ms: int = 0):
        seen.append(str(path))
        return np.zeros((8, 1), dtype=np.float32), 1

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=capturing_decode)
    spaced = str(tmp_path / "kick.wav") + " "
    pcm = provider.pcm_for_path(spaced)
    assert pcm is not None
    _assert_valid_pcm(pcm)
    assert seen == [spaced]
    # All-whitespace remains fail-soft and never reaches decode.
    assert provider.pcm_for_path("   ") is None
    assert seen == [spaced]


def test_canonicalize_pcm_path_does_not_strip_before_resolve(monkeypatch):
    """Whitespace-bearing paths must not resolve via a stripped neighbor."""
    module = _provider_module_or_fail()
    canonicalize = _require_symbol(module, "canonicalize_pcm_path")
    seen: list[str] = []

    def fake_realpath(path):
        seen.append(str(path))
        return str(path)

    monkeypatch.setattr(module.os.path, "realpath", fake_realpath)

    def fake_stat(_path):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(module.os, "stat", fake_stat)
    result = canonicalize("/samples/kick.wav ")
    assert result.endswith(" ")
    assert seen == ["/samples/kick.wav "]


def test_canonicalize_pcm_path_uses_inode_for_existing_files(tmp_path: Path):
    module = _provider_module_or_fail()
    canonicalize = _require_symbol(module, "canonicalize_pcm_path")
    wav = _write_mono_wav(tmp_path / "Kick.wav", sr=ENGINE_SR)
    key_a = canonicalize(str(wav))
    key_b = canonicalize(str(tmp_path / "." / "Kick.wav"))
    assert key_a == key_b
    assert ":" in key_a  # dev:inode

    # Missing differently-cased neighbor stays a distinct string key (Linux-safe).
    missing = str(tmp_path / "does-not-exist-Kick.wav")
    missing_key = canonicalize(missing)
    assert ":" not in missing_key or missing_key == missing


def test_provider_symlink_loop_canonicalization_fails_soft(monkeypatch, tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    module = _provider_module_or_fail()

    def boom(_path):
        raise RuntimeError("Symlink loop from resolve")

    monkeypatch.setattr(module, "canonicalize_pcm_path", boom)
    provider = provider_cls(
        sample_rate=ENGINE_SR,
        decode_fn=lambda *a, **k: (_ for _ in ()).throw(AssertionError("decode")),
    )
    assert provider.pcm_for_path(str(tmp_path / "loop.wav")) is None


def test_provider_cache_key_canonicalizes_path_aliases(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    wav = _write_mono_wav(tmp_path / "tone.wav", sr=ENGINE_SR)
    decode_calls: list[str] = []

    def counting_decode(path, *, sample_rate: int, start_ms: int = 0):
        decode_calls.append(str(path))
        decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
        return decode(path, sample_rate=sample_rate, start_ms=start_ms)

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=counting_decode)
    absolute = str(wav.resolve())
    via_dot = str(tmp_path / "." / "tone.wav")
    first = provider.pcm_for_path(absolute)
    second = provider.pcm_for_path(via_dot)
    assert first is not None and second is not None
    assert len(decode_calls) == 1

    # Existing-file identity uses inode; casing aliases share one entry only when
    # the filesystem treats both spellings as the same existing file.
    decode_calls.clear()
    mixed = absolute.swapcase() if absolute != absolute.swapcase() else absolute
    if Path(mixed).exists():
        third = provider.pcm_for_path(mixed)
        assert third is not None
        assert len(decode_calls) == 0
    else:
        third = provider.pcm_for_path(mixed)
        assert third is None
        assert len(decode_calls) == 1


def test_canonicalize_symlink_loop_stays_fail_soft(monkeypatch, tmp_path: Path):
    """realpath/abspath RuntimeError (symlink loop) must stay fail-soft."""
    module = _provider_module_or_fail()
    canonicalize = _require_symbol(module, "canonicalize_pcm_path")
    provider_cls = _require_symbol(module, "SequencerPcmProvider")

    def boom_realpath(_path):
        raise RuntimeError("Symlink loop from realpath")

    def boom_abspath(_path):
        raise RuntimeError("Symlink loop from abspath")

    monkeypatch.setattr(module.os.path, "realpath", boom_realpath)
    monkeypatch.setattr(module.os.path, "abspath", boom_abspath)
    monkeypatch.setattr(module.os.path, "normpath", lambda p: p)
    monkeypatch.setattr(module.os.path, "normcase", lambda p: p)

    raw = str(tmp_path / "loop.wav")
    assert canonicalize(raw) == raw

    def ok_decode(path, *, sample_rate: int, start_ms: int = 0):
        return np.zeros((8, 1), dtype=np.float32), 1

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=ok_decode)
    assert provider.pcm_for_path(raw) is not None


# --- Sequencer + Channel Rack integration -----------------------------------


def test_schedule_pattern_once_uses_provider_pcm_for_path_contract(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    sequencer = importlib.import_module("src.sequencer_playback")
    schedule = sequencer.schedule_pattern_once
    ScheduledTrigger = sequencer.ScheduledTrigger

    wav = _write_mono_wav(tmp_path / "kick.wav", sr=ENGINE_SR)
    provider = provider_cls(sample_rate=ENGINE_SR)
    engine = MagicMock(name="native_engine")
    engine.create_voice.side_effect = lambda cfg: cfg.id
    planned = (
        ScheduledTrigger(
            channel_id="ch_kick",
            sample_path=str(wav),
            position=Fraction(0, 1),
            engine_frame=1000,
        ),
    )

    result = schedule(
        planned_triggers=planned,
        engine=engine,
        pcm_for_path=provider,
        allocate_voice_id=_voice_id_allocator(1),
    )
    assert result.scheduled_count == 1
    assert engine.create_voice.call_count == 1
    voice_cfg = engine.create_voice.call_args.args[0]
    assert voice_cfg.pcm_buffer is not None
    _assert_valid_pcm(voice_cfg.pcm_buffer)


def test_channel_rack_playback_reaches_production_provider(tmp_path: Path):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    rack = importlib.import_module("src.channel_rack")
    play = rack.play_channel_rack_once

    wav = _write_mono_wav(tmp_path / "kick_01.wav", sr=ENGINE_SR)
    live_kit = LiveKitState()
    live_kit.assign("Kick + Bass", "Kick", _synthetic_row(wav))
    state = _rack_state_with_single_kick_step(rack, live_kit, step=0)
    provider = provider_cls(sample_rate=ENGINE_SR)
    tempo_map = TempoMap(sample_rate=ENGINE_SR, bpm=120)
    engine = _lifecycle_mock_engine()

    result = play(
        state,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
        engine=engine,
        lookahead_frames=4800,
        pcm_for_path=provider,
        allocate_voice_id=_voice_id_allocator(10),
    )
    assert result.scheduled_count == 1
    assert engine.create_voice.call_count == 1


def test_play_channel_rack_once_requires_long_lived_pcm_injector(tmp_path: Path):
    """P1: no ephemeral provider — callers must pass pcm_provider or pcm_for_path."""
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    rack = importlib.import_module("src.channel_rack")
    play = rack.play_channel_rack_once
    sig = inspect.signature(play)
    assert sig.parameters["pcm_for_path"].default is None
    assert "pcm_provider" in sig.parameters
    assert sig.parameters["pcm_provider"].default is None
    assert "lookahead_frames" in sig.parameters

    wav = _write_mono_wav(tmp_path / "kick_01.wav", sr=ENGINE_SR)
    live_kit = LiveKitState()
    live_kit.assign("Kick + Bass", "Kick", _synthetic_row(wav))
    state = _rack_state_with_single_kick_step(rack, live_kit, step=0)
    tempo_map = TempoMap(sample_rate=ENGINE_SR, bpm=120)
    engine = _lifecycle_mock_engine()

    with pytest.raises(ValueError, match="pcm_provider or pcm_for_path"):
        play(
            state,
            tempo_map=tempo_map,
            pattern_start_quarter=Fraction(0, 1),
            pattern_start_engine_frame=0,
            engine=engine,
            lookahead_frames=4800,
            allocate_voice_id=_voice_id_allocator(1),
        )

    provider = provider_cls(sample_rate=ENGINE_SR)
    result = play(
        state,
        tempo_map=tempo_map,
        pattern_start_quarter=Fraction(0, 1),
        pattern_start_engine_frame=0,
        engine=engine,
        lookahead_frames=4800,
        pcm_provider=provider,
        allocate_voice_id=_voice_id_allocator(1),
    )
    assert result.scheduled_count == 1


def test_play_channel_rack_once_rejects_mismatched_provider_sample_rate(
    tmp_path: Path,
):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    rack = importlib.import_module("src.channel_rack")
    play = rack.play_channel_rack_once

    wav = _write_mono_wav(tmp_path / "kick_01.wav", sr=ENGINE_SR)
    live_kit = LiveKitState()
    live_kit.assign("Kick + Bass", "Kick", _synthetic_row(wav))
    state = _rack_state_with_single_kick_step(rack, live_kit, step=0)
    tempo_map = TempoMap(sample_rate=48_000, bpm=120)
    provider = provider_cls(sample_rate=44_100)
    engine = MagicMock(name="native_engine")

    with pytest.raises(ValueError, match="sample_rate must match"):
        play(
            state,
            tempo_map=tempo_map,
            pattern_start_quarter=Fraction(0, 1),
            pattern_start_engine_frame=0,
            engine=engine,
            lookahead_frames=4800,
            pcm_provider=provider,
            allocate_voice_id=_voice_id_allocator(1),
        )

    with pytest.raises(ValueError, match="sample_rate must match"):
        play(
            state,
            tempo_map=tempo_map,
            pattern_start_quarter=Fraction(0, 1),
            pattern_start_engine_frame=0,
            engine=engine,
            lookahead_frames=4800,
            pcm_for_path=provider.pcm_for_path,
            allocate_voice_id=_voice_id_allocator(1),
        )


def test_channel_rack_reuses_long_lived_pcm_provider_across_passes(tmp_path: Path):
    """Production callers must keep SequencerPcmProvider at session/rack lifetime."""
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    rack = importlib.import_module("src.channel_rack")
    play = rack.play_channel_rack_once
    warm = getattr(rack, "warm_channel_rack_pcm", None)
    assert callable(warm), "MISSING_PRODUCTION_SURFACE: warm_channel_rack_pcm"

    wav = _write_mono_wav(tmp_path / "kick_01.wav", sr=ENGINE_SR)
    live_kit = LiveKitState()
    live_kit.assign("Kick + Bass", "Kick", _synthetic_row(wav))
    state = _rack_state_with_single_kick_step(rack, live_kit, step=0)
    tempo_map = TempoMap(sample_rate=ENGINE_SR, bpm=120)
    decode_calls: list[str] = []

    def counting_decode(path, *, sample_rate: int, start_ms: int = 0):
        decode_calls.append(str(path))
        decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
        return decode(path, sample_rate=sample_rate, start_ms=start_ms)

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=counting_decode)
    failed = warm(state, provider)
    assert failed == ()
    assert len(decode_calls) == 1

    engine = _lifecycle_mock_engine()
    for _ in range(2):
        result = play(
            state,
            tempo_map=tempo_map,
            pattern_start_quarter=Fraction(0, 1),
            pattern_start_engine_frame=0,
            engine=engine,
            lookahead_frames=4800,
            pcm_provider=provider,
            allocate_voice_id=_voice_id_allocator(1),
        )
        assert result.scheduled_count == 1
    assert len(decode_calls) == 1, "long-lived pcm_provider must cache across passes"


def test_warm_channel_rack_pcm_reports_failed_paths_and_counts_identities(
    tmp_path: Path,
):
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    rack = importlib.import_module("src.channel_rack")
    warm = rack.warm_channel_rack_pcm
    build = rack.build_channel_rack_state

    wav = _write_mono_wav(tmp_path / "kick_01.wav", sr=ENGINE_SR)
    live_kit = LiveKitState()
    live_kit.assign("Kick + Bass", "Kick", _synthetic_row(wav))
    state = build(live_kit)
    # Alias via "." should not double-count capacity.
    alias = str(tmp_path / "." / "kick_01.wav")
    state = rack.add_user_channel(state, sample_path=alias)
    provider = provider_cls(sample_rate=ENGINE_SR, max_entries=1)
    assert warm(state, provider) == ()

    missing_state = rack.add_user_channel(
        build(LiveKitState()),
        sample_path=str(tmp_path / "missing.wav"),
    )
    provider2 = provider_cls(sample_rate=ENGINE_SR, max_entries=2)
    failed = warm(missing_state, provider2)
    assert failed == (str(tmp_path / "missing.wav"),)


def test_provider_has_no_qml_or_preview_dependency():
    module = _provider_module_or_fail()
    source_path = Path(inspect.getsourcefile(module) or "")
    assert source_path.is_file()
    source = source_path.read_text(encoding="utf-8")
    for token in FORBIDDEN_PROVIDER_SURFACE_TOKENS:
        assert token not in source, f"forbidden provider surface token: {token}"
    tree = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
            if node.module.startswith("."):
                imports.add(node.module)
    assert "workbench_qml" not in imports
    assert "workbench_transport_ui" not in source


def test_no_decode_inside_sequencer_scheduler_module():
    sequencer = importlib.import_module("src.sequencer_playback")
    source = Path(inspect.getsourcefile(sequencer) or "").read_text(encoding="utf-8")
    for token in ("soundfile", "librosa", "sf.read", "decode_native_pcm", "wavfile"):
        assert token not in source, f"scheduler must not decode audio ({token})"


def test_provider_decode_happens_outside_native_create_voice(tmp_path: Path):
    """Decode must complete before engine.create_voice — not inside a callback."""
    provider_cls = _require_symbol(_provider_module_or_fail(), "SequencerPcmProvider")
    sequencer = importlib.import_module("src.sequencer_playback")
    wav = _write_mono_wav(tmp_path / "kick.wav", sr=ENGINE_SR)
    timeline: list[str] = []

    def tracing_decode(path, *, sample_rate: int, start_ms: int = 0):
        timeline.append("decode")
        decode = _require_symbol(_decode_or_fail(), "decode_native_pcm")
        return decode(path, sample_rate=sample_rate, start_ms=start_ms)

    provider = provider_cls(sample_rate=ENGINE_SR, decode_fn=tracing_decode)

    class Engine:
        def create_voice(self, config):
            timeline.append("create_voice")
            assert config.pcm_buffer is not None
            _assert_valid_pcm(config.pcm_buffer)
            return config.id

        def schedule_voice_start(self, voice_id, engine_frame):
            timeline.append("schedule")

    planned = (
        sequencer.ScheduledTrigger(
            channel_id="ch_kick",
            sample_path=str(wav),
            position=Fraction(0, 1),
            engine_frame=0,
        ),
    )
    sequencer.schedule_pattern_once(
        planned_triggers=planned,
        engine=Engine(),
        pcm_for_path=provider,
        allocate_voice_id=lambda: 1,
    )
    assert timeline == ["decode", "create_voice", "schedule"]
