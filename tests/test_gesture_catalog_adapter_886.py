"""Frozen acceptance for R&D Slice 3 — catalog → LibraryCandidate adapter (#680 / #886).

Docs authority: docs/GESTURE_CATALOG_ADAPTER_RND_SLICE3.md

These tests are intentionally RED until src/gesture_catalog_adapter.py exists.
Do not weaken assertions to fit an incorrect implementation.
Synthetic temp SQLite fixtures only — no private catalogs, paths, or audio.
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

# Planned public seam — missing module is the expected pre-implementation RED.
from src.gesture_catalog_adapter import (
    CatalogCandidateProjection,
    CatalogGestureRankResult,
    project_library_candidates_from_catalog,
    rank_gesture_against_catalog,
)


MFCC_DIM = 13


def _mfcc_blob(values: list[float] | None = None) -> bytes:
    arr = np.asarray(values if values is not None else [float(i) for i in range(MFCC_DIM)], dtype=np.float32)
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


def test_valid_oneshot_row_projects_one_library_candidate(tmp_path: Path) -> None:
    """1. Temp catalog with valid oneshot feature row → one valid LibraryCandidate."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=7, path="C:/synth/kick_a.wav")
    _insert_features(
        conn,
        sample_id=7,
        audio_class="oneshot",
        loudness=-11.5,
        brightness=900.0,
        mfcc_mean=_mfcc_blob([1.0] * MFCC_DIM),
    )
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert isinstance(projection, CatalogCandidateProjection)
    assert projection.status == "ok"
    assert len(projection.candidates) == 1
    cand = projection.candidates[0]
    assert isinstance(cand, LibraryCandidate)
    assert cand.sample_id == "7"
    assert cand.path == "C:/synth/kick_a.wav"
    assert cand.audio_class == "oneshot"
    assert cand.loudness == pytest.approx(-11.5)
    assert cand.brightness == pytest.approx(900.0)
    assert len(cand.mfcc13) == MFCC_DIM
    assert all(math.isfinite(x) for x in cand.mfcc13)


