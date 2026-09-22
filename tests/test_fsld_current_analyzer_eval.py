from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.fsld_current_analyzer_eval import (
    FsldCurrentAnalyzerEvalError,
    evaluate_current_analyzer,
    main,
    run_current_analyzer_evaluation,
)
from src.fsld_human_manifest import canonical_manifest_bytes


def _record(
    sample_id: str,
    *,
    split: str = "TEST",
    tier: str = "ma",
    root: str | None = "C",
    root_evidence: str = "known",
    mode: str | None = "maj",
    mode_evidence: str = "known",
    bpm: float | None = 120.0,
    bpm_evidence: str = "known",
    tonality: str = "tonal",
) -> dict[str, object]:
    return {
        "public_sample_id": sample_id,
        "split": split,
        "annotation_tier": tier,
        "ground_truth": {
            "tonality": tonality,
            "key_root": root,
            "root_evidence": root_evidence,
            "key_mode": mode,
            "mode_evidence": mode_evidence,
            "bpm": bpm,
            "bpm_evidence": bpm_evidence,
        },
    }


def _write_manifest(tmp_path: Path, records: list[dict[str, object]]) -> tuple[Path, Path]:
    manifest = {
        "document_type": "sample_brain.fsld_human_manifest",
        "schema_version": "1.0.0",
        "records": records,
    }
    manifest_path = tmp_path / "manifest.json"
    sidecar_path = tmp_path / "manifest.sha256"
    payload = canonical_manifest_bytes(manifest)
    manifest_path.write_bytes(payload)
    sidecar_path.write_text(
        f"{hashlib.sha256(payload).hexdigest()}  {manifest_path.name}\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_path, sidecar_path


def _features(key: str | None, mode: str | None, bpm: float | None) -> SimpleNamespace:
    return SimpleNamespace(
        key=key,
        key_mode=mode,
        bpm=bpm,
        key_conf=0.42,
        key_mode_evidence={"kind": "third_contrast", "contrast": 0.5},
        quality_note=None,
    )


def test_manifest_verification_fails_closed_for_noncanonical_bytes_and_sidecar(tmp_path: Path) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10")])
    manifest_path.write_bytes(manifest_path.read_bytes() + b" ")

    with pytest.raises(FsldCurrentAnalyzerEvalError, match="canonical"):
        evaluate_current_analyzer(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )

    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10")])
    sidecar_path.write_text("bad\n", encoding="utf-8")
    with pytest.raises(FsldCurrentAnalyzerEvalError, match="SHA256"):
        evaluate_current_analyzer(
            audio_root=tmp_path / "audio",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )


def test_runner_uses_only_id_wav_mapping_and_keeps_missing_audio_without_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, sidecar_path = _write_manifest(
        tmp_path, [_record("2"), _record("10")]
    )
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    (audio_root / "2.wav").touch()
    calls: list[Path] = []

    def fake_extract(path: Path, duration: float | None, *, bpm_normalization: str):
        calls.append(path)
        assert duration is None
        assert bpm_normalization == "none"
        return _features("Cmaj", "maj", 120.0)

    monkeypatch.setattr("src.fsld_current_analyzer_eval.extract_features", fake_extract)
    result = evaluate_current_analyzer(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )

    assert calls == [audio_root / "2.wav"]
    assert [record["public_sample_id"] for record in result["records"]] == ["2", "10"]
    assert result["records"][1]["status"] == "missing_audio"
    assert result["records"][1]["exclusion_reason"] == "audio_missing"
    assert result["run_status"] == "EVALUATED"
    encoded = json.dumps(result, sort_keys=True)
    assert str(audio_root) not in encoded
    assert "2.wav" not in encoded


@pytest.mark.parametrize("audio_root_name", ("missing-audio", "empty-audio"))
def test_zero_audio_is_explicitly_non_baseline_and_cli_is_non_success(
    tmp_path: Path, audio_root_name: str
) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10"), _record("11")])
    audio_root = tmp_path / audio_root_name
    if audio_root_name == "empty-audio":
        audio_root.mkdir()
    output_path = tmp_path.parent / f"{audio_root_name}-result.json"

    result = evaluate_current_analyzer(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )

    assert result["run_status"] == "PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY"
    assert result["metrics"] is None
    assert [record["status"] for record in result["records"]] == ["missing_audio", "missing_audio"]
    assert main([
        "--audio-root", str(audio_root),
        "--split", "TEST",
        "--output", str(output_path),
        "--manifest", str(manifest_path),
        "--sha256", str(sidecar_path),
    ]) != 0
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written["run_status"] == "PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY"
    assert written["metrics"] is None


def test_runner_rejects_output_inside_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10")])
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr("src.fsld_current_analyzer_eval.REPOSITORY_ROOT", repo_root)

    with pytest.raises(FsldCurrentAnalyzerEvalError, match="outside"):
        run_current_analyzer_evaluation(
            audio_root=tmp_path / "audio",
            split="TEST",
            output_path=repo_root / "result.json",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )


def test_metrics_remain_separate_by_annotation_tier_and_follow_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        _record("100", tier="ma", root="C", mode="maj", bpm=120.0),
        _record("101", tier="ma", root="D", mode="min", bpm=100.0),
        _record("102", tier="sa", root="C", mode="maj", bpm=100.0),
        _record("103", tier="sa", root=None, root_evidence="unknown", mode=None, mode_evidence="unknown"),
        _record("104", tier="sa", tonality="no_key", root=None, root_evidence="not_applicable", mode=None, mode_evidence="not_applicable"),
    ]
    manifest_path, sidecar_path = _write_manifest(tmp_path, records)
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    for record in records:
        (audio_root / f"{record['public_sample_id']}.wav").touch()
    predictions = {
        "100": _features("Cmaj", "maj", 120.0),
        "101": _features("D", None, 50.0),
        "102": _features("Dmin", "min", 200.0),
        "103": _features(None, None, None),
        "104": _features(None, None, None),
    }

    def fake_extract(path: Path, _duration: float | None, **_kwargs: object):
        return predictions[path.stem]

    monkeypatch.setattr("src.fsld_current_analyzer_eval.extract_features", fake_extract)
    result = evaluate_current_analyzer(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )

    ma = result["metrics"]["ma"]
    assert result["run_status"] == "EVALUATED"
    assert ma["key_root"] == {"eligible": 2, "predicted": 2, "exact": 2, "exact_rate": 1.0}
    assert ma["full_key"] == {"eligible": 2, "predicted": 1, "exact": 1, "exact_rate": 0.5}
    assert ma["tempo"]["relation_counts"]["correct"] == 1
    assert ma["tempo"]["relation_counts"]["half"] == 1

    sa = result["metrics"]["sa"]
    assert sa["key_root"] == {"eligible": 1, "predicted": 1, "exact": 0, "exact_rate": 0.0}
    assert sa["full_key"] == {"eligible": 1, "predicted": 1, "exact": 0, "exact_rate": 0.0}
    assert sa["tempo"]["relation_counts"]["double"] == 1
    assert sa["tempo"]["eligible"] == 3


def test_analysis_failures_remain_records_and_non_runtime_fields_are_stable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10"), _record("11")])
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    (audio_root / "10.wav").touch()
    (audio_root / "11.wav").touch()

    def fake_extract(path: Path, _duration: float | None, **_kwargs: object):
        if path.stem == "10":
            raise RuntimeError("private path must not escape")
        return None

    monkeypatch.setattr("src.fsld_current_analyzer_eval.extract_features", fake_extract)
    first = evaluate_current_analyzer(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )
    second = evaluate_current_analyzer(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )

    assert [record["status"] for record in first["records"]] == ["analysis_failed", "no_features"]
    assert "private path" not in json.dumps(first)
    for result in (first, second):
        for record in result["records"]:
            record["runtime_ms"] = None
    assert first == second
