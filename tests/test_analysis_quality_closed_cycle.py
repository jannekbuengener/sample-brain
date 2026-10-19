"""S9 composition tests using the real registered AQ1 headless adapter."""

from __future__ import annotations

import json

from src.analysis_eval_artifact import assert_portable_value, fingerprint
import src.analysis_quality_closed_cycle as closed_cycle
from src.analysis_quality_closed_cycle import (
    AnalysisQualityClosedCycleError,
    _read_result,
    run_quality_cycle,
)
from src.analysis_quality_loop_state import load_state, save_state_atomic
from src.analysis_quality_loop_supervisor import AnalysisQualityLoopSupervisorError
from src.analysis_post_merge import GitRepository
from tests.test_analysis_quality_loop_supervisor import (
    _aq1_path_b_request,
    _fresh_aq1_state,
    _patch_aq1_repo,
)
from tests.test_analysis_promotion import Host as S7Host
from tests.test_analysis_promotion import Provider as S7Provider
from tests.test_analysis_promotion import git, seal as seal_s7, sha
from tests.test_analysis_post_merge import (
    PostMergeProvider,
    S8Host,
    seal_plan,
)
from src.fsld_aq1_tempo_candidate_compare import candidate_by_id


def test_cycle_self_starts_real_aq1_and_stops_on_machine_hold(tmp_path, monkeypatch):
    _patch_aq1_repo(monkeypatch, tmp_path)
    state_path = tmp_path / "host" / "quality-state.json"
    state_path.parent.mkdir()
    save_state_atomic(state_path, _fresh_aq1_state())
    attempt_path = tmp_path / "host" / "cycle-attempt.json"
    work = tmp_path / "aq1-work"
    work.mkdir()
    seen = {}
    competing_cycle_blocked = []

    def calibration_inputs(*, state_path, state):
        try:
            run_quality_cycle(
                state_path=state_path,
                attempt_path=tmp_path / "host" / "competing-cycle.json",
                calibration_inputs=calibration_inputs,
                locked_inputs=lambda **_: {},
                promotion_inputs=lambda **_: {},
                post_merge_inputs=lambda **_: {},
            )
        except closed_cycle.AnalysisQualityClosedCycleError as exc:
            competing_cycle_blocked.append(str(exc))
        request = _aq1_path_b_request(
            work, current_candidate_id=state["active_candidate"]["candidate_id"]
        )

        def decide(context):
            headless_result = context["headless_result"]
            analysis_eval_artifact = context["analysis_eval"]
            seen["headless"] = headless_result
            seen["eval"] = analysis_eval_artifact
            return {
                "evidence_fingerprint": fingerprint(
                    {
                        "request_fingerprint": request["request_fingerprint"],
                        "analysis_eval_fingerprint": fingerprint(analysis_eval_artifact),
                        "domain_artifact_fingerprint": headless_result[
                            "domain_artifact"
                        ]["artifact_fingerprint"],
                    }
                ),
                "gate_verdict": "HOLD",
                "decision_token": None,
                "next_action": None,
            }

        return {
            "request": request,
            "bind_kwargs": {"work_dir": work},
            "decision_provider": decide,
            "decision_provider_id": "aq1-fixture-hold-policy-v1",
        }

    def must_not_promote(**_):
        raise AssertionError("HOLD must not reach S7")

    real_step = closed_cycle.run_supervisor_step
    call_count = 0

    def step_with_lost_reply(**kwargs):
        nonlocal call_count
        call_count += 1
        result = real_step(**kwargs)
        raise RuntimeError("simulated S5 reply loss after atomic commit")

    monkeypatch.setattr(closed_cycle, "run_supervisor_step", step_with_lost_reply)
    inputs = {
        "state_path": state_path,
        "attempt_path": attempt_path,
        "calibration_inputs": calibration_inputs,
        "locked_inputs": lambda **_: (_ for _ in ()).throw(
            AssertionError("HOLD must not reach S6")
        ),
        "promotion_inputs": must_not_promote,
        "post_merge_inputs": must_not_promote,
    }
    try:
        run_quality_cycle(**inputs)
    except RuntimeError as exc:
        assert "S5 reply loss" in str(exc)
    else:
        raise AssertionError("the simulated lost S5 reply must interrupt the first call")
    monkeypatch.setattr(closed_cycle, "run_supervisor_step", real_step)
    result = run_quality_cycle(**inputs)

    assert result["status"] == "held"
    assert result["reason"] == "calibration_decision_not_actionable"
    assert seen["headless"]["run_status"] == "completed"
    assert seen["headless"]["adapter_id"] == "aq1.tempo.candidate_compare"
    assert seen["eval"]["document_type"] == "sample-brain.analysis-eval.v1"
    cycle = load_state(state_path)
    assert cycle["loop_status"] == "held"
    assert cycle["last_orchestration_ref"]["request_fingerprint"] == result[
        "calibration_refs"
    ][0]["request_fingerprint"]
    assert cycle["last_orchestration_ref"]["decision_provider_id"] == (
        "aq1-fixture-hold-policy-v1"
    )
    assert call_count == 1
    assert competing_cycle_blocked == ["cycle generation is already executing"]


