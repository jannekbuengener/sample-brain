"""Tests for the #374 live-performance deconstruction profile.

Synthetic signals only (no committed audio). Validates the compact layout
contract: real producer-group sources, 4-bar default loops, truthful
no_result, full-length arrangement tracks, config-driven output, and the
absence of master fallbacks / private paths.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from src.canon_audio import AudioTimebase
from src.live_profile import (
    ALLOWED_LOOP_BARS,
    ELEM_DRUMS_PRESENT,
    ELEM_DRUMS_REDUCED,
    ELEM_KICK_BASS,
    ELEM_MELODIC,
    ELEM_OTHER,
    ELEM_VOCALS,
    REASON_NO_DISTINCT_REDUCED,
    REASON_NO_SOURCE,
    REASON_SILENT_LOOP_WINDOW,
    LiveLayoutConfig,
    build_live_layout,
    find_live_layout,
    read_live_layout,
    write_live_layout,
)
from src.producer_groups import ProducerGroup, ProducerGroupParams, derive_producer_groups


# ---------------------------------------------------------------------------
# Synthetic fixtures (deterministic, no randomness)
# ---------------------------------------------------------------------------


def _make_kick_transients(sr: int, n: int, bpm: float = 120.0, hz: float = 60.0):
    out = np.zeros(n, dtype=np.float32)
    interval = int(sr * 60.0 / bpm)
    decay = int(sr * 0.15)
    t = np.linspace(0.0, 0.15, decay, dtype=np.float32)
    env = np.exp(-t * 25.0).astype(np.float32)
    kick = (0.9 * np.sin(2.0 * np.pi * hz * t) * env).astype(np.float32)
    pos = 0
    while pos + decay <= n:
        out[pos : pos + decay] += kick
        pos += interval
    return out


def _make_hat_noise(sr: int, n: int, bpm: float = 120.0, amp: float = 0.2):
    rng = np.random.default_rng(0)
    noise = (rng.standard_normal(n) * amp).astype(np.float32)
    interval = int(sr * 60.0 / bpm / 4)
    gated = np.zeros(n, dtype=np.float32)
    pos = interval // 2
    while pos + interval <= n:
        gated[pos : pos + interval] = noise[pos : pos + interval]
        pos += interval
    return gated


def _make_drums(sr: int, n: int) -> np.ndarray:
    return (_make_kick_transients(sr, n) + _make_hat_noise(sr, n)).astype(np.float32)


def _make_bass(sr: int, n: int) -> np.ndarray:
    out = np.zeros(n, dtype=np.float32)
    notes = [80.0, 100.0, 120.0, 90.0]
    seg = n // len(notes)
    t = np.arange(seg, dtype=np.float32) / sr
    for i, f in enumerate(notes):
        start = i * seg
        env = np.exp(-t * 1.5).astype(np.float32)
        out[start : start + seg] = (0.4 * np.sin(2.0 * np.pi * f * t) * env).astype(np.float32)
    return out


def _make_vocals(sr: int, n: int) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / sr
    env = (0.5 + 0.5 * np.sin(2.0 * np.pi * 0.5 * t)).astype(np.float32)
    return (0.5 * np.sin(2.0 * np.pi * 300.0 * t) * env).astype(np.float32)


def _make_other(sr: int, n: int) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / sr
    return (
        0.25 * np.sin(2.0 * np.pi * 220.0 * t)
        + 0.2 * np.sin(2.0 * np.pi * 277.0 * t)
        + 0.2 * np.sin(2.0 * np.pi * 330.0 * t)
    ).astype(np.float32)


def _make_flat_drums(sr: int, n: int) -> np.ndarray:
    # Constant-amplitude tone => effectively flat per-bar energy (no distinct
    # reduced drum state can be evidenced).
    t = np.arange(n, dtype=np.float32) / sr
    return (0.3 * np.sin(2.0 * np.pi * 90.0 * t)).astype(np.float32)


SR = 44100
BARS = 10
N = BARS * SR  # 10 seconds -> 10 bars at 1 bar/sec


def _full_stems(sr: int = SR, n: int = N) -> dict[str, np.ndarray]:
    return {
        "drums": _make_drums(sr, n),
        "bass": _make_bass(sr, n),
        "vocals": _make_vocals(sr, n),
        "other": _make_other(sr, n),
    }


def _bars(sr: int = SR, n_bars: int = BARS) -> list[int]:
    return [i * sr for i in range(n_bars + 1)]


def _pg(stems, sr: int = SR):
    return derive_producer_groups(
        stems, params=ProducerGroupParams(sample_rate=sr), track_ref="/source/working_audio"
    )


def _default_config(**kw) -> LiveLayoutConfig:
    return LiveLayoutConfig(**kw)


# ---------------------------------------------------------------------------
# 1. kick_bass uses the real producer-group audio source
# ---------------------------------------------------------------------------


def test_kick_bass_uses_real_producer_group_source(tmp_path: Path):
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(), bars=_bars(), pack_root=tmp_path, sample_rate=SR
    )
    kb = next(e for e in layout.playable_loops if e.element == ELEM_KICK_BASS)
    assert kb.status == "ok"
    assert kb.source_kind == "producer_group"
    assert kb.source_ref == "producergroup_kick_bass"
    assert kb.technical_stems == ("drums", "bass")

    # The emitted audio must equal the real #268 kick_bass derivation.
    import soundfile as sf

    data, sr = sf.read(str(tmp_path / kb.audio_ref))
    assert sr == SR
    # The emitted loop is the bar-aligned 4-bar slice of the real kick_bass
    # producer-group audio (not a master low-frequency split).
    assert data.shape[0] == 4 * SR
    # PCM_16 clips peaks that exceed [-1, 1]; compare the clipped signals.
    expected = np.clip(groups["kick_bass"].audio[0 : 4 * SR], -1.0, 1.0)
    got = np.clip(data, -1.0, 1.0)
    assert np.allclose(got, expected, atol=1e-2)


# ---------------------------------------------------------------------------
# 2. drums default 4 bars
# ---------------------------------------------------------------------------


def test_drums_default_four_bars():
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(), bars=_bars(), pack_root=None, sample_rate=SR
    )
    drums = next(e for e in layout.playable_loops if e.element == ELEM_DRUMS_PRESENT)
    assert drums.status == "ok"
    assert drums.role == "playable_loop"
    assert drums.bars == 4
    assert drums.source_kind == "producer_group"
    assert drums.source_ref == "producergroup_drums"


# ---------------------------------------------------------------------------
# 3. no 16-bar default selection
# ---------------------------------------------------------------------------


def test_no_sixteen_bar_default():
    # Config validation rejects 16-bar requests outright.
    with pytest.raises(ValueError):
        LiveLayoutConfig(default_loop_bars=16)

    assert 16 not in ALLOWED_LOOP_BARS

    # And a normal build never yields a 16-bar loop even with many bars.
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(), bars=_bars(n_bars=40), pack_root=None, sample_rate=SR
    )
    for e in layout.playable_loops:
        assert e.bars in (4, 8)
        assert e.bars != 16


# ---------------------------------------------------------------------------
# 4. optional second drum state can be no_result
# ---------------------------------------------------------------------------


def test_optional_second_drum_state_can_be_no_result():
    stems = {"drums": _make_flat_drums(SR, N), "bass": _make_bass(SR, N)}
    groups = _pg(stems)
    # drums_states=2 but the source has no distinct reduced region.
    layout = build_live_layout(
        groups, stems, _default_config(drums_states=2),
        bars=_bars(), pack_root=None, sample_rate=SR,
    )
    present = next(e for e in layout.playable_loops if e.element == ELEM_DRUMS_PRESENT)
    reduced = next(e for e in layout.playable_loops if e.element == ELEM_DRUMS_REDUCED)
    # present loop is still ok from the (near-silent) drums group.
    assert present.element == ELEM_DRUMS_PRESENT
    assert reduced.status == "no_result"
    assert reduced.reason_code == REASON_NO_DISTINCT_REDUCED
    assert reduced.audio_ref is None
    # The reduced state is NOT a duplicate of present.
    assert reduced.element != present.element


# ---------------------------------------------------------------------------
# 5. full-length vocals stay full-length
# ---------------------------------------------------------------------------


def test_full_length_vocals_stay_full_length(tmp_path: Path):
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(), bars=_bars(), pack_root=tmp_path, sample_rate=SR
    )
    vocals = next(e for e in layout.full_length_tracks if e.element == ELEM_VOCALS)
    assert vocals.status == "ok"
    assert vocals.role == "full_length_track"
    assert vocals.full_length is True
    assert vocals.bars is None
    assert vocals.source_kind in ("producer_group", "stem")

    import soundfile as sf

    data, _ = sf.read(str(tmp_path / vocals.audio_ref))
    # Not chopped into a 4-bar loop; it spans the whole track.
    assert data.shape[0] == N


# ---------------------------------------------------------------------------
# 6. full-length melodic / other stay full-length
# ---------------------------------------------------------------------------


def test_full_length_melodic_and_other(tmp_path: Path):
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(other_full=True),
        bars=_bars(), pack_root=tmp_path, sample_rate=SR,
    )
    melodic = next(e for e in layout.full_length_tracks if e.element == ELEM_MELODIC)
    other = next(e for e in layout.full_length_tracks if e.element == ELEM_OTHER)
    for e in (melodic, other):
        assert e.status == "ok"
        assert e.full_length is True
        assert e.bars is None
    # melodic comes from the producer-group HPSS split, other from the raw stem;
    # they are NOT duplicates of each other.
    assert melodic.source_kind == "producer_group"
    assert other.source_kind == "stem"
    assert melodic.source_ref != other.source_ref


# ---------------------------------------------------------------------------
# 7. layout config affects output
# ---------------------------------------------------------------------------


def test_layout_config_affects_output():
    stems = _full_stems()
    groups = _pg(stems)

    cfg_min = _default_config(kick_bass=False, drums_states=1, vocals_full=False,
                              melodic_full=False, fx_full=False, other_full=False)
    cfg_max = _default_config(drums_states=2, other_full=True)

    lo = build_live_layout(groups, stems, cfg_min, bars=_bars(), sample_rate=SR)
    hi = build_live_layout(groups, stems, cfg_max, bars=_bars(), sample_rate=SR)

    lo_keys = {e.element for e in lo.all_elements}
    hi_keys = {e.element for e in hi.all_elements}
    assert lo_keys != hi_keys
    assert ELEM_KICK_BASS not in lo_keys
    assert ELEM_KICK_BASS in hi_keys
    assert ELEM_DRUMS_REDUCED in hi_keys
    assert ELEM_OTHER in hi_keys


# ---------------------------------------------------------------------------
# 8. output stays compact / no candidate flood
# ---------------------------------------------------------------------------


def test_output_compact_no_candidate_flood():
    stems = _full_stems()
    groups = _pg(stems)
    # Default config: only the explicitly requested elements are emitted.
    cfg = _default_config(other_full=True)
    layout = build_live_layout(groups, stems, cfg, bars=_bars(), sample_rate=SR)
    expected = 1 + cfg.drums_states + sum([
        cfg.vocals_full, cfg.melodic_full, cfg.fx_full, cfg.other_full
    ])
    assert len(layout.all_elements) == expected
    # Exactly one playable kick_bass, never a flood of kick variants.
    assert sum(1 for e in layout.playable_loops if e.element == ELEM_KICK_BASS) == 1


# ---------------------------------------------------------------------------
# 9. no master fallbacks for missing stem/group sources
# ---------------------------------------------------------------------------


def test_no_master_fallback_for_missing_sources():
    # No stems and no producer groups at all.
    layout = build_live_layout(
        {}, {}, _default_config(other_full=True), bars=_bars(), sample_rate=SR
    )
    for e in layout.all_elements:
        assert e.status == "no_result"
        # Never silently rewired to a master source.
        assert e.source_kind != "master"
        if e.source_kind is not None:
            assert e.source_ref != "master"
    # And specifically no usable kick_bass / drums were fabricated.
    kb = next(e for e in layout.playable_loops if e.element == ELEM_KICK_BASS)
    assert kb.reason_code == REASON_NO_SOURCE


def test_missing_bass_makes_kick_bass_no_result_not_master():
    stems = {"drums": _make_drums(SR, N)}  # no bass -> no kick_bass group
    groups = _pg(stems)
    layout = build_live_layout(groups, stems, _default_config(), bars=_bars(), sample_rate=SR)
    kb = next(e for e in layout.playable_loops if e.element == ELEM_KICK_BASS)
    assert kb.status == "no_result"
    assert kb.source_kind != "master"


# ---------------------------------------------------------------------------
# 10. no private / local paths in the repository output
# ---------------------------------------------------------------------------


def test_no_private_paths_in_layout_manifest(tmp_path: Path):
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(other_full=True),
        bars=_bars(), pack_root=tmp_path, sample_rate=SR,
    )
    ref = write_live_layout(layout, tmp_path)
    assert ref == "live/live_layout.json"
    data = read_live_layout(tmp_path / ref)

    import json

    raw = json.dumps(data)
    # No drive letters, no absolute roots, no parent traversal, no file://.
    assert "file://" not in raw
    assert ".." not in raw
    for bad in (":\\", ":/"):
        assert bad not in raw

    for e in data["playable_loops"] + data["full_length_tracks"]:
        ar = e.get("audio_ref")
        if ar is not None:
            assert not ar.startswith("/")
            assert ":" not in ar
            assert ".." not in ar
        # Provenance never leaks an absolute source path.
        sk = e.get("source_kind")
        if sk is not None:
            assert sk in ("producer_group", "stem")


def test_find_live_layout_reads_back(tmp_path: Path):
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(), bars=_bars(), pack_root=tmp_path, sample_rate=SR
    )
    write_live_layout(layout, tmp_path)
    found = find_live_layout(tmp_path)
    assert found is not None
    assert found["document_type"] == "sample_brain.live_layout"
    # no_result elements are surfaced explicitly in the manifest.
    assert "no_result_elements" in found


# ---------------------------------------------------------------------------
# Integration: live layout independent of a failed/missing arrangement step
# ---------------------------------------------------------------------------


def test_live_layout_without_arrangement_but_with_stems(tmp_path: Path):
    from src.deconstruct import StepContext, _default_assets_adapter
    from src.live_profile import LiveLayoutConfig

    stems_payload = {
        "stems": [
            {"stem_kind": "drums", "audio": _make_drums(SR, N)},
            {"stem_kind": "bass", "audio": _make_bass(SR, N)},
            {"stem_kind": "vocals", "audio": _make_vocals(SR, N)},
            {"stem_kind": "other", "audio": _make_other(SR, N)},
        ],
        "track_ref": "track_abc",
    }
    # No arrangement result at all (step failed / unavailable upstream).
    ctx = StepContext(
        track_path=tmp_path / "ignored.wav",
        pack_root=tmp_path,
        bpm_normalization="none",
        beat_backend="auto",
        artifacts={"stems": stems_payload, "arrangement": None},
        live_profile_config=LiveLayoutConfig(),
    )
    result, payload = _default_assets_adapter(ctx)

    # The assets step still completes via the live layout output.
    assert result.status == "ok"
    assert "live/live_layout.json" in result.output_refs

    layout = read_live_layout(tmp_path / "live" / "live_layout.json")

    # Full-length anchor tracks are built directly from stems (no arrangement).
    fl = {e["element"]: e for e in layout["full_length_tracks"]}
    assert fl["vocals"]["status"] == "ok"
    assert fl["melodic"]["status"] == "ok"
    assert fl["fx"]["status"] == "ok"
    assert fl["vocals"]["full_length"] is True
    # Full-length tracks carry no loop bar count.
    assert "bars" not in fl["vocals"]

    # Playable loops cannot be sliced without a valid bar/beat grid: they are
    # reported truthfully as no_result, never an invented 4-bar region.
    pl = {e["element"]: e for e in layout["playable_loops"]}
    assert pl["kick_bass"]["status"] == "no_result"
    assert pl["drums_present"]["status"] == "no_result"
    assert pl["kick_bass"]["reason_code"] is not None

    # No element was silently rewired to a master fallback.
    for e in layout["playable_loops"] + layout["full_length_tracks"]:
        assert e.get("source_kind") != "master"


# ---------------------------------------------------------------------------
# #501 — silent drums_present must never be status=ok
# ---------------------------------------------------------------------------


def _make_drums_silent_then_active(sr: int, n: int, silent_bars: int = 4) -> np.ndarray:
    """First ``silent_bars`` seconds all-zero; remaining bars have drum signal."""
    out = np.zeros(n, dtype=np.float32)
    active = _make_drums(sr, n)
    cut = min(n, silent_bars * sr)
    out[cut:] = active[cut:]
    return out


def test_drums_present_skips_silent_first_window_for_audible_later(tmp_path: Path):
    """Silent first 4 bars + later signal -> audible window, status=ok, non-silent WAV."""
    stems = {
        "drums": _make_drums_silent_then_active(SR, N, silent_bars=4),
        "bass": _make_bass(SR, N),
        "vocals": _make_vocals(SR, N),
        "other": _make_other(SR, N),
    }
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(drums_states=1),
        bars=_bars(), pack_root=tmp_path, sample_rate=SR,
    )
    drums = next(e for e in layout.playable_loops if e.element == ELEM_DRUMS_PRESENT)
    assert drums.status == "ok"
    assert drums.bars == 4
    assert drums.audio_ref == "live/drums_present.wav"
    assert drums.reason_code is None

    import soundfile as sf

    data, sr = sf.read(str(tmp_path / drums.audio_ref))
    assert sr == SR
    assert data.shape[0] == 4 * SR
    assert float(np.max(np.abs(data))) > 0.0
    # Must not be the silent first window.
    assert not np.allclose(data, 0.0)


def test_drums_present_all_silent_group_is_truthful_no_result(tmp_path: Path):
    """All-zero drums group audio -> no_result, never status=ok / no WAV."""
    tb = AudioTimebase(sample_rate=SR, n_samples=N)
    silent = np.zeros(N, dtype=np.float32)
    # Bypass upstream min_rms filtering: a group that still carries zero PCM.
    groups = {
        "drums": ProducerGroup(
            group_kind="drums",
            group_id="pg_drums",
            group_ref="producergroup_drums",
            status="ok",
            timebase=tb,
            technical_stems=("drums",),
            audio=silent,
        )
    }
    stems = {"drums": silent}
    layout = build_live_layout(
        groups, stems, _default_config(drums_states=1),
        bars=_bars(), pack_root=tmp_path, sample_rate=SR,
    )
    drums = next(e for e in layout.playable_loops if e.element == ELEM_DRUMS_PRESENT)
    assert drums.status == "no_result"
    assert drums.reason_code == REASON_SILENT_LOOP_WINDOW
    assert drums.audio_ref is None
    assert not (tmp_path / "live" / "drums_present.wav").exists()

    payload = layout.as_dict()
    nr = payload.get("no_result_elements") or []
    # Contract may list element keys or element dicts; accept either.
    if nr and isinstance(nr[0], dict):
        assert any(
            e.get("element") == ELEM_DRUMS_PRESENT and e.get("status") == "no_result"
            for e in nr
        )
    else:
        assert ELEM_DRUMS_PRESENT in nr


def test_playable_loop_final_all_zero_never_ok(tmp_path: Path):
    """Final all-zero PCM must not be reported as ok even with a bar grid."""
    tb = AudioTimebase(sample_rate=SR, n_samples=N)
    silent = np.zeros(N, dtype=np.float32)
    groups = {
        "drums": ProducerGroup(
            group_kind="drums",
            group_id="pg_drums",
            group_ref="producergroup_drums",
            status="ok",
            timebase=tb,
            technical_stems=("drums",),
            audio=silent,
        )
    }
    layout = build_live_layout(
        groups, {}, _default_config(kick_bass=False, drums_states=1),
        bars=_bars(), pack_root=tmp_path, sample_rate=SR,
    )
    drums = next(e for e in layout.playable_loops if e.element == ELEM_DRUMS_PRESENT)
    assert drums.status != "ok"
    assert drums.reason_code == REASON_SILENT_LOOP_WINDOW
    assert drums.audio_ref is None


def test_drums_states_1_does_not_emit_drums_reduced():
    stems = _full_stems()
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(drums_states=1), bars=_bars(), sample_rate=SR
    )
    keys = {e.element for e in layout.playable_loops}
    assert ELEM_DRUMS_PRESENT in keys
    assert ELEM_DRUMS_REDUCED not in keys


def test_kick_bass_still_ok_when_drums_first_window_silent(tmp_path: Path):
    """#501 fix must not break kick_bass when early drums bars are silent."""
    stems = {
        "drums": _make_drums_silent_then_active(SR, N, silent_bars=4),
        "bass": _make_bass(SR, N),
    }
    groups = _pg(stems)
    layout = build_live_layout(
        groups, stems, _default_config(drums_states=1),
        bars=_bars(), pack_root=tmp_path, sample_rate=SR,
    )
    kb = next(e for e in layout.playable_loops if e.element == ELEM_KICK_BASS)
    drums = next(e for e in layout.playable_loops if e.element == ELEM_DRUMS_PRESENT)
    assert kb.status == "ok"
    assert drums.status == "ok"
    import soundfile as sf

    kb_data, _ = sf.read(str(tmp_path / kb.audio_ref))
    assert float(np.max(np.abs(kb_data))) > 0.0

