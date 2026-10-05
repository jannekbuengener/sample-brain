"""Frozen acceptance for R&D Slice 3 — catalog → LibraryCandidate adapter (#680 / #886).

Docs authority: docs/GESTURE_CATALOG_ADAPTER_RND_SLICE3.md

Intentionally RED until src/gesture_catalog_adapter.py exists.
Synthetic tmp_path SQLite only — no private catalogs, paths, or audio.
"""

from __future__ import annotations

import ast
import importlib
import math
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from src.gesture_analysis import FEATURE_DIM, GestureAnalysis, GestureEvent
from src.gesture_library_ranking import (
    ClusterRanking,
    LibraryCandidate,
    rank_gesture_library_candidates,
)

from src.gesture_catalog_adapter import (
    load_gesture_library_candidates,
    rank_gesture_against_catalog,
)


MFCC_DIM = 13


def _mfcc_blob(values: list[float] | None = None) -> bytes:
    arr = np.asarray(
        values if values is not None else [float(i) for i in range(MFCC_DIM)],
        dtype=np.float32,
    )
    assert arr.shape == (MFCC_DIM,)
    return arr.tobytes()


def _init_catalog(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE samples (
            id INTEGER PRIMARY KEY,
            path TEXT UNIQUE,
            relpath TEXT,
            samplerate INTEGER,
            channels INTEGER,
            duration REAL,
            size_bytes INTEGER,
            hash TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE features (
            sample_id INTEGER PRIMARY KEY,
            bpm REAL,
            key TEXT,
            key_conf REAL,
            loudness REAL,
            brightness REAL,
            mfcc_mean BLOB,
            mfcc_std BLOB,
            chroma_mean BLOB,
            chroma_std BLOB,
            class TEXT,
            FOREIGN KEY(sample_id) REFERENCES samples(id)
        )
        """
    )
    conn.commit()
    return conn


def _insert_sample(
    conn: sqlite3.Connection,
    *,
    sample_id: int,
    path: str,
    duration: float = 0.5,
) -> None:
    conn.execute(
        """
        INSERT INTO samples (id, path, relpath, samplerate, channels, duration, size_bytes, hash)
        VALUES (?, ?, ?, 44100, 1, ?, 100, ?)
        """,
        (sample_id, path, Path(path).name, duration, f"hash-{sample_id}"),
    )


def _insert_features(
    conn: sqlite3.Connection,
    *,
    sample_id: int,
    audio_class: str = "oneshot",
    loudness: float | None = -12.0,
    brightness: float | None = 1200.0,
    mfcc_mean: bytes | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO features (
            sample_id, bpm, key, key_conf, loudness, brightness,
            mfcc_mean, mfcc_std, chroma_mean, chroma_std, class
        ) VALUES (?, NULL, NULL, NULL, ?, ?, ?, NULL, NULL, NULL, ?)
        """,
        (sample_id, loudness, brightness, mfcc_mean, audio_class),
    )


def _analysis(cluster_id: int = 0) -> GestureAnalysis:
    vec = (0.25, 1200.0) + tuple(float(i) for i in range(MFCC_DIM))
    assert len(vec) == FEATURE_DIM
    return GestureAnalysis(
        events=(GestureEvent(0.2, vec, cluster_id),),
        sample_rate=44100,
        duration_sec=1.0,
        feature_dim=FEATURE_DIM,
        status="ok",
    )


def _imported_module_names(mod: object) -> set[str]:
    path = Path(getattr(mod, "__file__"))
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def test_01_valid_temp_catalog_row_projects_library_candidate(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=7, path="synth/kick_a.wav")
    _insert_features(
        conn,
        sample_id=7,
        loudness=-11.5,
        brightness=900.0,
        mfcc_mean=_mfcc_blob([1.0] * MFCC_DIM),
    )
    conn.commit()
    conn.close()

    candidates = load_gesture_library_candidates(db)
    assert len(candidates) == 1
    assert isinstance(candidates[0], LibraryCandidate)


def test_02_sample_id_exact_str_of_samples_id(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=42, path="x.wav")
    _insert_features(conn, sample_id=42, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    candidates = load_gesture_library_candidates(db)
    assert candidates[0].sample_id == "42"
    assert candidates[0].sample_id == str(42)


def test_03_path_preserved_as_optional_reference(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="packs/ref/hit.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    candidates = load_gesture_library_candidates(db)
    assert candidates[0].path == "packs/ref/hit.wav"


def test_04_oneshot_eligible(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="hit.wav")
    _insert_features(conn, sample_id=1, audio_class="oneshot", mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    candidates = load_gesture_library_candidates(db)
    assert len(candidates) == 1
    assert candidates[0].audio_class == "oneshot"


def test_05_loop_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="loop.wav", duration=4.0)
    _insert_features(conn, sample_id=1, audio_class="loop", mfcc_mean=_mfcc_blob())
    _insert_sample(conn, sample_id=2, path="hit.wav")
    _insert_features(conn, sample_id=2, audio_class="oneshot", mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    candidates = load_gesture_library_candidates(db)
    assert [c.sample_id for c in candidates] == ["2"]


def test_06_missing_feature_row_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="no_feat.wav")
    _insert_sample(conn, sample_id=2, path="ok.wav")
    _insert_features(conn, sample_id=2, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    assert [c.sample_id for c in load_gesture_library_candidates(db)] == ["2"]


def test_07_loudness_none_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, loudness=None, brightness=1000.0, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_08_brightness_none_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, loudness=-12.0, brightness=None, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_09_nan_loudness_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(
        conn, sample_id=1, loudness=float("nan"), brightness=1000.0, mfcc_mean=_mfcc_blob()
    )
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_10_inf_brightness_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(
        conn, sample_id=1, loudness=-12.0, brightness=float("inf"), mfcc_mean=_mfcc_blob()
    )
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_11_valid_mfcc_blob_exactly_13_floats(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    values = [float(i) * 0.1 for i in range(MFCC_DIM)]
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob(values))
    conn.commit()
    conn.close()

    candidates = load_gesture_library_candidates(db)
    assert len(candidates[0].mfcc13) == 13
    assert candidates[0].mfcc13 == pytest.approx(tuple(values))
    assert all(math.isfinite(x) for x in candidates[0].mfcc13)


def test_12_short_mfcc_blob_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(
        conn, sample_id=1, mfcc_mean=np.asarray([1.0, 2.0], dtype=np.float32).tobytes()
    )
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_13_long_mfcc_blob_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(
        conn, sample_id=1, mfcc_mean=np.asarray([1.0] * 20, dtype=np.float32).tobytes()
    )
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_14_malformed_byte_length_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    # 13 float32 would be 52 bytes; 51 is malformed.
    _insert_features(conn, sample_id=1, mfcc_mean=b"\x00" * 51)
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_15_nan_mfcc_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    bad = [0.0] * MFCC_DIM
    bad[0] = float("nan")
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob(bad))
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_16_inf_mfcc_excluded(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    bad = [0.0] * MFCC_DIM
    bad[2] = float("inf")
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob(bad))
    conn.commit()
    conn.close()

    assert load_gesture_library_candidates(db) == ()


def test_17_multiple_valid_rows_deterministic_numeric_order(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    for sid in (10, 2, 3):
        _insert_sample(conn, sample_id=sid, path=f"s{sid}.wav")
        _insert_features(conn, sample_id=sid, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    # Ascending numeric samples.id — not lexicographic str order.
    assert [c.sample_id for c in load_gesture_library_candidates(db)] == ["2", "3", "10"]


def test_18_sql_insertion_order_permutation_same_candidates(tmp_path: Path) -> None:
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    for db, order in ((db_a, (1, 2, 3)), (db_b, (3, 1, 2))):
        conn = _init_catalog(db)
        for sid in order:
            _insert_sample(conn, sample_id=sid, path=f"s{sid}.wav")
            _insert_features(
                conn,
                sample_id=sid,
                loudness=-10.0 - sid,
                brightness=800.0 + sid,
                mfcc_mean=_mfcc_blob([float(sid)] * MFCC_DIM),
            )
        conn.commit()
        conn.close()

    assert load_gesture_library_candidates(db_a) == load_gesture_library_candidates(db_b)


def test_19_missing_catalog_path_empty_tuple(tmp_path: Path) -> None:
    missing = tmp_path / "missing.db"
    assert load_gesture_library_candidates(missing) == ()


def test_20_missing_tables_or_corrupt_shape_fail_soft(tmp_path: Path) -> None:
    empty_file = tmp_path / "empty.db"
    empty_file.write_bytes(b"")
    assert load_gesture_library_candidates(empty_file) == ()

    no_features = tmp_path / "samples_only.db"
    conn = sqlite3.connect(no_features)
    conn.execute("CREATE TABLE samples (id INTEGER PRIMARY KEY, path TEXT)")
    conn.execute("INSERT INTO samples (id, path) VALUES (1, 'a.wav')")
    conn.commit()
    conn.close()
    assert load_gesture_library_candidates(no_features) == ()


def test_21_adapter_does_not_mutate_db(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob())
    conn.commit()
    before_tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }
    before_feat = conn.execute(
        "SELECT sample_id, loudness, brightness, class, mfcc_mean FROM features"
    ).fetchall()
    conn.close()
    before_mtime = db.stat().st_mtime_ns

    load_gesture_library_candidates(db)
    rank_gesture_against_catalog(_analysis(), db, top_n=2)

    assert db.stat().st_mtime_ns == before_mtime
    conn = sqlite3.connect(db)
    after_tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }
    after_feat = conn.execute(
        "SELECT sample_id, loudness, brightness, class, mfcc_mean FROM features"
    ).fetchall()
    conn.close()
    assert after_tables == before_tables
    assert after_feat == before_feat


def test_22_adapter_does_not_call_schema_init_migration(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _boom(*_a, **_k):
        calls.append("init_db")
        raise AssertionError("init_db must not be called")

    monkeypatch.setattr("src.db.init_db", _boom, raising=False)
    assert load_gesture_library_candidates(Path("definitely-missing-886.db")) == ()
    assert calls == []

    mod = importlib.import_module("src.gesture_catalog_adapter")
    imported = _imported_module_names(mod)
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "db" not in imported
    assert "init_db" not in src


def test_23_integration_seam_calls_existing_882_ranker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=9, path="hit.wav")
    _insert_features(conn, sample_id=9, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    calls: list[object] = []

    def _spy(analysis, candidates, *, top_n=5):
        calls.append((analysis, tuple(candidates), top_n))
        return rank_gesture_library_candidates(analysis, candidates, top_n=top_n)

    monkeypatch.setattr(
        "src.gesture_catalog_adapter.rank_gesture_library_candidates",
        _spy,
    )
    analysis = _analysis()
    rank_gesture_against_catalog(analysis, db, top_n=2)
    assert len(calls) == 1
    assert calls[0][0] is analysis
    assert calls[0][2] == 2


def test_24_882_ranking_result_type_returned_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    result = rank_gesture_against_catalog(_analysis(), db, top_n=1)
    assert isinstance(result, tuple)
    assert all(isinstance(row, ClusterRanking) for row in result)


def test_25_empty_candidate_projection_empty_ranked_per_882(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    conn.close()

    analysis = _analysis(cluster_id=3)
    expected = rank_gesture_library_candidates(analysis, (), top_n=5)
    actual = rank_gesture_against_catalog(analysis, db, top_n=5)
    assert actual == expected
    assert actual[0].cluster_id == 3
    assert actual[0].ranked == ()


def test_26_same_analysis_and_catalog_twice_identical(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob([0.5] * MFCC_DIM))
    _insert_sample(conn, sample_id=2, path="b.wav")
    _insert_features(
        conn,
        sample_id=2,
        loudness=-20.0,
        brightness=4000.0,
        mfcc_mean=_mfcc_blob([-1.0] * MFCC_DIM),
    )
    conn.commit()
    conn.close()

    analysis = _analysis()
    a = rank_gesture_against_catalog(analysis, db, top_n=2)
    b = rank_gesture_against_catalog(analysis, db, top_n=2)
    assert a == b
    assert load_gesture_library_candidates(db) == load_gesture_library_candidates(db)


def test_27_no_embedding_import_or_call() -> None:
    mod = importlib.import_module("src.gesture_catalog_adapter")
    imported = _imported_module_names(mod)
    for banned in ("embed", "search", "torch", "transformers"):
        assert banned not in imported


def test_28_no_pattern_channel_trigger_import_or_call() -> None:
    mod = importlib.import_module("src.gesture_catalog_adapter")
    imported = _imported_module_names(mod)
    for banned in ("pattern_core", "channel_rack"):
        assert banned not in imported
    result = rank_gesture_against_catalog(_analysis(), Path("missing-886.db"), top_n=1)
    # Missing catalog → empty candidates → #882 empty rankings (not Pattern objects).
    assert all(isinstance(row, ClusterRanking) for row in result)


def test_29_gesture_analysis_unchanged(tmp_path: Path) -> None:
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    analysis = _analysis(cluster_id=4)
    before_events = analysis.events
    before_onsets = [e.onset_time_sec for e in analysis.events]
    before_ids = [e.cluster_id for e in analysis.events]
    before_feats = [e.feature_vector for e in analysis.events]
    rank_gesture_against_catalog(analysis, db, top_n=1)
    assert analysis.events is before_events
    assert [e.onset_time_sec for e in analysis.events] == before_onsets
    assert [e.cluster_id for e in analysis.events] == before_ids
    assert [e.feature_vector for e in analysis.events] == before_feats


def test_30_no_workbench_qml_dependency() -> None:
    mod = importlib.import_module("src.gesture_catalog_adapter")
    imported = _imported_module_names(mod)
    for banned in (
        "workbench_catalog",
        "workbench_qml",
        "workbench_controller",
        "workbench_library",
    ):
        assert banned not in imported
