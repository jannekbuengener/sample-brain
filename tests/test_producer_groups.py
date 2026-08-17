"""Tests for the #268 producer-group derivation contract (deterministic).

Synthetic signals only; no audio binaries are committed. The fixtures follow
the ``tests/audio_fixtures.py`` philosophy: generated in-memory at runtime.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.canon_audio import AudioTimebase
from src.producer_groups import (
    ALLOWED_STATUS,
    GROUP_KINDS,
    REASON_MISSING_BASSLINE,
    REASON_MISSING_STEM,
    ProducerGroup,
    ProducerGroupParams,
    build_producer_group_manifest,
    derive_producer_groups,
    extract_kick_envelope,
    validate_producer_group_manifest,
)


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
    rng = np.random.default_rng(0)  # fixed seed -> deterministic
    noise = (rng.standard_normal(n) * amp).astype(np.float32)
    # Gate the noise to offbeat sixteenths so it is clearly non-kick percussion.
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
    # A clearly musical bassline: changing low notes, NOT a low-frequency rumble.
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
    pad = (
        0.25 * np.sin(2.0 * np.pi * 220.0 * t)
        + 0.2 * np.sin(2.0 * np.pi * 277.0 * t)
        + 0.2 * np.sin(2.0 * np.pi * 330.0 * t)
    ).astype(np.float32)
    # A little percussive fx sprinkle.
    rng = np.random.default_rng(7)
    fx = (rng.standard_normal(n) * 0.1).astype(np.float32)
    fx[: int(0.02 * sr)] *= 0.0
    return (pad + fx * 0.3).astype(np.float32)


def _full_stems(sr: int, n: int) -> dict[str, np.ndarray]:
    return {
        "drums": _make_drums(sr, n),
        "bass": _make_bass(sr, n),
        "vocals": _make_vocals(sr, n),
        "other": _make_other(sr, n),
    }


SR = 44100
N = 4 * SR  # 4 seconds


# ---------------------------------------------------------------------------
# Hard rule: kick_bass != drums + bass
# ---------------------------------------------------------------------------


def test_kick_bass_not_equal_drums_plus_bass():
    stems = _full_stems(SR, N)
    groups = derive_producer_groups(stems, params=ProducerGroupParams(sample_rate=SR))
    kb = groups["kick_bass"]
    assert kb.status == "ok"
    drums = stems["drums"]
    bass = stems["bass"]
    combined = (drums + bass).astype(np.float32)

    # The central contract: kick_bass is NOT simply drums + bass.
    assert not np.allclose(kb.audio, combined, atol=1e-3)
    assert float(np.max(np.abs(kb.audio - combined))) > 1e-2

    # And the drums-derived part must be the gated kick, not the full drums.
    _, kick_component, _ = extract_kick_envelope(drums, ProducerGroupParams(sample_rate=SR))
    # kick_bass = kick_component + bass  =>  kick_bass - bass == kick_component
    assert np.allclose(kb.audio - bass, kick_component, atol=1e-3)

    # The bassline component is the actual musical bass stem (not low-freq mud).
    bass_corr = float(np.corrcoef(kb.audio, bass)[0, 1])
    assert bass_corr > 0.5


# ---------------------------------------------------------------------------
# Low-frequency rumble must NOT become a bassline
# ---------------------------------------------------------------------------


def test_low_freq_rumble_not_bassline():
    # drums carries a low-frequency rumble + a kick; bass is silent/empty.
    drums = (_make_kick_transients(SR, N) + 0.5 * np.sin(
        2.0 * np.pi * 40.0 * (np.arange(N) / SR)
    ).astype(np.float32)).astype(np.float32)
    stems = {"drums": drums, "bass": np.zeros(N, dtype=np.float32)}
    groups = derive_producer_groups(stems, params=ProducerGroupParams(sample_rate=SR))

    kb = groups["kick_bass"]
    assert kb.status == "no_result"
    assert kb.reason_code == REASON_MISSING_BASSLINE
    assert kb.audio is None  # rumble is NOT promoted to a bassline

    # The kick envelope is still inspectable internally but is NOT emitted.
    gain, _, _ = extract_kick_envelope(drums, ProducerGroupParams(sample_rate=SR))
    assert float(np.max(gain)) > 0.5  # kick onsets detected
    assert kb.technical_stems == ("drums",)  # no bass counted as a component


# ---------------------------------------------------------------------------
# no_result is a valid, well-formed outcome
# ---------------------------------------------------------------------------


def test_no_result_when_source_missing():
    base = _full_stems(SR, N)

    # Missing bass -> kick_bass no_result (not drums + nothing).
    s = {k: v for k, v in base.items() if k != "bass"}
    g = derive_producer_groups(s, params=ProducerGroupParams(sample_rate=SR))
    assert g["kick_bass"].status == "no_result"
    assert g["kick_bass"].reason_code == REASON_MISSING_BASSLINE
    assert g["kick_bass"].audio is None

    # Missing 'other' -> melodic / atmos_fx no_result.
    s = {k: v for k, v in base.items() if k != "other"}
    g = derive_producer_groups(s, params=ProducerGroupParams(sample_rate=SR))
    assert g["melodic"].status == "no_result"
    assert g["atmos_fx"].status == "no_result"
    assert g["melodic"].reason_code == REASON_MISSING_STEM
    assert g["melodic"].audio is None

    # Missing drums -> kick_bass and drums no_result.
    s = {k: v for k, v in base.items() if k != "drums"}
    g = derive_producer_groups(s, params=ProducerGroupParams(sample_rate=SR))
    assert g["kick_bass"].status == "no_result"
    assert g["kick_bass"].reason_code == REASON_MISSING_STEM
    assert g["drums"].status == "no_result"

    # Missing vocals -> vocal no_result.
    s = {k: v for k, v in base.items() if k != "vocals"}
    g = derive_producer_groups(s, params=ProducerGroupParams(sample_rate=SR))
    assert g["vocal"].status == "no_result"


# ---------------------------------------------------------------------------
# Traceability of every group
# ---------------------------------------------------------------------------


def test_components_processing_traceable():
    groups = derive_producer_groups(_full_stems(SR, N), params=ProducerGroupParams(sample_rate=SR))
    for kind, g in groups.items():
        assert g.group_kind == kind
        assert g.status in ALLOWED_STATUS
        assert g.masks
        assert g.summation or g.status == "no_result"
        assert isinstance(g.processing, tuple)
        if g.status == "ok":
            assert g.technical_stems
            assert g.components
        if kind == "kick_bass":
            assert g.status == "ok"
            assert g.technical_stems == ("drums", "bass")
            assert len(g.components) == 2


# ---------------------------------------------------------------------------
# Shared timebase with the master
# ---------------------------------------------------------------------------


def test_timebase_shared_with_master():
    tb = AudioTimebase(sample_rate=SR, n_samples=N)
    groups = derive_producer_groups(
        _full_stems(SR, N), timebase=tb, params=ProducerGroupParams(sample_rate=SR)
    )
    for g in groups.values():
        assert g.timebase.sample_rate == SR
        assert g.timebase.n_samples == N
        if g.audio is not None:
            assert g.audio.shape[0] == N


# ---------------------------------------------------------------------------
# vocal is identity
# ---------------------------------------------------------------------------


def test_vocal_identity():
    stems = _full_stems(SR, N)
    groups = derive_producer_groups(stems, params=ProducerGroupParams(sample_rate=SR))
    assert groups["vocal"].status == "ok"
    assert np.allclose(groups["vocal"].audio, stems["vocals"], atol=1e-6)


# ---------------------------------------------------------------------------
# Deterministic (no randomness)
# ---------------------------------------------------------------------------


def test_deterministic():
    p = ProducerGroupParams(sample_rate=SR)
    g1 = derive_producer_groups(_full_stems(SR, N), params=p)
    g2 = derive_producer_groups(_full_stems(SR, N), params=p)
    for kind in GROUP_KINDS:
        a1, a2 = g1[kind].audio, g2[kind].audio
        if a1 is None:
            assert a2 is None
        else:
            assert np.array_equal(a1, a2)
        assert build_producer_group_manifest(g1[kind]) == build_producer_group_manifest(g2[kind])


# ---------------------------------------------------------------------------
# Manifest contract validation
# ---------------------------------------------------------------------------


def test_manifest_validation_ok_and_no_result():
    groups = derive_producer_groups(_full_stems(SR, N), params=ProducerGroupParams(sample_rate=SR))
    assert validate_producer_group_manifest(build_producer_group_manifest(groups["kick_bass"])) == []
    assert validate_producer_group_manifest(build_producer_group_manifest(groups["melodic"])) == []
    # no_result group also validates.
    s = {k: v for k, v in _full_stems(SR, N).items() if k != "bass"}
    g = derive_producer_groups(s, params=ProducerGroupParams(sample_rate=SR))
    assert validate_producer_group_manifest(build_producer_group_manifest(g["kick_bass"])) == []


def test_manifest_validation_rejects_bad_contract():
    groups = derive_producer_groups(_full_stems(SR, N), params=ProducerGroupParams(sample_rate=SR))
    m = build_producer_group_manifest(groups["kick_bass"])
    m["group_kind"] = "kick_drums"
    errs = validate_producer_group_manifest(m)
    assert any("group_kind must be one of" in e for e in errs)

    # no_result without reason_code is invalid.
    s = {k: v for k, v in _full_stems(SR, N).items() if k != "other"}
    g = derive_producer_groups(s, params=ProducerGroupParams(sample_rate=SR))
    m2 = build_producer_group_manifest(g["melodic"])
    m2.pop("reason_code")
    errs2 = validate_producer_group_manifest(m2)
    assert any("reason_code must be a non-empty string" in e for e in errs2)


# ---------------------------------------------------------------------------
# Plugs into the existing #250/#255 producer_group source contract
# ---------------------------------------------------------------------------


def test_producer_group_source_plugs_into_asset_contract():
    from src.loop_candidates import LoopSourceIdentity

    groups = derive_producer_groups(_full_stems(SR, N), params=ProducerGroupParams(sample_rate=SR))
    kb = groups["kick_bass"]
    identity = LoopSourceIdentity(
        source_kind="producer_group",
        producer_group_id=kb.group_id,
        producer_group_ref=kb.group_ref,
    )
    d = identity.as_dict()
    assert d["source_kind"] == "producer_group"
    assert d["producer_group_id"] == kb.group_id
    assert d["producer_group_ref"] == kb.group_ref


# ---------------------------------------------------------------------------
# Pilot writer (renders reconstructed audio; not used by contract tests)
# ---------------------------------------------------------------------------


def test_write_producer_group_audio(tmp_path: Path):
    import soundfile as sf

    from src.producer_groups import write_producer_group_audio

    groups = derive_producer_groups(_full_stems(SR, N), params=ProducerGroupParams(sample_rate=SR))
    ref = write_producer_group_audio(groups["kick_bass"], tmp_path)
    assert ref == "producer_groups/kick_bass.wav"
    path = tmp_path / ref
    assert path.is_file()
    data, sr = sf.read(str(path))
    assert sr == SR
    assert data.shape[0] == N

    # no_result group produces no file.
    s = {k: v for k, v in _full_stems(SR, N).items() if k != "bass"}
    g = derive_producer_groups(s, params=ProducerGroupParams(sample_rate=SR))
    assert write_producer_group_audio(g["kick_bass"], tmp_path) is None
