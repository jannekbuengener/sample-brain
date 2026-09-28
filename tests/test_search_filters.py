from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

import src.config as config_module
import src.db as db_module
from src.config import set_db_path
from src.db import init_db, list_sample_tags, replace_sample_tags
from src.key_analysis_v2 import (
    KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    KeyAnalysisV2Result,
    write_key_analysis_v2_features,
)
from src.search_filters import (
    SearchFilters,
    key_matches_scale,
    resolve_filtered_sample_ids,
    sync_pred_type_tags,
)


def _v2_result(*, root: str = "C", mode: str | None = "maj") -> KeyAnalysisV2Result:
    if mode is None:
        mode_evidence = {
            "kind": "third_contrast",
            "major_third_energy": 0.2,
            "minor_third_energy": 0.2,
            "contrast": 0.0,
            "threshold": 0.3,
            "mode": None,
            "root": root,
            "root_source": "joint_24_profile_pearson",
        }
    elif mode == "maj":
        mode_evidence = {
            "kind": "third_contrast",
            "major_third_energy": 0.8,
            "minor_third_energy": 0.2,
            "contrast": 0.6,
            "threshold": 0.3,
            "mode": "maj",
            "root": root,
            "root_source": "joint_24_profile_pearson",
        }
    else:
        mode_evidence = {
            "kind": "third_contrast",
            "major_third_energy": 0.2,
            "minor_third_energy": 0.8,
            "contrast": 0.6,
            "threshold": 0.3,
            "mode": "min",
            "root": root,
            "root_source": "joint_24_profile_pearson",
        }
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
        mode_evidence=mode_evidence,
        contract_version=KEY_ANALYSIS_V2_SHADOW_CONTRACT_VERSION,
    )


def _insert_sample(
    sample_id: int,
    *,
    path: str,
    duration: float = 1.0,
    hash_value: str | None = None,
) -> None:
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO samples (id, path, hash, hash_algorithm, duration)
                VALUES (:id, :path, :hash, 'sha256', :duration)
                """
            ),
            {
                "id": sample_id,
                "path": path,
                "hash": hash_value or ("a" * 64),
                "duration": duration,
            },
        )


def _insert_v1_features(
    sample_id: int,
    *,
    key: str | None,
    bpm: float = 120.0,
    pred_type: str | None = None,
    key_conf: float | None = 0.55,
) -> None:
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (sample_id, bpm, key, key_conf, pred_type, class)
                VALUES (:sample_id, :bpm, :key, :key_conf, :pred_type, 'percussive')
                """
            ),
            {
                "sample_id": sample_id,
                "bpm": bpm,
                "key": key,
                "key_conf": key_conf,
                "pred_type": pred_type,
            },
        )


@pytest.fixture
def filter_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "filters.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    init_db()

    _insert_sample(1, path="/kick.wav", duration=0.5, hash_value="hash-1")
    _insert_sample(2, path="/snare.wav", duration=1.5, hash_value="hash-2")
    _insert_v1_features(1, key="Am", bpm=128.0, pred_type="kick")
    _insert_v1_features(2, key="C", bpm=90.0, pred_type="snare")
    replace_sample_tags(1, [("kick", "pred_type")])
    return db_path


