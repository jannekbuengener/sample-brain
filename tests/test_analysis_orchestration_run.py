"""Contract tests for sample-brain.analysis-orchestration-run.v1 (#1060 W0/W1)."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from src.analysis_automation_decision import validate_decision
from src.analysis_eval_artifact import fingerprint, validate_artifact
from src.analysis_headless_run import (
    STATIC_ADAPTER_REGISTRY,
    build_request,
    build_result,
    validate_result,
)
from src.analysis_orchestration_run import (
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    AnalysisOrchestrationRunError,
    map_decision_inputs,
    map_eval_partition_role,
    outcome_semantic_fingerprint,
    project_analysis_eval_from_headless,
    run_orchestration,
    validate_outcome,
)
from src.aq_headless_adapters.aq1_tempo_compare import (
    ADAPTER_ID as AQ1_ADAPTER_ID,
    DOMAIN as AQ1_DOMAIN,
    tempo_candidate_config_fingerprint,
)
from src.fsld_aq1_tempo_candidate_compare import TEMPO_CANDIDATES
from src.fsld_human_manifest import canonical_manifest_bytes

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
OPAQUE_EVIDENCE_FP = "a" * 64


def _baseline_id() -> str:
    return TEMPO_CANDIDATES[0].candidate_id


def _current_id() -> str:
    return TEMPO_CANDIDATES[1].candidate_id


def _synthetic_completed_headless() -> tuple[dict[str, Any], dict[str, Any]]:
    baseline_id = _baseline_id()
    current_id = _current_id()
    request = build_request(
        domain=AQ1_DOMAIN,
        adapter_id=AQ1_ADAPTER_ID,
        operation="compare",
        benchmark_id="orch-synthetic-bench",
        dataset_id="orch-synthetic-dataset",
        dataset_content_fingerprint="b" * 64,
        partition_id="orch-cal-1",
        partition_role="calibration",
        baseline_candidate_id=baseline_id,
        baseline_config_fingerprint=tempo_candidate_config_fingerprint(baseline_id),
        current_candidate_id=current_id,
        current_config_fingerprint=tempo_candidate_config_fingerprint(current_id),
        evidence_intent="domain_artifact",
    )
    result = build_result(
        run_status="completed",
        adapter_id=AQ1_ADAPTER_ID,
        adapter_version="1.0.0",
        request_fingerprint=request["request_fingerprint"],
        domain=AQ1_DOMAIN,
        operation="compare",
        partition_id="orch-cal-1",
        partition_role="calibration",
        benchmark_id="orch-synthetic-bench",
        dataset_id="orch-synthetic-dataset",
        dataset_content_fingerprint="b" * 64,
        baseline_candidate_id=baseline_id,
        baseline_config_fingerprint=tempo_candidate_config_fingerprint(baseline_id),
        current_candidate_id=current_id,
        current_config_fingerprint=tempo_candidate_config_fingerprint(current_id),
        domain_artifact_id="sample-brain.aq1.tempo.candidate_compare",
        domain_artifact_fingerprint="c" * 64,
    )
    return request, validate_result(result)


def test_document_identity_frozen() -> None:
    assert DOCUMENT_TYPE == "sample-brain.analysis-orchestration-run.v1"
    assert ARTIFACT_VERSION == "1.0.0"


def test_no_arvp_import_in_orchestration_module() -> None:
    tree = ast.parse((SRC_ROOT / "analysis_orchestration_run.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("arvp")
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("arvp")


def test_map_eval_partition_role_holdout_to_test() -> None:
    assert map_eval_partition_role("holdout") == "test"
    assert map_eval_partition_role("calibration") == "calibration"
    with pytest.raises(AnalysisOrchestrationRunError, match="unsupported partition"):
        map_eval_partition_role("not-a-role")


def test_map_decision_inputs_headless_hold_and_cf() -> None:
    status, token, action = map_decision_inputs(
        run_status="hold", gate_verdict=None, partition_role="calibration"
    )
    assert status == "hold"
    assert token is None
    assert action == "defer_for_evidence"

    status, token, action = map_decision_inputs(
        run_status="controlled_failure",
        gate_verdict=None,
        partition_role="calibration",
    )
    assert status == "controlled_failure"
    assert token is None
    assert action == "stop_controlled_failure"


def test_map_decision_inputs_completed_gate_paths() -> None:
    status, token, action = map_decision_inputs(
        run_status="completed", gate_verdict="HOLD", partition_role="calibration"
    )
    assert (status, token, action) == ("hold", None, "defer_for_evidence")

    status, token, action = map_decision_inputs(
        run_status="completed", gate_verdict="PASS", partition_role="calibration"
    )
    assert status == "ready"
    assert token == "KEEP_CURRENT_BASELINE_PATH"
    assert action == "keep_baseline_and_stop"

    status, token, action = map_decision_inputs(
        run_status="completed", gate_verdict="FAIL", partition_role="calibration"
    )
    assert status == "ready"
    assert token == "NO_JUSTIFIED_CANDIDATE"


def test_map_decision_inputs_test_partition_forbids_tuning() -> None:
    with pytest.raises(AnalysisOrchestrationRunError, match="partition firewall"):
        map_decision_inputs(
            run_status="completed",
            gate_verdict="PASS",
            partition_role="test",
            decision_token="NO_JUSTIFIED_CANDIDATE",
            next_action="continue_calibration",
        )


def test_project_analysis_eval_from_completed_headless_is_portable() -> None:
    request, result = _synthetic_completed_headless()
    artifact = project_analysis_eval_from_headless(
        request=request, headless_result=result
    )
    validated = validate_artifact(artifact)
    assert validated["document_type"] == "sample-brain.analysis-eval.v1"
    assert validated["partition"]["role"] == "calibration"
    fp1 = fingerprint(validated)
    fp2 = fingerprint(
        project_analysis_eval_from_headless(request=request, headless_result=result)
    )
    assert fp1 == fp2
    assert len(fp1) == 64


def test_project_rejects_absolute_path_payload_via_host_artifact() -> None:
    request, result = _synthetic_completed_headless()
    artifact = project_analysis_eval_from_headless(
        request=request, headless_result=result
    )
    # Inject a forbidden absolute path into a portable field and ensure validate fails.
    poisoned = dict(artifact)
    poisoned_records = [dict(artifact["records"][0])]
    poisoned_obs = [dict(poisoned_records[0]["observations"][0])]
    payload = dict(poisoned_obs[0]["payload"] or {})
    payload["leak"] = "C:/Users/private/sample.wav"
    poisoned_obs[0]["payload"] = payload
    poisoned_records[0]["observations"] = poisoned_obs
    poisoned["records"] = poisoned_records
    with pytest.raises(Exception, match="absolute/private path|path is forbidden"):
        validate_artifact(poisoned)


def test_unknown_adapter_fail_closed(tmp_path: Path) -> None:
    request, _ = _synthetic_completed_headless()
    bad = dict(request)
    bad["adapter_id"] = "aq99.does.not.exist"
    bad.pop("request_fingerprint", None)
    with pytest.raises(Exception):
        # rebuild fingerprint via validate_request path inside run_orchestration
        from src.analysis_headless_run import validate_request

        validated = validate_request(bad)
        run_orchestration(
            request=validated,
            bind_kwargs={"work_dir": tmp_path},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )


# ---------------------------------------------------------------------------
# W1 — real AQ1 Path B proof helpers / cases
# ---------------------------------------------------------------------------


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


def _aq1_path_b_request(
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
            "dataset_id": "aq1-orch-path-b",
            "members": sorted(r["public_sample_id"] for r in records),
            "manifest_relpath": manifest_rel,
            "baseline_predictions_relpath": baseline_rel,
        }
    )
    return build_request(
        domain=AQ1_DOMAIN,
        adapter_id=AQ1_ADAPTER_ID,
        operation=operation,
        benchmark_id="aq1-tempo-orch-bench-v1",
        dataset_id="aq1-orch-path-b",
        dataset_content_fingerprint=dataset_fp,
        partition_id="aq1-orch-cal",
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
                "output_relpath": "out/aq1-orch-compare.json",
                "manifest_relpath": manifest_rel,
                "sha256_relpath": sha_rel,
                "split": split,
            }
        },
    )


def test_aq1_calibration_orchestration_e2e_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "aq1-orch-work"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    request = _aq1_path_b_request(work)
    outcome_a = run_orchestration(
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    outcome_b = run_orchestration(
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )

    validated = validate_outcome(outcome_a)
    assert validated["document_type"] == DOCUMENT_TYPE
    assert validated["production_authorized"] is False
    assert validated["headless_result"]["run_status"] == "completed"
    assert validated["headless_result"]["adapter_id"] == AQ1_ADAPTER_ID
    assert "decision_token" not in validated["headless_result"]
    assert "next_action" not in validated["headless_result"]

    eval_fp = validated["analysis_eval"]["artifact_fingerprint"]
    assert len(eval_fp) == 64
    assert (
        validated["decision"]["evidence"]["analysis_eval_fingerprint"] == eval_fp
    )
    decision = validate_decision(validated["decision"])
    assert decision["decision_status"] == "ready"
    assert decision["decision_token"] == "KEEP_CURRENT_BASELINE_PATH"
    assert decision["next_action"] == "keep_baseline_and_stop"
    assert decision["production_authorized"] is False
    assert decision["evidence"]["gate_decision"]["verdict"] == "PASS"
    assert decision["evidence"]["evidence_fingerprint"] == OPAQUE_EVIDENCE_FP

    assert outcome_a["outcome_fingerprint"] == outcome_b["outcome_fingerprint"]
    assert outcome_semantic_fingerprint(outcome_a) == outcome_a["outcome_fingerprint"]


def test_aq1_completed_gate_hold_maps_to_decision_hold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "aq1-orch-hold"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    request = _aq1_path_b_request(work)
    outcome = run_orchestration(
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="HOLD",
    )
    assert outcome["decision"]["decision_status"] == "hold"
    assert "decision_token" not in outcome["decision"]
    assert outcome["decision"]["next_action"] == "defer_for_evidence"


def test_unknown_operation_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "aq1-orch-bad-op"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    request = _aq1_path_b_request(work)
    bad = dict(request)
    bad["operation"] = "tune_on_holdout"
    bad.pop("request_fingerprint", None)
    with pytest.raises(Exception):
        from src.analysis_headless_run import validate_request

        run_orchestration(
            request=validate_request(bad),
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )


def test_test_partition_exploratory_compare_fail_closed(tmp_path: Path) -> None:
    work = tmp_path / "aq1-orch-test"
    work.mkdir()
    with pytest.raises(Exception, match="partition|exploratory|tuning|non-tuning"):
        _aq1_path_b_request(work, partition_role="test", split="TEST")


def test_aq6_registry_still_present() -> None:
    assert "aq6.ranking.candidate_compare" in STATIC_ADAPTER_REGISTRY
    assert AQ1_ADAPTER_ID in STATIC_ADAPTER_REGISTRY


def test_controlled_failure_path_no_ready_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "aq1-orch-cf"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    request = _aq1_path_b_request(work)
    tampered = dict(request)
    baseline = dict(request["baseline"])
    baseline["config_fingerprint"] = "0" * 64
    tampered["baseline"] = baseline
    tampered.pop("request_fingerprint", None)
    from src.analysis_headless_run import validate_request

    outcome = run_orchestration(
        request=validate_request(tampered),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    assert outcome["headless_result"]["run_status"] == "controlled_failure"
    assert outcome["decision"]["decision_status"] == "controlled_failure"
    assert "decision_token" not in outcome["decision"]
    assert outcome["decision"]["next_action"] == "stop_controlled_failure"
    assert outcome["production_authorized"] is False


def test_non_finite_rejected_in_projected_eval() -> None:
    request, result = _synthetic_completed_headless()
    artifact = project_analysis_eval_from_headless(
        request=request, headless_result=result
    )
    poisoned = dict(artifact)
    records = [dict(artifact["records"][0])]
    obs = [dict(records[0]["observations"][0])]
    obs[0]["value"] = float("nan")
    records[0]["observations"] = obs
    poisoned["records"] = records
    with pytest.raises(Exception, match="non-finite|finite"):
        validate_artifact(poisoned)


def test_completed_without_valid_portable_eval_never_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing/invalid host-supplied eval must fail closed (no fabricated ready)."""
    work = tmp_path / "aq1-orch-missing-eval"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    request = _aq1_path_b_request(work)
    with pytest.raises(AnalysisOrchestrationRunError):
        run_orchestration(
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            analysis_eval_artifact={
                "document_type": "sample-brain.analysis-eval.v1",
                "not": "a valid artifact",
            },
        )


