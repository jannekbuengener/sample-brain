from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from sqlalchemy import text

import src.config as config_module
import src.db as db_module
from src.analyze import extract_features, run_analyze
from src.content_hash import hash_record
from src.joint_key_profile import JointKeyProfileResult, KeyProfileHypothesis
from src.key_analysis_v2 import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    estimate_key_v2_shadow,
    read_key_analysis_v2_shadow,
    serialize_key_analysis_v2_evidence,
    write_key_analysis_v2_shadow,
)
from tests.audio_fixtures import (
    write_key_audio_wav,
    write_major_minor_blend_wav,
    write_octave_wav,
    write_root_fifth_wav,
    write_sine_wav,
)


NOTE_HZ = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
}


def _joint_result(root: str = "G", mode: str = "maj", score: float = 0.75) -> JointKeyProfileResult:
    hypothesis = KeyProfileHypothesis(root=root, mode=mode, score=score)
    return JointKeyProfileResult(root=root, mode=mode, raw_score=score, ranking=(hypothesis,))


def _result(*, root: str = "C", mode: str | None = None) -> KeyAnalysisV2Result:
    return KeyAnalysisV2Result(
        key=f"{root}{mode or ''}",
        root=root,
        mode=mode,
        root_evidence={
            "kind": "joint_24_profile_pearson",
            "selected_root": root,
            "raw_top_score": 0.75,
            "raw_top_mode": "maj",
            "raw_top_mode_authoritative": False,
        },
        mode_evidence={
            "kind": "third_contrast",
            "major_third_energy": 0.2,
            "minor_third_energy": 0.2,
            "contrast": 0.0,
            "threshold": 0.3,
            "mode": mode,
            "root": root,
            "root_source": "joint_24_profile_pearson",
        },
    )


def _use_temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "catalog.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    config_module.DB_PATH = db_path
    config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    return db_path


def _insert_sample(sample_id: int, identity: dict[str, str]) -> None:
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                "INSERT INTO samples (id, path, hash, hash_algorithm) "
                "VALUES (:id, :path, :hash, :algorithm)"
            ),
            {
                "id": sample_id,
                "path": f"sample-{sample_id}.wav",
                "hash": identity["value"],
                "algorithm": identity["algorithm"],
            },
        )


def _write_c_major_bass_fixture(path: Path, *, fifth_bass: bool) -> Path:
    sr = 44100
    duration = 2.0
    t = np.linspace(0.0, duration, int(sr * duration), endpoint=False, dtype=np.float32)
    if fifth_bass:
        bass = 0.65 * np.sin(2.0 * np.pi * 98.00 * t)
        triad_gain = 0.35
    else:
        bass = 0.85 * np.sin(2.0 * np.pi * 65.406 * t)
        triad_gain = 0.30
    triad = triad_gain * sum(
        np.sin(2.0 * np.pi * frequency * t) for frequency in (261.63, 329.63, 392.00)
    )
    sf.write(path, np.clip(bass + triad, -1.0, 1.0).astype(np.float32), sr, subtype="PCM_16")
    return path


def _load(path: Path) -> tuple[np.ndarray, int]:
    y, sr = sf.read(str(path), dtype="float32", always_2d=False)
    return np.asarray(y, dtype=np.float32), int(sr)