def test_mfcc_mean_float32_blob_decodes_to_13_finite(tmp_path: Path) -> None:
    """2. mfcc_mean float32 blob decodes to exactly 13 finite floats."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    values = [float(i) * 0.25 for i in range(MFCC_DIM)]
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob(values))
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert projection.status == "ok"
    assert projection.candidates[0].mfcc13 == pytest.approx(tuple(values))


def test_malformed_mfcc_blob_lengths_excluded(tmp_path: Path) -> None:
    """3. malformed/short/long MFCC blob excluded/fail-closed."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="short.wav")
    _insert_features(
        conn,
        sample_id=1,
        mfcc_mean=np.asarray([1.0, 2.0], dtype=np.float32).tobytes(),
    )
    _insert_sample(conn, sample_id=2, path="long.wav")
    _insert_features(
        conn,
        sample_id=2,
        mfcc_mean=np.asarray([1.0] * 20, dtype=np.float32).tobytes(),
    )
    _insert_sample(conn, sample_id=3, path="good.wav")
    _insert_features(conn, sample_id=3, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    ids = [c.sample_id for c in projection.candidates]
    assert ids == ["3"]
    assert projection.excluded_count >= 2


def test_nan_inf_mfcc_excluded(tmp_path: Path) -> None:
    """4. NaN/Inf MFCC excluded/fail-closed."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    bad = [0.0] * MFCC_DIM
    bad[0] = float("nan")
    _insert_sample(conn, sample_id=1, path="nan.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob(bad))
    inf = [0.0] * MFCC_DIM
    inf[1] = float("inf")
    _insert_sample(conn, sample_id=2, path="inf.wav")
    _insert_features(conn, sample_id=2, mfcc_mean=_mfcc_blob(inf))
    _insert_sample(conn, sample_id=3, path="good.wav")
    _insert_features(conn, sample_id=3, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert [c.sample_id for c in projection.candidates] == ["3"]


def test_missing_features_row_excluded(tmp_path: Path) -> None:
    """5. missing features row excluded."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="no_feat.wav")
    _insert_sample(conn, sample_id=2, path="with_feat.wav")
    _insert_features(conn, sample_id=2, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert [c.sample_id for c in projection.candidates] == ["2"]
    assert projection.excluded_count >= 1


def test_missing_loudness_or_brightness_excluded(tmp_path: Path) -> None:
    """6. missing loudness/brightness excluded."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="no_loud.wav")
    _insert_features(conn, sample_id=1, loudness=None, brightness=1200.0, mfcc_mean=_mfcc_blob())
    _insert_sample(conn, sample_id=2, path="no_bright.wav")
    _insert_features(conn, sample_id=2, loudness=-12.0, brightness=None, mfcc_mean=_mfcc_blob())
    _insert_sample(conn, sample_id=3, path="good.wav")
    _insert_features(conn, sample_id=3, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert [c.sample_id for c in projection.candidates] == ["3"]


def test_loop_row_excluded(tmp_path: Path) -> None:
    """7. loop row excluded."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="loop.wav", duration=4.0)
    _insert_features(conn, sample_id=1, audio_class="loop", mfcc_mean=_mfcc_blob())
    _insert_sample(conn, sample_id=2, path="hit.wav", duration=0.4)
    _insert_features(conn, sample_id=2, audio_class="oneshot", mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert [c.sample_id for c in projection.candidates] == ["2"]
    assert all(c.audio_class == "oneshot" for c in projection.candidates)


def test_empty_catalog_empty_projection(tmp_path: Path) -> None:
    """8. empty catalog → empty projection/result."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert projection.status == "empty"
    assert projection.candidates == ()
    assert projection.excluded_count == 0


def test_missing_catalog_path_fail_soft(tmp_path: Path) -> None:
    """9. missing catalog path → defined fail-soft result, no crash."""
    missing = tmp_path / "does_not_exist.db"
    projection = project_library_candidates_from_catalog(missing)
    assert projection.status == "missing_catalog"
    assert projection.candidates == ()

    result = rank_gesture_against_catalog(_analysis(), missing, top_n=3)
    assert isinstance(result, CatalogGestureRankResult)
    assert result.status == "missing_catalog"
    assert result.candidates == ()
    assert result.rankings == ()


def test_read_only_adapter_no_writes_or_schema_changes(tmp_path: Path) -> None:
    """10. read-only adapter performs no writes/schema changes."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=1, path="a.wav")
    _insert_features(conn, sample_id=1, mfcc_mean=_mfcc_blob())
    conn.commit()
    before_tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    }
    before_feat = conn.execute(
        "SELECT sample_id, loudness, brightness, class, mfcc_mean FROM features"
    ).fetchall()
    conn.close()
    before_mtime = db.stat().st_mtime_ns

    project_library_candidates_from_catalog(db)
    rank_gesture_against_catalog(_analysis(), db, top_n=2)

    after_mtime = db.stat().st_mtime_ns
    assert after_mtime == before_mtime
    conn = sqlite3.connect(db)
    after_tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    }
    after_feat = conn.execute(
        "SELECT sample_id, loudness, brightness, class, mfcc_mean FROM features"
    ).fetchall()
    conn.close()
    assert after_tables == before_tables
    assert after_feat == before_feat


def test_stable_sample_identity_tie_break_via_882(tmp_path: Path) -> None:
    """11. stable sample identity tie-break remains deterministic."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    # Identical features, different ids — #882 lexicographic sample_id tie-break.
    for sid, name in ((3, "c.wav"), (1, "a.wav"), (2, "b.wav")):
        _insert_sample(conn, sample_id=sid, path=name)
        _insert_features(
            conn,
            sample_id=sid,
            loudness=-14.0,
            brightness=1000.0,
            mfcc_mean=_mfcc_blob([0.0] * MFCC_DIM),
        )
    conn.commit()
    conn.close()

    # Gesture prototype aligned near the shared candidate features.
    analysis = GestureAnalysis(
        events=(
            GestureEvent(
                0.2,
                (10 ** (-14.0 / 20.0), 1000.0) + (0.0,) * MFCC_DIM,
                0,
            ),
        ),
        sample_rate=44100,
        duration_sec=1.0,
        feature_dim=FEATURE_DIM,
        status="ok",
    )
    result = rank_gesture_against_catalog(analysis, db, top_n=3)
    assert result.status == "ok"
    ids = [r.sample_id for r in result.rankings[0].ranked]
    assert ids == ["1", "2", "3"]


def test_sql_order_permutation_same_semantic_result(tmp_path: Path) -> None:
    """12. SQL/input order permutation does not change semantic result."""
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
                brightness=800.0 + 100 * sid,
                mfcc_mean=_mfcc_blob([float(sid)] * MFCC_DIM),
            )
        conn.commit()
        conn.close()

    analysis = _analysis()
    ra = rank_gesture_against_catalog(analysis, db_a, top_n=3)
    rb = rank_gesture_against_catalog(analysis, db_b, top_n=3)
    assert ra.status == rb.status == "ok"
    assert ra.candidates == rb.candidates
    assert ra.rankings == rb.rankings


def test_integration_uses_882_ranker_not_duplicate_math(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """13. integration uses rank_gesture_library_candidates(...) rather than duplicating ranking math."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    _insert_sample(conn, sample_id=9, path="hit.wav")
    _insert_features(conn, sample_id=9, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    calls: list[tuple[object, ...]] = []

    def _spy(analysis, candidates, *, top_n=5):
        calls.append((analysis, tuple(candidates), top_n))
        return rank_gesture_library_candidates(analysis, candidates, top_n=top_n)

    monkeypatch.setattr(
        "src.gesture_catalog_adapter.rank_gesture_library_candidates",
        _spy,
    )
    analysis = _analysis()
    result = rank_gesture_against_catalog(analysis, db, top_n=2)
    assert len(calls) == 1
    assert calls[0][0] is analysis
    assert calls[0][2] == 2
    assert result.rankings
    assert all(isinstance(row, ClusterRanking) for row in result.rankings)

    mod = importlib.import_module("src.gesture_catalog_adapter")
    src = Path(mod.__file__).read_text(encoding="utf-8")
    assert "rank_gesture_library_candidates" in src
    # Adapter must not re-implement distance/normalization primitives.
    for banned in ("np.linalg.norm", "zscore", "_zscore", "CLUSTER_DISTANCE"):
        assert banned not in src


def test_882_focused_suite_still_importable_and_green() -> None:
    """14. #882 focused tests remain green unchanged (collection smoke + marker)."""
    # Behavioral guard: ranking module import surface unchanged for LibraryCandidate.
    from src import gesture_library_ranking as ranking

    assert hasattr(ranking, "LibraryCandidate")
    assert hasattr(ranking, "rank_gesture_library_candidates")
    fields = ranking.LibraryCandidate.__dataclass_fields__
    assert set(fields) == {
        "sample_id",
        "path",
        "audio_class",
        "loudness",
        "brightness",
        "mfcc13",
    }


def test_slice1_gesture_analysis_not_mutated(tmp_path: Path) -> None:
    """15. Slice-1 gesture data remains unmodified."""
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


def test_adapter_import_boundary_no_workbench_qml_pattern_embed() -> None:
    """Architecture: adapter must not import Workbench/QML/Pattern/embed/search."""
    mod = importlib.import_module("src.gesture_catalog_adapter")
    imported = _imported_module_names(mod)
    for banned in (
        "workbench_catalog",
        "workbench_qml",
        "workbench_controller",
        "pattern_core",
        "channel_rack",
        "embed",
        "search",
        "torch",
        "clap",
    ):
        assert banned not in imported


def test_projection_candidates_sorted_by_sample_id(tmp_path: Path) -> None:
    """Projection output is deterministic: sorted by sample_id ascending."""
    db = tmp_path / "catalog.db"
    conn = _init_catalog(db)
    for sid in (10, 2, 3):
        _insert_sample(conn, sample_id=sid, path=f"s{sid}.wav")
        _insert_features(conn, sample_id=sid, mfcc_mean=_mfcc_blob())
    conn.commit()
    conn.close()

    projection = project_library_candidates_from_catalog(db)
    assert [c.sample_id for c in projection.candidates] == ["10", "2", "3"]
