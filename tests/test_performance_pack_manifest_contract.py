from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "docs" / "performance_pack_manifest_v1_examples.json"
DOC_PATH = REPO_ROOT / "docs" / "PERFORMANCE_PACK_MANIFEST_V1.md"

EXPECTED_DOCUMENT_TYPE = "sample_brain.performance_pack_manifest"
SUPPORTED_MAJOR = 1
ALLOWED_STATUS = {"ok", "partial", "not_run", "failed", "no_result"}
ASSET_KINDS = {"loop", "section"}
SOURCE_KINDS = {"master", "stem", "producer_group"}


def _is_portable_ref(value: str) -> bool:
    if not isinstance(value, str) or not value:
        return False
    if ".." in value:
        return False
    if "file://" in value:
        return False
    if "\\" in value:
        return False
    if value.startswith("/"):
        return False
    if any(c.isalpha() and value[i + 1] == ":" for i, c in enumerate(value[:-1])):
        return False
    return True


def validate_pack(pack: dict) -> list[str]:
    errors: list[str] = []

    if pack.get("document_type") != EXPECTED_DOCUMENT_TYPE:
        errors.append(f"document_type must be {EXPECTED_DOCUMENT_TYPE!r}")

    schema_version = pack.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        errors.append("schema_version must be a non-empty string")
    else:
        try:
            major = int(schema_version.split(".")[0])
        except ValueError:
            errors.append("schema_version is not valid SemVer")
        else:
            if major != SUPPORTED_MAJOR:
                errors.append(f"unsupported schema_version major {major}")

    pack_id = pack.get("pack_id")
    if not isinstance(pack_id, str) or not pack_id:
        errors.append("pack_id must be a non-empty string")

    # source_track
    st = pack.get("source_track")
    if not isinstance(st, dict):
        errors.append("source_track must be an object")
    else:
        for field in ("track_id", "track_ref", "file_name"):
            if not isinstance(st.get(field), str) or not st[field]:
                errors.append(f"source_track.{field} must be a non-empty string")
        if not _is_portable_ref(st.get("track_ref", "")):
            errors.append("source_track.track_ref must be a portable relative reference")
        h = st.get("hash")
        if not isinstance(h, dict) or not h.get("algorithm") or not h.get("value"):
            errors.append("source_track.hash must have algorithm and value")
        ap = st.get("audio_properties")
        if not isinstance(ap, dict):
            errors.append("source_track.audio_properties must be an object")
        else:
            for fld in ("duration_sec", "sample_rate_hz", "channels"):
                if fld not in ap:
                    errors.append(f"source_track.audio_properties.{fld} is required")
            if not isinstance(ap.get("sample_rate_hz"), int) or not isinstance(
                ap.get("channels"), int
            ):
                errors.append(
                    "source_track.audio_properties.sample_rate_hz/channels must be integers"
                )

    # documents
    docs = pack.get("documents")
    if not isinstance(docs, dict):
        errors.append("documents must be an object")
    else:
        tm = docs.get("track_map")
        if not isinstance(tm, dict):
            errors.append("documents.track_map is required")
        else:
            if tm.get("document_type") != "sample_brain.track_map":
                errors.append("documents.track_map.document_type must be sample_brain.track_map")
            if not _is_portable_ref(tm.get("ref", "")):
                errors.append("documents.track_map.ref must be a portable relative reference")
            if tm.get("status") not in ALLOWED_STATUS:
                errors.append("documents.track_map.status invalid")
        for key in ("arrangement", "stem_manifest"):
            opt = docs.get(key)
            if opt is None:
                continue
            if not isinstance(opt, dict):
                errors.append(f"documents.{key} must be an object when present")
            elif opt.get("status") not in ALLOWED_STATUS:
                errors.append(f"documents.{key}.status invalid")

        if isinstance(st, dict) and isinstance(tm, dict):
            if st.get("track_ref") and tm.get("ref") and st["track_ref"] != tm["ref"]:
                errors.append("source_track.track_ref must equal documents.track_map.ref")

    # assets
    assets = pack.get("assets")
    if not isinstance(assets, list):
        errors.append("assets must be an array")
    else:
        for idx, a in enumerate(assets):
            p = f"assets[{idx}]"
            if not isinstance(a, dict):
                errors.append(f"{p} must be an object")
                continue
            if not isinstance(a.get("asset_id"), str) or not a["asset_id"]:
                errors.append(f"{p}.asset_id required")
            if not _is_portable_ref(a.get("asset_ref", "")):
                errors.append(f"{p}.asset_ref must be portable")
            if a.get("document_type") != "sample_brain.asset_manifest":
                errors.append(f"{p}.document_type must be sample_brain.asset_manifest")
            if a.get("asset_kind") not in ASSET_KINDS:
                errors.append(f"{p}.asset_kind must be loop|section")
            sk = a.get("source_kind")
            if sk not in SOURCE_KINDS:
                errors.append(f"{p}.source_kind must be master|stem|producer_group")
            if isinstance(st, dict) and a.get("track_ref") != st.get("track_id"):
                errors.append(f"{p}.track_ref must equal source_track.track_id")
            rng = a.get("range")
            if not isinstance(rng, dict):
                errors.append(f"{p}.range required")
            else:
                s = rng.get("start_sample")
                e = rng.get("end_sample_exclusive")
                n = rng.get("n_samples")
                sr = rng.get("sample_rate_hz")
                if not (isinstance(s, int) and isinstance(e, int) and e > s >= 0):
                    errors.append(f"{p}.range invalid sample interval")
                if not (isinstance(n, int) and n == e - s):
                    errors.append(f"{p}.range.n_samples must equal end-start")
                if not (isinstance(sr, int) and sr > 0):
                    errors.append(f"{p}.range.sample_rate_hz must be positive int")
            if sk == "stem":
                if not a.get("stem_id") or not _is_portable_ref(a.get("stem_ref", "")):
                    errors.append(f"{p} stem source requires stem_id and stem_ref")
            elif sk == "producer_group":
                if not a.get("producer_group_id") or not _is_portable_ref(
                    a.get("producer_group_ref", "")
                ):
                    errors.append(
                        f"{p} producer_group source requires producer_group_id and producer_group_ref"
                    )
            elif sk == "master":
                if a.get("stem_id") is not None or a.get("producer_group_id") is not None:
                    errors.append(f"{p} master source must not carry stem/producer_group ids")
            if a.get("status") not in ALLOWED_STATUS:
                errors.append(f"{p}.status invalid")

    # stems (optional)
    stems = pack.get("stems")
    if stems is not None:
        if not isinstance(stems, list):
            errors.append("stems must be an array when present")
        else:
            for idx, sm in enumerate(stems):
                p = f"stems[{idx}]"
                if not isinstance(sm, dict):
                    errors.append(f"{p} must be an object")
                    continue
                if not isinstance(sm.get("stem_id"), str) or not sm["stem_id"]:
                    errors.append(f"{p}.stem_id required")
                if not _is_portable_ref(sm.get("stem_ref", "")):
                    errors.append(f"{p}.stem_ref must be portable")
                if sm.get("document_type") != "sample_brain.stem_manifest":
                    errors.append(f"{p}.document_type must be sample_brain.stem_manifest")
                if isinstance(st, dict) and sm.get("track_ref") != st.get("track_id"):
                    errors.append(f"{p}.track_ref must equal source_track.track_id")
                if sm.get("status") not in ALLOWED_STATUS:
                    errors.append(f"{p}.status invalid")

    # provenance + quality
    prov = pack.get("provenance")
    if not isinstance(prov, dict) or not isinstance(prov.get("components"), dict) or not prov["components"]:
        errors.append("provenance.components must be a non-empty object")

    q = pack.get("quality")
    if not isinstance(q, dict) or not isinstance(q.get("notes"), list):
        errors.append("quality.notes must be an array")

    # status consistency
    computed = compute_status(pack)
    if pack.get("status") != computed:
        errors.append(f"status {pack.get('status')!r} != computed {computed!r}")

    return errors


