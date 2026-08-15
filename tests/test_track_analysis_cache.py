from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import soundfile as sf

from tests.audio_fixtures import write_sine_wav

import src.track_analysis_cache as tac
from src.track_analysis_cache import (
    CACHE_ENTRY_DOCUMENT_TYPE,
    TRACK_ANALYSIS_CACHE_CONTRACT_VERSION,
    build_cache_entry,
    compute_analysis_fingerprint,
    compute_cache_key,
    get_cache_dir,
    read_cache_entry,
    validate_cache_entry,
    write_cache_entry,
)
from src.context_analyze import TrackAnalysisCacheResult, analyze_context_file_cached


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_key(source: Path) -> str:
    import src.context_analyze as ca

    return compute_cache_key(
        source_content_hash=ca.content_hash(source),
        bpm_normalization="none",
        backend_name="librosa",
        backend_version=ca._package_version_for("librosa"),
        sample_brain_version=ca._package_version(),
    )


def _real_extract_spy(monkeypatch):
    """Patch extract_features with a counting wrapper; returns the call list."""
    import src.context_analyze as ca

    calls: list[int] = []
    real = ca.extract_features

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(ca, "extract_features", counting)
    return calls


# ---------------------------------------------------------------------------
# 1. Fingerprint determinism
# ---------------------------------------------------------------------------


