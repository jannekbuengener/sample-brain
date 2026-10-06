"""Tests for AQ1 tempo candidate comparison registry + metric parity (#977)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.analyze import normalize_bpm
from src.fsld_aq1_tempo_candidate_compare import (
    DOCUMENT_TYPE,
    SCHEMA_VERSION,
    TEMPO_CANDIDATES,
    FsldAq1TempoCandidateCompareError,
    candidate_by_id,
    evaluate_tempo_candidates,
    list_tempo_candidates,
    main,
    run_tempo_candidate_comparison,
)
from src.fsld_current_analyzer_eval import _tempo_metrics
from src.fsld_human_manifest import canonical_manifest_bytes


def _record(
    sample_id: str,
    *,
    split: str = "TEST",
    tier: str = "ma",
    bpm: float | None = 120.0,
    bpm_evidence: str = "known",
) -> dict[str, object]:
    return {
        "public_sample_id": sample_id,
        "split": split,
        "annotation_tier": tier,
        "ground_truth": {
            "tonality": "tonal",
            "key_root": "C",
            "root_evidence": "known",
            "key_mode": "maj",
            "mode_evidence": "known",
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


def _features(bpm: float | None) -> SimpleNamespace:
    return SimpleNamespace(
        key="Cmaj",
        key_mode="maj",
        bpm=bpm,
        key_conf=0.42,
        key_mode_evidence={"kind": "third_contrast", "contrast": 0.5},
        quality_note=None,
    )


def test_tempo_candidate_registry_is_frozen_and_thin() -> None:
    candidates = list_tempo_candidates()
    assert 1 <= len(candidates) <= 4
    assert candidates == list(TEMPO_CANDIDATES)
    ids = [c.candidate_id for c in candidates]
    assert len(ids) == len(set(ids))
    modes = {c.bpm_normalization for c in candidates}
    assert modes == {"none", "heuristic", "domain_110_170"}
    baseline = candidate_by_id("extract_features.bpm_normalization.none")
    assert baseline.bpm_normalization == "none"
    assert baseline.analyzer_id == "sample_brain.analyze.extract_features"


def test_candidate_metrics_reuse_tempo_metrics_and_preserve_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = [
        _record("200", bpm=120.0),  # raw 120 -> correct
        _record("201", bpm=120.0),  # raw 60 -> half; domain folds to 120
        _record("202", bpm=120.0),  # raw 240 -> double; heuristic folds to 120
        _record("203", bpm=100.0),  # missing prediction
    ]
    manifest_path, sidecar_path = _write_manifest(tmp_path, records)
    audio_root = tmp_path / "audio"
    audio_root.mkdir()
    for record in records:
        (audio_root / f"{record['public_sample_id']}.wav").touch()
    predictions = {
        "200": _features(120.0),
        "201": _features(60.0),
        "202": _features(240.0),
        "203": _features(None),
    }

    def fake_extract(path: Path, _duration: float | None, *, bpm_normalization: str):
        assert bpm_normalization == "none"
        return predictions[path.stem]

    monkeypatch.setattr(
        "src.fsld_current_analyzer_eval.extract_features", fake_extract
    )
    result = evaluate_tempo_candidates(
        audio_root=audio_root,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )

    assert result["document_type"] == DOCUMENT_TYPE
    assert result["schema_version"] == SCHEMA_VERSION
    assert result["run_status"] == "EVALUATED"
    assert result["beat_grid_status"] == "HOLD"
    assert result["raw_source"] == "live_extract_features"
    assert len(result["candidates"]) == 3

    by_id = {entry["candidate_id"]: entry for entry in result["candidates"]}
    none_tempo = by_id["extract_features.bpm_normalization.none"]["metrics"]["ma"]["tempo"]
    heuristic_tempo = by_id["extract_features.bpm_normalization.heuristic"]["metrics"]["ma"][
        "tempo"
    ]
    domain_tempo = by_id["extract_features.bpm_normalization.domain_110_170"]["metrics"]["ma"][
        "tempo"
    ]

    required = {
        "eligible",
        "predicted",
        "coverage_rate",
        "abstention_rate",
        "accuracy_within_0_5_bpm",
        "accuracy_within_1_bpm",
        "accuracy_within_2_bpm",
        "absolute_bpm_error",
        "relative_bpm_error",
        "relation_counts",
        "relation_rates",
    }
    assert required <= set(none_tempo)
    assert none_tempo["relation_counts"]["half"] == 1
    assert none_tempo["relation_counts"]["double"] == 1
    assert heuristic_tempo["relation_counts"]["double"] == 0
    assert heuristic_tempo["relation_counts"]["correct"] >= none_tempo["relation_counts"]["correct"]
    assert domain_tempo["relation_counts"]["half"] == 0
    assert domain_tempo["relation_counts"]["correct"] >= none_tempo["relation_counts"]["correct"]

    # Metric parity: rebuild from shared raw predictions via the same helper.
    shared = result["records"]
    rebuilt = []
    for record in shared:
        rebuilt.append(
            {
                **record,
                "predicted_bpm": normalize_bpm(
                    record["raw_predicted_bpm"], mode="none"
                ),
            }
        )
    assert _tempo_metrics(rebuilt) == none_tempo


def test_baseline_predictions_path_applies_adapters_without_audio(
    tmp_path: Path,
) -> None:
    records = [
        _record("10", bpm=120.0),
        _record("11", bpm=120.0),
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
                "bpm_normalization": "none",
                "predicted_bpm": 60.0,
                "status": "ok",
            },
            {
                "public_sample_id": "11",
                "split": "TEST",
                "annotation_tier": "ma",
                "ground_truth": records[1]["ground_truth"],
                "bpm_normalization": "none",
                "predicted_bpm": 120.0,
                "status": "ok",
            },
        ],
        "metrics": {"ma": {"tempo": {}}, "sa": {"tempo": {}}},
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    result = evaluate_tempo_candidates(
        baseline_predictions_path=baseline_path,
        split="TEST",
        manifest_path=manifest_path,
        sha256_path=sidecar_path,
    )
    assert result["raw_source"] == "baseline_predictions"
    assert result["run_status"] == "EVALUATED"
    by_id = {entry["candidate_id"]: entry for entry in result["candidates"]}
    none_tempo = by_id["extract_features.bpm_normalization.none"]["metrics"]["ma"]["tempo"]
    domain_tempo = by_id["extract_features.bpm_normalization.domain_110_170"]["metrics"]["ma"][
        "tempo"
    ]
    assert none_tempo["relation_counts"]["half"] == 1
    assert domain_tempo["relation_counts"]["half"] == 0
    assert domain_tempo["relation_counts"]["correct"] == 2


def test_runner_rejects_in_repo_output_and_requires_exclusive_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10")])
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", repo_root
    )
    with pytest.raises(FsldAq1TempoCandidateCompareError, match="outside"):
        run_tempo_candidate_comparison(
            audio_root=tmp_path / "audio",
            split="TEST",
            output_path=repo_root / "out.json",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )
    with pytest.raises(FsldAq1TempoCandidateCompareError, match="exactly one"):
        evaluate_tempo_candidates(
            audio_root=tmp_path / "audio",
            baseline_predictions_path=tmp_path / "baseline.json",
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )
    with pytest.raises(FsldAq1TempoCandidateCompareError, match="exactly one"):
        evaluate_tempo_candidates(
            split="TEST",
            manifest_path=manifest_path,
            sha256_path=sidecar_path,
        )


def test_missing_audio_is_explicit_non_baseline(tmp_path: Path) -> None:
    manifest_path, sidecar_path = _write_manifest(tmp_path, [_record("10")])
    audio_root = tmp_path / "empty-audio"
    audio_root.mkdir()
    output_path = tmp_path.parent / "compare-missing.json"
    result = evaluate_tempo_candidates(
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
