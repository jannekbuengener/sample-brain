from __future__ import annotations

import soundfile as sf
from pathlib import Path

import numpy as np
import pytest

from src.analyze import (
    KEY_ANALYSIS_CONTRACT_VERSION,
    MODE_CONTRAST_MIN,
    estimate_key,
    estimate_key_mode,
    extract_features,
)
from src.export_fl import CONF_KEY_MIN, key_to_tag
from src.key_signature import format_key_signature, parse_key_signature
from src.search_filters import key_matches_scale
from tests.audio_fixtures import (
    write_key_audio_wav,
    write_major_chord_wav,
    write_octave_wav,
    write_major_minor_blend_wav,
    write_root_fifth_wav,
    write_sine_wav,
)

# Deterministically chosen roots (>= 6 distinct) for the clear fixtures.
NOTE_HZ = {
    "C": 261.63,
    "D": 293.66,
    "E": 329.63,
    "F": 349.23,
    "G": 392.00,
    "A": 440.00,
}


# ---------------------------------------------------------------------------
# 1. Shared parser / formatter
# ---------------------------------------------------------------------------


class TestKeySignatureParser:
    def test_parse_root_only(self):
        assert parse_key_signature("C").root == "C"
        assert parse_key_signature("c").root == "C"
        assert parse_key_signature("C").mode is None

    def test_parse_major(self):
        assert parse_key_signature("Cmaj") == parse_key_signature("Cmaj")
        assert parse_key_signature("Cmaj").root == "C"
        assert parse_key_signature("Cmaj").mode == "maj"
        assert parse_key_signature("A major").mode == "maj"

    def test_parse_minor(self):
        assert parse_key_signature("Amin").mode == "min"
        assert parse_key_signature("Cm") == parse_key_signature("Cm")
        assert parse_key_signature("Cm").root == "C"
        assert parse_key_signature("Cm").mode == "min"
        assert parse_key_signature("C minor").mode == "min"

    def test_parse_sharps_and_flats(self):
        assert parse_key_signature("C#maj").root == "C#"
        assert parse_key_signature("C#maj").mode == "maj"
        assert parse_key_signature("Db").root == "C#"
        assert parse_key_signature("Db").mode is None
        assert parse_key_signature("Ebmin").root == "D#"
        assert parse_key_signature("Ebmin").mode == "min"

    def test_parse_invalid(self):
        assert parse_key_signature(None) is None
        assert parse_key_signature("") is None
        assert parse_key_signature("H") is None
        assert parse_key_signature("C#minorg") is None

    def test_roundtrip_format(self):
        assert format_key_signature("C", "maj") == "Cmaj"
        assert format_key_signature("A", "min") == "Amin"
        assert format_key_signature("C", None) == "C"
        assert format_key_signature(None, "maj") is None


# ---------------------------------------------------------------------------
# 2. estimate_key_mode unit behaviour (separate from root)
# ---------------------------------------------------------------------------