def test_holdout_partition_forbids_tuning_next_action() -> None:
    with pytest.raises(AnalysisOrchestrationRunError, match="partition firewall"):
        map_decision_inputs(
            run_status="completed",
            gate_verdict="PASS",
            partition_role="holdout",
            decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
            next_action="freeze_candidate",
        )


def test_host_eval_from_different_benchmark_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.analysis_eval_artifact import aq1_tempo_fixture

    work = tmp_path / "aq1-orch-cross-eval"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    request = _aq1_path_b_request(work)
    foreign = aq1_tempo_fixture()
    with pytest.raises(AnalysisOrchestrationRunError, match="identity mismatch"):
        run_orchestration(
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            analysis_eval_artifact=foreign,
        )


def test_non_completed_forces_hold_gate_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "aq1-orch-cf-gate"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    request = _aq1_path_b_request(work)
    tampered = dict(request)
    baseline = dict(request["baseline"])
    baseline["config_fingerprint"] = "0" * 64
    tampered["baseline"] = baseline
    tampered.pop("request_fingerprint", None)
    from src.analysis_headless_run import validate_request

    outcome = run_orchestration(
        request=validate_request(tampered),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",  # must be discarded for non-completed
    )
    assert outcome["headless_result"]["run_status"] == "controlled_failure"
    assert outcome["decision"]["evidence"]["gate_decision"]["verdict"] == "HOLD"
    assert outcome["decision"]["decision_status"] == "controlled_failure"


