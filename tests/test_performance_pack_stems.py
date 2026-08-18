from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import soundfile as sf

from src.deconstruct import RunResult, StepResult
from src.performance_pack import (
    build_performance_pack_manifest,
    finalize_performance_pack,
)
from tests.audio_fixtures import write_sine_wav

TRACK_ID = "track_9f8e7d6c5b4a3c2d1e0f11223344556677889900"


def _write_track_map(pack_root: Path, track_id: str) -> None:
    (pack_root / "analysis").mkdir(parents=True, exist_ok=True)
    track_map = {
        "document_type": "sample_brain.track_map",
        "schema_version": "1.0.0",
        "source": {
            "original": {
                "file_name": "demo.wav",
                "hash": {"algorithm": "sha1", "value": track_id},
                "audio_properties": {
                    "duration_sec": 2.0,
                    "sample_rate_hz": 44100,
                    "channels": 1,
                },
            }
        },
        "analysis": {"status": "ok"},
    }
    (pack_root / "analysis" / "track_map.json").write_text(
        json.dumps(track_map), encoding="utf-8"
    )


def _audio_props(wav_path: Path) -> dict:
    with sf.SoundFile(str(wav_path)) as f:
        return {
            "sample_rate_hz": int(f.samplerate),
            "channels": int(f.channels),
            "n_samples": int(len(f)),
        }


def _make_stem_manifest(
    stem_id: str,
    stem_kind: str,
    track_id: str,
    wav_path: Path,
    status: str = "ok",
) -> dict:
    from src.content_hash import compute_file_hash, hash_record

    if Path(wav_path).exists():
        props = _audio_props(wav_path)
        wav_hash = compute_file_hash(wav_path)
    else:
        # Used for negative tests where the referenced WAV is intentionally absent.
        props = {"sample_rate_hz": 44100, "channels": 1, "n_samples": 44100}
        wav_hash = hash_record("sha256", "0" * 64)
    manifest = {
        "document_type": "sample_brain.stem_manifest",
        "schema_version": "1.0.0",
        "stem_id": stem_id,
        "stem_kind": stem_kind,
        "track_ref": track_id,
        "status": status,
        "source": {
            "audio_ref": "/source/original",
            "hash": wav_hash,
            "audio_properties": props,
            "origin_sample": 0,
        },
        "provenance": {"component": "stem_separator", "sample_brain_version": "0.1.0"},
        "quality": {"notes": []},
    }
    if status in ("ok", "partial"):
        manifest["output"] = {
            "file_ref": wav_path.name,
            "hash": wav_hash,
            "audio_properties": props,
        }
    elif status == "failed":
        manifest["error"] = {"code": "SEP_FAILED", "message": "separator crashed"}
    else:
        manifest["reason_code"] = "STEM_NOT_REQUESTED"
    return manifest