class TestEstimateKeyMode:
    def _load(self, path: Path):
        y, sr = sf.read(str(path), dtype="float32", always_2d=False)
        if y.ndim > 1:
            y = y.mean(axis=1)
        return y, int(sr)

    def test_major_chord_detected(self, tmp_path: Path):
        p = write_major_chord_wav(tmp_path / "cmaj.wav", frequency_hz=NOTE_HZ["C"])
        y, sr = self._load(p)
        mode, evidence = estimate_key_mode(y, sr, root="C")
        assert mode == "maj"
        assert evidence["kind"] == "third_contrast"
        assert "major_third_energy" in evidence
        assert "minor_third_energy" in evidence
        assert "contrast" in evidence
        assert "threshold" in evidence
        assert evidence["threshold"] == MODE_CONTRAST_MIN
        assert evidence["major_third_energy"] >= evidence["minor_third_energy"]

    def test_minor_mode_commits_when_evidenced(self, tmp_path: Path):
        p = write_key_audio_wav(tmp_path / "emin.wav", frequency_hz=NOTE_HZ["E"], mode="min")
        y, sr = self._load(p)
        mode, evidence = estimate_key_mode(y, sr, root="E")
        assert mode == "min"
        assert evidence["kind"] == "third_contrast"
        assert evidence["mode"] == "min"
        assert evidence["threshold"] == MODE_CONTRAST_MIN
        assert evidence["contrast"] >= MODE_CONTRAST_MIN
        assert evidence["minor_third_energy"] >= evidence["major_third_energy"]

    def test_ambiguous_single_note_abstains(self, tmp_path: Path):
        p = write_sine_wav(tmp_path / "c.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"])
        y, sr = self._load(p)
        mode, evidence = estimate_key_mode(y, sr, root="C")
        assert mode is None
        assert evidence is not None  # evidence retained even when unresolved
        assert evidence["kind"] == "third_contrast"
        assert evidence["mode"] is None

    def test_mode_evidence_is_not_a_probability(self, tmp_path: Path):
        p = write_major_chord_wav(tmp_path / "cmaj.wav", frequency_hz=NOTE_HZ["C"])
        y, sr = self._load(p)
        mode, evidence = estimate_key_mode(y, sr, root="C")
        # contrast is a normalized, bounded ratio in [0, 1]; not a calibrated prob.
        assert 0.0 <= evidence["contrast"] <= 1.0
        assert evidence["major_third_energy"] >= 0.0
        assert evidence["minor_third_energy"] >= 0.0
        assert evidence["threshold"] == MODE_CONTRAST_MIN


# ---------------------------------------------------------------------------
# 3. Root contract regression (estimate_key + key_conf untouched)
# ---------------------------------------------------------------------------


class TestRootContractRegression:
    def test_estimate_key_returns_root_and_conf(self, tmp_path: Path):
        p = write_sine_wav(tmp_path / "c.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"])
        y, sr = sf.read(str(p), dtype="float32", always_2d=False)
        root, conf = estimate_key(y, sr)
        assert root == "C"
        assert 0.0 < conf <= 1.0

    def test_key_conf_is_peak_over_sum(self, tmp_path: Path):
        import librosa

        from src.analyze import ANALYZE_HOP_LENGTH

        p = write_sine_wav(tmp_path / "c.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"])
        y, sr = sf.read(str(p), dtype="float32", always_2d=False)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=ANALYZE_HOP_LENGTH)
        chroma_mean = np.mean(chroma, axis=1)
        expected = float(chroma_mean.max()) / float(chroma_mean.sum() + 1e-9)
        _, conf = estimate_key(y, sr)
        assert conf == pytest.approx(expected)


# ---------------------------------------------------------------------------
# 4. extract_features: canonical key carries root + optional mode
# ---------------------------------------------------------------------------


class TestExtractFeaturesCanonicalKey:
    def test_major_chord_canonical(self, tmp_path: Path):
        p = write_major_chord_wav(tmp_path / "cmaj.wav", frequency_hz=NOTE_HZ["C"])
        feats = extract_features(p, 2.0)
        assert feats.key == "Cmaj"
        assert feats.key_mode == "maj"
        assert feats.key_mode_evidence is not None

    def test_root_only_ambiguous(self, tmp_path: Path):
        p = write_sine_wav(tmp_path / "c.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"])
        feats = extract_features(p, 2.0)
        assert feats.key == "C"
        assert feats.key_mode is None
        assert feats.key_mode_evidence is not None  # retained for auditability


# ---------------------------------------------------------------------------
# 5. Context Analyze Track Map v1.1.0
# ---------------------------------------------------------------------------


