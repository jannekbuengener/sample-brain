from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = REPO_ROOT / "docs" / "stem_manifest_v1_examples.json"
DOC_PATH = REPO_ROOT / "docs" / "STEM_MANIFEST_V1.md"

EXPECTED_DOCUMENT_TYPE = "sample_brain.stem_manifest"
SUPPORTED_MAJOR = 1
ALLOWED_STATUS = {"ok", "partial", "not_run", "no_result", "failed"}
STANDARD_STEM_KINDS = {"drums", "bass", "vocals", "other"}


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


def validate_stem_manifest(manifest: dict) -> list[str]:
    errors: list[str] = []

    if manifest.get("document_type") != EXPECTED_DOCUMENT_TYPE:
        errors.append(f"document_type must be {EXPECTED_DOCUMENT_TYPE!r}")

    schema_version = manifest.get("schema_version")
    if not isinstance(schema_version, str) or not schema_version:
        errors.append("schema_version must be a non-empty string")
    else:
        try:
            major = int(schema_version.split(".")[0])
        except (ValueError, IndexError):
            errors.append("schema_version is not valid SemVer")
        else:
            if major != SUPPORTED_MAJOR:
                errors.append(f"unsupported schema_version major {major}")

    stem_id = manifest.get("stem_id")
    if not isinstance(stem_id, str) or not stem_id:
        errors.append("stem_id must be a non-empty string")

    stem_kind = manifest.get("stem_kind")
    if stem_kind not in STANDARD_STEM_KINDS:
        errors.append(f"stem_kind must be one of {STANDARD_STEM_KINDS}, got {stem_kind!r}")

    track_ref = manifest.get("track_ref")
    if not isinstance(track_ref, str) or not track_ref:
        errors.append("track_ref is required and must be a string")
    else:
        # track_ref must be a portable ID (e.g. content hash), not a path or filename fallback
        if "/" in track_ref or "\\" in track_ref or ":" in track_ref or track_ref.endswith((".wav", ".mp3", ".flac")):
            errors.append(f"track_ref must be a portable track ID, not a path or filename: {track_ref!r}")

    status = manifest.get("status")
    if status not in ALLOWED_STATUS:
        errors.append(f"status must be one of {ALLOWED_STATUS}, got {status!r}")

    # source
    src = manifest.get("source")
    if not isinstance(src, dict):
        errors.append("source must be an object")
    else:
        audio_ref = src.get("audio_ref")
        if audio_ref not in {"/source/original", "/source/working_audio"}:
            errors.append("source.audio_ref must be a valid JSON pointer: /source/original or /source/working_audio")

        origin_sample = src.get("origin_sample")
        if origin_sample != 0:
            errors.append(f"source.origin_sample must be 0, got {origin_sample!r}")

        h = src.get("hash")
        if not isinstance(h, dict) or not h.get("algorithm") or not h.get("value"):
            errors.append("source.hash is required with algorithm and value")

        ap = src.get("audio_properties")
        if not isinstance(ap, dict):
            errors.append("source.audio_properties must be an object")
        else:
            for field in ("sample_rate_hz", "channels", "n_samples"):
                val = ap.get(field)
                if not isinstance(val, int) or val <= 0:
                    errors.append(f"source.audio_properties.{field} must be a positive integer, got {val!r}")

    # status based constraints
    output = manifest.get("output")
    if status in {"ok", "partial"}:
        if not isinstance(output, dict):
            errors.append(f"output is required when status is {status!r}")
        else:
            file_ref = output.get("file_ref")
            if not isinstance(file_ref, str) or not file_ref:
                errors.append("output.file_ref must be a non-empty string")
            elif not _is_portable_ref(file_ref):
                errors.append(f"output.file_ref must be portable and relative, got {file_ref!r}")

            oh = output.get("hash")
            if not isinstance(oh, dict) or not oh.get("algorithm") or not oh.get("value"):
                errors.append("output.hash is required with algorithm and value")

            oap = output.get("audio_properties")
            if not isinstance(oap, dict):
                errors.append("output.audio_properties must be an object")
            else:
                for field in ("sample_rate_hz", "channels", "n_samples"):
                    val = oap.get(field)
                    if not isinstance(val, int) or val <= 0:
                        errors.append(f"output.audio_properties.{field} must be a positive integer, got {val!r}")
    else:
        if output is not None:
            errors.append(f"output must be absent when status is {status!r}")

    if status in {"not_run", "no_result"}:
        reason_code = manifest.get("reason_code")
        if not isinstance(reason_code, str) or not reason_code:
            errors.append(f"reason_code must be a non-empty string when status is {status!r}")

    if status == "failed":
        err_block = manifest.get("error")
        if not isinstance(err_block, dict):
            errors.append("error is required when status is 'failed'")
        else:
            if not isinstance(err_block.get("code"), str) or not err_block["code"]:
                errors.append("error.code is required and must be a non-empty string")
            if not isinstance(err_block.get("message"), str) or not err_block["message"]:
                errors.append("error.message is required and must be a non-empty string")

    # provenance
    prov = manifest.get("provenance")
    if not isinstance(prov, dict):
        errors.append("provenance must be an object")
    else:
        if not isinstance(prov.get("component"), str) or not prov["component"]:
            errors.append("provenance.component is required")
        if not isinstance(prov.get("sample_brain_version"), str) or not prov["sample_brain_version"]:
            errors.append("provenance.sample_brain_version is required")

        # attempted runs with models should document model details
        if status in {"ok", "partial", "no_result", "failed"}:
            model = prov.get("model")
            if model is not None:
                if not isinstance(model, dict):
                    errors.append("provenance.model must be an object when present")
                else:
                    for field in ("family", "name", "checkpoint", "code_license", "weight_license"):
                        if not isinstance(model.get(field), str) or not model[field]:
                            errors.append(f"provenance.model.{field} is required")

                    wh = model.get("weight_hash")
                    if not isinstance(wh, dict) or not wh.get("algorithm") or not wh.get("value"):
                        errors.append("provenance.model.weight_hash must have algorithm and value")

    # quality notes
    q = manifest.get("quality")
    if not isinstance(q, dict) or not isinstance(q.get("notes"), list):
        errors.append("quality.notes must be an array")
    elif q.get("notes"):
        for idx, note in enumerate(q["notes"]):
            p = f"quality.notes[{idx}]"
            if not isinstance(note, dict):
                errors.append(f"{p} must be an object")
                continue
            if not isinstance(note.get("code"), str) or not note["code"]:
                errors.append(f"{p}.code must be a non-empty string")
            if note.get("severity") not in {"info", "warning", "error"}:
                errors.append(f"{p}.severity must be info|warning|error")
            if not isinstance(note.get("path"), str) or not note["path"]:
                errors.append(f"{p}.path must be a non-empty string pointer")
            if not isinstance(note.get("message"), str) or not note["message"]:
                errors.append(f"{p}.message must be a non-empty string")

    return errors