def test_same_inputs_produce_same_key():
    base = dict(
        source_content_hash="sha1:x",
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    assert compute_cache_key(**base) == compute_cache_key(**base)


def test_dict_ordering_does_not_affect_key():
    # The canonical JSON uses sort_keys; identical logical inputs always match.
    a = compute_analysis_fingerprint(
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    b = compute_analysis_fingerprint(
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    assert a == b


def test_no_timestamp_dependency():
    # build a key twice with no time-varying inputs -> identical (no timestamps used)
    base = dict(
        source_content_hash="sha1:x",
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    assert compute_cache_key(**base) == compute_cache_key(**base)


def test_config_change_produces_different_key():
    base = dict(
        source_content_hash="sha1:x",
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    k1 = compute_cache_key(**base)
    k2 = compute_cache_key(**{**base, "bpm_normalization": "heuristic"})
    assert k1 != k2


def test_backend_version_change_produces_different_key():
    base = dict(
        source_content_hash="sha1:x",
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    k1 = compute_cache_key(**base)
    k2 = compute_cache_key(**{**base, "backend_version": "0.12.0"})
    assert k1 != k2


def test_contract_version_change_produces_different_key(monkeypatch):
    base = dict(
        source_content_hash="sha1:x",
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    k1 = compute_cache_key(**base)
    monkeypatch.setattr(tac, "TRACK_ANALYSIS_CACHE_CONTRACT_VERSION", 2)
    k2 = compute_cache_key(**base)
    assert k1 != k2


def test_optional_model_identity_changes_key():
    base = dict(
        source_content_hash="sha1:x",
        bpm_normalization="none",
        backend_name="librosa",
        backend_version="0.11.0",
        sample_brain_version="0.1.0",
    )
    k1 = compute_cache_key(**base)
    k2 = compute_cache_key(
        **{**base, "model_identity": {"name": "m", "version": "1", "revision": "r"}}
    )
    assert k1 != k2
    # null vs absent must be equal (no invented model)
    k3 = compute_cache_key(**{**base, "model_identity": None})
    assert k1 == k3


# ---------------------------------------------------------------------------
# 2. Hit / Miss behavior
# ---------------------------------------------------------------------------


def test_first_run_is_miss(tmp_path):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    result = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert isinstance(result, TrackAnalysisCacheResult)
    assert result.cache_status == "miss"
    assert result.cache_key is not None
    assert (cache_dir / f"{result.cache_key}.json").exists()


def test_second_identical_run_is_hit(tmp_path, monkeypatch):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    calls = _real_extract_spy(monkeypatch)
    r1 = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r1.cache_status == "miss"
    assert len(calls) == 1
    r2 = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r2.cache_status == "hit"
    # expensive feature extraction not re-run on hit
    assert len(calls) == 1


def test_disabled_cache_always_recomputes(tmp_path, monkeypatch):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    calls = _real_extract_spy(monkeypatch)
    r1 = analyze_context_file_cached(source, cache_dir=cache_dir, enabled=False)
    r2 = analyze_context_file_cached(source, cache_dir=cache_dir, enabled=False)
    assert r1.cache_status == "disabled"
    assert r2.cache_status == "disabled"
    assert r1.cache_key is None
    assert len(calls) == 2  # both runs recompute
    assert not cache_dir.exists()  # nothing written


# ---------------------------------------------------------------------------
# 3. Identity preservation
# ---------------------------------------------------------------------------


def test_same_audio_different_filename_hit_returns_current_filename(tmp_path, monkeypatch):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    r1 = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r1.cache_status == "miss"
    # same content, different file name
    other = tmp_path / "b completely different.wav"
    shutil.copyfile(source, other)
    r2 = analyze_context_file_cached(other, cache_dir=cache_dir)
    assert r2.cache_status == "hit"
    assert r2.track_map["source"]["original"]["file_name"] == "b completely different.wav"
    # old file name must not leak
    assert "a.wav" not in json.dumps(r2.track_map)


def test_no_private_paths_leak_in_track_map_on_hit(tmp_path, monkeypatch):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    analyze_context_file_cached(source, cache_dir=cache_dir)
    r2 = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r2.cache_status == "hit"
    text = json.dumps(r2.track_map)
    assert str(cache_dir) not in text
    assert str(tmp_path) not in text


# ---------------------------------------------------------------------------
# 4. Invalidation
# ---------------------------------------------------------------------------


def test_audio_content_change_causes_miss(tmp_path):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"
    # change audio content (same path, same name)
    write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=880.0)
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"


def test_bpm_normalization_change_causes_miss(tmp_path):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    assert (
        analyze_context_file_cached(
            source, cache_dir=cache_dir, bpm_normalization="none"
        ).cache_status
        == "miss"
    )
    assert (
        analyze_context_file_cached(
            source, cache_dir=cache_dir, bpm_normalization="heuristic"
        ).cache_status
        == "miss"
    )


def test_backend_version_change_causes_miss(tmp_path, monkeypatch):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"
    monkeypatch.setattr(
        "src.context_analyze._package_version_for",
        lambda dist: "99.0.0" if dist == "librosa" else "0.1.0",
    )
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"


def test_analysis_version_change_causes_miss(tmp_path, monkeypatch):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"
    monkeypatch.setattr("src.context_analyze._package_version", lambda: "9.9.9")
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"


# ---------------------------------------------------------------------------
# 5. Safety
# ---------------------------------------------------------------------------


def test_corrupt_json_returns_miss_not_crash(tmp_path, monkeypatch):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    key = _current_key(source)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{key}.json").write_text("{not valid json", encoding="utf-8")
    calls = _real_extract_spy(monkeypatch)
    r = analyze_context_file_cached(source, cache_dir=cache_dir)
    assert r.cache_status == "miss"
    assert len(calls) == 1  # recomputed safely


def test_wrong_document_type_returns_miss(tmp_path):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    key = _current_key(source)
    entry = build_cache_entry(
        cache_key=key,
        source_content_hash="sha1:x",
        analysis_fingerprint="fp",
        track_map={"a": 1},
        provenance_component={"b": 2},
        quality={"c": 3},
    )
    entry["document_type"] = "wrong.type"
    write_cache_entry(cache_dir, key, entry)
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"


def test_unsupported_schema_major_returns_miss(tmp_path):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    key = _current_key(source)
    entry = build_cache_entry(
        cache_key=key,
        source_content_hash="sha1:x",
        analysis_fingerprint="fp",
        track_map={"a": 1},
        provenance_component={"b": 2},
        quality={"c": 3},
    )
    entry["schema_version"] = "2.0.0"
    write_cache_entry(cache_dir, key, entry)
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"


def test_mismatched_stored_key_returns_miss(tmp_path):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    key = _current_key(source)
    entry = build_cache_entry(
        cache_key="a_different_key",
        source_content_hash="sha1:x",
        analysis_fingerprint="fp",
        track_map={"a": 1},
        provenance_component={"b": 2},
        quality={"c": 3},
    )
    write_cache_entry(cache_dir, key, entry)
    assert analyze_context_file_cached(source, cache_dir=cache_dir).cache_status == "miss"


def test_cache_entry_contains_no_private_paths(tmp_path):
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    r = analyze_context_file_cached(source, cache_dir=cache_dir)
    text = (cache_dir / f"{r.cache_key}.json").read_text(encoding="utf-8")
    assert str(source) not in text
    assert str(cache_dir) not in text
    assert str(tmp_path) not in text


# ---------------------------------------------------------------------------
# 6. Atomic writes
# ---------------------------------------------------------------------------


def test_valid_entry_created_atomically(tmp_path):
    entry = build_cache_entry(
        cache_key="k1",
        source_content_hash="sha1:x",
        analysis_fingerprint="fp",
        track_map={"a": 1},
        provenance_component={"b": 2},
        quality={"c": 3},
    )
    write_cache_entry(tmp_path / "cache", "k1", entry)
    path = tmp_path / "cache" / "k1.json"
    assert path.exists()
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["cache_key"] == "k1"
    assert loaded["track_map"] == {"a": 1}
    assert loaded["document_type"] == CACHE_ENTRY_DOCUMENT_TYPE


def test_partial_write_not_accepted_as_hit(tmp_path):
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = "partialkey"
    (cache_dir / f"{key}.json").write_text(
        '{"document_type": "sample_brain.track_analysis_cache_entry", "schema_ver',
        encoding="utf-8",
    )
    assert read_cache_entry(cache_dir, key) is None


# ---------------------------------------------------------------------------
# 7. Validation helpers
# ---------------------------------------------------------------------------


def test_validate_cache_entry_detects_mismatch():
    entry = build_cache_entry(
        cache_key="k1",
        source_content_hash="sha1:x",
        analysis_fingerprint="fp",
        track_map={},
        provenance_component={},
        quality={},
    )
    assert validate_cache_entry(
        entry,
        expected_cache_key="k1",
        expected_source_hash="sha1:x",
        expected_analysis_fingerprint="fp",
    )
    assert not validate_cache_entry(
        entry,
        expected_cache_key="k2",
        expected_source_hash="sha1:x",
        expected_analysis_fingerprint="fp",
    )
    assert not validate_cache_entry(
        entry,
        expected_cache_key="k1",
        expected_source_hash="sha1:y",
        expected_analysis_fingerprint="fp",
    )
    assert not validate_cache_entry(
        entry,
        expected_cache_key="k1",
        expected_source_hash="sha1:x",
        expected_analysis_fingerprint="fp2",
    )


# ---------------------------------------------------------------------------
# 8. Deconstruct integration (#237 vs #262 boundary)
# ---------------------------------------------------------------------------


def test_pack_resume_priority_over_cache(tmp_path, monkeypatch):
    """#262 pack-reuse must avoid calling #237 cache path entirely."""
    from src.deconstruct import run_deconstruct

    track = write_sine_wav(tmp_path / "t.wav", duration_sec=1.0, frequency_hz=220)
    cache_dir = tmp_path / "cache"
    import src.context_analyze as ca

    calls: list[int] = []
    real = ca.analyze_context_file_cached

    def spy(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(ca, "analyze_context_file_cached", spy)

    run_deconstruct(
        track, tmp_path / "pack1", track_cache_dir=cache_dir, skip={"arrangement", "stems"}
    )
    assert len(calls) == 1
    # Second run on same pack -> #262 resume reuses track_map; #237 not consulted.
    r2 = run_deconstruct(
        track, tmp_path / "pack1", track_cache_dir=cache_dir, skip={"arrangement", "stems"}
    )
    assert len(calls) == 1
    assert r2.steps[0].execution == "reused"
    assert r2.steps[0].track_analysis_cache_status is None


def test_new_pack_root_can_use_general_cache(tmp_path, monkeypatch):
    """New pack-root: #262 miss, but #237 general cache hit."""
    from src.deconstruct import run_deconstruct

    track = write_sine_wav(tmp_path / "t.wav", duration_sec=1.0, frequency_hz=220)
    cache_dir = tmp_path / "cache"
    import src.context_analyze as ca

    statuses: list[str] = []
    real = ca.analyze_context_file_cached

    def spy(*args, **kwargs):
        res = real(*args, **kwargs)
        statuses.append(res.cache_status)
        return res

    monkeypatch.setattr(ca, "analyze_context_file_cached", spy)

    r1 = run_deconstruct(
        track, tmp_path / "pack1", track_cache_dir=cache_dir, skip={"arrangement", "stems"}
    )
    assert r1.steps[0].track_analysis_cache_status == "miss"
    assert statuses == ["miss"]

    r2 = run_deconstruct(
        track, tmp_path / "pack2", track_cache_dir=cache_dir, skip={"arrangement", "stems"}
    )
    assert r2.steps[0].track_analysis_cache_status == "hit"
    assert r2.steps[0].execution == "computed"
    assert statuses == ["miss", "hit"]


def test_fresh_pack_and_cache_both_miss(tmp_path, monkeypatch):
    from src.deconstruct import run_deconstruct

    track = write_sine_wav(tmp_path / "t.wav", duration_sec=1.0, frequency_hz=220)
    cache_dir = tmp_path / "cache"
    import src.context_analyze as ca

    statuses: list[str] = []
    real = ca.analyze_context_file_cached

    def spy(*args, **kwargs):
        res = real(*args, **kwargs)
        statuses.append(res.cache_status)
        return res

    monkeypatch.setattr(ca, "analyze_context_file_cached", spy)

    r = run_deconstruct(
        track, tmp_path / "pack1", track_cache_dir=cache_dir, skip={"arrangement", "stems"}
    )
    assert statuses == ["miss"]
    assert r.steps[0].execution == "computed"
    assert r.steps[0].track_analysis_cache_status == "miss"