@pytest.fixture
def version_aware_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Catalog covering V1, V2, and fail-closed key contracts for Search (#658)."""

    db_path = tmp_path / "version_aware_filters.db"
    monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
    set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
    config_module.DB_PATH = db_path
    init_db()

    # 1: V1 modeful Am
    _insert_sample(1, path="/v1-am.wav", duration=0.5, hash_value="h1" + ("a" * 62))
    _insert_v1_features(1, key="Am", bpm=128.0, pred_type="kick")
    replace_sample_tags(1, [("kick", "manual")])

    # 2: V1 root-only C
    _insert_sample(2, path="/v1-c.wav", duration=1.5, hash_value="h2" + ("a" * 62))
    _insert_v1_features(2, key="C", bpm=90.0, pred_type="snare")

    # 3: V1 Cmaj
    _insert_sample(3, path="/v1-cmaj.wav", duration=2.0, hash_value="h3" + ("a" * 62))
    _insert_v1_features(3, key="Cmaj", bpm=100.0, pred_type="loop")

    # 4: valid V2 modeful Cmaj
    _insert_sample(4, path="/v2-cmaj.wav", duration=1.0, hash_value="h4" + ("a" * 62))
    write_key_analysis_v2_features(sample_id=4, result=_v2_result(root="C", mode="maj"))
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE features SET bpm = 110.0, pred_type = 'pad' WHERE sample_id = 4")
        )

    # 5: valid V2 modeful Amin
    _insert_sample(5, path="/v2-amin.wav", duration=1.0, hash_value="h5" + ("a" * 62))
    write_key_analysis_v2_features(sample_id=5, result=_v2_result(root="A", mode="min"))
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE features SET bpm = 120.0, pred_type = 'bass' WHERE sample_id = 5")
        )

    # 6: valid V2 root-only G
    _insert_sample(6, path="/v2-g.wav", duration=1.0, hash_value="h6" + ("a" * 62))
    write_key_analysis_v2_features(sample_id=6, result=_v2_result(root="G", mode=None))
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE features SET bpm = 95.0, pred_type = 'hit' WHERE sample_id = 6")
        )

    # 7: unknown contract — raw key would match Cmaj
    _insert_sample(7, path="/unknown.wav", duration=1.0, hash_value="h7" + ("a" * 62))
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (
                    sample_id, bpm, key, key_conf, pred_type,
                    key_analysis_contract_version
                ) VALUES (7, 105.0, 'Cmaj', NULL, 'fx', 99)
                """
            )
        )

    # 8: malformed V2 — raw key would match Cmaj
    _insert_sample(8, path="/malformed.wav", duration=1.0, hash_value="h8" + ("a" * 62))
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (
                    sample_id, bpm, key, key_conf, key_mode, key_mode_evidence,
                    key_analysis_contract_version, key_root_evidence, pred_type
                ) VALUES (
                    8, 106.0, 'Cmaj', NULL, 'maj', :mode_evidence, 2, :root_evidence, 'fx'
                )
                """
            ),
            {
                "mode_evidence": json.dumps(
                    _v2_result(root="C", mode="maj").mode_evidence,
                    sort_keys=True,
                ),
                "root_evidence": json.dumps({"kind": "not-v2"}, sort_keys=True),
            },
        )

    # 9: stale hybrid — V1 overwrite left contract_version=2; raw key Amin
    _insert_sample(9, path="/stale.wav", duration=1.0, hash_value="h9" + ("a" * 62))
    write_key_analysis_v2_features(sample_id=9, result=_v2_result(root="C", mode="maj"))
    with db_module.get_engine().begin() as conn:
        conn.execute(
            text(
                """
                UPDATE features
                SET key = 'Amin', key_conf = 0.77, key_mode = 'min',
                    bpm = 107.0, pred_type = 'fx'
                WHERE sample_id = 9
                """
            )
        )

    return db_path


class TestSearchFilters:
    def test_key_matches_scale_minor(self):
        assert key_matches_scale("Am", "minor")
        assert not key_matches_scale("C", "minor")

    def test_resolve_filtered_sample_ids_by_pred_type(self, filter_db):
        sample_ids = resolve_filtered_sample_ids(
            SearchFilters(pred_type="kick")
        )
        assert sample_ids == {1}

    def test_resolve_filtered_sample_ids_by_tag(self, filter_db):
        sample_ids = resolve_filtered_sample_ids(SearchFilters(tags=("kick",)))
        assert sample_ids == {1}

    def test_resolve_filtered_sample_ids_by_duration(self, filter_db):
        sample_ids = resolve_filtered_sample_ids(
            SearchFilters(min_duration=1.0, max_duration=2.0)
        )
        assert sample_ids == {2}

    def test_sync_pred_type_tags(self, filter_db):
        synced = sync_pred_type_tags()
        assert synced >= 1
        kick_tags = list_sample_tags(sample_id=1)
        assert any(row["tag"] == "kick" for row in kick_tags)
        snare_tags = list_sample_tags(sample_id=2)
        assert any(row["tag"] == "snare" for row in snare_tags)


