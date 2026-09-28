from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import pytest

from src.fsld_human_manifest import DOCUMENT_TYPE as FSLD_MANIFEST_DOCUMENT_TYPE
from src.fsld_human_manifest import canonical_manifest_bytes
from src.joint_key_profile import JointKeyProfileError, MAJOR_PROFILE, SEMITONES, rotate_profile
from src.joint_key_profile_benchmark import (
    JointKeyProfileBenchmarkError,
    evaluate_joint_key_profiles,
    mean_cqt_chroma,
    score_audio,
)
from tests.audio_fixtures import write_major_chord_wav


def _write_manifest(tmp_path: Path, records: list[object]) -> tuple[Path, Path]:
    manifest = {"document_type": FSLD_MANIFEST_DOCUMENT_TYPE, "records": records}
    raw = canonical_manifest_bytes(manifest)
    manifest_path = tmp_path / "manifest.json"
    sha256_path = tmp_path / "manifest.sha256"
    manifest_path.write_bytes(raw)
    sha256_path.write_bytes(f"{hashlib.sha256(raw).hexdigest()}  {manifest_path.name}\n".encode("utf-8"))
    return manifest_path, sha256_path


def _valid_manifest_record() -> dict[str, object]:
    return {
        "public_sample_id": "123",
        "split": "TEST",
        "annotation_tier": "ma",
        "ground_truth": {},
    }


def _write_nonfinite_manifest(tmp_path: Path) -> tuple[Path, Path]:
    raw = (
        b'{"document_type":"sample_brain.fsld_human_manifest","records":['
        b'{"annotation_tier":"ma","ground_truth":{"bpm":NaN},'
        b'"public_sample_id":"123","split":"TEST"}]}\n'
    )
    manifest_path = tmp_path / "manifest.json"
    sha256_path = tmp_path / "manifest.sha256"
    manifest_path.write_bytes(raw)
    sha256_path.write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {manifest_path.name}\n", encoding="utf-8"
    )
    return manifest_path, sha256_path


def _write_oversized_integer_manifest(tmp_path: Path) -> tuple[Path, Path, bytes]:
    raw = b'{"oversized_integer":' + b"1" * (sys.get_int_max_str_digits() + 1) + b"}\n"
    manifest_path = tmp_path / "manifest.json"
    sha256_path = tmp_path / "manifest.sha256"
    manifest_path.write_bytes(raw)
    sha256_path.write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {manifest_path.name}\n", encoding="utf-8"
    )
    return manifest_path, sha256_path, raw


def test_adapter_uses_cqt_mean_and_returns_joint_raw_evidence(tmp_path: Path):
    audio = write_major_chord_wav(tmp_path / "c_major.wav")

    result = mean_cqt_chroma(audio)

    assert result.chroma_mean.shape == (12,)
    assert np.isfinite(result.chroma_mean).all()


def test_benchmark_reports_external_audio_unavailable_without_writing_repo_artifacts(tmp_path: Path):
    result = evaluate_joint_key_profiles(audio_root=tmp_path / "missing", split="TEST")

    assert result["run_status"] == "PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY"
    assert result["records"]


def test_invalid_chroma_from_adapter_is_fail_closed(monkeypatch, tmp_path: Path):
    audio = write_major_chord_wav(tmp_path / "c_major.wav")
    monkeypatch.setattr(
        "src.joint_key_profile_benchmark.mean_cqt_chroma",
        lambda _path: type("Result", (), {"chroma_mean": np.zeros(12)})(),
    )

    with pytest.raises(JointKeyProfileError):
        score_audio(audio)


def test_profile_fixture_input_is_accepted_by_core_contract():
    result = rotate_profile(MAJOR_PROFILE, SEMITONES.index("C"))
    assert result.shape == (12,)


@pytest.mark.parametrize(
    "record, message",
    [
        (["not", "an", "object"], "record 0 must be an object"),
        ({"split": "TEST", "annotation_tier": "ma", "ground_truth": {}}, "public_sample_id"),
        ({**_valid_manifest_record(), "public_sample_id": 123}, "public_sample_id"),
        ({**_valid_manifest_record(), "split": "UNSUPPORTED"}, "split"),
        ({**_valid_manifest_record(), "annotation_tier": "unknown"}, "annotation_tier"),
        ({key: value for key, value in _valid_manifest_record().items() if key != "ground_truth"}, "ground_truth"),
        ({**_valid_manifest_record(), "ground_truth": []}, "ground_truth"),
    ],
)
def test_external_manifest_rejects_malformed_records_with_controlled_error(
    tmp_path: Path, record: object, message: str
):
    manifest_path, sha256_path = _write_manifest(tmp_path, [record])

    with pytest.raises(JointKeyProfileBenchmarkError, match=message):
        evaluate_joint_key_profiles(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sha256_path,
        )


def test_external_manifest_rejects_nonfinite_json_with_controlled_error(tmp_path: Path):
    manifest_path, sha256_path = _write_nonfinite_manifest(tmp_path)

    with pytest.raises(JointKeyProfileBenchmarkError, match="non-finite JSON"):
        evaluate_joint_key_profiles(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sha256_path,
        )


def test_external_manifest_rejects_lone_surrogate_with_controlled_error(tmp_path: Path):
    raw = (
        b'{"document_type":"sample_brain.fsld_human_manifest","records":['
        b'{"annotation_tier":"ma","ground_truth":{"label":"\\ud800"},'
        b'"public_sample_id":"123","split":"TEST"}]}\n'
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(raw)

    parsed = json.loads(raw)
    assert parsed["records"][0]["ground_truth"]["label"] == "\ud800"
    with pytest.raises(UnicodeEncodeError):
        canonical_manifest_bytes(parsed)
    with pytest.raises(JointKeyProfileBenchmarkError, match="invalid Unicode"):
        evaluate_joint_key_profiles(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=tmp_path / "manifest.sha256",
        )


def test_external_manifest_rejects_oversized_json_integer_with_controlled_error(tmp_path: Path):
    manifest_path, sha256_path, raw = _write_oversized_integer_manifest(tmp_path)

    with pytest.raises(ValueError, match="Exceeds the limit"):
        json.loads(raw)
    with pytest.raises(JointKeyProfileBenchmarkError, match="UTF-8 JSON"):
        evaluate_joint_key_profiles(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sha256_path,
        )


def test_external_manifest_translates_parse_recursion_error(monkeypatch, tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(b"{}")

    def raise_recursion_error(_payload: str) -> object:
        raise RecursionError("nested JSON")

    monkeypatch.setattr(
        "src.joint_key_profile_benchmark.json.loads",
        raise_recursion_error,
    )

    with pytest.raises(JointKeyProfileBenchmarkError, match="UTF-8 JSON"):
        evaluate_joint_key_profiles(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=tmp_path / "manifest.sha256",
        )


def test_external_manifest_rejects_oversized_decimal_sample_id_with_controlled_error(
    tmp_path: Path,
):
    sample_id = "1" * (sys.get_int_max_str_digits() + 1)
    manifest_path, sha256_path = _write_manifest(
        tmp_path, [{**_valid_manifest_record(), "public_sample_id": sample_id}]
    )

    parsed = json.loads(manifest_path.read_bytes())
    assert parsed["records"][0]["public_sample_id"] == sample_id
    assert sample_id.isdecimal()
    with pytest.raises(ValueError, match="Exceeds the limit"):
        int(sample_id)
    with pytest.raises(JointKeyProfileBenchmarkError, match="convertible to integer"):
        evaluate_joint_key_profiles(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sha256_path,
        )