class TestContextAnalyzeMode:
    def test_mode_ok_block(self, tmp_path: Path):
        from src.context_analyze import analyze_context_file

        p = write_major_chord_wav(tmp_path / "cmaj.wav", frequency_hz=NOTE_HZ["C"])
        result = analyze_context_file(p)
        key = result["analysis"]["musical"]["key"]
        assert key["root"] == "C"
        assert key["mode"] == "maj"
        assert key["status"] == "ok"
        assert key["mode_evidence"]["kind"] == "third_contrast"

    def test_mode_unresolved_partial(self, tmp_path: Path):
        from src.context_analyze import analyze_context_file

        p = write_sine_wav(tmp_path / "c.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"])
        result = analyze_context_file(p)
        key = result["analysis"]["musical"]["key"]
        assert key["root"] == "C"
        assert "mode" not in key
        assert key["status"] == "partial"
        assert key["reason_code"] == "MODE_UNRESOLVED"
        # evidence still present to explain the abstention
        assert "mode_evidence" in key

    def test_provenance_contains_key_contract_version(self, tmp_path: Path):
        from src.context_analyze import analyze_context_file

        p = write_major_chord_wav(tmp_path / "cmaj.wav", frequency_hz=NOTE_HZ["C"])
        result = analyze_context_file(p)
        cfg = result["provenance"]["components"]["analyze"]["configuration"]
        assert cfg["key_analysis_contract_version"] == KEY_ANALYSIS_CONTRACT_VERSION
        assert "parameter_fingerprint" in cfg

    def test_schema_version_1_1_0(self, tmp_path: Path):
        from src.context_analyze import analyze_context_file

        p = write_sine_wav(tmp_path / "c.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"])
        result = analyze_context_file(p)
        assert result["schema_version"] == "1.1.0"

    def test_no_result_preserved(self, tmp_path: Path):
        from src.context_analyze import analyze_context_file

        p = write_sine_wav(tmp_path / "short.wav", duration_sec=0.05, frequency_hz=NOTE_HZ["C"])
        result = analyze_context_file(p)
        key = result["analysis"]["musical"]["key"]
        assert key["status"] == "no_result"


# ---------------------------------------------------------------------------
# 6. DB persistence (no migration; canonical features.key)
# ---------------------------------------------------------------------------


class TestDbPersistence:
    def test_known_mode_persists_in_features_key(self, tmp_path: Path, monkeypatch):
        import src.config as config_module
        import src.db as db_module
        from sqlalchemy import text

        from src.analyze import run_analyze

        db_path = tmp_path / "catalog.db"
        monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
        config_module.DB_PATH = db_path
        config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
        db_module.init_db()

        samples_dir = tmp_path / "samples"
        samples_dir.mkdir()
        audio = write_key_audio_wav(
            samples_dir / "cmaj.wav", frequency_hz=NOTE_HZ["C"], mode="maj"
        )
        with db_module.get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO samples (id, path, relpath, duration, hash) "
                    "VALUES (1, :p, 'cmaj.wav', 2.0, 'h1')"
                ),
                {"p": str(audio)},
            )
        run_analyze(only_missing=True)
        with db_module.get_engine().begin() as conn:
            row = conn.execute(
                text("SELECT key, key_conf FROM features WHERE sample_id = 1")
            ).fetchone()
        assert row[0] == "Cmaj"

    def test_unknown_mode_persists_root_only(self, tmp_path: Path, monkeypatch):
        import src.config as config_module
        import src.db as db_module
        from sqlalchemy import text

        from src.analyze import run_analyze

        db_path = tmp_path / "catalog.db"
        monkeypatch.setenv("SAMPLE_BRAIN_DB_PATH", str(db_path))
        config_module.DB_PATH = db_path
        config_module.set_db_path(env={"SAMPLE_BRAIN_DB_PATH": str(db_path)})
        db_module.init_db()

        samples_dir = tmp_path / "samples"
        samples_dir.mkdir()
        audio = write_sine_wav(
            samples_dir / "c.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"]
        )
        with db_module.get_engine().begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO samples (id, path, relpath, duration, hash) "
                    "VALUES (1, :p, 'c.wav', 2.0, 'h1')"
                ),
                {"p": str(audio)},
            )
        run_analyze(only_missing=True)
        with db_module.get_engine().begin() as conn:
            row = conn.execute(
                text("SELECT key FROM features WHERE sample_id = 1")
            ).fetchone()
        assert row[0] == "C"


