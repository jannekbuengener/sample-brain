"""Contract tests for path-metadata pre-pass and evidence reconciliation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from sqlalchemy import text

from src import config
from src.db import init_db, insert_sample, list_sample_tags
from src.path_metadata import (
    STATUS_ANALYSIS_ONLY,
    STATUS_COMPATIBLE,
    STATUS_CONFIRMED,
    STATUS_CONFLICT,
    STATUS_DECLARED_ONLY,
    STATUS_PARTIAL,
    extract_bpm_hint,
    extract_claims_from_path,
    extract_genre_claims,
    extract_key_hint,
    extract_pred_type_claim,
    extract_type_hint,
    list_metadata_resolutions,
    list_path_metadata_claims,
    path_fingerprint,
    run_metadata_reconcile,
    run_path_metadata_prepass,
)


@pytest.fixture
def catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "catalog.db"
    monkeypatch.setattr(config, "DB_PATH", db_path)
    init_db()
    return db_path


def _hash(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _insert(
    path: str,
    *,
    relpath: str | None = None,
    content_hash: str | None = None,
) -> int:
    return insert_sample(
        path=path,
        relpath=relpath or Path(path).name,
        samplerate=44100,
        channels=1,
        duration=1.0,
        size_bytes=100,
        content_hash=content_hash or _hash(path),
    )


def _set_features(
    sample_id: int,
    *,
    bpm: float | None = None,
    key: str | None = None,
    clazz: str | None = None,
    pred_type: str | None = None,
) -> None:
    engine = init_db()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO features (sample_id, bpm, key, class, pred_type)
                VALUES (:sid, :bpm, :key, :clazz, :pred)
                ON CONFLICT(sample_id) DO UPDATE SET
                    bpm=excluded.bpm,
                    key=excluded.key,
                    class=excluded.class,
                    pred_type=excluded.pred_type
                """
            ),
            {
                "sid": sample_id,
                "bpm": bpm,
                "key": key,
                "clazz": clazz,
                "pred": pred_type,
            },
        )


def _resolution(sample_id: int, field: str) -> dict:
    rows = [r for r in list_metadata_resolutions(sample_id) if r["field"] == field]
    assert len(rows) == 1
    return rows[0]


# --- 1–7: parsing ---


def test_explicit_bpm_parsing():
    assert extract_bpm_hint("KickLoop_132BPM.wav") == 132.0
    assert extract_bpm_hint("Percussion 128 bpm.wav") == 128.0
    assert extract_bpm_hint("Techno_Loop_140BPM_Cm.wav") == 140.0


def test_bpm_false_positive_protection():
    assert extract_bpm_hint("sample_132_v3.wav") is None
    assert extract_bpm_hint("final_1402.wav") is None
    assert extract_bpm_hint("Cinematic_Amazing_01.wav") is None


def test_explicit_key_and_mode_parsing():
    assert extract_key_hint("pad_F#m.wav") == "F#min"
    assert extract_key_hint("pad_F#min.wav") == "F#min"
    assert extract_key_hint("pad F# minor.wav") == "F#min"
    assert extract_key_hint("lead_Amaj.wav") == "Amaj"
    assert extract_key_hint("lead A major.wav") == "Amaj"
    assert extract_key_hint("Bass_A.wav") is None


def test_enharmonic_normalization():
    assert extract_key_hint("loop_Dbmin.wav") == "C#min"
    assert extract_key_hint("loop_Bbmin.wav") == "A#min"


def test_loop_oneshot_extraction():
    assert extract_type_hint("KickLoop_132BPM.wav") == "loop"
    assert extract_type_hint("snare_one_shot.wav") == "oneshot"
    assert extract_type_hint("clap oneshot.wav") == "oneshot"
    assert extract_type_hint("hat-one-shot.wav") == "oneshot"