def compute_status(pack: dict) -> str:
    docs = pack.get("documents") or {}
    tm = docs.get("track_map")
    if not isinstance(tm, dict) or tm.get("status") == "failed":
        return "failed"
    components = []
    if isinstance(docs.get("arrangement"), dict):
        components.append(docs["arrangement"].get("status"))
    if isinstance(docs.get("stem_manifest"), dict):
        components.append(docs["stem_manifest"].get("status"))
    for a in pack.get("assets", []) or []:
        if isinstance(a, dict):
            components.append(a.get("status"))
    for sm in pack.get("stems", []) or []:
        if isinstance(sm, dict):
            components.append(sm.get("status"))
    if any(c in ("partial", "failed") for c in components):
        return "partial"
    return "complete"


def _load_examples() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _example(name: str) -> dict:
    return deepcopy(_load_examples()["examples"][name])


def test_fixture_and_doc_exist():
    assert FIXTURE_PATH.exists()
    assert DOC_PATH.exists()


def test_document_header_in_doc():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "sample_brain.performance_pack_manifest" in text
    assert 'schema_version`: `1.0.0`' in text or "1.0.0" in text


def test_complete_full_pack_is_valid():
    errors = validate_pack(_example("complete_full_pack"))
    assert errors == [], errors


def test_valid_without_optional_stems_is_valid():
    errors = validate_pack(_example("valid_without_optional_stems"))
    assert errors == [], errors