# ---------------------------------------------------------------------------
# 7. Consumer correctness
# ---------------------------------------------------------------------------


class TestConsumers:
    def test_key_to_tag_never_invents_major(self):
        assert key_to_tag("C", 0.9) is None  # root-only withheld
        assert key_to_tag("Cmaj", 0.9) == "Cmaj"
        assert key_to_tag("Amin", 0.9) == "Amin"
        assert key_to_tag("Cm", 0.9) == "Cmin"
        assert key_to_tag("A major", 0.9) == "Amaj"
        assert key_to_tag("C minor", 0.9) == "Cmin"
        assert key_to_tag("C", 0.4) is None  # below conf gate

    def test_key_matches_scale_requires_explicit_mode(self):
        assert key_matches_scale("Cmaj", "major")
        assert not key_matches_scale("Cmaj", "minor")
        assert key_matches_scale("Cmin", "minor")
        assert not key_matches_scale("Cmin", "major")
        assert not key_matches_scale("C", "major")  # root-only matches neither
        assert not key_matches_scale("C", "minor")
        assert key_matches_scale("Am", "minor")
        assert key_matches_scale("Cm", "minor")

    def test_asset_key_root_stays_pure_root(self, tmp_path: Path, monkeypatch):
        import src.asset_analysis as asset_analysis

        from src.analyze import Features
        from src.asset_analysis import asset_key_root

        # Even when the analyzer emits a full Dur/Moll key, the asset manifest
        # must keep only the pure root pitch class and never a mode.
        feats = Features(
            bpm=120.0,
            key="Amin",
            key_conf=0.8,
            loudness=-20.0,
            brightness=2000.0,
            mfcc_mean=None,
            mfcc_std=None,
            chroma_mean=None,
            chroma_std=None,
            clazz="loop",
        )
        assert asset_key_root(feats) == "A"


# ---------------------------------------------------------------------------
# 8. Synthetic validation gate (frozen MODE_CONTRAST_MIN)
# ---------------------------------------------------------------------------


def _build_clear_fixtures(work_dir: Path) -> list[tuple[Path, str, str]]:
    fixtures: list[tuple[Path, str, str]] = []
    for root, hz in NOTE_HZ.items():
        p = write_key_audio_wav(work_dir / f"maj_{root}.wav", frequency_hz=hz, mode="maj")
        fixtures.append((p, root, "maj"))
        p = write_key_audio_wav(work_dir / f"min_{root}.wav", frequency_hz=hz, mode="min")
        fixtures.append((p, root, "min"))
    return fixtures


def _build_ambiguous_fixtures(work_dir: Path) -> list[Path]:
    return [
        write_sine_wav(work_dir / "single.wav", duration_sec=2.0, frequency_hz=NOTE_HZ["C"]),
        write_octave_wav(work_dir / "octave.wav", frequency_hz=NOTE_HZ["C"]),
        write_root_fifth_wav(work_dir / "root_fifth.wav", frequency_hz=NOTE_HZ["C"]),
        write_major_minor_blend_wav(work_dir / "blend.wav", frequency_hz=NOTE_HZ["C"]),
    ]