def test_cycle_retries_after_retry_only_s5_updates_and_holds_on_exhaustion(
    tmp_path, monkeypatch
):
    _patch_aq1_repo(monkeypatch, tmp_path)
    state_path = tmp_path / "host" / "quality-state.json"
    state_path.parent.mkdir()
    save_state_atomic(state_path, _fresh_aq1_state())
    attempt_path = tmp_path / "host" / "cycle-attempt.json"
    work = tmp_path / "retry-work"
    work.mkdir()
    provider_calls = {"count": 0}

    def calibration_inputs(*, state_path, state):
        request = _aq1_path_b_request(
            work, current_candidate_id=state["active_candidate"]["candidate_id"]
        )

        def decide(context):
            headless_result = context["headless_result"]
            analysis_eval_artifact = context["analysis_eval"]
            provider_calls["count"] += 1
            if provider_calls["count"] <= 3:
                raise RuntimeError("transient decision provider failure")
            return {
                "evidence_fingerprint": fingerprint(
                    {
                        "request_fingerprint": request["request_fingerprint"],
                        "analysis_eval_fingerprint": fingerprint(analysis_eval_artifact),
                        "domain_artifact_fingerprint": headless_result[
                            "domain_artifact"
                        ]["artifact_fingerprint"],
                    }
                ),
                "gate_verdict": "HOLD",
                "decision_token": None,
                "next_action": "defer_for_evidence",
            }

        return {
            "request": request,
            "bind_kwargs": {"work_dir": work},
            "decision_provider": decide,
            "decision_provider_id": "aq1-fixture-retry-policy-v1",
        }

    args = {
        "state_path": state_path,
        "attempt_path": attempt_path,
        "calibration_inputs": calibration_inputs,
        "locked_inputs": lambda **_: (_ for _ in ()).throw(
            AssertionError("retry HOLD must not reach S6")
        ),
        "promotion_inputs": lambda **_: (_ for _ in ()).throw(
            AssertionError("retry HOLD must not reach S7")
        ),
        "post_merge_inputs": lambda **_: (_ for _ in ()).throw(
            AssertionError("retry HOLD must not reach S8")
        ),
    }
    for _ in range(3):
        try:
            run_quality_cycle(**args)
        except Exception as exc:
            assert "transient decision provider failure" in str(exc)
        else:
            raise AssertionError("transient provider failure must consume retry budget")

    exhausted_state = load_state(state_path)
    assert exhausted_state["generation"] == 0
    assert exhausted_state["retry"]["budget_remaining"] == 0
    assert exhausted_state["loop_status"] == "retry_exhausted"
    result = run_quality_cycle(**args)

    assert result["status"] == "held"
    assert result["reason"] == "calibration_retry_exhausted"
    assert provider_calls["count"] == 3

    replayed = run_quality_cycle(**args)
    assert replayed["attempt_fingerprint"] == result["attempt_fingerprint"]
    assert provider_calls["count"] == 3


def test_cycle_lock_is_stable_across_s5_identity_resets(tmp_path):
    state_path = tmp_path / "quality-state.json"
    first = {
        "domain": "aq1.tempo",
        "baseline_candidate": {"candidate_id": "baseline-a"},
        "search_space_fingerprint": "1" * 64,
    }
    reset = {
        "domain": "aq1.tempo",
        "baseline_candidate": {"candidate_id": "baseline-b"},
        "search_space_fingerprint": "2" * 64,
    }

    assert closed_cycle._domain_lock_path(state_path, first) == (
        closed_cycle._domain_lock_path(state_path, reset)
    )


def test_terminal_attempt_rejects_reset_s5_lineage(tmp_path):
    state_path = tmp_path / "quality-state.json"
    initial = _fresh_aq1_state()
    save_state_atomic(state_path, initial)
    attempt_path = tmp_path / "cycle-attempt.json"
    attempt = closed_cycle._new_attempt(initial)
    attempt["phase"] = "held"
    attempt["status"] = "held"
    attempt["reason"] = "transition_budget_exhausted"
    closed_cycle._save_attempt(attempt_path, attempt)

    reset = dict(initial)
    reset.pop("state_fingerprint")
    reset["generation"] = initial["generation"] + 1
    save_state_atomic(state_path, reset)

    inputs = {
        "state_path": state_path,
        "attempt_path": attempt_path,
        "calibration_inputs": lambda **_: {},
        "locked_inputs": lambda **_: {},
        "promotion_inputs": lambda **_: {},
        "post_merge_inputs": lambda **_: {},
    }
    try:
        run_quality_cycle(**inputs)
    except AnalysisQualityClosedCycleError as exc:
        assert "terminal" in str(exc).lower()
    else:
        raise AssertionError("stale terminal attempt must fail closed")


def test_malformed_closed_cycle_result_fails_with_contract_error(tmp_path):
    result_path = tmp_path / "cycle.result.json"
    result_path.write_text(json.dumps({"post_merge_ref": None}), encoding="utf-8")

    try:
        _read_result(result_path)
    except AnalysisQualityClosedCycleError as exc:
        assert "closed-cycle result" in str(exc)
    else:
        raise AssertionError("malformed references must fail closed")


