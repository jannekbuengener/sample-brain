"""AQ1 thin headless DomainAdapter proof (#1054 M3).

Path B (baseline-predictions) only — deterministic, no live audio.
Registry wiring is owned by M6 (`STATIC_ADAPTER_REGISTRY`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import (
    STATIC_ADAPTER_REGISTRY,
    DomainAdapter,
    build_request,
    lookup_adapter,
    validate_result,
)
from src.aq_headless_adapters.aq1_tempo_compare import (
    ADAPTER_ID,
    ADAPTER_VERSION,
    DOMAIN,
    Aq1TempoCompareAdapter,
    tempo_candidate_config_fingerprint,
)
from src.fsld_aq1_tempo_candidate_compare import TEMPO_CANDIDATES
from src.fsld_human_manifest import canonical_manifest_bytes


def _record(
    sample_id: str,
    *,
    split: str = "CALIBRATION",
    tier: str = "ma",
    bpm: float | None = 120.0,
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
            "bpm_evidence": "known",
        },
    }


def _write_manifest(work_dir: Path, records: list[dict[str, object]]) -> tuple[str, str]:
    manifest = {
        "document_type": "sample_brain.fsld_human_manifest",
        "schema_version": "1.0.0",
        "records": records,
    }
    manifest_rel = "manifest.json"
    sha_rel = "manifest.sha256"
    payload = canonical_manifest_bytes(manifest)
    (work_dir / manifest_rel).write_bytes(payload)
    (work_dir / sha_rel).write_text(
        f"{hashlib.sha256(payload).hexdigest()}  {manifest_rel}\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest_rel, sha_rel


def _write_baseline_predictions(
    work_dir: Path,
    *,
    records: list[dict[str, object]],
    predicted: list[tuple[str, float | None, str]],
    split: str = "CALIBRATION",
) -> str:
    manifest_sha = hashlib.sha256(
        canonical_manifest_bytes(
            {
                "document_type": "sample_brain.fsld_human_manifest",
                "schema_version": "1.0.0",
                "records": records,
            }
        )
    ).hexdigest()
    baseline_records = []
    by_id = {str(r["public_sample_id"]): r for r in records}
    for sample_id, predicted_bpm, status in predicted:
        src = by_id[sample_id]
        baseline_records.append(
            {
                "public_sample_id": sample_id,
                "split": split,
                "annotation_tier": src["annotation_tier"],
                "ground_truth": src["ground_truth"],
                "bpm_normalization": "none",
                "predicted_bpm": predicted_bpm,
                "status": status,
            }
        )
    payload = {
        "document_type": "sample_brain.fsld_current_analyzer_eval",
        "schema_version": "1.0.0",
        "split": split,
        "run_status": "EVALUATED",
        "manifest_sha256": manifest_sha,
        "records": baseline_records,
        "metrics": {"ma": {"tempo": {}}, "sa": {"tempo": {}}},
    }
    rel = "baseline.json"
    (work_dir / rel).write_text(json.dumps(payload), encoding="utf-8")
    return rel


def _outside_work_dir(tmp_path: Path) -> Path:
    """Prefer a work dir that is not under the repository tree."""
    work = tmp_path / "aq1-headless-work"
    work.mkdir(parents=True, exist_ok=True)
    return work


def _baseline_id() -> str:
    return TEMPO_CANDIDATES[0].candidate_id


def _current_id() -> str:
    return TEMPO_CANDIDATES[1].candidate_id


def _path_b_request(
    work_dir: Path,
    *,
    operation: str = "compare",
    partition_role: str = "calibration",
    split: str = "CALIBRATION",
) -> dict[str, Any]:
    records = [
        _record("10", split=split, bpm=120.0),
        _record("11", split=split, bpm=120.0),
    ]
    manifest_rel, sha_rel = _write_manifest(work_dir, records)
    baseline_rel = _write_baseline_predictions(
        work_dir,
        records=records,
        predicted=[("10", 60.0, "ok"), ("11", 120.0, "ok")],
        split=split,
    )
    dataset_fp = fingerprint(
        {
            "dataset_id": "aq1-path-b-smoke",
            "members": sorted(r["public_sample_id"] for r in records),
            "manifest_relpath": manifest_rel,
            "baseline_predictions_relpath": baseline_rel,
        }
    )
    return build_request(
        domain=DOMAIN,
        adapter_id=ADAPTER_ID,
        operation=operation,
        benchmark_id="aq1-tempo-bench-v1",
        dataset_id="aq1-path-b-smoke",
        dataset_content_fingerprint=dataset_fp,
        partition_id="aq1-cal-p1",
        partition_role=partition_role,
        baseline_candidate_id=_baseline_id(),
        baseline_config_fingerprint=tempo_candidate_config_fingerprint(_baseline_id()),
        current_candidate_id=_current_id(),
        current_config_fingerprint=tempo_candidate_config_fingerprint(_current_id()),
        evidence_intent="domain_artifact",
        extra_fields={
            "aq1_inputs": {
                "raw_source": "baseline_predictions",
                "baseline_predictions_relpath": baseline_rel,
                "output_relpath": "out/aq1-compare.json",
                "manifest_relpath": manifest_rel,
                "sha256_relpath": sha_rel,
                "split": split,
            }
        },
    )


def test_adapter_id_and_version_are_frozen() -> None:
    assert ADAPTER_ID == "aq1.tempo.candidate_compare"
    assert ADAPTER_VERSION == "1.0.0"
    assert DOMAIN == "aq1.tempo"


def test_adapter_implements_domain_adapter_protocol(tmp_path: Path) -> None:
    adapter = Aq1TempoCompareAdapter(work_dir=_outside_work_dir(tmp_path))
    assert isinstance(adapter, DomainAdapter)
    assert adapter.adapter_id == ADAPTER_ID
    assert adapter.adapter_version == ADAPTER_VERSION
    assert "compare" in adapter.capabilities
    assert "baseline" in adapter.capabilities
    assert "locked_evaluation" in adapter.capabilities


def test_adapter_registered_in_static_registry() -> None:
    """M6 wires STATIC_ADAPTER_REGISTRY; entry requires host bind before run."""
    assert ADAPTER_ID in STATIC_ADAPTER_REGISTRY
    entry = lookup_adapter(ADAPTER_ID)
    assert entry.adapter_id == ADAPTER_ID
    assert entry.adapter_version == ADAPTER_VERSION
    with pytest.raises(Exception, match="unbound"):
        entry.run({})


def test_path_b_compare_completes_with_domain_artifact_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _outside_work_dir(tmp_path)
    # Ensure runner outside-repo guard uses a synthetic repo root.
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    adapter = Aq1TempoCompareAdapter(work_dir=work)
    request = _path_b_request(work)
    result = adapter.run(request)
    validated = validate_result(result)

    assert validated["run_status"] == "completed"
    assert validated["adapter_id"] == ADAPTER_ID
    assert validated["adapter_version"] == ADAPTER_VERSION
    assert validated["request_fingerprint"] == request["request_fingerprint"]
    assert validated["production_authorized"] is False
    assert "decision_token" not in validated
    assert "next_action" not in validated
    assert "metrics" not in validated
    da = validated["domain_artifact"]
    assert da["artifact_id"]
    assert len(da["artifact_fingerprint"]) == 64
    out_path = work / "out" / "aq1-compare.json"
    assert out_path.is_file()
    domain_payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert domain_payload["raw_source"] == "baseline_predictions"
    assert domain_payload["run_status"] == "EVALUATED"


def test_path_b_compare_is_deterministic_across_repeated_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _outside_work_dir(tmp_path)
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    adapter = Aq1TempoCompareAdapter(work_dir=work)
    request = _path_b_request(work)

    first = validate_result(adapter.run(request))
    # Second run writes same relative output; fingerprints must match.
    second = validate_result(adapter.run(request))
    assert first["result_fingerprint"] == second["result_fingerprint"]
    assert (
        first["domain_artifact"]["artifact_fingerprint"]
        == second["domain_artifact"]["artifact_fingerprint"]
    )


def test_result_rejects_absolute_path_leakage_in_envelope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _outside_work_dir(tmp_path)
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    adapter = Aq1TempoCompareAdapter(work_dir=work)
    result = validate_result(adapter.run(_path_b_request(work)))
    blob = json.dumps(result)
    assert ":\\" not in blob
    assert "\\\\" not in blob.replace("\\\\", "")
    # Portable guard: no drive-letter absolute forms in string values.
    def _walk(value: object) -> None:
        if isinstance(value, str):
            assert not (len(value) >= 3 and value[1] == ":" and value[2] in "\\/")
            assert not value.startswith("/")
            assert not value.lower().startswith("file://")
        elif isinstance(value, dict):
            for child in value.values():
                _walk(child)
        elif isinstance(value, list):
            for child in value:
                _walk(child)

    _walk(result)


def test_controlled_failure_on_missing_baseline_predictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _outside_work_dir(tmp_path)
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    records = [_record("10")]
    manifest_rel, sha_rel = _write_manifest(work, records)
    request = build_request(
        domain=DOMAIN,
        adapter_id=ADAPTER_ID,
        operation="compare",
        benchmark_id="aq1-tempo-bench-v1",
        dataset_id="aq1-missing-baseline",
        dataset_content_fingerprint=fingerprint({"members": ["10"]}),
        partition_id="aq1-cal-p1",
        partition_role="calibration",
        baseline_candidate_id=_baseline_id(),
        baseline_config_fingerprint=tempo_candidate_config_fingerprint(_baseline_id()),
        current_candidate_id=_current_id(),
        current_config_fingerprint=tempo_candidate_config_fingerprint(_current_id()),
        evidence_intent="domain_artifact",
        extra_fields={
            "aq1_inputs": {
                "raw_source": "baseline_predictions",
                "baseline_predictions_relpath": "missing-baseline.json",
                "output_relpath": "out/fail.json",
                "manifest_relpath": manifest_rel,
                "sha256_relpath": sha_rel,
                "split": "CALIBRATION",
            }
        },
    )
    adapter = Aq1TempoCompareAdapter(work_dir=work)
    result = validate_result(adapter.run(request))
    assert result["run_status"] == "controlled_failure"
    assert result["error"]["code"]
    assert result["error"]["detail"]
    assert result.get("domain_artifact") is None
    assert "decision_token" not in result
    assert "next_action" not in result


def test_hold_when_path_b_has_no_successful_predictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = _outside_work_dir(tmp_path)
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    records = [_record("10"), _record("11")]
    manifest_rel, sha_rel = _write_manifest(work, records)
    baseline_rel = _write_baseline_predictions(
        work,
        records=records,
        predicted=[
            ("10", None, "missing_audio"),
            ("11", None, "missing_audio"),
        ],
        split="CALIBRATION",
    )
    request = build_request(
        domain=DOMAIN,
        adapter_id=ADAPTER_ID,
        operation="compare",
        benchmark_id="aq1-tempo-bench-v1",
        dataset_id="aq1-hold-smoke",
        dataset_content_fingerprint=fingerprint({"members": ["10", "11"]}),
        partition_id="aq1-cal-p1",
        partition_role="calibration",
        baseline_candidate_id=_baseline_id(),
        baseline_config_fingerprint=tempo_candidate_config_fingerprint(_baseline_id()),
        current_candidate_id=_current_id(),
        current_config_fingerprint=tempo_candidate_config_fingerprint(_current_id()),
        evidence_intent="domain_artifact",
        extra_fields={
            "aq1_inputs": {
                "raw_source": "baseline_predictions",
                "baseline_predictions_relpath": baseline_rel,
                "output_relpath": "out/hold.json",
                "manifest_relpath": manifest_rel,
                "sha256_relpath": sha_rel,
                "split": "CALIBRATION",
            }
        },
    )
    adapter = Aq1TempoCompareAdapter(work_dir=work)
    result = validate_result(adapter.run(request))
    assert result["run_status"] == "hold"
    assert result["error"]["code"]
    assert result.get("domain_artifact") is None


def test_tempo_candidate_config_fingerprint_stable() -> None:
    a = tempo_candidate_config_fingerprint(_baseline_id())
    b = tempo_candidate_config_fingerprint(_baseline_id())
    assert a == b
    assert len(a) == 64
    assert a != tempo_candidate_config_fingerprint(_current_id())
