from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from src import config
from src.db import get_engine, init_db
from src.matching import (
    MatchCandidate,
    MatchProfile,
    collect_matches,
    match_candidates,
    run_match,
    score_bpm_match,
)


def _seed_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "catalog" / "matching.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(config, "DB_PATH", db_path)
    init_db()
    return db_path


class TestMatchCandidates:
    def test_identical_bpm_ranks_higher_than_close_bpm(self):
        profile = MatchProfile(target_bpm=128.0, limit=None)
        candidates = [
            MatchCandidate(sample_id=2, path="/synthetic/close.wav", bpm=124.0),
            MatchCandidate(sample_id=1, path="/synthetic/exact.wav", bpm=128.0),
        ]

        results = match_candidates(candidates, profile)

        assert [result.sample_id for result in results] == [1, 2]
        assert results[0].bpm_score == pytest.approx(1.0)
        assert results[1].bpm_score == pytest.approx(0.5)

    def test_half_time_candidate_gets_plausible_bonus(self):
        profile = MatchProfile(target_bpm=140.0, limit=None)
        candidates = [
            MatchCandidate(sample_id=1, path="/synthetic/exact.wav", bpm=140.0),
            MatchCandidate(sample_id=2, path="/synthetic/half.wav", bpm=70.0),
            MatchCandidate(sample_id=3, path="/synthetic/far.wav", bpm=100.0),
        ]

        results = match_candidates(candidates, profile)

        assert [result.sample_id for result in results] == [1, 2, 3]
        assert score_bpm_match(70.0, 140.0, 8.0) == pytest.approx(0.9)
        assert results[1].bpm_score == pytest.approx(0.9)
        assert "half-time" in results[1].reasons[0]

    def test_missing_fields_do_not_crash(self):
        profile = MatchProfile(
            target_bpm=128.0, target_key="Am", desired_type="kick", limit=None
        )
        candidates = [
            MatchCandidate(
                sample_id=1,
                path="/synthetic/full.wav",
                bpm=128.0,
                key="A",
                pred_type="kick",
            ),
            MatchCandidate(
                sample_id=2,
                path="/synthetic/missing.wav",
                bpm=None,
                key=None,
                pred_type=None,
            ),
        ]

        results = match_candidates(candidates, profile)

        assert [result.sample_id for result in results] == [1, 2]
        assert results[1].total_score == pytest.approx(0.0)
        assert "bpm missing" in results[1].reasons
        assert "key missing" in results[1].reasons
        assert "type missing" in results[1].reasons

    def test_key_and_type_matches_improve_total_score(self):
        profile = MatchProfile(
            target_bpm=128.0, target_key="Am", desired_type="kick", limit=None
        )
        candidates = [
            MatchCandidate(
                sample_id=2,
                path="/synthetic/mismatch.wav",
                bpm=128.0,
                key="C",
                pred_type="snare",
            ),
            MatchCandidate(
                sample_id=1,
                path="/synthetic/match.wav",
                bpm=128.0,
                key="A",
                pred_type="kick",
            ),
        ]

        results = match_candidates(candidates, profile)

        assert [result.sample_id for result in results] == [1, 2]
        assert results[0].key_score == pytest.approx(1.0)
        assert results[0].type_score == pytest.approx(1.0)
        assert results[0].total_score > results[1].total_score

    def test_sorting_is_deterministic_for_ties(self):
        profile = MatchProfile(target_bpm=128.0, limit=None)
        candidates = [
            MatchCandidate(sample_id=30, path="/synthetic/c.wav", bpm=128.0),
            MatchCandidate(sample_id=10, path="/synthetic/a.wav", bpm=128.0),
        ]

        first = match_candidates(candidates, profile)
        second = match_candidates(candidates, profile)

        assert [result.sample_id for result in first] == [10, 30]
        assert [result.sample_id for result in second] == [10, 30]

    def test_limit_is_applied(self):
        profile = MatchProfile(target_bpm=128.0, limit=1)
        candidates = [
            MatchCandidate(sample_id=1, path="/synthetic/first.wav", bpm=128.0),
            MatchCandidate(sample_id=2, path="/synthetic/second.wav", bpm=124.0),
        ]

        results = match_candidates(candidates, profile)

        assert len(results) == 1
        assert results[0].sample_id == 1


class TestCatalogMatching:
    def test_collect_matches_reads_catalog_data(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        _seed_catalog(tmp_path, monkeypatch)
        engine = get_engine()
        with engine.begin() as conn:
            conn.execute(text("""
                    INSERT INTO samples (id, path, relpath, duration, hash)
                    VALUES
                        (1, '/synthetic/kick.wav', 'kick.wav', 0.8, 'h1'),
                        (2, '/synthetic/loop.wav', 'loop.wav', 2.0, 'h2')
                    """))
            conn.execute(text("""
                    INSERT INTO features (sample_id, bpm, key, pred_type)
                    VALUES
                        (1, 128.0, 'A', 'kick'),
                        (2, 64.0, 'C', 'loop')
                    """))

        result = collect_matches(
            MatchProfile(target_bpm=128.0, target_key="Am", desired_type="kick")
        )

        assert result.ok
        assert [match.sample_id for match in result.matches] == [1, 2]
        assert result.matches[0].path == "/synthetic/kick.wav"
        assert result.matches[1].bpm_score == pytest.approx(0.9)

    def test_run_match_prints_info_when_catalog_has_no_features(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        _seed_catalog(tmp_path, monkeypatch)

        run_match(target_bpm=128.0)
        captured = capsys.readouterr()

        assert "No analyzed samples available for matching" in captured.out
