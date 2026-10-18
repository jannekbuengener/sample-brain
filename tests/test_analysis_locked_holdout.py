"""Frozen proof tests for sample-brain.analysis-locked-holdout-transition.v1 (#1170).

TEST_GATE / TEST_FREEZE: these cases define the acceptance surface before
implementation. Imports target the planned public API that intentionally does
not exist yet at the RED gate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import build_request
from src.aq_candidate_search_spaces.aq1_tempo import Aq1TempoSearchSpaceProvider
from src.aq_headless_adapters.aq1_tempo_compare import (
    ADAPTER_ID as AQ1_ADAPTER_ID,
    DOMAIN as AQ1_DOMAIN,
    tempo_candidate_config_fingerprint,
)
from src.fsld_aq1_tempo_candidate_compare import TEMPO_CANDIDATES
from src.fsld_human_manifest import canonical_manifest_bytes
from src.analysis_quality_loop_state import (
    AnalysisQualityLoopStateError,
    fresh_state,
    load_state,
    save_state_atomic,
    validate_locked_evaluation_ref,
    validate_state,
)
from src.analysis_quality_loop_supervisor import run_supervisor_step

# Planned public API (#1170) — controlled RED until implementation lands.
from src.analysis_locked_holdout import (  # noqa: F401
    AnalysisLockedHoldoutError,
    build_locked_evaluation_ref,
    run_locked_holdout_transition,
)

OPAQUE_EVIDENCE_FP = "b" * 64


def _candidate_id(index: int) -> str:
    return TEMPO_CANDIDATES[index].candidate_id


def _record(
    sample_id: str,
    *,
    split: str = "TEST",
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
    split: str = "TEST",
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


def _locked_request(
    work_dir: Path,
    *,
    operation: str = "locked_evaluation",
    partition_role: str = "test",
    split: str = "TEST",
    current_candidate_id: str | None = None,
    output_relpath: str = "out/aq1-locked.json",
    baseline_relpath: str | None = None,
) -> dict[str, Any]:
    records = [
        _record("20", split=split, bpm=120.0),
        _record("21", split=split, bpm=120.0),
    ]
    manifest_rel, sha_rel = _write_manifest(work_dir, records)
    baseline_rel = _write_baseline_predictions(
        work_dir,
        records=records,
        predicted=[("20", 60.0, "ok"), ("21", 120.0, "ok")],
        split=split,
    )
    dataset_fp = fingerprint(
        {
            "dataset_id": "aq1-locked-path-b",
            "members": sorted(r["public_sample_id"] for r in records),
            "manifest_relpath": manifest_rel,
            "baseline_predictions_relpath": baseline_relpath or baseline_rel,
        }
    )
    baseline_id = _candidate_id(0)
    current_id = current_candidate_id or baseline_id
    return build_request(
        domain=AQ1_DOMAIN,
        adapter_id=AQ1_ADAPTER_ID,
        operation=operation,
        benchmark_id="aq1-tempo-locked-bench-v1",
        dataset_id="aq1-locked-path-b",
        dataset_content_fingerprint=dataset_fp,
        partition_id=f"aq1-locked-{partition_role}",
        partition_role=partition_role,
        baseline_candidate_id=baseline_id,
        baseline_config_fingerprint=tempo_candidate_config_fingerprint(baseline_id),
        current_candidate_id=current_id,
        current_config_fingerprint=tempo_candidate_config_fingerprint(current_id),
        evidence_intent="domain_artifact",
        extra_fields={
            "aq1_inputs": {
                "raw_source": "baseline_predictions",
                "baseline_predictions_relpath": baseline_relpath or baseline_rel,
                "output_relpath": output_relpath,
                "manifest_relpath": manifest_rel,
                "sha256_relpath": sha_rel,
                "split": split,
            }
        },
    )


def _patch_aq1_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake_repo = tmp_path / "fake-repo"
    fake_repo.mkdir(exist_ok=True)
    monkeypatch.setattr(
        "src.fsld_aq1_tempo_candidate_compare.REPOSITORY_ROOT", fake_repo
    )


def _fresh_frozen_state(
    *, active_index: int = 0, visited_ids: list[str] | None = None
) -> dict[str, Any]:
    """Frozen supervisor state with active candidate at `active_index`."""
    provider = Aq1TempoSearchSpaceProvider()
    active_id = _candidate_id(active_index)
    active = {
        "candidate_id": active_id,
        "config_fingerprint": tempo_candidate_config_fingerprint(active_id),
    }
    baseline_id = _candidate_id(0)
    baseline = {
        "candidate_id": baseline_id,
        "config_fingerprint": tempo_candidate_config_fingerprint(baseline_id),
    }
    if visited_ids is None:
        visited = [
            _candidate_id(i) for i in range(active_index + 1)
        ]
    else:
        visited = list(visited_ids)
    state = fresh_state(
        domain=AQ1_DOMAIN,
        partition_id="aq1-locked-cal",
        partition_role="calibration",
        baseline_candidate=baseline,
        active_candidate=dict(active),
        search_space_id=provider.search_space_id,
        search_space_version=provider.search_space_version,
        search_space_fingerprint=provider.search_space_fingerprint(),
        visited_candidate_ids=visited,
        retry_budget=3,
    )
    # Freeze: CALIBRATION produced the frozen tip; loop_status is terminal.
    state["loop_status"] = "frozen"
    state.pop("state_fingerprint", None)
    return validate_state(state)


def _state_path(tmp_path: Path) -> Path:
    return tmp_path / "supervisor" / "quality-loop-state.json"


def _transition(tmp_path: Path, work_dir: Path, **kwargs: Any) -> dict[str, Any]:
    return run_locked_holdout_transition(
        state_path=_state_path(tmp_path),
        request=kwargs.pop("request"),
        bind_kwargs={"work_dir": work_dir},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# 1 — frozen state transitions to exactly one locked evaluation
# ---------------------------------------------------------------------------


def test_01_frozen_state_transitions_to_one_locked_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-locked-work"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    frozen = _fresh_frozen_state(active_index=1)
    save_state_atomic(state_path, frozen)

    request = _locked_request(work, current_candidate_id=_candidate_id(1))
    result = run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )

    assert result["production_authorized"] is False
    assert result["already_committed"] is False
    locked = result["locked_evaluation"]
    assert locked["candidate"]["candidate_id"] == _candidate_id(1)
    assert locked["candidate"]["config_fingerprint"] == frozen["active_candidate"][
        "config_fingerprint"
    ]
    assert locked["baseline_candidate"]["candidate_id"] == _candidate_id(0)
    assert locked["partition"]["role"] == "test"
    assert locked["terminal_status"] == "completed"
    assert locked["production_authorized"] is False
    decision = result["decision"]
    assert decision["decision_status"] == "ready"
    assert decision["next_action"] == "keep_baseline_and_stop"

    loaded = load_state(state_path)
    assert loaded["loop_status"] == "frozen"
    assert loaded["generation"] == frozen["generation"] + 1
    assert loaded["locked_evaluation"]["outcome_fingerprint"] == locked[
        "outcome_fingerprint"
    ]
    validate_locked_evaluation_ref(loaded["locked_evaluation"])
    # Frozen identities remain traceable end-to-end.
    assert loaded["active_candidate"] == frozen["active_candidate"]
    assert loaded["baseline_candidate"] == frozen["baseline_candidate"]


# ---------------------------------------------------------------------------
# 2 — non-frozen states fail closed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["ready", "held", "stopped", "exhausted"])
def test_02_non_frozen_states_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, status: str
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / f"aq1-nonfrozen-{status}"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    state = _fresh_frozen_state()
    state["loop_status"] = status
    state.pop("state_fingerprint", None)
    save_state_atomic(state_path, state)

    request = _locked_request(work)
    with pytest.raises(AnalysisLockedHoldoutError, match="frozen"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
    # No locked evaluation was committed.
    loaded = load_state(state_path)
    assert loaded.get("locked_evaluation") is None
    # Domain execution never happened.
    assert not (work / "out" / "aq1-locked.json").exists()


# ---------------------------------------------------------------------------
# 3 — frozen candidate identity mismatch fails closed before domain execution
# ---------------------------------------------------------------------------


def test_03_candidate_identity_mismatch_fails_closed_before_domain_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-cand-mismatch"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    frozen = _fresh_frozen_state(active_index=1)
    save_state_atomic(state_path, frozen)

    # Request claims a different (not-frozen) candidate.
    request = _locked_request(work, current_candidate_id=_candidate_id(2))
    with pytest.raises(AnalysisLockedHoldoutError, match="active_candidate"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
    loaded = load_state(state_path)
    assert loaded.get("locked_evaluation") is None
    assert not (work / "out" / "aq1-locked.json").exists()


# ---------------------------------------------------------------------------
# 4 — baseline identity mismatch fails closed
# ---------------------------------------------------------------------------


def test_04_baseline_identity_mismatch_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-baseline-mismatch"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    frozen = _fresh_frozen_state()
    # Freeze against a different baseline than the request declares.
    other_baseline = {
        "candidate_id": _candidate_id(1),
        "config_fingerprint": tempo_candidate_config_fingerprint(_candidate_id(1)),
    }
    mutated = dict(frozen)
    mutated["baseline_candidate"] = other_baseline
    mutated.pop("state_fingerprint", None)
    save_state_atomic(state_path, mutated)

    request = _locked_request(work)
    with pytest.raises(AnalysisLockedHoldoutError, match="baseline_candidate"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
    assert load_state(state_path).get("locked_evaluation") is None


# ---------------------------------------------------------------------------
# 5 — only operation=locked_evaluation may enter the transition
# ---------------------------------------------------------------------------


def test_05_exploratory_operation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-wrong-op"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    # Valid #1054 request (compare on tunable role is buildable), but the
    # locked transition must refuse any non-locked_evaluation operation.
    request = _locked_request(
        work, operation="compare", partition_role="calibration", split="CALIBRATION"
    )
    with pytest.raises(AnalysisLockedHoldoutError, match="locked_evaluation"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
    assert load_state(state_path).get("locked_evaluation") is None


# ---------------------------------------------------------------------------
# 6 — locked evaluation uses test/holdout, never CALIBRATION
# ---------------------------------------------------------------------------


def test_06_calibration_role_fails_closed_holdout_role_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)

    work_cal = tmp_path / "aq1-locked-cal-role"
    work_cal.mkdir()
    save_state_atomic(state_path, _fresh_frozen_state())
    request = _locked_request(work_cal, partition_role="calibration", split="CALIBRATION")
    with pytest.raises(AnalysisLockedHoldoutError, match="test.*holdout|holdout.*test"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work_cal},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
    assert load_state(state_path).get("locked_evaluation") is None
    assert not (work_cal / "out" / "aq1-locked.json").exists()

    # holdout role maps onto the TEST split and is accepted.
    work_hold = tmp_path / "aq1-locked-holdout-role"
    work_hold.mkdir()
    state = _fresh_frozen_state()
    state.pop("state_fingerprint", None)
    save_state_atomic(state_path, state)
    request = _locked_request(
        work_hold, partition_role="holdout", split="TEST"
    )
    result = run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work_hold},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    assert result["locked_evaluation"]["partition"]["role"] == "holdout"


# ---------------------------------------------------------------------------
# 7 — TEST/HOLDOUT cannot emit tuning actions
# ---------------------------------------------------------------------------


def test_07_test_partition_cannot_emit_tuning_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-tuning-leak"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    request = _locked_request(work)
    with pytest.raises(
        (
            AnalysisLockedHoldoutError,
            AnalysisQualityLoopStateError,
        )
    ):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            next_action="continue_calibration",
        )
    loaded = load_state(state_path)
    assert loaded.get("locked_evaluation") is None


# ---------------------------------------------------------------------------
# 8 — deterministic locked evaluation refs across independent runs
# ---------------------------------------------------------------------------


def test_08_locked_refs_deterministic_across_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    refs = []
    for index in (0, 1):
        root = tmp_path / f"run-{index}"
        work = root / "work"
        work.mkdir(parents=True)
        state_path = root / "state.json"
        save_state_atomic(state_path, _fresh_frozen_state(active_index=1))
        request = _locked_request(work, current_candidate_id=_candidate_id(1))
        result = run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
        refs.append(result["locked_evaluation"])
    assert refs[0] == refs[1]


# ---------------------------------------------------------------------------
# 9 — HOLD emits no ready token
# ---------------------------------------------------------------------------


def test_09_gate_hold_yields_hold_decision_without_ready_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-gate-hold"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    request = _locked_request(work)
    result = run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="HOLD",
    )
    decision = result["decision"]
    assert decision["decision_status"] == "hold"
    assert "decision_token" not in decision
    assert decision["next_action"] == "defer_for_evidence"
    assert result["locked_evaluation"]["terminal_status"] == "held"
    loaded = load_state(state_path)
    assert loaded["loop_status"] == "frozen"
    assert loaded["locked_evaluation"]["terminal_status"] == "held"


# ---------------------------------------------------------------------------
# 10 — controlled failure stops fail-closed
# ---------------------------------------------------------------------------


def test_10_controlled_failure_stops_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-controlled-failure"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    # Fully valid request whose adapter input file is missing: the AQ1 adapter
    # maps the runner failure into a typed controlled-failure headless result.
    request = _locked_request(work, baseline_relpath="missing/baseline.json")
    result = run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    decision = result["decision"]
    assert decision["decision_status"] == "controlled_failure"
    assert decision["next_action"] == "stop_controlled_failure"
    assert result["locked_evaluation"]["terminal_status"] == "controlled_failure"
    loaded = load_state(state_path)
    assert loaded["loop_status"] == "frozen"
    assert loaded["locked_evaluation"]["terminal_status"] == "controlled_failure"
    assert loaded["production_authorized"] is False


# ---------------------------------------------------------------------------
# 11 — promotion-candidate output keeps production_authorized false
# ---------------------------------------------------------------------------


def test_11_promotion_candidate_output_stays_unauthorized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-promo-cand"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    request = _locked_request(work)
    result = run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
        next_action="keep_baseline_and_stop",
    )
    decision = result["decision"]
    assert decision["decision_status"] == "ready"
    assert decision["decision_token"] == "PROMOTION_CANDIDATE_IDENTIFIED"
    assert decision["next_action"] == "keep_baseline_and_stop"
    assert decision["production_authorized"] is False
    assert result["production_authorized"] is False
    loaded = load_state(state_path)
    assert loaded["production_authorized"] is False
    assert loaded["locked_evaluation"]["production_authorized"] is False
    assert loaded["locked_evaluation"]["decision"]["decision_token"] == (
        "PROMOTION_CANDIDATE_IDENTIFIED"
    )


# ---------------------------------------------------------------------------
# 12 — duplicate replay is idempotent and does not rerun orchestration
# ---------------------------------------------------------------------------


def test_12_replay_is_idempotent_no_rerun(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-replay"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    request = _locked_request(work)
    first = run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    committed = state_path.read_bytes()

    # Orchestration must not be called again on replay.
    def _explode(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise AssertionError("orchestration must not rerun on replay")

    monkeypatch.setattr(
        "src.analysis_locked_holdout.run_orchestration", _explode
    )
    replay = run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    assert replay["already_committed"] is True
    assert replay["locked_evaluation"] == first["locked_evaluation"]
    assert state_path.read_bytes() == committed
    loaded = load_state(state_path)
    assert loaded["generation"] == first["state"]["generation"]


# ---------------------------------------------------------------------------
# 13 — replay with changed request fails closed
# ---------------------------------------------------------------------------


def test_13_replay_with_changed_request_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-replay-changed"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    request = _locked_request(work)
    run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    committed = state_path.read_bytes()

    # Different partition identity → different request fingerprint.
    changed = _locked_request(
        work, output_relpath="out/aq1-locked-alt.json"
    )
    with pytest.raises(AnalysisLockedHoldoutError, match="already committed"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=changed,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
    assert state_path.read_bytes() == committed


# ---------------------------------------------------------------------------
# 14 — replay with changed evidence/gate seam fails closed
# ---------------------------------------------------------------------------


def test_14_replay_with_changed_inputs_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-replay-seam"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    request = _locked_request(work)
    run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    committed = state_path.read_bytes()

    other_evidence = "c" * 64
    with pytest.raises(AnalysisLockedHoldoutError, match="already committed"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=other_evidence,
            gate_verdict="PASS",
        )
    with pytest.raises(AnalysisLockedHoldoutError, match="already committed"):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="FAIL",
        )
    assert state_path.read_bytes() == committed


# ---------------------------------------------------------------------------
# 15 — restart: frozen terminal state refuses CALIBRATION; replay stays intact
# ---------------------------------------------------------------------------


def test_15_restart_frozen_refuses_calibration_replay_intact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-restart"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state(active_index=1))

    request = _locked_request(work, current_candidate_id=_candidate_id(1))
    run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )

    # Simulate restart: only the persisted file remains authoritative.
    reloaded = load_state(state_path)
    assert reloaded["locked_evaluation"]["terminal_status"] == "completed"
    validate_state(reloaded)

    # #1097 frozen status still refuses CALIBRATION iteration.
    with pytest.raises(Exception, match="frozen"):
        run_supervisor_step(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            next_action="continue_calibration",
        )


# ---------------------------------------------------------------------------
# 16 — missing state file fails closed (no silent fresh loop)
# ---------------------------------------------------------------------------


def test_16_missing_state_file_fails_closed(tmp_path: Path) -> None:
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    work = tmp_path / "aq1-missing"
    work.mkdir()
    request = _locked_request(work)
    with pytest.raises(AnalysisLockedHoldoutError):
        run_locked_holdout_transition(
            state_path=state_path,
            request=request,
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )
    assert not state_path.exists()


# ---------------------------------------------------------------------------
# 17 — no post-freeze identity mutation path in persisted state
# ---------------------------------------------------------------------------


def test_17_no_post_freeze_identity_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-no-mutation"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    frozen = _fresh_frozen_state(active_index=1)
    save_state_atomic(state_path, frozen)

    request = _locked_request(work, current_candidate_id=_candidate_id(1))
    run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    loaded = load_state(state_path)
    for field in (
        "domain",
        "partition",
        "baseline_candidate",
        "active_candidate",
        "search_space_id",
        "search_space_version",
        "search_space_fingerprint",
        "visited_candidate_ids",
        "iteration_index",
        "max_iterations",
    ):
        assert loaded[field] == frozen[field]


# ---------------------------------------------------------------------------
# 18 — persisted state contains no forbidden/private paths
# ---------------------------------------------------------------------------


def test_18_persisted_state_has_no_forbidden_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-privacy"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_frozen_state())

    request = _locked_request(work)
    run_locked_holdout_transition(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )
    loaded = validate_state(load_state(state_path))
    raw = json.dumps(loaded)
    assert str(work) not in raw
    assert str(state_path) not in raw
    assert "C:\\\\" not in raw and "C:/" not in raw
    assert "work_dir" not in loaded
    assert ".wav" not in raw.lower()
    assert loaded["locked_evaluation"]["production_authorized"] is False


# ---------------------------------------------------------------------------
# 19 — backward compatibility: #1097 states without the extension stay valid
# ---------------------------------------------------------------------------


def test_19_state_extension_backward_compatible(tmp_path: Path) -> None:
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    state = _fresh_frozen_state()
    save_state_atomic(state_path, state)
    loaded = load_state(state_path)
    assert "locked_evaluation" not in loaded
    # Pre-S6 fingerprint semantics unchanged for extension-free states.
    assert loaded["state_fingerprint"] == state["state_fingerprint"]
