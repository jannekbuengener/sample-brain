from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

from src import config
from src.db import get_engine, init_db
from src.matching import (
    BPM_RELATION_DIRECT,
    BPM_RELATION_DOUBLE_TIME,
    BPM_RELATION_HALF_TIME,
    BPM_RELATION_NO_RESULT,
    DIMENSION_NO_RESULT,
    MatchCandidate,
    MatchProfile,
    collect_matches,
    match_candidates,
    run_match,
    score_bpm_match,
    score_candidate,
    semitone_hint,
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
        assert results[0].bpm_relation == BPM_RELATION_DIRECT
        assert results[0].tempo_multiplier == pytest.approx(1.0)
        assert results[1].bpm_score == pytest.approx(0.5)

    def test_half_time_candidate_exposes_structured_relation(self):
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
        assert results[1].bpm_relation == BPM_RELATION_HALF_TIME
        assert results[1].tempo_multiplier == pytest.approx(2.0)
        assert "half-time" in results[1].reasons[0]
        assert "70 -> 140" in results[1].reasons[0]

    def test_double_time_candidate_exposes_structured_relation(self):
        result = score_candidate(
            MatchCandidate(sample_id=1, path="/synthetic/double.wav", bpm=280.0),
            MatchProfile(target_bpm=140.0, limit=None),
        )

        assert result.bpm_score == pytest.approx(0.9)
        assert result.bpm_relation == BPM_RELATION_DOUBLE_TIME
        assert result.tempo_multiplier == pytest.approx(0.5)

    @pytest.mark.parametrize("bpm", [None, 0.0, -1.0, float("nan")])
    def test_missing_or_invalid_bpm_is_no_result(self, bpm: float | None):
        result = score_candidate(
            MatchCandidate(sample_id=1, path="/synthetic/bad-bpm.wav", bpm=bpm),
            MatchProfile(target_bpm=128.0, limit=None),
        )

        bpm_dimension = next(d for d in result.dimensions if d.name == "bpm")
        assert result.bpm_relation == BPM_RELATION_NO_RESULT
        assert result.tempo_multiplier is None
        assert bpm_dimension.status == DIMENSION_NO_RESULT
        assert not bpm_dimension.active
        assert result.total_score == pytest.approx(0.0)

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

    def test_missing_dimension_does_not_enter_score_denominator(self):
        result = score_candidate(
            MatchCandidate(
                sample_id=1,
                path="/synthetic/no-key.wav",
                bpm=128.0,
                key=None,
            ),
            MatchProfile(target_bpm=128.0, target_key="Amin", limit=None),
        )

        assert result.active_dimensions == ("bpm",)
        assert result.total_score == pytest.approx(1.0)
        key_dimension = next(d for d in result.dimensions if d.name == "key")
        assert key_dimension.status == DIMENSION_NO_RESULT
        assert not key_dimension.active

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

    def test_flat_and_sharp_key_normalization_reuses_canonical_parser(self):
        result = score_candidate(
            MatchCandidate(
                sample_id=1,
                path="/synthetic/flat.wav",
                bpm=128.0,
                key="Db minor",
            ),
            MatchProfile(target_bpm=128.0, target_key="C#min", limit=None),
        )

        assert result.key_score == pytest.approx(1.0)
        assert result.semitone_hint == 0

    @pytest.mark.parametrize(
        ("sample_key", "target_key", "expected"),
        [
            ("Cmaj", "C#maj", 1),
            ("C#maj", "Cmaj", -1),
            ("Cmaj", "F#maj", 6),
        ],
    )
    def test_semitone_hint_is_smallest_signed_shift(
        self, sample_key: str, target_key: str, expected: int
    ):
        assert semitone_hint(sample_key, target_key) == expected

    def test_major_minor_mismatch_does_not_claim_pitch_shift_fixes_harmony(self):
        result = score_candidate(
            MatchCandidate(
                sample_id=1,
                path="/synthetic/mode.wav",
                bpm=128.0,
                key="Amaj",
            ),
            MatchProfile(target_bpm=128.0, target_key="Amin", limit=None),
        )

        assert result.key_score == pytest.approx(0.0)
        assert result.semitone_hint is None
        assert any("mode mismatch" in reason for reason in result.reasons)

    @pytest.mark.parametrize("sample_key", [None, "Hmaj", "not-a-key"])
    def test_missing_or_unparseable_key_has_no_hint(self, sample_key: str | None):
        result = score_candidate(
            MatchCandidate(
                sample_id=1,
                path="/synthetic/key.wav",
                bpm=128.0,
                key=sample_key,
            ),
            MatchProfile(target_bpm=128.0, target_key="Cmaj", limit=None),
        )

        assert result.semitone_hint is None
        if sample_key is None or sample_key not in {"Cmaj"}:
            key_dimension = next(d for d in result.dimensions if d.name == "key")
            assert key_dimension.status == DIMENSION_NO_RESULT

    def test_groove_is_fail_closed_and_excluded(self):
        result = score_candidate(
            MatchCandidate(sample_id=1, path="/synthetic/a.wav", bpm=128.0),
            MatchProfile(target_bpm=128.0, limit=None),
        )

        groove = next(d for d in result.dimensions if d.name == "groove")
        assert result.groove_status == DIMENSION_NO_RESULT
        assert groove.reason == "GROOVE_EVIDENCE_UNAVAILABLE"
        assert groove.score is None
        assert not groove.active
        assert groove.weight == pytest.approx(0.0)

    def test_score_is_bounded_and_breakdown_exposes_weights(self):
        result = score_candidate(
            MatchCandidate(
                sample_id=1,
                path="/synthetic/full.wav",
                bpm=128.0,
                key="Amin",
                pred_type="kick",
            ),
            MatchProfile(
                target_bpm=128.0,
                target_key="Amin",
                desired_type="kick",
                limit=None,
            ),
        )

        assert 0.0 <= result.total_score <= 1.0
        assert result.active_dimensions == ("bpm", "key", "type")
        weights = {d.name: d.weight for d in result.dimensions}
        assert weights == {
            "bpm": pytest.approx(0.5),
            "key": pytest.approx(0.3),
            "type": pytest.approx(0.2),
            "groove": pytest.approx(0.0),
        }

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
        assert result.matches[1].bpm_relation == BPM_RELATION_HALF_TIME

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