def test_s9_promotion_rejects_repository_outside_temporary_root():
    class Repository:
        path = closed_cycle.Path("C:/Persistent/repository")

        @staticmethod
        def git(*_):
            return "https://github.com/example/repo.git"

    try:
        closed_cycle._require_simulation_repository(
            {"repository": Repository()}, {"repository_id": "example/repo"}
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "temporary directory" in str(exc)
    else:
        raise AssertionError("persistent repositories must not enter S9 proof promotion")


def test_s9_promotion_requires_both_simulation_adapters_even_for_temp_checkout(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(closed_cycle.tempfile, "gettempdir", lambda: str(tmp_path))

    class Repository:
        path = tmp_path / "proof-repository"

        @staticmethod
        def git(*_):
            return "https://github.com/another-owner/production-repo.git"

    class Host:
        repository_id = "another-owner/production-repo"
        repository = Repository.path

    Repository.path.mkdir()
    for repository_is_simulation, host_is_simulation in ((True, False), (False, True)):
        repository = Repository()
        repository.simulation_only = repository_is_simulation
        host = Host()
        host.simulation_only = host_is_simulation
        try:
            closed_cycle._require_simulation_repository(
                {"repository": repository, "host": host},
                {"repository_id": "another-owner/production-repo"},
            )
        except AnalysisQualityClosedCycleError as exc:
            assert "explicitly simulation-only" in str(exc)
        else:
            raise AssertionError("both S9 proof adapters must be marked simulation-only")


def test_s9_temporary_path_component_does_not_authorize_persistent_repository(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(closed_cycle.tempfile, "gettempdir", lambda: str(tmp_path / "system-temp"))

    class Repository:
        path = tmp_path / "workspace" / "tmp" / "customer-repo"

        @staticmethod
        def git(*_):
            return "https://github.com/example/repo.git"

    Repository.path.mkdir(parents=True)
    try:
        closed_cycle._require_simulation_repository(
            {"repository": Repository()}, {"repository_id": "example/repo"}
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "temporary directory" in str(exc)
    else:
        raise AssertionError("a tmp-named child of a persistent root is not temporary")


def test_s9_attempt_authority_fingerprints_bind_durable_storage(tmp_path):
    class Repository:
        path = tmp_path / "repository"

        @staticmethod
        def git(*_):
            return "https://github.com/example/repo.git"

    class Host:
        repository_id = "example/repo"
        repository = Repository.path

    class Provider:
        domain = "aq1.tempo"
        materializer_id = "materializer-v1"
        materializer_version = "1.0"
        verification_id = "verify-v1"
        verification_version = "1.0"
        recovery_materializer_id = "recover-v1"
        recovery_materializer_version = "1.0"

    inputs = {
        "repository": Repository(),
        "host": Host(),
        "provider": Provider(),
        "attempt_root": tmp_path / "s7-attempts",
        "worktree_root": tmp_path / "s7-worktrees",
    }
    manifest = {"repository_id": "example/repo"}
    s7_fingerprint = closed_cycle._promotion_authority_fingerprint(inputs, manifest)
    inputs["attempt_root"] = tmp_path / "alternate-s7-attempts"
    assert closed_cycle._promotion_authority_fingerprint(inputs, manifest) != s7_fingerprint

    post = {
        "repository": Repository(),
        "host": Host(),
        "provider": Provider(),
        "attempt_root": tmp_path / "s8-attempts",
        "baseline_state_path": tmp_path / "baseline.json",
        "verification_root": tmp_path / "verification",
        "worktree_root": tmp_path / "s8-worktrees",
    }
    promotion_attempt_path = tmp_path / "s7-attempts" / "attempt.json"
    s8_fingerprint = closed_cycle._post_merge_authority_fingerprint(
        post, promotion_attempt_path
    )
    post["baseline_state_path"] = tmp_path / "alternate-baseline.json"
    assert closed_cycle._post_merge_authority_fingerprint(
        post, promotion_attempt_path
    ) != s8_fingerprint


def test_terminal_cycle_phases_reload_and_unrelated_s5_invocation_is_rejected(
    tmp_path,
):
    attempt = closed_cycle._new_attempt(_fresh_aq1_state())
    attempt["phase"] = "failed"
    attempt["status"] = "failed"
    attempt_path = tmp_path / "terminal-attempt.json"
    attempt_path.write_text(
        json.dumps(closed_cycle._seal_attempt(attempt)), encoding="utf-8"
    )

    assert closed_cycle._load_attempt(attempt_path)["status"] == "failed"
    try:
        closed_cycle._recovered_orchestration_ref(
            {
                "last_orchestration_ref": {
                    "request_fingerprint": "a" * 64,
                    "decision_provider_id": "other-policy-v1",
                }
            },
            {
                "request_fingerprint": "b" * 64,
                "decision_provider_id": "expected-policy-v1",
            },
            "S5",
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "outside the pending invocation" in str(exc)
    else:
        raise AssertionError("unrelated S5 invocation must not satisfy pending recovery")
    try:
        closed_cycle._require_cycle_owned_freeze(
            {"calibration_refs": [], "initial_state_fingerprint": "s5-state"},
            {
                "state_fingerprint": "s5-state",
                "loop_status": "frozen",
                "last_decision": {"next_action": "freeze_candidate"},
            },
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "lacks this cycle's committed selection evidence" in str(exc)
    else:
        raise AssertionError("an unclaimed frozen S5 state must not enter S6")
    try:
        closed_cycle._require_cycle_owned_freeze(
            {
                "calibration_refs": [
                    {
                        "next_action": "freeze_candidate",
                        "decision_fingerprint": "expected",
                        "candidate": {"candidate_id": "expected"},
                        "committed_state_fingerprint": "s5-state",
                    }
                ]
            },
            {
                "last_decision": {
                    "next_action": "freeze_candidate",
                    "decision_fingerprint": "foreign",
                },
                "state_fingerprint": "s5-state",
                "loop_status": "frozen",
                "active_candidate": {"candidate_id": "foreign"},
            },
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "lacks this cycle's committed selection evidence" in str(exc)
    else:
        raise AssertionError("a different frozen decision must not enter S6")
    initial = _fresh_aq1_state()
    closed_cycle._require_cycle_owned_ready(
        {"initial_state_fingerprint": initial["state_fingerprint"], "calibration_refs": []},
        initial,
    )
    changed_ready = dict(initial)
    changed_ready["state_fingerprint"] = "external-advance"
    try:
        closed_cycle._require_cycle_owned_ready(
            {"initial_state_fingerprint": initial["state_fingerprint"], "calibration_refs": []},
            changed_ready,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "committed calibration lineage" in str(exc)
    else:
        raise AssertionError("an unclaimed ready S5 advance must not be evaluated")


def test_retry_only_s5_update_is_distinguished_from_committed_decision():
    identity = {
        "s5_generation": 4,
        "previous_decision_fingerprint": "decision-fp",
        "active_candidate": {"candidate_id": "candidate-a"},
        "visited_candidate_ids": ["candidate-a"],
        "retry": {"budget_remaining": 3, "consecutive_failures": 0},
    }
    retry_state = {
        "generation": 4,
        "last_decision": {"decision_fingerprint": "decision-fp"},
        "active_candidate": {"candidate_id": "candidate-a"},
        "visited_candidate_ids": ["candidate-a"],
        "retry": {
            "budget_remaining": 2,
            "consecutive_failures": 1,
            "last_failure_class": "unknown",
        },
        "loop_status": "ready",
    }
    assert closed_cycle._retry_only_s5_update(identity, retry_state)
    retry_state["generation"] = 5
    assert not closed_cycle._retry_only_s5_update(identity, retry_state)
    retry_state["generation"] = 4
    retry_state["retry"]["budget_remaining"] = 0
    retry_state["loop_status"] = "retry_exhausted"
    assert closed_cycle._retry_only_s5_update(identity, retry_state)

    expected_seed = {"state_fingerprint": "expected-seed"}
    changed_seed = {"state_fingerprint": "foreign-seed"}
    try:
        closed_cycle._require_continuation_seed_ownership(
            expected_seed, changed_seed, None
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "lacks this cycle's committed S8 seed" in str(exc)
    else:
        raise AssertionError("an unclaimed continuation state must not be reused")
    closed_cycle._require_continuation_seed_ownership(
        expected_seed,
        changed_seed,
        {"phase": "continuation"},
    )


def test_cycle_composes_real_aq1_s5_s6_with_s7_s8_and_continuation(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(closed_cycle.tempfile, "gettempdir", lambda: str(tmp_path))
    _patch_aq1_repo(monkeypatch, tmp_path)
    state_path = tmp_path / "host" / "quality-state.json"
    state_path.parent.mkdir()
    save_state_atomic(state_path, _fresh_aq1_state())
    attempt_path = tmp_path / "host" / "cycle-attempt.json"
    repo_root = tmp_path / "promotion-repo"
    s7_cache = {}
    s8_cache = {}
    fail_continuation_provider_once = {"pending": True}

    def calibration_inputs(*, state_path, state):
        candidate_id = state["active_candidate"]["candidate_id"]
        baseline_id = state["baseline_candidate"]["candidate_id"]
        work = tmp_path / "domain" / state_path.stem / f"{state['generation']}-{candidate_id}"
        work.mkdir(parents=True, exist_ok=True)
        request = _aq1_path_b_request(
            work,
            current_candidate_id=candidate_id,
            baseline_candidate_id=baseline_id,
        )

        def decide(context):
            headless_result = context["headless_result"]
            analysis_eval_artifact = context["analysis_eval"]
            if (
                "continuation-" in state_path.stem
                and fail_continuation_provider_once["pending"]
            ):
                fail_continuation_provider_once["pending"] = False
                raise RuntimeError("simulated transient continuation provider failure")
            output_relpath = request["aq1_inputs"]["output_relpath"]
            domain_result = json.loads((work / output_relpath).read_text(encoding="utf-8"))
            by_id = {item["candidate_id"]: item for item in domain_result["candidates"]}
            baseline_score = by_id[baseline_id]["metrics"]["ma"]["tempo"][
                "accuracy_within_2_bpm"
            ]
            current_score = by_id[candidate_id]["metrics"]["ma"]["tempo"][
                "accuracy_within_2_bpm"
            ]
            improved = current_score > baseline_score
            locked = request["partition"]["role"] in {"test", "holdout"}
            if locked and improved:
                verdict = "PASS"
                token = "PROMOTION_CANDIDATE_IDENTIFIED"
                action = "handoff_promotion_controller"
            elif not locked and improved:
                verdict = "PASS"
                token = "PROMOTION_CANDIDATE_IDENTIFIED"
                action = "freeze_candidate"
            else:
                verdict = "FAIL"
                token = "NO_JUSTIFIED_CANDIDATE"
                action = "keep_baseline_and_stop" if locked else "continue_calibration"
            evidence = {
                "request_fingerprint": request["request_fingerprint"],
                "domain_artifact_fingerprint": headless_result["domain_artifact"][
                    "artifact_fingerprint"
                ],
                "analysis_eval_fingerprint": fingerprint(analysis_eval_artifact),
                "baseline_accuracy_within_2_bpm": baseline_score,
                "candidate_accuracy_within_2_bpm": current_score,
                "improved": improved,
            }
            return {
                "evidence_fingerprint": fingerprint(evidence),
                "gate_verdict": verdict,
                "decision_token": token,
                "next_action": action,
            }

        return {
            "request": request,
            "bind_kwargs": {"work_dir": work},
            "decision_provider": decide,
            "decision_provider_id": "aq1-fixture-metric-comparison-v1",
        }

    def locked_inputs(*, state_path, state):
        candidate_id = state["active_candidate"]["candidate_id"]
        baseline_id = state["baseline_candidate"]["candidate_id"]
        work = tmp_path / "locked-domain"
        work.mkdir(exist_ok=True)
        request = _aq1_path_b_request(
            work,
            operation="locked_evaluation",
            partition_role="holdout",
            split="TEST",
            current_candidate_id=candidate_id,
            baseline_candidate_id=baseline_id,
        )

        def decide(context):
            headless_result = context["headless_result"]
            analysis_eval_artifact = context["analysis_eval"]
            output_relpath = request["aq1_inputs"]["output_relpath"]
            domain_result = json.loads((work / output_relpath).read_text(encoding="utf-8"))
            by_id = {item["candidate_id"]: item for item in domain_result["candidates"]}
            baseline_score = by_id[baseline_id]["metrics"]["ma"]["tempo"][
                "accuracy_within_2_bpm"
            ]
            current_score = by_id[candidate_id]["metrics"]["ma"]["tempo"][
                "accuracy_within_2_bpm"
            ]
            improved = current_score > baseline_score
            evidence = {
                "request_fingerprint": request["request_fingerprint"],
                "domain_artifact_fingerprint": headless_result["domain_artifact"][
                    "artifact_fingerprint"
                ],
                "analysis_eval_fingerprint": fingerprint(analysis_eval_artifact),
                "baseline_accuracy_within_2_bpm": baseline_score,
                "candidate_accuracy_within_2_bpm": current_score,
                "improved": improved,
            }
            return {
                "evidence_fingerprint": fingerprint(evidence),
                "gate_verdict": "PASS" if improved else "FAIL",
                "decision_token": (
                    "PROMOTION_CANDIDATE_IDENTIFIED"
                    if improved
                    else "NO_JUSTIFIED_CANDIDATE"
                ),
                "next_action": (
                    "handoff_promotion_controller"
                    if improved
                    else "keep_baseline_and_stop"
                ),
            }

        return {
            "request": request,
            "bind_kwargs": {"work_dir": work},
            "decision_provider": decide,
            "decision_provider_id": "aq1-fixture-metric-comparison-v1",
        }

    def promotion_inputs(*, locked_result):
        if not s7_cache:
            repo_root.mkdir()
            git(repo_root, "init", "-b", "main")
            git(repo_root, "config", "user.name", "Synthetic Fixture")
            git(repo_root, "config", "user.email", "fixture@example.invalid")
            git(repo_root, "config", "core.autocrlf", "false")
            (repo_root / "config").mkdir()
            (repo_root / "config/promotion.json").write_text("{}\n", newline="\n")
            git(repo_root, "add", "config/promotion.json")
            git(repo_root, "commit", "-m", "synthetic baseline")
            base = git(repo_root, "rev-parse", "HEAD")
            git(repo_root, "update-ref", "refs/remotes/origin/main", base)
            git(repo_root, "remote", "add", "origin", "https://github.com/example/repo.git")
            selected = candidate_by_id(
                locked_result["current_candidate"]["candidate_id"]
            )
            payload = {
                "domain": locked_result["domain"],
                "candidate_id": locked_result["current_candidate"]["candidate_id"],
                "config_fingerprint": locked_result["current_candidate"][
                    "config_fingerprint"
                ],
                "bpm_normalization": selected.bpm_normalization,
            }
            promoted_content = json.dumps(
                payload, sort_keys=True, separators=(",", ":")
            ) + "\n"

            class Aq1PromotionProvider(S7Provider):
                def __init__(self):
                    super().__init__()
                    self.payload = {"config/promotion.json": promoted_content}
                    self.inputs = {
                        "candidate_id": payload["candidate_id"],
                        "config_fingerprint": payload["config_fingerprint"],
                        "bpm_normalization": payload["bpm_normalization"],
                    }

                def validate_plan(self, manifest, result):
                    return (
                        result["current_candidate"]
                        == locked_result["current_candidate"]
                        and manifest["current_candidate"]
                        == locked_result["current_candidate"]
                        and manifest["materializer"]["inputs"] == self.inputs
                    )

                def materialize(self, inputs):
                    assert inputs == self.inputs
                    self.calls += 1
                    return self.payload

            provider = Aq1PromotionProvider()

            class CycleHost(S7Host):
                simulation_only = True

                def merge(self, number, expected_head_sha, method):
                    super().merge(number, expected_head_sha, method)
                    git(repo_root, "update-ref", "refs/remotes/origin/main", expected_head_sha)

            host = CycleHost(repo_root, base)
            manifest = seal_s7(
                {
                    "document_type": "sample-brain.analysis-promotion-manifest.v1",
                    "artifact_version": "1.0.0",
                    "domain": locked_result["domain"],
                    "baseline_candidate": locked_result["baseline_candidate"],
                    "current_candidate": locked_result["current_candidate"],
                    "locked_result_fingerprint": locked_result["result_fingerprint"],
                    "decision_fingerprint": locked_result["decision"]["decision_fingerprint"],
                    "evidence_fingerprint": locked_result["decision"]["evidence"]["evidence_fingerprint"],
                    "expected_base_sha": base,
                    "repository_id": "example/repo",
                    "allowed_paths": ["config/promotion.json"],
                    "forbidden_paths": ["private"],
                    "materializer": {
                        "id": provider.materializer_id,
                        "version": provider.materializer_version,
                        "inputs": provider.inputs,
                    },
                    "changes": {
                        "config/promotion.json": {
                            "before_sha256": sha("{}\n"),
                            "after_sha256": sha(provider.payload["config/promotion.json"]),
                        }
                    },
                    "validation": ["synthetic.regression.v1"],
                    "policy": {
                        "version": "1.0.0",
                        "required_checks": [{"name": "required", "app_id": 15368}],
                        "merge_method": "squash",
                        "review_gate": "all_feedback_dispositioned.v1",
                    },
                }
            )
            repository = GitRepository(repo_root)
            repository.simulation_only = True
            s7_cache.update(
                provider=provider,
                host=host,
                base=base,
                manifest=manifest,
                repository=repository,
                worktree_root=tmp_path / "promotion-worktrees",
                attempt_root=tmp_path / "promotion-attempts",
            )
        return {key: value for key, value in s7_cache.items() if key != "base"}

    def post_merge_inputs(*, locked_result, promotion_manifest, promotion_attempt):
        class CyclePostMergeHost(S8Host):
            simulation_only = True

        class Aq1PostMergeProvider(PostMergeProvider):
            def verify_candidate(self, worktree, candidate, contract_id, evidence_root):
                assert contract_id == "synthetic.post-merge.v1"
                head = git(worktree, "rev-parse", "HEAD")
                content = (worktree / "config/promotion.json").read_text(encoding="utf-8")
                expected = (
                    s7_cache["provider"].payload["config/promotion.json"]
                    if head == self.promoted_sha
                    else "{}\n"
                )
                assert content == expected
                self.verify_calls.append((candidate["candidate_id"], head, contract_id))
                outcome = self.outcomes["promoted" if head == self.promoted_sha else "baseline"]
                return {
                    "outcome": outcome,
                    "evidence_fingerprint": fingerprint(
                        {"candidate": candidate["candidate_id"], "content": content, "outcome": outcome}
                    ),
                    "reason_code": None if outcome == "PASS" else "synthetic_verification_failed",
                }

        provider = s8_cache.setdefault("provider", Aq1PostMergeProvider())
        provider.promoted_sha = promotion_attempt["merge_sha"]
        recovery_policy = {
            "version": "1.0.0",
            "required_checks": [{"name": "required", "app_id": 15368}],
            "merge_method": "squash",
            "review_gate": "all_feedback_dispositioned.v1",
        }
        plan = seal_plan(
            {
                "document_type": "sample-brain.analysis-post-merge-plan.v1",
                "artifact_version": "1.0.0",
                "domain": locked_result["domain"],
                "promotion_manifest_fingerprint": promotion_manifest["manifest_fingerprint"],
                "promotion_attempt_fingerprint": promotion_attempt["state_fingerprint"],
                "locked_result_fingerprint": locked_result["result_fingerprint"],
                "decision_fingerprint": locked_result["decision"]["decision_fingerprint"],
                "evidence_fingerprint": locked_result["decision"]["evidence"]["evidence_fingerprint"],
                "merge_sha": promotion_attempt["merge_sha"],
                "previous_baseline_candidate": locked_result["baseline_candidate"],
                "promoted_candidate": locked_result["current_candidate"],
                "repository_id": "example/repo",
                "verification": {
                    "id": provider.verification_id,
                    "version": provider.verification_version,
                    "contracts": ["synthetic.post-merge.v1"],
                },
                "recovery": {
                    "expected_base_sha": promotion_attempt["merge_sha"],
                    "allowed_paths": ["config/promotion.json"],
                    "forbidden_paths": ["private"],
                    "materializer": {
                        "id": provider.recovery_materializer_id,
                        "version": provider.recovery_materializer_version,
                        "inputs": {"mode": "last-known-good"},
                    },
                    "changes": {
                        "config/promotion.json": {
                            "before_sha256": sha(s7_cache["provider"].payload["config/promotion.json"]),
                            "after_sha256": sha("{}\n"),
                        }
                    },
                    "change_fingerprint": "0" * 64,
                    "validation": ["synthetic.recovery.v1"],
                    "policy": recovery_policy,
                    "policy_fingerprint": "0" * 64,
                },
            }
        )
        return {
            "plan": plan,
            "provider": provider,
            "repository": s7_cache["repository"],
            "host": s8_cache.setdefault(
                "host", CyclePostMergeHost(repo_root, promotion_attempt)
            ),
            "verification_root": tmp_path / "verification",
            "worktree_root": tmp_path / "s8-worktrees",
            "attempt_root": tmp_path / "s8-attempts",
            "baseline_state_path": tmp_path / "accepted-baseline.json",
        }

    def live_post_merge_host_inputs(**kwargs):
        post = post_merge_inputs(**kwargs)
        post["host"] = S8Host(repo_root, kwargs["promotion_attempt"])
        return post

    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=live_post_merge_host_inputs,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "explicitly simulation-only" in str(exc)
    else:
        raise AssertionError("S8 must reject an unmarked host before recovery can run")
    assert not s8_cache["provider"].verify_calls

    real_run_post_merge = closed_cycle.run_post_merge
    lost_reply = {"pending": True}

    def run_post_merge_with_one_lost_reply(**kwargs):
        outcome = real_run_post_merge(**kwargs)
        if lost_reply["pending"]:
            lost_reply["pending"] = False
            raise RuntimeError("simulated lost S8 response after durable acceptance")
        return outcome

    monkeypatch.setattr(closed_cycle, "run_post_merge", run_post_merge_with_one_lost_reply)
    first_result = None
    try:
        first_result = run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except RuntimeError as exc:
        assert "lost S8 response" in str(exc)
    else:
        raise AssertionError(
            f"the simulated lost S8 reply must interrupt the first call: {first_result!r}"
        )

    def changed_promotion_inputs(*, locked_result):
        inputs = promotion_inputs(locked_result=locked_result)
        inputs["manifest"] = dict(inputs["manifest"])
        inputs["manifest"]["manifest_fingerprint"] = "0" * 64
        return inputs

    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=changed_promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "S7 manifest differs" in str(exc)
    else:
        raise AssertionError("S8 replay must reject a changed S7 manifest")
    assert s7_cache["host"].creates == 1
    assert s7_cache["host"].merges == 1

    def changed_post_merge_authority(**kwargs):
        post = post_merge_inputs(**kwargs)
        post["attempt_root"] = tmp_path / "alternate-s8-attempts"
        return post

    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=changed_post_merge_authority,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "pending cycle invocation identity mismatch" in str(exc)
    else:
        raise AssertionError("S8 replay must reject a changed attempt authority")

    post_merge_calls = {"count": 0}

    def changed_post_merge_inputs(*, locked_result, promotion_manifest, promotion_attempt):
        post = post_merge_inputs(
            locked_result=locked_result,
            promotion_manifest=promotion_manifest,
            promotion_attempt=promotion_attempt,
        )
        post_merge_calls["count"] += 1
        if post_merge_calls["count"] == 2:
            post["plan"] = dict(post["plan"])
            post["plan"]["plan_fingerprint"] = "f" * 64
        return post

    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=changed_post_merge_inputs,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "S8 plan differs" in str(exc)
    else:
        raise AssertionError("continuation must reject a changed S8 acceptance plan")

    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except Exception as exc:
        assert "transient continuation provider failure" in str(exc)
    else:
        raise AssertionError("continuation retry must preserve transient failure")

    real_supervisor_step = closed_cycle.run_supervisor_step
    continuation_race = {"done": False, "path": None, "state": None}

    def race_continuation_dispatch(**kwargs):
        path = closed_cycle.Path(kwargs["state_path"])
        if "continuation-" in path.stem and not continuation_race["done"]:
            continuation_race["done"] = True
            before = load_state(path)
            continuation_race["path"] = path
            continuation_race["state"] = before
            changed = dict(before)
            changed.pop("state_fingerprint")
            changed["generation"] = int(before["generation"]) + 1
            save_state_atomic(path, changed)
        return real_supervisor_step(**kwargs)

    monkeypatch.setattr(closed_cycle, "run_supervisor_step", race_continuation_dispatch)
    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except AnalysisQualityLoopSupervisorError as exc:
        assert "state changed before supervisor dispatch" in str(exc)
    else:
        raise AssertionError("continuation dispatch must reject a changed pre-dispatch state")
    assert continuation_race["path"] is not None
    save_state_atomic(continuation_race["path"], continuation_race["state"])
    monkeypatch.setattr(closed_cycle, "run_supervisor_step", real_supervisor_step)

    lost_continuation_reply = {"pending": True}

    def lose_continuation_reply(**kwargs):
        outcome = real_supervisor_step(**kwargs)
        if "continuation-" in closed_cycle.Path(kwargs["state_path"]).stem and lost_continuation_reply["pending"]:
            lost_continuation_reply["pending"] = False
            raise RuntimeError("simulated lost continuation response after durable state commit")
        return outcome

    monkeypatch.setattr(closed_cycle, "run_supervisor_step", lose_continuation_reply)
    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except RuntimeError as exc:
        assert "lost continuation response" in str(exc)
    else:
        raise AssertionError("lost continuation response must interrupt the first call")
    monkeypatch.setattr(closed_cycle, "run_supervisor_step", real_supervisor_step)
    result = run_quality_cycle(
        state_path=state_path,
        attempt_path=attempt_path,
        calibration_inputs=calibration_inputs,
        locked_inputs=locked_inputs,
        promotion_inputs=promotion_inputs,
        post_merge_inputs=post_merge_inputs,
    )

    assert result["outcome_token"] == "AUTONOMOUS_QUALITY_LOOP_FIRST_CLOSED_CYCLE"
    assert result["evidence_classifications"]["domain_execution"] == "REAL_SANITIZED_DOMAIN_EXECUTION"
    assert result["evidence_classifications"]["proof_evaluator"] == "INJECTED_PROOF_EVALUATOR"
    assert result["evidence_classifications"]["repository_governance"] == "INFRASTRUCTURE_SIMULATION"
    assert result["locked_ref"]["terminal_status"] == "ready"
    assert result["promotion_ref"]["status"] == "merged"
    assert result["post_merge_ref"]["status"] == "accepted"
    assert result["accepted_baseline"]["candidate"] == result["final_candidate"]
    assert result["last_known_good"]["candidate"] == result["initial_baseline_candidate"]
    assert result["continuation_ref"]["next_action"] == "continue_calibration"
    assert result["continuation_ref"]["decision_provider_id"] == (
        "aq1-fixture-metric-comparison-v1"
    )
    assert result["continuation_ref"]["candidate"]["candidate_id"] != result["final_candidate"]["candidate_id"]
    assert len(result["calibration_refs"]) == 2
    assert result["calibration_refs"][0]["next_action"] == "continue_calibration"
    assert result["calibration_refs"][1]["next_action"] == "freeze_candidate"
    assert result["calibration_refs"][0]["candidate"] == result[
        "initial_baseline_candidate"
    ]
    assert result["calibration_refs"][1]["candidate"] == result["final_candidate"]
    assert s7_cache["host"].creates == 1
    assert s7_cache["host"].merges == 1
    assert_portable_value(result)
    assert run_quality_cycle(
        state_path=state_path,
        attempt_path=attempt_path,
        calibration_inputs=calibration_inputs,
        locked_inputs=locked_inputs,
        promotion_inputs=promotion_inputs,
        post_merge_inputs=post_merge_inputs,
    ) == result

    # Completed replay is bound to the current S5 lineage through the public cycle API.
    owned_s5 = load_state(state_path)
    reset_s5 = dict(owned_s5)
    reset_s5.pop("state_fingerprint")
    reset_s5["generation"] = int(owned_s5["generation"]) + 1
    save_state_atomic(state_path, reset_s5)
    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "different S5 lineage" in str(exc)
    else:
        raise AssertionError("completed replay must reject a reset S5 lineage")
    save_state_atomic(state_path, owned_s5)

    result_path = closed_cycle._result_path(attempt_path)
    copied_result = dict(result)
    copied_result["locked_ref"] = dict(copied_result["locked_ref"])
    copied_result["locked_ref"]["result_fingerprint"] = "8" * 64
    copied_result["result_fingerprint"] = fingerprint(
        {key: value for key, value in copied_result.items() if key != "result_fingerprint"}
    )
    result_path.write_text(json.dumps(copied_result), encoding="utf-8")
    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "persisted cycle attempt" in str(exc)
    else:
        raise AssertionError("same-cycle copied result must be bound to its owning attempt")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    # Recreate the durable crash window after result publication but before the
    # terminal attempt commit, then recover only through the public entry point.
    crash_attempt = json.loads(attempt_path.read_text(encoding="utf-8"))
    crash_attempt.pop("attempt_fingerprint")
    crash_attempt["phase"] = "continuation"
    crash_attempt["status"] = "running"
    crash_attempt["pending"] = None
    closed_cycle._save_attempt(attempt_path, crash_attempt)
    assert run_quality_cycle(
        state_path=state_path,
        attempt_path=attempt_path,
        calibration_inputs=calibration_inputs,
        locked_inputs=locked_inputs,
        promotion_inputs=promotion_inputs,
        post_merge_inputs=post_merge_inputs,
    ) == result

    foreign_result = dict(result)
    foreign_result["cycle_id"] = "another-completed-cycle"
    foreign_result["result_fingerprint"] = fingerprint(
        {key: value for key, value in foreign_result.items() if key != "result_fingerprint"}
    )
    result_path = closed_cycle._result_path(attempt_path)
    result_path.write_text(json.dumps(foreign_result), encoding="utf-8")
    assert _read_result(result_path) == foreign_result
    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=promotion_inputs,
            post_merge_inputs=post_merge_inputs,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "another cycle" in str(exc)
    else:
        raise AssertionError("completed replay must reject a valid foreign cycle result")

    # Recreate a promotion restart with a replaced S6 artifact; the public cycle
    # must reject it before the S7 input factory can run.
    result_path.write_text(json.dumps(result), encoding="utf-8")
    promotion_restart = json.loads(attempt_path.read_text(encoding="utf-8"))
    promotion_restart.pop("attempt_fingerprint")
    promotion_restart["phase"] = "promotion"
    promotion_restart["status"] = "running"
    promotion_restart["pending"] = None
    closed_cycle._save_attempt(attempt_path, promotion_restart)
    result_path.unlink()
    locked_path = state_path.with_name(state_path.name + ".locked-result.json")
    replaced_locked = json.loads(locked_path.read_text(encoding="utf-8"))
    replaced_locked["result_fingerprint"] = "7" * 64
    locked_path.write_text(json.dumps(replaced_locked), encoding="utf-8")
    try:
        run_quality_cycle(
            state_path=state_path,
            attempt_path=attempt_path,
            calibration_inputs=calibration_inputs,
            locked_inputs=locked_inputs,
            promotion_inputs=lambda **_: (_ for _ in ()).throw(
                AssertionError("replaced S6 artifact must fail before S7 input construction")
            ),
            post_merge_inputs=post_merge_inputs,
        )
    except AnalysisQualityClosedCycleError as exc:
        assert "committed S6" in str(exc)
    else:
        raise AssertionError("promotion restart must reject a replaced S6 result")