def test_v2_uses_one_chroma_for_joint_root_and_third_contrast(monkeypatch: pytest.MonkeyPatch):
    import src.key_analysis_v2 as module

    chroma = np.linspace(0.0, 1.0, 12, dtype=np.float64)
    calls: list[str] = []

    def fake_chroma(y, sr):
        calls.append("chroma")
        assert y.shape == (8,)
        assert sr == 44100
        return chroma

    def fake_rank(received):
        calls.append("rank")
        assert received is chroma
        return _joint_result()

    def fake_mode(y, sr, *, root, chroma_mean):
        calls.append("mode")
        assert root == "G"
        assert chroma_mean is chroma
        return None, {"kind": "third_contrast", "mode": None}

    monkeypatch.setattr(module, "_chroma_mean", fake_chroma)
    monkeypatch.setattr(module, "rank_joint_key_profiles", fake_rank)
    monkeypatch.setattr(module, "estimate_key_mode", fake_mode)

    result = estimate_key_v2_shadow(np.ones(8, dtype=np.float32), 44100)

    assert calls == ["chroma", "rank", "mode"]
    assert result is not None
    assert (result.root, result.mode, result.key) == ("G", None, "G")
    assert result.contract_version == KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION
    assert result.root_evidence == {
        "kind": "joint_24_profile_pearson",
        "selected_root": "G",
        "raw_top_score": 0.75,
        "raw_top_mode": "maj",
        "raw_top_mode_authoritative": False,
    }
    assert result.mode_evidence == {
        "kind": "third_contrast",
        "mode": None,
        "root": "G",
        "root_source": "joint_24_profile_pearson",
    }


def test_joint_mode_never_overrides_third_contrast_abstention(monkeypatch: pytest.MonkeyPatch):
    import src.key_analysis_v2 as module

    monkeypatch.setattr(module, "_chroma_mean", lambda *_args: np.arange(12, dtype=np.float64))
    monkeypatch.setattr(module, "rank_joint_key_profiles", lambda _chroma: _joint_result("G", "maj"))
    monkeypatch.setattr(
        module,
        "estimate_key_mode",
        lambda *_args, **_kwargs: (None, {"kind": "third_contrast", "mode": None}),
    )

    result = estimate_key_v2_shadow(np.ones(4, dtype=np.float32), 44100)

    assert result is not None
    assert result.root_evidence["raw_top_mode"] == "maj"
    assert result.root_evidence["raw_top_mode_authoritative"] is False
    assert result.mode is None
    assert result.key == "G"


@pytest.mark.parametrize(
    "chroma",
    [None, np.asarray([np.nan] * 12), np.ones(12, dtype=np.float64)],
)
def test_v2_fails_closed_for_missing_or_invalid_chroma(monkeypatch: pytest.MonkeyPatch, chroma):
    import src.key_analysis_v2 as module

    monkeypatch.setattr(module, "_chroma_mean", lambda *_args: chroma)

    assert estimate_key_v2_shadow(np.ones(4, dtype=np.float32), 44100) is None


def test_v2_418_clear_and_ambiguous_contract(tmp_path: Path):
    clear: list[tuple[Path, str, str]] = []
    for root, frequency in NOTE_HZ.items():
        clear.append((write_key_audio_wav(tmp_path / f"{root}_maj.wav", frequency_hz=frequency, mode="maj"), root, "maj"))
        clear.append((write_key_audio_wav(tmp_path / f"{root}_min.wav", frequency_hz=frequency, mode="min"), root, "min"))

    clear_results = []
    for path, root, mode in clear:
        y, sr = _load(path)
        result = estimate_key_v2_shadow(y, sr)
        assert result is not None
        clear_results.append((result.root == root, result.mode == mode, result.key == f"{root}{mode}"))

    assert sum(root for root, _mode, _combined in clear_results) == 12
    assert sum(mode for _root, mode, _combined in clear_results) == 12
    assert sum(combined for _root, _mode, combined in clear_results) == 12

    ambiguous = (
        write_sine_wav(tmp_path / "single.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"]),
        write_octave_wav(tmp_path / "octave.wav", frequency_hz=NOTE_HZ["C"]),
        write_root_fifth_wav(tmp_path / "fifth.wav", frequency_hz=NOTE_HZ["C"]),
        write_major_minor_blend_wav(tmp_path / "blend.wav", frequency_hz=NOTE_HZ["C"]),
    )
    for path in ambiguous:
        y, sr = _load(path)
        result = estimate_key_v2_shadow(y, sr)
        assert result is not None
        assert result.mode is None
        assert result.mode_evidence["mode"] is None