def test_aq1_hold_path_when_no_predictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adapter hold (empty predictions) maps to decision hold, never ready."""
    work = tmp_path / "aq1-orch-empty"
    work.mkdir()
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir()
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )
    records = [
        _record("10", split="CALIBRATION", bpm=120.0),
        _record("11", split="CALIBRATION", bpm=120.0),
    ]
    manifest_rel, sha_rel = _write_manifest(work, records)
    # Predictions with missing BPM → adapter may hold or CF depending on runner.
    baseline_rel = _write_baseline_predictions(
        work,
        records=records,
        predicted=[("10", None, "missing"), ("11", None, "missing")],
        split="CALIBRATION",
    )
    dataset_fp = fingerprint(
        {
            "dataset_id": "aq1-orch-empty",
            "members": ["10", "11"],
            "manifest_relpath": manifest_rel,
            "baseline_predictions_relpath": baseline_rel,
        }
    )
    request = build_request(
        domain=AQ1_DOMAIN,
        adapter_id=AQ1_ADAPTER_ID,
        operation="compare",
        benchmark_id="aq1-tempo-orch-empty",
        dataset_id="aq1-orch-empty",
        dataset_content_fingerprint=dataset_fp,
        partition_id="aq1-orch-empty",
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
                "output_relpath": "out/aq1-orch-empty.json",
                "manifest_relpath": manifest_rel,
                "sha256_relpath": sha_rel,
                "split": "CALIBRATION",
            }
        },
    )
    outcome = run_orchestration(
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    assert outcome["headless_result"]["run_status"] in {"hold", "controlled_failure"}
    assert outcome["decision"]["decision_status"] in {"hold", "controlled_failure"}
    assert "decision_token" not in outcome["decision"]
    assert outcome["production_authorized"] is False
    assert outcome["decision"]["evidence"]["gate_decision"]["verdict"] == "HOLD"


# ---------------------------------------------------------------------------
# #1063 — cross-envelope invocation identity binding (Codex repair)
# ---------------------------------------------------------------------------


class _StubDomainAdapter:
    """Host-bound adapter stub that returns a prebuilt headless result."""

    def __init__(
        self,
        *,
        result: Mapping[str, Any],
        adapter_id: str = AQ1_ADAPTER_ID,
        adapter_version: str = "1.0.0",
    ) -> None:
        self._result = dict(result)
        self._adapter_id = adapter_id
        self._adapter_version = adapter_version

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"baseline", "compare", "locked_evaluation"})

    def run(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        return dict(self._result)


def _stub_bind(monkeypatch: pytest.MonkeyPatch, adapter: _StubDomainAdapter) -> None:
    monkeypatch.setattr(
        "src.analysis_orchestration_run.bind_adapter",
        lambda adapter_id, **host_kwargs: adapter,
    )


def _completed_result_for_request(
    request: Mapping[str, Any],
    *,
    include_candidates: bool = True,
    request_fingerprint: str | None = None,
    adapter_id: str | None = None,
    adapter_version: str = "1.0.0",
    domain: str | None = None,
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "run_status": "completed",
        "adapter_id": adapter_id or str(request["adapter_id"]),
        "adapter_version": adapter_version,
        "request_fingerprint": request_fingerprint or str(request["request_fingerprint"]),
        "domain": domain or str(request["domain"]),
        "operation": str(request["operation"]),
        "partition_id": str(request["partition"]["partition_id"]),
        "partition_role": str(request["partition"]["role"]),
        "benchmark_id": str(request["benchmark"]["benchmark_id"]),
        "dataset_id": str(request["benchmark"]["dataset_id"]),
        "dataset_content_fingerprint": str(
            request["benchmark"]["dataset_content_fingerprint"]
        ),
        "domain_artifact_id": "sample-brain.aq1.tempo.candidate_compare",
        "domain_artifact_fingerprint": "c" * 64,
    }
    if include_candidates:
        kwargs["baseline_candidate_id"] = str(request["baseline"]["candidate_id"])
        kwargs["baseline_config_fingerprint"] = str(
            request["baseline"]["config_fingerprint"]
        )
        kwargs["current_candidate_id"] = str(request["current"]["candidate_id"])
        kwargs["current_config_fingerprint"] = str(
            request["current"]["config_fingerprint"]
        )
    return validate_result(build_result(**kwargs))


def _matching_eval_for_request(
    request: Mapping[str, Any],
    *,
    candidate_id: str | None = None,
    benchmark_id: str | None = None,
    dataset_id: str | None = None,
    partition_id: str | None = None,
    partition_role: str | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    from src.analysis_eval_artifact import (
        build_artifact,
        build_candidate,
        build_observation,
        build_record,
    )

    cand_id = candidate_id or str(request["current"]["candidate_id"])
    cfg_fp = str(request["current"]["config_fingerprint"])
    if candidate_id is not None:
        cfg_fp = "e" * 64
    candidate = build_candidate(
        candidate_id=cand_id,
        implementation_id=str(request["adapter_id"]),
        revision="1.0.0",
        configuration={
            "domain": domain or str(request["domain"]),
            "candidate_id": cand_id,
            "config_fingerprint": cfg_fp,
            "headless_run_status": "completed",
        },
    )
    record = build_record(
        record_id="orch.headless.primary",
        domain=domain or str(request["domain"]),
        eligibility={"status": "eligible"},
        ground_truth={},
        observations=[
            build_observation(
                observation_id="orch.headless.primary.domain_artifact.link",
                metric_id="orchestration.domain_artifact.link",
                status="measured",
                value=1.0,
                unit="count",
                direction="maximize",
                payload={
                    "domain_artifact_id": "sample-brain.aq1.tempo.candidate_compare",
                    "domain_artifact_fingerprint": "c" * 64,
                    "adapter_id": str(request["adapter_id"]),
                    "adapter_version": "1.0.0",
                    "headless_run_status": "completed",
                },
            )
        ],
    )
    return validate_artifact(
        build_artifact(
            benchmark_id=benchmark_id or str(request["benchmark"]["benchmark_id"]),
            dataset_id=dataset_id or str(request["benchmark"]["dataset_id"]),
            dataset_member_ids=["orch.headless.primary"],
            partition_id=partition_id or str(request["partition"]["partition_id"]),
            partition_role=partition_role
            or map_eval_partition_role(str(request["partition"]["role"])),
            candidate=candidate,
            source_benchmark_version=ARTIFACT_VERSION,
            run_id="orch-identity-probe",
            records=[record],
            source_origin="orchestration-binder",
        )
    )


def test_stale_request_fingerprint_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    request, _ = _synthetic_completed_headless()
    stale = _completed_result_for_request(
        request, request_fingerprint="d" * 64
    )
    _stub_bind(monkeypatch, _StubDomainAdapter(result=stale))
    with pytest.raises(AnalysisOrchestrationRunError, match="request_fingerprint"):
        run_orchestration(
            request=request,
            bind_kwargs={},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )


def test_wrong_adapter_id_on_result_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    request, _ = _synthetic_completed_headless()
    wrong = _completed_result_for_request(
        request,
        adapter_id="aq6.ranking.candidate_compare",
        domain="aq6.ranking",
    )
    _stub_bind(
        monkeypatch,
        _StubDomainAdapter(
            result=wrong,
            adapter_id=AQ1_ADAPTER_ID,
            adapter_version="1.0.0",
        ),
    )
    with pytest.raises(AnalysisOrchestrationRunError, match="adapter_id"):
        run_orchestration(
            request=request,
            bind_kwargs={},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )


def test_wrong_adapter_version_on_result_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _ = _synthetic_completed_headless()
    wrong = _completed_result_for_request(request, adapter_version="9.9.9")
    _stub_bind(
        monkeypatch,
        _StubDomainAdapter(
            result=wrong, adapter_id=AQ1_ADAPTER_ID, adapter_version="1.0.0"
        ),
    )
    with pytest.raises(AnalysisOrchestrationRunError, match="adapter_version"):
        run_orchestration(
            request=request,
            bind_kwargs={},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )


@pytest.mark.parametrize(
    "field,mutate",
    [
        ("benchmark", lambda r, e: _matching_eval_for_request(r, benchmark_id="OTHER_BENCH")),
        ("dataset", lambda r, e: _matching_eval_for_request(r, dataset_id="OTHER_DATASET")),
        ("partition", lambda r, e: _matching_eval_for_request(r, partition_id="OTHER_PART")),
        (
            "partition_role",
            lambda r, e: _matching_eval_for_request(r, partition_role="validation"),
        ),
        (
            "baseline_candidate",
            lambda r, e: _matching_eval_for_request(r, candidate_id="FOREIGN_BASELINE"),
        ),
        (
            "current_candidate",
            lambda r, e: _matching_eval_for_request(r, candidate_id="FOREIGN_CURRENT"),
        ),
    ],
)
@pytest.mark.parametrize("include_candidates", [True, False])
def test_supplied_eval_identity_mismatch_rejected(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    mutate,
    include_candidates: bool,
) -> None:
    request, _ = _synthetic_completed_headless()
    result = _completed_result_for_request(
        request, include_candidates=include_candidates
    )
    foreign_eval = mutate(request, None)
    _stub_bind(monkeypatch, _StubDomainAdapter(result=result))
    with pytest.raises(AnalysisOrchestrationRunError, match="identity mismatch|candidate"):
        run_orchestration(
            request=request,
            bind_kwargs={},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            analysis_eval_artifact=foreign_eval,
        )


@pytest.mark.parametrize("gate", ["PASS", "FAIL"])
@pytest.mark.parametrize("run_status", ["hold", "controlled_failure"])
def test_non_completed_supplied_pass_fail_cannot_survive(
    monkeypatch: pytest.MonkeyPatch, gate: str, run_status: str
) -> None:
    request, _ = _synthetic_completed_headless()
    result = validate_result(
        build_result(
            run_status=run_status,
            adapter_id=AQ1_ADAPTER_ID,
            adapter_version="1.0.0",
            request_fingerprint=request["request_fingerprint"],
            domain=AQ1_DOMAIN,
            operation="compare",
            partition_id=str(request["partition"]["partition_id"]),
            partition_role=str(request["partition"]["role"]),
            benchmark_id=str(request["benchmark"]["benchmark_id"]),
            dataset_id=str(request["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            baseline_candidate_id=str(request["baseline"]["candidate_id"]),
            baseline_config_fingerprint=str(request["baseline"]["config_fingerprint"]),
            current_candidate_id=str(request["current"]["candidate_id"]),
            current_config_fingerprint=str(request["current"]["config_fingerprint"]),
            error_code="probe.non_completed",
            error_detail=f"synthetic {run_status}",
        )
    )
    _stub_bind(monkeypatch, _StubDomainAdapter(result=result))
    outcome = run_orchestration(
        request=request,
        bind_kwargs={},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict=gate,
    )
    assert outcome["headless_result"]["run_status"] == run_status
    assert outcome["decision"]["decision_status"] == run_status
    assert outcome["decision"]["evidence"]["gate_decision"]["verdict"] == "HOLD"
    assert "decision_token" not in outcome["decision"]
    assert outcome["decision"]["decision_status"] != "ready"


@pytest.mark.parametrize(
    "field",
    [
        "domain",
        "benchmark",
        "dataset",
        "partition",
        "baseline_candidate",
        "current_candidate",
    ],
)
@pytest.mark.parametrize("include_candidates", [True, False])
def test_validate_outcome_rejects_tampered_decision_identity(
    field: str, include_candidates: bool
) -> None:
    from src.analysis_automation_decision import build_decision

    request, _ = _synthetic_completed_headless()
    result = _completed_result_for_request(
        request, include_candidates=include_candidates
    )
    # Seal path: outcome may carry request-fallback candidates even when the
    # raw adapter result omitted them; craft a portable outcome then tamper.
    if not include_candidates:
        sealed = dict(result)
        sealed["baseline"] = dict(request["baseline"])
        sealed["current"] = dict(request["current"])
        sealed.pop("result_fingerprint", None)
        result = validate_result(sealed)

    eval_fp = "f" * 64
    decision = build_decision(
        domain=AQ1_DOMAIN,
        benchmark_id=str(request["benchmark"]["benchmark_id"]),
        dataset_id=str(request["benchmark"]["dataset_id"]),
        dataset_content_fingerprint=str(
            request["benchmark"]["dataset_content_fingerprint"]
        ),
        partition_id=str(request["partition"]["partition_id"]),
        partition_role=str(request["partition"]["role"]),
        baseline_candidate_id=str(request["baseline"]["candidate_id"]),
        baseline_config_fingerprint=str(request["baseline"]["config_fingerprint"]),
        current_candidate_id=str(request["current"]["candidate_id"]),
        current_config_fingerprint=str(request["current"]["config_fingerprint"]),
        analysis_eval_fingerprint=eval_fp,
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        decision_status="ready",
        next_action="keep_baseline_and_stop",
        decision_token="KEEP_CURRENT_BASELINE_PATH",
        production_authorized=False,
    )

    if field == "domain":
        decision = build_decision(
            domain="aq99.other",
            benchmark_id=str(request["benchmark"]["benchmark_id"]),
            dataset_id=str(request["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            partition_id=str(request["partition"]["partition_id"]),
            partition_role=str(request["partition"]["role"]),
            baseline_candidate_id=str(request["baseline"]["candidate_id"]),
            baseline_config_fingerprint=str(request["baseline"]["config_fingerprint"]),
            current_candidate_id=str(request["current"]["candidate_id"]),
            current_config_fingerprint=str(request["current"]["config_fingerprint"]),
            analysis_eval_fingerprint=eval_fp,
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            decision_status="ready",
            next_action="keep_baseline_and_stop",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            production_authorized=False,
        )
    elif field == "benchmark":
        decision = build_decision(
            domain=AQ1_DOMAIN,
            benchmark_id="TAMPERED_BENCH",
            dataset_id=str(request["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            partition_id=str(request["partition"]["partition_id"]),
            partition_role=str(request["partition"]["role"]),
            baseline_candidate_id=str(request["baseline"]["candidate_id"]),
            baseline_config_fingerprint=str(request["baseline"]["config_fingerprint"]),
            current_candidate_id=str(request["current"]["candidate_id"]),
            current_config_fingerprint=str(request["current"]["config_fingerprint"]),
            analysis_eval_fingerprint=eval_fp,
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            decision_status="ready",
            next_action="keep_baseline_and_stop",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            production_authorized=False,
        )
    elif field == "dataset":
        decision = build_decision(
            domain=AQ1_DOMAIN,
            benchmark_id=str(request["benchmark"]["benchmark_id"]),
            dataset_id="TAMPERED_DATASET",
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            partition_id=str(request["partition"]["partition_id"]),
            partition_role=str(request["partition"]["role"]),
            baseline_candidate_id=str(request["baseline"]["candidate_id"]),
            baseline_config_fingerprint=str(request["baseline"]["config_fingerprint"]),
            current_candidate_id=str(request["current"]["candidate_id"]),
            current_config_fingerprint=str(request["current"]["config_fingerprint"]),
            analysis_eval_fingerprint=eval_fp,
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            decision_status="ready",
            next_action="keep_baseline_and_stop",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            production_authorized=False,
        )
    elif field == "partition":
        decision = build_decision(
            domain=AQ1_DOMAIN,
            benchmark_id=str(request["benchmark"]["benchmark_id"]),
            dataset_id=str(request["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            partition_id="TAMPERED_PART",
            partition_role=str(request["partition"]["role"]),
            baseline_candidate_id=str(request["baseline"]["candidate_id"]),
            baseline_config_fingerprint=str(request["baseline"]["config_fingerprint"]),
            current_candidate_id=str(request["current"]["candidate_id"]),
            current_config_fingerprint=str(request["current"]["config_fingerprint"]),
            analysis_eval_fingerprint=eval_fp,
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            decision_status="ready",
            next_action="keep_baseline_and_stop",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            production_authorized=False,
        )
    elif field == "baseline_candidate":
        decision = build_decision(
            domain=AQ1_DOMAIN,
            benchmark_id=str(request["benchmark"]["benchmark_id"]),
            dataset_id=str(request["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            partition_id=str(request["partition"]["partition_id"]),
            partition_role=str(request["partition"]["role"]),
            baseline_candidate_id="TAMPERED_BASE",
            baseline_config_fingerprint="1" * 64,
            current_candidate_id=str(request["current"]["candidate_id"]),
            current_config_fingerprint=str(request["current"]["config_fingerprint"]),
            analysis_eval_fingerprint=eval_fp,
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            decision_status="ready",
            next_action="keep_baseline_and_stop",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            production_authorized=False,
        )
    elif field == "current_candidate":
        decision = build_decision(
            domain=AQ1_DOMAIN,
            benchmark_id=str(request["benchmark"]["benchmark_id"]),
            dataset_id=str(request["benchmark"]["dataset_id"]),
            dataset_content_fingerprint=str(
                request["benchmark"]["dataset_content_fingerprint"]
            ),
            partition_id=str(request["partition"]["partition_id"]),
            partition_role=str(request["partition"]["role"]),
            baseline_candidate_id=str(request["baseline"]["candidate_id"]),
            baseline_config_fingerprint=str(request["baseline"]["config_fingerprint"]),
            current_candidate_id="TAMPERED_CUR",
            current_config_fingerprint="2" * 64,
            analysis_eval_fingerprint=eval_fp,
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            decision_status="ready",
            next_action="keep_baseline_and_stop",
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            production_authorized=False,
        )

    # Raw omitted-candidate shape: attacker strips candidates then swaps decision.
    if not include_candidates:
        stripped = dict(result)
        stripped.pop("baseline", None)
        stripped.pop("current", None)
        stripped.pop("result_fingerprint", None)
        result = validate_result(stripped)

    outcome = {
        "document_type": DOCUMENT_TYPE,
        "artifact_version": ARTIFACT_VERSION,
        "producer_id": "sample-brain.analysis-orchestration-run",
        "adapter_id": AQ1_ADAPTER_ID,
        "headless_result": result,
        "analysis_eval": {
            "document_type": "sample-brain.analysis-eval.v1",
            "artifact_fingerprint": eval_fp,
        },
        "decision": decision,
        "production_authorized": False,
    }
    outcome["outcome_fingerprint"] = outcome_semantic_fingerprint(outcome)
    with pytest.raises(
        AnalysisOrchestrationRunError,
        match="identity mismatch|candidate",
    ):
        validate_outcome(outcome)


def test_eval_with_matching_identities_accepted_when_result_omits_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, _ = _synthetic_completed_headless()
    result = _completed_result_for_request(request, include_candidates=False)
    matching = _matching_eval_for_request(request)
    _stub_bind(monkeypatch, _StubDomainAdapter(result=result))
    outcome = run_orchestration(
        request=request,
        bind_kwargs={},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        analysis_eval_artifact=matching,
    )
    assert outcome["decision"]["decision_status"] == "ready"
    assert "baseline" in outcome["headless_result"]
    assert "current" in outcome["headless_result"]
    assert outcome["headless_result"]["baseline"]["candidate_id"] == request[
        "baseline"
    ]["candidate_id"]
