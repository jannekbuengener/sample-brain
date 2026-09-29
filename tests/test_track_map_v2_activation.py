"""#683 Track Map V2 explicit analyzer + cache identity activation."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import pytest

from src.analyze import KEY_ANALYSIS_CONTRACT_VERSION, SHORT_AUDIO_QUALITY_NOTE
from src.key_analysis_v2 import KeyAnalysisV2Result
from src.track_analysis_cache import TRACK_ANALYSIS_CACHE_CONTRACT_VERSION
from tests.audio_fixtures import write_key_audio_wav, write_major_chord_wav, write_sine_wav

NOTE_HZ = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
}


def _v2_modeful() -> KeyAnalysisV2Result:
    return KeyAnalysisV2Result(
        key="Cmaj",
        root="C",
        mode="maj",
        root_evidence={
            "kind": "joint_24_profile_pearson",
            "selected_root": "C",
            "raw_top_score": 0.91,
            "raw_top_mode": "maj",
            "raw_top_mode_authoritative": False,
        },
        mode_evidence={
            "kind": "third_contrast",
            "mode": "maj",
            "root": "C",
            "root_source": "joint_24_profile_pearson",
        },
        contract_version=2,
    )


def _v2_root_only() -> KeyAnalysisV2Result:
    return KeyAnalysisV2Result(
        key="G",
        root="G",
        mode=None,
        root_evidence={
            "kind": "joint_24_profile_pearson",
            "selected_root": "G",
            "raw_top_score": 0.77,
            "raw_top_mode": "maj",
            "raw_top_mode_authoritative": False,
        },
        mode_evidence={
            "kind": "third_contrast",
            "mode": None,
            "root": "G",
            "root_source": "joint_24_profile_pearson",
        },
        contract_version=2,
    )


def _analyze_cfg(track_map: dict[str, Any]) -> dict[str, Any]:
    return track_map["provenance"]["components"]["analyze"]["configuration"]


def test_default_analyze_context_file_is_contract_1(tmp_path: Path) -> None:
    from src.context_analyze import analyze_context_file

    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    result = analyze_context_file(source)
    assert result["schema_version"] == "1.2.0"
    assert _analyze_cfg(result)["key_analysis_contract_version"] == 1
    assert KEY_ANALYSIS_CONTRACT_VERSION == 1


def test_explicit_contract_1_remains_v1(tmp_path: Path) -> None:
    from src.context_analyze import analyze_context_file

    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    result = analyze_context_file(source, key_analysis_contract_version=1)
    key = result["analysis"]["musical"]["key"]
    assert _analyze_cfg(result)["key_analysis_contract_version"] == 1
    assert "root_evidence" not in key
    if key.get("status") in {"ok", "partial"} and "key_conf" in key:
        assert key["key_conf_kind"] == "chroma_peak_prominence"


def test_explicit_contract_2_uses_v2_estimator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    calls: list[str] = []

    def fake_estimate(y, sr):
        calls.append("v2")
        return _v2_modeful()

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", fake_estimate)
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    result = ca.analyze_context_file(source, key_analysis_contract_version=2)
    assert calls == ["v2"]
    assert _analyze_cfg(result)["key_analysis_contract_version"] == 2


def test_v2_modeful_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_modeful())
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    result = ca.analyze_context_file(source, key_analysis_contract_version=2)
    key = result["analysis"]["musical"]["key"]
    assert key["status"] == "ok"
    assert key["root"] == "C"
    assert key["mode"] == "maj"
    assert key["root_evidence"]["kind"] == "joint_24_profile_pearson"
    assert key["mode_evidence"]["kind"] == "third_contrast"
    assert "key_conf" not in key
    assert "key_conf_kind" not in key
    assert result["schema_version"] == "1.2.0"


def test_v2_root_only_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_root_only())
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    result = ca.analyze_context_file(source, key_analysis_contract_version=2)
    key = result["analysis"]["musical"]["key"]
    assert key["status"] == "partial"
    assert key["reason_code"] == "MODE_UNRESOLVED"
    assert key["root"] == "G"
    assert "mode" not in key
    assert "root_evidence" in key
    assert "mode_evidence" in key
    assert "key_conf" not in key
    assert "key_conf_kind" not in key


def test_v2_estimator_none_is_key_undetectable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: None)
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    result = ca.analyze_context_file(source, key_analysis_contract_version=2)
    key = result["analysis"]["musical"]["key"]
    assert key == {
        "status": "no_result",
        "reason_code": "KEY_UNDETECTABLE",
        "source_ref": "analyze",
    }


def test_v1_semantics_under_schema_1_2_0(tmp_path: Path) -> None:
    from src.context_analyze import analyze_context_file

    source = write_major_chord_wav(tmp_path / "cmaj.wav", frequency_hz=NOTE_HZ["C"])
    result = analyze_context_file(source)
    assert result["schema_version"] == "1.2.0"
    key = result["analysis"]["musical"]["key"]
    assert key["status"] == "ok"
    assert key["root"] == "C"
    assert key["mode"] == "maj"
    assert "key_conf" in key
    assert key["key_conf_kind"] == "chroma_peak_prominence"
    assert "root_evidence" not in key
    assert _analyze_cfg(result)["key_analysis_contract_version"] == 1


def test_v1_and_v2_fingerprints_and_cache_keys_differ(tmp_path: Path) -> None:
    from src.context_analyze import _package_version, _package_version_for
    from src.track_analysis_cache import compute_analysis_fingerprint, compute_cache_key
    from src.content_hash import compute_file_hash

    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    source_hash = compute_file_hash(source)
    common = dict(
        bpm_normalization="none",
        backend_name="librosa",
        backend_version=_package_version_for("librosa"),
        sample_brain_version=_package_version(),
    )
    fp1 = compute_analysis_fingerprint(**common, key_analysis_contract_version=1)
    fp2 = compute_analysis_fingerprint(**common, key_analysis_contract_version=2)
    k1 = compute_cache_key(
        source_content_hash=source_hash, **common, key_analysis_contract_version=1
    )
    k2 = compute_cache_key(
        source_content_hash=source_hash, **common, key_analysis_contract_version=2
    )
    assert fp1 != fp2
    assert k1 != k2


def test_cache_hit_miss_matrix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_modeful())
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"

    v1_miss = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=1
    )
    assert v1_miss.cache_status == "miss"
    v1_hit = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=1
    )
    assert v1_hit.cache_status == "hit"
    assert _analyze_cfg(v1_hit.track_map)["key_analysis_contract_version"] == 1

    v2_miss = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=2
    )
    assert v2_miss.cache_status == "miss"
    assert _analyze_cfg(v2_miss.track_map)["key_analysis_contract_version"] == 2
    v2_hit = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=2
    )
    assert v2_hit.cache_status == "hit"

    cross_v2 = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=2
    )
    # already warm V2; still same-contract hit
    assert cross_v2.cache_status == "hit"
    # V1 entry still hits for V1 request
    assert (
        ca.analyze_context_file_cached(
            source, cache_dir=cache_dir, key_analysis_contract_version=1
        ).cache_status
        == "hit"
    )
    assert v1_miss.cache_key != v2_miss.cache_key


def test_cross_version_cache_is_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_modeful())
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_v1 = tmp_path / "cache_v1"
    cache_v2 = tmp_path / "cache_v2"

    ca.analyze_context_file_cached(
        source, cache_dir=cache_v1, key_analysis_contract_version=1
    )
    # Request V2 against a V1-only cache dir → miss
    r = ca.analyze_context_file_cached(
        source, cache_dir=cache_v1, key_analysis_contract_version=2
    )
    assert r.cache_status == "miss"

    ca.analyze_context_file_cached(
        source, cache_dir=cache_v2, key_analysis_contract_version=2
    )
    r2 = ca.analyze_context_file_cached(
        source, cache_dir=cache_v2, key_analysis_contract_version=1
    )
    assert r2.cache_status == "miss"


def test_unknown_contract_fails_closed_without_cache_write(tmp_path: Path) -> None:
    from src.context_analyze import ContextAnalyzeError, analyze_context_file_cached

    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    with pytest.raises(ContextAnalyzeError) as exc:
        analyze_context_file_cached(
            source, cache_dir=cache_dir, key_analysis_contract_version=99
        )
    assert exc.value.code == "UNSUPPORTED_KEY_ANALYSIS_CONTRACT"
    assert not cache_dir.exists() or not any(cache_dir.glob("*.json"))


def test_unknown_contract_fails_before_analyze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca

    calls: list[str] = []

    def boom(*_a, **_k):
        calls.append("analyze")
        raise AssertionError("must not analyze")

    monkeypatch.setattr(ca, "extract_features", boom)
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    with pytest.raises(ca.ContextAnalyzeError) as exc:
        ca.analyze_context_file(source, key_analysis_contract_version=99)
    assert exc.value.code == "UNSUPPORTED_KEY_ANALYSIS_CONTRACT"
    assert calls == []


def test_cache_disabled_still_honors_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_modeful())
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    r1 = ca.analyze_context_file_cached(
        source,
        cache_dir=cache_dir,
        enabled=False,
        key_analysis_contract_version=1,
    )
    r2 = ca.analyze_context_file_cached(
        source,
        cache_dir=cache_dir,
        enabled=False,
        key_analysis_contract_version=2,
    )
    assert r1.cache_status == "disabled"
    assert r2.cache_status == "disabled"
    assert r1.cache_key is None
    assert _analyze_cfg(r1.track_map)["key_analysis_contract_version"] == 1
    assert _analyze_cfg(r2.track_map)["key_analysis_contract_version"] == 2
    assert "key_conf" not in r2.track_map["analysis"]["musical"]["key"]
    assert not cache_dir.exists()


def test_sha1_to_sha256_migration_preserves_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2
    from src.content_hash import (
        DEFAULT_CONTENT_HASH_ALGORITHM,
        LEGACY_CONTENT_HASH_ALGORITHM,
        compute_file_hashes,
    )
    from src.track_analysis_cache import (
        build_cache_entry,
        compute_analysis_fingerprint,
        compute_cache_key,
        write_cache_entry,
    )

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_modeful())
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    hashes = compute_file_hashes(
        source, algorithms=(DEFAULT_CONTENT_HASH_ALGORITHM, LEGACY_CONTENT_HASH_ALGORITHM)
    )
    package_version = ca._package_version()
    backend_version = ca._package_version_for("librosa")
    common = dict(
        bpm_normalization="none",
        backend_name="librosa",
        backend_version=backend_version,
        sample_brain_version=package_version,
    )

    # Seed a legacy SHA-1 V1 entry.
    fp_v1 = compute_analysis_fingerprint(**common, key_analysis_contract_version=1)
    legacy_key = compute_cache_key(
        source_content_hash=hashes[LEGACY_CONTENT_HASH_ALGORITHM],
        **common,
        key_analysis_contract_version=1,
    )
    track_map = ca.analyze_context_file(source, key_analysis_contract_version=1)
    entry = build_cache_entry(
        cache_key=legacy_key,
        source_content_hash=hashes[LEGACY_CONTENT_HASH_ALGORITHM],
        analysis_fingerprint=fp_v1,
        track_map=track_map,
        provenance_component=track_map["provenance"]["components"]["analyze"],
        quality=track_map["quality"],
    )
    write_cache_entry(cache_dir, legacy_key, entry)

    hit = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=1
    )
    assert hit.cache_status == "hit"
    current_key = compute_cache_key(
        source_content_hash=hashes[DEFAULT_CONTENT_HASH_ALGORITHM],
        **common,
        key_analysis_contract_version=1,
    )
    assert hit.cache_key == current_key
    assert (cache_dir / f"{current_key}.json").exists()

    # Same legacy V1 entry must not satisfy a V2 request.
    miss = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=2
    )
    assert miss.cache_status == "miss"
    assert _analyze_cfg(miss.track_map)["key_analysis_contract_version"] == 2


def test_no_private_paths_in_v2_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_modeful())
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    r = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=2
    )
    text = json.dumps(r.track_map)
    assert str(tmp_path) not in text
    assert str(cache_dir) not in text
    entry_text = (cache_dir / f"{r.cache_key}.json").read_text(encoding="utf-8")
    assert str(tmp_path) not in entry_text


def test_no_catalog_db_access_on_v2_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.db as db
    import src.key_analysis_v2 as v2

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", lambda *_a, **_k: _v2_modeful())

    def boom(*_a, **_k):
        raise AssertionError("catalog DB must not be touched")

    monkeypatch.setattr(db, "get_engine", boom)
    monkeypatch.setattr(db, "init_db", boom)
    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    ca.analyze_context_file(source, key_analysis_contract_version=2)


def test_short_audio_does_not_bypass_via_v2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import src.context_analyze as ca
    import src.key_analysis_v2 as v2

    calls: list[str] = []

    def fake_estimate(*_a, **_k):
        calls.append("v2")
        return _v2_modeful()

    monkeypatch.setattr(v2, "estimate_key_v2_shadow", fake_estimate)
    source = write_sine_wav(tmp_path / "short.wav", duration_sec=0.05, frequency_hz=440.0)
    result = ca.analyze_context_file(source, key_analysis_contract_version=2)
    assert calls == []
    key = result["analysis"]["musical"]["key"]
    assert key["status"] == "no_result"
    assert key["reason_code"] == "KEY_UNDETECTABLE"
    notes = result["quality"]["notes"]
    assert any(n.get("message") == SHORT_AUDIO_QUALITY_NOTE or n.get("code") == "SHORT_AUDIO" for n in notes)


def test_cli_deconstruct_track_context_signatures_default_v1() -> None:
    from src.context_analyze import analyze_context_file, analyze_context_file_cached
    from src.deconstruct import _default_track_map_adapter
    from src.track_context import analyze_track_context

    assert (
        inspect.signature(analyze_context_file)
        .parameters["key_analysis_contract_version"]
        .default
        == 1
    )
    assert (
        inspect.signature(analyze_context_file_cached)
        .parameters["key_analysis_contract_version"]
        .default
        == 1
    )
    # Callers must not require / force a V2 argument.
    assert "key_analysis_contract_version" not in inspect.signature(
        analyze_track_context
    ).parameters
    src = inspect.getsource(_default_track_map_adapter)
    assert "key_analysis_contract_version" not in src


def test_cli_context_analyze_path_does_not_pass_v2() -> None:
    import src.cli as cli

    src = inspect.getsource(cli)
    # No CLI flag / kwarg for key analysis contract in this slice.
    assert "--key-analysis" not in src
    assert "key_analysis_contract_version=" not in src


def test_global_analyzer_and_cache_contract_unchanged() -> None:
    assert KEY_ANALYSIS_CONTRACT_VERSION == 1
    assert TRACK_ANALYSIS_CACHE_CONTRACT_VERSION == 2


def test_v2_live_estimator_smoke_shape(tmp_path: Path) -> None:
    """Live V2 path: contract/shape only — no exact DSP key values."""
    from src.context_analyze import analyze_context_file

    source = write_key_audio_wav(
        tmp_path / "c_maj.wav", frequency_hz=NOTE_HZ["C"], mode="maj"
    )
    result = analyze_context_file(source, key_analysis_contract_version=2)
    key = result["analysis"]["musical"]["key"]
    assert key["status"] in {"ok", "partial", "no_result"}
    assert "key_conf" not in key
    assert "key_conf_kind" not in key
    assert _analyze_cfg(result)["key_analysis_contract_version"] == 2
    assert result["schema_version"] == "1.2.0"
    if key["status"] in {"ok", "partial"}:
        assert "root" in key
        assert key["root_evidence"]["kind"] == "joint_24_profile_pearson"
        assert "mode_evidence" in key


def test_cache_hit_normalizes_track_map_schema_version(tmp_path: Path) -> None:
    """Warm pre-1.2.0 entries must not leak stale schema_version on hit."""
    import src.context_analyze as ca
    from src.content_hash import compute_file_hash
    from src.track_analysis_cache import (
        build_cache_entry,
        compute_analysis_fingerprint,
        compute_cache_key,
        write_cache_entry,
    )

    source = write_sine_wav(tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0)
    cache_dir = tmp_path / "cache"
    package_version = ca._package_version()
    backend_version = ca._package_version_for("librosa")
    common = dict(
        bpm_normalization="none",
        backend_name="librosa",
        backend_version=backend_version,
        sample_brain_version=package_version,
        key_analysis_contract_version=1,
    )
    source_hash = compute_file_hash(source)
    fp = compute_analysis_fingerprint(**common)
    key = compute_cache_key(source_content_hash=source_hash, **common)
    track_map = ca.analyze_context_file(source, key_analysis_contract_version=1)
    track_map = dict(track_map)
    track_map["schema_version"] = "1.1.0"
    entry = build_cache_entry(
        cache_key=key,
        source_content_hash=source_hash,
        analysis_fingerprint=fp,
        track_map=track_map,
        provenance_component=track_map["provenance"]["components"]["analyze"],
        quality=track_map["quality"],
    )
    write_cache_entry(cache_dir, key, entry)

    hit = ca.analyze_context_file_cached(
        source, cache_dir=cache_dir, key_analysis_contract_version=1
    )
    assert hit.cache_status == "hit"
    assert hit.track_map["schema_version"] == "1.2.0"