def _load_examples() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _example(name: str) -> dict:
    return deepcopy(_load_examples()["examples"][name])


def test_fixture_and_doc_exist():
    assert FIXTURE_PATH.exists()
    assert DOC_PATH.exists()


def test_document_header_in_doc():
    text = DOC_PATH.read_text(encoding="utf-8")
    assert "sample_brain.stem_manifest" in text
    assert "1.0.0" in text


def test_all_synthetic_examples_are_valid():
    examples = _load_examples()["examples"]
    for name, manifest in examples.items():
        errors = validate_stem_manifest(manifest)
        assert errors == [], f"{name} should be valid but has errors: {errors}"


def test_invalid_stem_kind_is_rejected():
    m = _example("valid_drums")
    m["stem_kind"] = "kick_bass"
    errors = validate_stem_manifest(m)
    assert any("stem_kind must be one of" in e for e in errors), errors


def test_invalid_status_is_rejected():
    m = _example("valid_drums")
    m["status"] = "amazing_stems"
    errors = validate_stem_manifest(m)
    assert any("status must be one of" in e for e in errors), errors


def test_unsupported_major_version_is_rejected():
    m = _example("valid_drums")
    m["schema_version"] = "2.0.0"
    errors = validate_stem_manifest(m)
    assert any("unsupported schema_version major" in e for e in errors), errors


def test_empty_stem_id_is_rejected():
    m = _example("valid_drums")
    m["stem_id"] = ""
    errors = validate_stem_manifest(m)
    assert any("stem_id must be a non-empty string" in e for e in errors), errors