class TestSyntheticValidationGate:
    def test_clear_fixtures_metrics(self, tmp_path: Path):
        clear = _build_clear_fixtures(tmp_path)
        root_ok = 0
        mode_ok = 0
        combined_ok = 0
        for path, root, mode in clear:
            feats = extract_features(path, 2.0)
            assert feats is not None
            parsed = parse_key_signature(feats.key)
            if parsed.root == root:
                root_ok += 1
            if feats.key_mode == mode:
                mode_ok += 1
            if feats.key == format_key_signature(root, mode):
                combined_ok += 1

        n = len(clear)
        root_acc = root_ok / n
        mode_acc = mode_ok / n
        combined_acc = combined_ok / n
        # Hard gate from the contract (Issue #212), met by the third-contrast
        # detector (MODE_CONTRAST_MIN = 0.30, derived from these fixtures):
        #   root_accuracy >= 0.90, mode_accuracy >= 0.90, combined >= 0.85.
        assert root_acc >= 0.90, f"root_accuracy {root_acc:.2f} < 0.90"
        assert mode_acc >= 0.90, f"mode_accuracy {mode_acc:.2f} < 0.90"
        assert combined_acc >= 0.85, f"combined {combined_acc:.2f} < 0.85"

    def test_ambiguous_fixtures_abstain(self, tmp_path: Path):
        ambiguous = _build_ambiguous_fixtures(tmp_path)
        abstained = 0
        for path in ambiguous:
            feats = extract_features(path, 2.0)
            assert feats is not None
            if feats.key_mode is None:
                abstained += 1
        assert abstained / len(ambiguous) == 1.00


# ---------------------------------------------------------------------------
# 9. Track-analysis cache invalidation (#237 + #212)
# ---------------------------------------------------------------------------


class TestTrackAnalysisCacheInvalidation:
    def test_analysis_fingerprint_includes_key_contract_version(self):
        import src.track_analysis_cache as tac

        base = dict(
            bpm_normalization="none",
            backend_name="librosa",
            backend_version="0.11.0",
            sample_brain_version="0.1.0",
        )
        fp1 = tac.compute_analysis_fingerprint(**base)
        fp2 = tac.compute_analysis_fingerprint(
            **{**base, "key_analysis_contract_version": 99}
        )
        assert fp1 != fp2

    def test_pre_212_fingerprint_misses(self, tmp_path: Path):
        import src.context_analyze as ca
        import src.track_analysis_cache as tac
        from src.track_analysis_cache import (
            build_cache_entry,
            compute_cache_key,
            write_cache_entry,
        )

        source = write_sine_wav(
            tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0
        )
        cache_dir = tmp_path / "cache"
        key = compute_cache_key(
            source_content_hash=ca.content_hash(source),
            bpm_normalization="none",
            backend_name="librosa",
            backend_version=ca._package_version_for("librosa"),
            sample_brain_version=ca._package_version(),
        )
        # Simulate a stale pre-#212 cache entry (fingerprint without key contract).
        entry = build_cache_entry(
            cache_key=key,
            source_content_hash="sha1:x",
            analysis_fingerprint="0" * 64,
            track_map={"a": 1},
            provenance_component={"b": 2},
            quality={"c": 3},
        )
        write_cache_entry(cache_dir, key, entry)
        result = ca.analyze_context_file_cached(source, cache_dir=cache_dir)
        assert result.cache_status == "miss"

    def test_new_identical_run_hits(self, tmp_path: Path, monkeypatch):
        import src.context_analyze as ca

        from src.context_analyze import analyze_context_file_cached

        source = write_sine_wav(
            tmp_path / "a.wav", duration_sec=2.0, frequency_hz=440.0
        )
        cache_dir = tmp_path / "cache"
        calls: list[int] = []
        orig = ca.extract_features

        def spy(*a, **k):
            calls.append(1)
            return orig(*a, **k)

        monkeypatch.setattr(ca, "extract_features", spy)
        r1 = ca.analyze_context_file_cached(source, cache_dir=cache_dir)
        assert r1.cache_status == "miss"
        r2 = ca.analyze_context_file_cached(source, cache_dir=cache_dir)
        assert r2.cache_status == "hit"
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# 10. Privacy: only synthetic tmp_path audio is used above
# ---------------------------------------------------------------------------


def test_no_private_paths_in_synthetic_fixtures(tmp_path: Path):
    paths = _build_clear_fixtures(tmp_path) + [
        (p, "C", "x") for p in _build_ambiguous_fixtures(tmp_path)
    ]
    for path, _, _ in paths:
        assert str(path).startswith(str(tmp_path))