def test_partial_optional_result_is_valid_and_partial():
    pack = _example("partial_optional_result")
    errors = validate_pack(pack)
    assert errors == [], errors
    assert pack["status"] == "partial"


def test_unsupported_major_is_rejected():
    pack = _example("complete_full_pack")
    pack["schema_version"] = "2.0.0"
    errors = validate_pack(pack)
    assert any("unsupported schema_version" in e for e in errors), errors


def test_absolute_private_path_is_rejected():
    pack = _example("complete_full_pack")
    pack["source_track"]["track_ref"] = "C:/Users/janne/private/demo_track.wav"
    errors = validate_pack(pack)
    assert any("portable" in e for e in errors), errors


def test_asset_track_ref_must_match_source_track():
    pack = _example("complete_full_pack")
    pack["assets"][0]["track_ref"] = "track_WRONG"
    errors = validate_pack(pack)
    assert any("track_ref" in e for e in errors), errors


def test_stem_source_requires_stem_ids():
    pack = _example("complete_full_pack")
    bad = pack["assets"][1]
    bad.pop("stem_id")
    bad.pop("stem_ref")
    errors = validate_pack(pack)
    assert any("stem source requires" in e for e in errors), errors


def test_master_source_must_not_carry_stem_ids():
    pack = _example("complete_full_pack")
    pack["assets"][0]["stem_id"] = "stem_x"
    errors = validate_pack(pack)
    assert any("master source" in e for e in errors), errors


def test_invalid_asset_range_is_rejected():
    pack = _example("complete_full_pack")
    pack["assets"][0]["range"]["n_samples"] = 1
    errors = validate_pack(pack)
    assert any("n_samples" in e for e in errors), errors


def test_missing_track_map_is_failed():
    pack = _example("complete_full_pack")
    pack["documents"].pop("track_map")
    assert compute_status(pack) == "failed"
    errors = validate_pack(pack)
    assert any("track_map is required" in e for e in errors), errors


def test_optional_no_result_does_not_downgrade_complete():
    pack = _example("valid_without_optional_stems")
    pack["documents"]["arrangement"]["status"] = "no_result"
    pack["documents"]["arrangement"]["reason_code"] = "ARRANGEMENT_NOT_REQUESTED"
    assert validate_pack(pack) == [], validate_pack(pack)
    assert pack["status"] == "complete"


def test_optional_failed_stem_downgrades_to_partial():
    pack = _example("valid_without_optional_stems")
    pack["stems"] = [
        {
            "stem_id": "stem_drums_01",
            "stem_ref": "stems/stem_drums_01.json",
            "document_type": "sample_brain.stem_manifest",
            "schema_version": "1.0.0",
            "track_ref": pack["source_track"]["track_id"],
            "status": "failed",
        }
    ]
    pack["status"] = "partial"
    errors = validate_pack(pack)
    assert errors == [], errors
    assert pack["status"] == "partial"