def test_filename_fallback_as_track_ref_is_rejected():
    m = _example("valid_drums")
    m["track_ref"] = "my_track.wav"
    errors = validate_stem_manifest(m)
    assert any("track_ref must be a portable track ID" in e for e in errors), errors


def test_absolute_file_ref_is_rejected():
    m = _example("valid_drums")
    m["output"]["file_ref"] = "C:/stems/drums.wav"
    errors = validate_stem_manifest(m)
    assert any("file_ref must be portable" in e for e in errors), errors


def test_unc_file_ref_is_rejected():
    m = _example("valid_drums")
    m["output"]["file_ref"] = "\\\\server\\share\\drums.wav"
    errors = validate_stem_manifest(m)
    assert any("file_ref must be portable" in e for e in errors), errors


def test_file_url_is_rejected():
    m = _example("valid_drums")
    m["output"]["file_ref"] = "file:///stems/drums.wav"
    errors = validate_stem_manifest(m)
    assert any("file_ref must be portable" in e for e in errors), errors


def test_dot_dot_traversal_is_rejected():
    m = _example("valid_drums")
    m["output"]["file_ref"] = "../outside/drums.wav"
    errors = validate_stem_manifest(m)
    assert any("file_ref must be portable" in e for e in errors), errors


def test_ok_needs_output():
    m = _example("valid_drums")
    m.pop("output")
    errors = validate_stem_manifest(m)
    assert any("output is required" in e for e in errors), errors


def test_partial_needs_output():
    m = _example("valid_partial")
    m.pop("output")
    errors = validate_stem_manifest(m)
    assert any("output is required" in e for e in errors), errors


def test_not_run_needs_reason_code_and_no_output():
    m = _example("valid_not_run")
    m.pop("reason_code")
    errors = validate_stem_manifest(m)
    assert any("reason_code must be a non-empty string" in e for e in errors), errors

    m2 = _example("valid_not_run")
    m2["output"] = _example("valid_drums")["output"]
    errors2 = validate_stem_manifest(m2)
    assert any("output must be absent" in e for e in errors2), errors2


def test_no_result_needs_reason_code():
    m = _example("valid_no_result")
    m.pop("reason_code")
    errors = validate_stem_manifest(m)
    assert any("reason_code must be a non-empty string" in e for e in errors), errors


def test_failed_needs_error():
    m = _example("valid_failed")
    m.pop("error")
    errors = validate_stem_manifest(m)
    assert any("error is required when status is 'failed'" in e for e in errors), errors


def test_positive_audio_properties():
    # positive sample rate
    m = _example("valid_drums")
    m["source"]["audio_properties"]["sample_rate_hz"] = -44100
    errors = validate_stem_manifest(m)
    assert any("sample_rate_hz must be a positive integer" in e for e in errors), errors

    # positive channels
    m2 = _example("valid_drums")
    m2["source"]["audio_properties"]["channels"] = 0
    errors2 = validate_stem_manifest(m2)
    assert any("channels must be a positive integer" in e for e in errors2), errors2

    # positive n_samples
    m3 = _example("valid_drums")
    m3["source"]["audio_properties"]["n_samples"] = -1
    errors3 = validate_stem_manifest(m3)
    assert any("n_samples must be a positive integer" in e for e in errors3), errors3


def test_model_license_is_separate():
    m = _example("valid_drums")
    m["provenance"]["model"].pop("code_license")
    errors = validate_stem_manifest(m)
    assert any("provenance.model.code_license is required" in e for e in errors), errors

    m2 = _example("valid_drums")
    m2["provenance"]["model"].pop("weight_license")
    errors2 = validate_stem_manifest(m2)
    assert any("provenance.model.weight_license is required" in e for e in errors2), errors2


def test_model_attempted_run_requires_checkpoint_and_hash():
    m = _example("valid_drums")
    m["provenance"]["model"].pop("checkpoint")
    errors = validate_stem_manifest(m)
    assert any("provenance.model.checkpoint is required" in e for e in errors), errors

    m2 = _example("valid_drums")
    m2["provenance"]["model"].pop("weight_hash")
    errors2 = validate_stem_manifest(m2)
    assert any("provenance.model.weight_hash must have algorithm and value" in e for e in errors2), errors2