def _write_stem(
    pack_root: Path,
    stem_id: str,
    stem_kind: str,
    track_id: str,
    status: str = "ok",
    *,
    with_wav: bool = True,
) -> str:
    (pack_root / "stems").mkdir(parents=True, exist_ok=True)
    wav = pack_root / "stems" / f"{stem_id}.wav"
    if with_wav:
        write_sine_wav(wav, duration_sec=1.0, frequency_hz=110.0)
    manifest = _make_stem_manifest(stem_id, stem_kind, track_id, wav, status=status)
    (pack_root / "stems" / f"{stem_id}.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    return f"stems/{stem_id}.json"


def _run_result(pack_root: Path, stem_step: StepResult) -> RunResult:
    return RunResult(
        status="complete",
        track={"file_name": "demo.wav"},
        pack_root=str(pack_root),
        steps=[
            StepResult("track_map", True, "ok", ("analysis/track_map.json",)),
            stem_step,
        ],
        reason_codes=[],
    )


def _build(pack_root: Path, stem_step: StepResult):
    return build_performance_pack_manifest(_run_result(pack_root, stem_step), pack_root)


def _stem_kind_of(pack_root: Path, ref: str) -> str:
    data = json.loads((pack_root / ref).read_text(encoding="utf-8"))
    return data["stem_kind"]


# --- A. FOUR VALID STEMS -----------------------------------------------------


def test_four_valid_stems(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    refs = [
        _write_stem(pack, "stem_drums_01", "drums", TRACK_ID),
        _write_stem(pack, "stem_bass_01", "bass", TRACK_ID),
        _write_stem(pack, "stem_vocals_01", "vocals", TRACK_ID),
        _write_stem(pack, "stem_other_01", "other", TRACK_ID),
    ]
    m = _build(pack, StepResult("stems", False, "ok", tuple(refs)))
    assert len(m.stems) == 4
    kinds = {_stem_kind_of(pack, s["stem_ref"]) for s in m.stems}
    assert kinds == {"drums", "bass", "vocals", "other"}
    for entry in m.stems:
        assert entry["document_type"] == "sample_brain.stem_manifest"
        assert entry["schema_version"] == "1.0.0"
        assert entry["track_ref"] == TRACK_ID
        assert entry["status"] == "ok"
        assert entry["hash"]["algorithm"] == "sha256"
        assert entry["hash"]["value"]
    assert m.status == "complete"


# --- B. NO STEMS -------------------------------------------------------------


def test_no_stems_not_run(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    m = _build(pack, StepResult("stems", False, "not_run", ()))
    assert m.stems == []
    assert m.status == "complete"


def test_stems_step_absent(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    rr = RunResult(
        status="complete",
        track={"file_name": "demo.wav"},
        pack_root=str(pack),
        steps=[StepResult("track_map", True, "ok", ("analysis/track_map.json",))],
        reason_codes=[],
    )
    m = build_performance_pack_manifest(rr, pack)
    assert m.stems == []
    assert m.status == "complete"


# --- clarification #1: failed stem step, no outputs -> no downgrade ----------


def test_failed_stem_step_without_outputs_no_downgrade(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    m = _build(pack, StepResult("stems", False, "failed", ()))
    assert m.stems == []
    assert m.status == "complete"
    assert m.quality["notes"] == []


# --- C. PARTIAL STEMS --------------------------------------------------------


def test_partial_stems_step(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    refs = [
        _write_stem(pack, "stem_drums_01", "drums", TRACK_ID),
        _write_stem(pack, "stem_bass_01", "bass", TRACK_ID),
    ]
    m = _build(pack, StepResult("stems", False, "partial", tuple(refs)))
    assert len(m.stems) == 2
    assert m.status == "partial"
    assert any(
        n["code"] in ("MISSING_STEM_MANIFEST", "INVALID_STEM_REFERENCE")
        for n in m.quality["notes"]
    )


# --- D. FAILED OPTIONAL STEM -------------------------------------------------


def test_failed_optional_stem_degrades_only_to_partial(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    ref = _write_stem(pack, "stem_drums_01", "drums", TRACK_ID, status="failed")
    m = _build(pack, StepResult("stems", False, "ok", (ref,)))
    assert len(m.stems) == 1
    assert m.stems[0]["status"] == "failed"
    assert m.status == "partial"
    assert m.status != "failed"


# --- E. TRACK REF MISMATCH ---------------------------------------------------


def test_track_ref_mismatch_rejected(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    ref = _write_stem(pack, "stem_drums_01", "drums", "track_WRONG_ID")
    m = _build(pack, StepResult("stems", False, "ok", (ref,)))
    assert m.stems == []
    assert m.status == "partial"
    assert any(n["code"] == "STEM_TRACK_REF_MISMATCH" for n in m.quality["notes"])


# --- F. MISSING MANIFEST -----------------------------------------------------


def test_missing_stem_manifest_reference(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    m = _build(pack, StepResult("stems", False, "ok", ("stems/missing.json",)))
    assert m.stems == []
    assert m.status == "partial"
    assert any(n["code"] == "MISSING_STEM_MANIFEST" for n in m.quality["notes"])


# --- G. MALFORMED JSON -------------------------------------------------------


def test_malformed_stem_manifest(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    (pack / "stems").mkdir(parents=True, exist_ok=True)
    (pack / "stems" / "bad.json").write_text("{not valid json", encoding="utf-8")
    m = _build(pack, StepResult("stems", False, "ok", ("stems/bad.json",)))
    assert m.stems == []
    assert m.status == "partial"
    assert any(n["code"] == "INVALID_STEM_REFERENCE" for n in m.quality["notes"])


# --- H. TRAVERSAL ------------------------------------------------------------


def test_traversal_stem_ref_rejected(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    # decoy outside the pack root must never be read/consumed
    decoy = tmp_path / "private.json"
    decoy.write_text(json.dumps({"hello": "private"}), encoding="utf-8")
    m = _build(pack, StepResult("stems", False, "ok", ("../private.json",)))
    assert m.stems == []
    assert m.status == "partial"
    assert any(n["code"] == "INVALID_STEM_REFERENCE" for n in m.quality["notes"])
    # decoy untouched
    assert decoy.exists()
    assert json.loads(decoy.read_text(encoding="utf-8")) == {"hello": "private"}


# --- I. MISSING STEM WAV -----------------------------------------------------


def test_missing_stem_wav_rejected(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    # manifest claims an ok stem but the WAV was never written
    ref = _write_stem(pack, "stem_drums_01", "drums", TRACK_ID, with_wav=False)
    m = _build(pack, StepResult("stems", False, "ok", (ref,)))
    assert m.stems == []
    assert m.status == "partial"
    assert any(n["code"] == "MISSING_STEM_MANIFEST" for n in m.quality["notes"])


# --- J. DETERMINISTIC ORDER --------------------------------------------------


def test_deterministic_stem_order(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    ids = {
        "drums": _write_stem(pack, "stem_drums_01", "drums", TRACK_ID),
        "bass": _write_stem(pack, "stem_bass_01", "bass", TRACK_ID),
        "vocals": _write_stem(pack, "stem_vocals_01", "vocals", TRACK_ID),
        "other": _write_stem(pack, "stem_other_01", "other", TRACK_ID),
    }
    import random

    for _ in range(5):
        shuffled = list(ids.values())
        random.shuffle(shuffled)
        m = _build(pack, StepResult("stems", False, "ok", tuple(shuffled)))
        order = [_stem_kind_of(pack, s["stem_ref"]) for s in m.stems]
        assert order == ["drums", "bass", "vocals", "other"]


# --- K. NO PRIVATE PATHS -----------------------------------------------------


def test_serialized_pack_has_no_private_paths(tmp_path):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    refs = [
        _write_stem(pack, "stem_drums_01", "drums", TRACK_ID),
        _write_stem(pack, "stem_bass_01", "bass", TRACK_ID),
    ]
    rr = _run_result(pack, StepResult("stems", False, "ok", tuple(refs)))
    finalize_performance_pack(rr, pack)
    text = (pack / "manifest.json").read_text(encoding="utf-8")
    assert "\\" not in text
    assert "file://" not in text
    assert ".." not in text
    assert re.search(r"[A-Za-z]:[\\/]", text) is None
    assert "cache" not in text.lower()


# --- L. RE-IMPORT REGRESSION -------------------------------------------------


@pytest.fixture
def isolated_catalog(tmp_path):
    from src.config import set_db_path
    from src.db import init_db

    set_db_path(str(tmp_path / "catalog.db"))
    init_db()
    yield


def test_stem_reimport_recognizes_pack_stem(tmp_path, isolated_catalog):
    pack = tmp_path / "pack"
    _write_track_map(pack, TRACK_ID)
    ref = _write_stem(pack, "stem_drums_01", "drums", TRACK_ID)
    rr = _run_result(pack, StepResult("stems", False, "ok", (ref,)))
    finalize_performance_pack(rr, pack)

    from src.performance_pack_import import run_pack_import

    result = run_pack_import(pack)
    # only the stem was produced (no loops/sections) -> exactly one import
    assert result.imported == 1
    assert len(result.sample_ids) == 1
    assert result.skipped == 0