def test_semantic_sample_type_extraction():
    assert extract_pred_type_claim("KickLoop_132BPM.wav") == "Kick"
    assert extract_pred_type_claim("deep_snare.wav") == "Snare"
    assert extract_pred_type_claim("closed_hat_tight.wav") == "HiHat-Closed"
    assert extract_pred_type_claim("open_hat_sizzle.wav") == "HiHat-Open"
    assert extract_pred_type_claim("bass_stab.wav") == "Bass"
    assert extract_pred_type_claim("pad_warm.wav") == "Pad"
    # Configured aliases from data/filename_tag_regex.json instrument map.
    assert extract_pred_type_claim("sub_hit.wav") == "Bass"
    assert extract_pred_type_claim("lead_arp_riff.wav") == "Lead"
    assert extract_pred_type_claim("shaker_loop.wav") == "Perc"


def test_configured_genre_tag_extraction():
    genres = {label for label, _ in extract_genre_claims("Techno_Loop_140BPM_Cm.wav")}
    assert "Techno" in genres
    folder_genres = {
        label for label, _ in extract_genre_claims("House/Deep/kick.wav")
    }
    assert "House" in folder_genres


# --- 8–17: reconciliation ---


def test_filename_audio_exact_agreement(catalog):
    sid = _insert("/lib/Kick_132BPM.wav", relpath="Kick_132BPM.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, bpm=132.0)
    run_metadata_reconcile([sid])
    row = _resolution(sid, "bpm")
    assert row["resolution_status"] == STATUS_CONFIRMED
    assert row["resolved_value"] == "132"


def test_bpm_tolerance_agreement(catalog):
    sid = _insert("/lib/Kick_132BPM.wav", relpath="Kick_132BPM.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, bpm=131.7)
    run_metadata_reconcile([sid])
    row = _resolution(sid, "bpm")
    assert row["resolution_status"] == STATUS_CONFIRMED
    assert row["resolved_value"] == "132"


def test_half_double_bpm_compatibility(catalog):
    sid = _insert("/lib/Loop_140BPM.wav", relpath="Loop_140BPM.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, bpm=70.0)
    run_metadata_reconcile([sid])
    row = _resolution(sid, "bpm")
    assert row["resolution_status"] == STATUS_COMPATIBLE
    assert row["resolved_value"] == "140"


def test_full_key_agreement_enharmonic(catalog):
    sid = _insert("/lib/Pad_Dbmin.wav", relpath="Pad_Dbmin.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, key="C#min")
    run_metadata_reconcile([sid])
    row = _resolution(sid, "key")
    assert row["resolution_status"] == STATUS_CONFIRMED
    assert row["resolved_value"] == "C#min"


def test_key_root_unresolved_mode_not_full_confirmation(catalog):
    sid = _insert("/lib/Pad_F#min.wav", relpath="Pad_F#min.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, key="F#")  # root-only analysis
    run_metadata_reconcile([sid])
    row = _resolution(sid, "key")
    assert row["resolution_status"] == STATUS_PARTIAL
    assert row["resolved_value"] == "F#"
    assert "not full confirmation" in (row["provenance_note"] or "").lower() or (
        "unresolved" in (row["provenance_note"] or "").lower()
    )


def test_hard_bpm_conflict(catalog):
    sid = _insert("/lib/Kick_128BPM.wav", relpath="Kick_128BPM.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, bpm=143.0)
    run_metadata_reconcile([sid])
    row = _resolution(sid, "bpm")
    assert row["resolution_status"] == STATUS_CONFLICT
    assert row["resolved_value"] is None
    assert row["filename_value"] == "128"
    assert row["analysis_value"] == "143"


def test_hard_key_conflict(catalog):
    sid = _insert("/lib/Pad_Amin.wav", relpath="Pad_Amin.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, key="Cmaj")
    run_metadata_reconcile([sid])
    row = _resolution(sid, "key")
    assert row["resolution_status"] == STATUS_CONFLICT
    assert row["resolved_value"] is None


def test_type_class_conflict(catalog):
    sid = _insert("/lib/KickLoop.wav", relpath="KickLoop.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, clazz="oneshot", pred_type="Snare")
    run_metadata_reconcile([sid])
    class_row = _resolution(sid, "sample_class")
    pred_row = _resolution(sid, "pred_type")
    assert class_row["resolution_status"] == STATUS_CONFLICT
    assert pred_row["resolution_status"] == STATUS_CONFLICT


def test_filename_only_field(catalog):
    sid = _insert("/lib/Techno_Kick_128BPM.wav", relpath="Techno_Kick_128BPM.wav")
    run_path_metadata_prepass([sid])
    # No features row / no genre analyzer
    run_metadata_reconcile([sid])
    genre = _resolution(sid, "genre")
    assert genre["resolution_status"] == STATUS_DECLARED_ONLY
    assert "Techno" in (genre["resolved_value"] or "")
    bpm = _resolution(sid, "bpm")
    assert bpm["resolution_status"] == STATUS_DECLARED_ONLY
    assert bpm["resolved_value"] == "128"


def test_analysis_only_field(catalog):
    sid = _insert("/lib/mystery.wav", relpath="mystery.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, bpm=120.0, key="Cmaj", clazz="loop", pred_type="Pad")
    run_metadata_reconcile([sid])
    assert _resolution(sid, "bpm")["resolution_status"] == STATUS_ANALYSIS_ONLY
    assert _resolution(sid, "key")["resolution_status"] == STATUS_ANALYSIS_ONLY
    assert _resolution(sid, "sample_class")["resolution_status"] == STATUS_ANALYSIS_ONLY
    assert _resolution(sid, "pred_type")["resolution_status"] == STATUS_ANALYSIS_ONLY


# --- 18–21: robustness / invariants ---


def test_malformed_filename_does_not_fail_analysis(catalog):
    sid = _insert("/lib/sample_132_v3.wav", relpath="sample_132_v3.wav")
    summary = run_path_metadata_prepass([sid])
    assert summary["samples_considered"] == 1
    claims = list_path_metadata_claims(sid)
    assert all(c["field"] != "bpm" for c in claims)
    _set_features(sid, bpm=99.0)
    recon = run_metadata_reconcile([sid])
    assert recon["samples_reconciled"] == 1
    assert _resolution(sid, "bpm")["resolution_status"] == STATUS_ANALYSIS_ONLY


def test_rename_path_change_refreshes_metadata_evidence(catalog):
    sid = _insert(
        "/lib/old/Kick_128BPM.wav",
        relpath="old/Kick_128BPM.wav",
        content_hash=_hash("unchanged-content"),
    )
    run_path_metadata_prepass([sid])
    before = list_path_metadata_claims(sid)
    assert any(c["field"] == "bpm" and c["normalized_value"] == "128" for c in before)
    old_fp = before[0]["path_fingerprint"]

    engine = init_db()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE samples
                SET path = :path, relpath = :relpath
                WHERE id = :sid
                """
            ),
            {
                "path": "/lib/new/Kick_140BPM.wav",
                "relpath": "new/Kick_140BPM.wav",
                "sid": sid,
            },
        )
    run_path_metadata_prepass([sid])
    after = list_path_metadata_claims(sid)
    assert after
    assert after[0]["path_fingerprint"] != old_fp
    assert any(c["field"] == "bpm" and c["normalized_value"] == "140" for c in after)
    assert path_fingerprint("Kick_140BPM.wav", "new/Kick_140BPM.wav") == after[0][
        "path_fingerprint"
    ]


def test_raw_analyzer_values_unchanged_after_reconciliation(catalog):
    sid = _insert("/lib/Kick_128BPM.wav", relpath="Kick_128BPM.wav")
    run_path_metadata_prepass([sid])
    _set_features(sid, bpm=143.0, key="Cmaj", clazz="oneshot", pred_type="Kick")
    engine = init_db()
    with engine.begin() as conn:
        before = conn.execute(
            text(
                "SELECT bpm, key, class, pred_type FROM features WHERE sample_id=:sid"
            ),
            {"sid": sid},
        ).fetchone()
    run_metadata_reconcile([sid])
    with engine.begin() as conn:
        after = conn.execute(
            text(
                "SELECT bpm, key, class, pred_type FROM features WHERE sample_id=:sid"
            ),
            {"sid": sid},
        ).fetchone()
    assert tuple(before) == tuple(after)
    assert after[0] == 143.0


def test_deterministic_repeated_runs(catalog):
    sid = _insert(
        "/lib/Techno/KickLoop_132BPM_F#m.wav",
        relpath="Techno/KickLoop_132BPM_F#m.wav",
    )
    run_path_metadata_prepass([sid])
    _set_features(sid, bpm=132.0, key="F#min", clazz="loop", pred_type="Kick")
    run_metadata_reconcile([sid])
    first_claims = list_path_metadata_claims(sid)
    first_res = list_metadata_resolutions(sid)
    run_path_metadata_prepass([sid])
    run_metadata_reconcile([sid])
    second_claims = list_path_metadata_claims(sid)
    second_res = list_metadata_resolutions(sid)

    def _claim_key(c: dict) -> tuple:
        return (
            c["field"],
            c["normalized_value"],
            c["source"],
            c["raw_evidence"],
            c["parser_version"],
            c["path_fingerprint"],
        )

    def _res_key(r: dict) -> tuple:
        return (
            r["field"],
            r["resolution_status"],
            r["resolved_value"],
            r["filename_value"],
            r["analysis_value"],
            r["provenance_note"],
            r["parser_version"],
        )

    assert sorted(_claim_key(c) for c in first_claims) == sorted(
        _claim_key(c) for c in second_claims
    )
    assert sorted(_res_key(r) for r in first_res) == sorted(
        _res_key(r) for r in second_res
    )


def test_extract_claims_separates_filename_and_folder():
    claims = extract_claims_from_path(
        "Kick_128BPM.wav", relpath="Techno/Drums/Kick_128BPM.wav"
    )
    fields = {(c.field, c.source, c.normalized_value) for c in claims}
    assert ("bpm", "filename", "128") in fields
    assert ("pred_type", "filename", "Kick") in fields
    assert any(c.field == "genre" and c.normalized_value == "Techno" for c in claims)


def test_genre_tags_written_with_provenance(catalog):
    sid = _insert(
        "/lib/Techno/Kick_128BPM.wav",
        relpath="Techno/Kick_128BPM.wav",
    )
    run_path_metadata_prepass([sid])
    tags = list_sample_tags(sid)
    assert any(
        t["tag"] == "techno" and t["source"] in {"filename", "folder"} for t in tags
    )


def test_path_derived_genre_tags_replaced_on_refresh(catalog):
    sid = _insert(
        "/lib/Techno/Kick_128BPM.wav",
        relpath="Techno/Kick_128BPM.wav",
        content_hash=_hash("stable-audio"),
    )
    run_path_metadata_prepass([sid])
    assert any(t["tag"] == "techno" for t in list_sample_tags(sid))

    engine = init_db()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE samples
                SET path = :path, relpath = :relpath
                WHERE id = :sid
                """
            ),
            {
                "path": "/lib/House/Kick_128BPM.wav",
                "relpath": "House/Kick_128BPM.wav",
                "sid": sid,
            },
        )
    run_path_metadata_prepass([sid])
    tags = {(t["tag"], t["source"]) for t in list_sample_tags(sid)}
    assert ("house", "folder") in tags or any(t == "house" for t, _ in tags)
    assert ("techno", "folder") not in tags
    assert ("techno", "filename") not in tags


def test_prepass_empty_sample_ids_is_noop(catalog):
    sid = _insert("/lib/Kick_128BPM.wav", relpath="Kick_128BPM.wav")
    summary = run_path_metadata_prepass([])
    assert summary == {"samples_considered": 0, "samples_refreshed": 0}
    assert list_path_metadata_claims(sid) == []