class TestVersionAwareSearchKeyFilters:
    """Frozen acceptance matrix for #658 — version-aware Search key/scale."""

    def test_v1_exact_key_compatible(self, version_aware_db):
        assert resolve_filtered_sample_ids(SearchFilters(key="Am")) == {1}
        assert resolve_filtered_sample_ids(SearchFilters(key="am")) == {1}

    def test_v1_major_scale_compatible(self, version_aware_db):
        ids = resolve_filtered_sample_ids(SearchFilters(scale="major"))
        assert 3 in ids
        assert 2 not in ids
        assert 1 not in ids

    def test_v1_minor_scale_compatible(self, version_aware_db):
        ids = resolve_filtered_sample_ids(SearchFilters(scale="minor"))
        assert 1 in ids
        assert 2 not in ids
        assert 3 not in ids

    def test_v1_root_only_matches_neither_scale(self, version_aware_db):
        assert 2 not in resolve_filtered_sample_ids(SearchFilters(scale="major"))
        assert 2 not in resolve_filtered_sample_ids(SearchFilters(scale="minor"))
        assert resolve_filtered_sample_ids(SearchFilters(key="C")) == {2}

    def test_v2_modeful_exact_key_match(self, version_aware_db):
        assert resolve_filtered_sample_ids(SearchFilters(key="Cmaj")) == {3, 4}
        assert resolve_filtered_sample_ids(SearchFilters(key="cmaj")) == {3, 4}
        assert resolve_filtered_sample_ids(SearchFilters(key="Amin")) == {5}

    def test_v2_modeful_correct_scale(self, version_aware_db):
        major_ids = resolve_filtered_sample_ids(SearchFilters(scale="major"))
        minor_ids = resolve_filtered_sample_ids(SearchFilters(scale="minor"))
        assert 4 in major_ids
        assert 5 in minor_ids
        assert 4 not in minor_ids
        assert 5 not in major_ids

    def test_v2_modeful_wrong_scale_no_match(self, version_aware_db):
        assert resolve_filtered_sample_ids(
            SearchFilters(key="Cmaj", scale="minor")
        ) == set()
        assert resolve_filtered_sample_ids(
            SearchFilters(key="Amin", scale="major")
        ) == set()

    def test_v2_root_only_exact_key_and_no_scale(self, version_aware_db):
        assert resolve_filtered_sample_ids(SearchFilters(key="G")) == {6}
        assert 6 not in resolve_filtered_sample_ids(SearchFilters(scale="major"))
        assert 6 not in resolve_filtered_sample_ids(SearchFilters(scale="minor"))

    def test_unknown_contract_no_key_match(self, version_aware_db):
        ids = resolve_filtered_sample_ids(SearchFilters(key="Cmaj"))
        assert 7 not in ids
        assert ids == {3, 4}

    def test_malformed_v2_no_key_match(self, version_aware_db):
        ids = resolve_filtered_sample_ids(SearchFilters(key="Cmaj"))
        assert 8 not in ids

    def test_stale_hybrid_no_key_match(self, version_aware_db):
        assert resolve_filtered_sample_ids(SearchFilters(key="Amin")) == {5}
        assert 9 not in resolve_filtered_sample_ids(SearchFilters(key="Amin"))
        assert 9 not in resolve_filtered_sample_ids(SearchFilters(scale="minor"))

    def test_no_raw_key_fallback_for_invalid_contracts(self, version_aware_db):
        """Invalid rows keep a matching raw features.key string but must not match."""

        with db_module.get_engine().begin() as conn:
            raw_keys = {
                int(row[0]): row[1]
                for row in conn.execute(
                    text(
                        "SELECT sample_id, key FROM features "
                        "WHERE sample_id IN (7, 8, 9)"
                    )
                ).fetchall()
            }
        assert raw_keys[7] == "Cmaj"
        assert raw_keys[8] == "Cmaj"
        assert raw_keys[9] == "Amin"

        assert 7 not in resolve_filtered_sample_ids(SearchFilters(key="Cmaj"))
        assert 8 not in resolve_filtered_sample_ids(SearchFilters(key="Cmaj"))
        assert 9 not in resolve_filtered_sample_ids(SearchFilters(key="Amin"))

    def test_key_and_scale_and_semantics(self, version_aware_db):
        assert resolve_filtered_sample_ids(
            SearchFilters(key="Cmaj", scale="major")
        ) == {3, 4}
        assert resolve_filtered_sample_ids(
            SearchFilters(key="Cmaj", scale="minor")
        ) == set()

    def test_bpm_only_ignores_invalid_key_contract(self, version_aware_db):
        ids = resolve_filtered_sample_ids(
            SearchFilters(min_bpm=104.0, max_bpm=108.0)
        )
        assert ids == {7, 8, 9}

    def test_tag_only_ignores_invalid_key_contract(self, version_aware_db):
        replace_sample_tags(7, [("special", "manual")])
        assert resolve_filtered_sample_ids(SearchFilters(tags=("special",))) == {7}

    def test_duration_only_unchanged(self, version_aware_db):
        assert resolve_filtered_sample_ids(
            SearchFilters(min_duration=1.4, max_duration=1.6)
        ) == {2}

    def test_pred_type_only_unchanged(self, version_aware_db):
        assert resolve_filtered_sample_ids(SearchFilters(pred_type="kick")) == {1}
        assert resolve_filtered_sample_ids(SearchFilters(pred_type="fx")) == {7, 8, 9}

    def test_mixed_filters_deterministic(self, version_aware_db):
        ids = resolve_filtered_sample_ids(
            SearchFilters(min_bpm=100.0, max_bpm=130.0, key="Cmaj", scale="major")
        )
        assert ids == {3, 4}

    def test_single_batch_read_not_n_plus_one(self, version_aware_db):
        with patch(
            "src.search_filters.read_key_analysis_feature_rows",
            wraps=db_module.read_key_analysis_feature_rows,
        ) as batch_read:
            resolve_filtered_sample_ids(SearchFilters(key="Cmaj", scale="major"))
            assert batch_read.call_count == 1

        with patch(
            "src.search_filters.read_key_analysis_feature_rows",
            wraps=db_module.read_key_analysis_feature_rows,
        ) as batch_read:
            resolve_filtered_sample_ids(SearchFilters(pred_type="kick"))
            assert batch_read.call_count == 0
