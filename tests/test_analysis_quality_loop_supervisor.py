"""Frozen proof tests for sample-brain.analysis-quality-loop-supervisor.v1 (#1097).

TEST_GATE / TEST_FREEZE: these 18 cases define the acceptance surface before
implementation. Imports target planned public APIs that intentionally do not
exist yet at the RED gate.
"""

from __future__ import annotations

import hashlib
import json
import os
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

# Planned public APIs (#1097) — controlled RED until Tasks 3/4 land.
from src.analysis_quality_loop_state import (  # noqa: F401
    ARTIFACT_VERSION,
    DOCUMENT_TYPE,
    SCHEMA_VERSION,
    AnalysisQualityLoopStateError,
    fresh_state,
    load_state,
    save_state_atomic,
    state_semantic_fingerprint,
    validate_state,
)
from src.analysis_quality_loop_supervisor import (  # noqa: F401
    AnalysisQualityLoopSupervisorError,
    run_supervisor_step,
)

OPAQUE_EVIDENCE_FP = "a" * 64
DEFAULT_RETRY_BUDGET = 3


def _baseline_id() -> str:
    return TEMPO_CANDIDATES[0].candidate_id


def _second_id() -> str:
    return TEMPO_CANDIDATES[1].candidate_id


def _third_id() -> str:
    return TEMPO_CANDIDATES[2].candidate_id


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
    current_candidate_id: str | None = None,
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
            "dataset_id": "aq1-supervisor-path-b",
            "members": sorted(r["public_sample_id"] for r in records),
            "manifest_relpath": manifest_rel,
            "baseline_predictions_relpath": baseline_rel,
        }
    )
    baseline_id = _baseline_id()
    current_id = current_candidate_id or baseline_id
    return build_request(
        domain=AQ1_DOMAIN,
        adapter_id=AQ1_ADAPTER_ID,
        operation=operation,
        benchmark_id="aq1-tempo-supervisor-bench-v1",
        dataset_id="aq1-supervisor-path-b",
        dataset_content_fingerprint=dataset_fp,
        partition_id="aq1-supervisor-cal",
        partition_role=partition_role,
        baseline_candidate_id=baseline_id,
        baseline_config_fingerprint=tempo_candidate_config_fingerprint(baseline_id),
        current_candidate_id=current_id,
        current_config_fingerprint=tempo_candidate_config_fingerprint(current_id),
        evidence_intent="domain_artifact",
        extra_fields={
            "aq1_inputs": {
                "raw_source": "baseline_predictions",
                "baseline_predictions_relpath": baseline_rel,
                "output_relpath": "out/aq1-supervisor-compare.json",
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


def _fresh_aq1_state(**overrides: Any) -> dict[str, Any]:
    provider = Aq1TempoSearchSpaceProvider()
    baseline_id = _baseline_id()
    baseline = {
        "candidate_id": baseline_id,
        "config_fingerprint": tempo_candidate_config_fingerprint(baseline_id),
    }
    kwargs: dict[str, Any] = {
        "domain": AQ1_DOMAIN,
        "partition_id": "aq1-supervisor-cal",
        "partition_role": "calibration",
        "baseline_candidate": baseline,
        "active_candidate": dict(baseline),
        "search_space_id": provider.search_space_id,
        "search_space_version": provider.search_space_version,
        "search_space_fingerprint": provider.search_space_fingerprint(),
        "visited_candidate_ids": [baseline_id],
        "retry_budget": DEFAULT_RETRY_BUDGET,
    }
    kwargs.update(overrides)
    return fresh_state(**kwargs)


def _state_path(tmp_path: Path) -> Path:
    # Host-supplied path outside any repo checkout semantics for tests.
    return tmp_path / "supervisor" / "quality-loop-state.json"


# ---------------------------------------------------------------------------
# 1 — fresh deterministic
# ---------------------------------------------------------------------------


def test_01_fresh_state_deterministic() -> None:
    assert DOCUMENT_TYPE == "sample-brain.analysis-quality-loop-supervisor.v1"
    assert ARTIFACT_VERSION == "1.0.0"
    assert SCHEMA_VERSION == 1

    a = _fresh_aq1_state()
    b = _fresh_aq1_state()
    va = validate_state(a)
    vb = validate_state(b)
    assert va["loop_status"] == "ready"
    assert va["production_authorized"] is False
    assert "running" not in va
    assert state_semantic_fingerprint(va) == state_semantic_fingerprint(vb)
    assert va["state_fingerprint"] == vb["state_fingerprint"]
    assert va["generation"] == 0
    assert va["retry"]["budget_remaining"] == DEFAULT_RETRY_BUDGET
    assert va["retry"]["budget_initial"] == DEFAULT_RETRY_BUDGET


# ---------------------------------------------------------------------------
# 2 — real AQ1 CALIBRATION orchestration through existing primitives
# ---------------------------------------------------------------------------


def test_02_real_aq1_calibration_orchestration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-work"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    request = _aq1_path_b_request(work)
    result = run_supervisor_step(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
    )

    assert result["production_authorized"] is False
    assert result["orchestration"]["outcome_fingerprint"]
    decision = result["decision"]
    assert decision["decision_status"] == "ready"
    assert decision["next_action"] == "keep_baseline_and_stop"
    loaded = load_state(state_path)
    assert loaded["loop_status"] == "stopped"
    assert loaded["last_orchestration_ref"]["outcome_fingerprint"] == result[
        "orchestration"
    ]["outcome_fingerprint"]


# ---------------------------------------------------------------------------
# 3 — continue_calibration → exactly one #1064 candidate
# ---------------------------------------------------------------------------


def test_03_continue_calibration_advances_exactly_one_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-continue"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    request = _aq1_path_b_request(work, current_candidate_id=_baseline_id())
    result = run_supervisor_step(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )

    assert result["decision"]["next_action"] == "continue_calibration"
    assert result["iterator"]["iterator_effect"] == "advance"
    assert result["iterator"]["next_candidate"]["candidate_id"] == _second_id()
    loaded = load_state(state_path)
    assert loaded["active_candidate"]["candidate_id"] == _second_id()
    assert loaded["visited_candidate_ids"] == [_baseline_id(), _second_id()]
    assert loaded["loop_status"] == "ready"
    assert loaded["generation"] == 1


# ---------------------------------------------------------------------------
# 4 — atomic commit
# ---------------------------------------------------------------------------


def test_04_atomic_commit_persists_valid_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-atomic"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    before = state_path.read_bytes()
    run_supervisor_step(
        state_path=state_path,
        request=_aq1_path_b_request(work),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    after = state_path.read_bytes()
    assert after != before
    # No leftover temp siblings from a non-atomic write path.
    leftovers = [
        p for p in state_path.parent.iterdir() if p.name != state_path.name
    ]
    assert leftovers == []
    validated = validate_state(load_state(state_path))
    assert validated["state_fingerprint"] == state_semantic_fingerprint(validated)


# ---------------------------------------------------------------------------
# 5 — restart resumes same committed state
# ---------------------------------------------------------------------------


def test_05_restart_resumes_same_committed_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-restart"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    run_supervisor_step(
        state_path=state_path,
        request=_aq1_path_b_request(work),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    committed = load_state(state_path)
    fp = committed["state_fingerprint"]
    generation = committed["generation"]
    active = committed["active_candidate"]["candidate_id"]

    # Simulate process restart: only the persisted file remains authoritative.
    reloaded = load_state(state_path)
    assert reloaded["state_fingerprint"] == fp
    assert reloaded["generation"] == generation
    assert reloaded["active_candidate"]["candidate_id"] == active
    assert reloaded["visited_candidate_ids"] == [_baseline_id(), _second_id()]


# ---------------------------------------------------------------------------
# 6 — completed iteration not repeated
# ---------------------------------------------------------------------------


def test_06_completed_iteration_not_repeated_on_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-replay"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    request = _aq1_path_b_request(work)
    first = run_supervisor_step(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    after_first = load_state(state_path)
    assert after_first["active_candidate"]["candidate_id"] == _second_id()
    assert after_first["generation"] == 1

    second = run_supervisor_step(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    after_second = load_state(state_path)
    # Same orchestration outcome fingerprint must not invent another candidate.
    assert (
        first["orchestration"]["outcome_fingerprint"]
        == second["orchestration"]["outcome_fingerprint"]
    )
    assert after_second["active_candidate"]["candidate_id"] == _second_id()
    assert after_second["visited_candidate_ids"] == [_baseline_id(), _second_id()]
    assert after_second["generation"] == after_first["generation"]
    assert second.get("already_committed") is True


# ---------------------------------------------------------------------------
# 7 — duplicate completion does not double-advance
# ---------------------------------------------------------------------------


def test_07_duplicate_completion_no_double_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-dup"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    request = _aq1_path_b_request(work)
    kwargs = dict(
        state_path=state_path,
        request=request,
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    run_supervisor_step(**kwargs)
    gen_after_one = load_state(state_path)["generation"]
    run_supervisor_step(**kwargs)
    run_supervisor_step(**kwargs)
    final = load_state(state_path)
    assert final["generation"] == gen_after_one
    assert final["active_candidate"]["candidate_id"] == _second_id()
    assert _third_id() not in final["visited_candidate_ids"]


# ---------------------------------------------------------------------------
# 8 — write failure observable; previous commit retained
# ---------------------------------------------------------------------------


def test_08_write_failure_observable_retains_previous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-write-fail"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())
    prior = load_state(state_path)
    prior_fp = prior["state_fingerprint"]

    real_replace = os.replace

    def _boom(src: str | os.PathLike[str], dst: str | os.PathLike[str]) -> None:
        if Path(dst) == state_path:
            raise OSError("simulated atomic replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", _boom)
    with pytest.raises(
        (AnalysisQualityLoopStateError, AnalysisQualityLoopSupervisorError, OSError)
    ):
        run_supervisor_step(
            state_path=state_path,
            request=_aq1_path_b_request(work),
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            next_action="continue_calibration",
            provider=Aq1TempoSearchSpaceProvider(),
        )

    monkeypatch.setattr(os, "replace", real_replace)
    retained = load_state(state_path)
    assert retained["state_fingerprint"] == prior_fp
    assert retained["active_candidate"]["candidate_id"] == _baseline_id()
    assert retained["generation"] == prior["generation"]


# ---------------------------------------------------------------------------
# 9 — corrupt state fail-closed (no silent fresh)
# ---------------------------------------------------------------------------


def test_09_corrupt_state_fail_closed_no_silent_fresh(tmp_path: Path) -> None:
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    state_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(AnalysisQualityLoopStateError):
        load_state(state_path)

    # File must remain corrupt — never rewritten to a silent fresh loop.
    assert state_path.read_text(encoding="utf-8") == "{not-json"


# ---------------------------------------------------------------------------
# 10 — unsupported version fail-closed
# ---------------------------------------------------------------------------


def test_10_unsupported_version_fail_closed(tmp_path: Path) -> None:
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    good = _fresh_aq1_state()
    save_state_atomic(state_path, good)
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload["artifact_version"] = "9.9.9"
    payload["schema_version"] = 99
    state_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(AnalysisQualityLoopStateError, match="unsupported"):
        load_state(state_path)
    with pytest.raises(AnalysisQualityLoopStateError, match="unsupported"):
        validate_state(payload)


# ---------------------------------------------------------------------------
# 11 — retry budget decrements and persists
# ---------------------------------------------------------------------------


def test_11_retry_budget_decrements_and_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-retry"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state(retry_budget=DEFAULT_RETRY_BUDGET))

    def _explode(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise RuntimeError("simulated infrastructure failure")

    monkeypatch.setattr(
        "src.analysis_quality_loop_supervisor.run_orchestration", _explode
    )

    with pytest.raises(
        (AnalysisQualityLoopSupervisorError, RuntimeError)
    ):
        run_supervisor_step(
            state_path=state_path,
            request=_aq1_path_b_request(work),
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )

    loaded = load_state(state_path)
    assert loaded["retry"]["budget_remaining"] == DEFAULT_RETRY_BUDGET - 1
    assert loaded["retry"]["consecutive_failures"] == 1
    assert loaded["retry"]["budget_initial"] == DEFAULT_RETRY_BUDGET
    assert loaded["loop_status"] == "ready"


# ---------------------------------------------------------------------------
# 12 — retry exhaustion terminates
# ---------------------------------------------------------------------------


def test_12_retry_exhaustion_terminates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-retry-ex"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state(retry_budget=2))

    monkeypatch.setattr(
        "src.analysis_quality_loop_supervisor.run_orchestration",
        lambda *_a, **_k: (_ for _ in ()).throw(
            RuntimeError("simulated infrastructure failure")
        ),
    )

    for _ in range(2):
        with pytest.raises(
            (AnalysisQualityLoopSupervisorError, RuntimeError)
        ):
            run_supervisor_step(
                state_path=state_path,
                request=_aq1_path_b_request(work),
                bind_kwargs={"work_dir": work},
                evidence_fingerprint=OPAQUE_EVIDENCE_FP,
                gate_verdict="PASS",
            )

    exhausted = load_state(state_path)
    assert exhausted["retry"]["budget_remaining"] == 0
    assert exhausted["loop_status"] == "retry_exhausted"

    with pytest.raises(AnalysisQualityLoopSupervisorError, match="retry_exhausted"):
        run_supervisor_step(
            state_path=state_path,
            request=_aq1_path_b_request(work),
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
        )


# ---------------------------------------------------------------------------
# 13 — freeze / stop → no next candidate
# ---------------------------------------------------------------------------


def test_13_freeze_and_stop_produce_no_next_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    provider = Aq1TempoSearchSpaceProvider()

    for action, expected_status in (
        ("freeze_candidate", "frozen"),
        ("keep_baseline_and_stop", "stopped"),
    ):
        work = tmp_path / f"aq1-{action}"
        work.mkdir()
        state_path = tmp_path / f"state-{action}.json"
        save_state_atomic(state_path, _fresh_aq1_state())
        result = run_supervisor_step(
            state_path=state_path,
            request=_aq1_path_b_request(work),
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            next_action=action,
            provider=provider,
        )
        assert result["decision"]["next_action"] == action
        iterator = result.get("iterator")
        if iterator is not None:
            assert iterator.get("next_candidate") is None
            assert iterator["iterator_effect"] in {"freeze", "stop"}
        loaded = load_state(state_path)
        assert loaded["loop_status"] == expected_status
        assert loaded["active_candidate"]["candidate_id"] == _baseline_id()
        assert loaded["visited_candidate_ids"] == [_baseline_id()]


# ---------------------------------------------------------------------------
# 14 — defer / HOLD → no next candidate
# ---------------------------------------------------------------------------


def test_14_defer_hold_produces_no_next_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-hold"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    result = run_supervisor_step(
        state_path=state_path,
        request=_aq1_path_b_request(work),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="HOLD",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    assert result["decision"]["decision_status"] == "hold"
    assert result["decision"]["next_action"] == "defer_for_evidence"
    iterator = result.get("iterator")
    if iterator is not None:
        assert iterator.get("next_candidate") is None
        assert iterator["iterator_effect"] == "hold"
    loaded = load_state(state_path)
    assert loaded["loop_status"] == "held"
    assert loaded["active_candidate"]["candidate_id"] == _baseline_id()
    assert _second_id() not in loaded["visited_candidate_ids"]


# ---------------------------------------------------------------------------
# 15 — exhaustion does not further iterate
# ---------------------------------------------------------------------------


def test_15_exhaustion_does_not_further_iterate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    provider = Aq1TempoSearchSpaceProvider()
    members = provider.ordered_members()
    # Start with all but the last candidate already visited; one advance → exhausted
    # on the subsequent continue.
    visited = [m["candidate_id"] for m in members]
    active = members[-1]
    state = _fresh_aq1_state(
        active_candidate=dict(active),
        visited_candidate_ids=list(visited),
    )
    work = tmp_path / "aq1-exhausted"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, state)

    result = run_supervisor_step(
        state_path=state_path,
        request=_aq1_path_b_request(
            work, current_candidate_id=active["candidate_id"]
        ),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=provider,
    )
    assert result["iterator"]["iterator_effect"] == "exhausted"
    assert result["iterator"].get("next_candidate") is None
    loaded = load_state(state_path)
    assert loaded["loop_status"] == "exhausted"
    assert loaded["visited_candidate_ids"] == visited

    with pytest.raises(AnalysisQualityLoopSupervisorError, match="exhausted"):
        run_supervisor_step(
            state_path=state_path,
            request=_aq1_path_b_request(
                work, current_candidate_id=active["candidate_id"]
            ),
            bind_kwargs={"work_dir": work},
            evidence_fingerprint=OPAQUE_EVIDENCE_FP,
            gate_verdict="PASS",
            next_action="continue_calibration",
            provider=provider,
        )
    still = load_state(state_path)
    assert still["loop_status"] == "exhausted"
    assert still["visited_candidate_ids"] == visited


# ---------------------------------------------------------------------------
# 16 — TEST / HOLDOUT cannot drive iteration
# ---------------------------------------------------------------------------


def test_16_test_holdout_cannot_drive_iteration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    provider = Aq1TempoSearchSpaceProvider()

    for role, split in (("test", "TEST"), ("holdout", "TEST")):
        work = tmp_path / f"aq1-{role}"
        work.mkdir()
        state_path = tmp_path / f"state-{role}.json"
        # Fresh state itself must reject non-tunable roles for this slice, or
        # the supervisor step must fail closed before inventing a candidate.
        with pytest.raises(
            (
                AnalysisQualityLoopStateError,
                AnalysisQualityLoopSupervisorError,
            )
        ):
            try:
                save_state_atomic(
                    state_path,
                    _fresh_aq1_state(
                        partition_role=role,
                        partition_id=f"aq1-supervisor-{role}",
                    ),
                )
            except (AnalysisQualityLoopStateError, AnalysisQualityLoopSupervisorError):
                raise
            run_supervisor_step(
                state_path=state_path,
                request=_aq1_path_b_request(
                    work,
                    partition_role=role,
                    split=split,
                    operation="locked_evaluation",
                ),
                bind_kwargs={"work_dir": work},
                evidence_fingerprint=OPAQUE_EVIDENCE_FP,
                gate_verdict="PASS",
                next_action="continue_calibration",
                provider=provider,
            )


# ---------------------------------------------------------------------------
# 17 — production_authorized remains false
# ---------------------------------------------------------------------------


def test_17_production_authorized_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-prod"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    fresh = _fresh_aq1_state()
    assert fresh["production_authorized"] is False
    save_state_atomic(state_path, fresh)

    result = run_supervisor_step(
        state_path=state_path,
        request=_aq1_path_b_request(work),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    assert result["production_authorized"] is False
    assert result["decision"]["production_authorized"] is False
    loaded = load_state(state_path)
    assert loaded["production_authorized"] is False


# ---------------------------------------------------------------------------
# 18 — no forbidden / private paths in persisted state
# ---------------------------------------------------------------------------


def test_18_persisted_state_has_no_forbidden_private_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_aq1_repo(monkeypatch, tmp_path)
    work = tmp_path / "aq1-privacy"
    work.mkdir()
    state_path = _state_path(tmp_path)
    state_path.parent.mkdir(parents=True)
    save_state_atomic(state_path, _fresh_aq1_state())

    run_supervisor_step(
        state_path=state_path,
        request=_aq1_path_b_request(work),
        bind_kwargs={"work_dir": work},
        evidence_fingerprint=OPAQUE_EVIDENCE_FP,
        gate_verdict="PASS",
        next_action="continue_calibration",
        provider=Aq1TempoSearchSpaceProvider(),
    )
    loaded = validate_state(load_state(state_path))
    raw = json.dumps(loaded)
    assert str(work) not in raw
    assert str(state_path) not in raw
    assert "/home/" not in raw
    assert "C:\\\\" not in raw and "C:/" not in raw
    assert "work_dir" not in loaded
    assert ".wav" not in raw.lower()
    assert "catalog.db" not in raw
    # validate_state / portability helpers must accept the committed envelope.
    assert loaded["document_type"] == DOCUMENT_TYPE
