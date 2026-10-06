"""Tests for AQ2 key/mode candidate comparison registry + metric parity (#987)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.export_fl import CONF_KEY_MIN
from src.fsld_aq2_key_candidate_compare import (
    DOCUMENT_TYPE,
    KEY_CANDIDATES,
    SCHEMA_VERSION,
    FsldAq2KeyCandidateCompareError,
    apply_key_candidate,
    candidate_by_id,
    evaluate_key_candidates,
    list_key_candidates,
    main,
    run_key_candidate_comparison,
)
from src.fsld_current_analyzer_eval import (
    _key_confusion_metrics,
    _key_metrics,
    _mode_metrics,
    _tonality_metrics,
)
from src.fsld_human_manifest import canonical_manifest_bytes


def _record(
    sample_id: str,
    *,
    split: str = "TEST",
    tier: str = "ma",
    tonality: str = "tonal",
    key_root: str | None = "C",
    root_evidence: str = "known",
    key_mode: str | None = "maj",
    mode_evidence: str = "known",
) -> dict[str, object]:
    return {
        "public_sample_id": sample_id,
        "split": split,
        "annotation_tier": tier,
        "ground_truth": {
            "tonality": tonality,
            "key_root": key_root,
            "root_evidence": root_evidence,
            "key_mode": key_mode,
            "mode_evidence": mode_evidence,
            "bpm": 120.0,
            "bpm_evidence": "known",
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


def _features(
    *,
    key: str | None,
    key_mode: str | None,
    key_conf: float | None,
    contrast: float | None,
    major: float | None = 0.8,
    minor: float | None = 0.2,
) -> SimpleNamespace:
    evidence = None
    if contrast is not None and major is not None and minor is not None:
        evidence = {
            "kind": "third_contrast",
            "major_third_energy": major,
            "minor_third_energy": minor,
            "contrast": contrast,
            "threshold": 0.30,
            "mode": key_mode,
        }
    return SimpleNamespace(
        key=key,
        key_mode=key_mode,
        bpm=120.0,
        key_conf=key_conf,
        key_mode_evidence=evidence,
        quality_note=None,
    )


def test_key_candidate_registry_is_frozen_and_thin() -> None:
    candidates = list_key_candidates()
    assert 1 <= len(candidates) <= 4
    assert candidates == list(KEY_CANDIDATES)
    ids = [c.candidate_id for c in candidates]
    assert len(ids) == len(set(ids))
    by_id = {c.candidate_id: c for c in candidates}
    baseline = candidate_by_id("extract_features.key_v1.mode_contrast.0.30")
    assert baseline.mode_contrast_min == 0.30
    assert baseline.key_conf_min is None
    assert baseline.analyzer_id == "sample_brain.analyze.extract_features"
    assert "extract_features.key_v1.mode_contrast.0.10" in by_id
    assert "extract_features.key_v1.mode_contrast.0.50" in by_id
    gated = by_id["extract_features.key_v1.key_conf_gate.0.55"]
    assert gated.mode_contrast_min == 0.30
    assert gated.key_conf_min == CONF_KEY_MIN == 0.55


def test_apply_key_candidate_recomputes_mode_and_conf_gate() -> None:
    shared = {
        "raw_predicted_key_root": "C",
        "raw_predicted_key_mode": None,
        "raw_key_conf": 0.42,
        "raw_key_mode_evidence": {
            "kind": "third_contrast",
            "major_third_energy": 0.9,
            "minor_third_energy": 0.1,
            "contrast": 0.8,
            "threshold": 0.30,
            "mode": "maj",
        },
        "status": "ok",
    }
    permissive = apply_key_candidate(
        shared, candidate_by_id("extract_features.key_v1.mode_contrast.0.10")
    )
    assert permissive["predicted_key_root"] == "C"
    assert permissive["predicted_key_mode"] == "maj"

    strict = apply_key_candidate(
        {
            **shared,
            "raw_key_mode_evidence": {
                "kind": "third_contrast",
                "major_third_energy": 0.55,
                "minor_third_energy": 0.45,
                "contrast": 0.1,
                "threshold": 0.30,
                "mode": None,
            },
        },
        candidate_by_id("extract_features.key_v1.mode_contrast.0.50"),
    )
    assert strict["predicted_key_root"] == "C"
    assert strict["predicted_key_mode"] is None

    gated = apply_key_candidate(
        shared, candidate_by_id("extract_features.key_v1.key_conf_gate.0.55")
    )
    assert gated["predicted_key_root"] is None
    assert gated["predicted_key_mode"] is None
    assert gated["predicted_key"] is None


def test_candidate_metrics_reuse_aq2_helpers_and_preserve_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        _record("300"),  # clear maj, high conf
        _record("301"),  # ambiguous mode contrast
        _record("302", tonality="no_key", key_root=None, root_evidence="n/a", key_mode=None, mode_evidence="n/a"),
        _record("303"),  # missing prediction
    ]
    manifest_path, sidecar_path = _write_manifest(tmp_path, records)
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    for record in records:
        (audio_root / f"{record['public_sample_id']}.wav").touch()
    predictions = {
        "300": _features(key="Cmaj", key_mode="maj", key_conf=0.80, contrast=0.80, major=0.9, minor=0.1),
        "301": _features(key="C", key_mode=None, key_conf=0.20, contrast=0.12, major=0.56, minor=0.44),
        "302": _features(key="G", key_mode=None, key_conf=0.15, contrast=0.05, major=0.52, minor=0.48),
        "303": _features(key=None, key_mode=None, key_conf=None, contrast=None, major=None, minor=None),
    }

    def fake_extract(path: Path, _duration: float | None, *, bpm_normalization: str):
        assert bpm_normalization == "none"
        return predictions[path.stem]

    monkeypatch.setattr(
        "src.fsld_current_analyzer_eval.extract_features", fake_extract
    )
    result = evaluate_key_candidates(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )

    assert result["document_type"] == DOCUMENT_TYPE
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["run_status"] == "EVALUATED"
    assert result["auroc_auprc_status"] == "HOLD"
    assert result["calibration_status"] == "HOLD"
    assert result["raw_source"] == "live_extract_features"
    assert len(result["candidates"]) == 4

    by_id = {entry["candidate_id"]: entry for entry in result["candidates"]}
    baseline = by_id["extract_features.key_v1.mode_contrast.0.30"]["metrics"]["ma"]
    permissive = by_id["extract_features.key_v1.mode_contrast.0.10"]["metrics"]["ma"]
    gated = by_id["extract_features.key_v1.key_conf_gate.0.55"]["metrics"]["ma"]

    for plane in ("key_root", "key_mode", "full_key", "key_confusion", "tonality"):
        assert plane in baseline
    assert baseline["tonality"]["auroc_auprc"] == "HOLD"
    assert baseline["tonality"]["calibration"] == "HOLD"
    assert "tempo" not in baseline

    # Permissive threshold commits mode on the ambiguous sample; baseline does not.
    assert permissive["key_mode"]["predicted"] >= baseline["key_mode"]["predicted"]
    # Export conf gate abstains on low-conf roots → lower tonal coverage / false claims.
    assert gated["tonality"]["coverage_rate"] <= baseline["tonality"]["coverage_rate"]
    assert gated["tonality"]["false_key_claim_rate"] <= baseline["tonality"]["false_key_claim_rate"]

    # Metric parity: rebuild baseline plane via the same helpers.
    adapted = [
        {
            "ground_truth": record["ground_truth"],
            "annotation_tier": record["annotation_tier"],
            **apply_key_candidate(
                record, candidate_by_id("extract_features.key_v1.mode_contrast.0.30")
            ),
        }
        for record in result["records"]
        if record["annotation_tier"] == "ma"
    ]
    assert _key_metrics(adapted, full_key=False) == baseline["key_root"]
    assert _mode_metrics(adapted) == baseline["key_mode"]
    assert _key_metrics(adapted, full_key=True) == baseline["full_key"]
    assert _key_confusion_metrics(adapted) == baseline["key_confusion"]
    assert _tonality_metrics(adapted) == baseline["tonality"]


def test_baseline_predictions_path_applies_adapters_without_audio(tmp_path: Path) -> None:
    records = [
        _record("10"),
        _record("11", tonality="no_key", key_root=None, root_evidence="n/a", key_mode=None, mode_evidence="n/a"),
    ]
    manifest_path, sidecar_path = _write_manifest(tmp_path, records)
    baseline = {
        "document_type": "sample_brain.fsld_current_analyzer_eval",
        "schema_version": "1.0.0",
        "split": "TEST",
        "run_status": "EVALUATED",
        "manifest_sha256": hashlib.sha256(
            canonical_manifest_bytes(
                {
                    "document_type": "sample_brain.fsld_human_manifest",
                    "schema_version": "1.0.0",
                    "records": records,
                }
            )
        ).hexdigest(),
        "records": [
            {
                "public_sample_id": "10",
                "split": "TEST",
                "annotation_tier": "ma",
                "ground_truth": records[0]["ground_truth"],
                "key_analysis_contract_version": 1,
                "mode_contrast_min": 0.30,
                "predicted_key_root": "C",
                "predicted_key_mode": None,
                "predicted_key": "C",
                "status": "ok",
                "native_evidence": {
                    "key_conf": 0.20,
                    "key_mode_evidence": {
                        "kind": "third_contrast",
                        "major_third_energy": 0.56,
                        "minor_third_energy": 0.44,
                        "contrast": 0.12,
                        "threshold": 0.30,
                        "mode": None,
                    },
                },
            },
            {
                "public_sample_id": "11",
                "split": "TEST",
                "annotation_tier": "ma",
                "ground_truth": records[1]["ground_truth"],
                "key_analysis_contract_version": 1,
                "mode_contrast_min": 0.30,
                "predicted_key_root": "G",
                "predicted_key_mode": None,
                "predicted_key": "G",
                "status": "ok",
                "native_evidence": {
                    "key_conf": 0.10,
                    "key_mode_evidence": {
                        "kind": "third_contrast",
                        "major_third_energy": 0.5,
                        "minor_third_energy": 0.5,
                        "contrast": 0.0,
                        "threshold": 0.30,
                        "mode": None,
                    },
                },
            },
        ],
        "metrics": {"ma": {}, "sa": {}},
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    result = evaluate_key_candidates(
        baseline_predictions_path=baseline_path,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )
    assert result["raw_source"] == "baseline_predictions"
    assert result["run_status"] == "EVALUATED"
    by_id = {entry["candidate_id"]: entry for entry in result["candidates"]}
    permissive = by_id["extract_features.key_v1.mode_contrast.0.10"]["metrics"]["ma"]
    gated = by_id["extract_features.key_v1.key_conf_gate.0.55"]["metrics"]["ma"]
    assert permissive["key_mode"]["predicted"] == 1
    assert gated["tonality"]["false_key_claims"] == 0
    assert gated["key_root"]["predicted"] == 0


def test_runner_rejects_in_repo_output_and_requires_exclusive_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10")])
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq2_key_candidate_compare.REPOSITORY_ROOT", repo_root
    )
    with pytest.raises(FsldAq2KeyCandidateCompareError, match="outside"):
        run_key_candidate_comparison(
            audio_root=tmp_path / "audio",
            split="TEST",
            output_path=repo_root / "out.json",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )
    with pytest.raises(FsldAq2KeyCandidateCompareError, match="exactly one"):
        evaluate_key_candidates(
            audio_root=tmp_path / "audio",
            baseline_predictions_path=tmp_path / "baseline.json",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )
    with pytest.raises(FsldAq2KeyCandidateCompareError, match="exactly one"):
        evaluate_key_candidates(
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )


def test_missing_audio_is_explicit_non_baseline(tmp_path: Path) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10")])
    audio_root = tmp_path / "empty-audio"
    audio_root.mkdir()
    output_path = tmp_path.parent / "aq2-compare-missing.json"
    result = evaluate_key_candidates(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )
    assert result["run_status"] == "PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY"
    assert all(entry["metrics"] is None for entry in result["candidates"])
    assert (
        main(
            [
                "--audio-root",
                str(audio_root),
                "--split",
                "TEST",
                "--output",
                str(output_path),
                "--manifest",
                str(manifest_path),
                "--sha256",
                str(sidecar_path),
            ]
        )
        != 0
    )