def test_v2_418_bass_contract(tmp_path: Path):
    root_y, root_sr = _load(_write_c_major_bass_fixture(tmp_path / "root.wav", fifth_bass=False))
    fifth_y, fifth_sr = _load(_write_c_major_bass_fixture(tmp_path / "fifth.wav", fifth_bass=True))

    root_result = estimate_key_v2_shadow(root_y, root_sr)
    fifth_result = estimate_key_v2_shadow(fifth_y, fifth_sr)

    assert root_result is not None
    assert (root_result.root, root_result.mode, root_result.key) == ("C", "maj", "Cmaj")
    assert fifth_result is not None
    assert fifth_result.root == "G"
    assert fifth_result.root_evidence["raw_top_mode"] in {"maj", "min"}
    assert fifth_result.mode is None
    assert fifth_result.key == "G"


def test_evidence_json_is_deterministic_and_excludes_unsupported_fields():
    result = _result()

    first = serialize_key_analysis_v2_evidence(result.root_evidence)
    second = serialize_key_analysis_v2_evidence(result.root_evidence)

    assert first == second
    assert first == json.dumps(result.root_evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    decoded = json.loads(first)
    assert set(decoded) == {
        "kind",
        "selected_root",
        "raw_top_score",
        "raw_top_mode",
        "raw_top_mode_authoritative",
    }
    assert not ({"ranking", "margin", "probability", "confidence", "no_key_score"} & set(decoded))


def test_sidecar_fresh_write_read_stale_and_malformed_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    identity = hash_record("sha256", "a" * 64)
    _insert_sample(1, identity)
    result = _result()

    write_key_analysis_v2_shadow(sample_id=1, source_identity=identity, result=result)
    stored = read_key_analysis_v2_shadow(sample_id=1, source_identity=identity)

    assert stored == result
    assert read_key_analysis_v2_shadow(sample_id=1, source_identity=hash_record("sha1", "b" * 40)) is None

    with engine.begin() as conn:
        conn.execute(text("UPDATE key_analysis_v2_shadow SET key_root_evidence = '{bad' WHERE sample_id = 1"))
    assert read_key_analysis_v2_shadow(sample_id=1, source_identity=identity) is None

    write_key_analysis_v2_shadow(sample_id=1, source_identity=identity, result=result)
    with engine.begin() as conn:
        conn.execute(text("UPDATE key_analysis_v2_shadow SET key_mode_evidence = '{bad' WHERE sample_id = 1"))
    assert read_key_analysis_v2_shadow(sample_id=1, source_identity=identity) is None


def test_sidecar_rejects_missing_sample_wrong_contract_and_invalid_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    identity = hash_record("sha256", "a" * 64)

    with pytest.raises(ValueError, match="sample does not exist"):
        write_key_analysis_v2_shadow(sample_id=1, source_identity=identity, result=_result())
    with pytest.raises(ValueError, match="content hash"):
        read_key_analysis_v2_shadow(sample_id=1, source_identity={"algorithm": "md5", "value": "a" * 32})

    _insert_sample(1, identity)
    write_key_analysis_v2_shadow(sample_id=1, source_identity=identity, result=_result())
    with engine.begin() as conn:
        conn.execute(text("UPDATE key_analysis_v2_shadow SET contract_version = 1 WHERE sample_id = 1"))
    assert read_key_analysis_v2_shadow(sample_id=1, source_identity=identity) is None


def test_sidecar_rejects_noncanonical_root_and_contradictory_mode_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _use_temp_db(tmp_path, monkeypatch)
    db_module.init_db()
    identity = hash_record("sha256", "a" * 64)
    _insert_sample(1, identity)

    noncanonical_root = _result(root="H", mode="maj")
    noncanonical_root.mode_evidence.update(
        {
            "major_third_energy": 0.8,
            "minor_third_energy": 0.2,
            "contrast": 0.6,
            "mode": "maj",
        }
    )
    with pytest.raises(ValueError, match="root evidence"):
        write_key_analysis_v2_shadow(
            sample_id=1, source_identity=identity, result=noncanonical_root
        )

    contradictory_mode = _result(root="C", mode="min")
    contradictory_mode.mode_evidence.update(
        {
            "major_third_energy": 1.0,
            "minor_third_energy": 0.0,
            "contrast": 1.0,
            "mode": "min",
        }
    )
    with pytest.raises(ValueError, match="mode evidence"):
        write_key_analysis_v2_shadow(
            sample_id=1, source_identity=identity, result=contradictory_mode
        )

    negative_energy = _result(root="C", mode=None)
    negative_energy.mode_evidence.update(
        {
            "major_third_energy": -2.0,
            "minor_third_energy": -1.0,
            "contrast": -1.0 / 3.0,
        }
    )
    with pytest.raises(ValueError, match="mode evidence"):
        write_key_analysis_v2_shadow(
            sample_id=1, source_identity=identity, result=negative_energy
        )

    invalid_pearson_score = _result(root="C", mode=None)
    invalid_pearson_score.root_evidence["raw_top_score"] = 1.01
    with pytest.raises(ValueError, match="root evidence"):
        write_key_analysis_v2_shadow(
            sample_id=1, source_identity=identity, result=invalid_pearson_score
        )

    rounded_abstention = _result(root="C", mode=None)
    rounded_abstention.mode_evidence.update(
        {
            "major_third_energy": 1.3,
            "minor_third_energy": 0.7,
            "contrast": 0.3,
        }
    )
    write_key_analysis_v2_shadow(
        sample_id=1, source_identity=identity, result=rounded_abstention
    )
    assert (
        read_key_analysis_v2_shadow(sample_id=1, source_identity=identity)
        == rounded_abstention
    )


def test_sidecar_migrates_legacy_catalog_and_preserves_sha1_semantics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = _use_temp_db(tmp_path, monkeypatch)
    legacy_identity = hash_record("sha1", "b" * 40)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, path TEXT UNIQUE NOT NULL, hash TEXT)")
        conn.execute("CREATE TABLE features (sample_id INTEGER PRIMARY KEY, key TEXT, key_conf REAL)")
        conn.execute("INSERT INTO samples (id, path, hash) VALUES (1, 'legacy.wav', ?)", (legacy_identity["value"],))
        conn.execute("INSERT INTO features (sample_id, key, key_conf) VALUES (1, 'C', 0.5)")

    engine = db_module.init_db()
    with engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(key_analysis_v2_shadow)"))}
        legacy = conn.execute(text("SELECT key, key_conf FROM features WHERE sample_id = 1")).one()

    assert columns == {
        "sample_id",
        "source_hash",
        "source_hash_algorithm",
        "contract_version",
        "key",
        "key_mode",
        "key_root_evidence",
        "key_mode_evidence",
        "analyzed_at",
    }
    with engine.begin() as conn:
        feature_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(features)"))}
    assert "key_analysis_contract_version" not in feature_columns
    assert "key_root_evidence" not in feature_columns
    assert legacy == ("C", 0.5)
    assert db_module.find_sample_identity_by_path("legacy.wav") == (1, legacy_identity)

    write_key_analysis_v2_shadow(sample_id=1, source_identity=legacy_identity, result=_result())
    assert read_key_analysis_v2_shadow(sample_id=1, source_identity=legacy_identity) == _result()


def test_normal_v1_analysis_never_writes_shadow_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _use_temp_db(tmp_path, monkeypatch)
    engine = db_module.init_db()
    path = write_sine_wav(tmp_path / "v1.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"])
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO samples (id, path, duration, hash, hash_algorithm) VALUES (1, :path, 2.0, :hash, 'sha256')"),
            {"path": str(path), "hash": "a" * 64},
        )

    run_analyze(only_missing=True)

    with db_module.get_engine().begin() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM features WHERE sample_id = 1")).scalar_one() == 1
        assert conn.execute(text("SELECT COUNT(*) FROM key_analysis_v2_shadow")).scalar_one() == 0
    features = extract_features(path, 2.0)
    assert features is not None
    assert features.key_conf is not None
