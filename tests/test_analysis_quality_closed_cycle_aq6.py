"""S10 second-domain portability proof: AQ6 through the generic S5-S9 chain.

The AQ1 proof (tests/test_analysis_quality_closed_cycle.py) stays the frozen
first-domain reference. These cases prove the same generic composition runs for
AQ6 Harmonic Ranking with only domain-owned adapter/search-space/policy inputs
changed, and that the generic chain keeps no AQ6 special case.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

import src.analysis_quality_closed_cycle as closed_cycle
from src.analysis_eval_artifact import fingerprint
from src.analysis_headless_run import build_request
from src.analysis_quality_closed_cycle import (
    AnalysisQualityClosedCycleError,
    run_quality_cycle,
)
from src.analysis_quality_loop_state import fresh_state, load_state, save_state_atomic
from src.analysis_post_merge import GitRepository
from src.aq6_harmonic_ranking_candidate_compare import (
    candidate_by_id,
    candidate_public,
)
from src.aq_candidate_search_spaces import (
    default_search_space_provider,
    registered_search_space_domains,
)
from src.aq_candidate_search_spaces.aq6_harmonic import Aq6HarmonicSearchSpaceProvider
from tests.test_analysis_post_merge import PostMergeProvider, S8Host, seal_plan
from tests.test_analysis_promotion import Host as S7Host
from tests.test_analysis_promotion import Provider as S7Provider
from tests.test_analysis_promotion import git, seal as seal_s7, sha

AQ6_DOMAIN = "aq6.ranking"
AQ6_ADAPTER_ID = "aq6.ranking.candidate_compare"
AQ6_PARTITION_ID = "aq6-s10-cal"

BASELINE_ID = "harmonic.baseline.v1"
JUSTIFIED_ID = "harmonic.rank_filter.drop_uncertain"
EXPECTED_ORDER = (
    "harmonic.baseline.v1",
    "harmonic.weights.harmony_0.90_bpm_0.10",
    "harmonic.weights.harmony_1.00_bpm_0.00",
    "harmonic.rank_filter.drop_uncertain",
)


def _provider() -> Aq6HarmonicSearchSpaceProvider:
    return Aq6HarmonicSearchSpaceProvider()


def _config_fp(candidate_id: str) -> str:
    return fingerprint(candidate_public(candidate_by_id(candidate_id)))


def _fresh_aq6_state(**overrides: Any) -> dict[str, Any]:
    provider = _provider()
    baseline = {
        "candidate_id": BASELINE_ID,
        "config_fingerprint": _config_fp(BASELINE_ID),
    }
    kwargs: dict[str, Any] = {
        "domain": AQ6_DOMAIN,
        "partition_id": AQ6_PARTITION_ID,
        "partition_role": "calibration",
        "baseline_candidate": baseline,
        "active_candidate": dict(baseline),
        "search_space_id": provider.search_space_id,
        "search_space_version": provider.search_space_version,
        "search_space_fingerprint": provider.search_space_fingerprint(),
        "visited_candidate_ids": [BASELINE_ID],
        "retry_budget": 3,
    }
    kwargs.update(overrides)
    return fresh_state(**kwargs)


def _aq6_request(
    *,
    operation: str,
    partition_role: str,
    partition_id: str,
    candidate_id: str,
    baseline_id: str,
) -> dict[str, Any]:
    return build_request(
        domain=AQ6_DOMAIN,
        adapter_id=AQ6_ADAPTER_ID,
        operation=operation,
        benchmark_id="aq6-s10-closed-cycle-bench-v1",
        dataset_id="aq6-s10-closed-cycle-dataset-v1",
        dataset_content_fingerprint=fingerprint(
            {"dataset_id": "aq6-s10-closed-cycle-dataset-v1"}
        ),
        partition_id=partition_id,
        partition_role=partition_role,
        baseline_candidate_id=baseline_id,
        baseline_config_fingerprint=_config_fp(baseline_id),
        current_candidate_id=candidate_id,
        current_config_fingerprint=_config_fp(candidate_id),
        evidence_intent="domain_artifact",
    )


def _aq6_decision(
    *,
    output_path: Path,
    candidate_id: str,
    baseline_id: str,
    locked: bool,
    observed: list | None = None,
):
    """Domain-owned AQ6 policy over existing AQ6 evidence only.

    Theory stays a hard gate, ranking metrics may not regress, and a candidate
    is only justified when it strictly improves an existing AQ6 metric.
    """

    def decide(context):
        if observed is not None:
            observed.append(context["headless_result"])
        headless_result = context["headless_result"]
        if headless_result["run_status"] != "completed":
            # A non-completed domain execution can never become a ready
            # decision: no token, no promotion action.
            return {
                "evidence_fingerprint": fingerprint(
                    {
                        "request_fingerprint": context["request_fingerprint"],
                        "run_status": headless_result["run_status"],
                    }
                ),
                "gate_verdict": "HOLD",
                "decision_token": None,
                "next_action": "stop_controlled_failure",
            }
        domain_result = json.loads(Path(output_path).read_text(encoding="utf-8"))
        by_id = {item["candidate_id"]: item for item in domain_result["candidates"]}
        current = by_id[candidate_id]
        base = by_id[baseline_id]
        current_macro = current["ranking"]["as_labeled"]["macro"]
        base_macro = base["ranking"]["as_labeled"]["macro"]
        theory_pass = current["theory_gate"]["pass"] is True
        no_regression = (
            current_macro["precision_at_1"] >= base_macro["precision_at_1"]
            and current_macro["mrr_at_5"] >= base_macro["mrr_at_5"]
            and current_macro["ndcg_at_5"] >= base_macro["ndcg_at_5"]
            and current_macro["top_5_false_positive_rate"]
            <= base_macro["top_5_false_positive_rate"]
        )
        strict_improvement = (
            current_macro["precision_at_1"] > base_macro["precision_at_1"]
            or current_macro["mrr_at_5"] > base_macro["mrr_at_5"]
            or current_macro["ndcg_at_5"] > base_macro["ndcg_at_5"]
            or current_macro["top_5_false_positive_rate"]
            < base_macro["top_5_false_positive_rate"]
        )
        justified = theory_pass and no_regression and strict_improvement
        evidence = {
            "request_fingerprint": context["request_fingerprint"],
            "domain_artifact_fingerprint": context["headless_result"]["domain_artifact"][
                "artifact_fingerprint"
            ],
            "analysis_eval_fingerprint": fingerprint(context["analysis_eval"]),
            "baseline_candidate_id": baseline_id,
            "current_candidate_id": candidate_id,
            "baseline_top_5_false_positive_rate": base_macro[
                "top_5_false_positive_rate"
            ],
            "candidate_top_5_false_positive_rate": current_macro[
                "top_5_false_positive_rate"
            ],
            "theory_gate_pass": theory_pass,
            "justified": justified,
        }
        if justified and locked:
            verdict = "PASS"
            token = "PROMOTION_CANDIDATE_IDENTIFIED"
            action = "handoff_promotion_controller"
        elif justified:
            verdict = "PASS"
            token = "PROMOTION_CANDIDATE_IDENTIFIED"
            action = "freeze_candidate"
        elif locked:
            verdict = "FAIL"
            token = "NO_JUSTIFIED_CANDIDATE"
            action = "keep_baseline_and_stop"
        else:
            verdict = "FAIL"
            token = "NO_JUSTIFIED_CANDIDATE"
            action = "continue_calibration"
        return {
            "evidence_fingerprint": fingerprint(evidence),
            "gate_verdict": verdict,
            "decision_token": token,
            "next_action": action,
        }

    return decide


def _bind_kwargs(output_path: Path, theory_fixture_path: Path | None) -> dict[str, str]:
    kwargs = {"output_path": str(output_path)}
    if theory_fixture_path is not None:
        kwargs["theory_fixture_path"] = str(theory_fixture_path)
    return kwargs


def _promotion_payload(candidate_id: str, config_fingerprint: str) -> dict[str, Any]:
    public = candidate_public(candidate_by_id(candidate_id))
    return {
        "candidate_id": public["candidate_id"],
        "config_fingerprint": config_fingerprint,
        "harmony_weight": public["harmony_weight"],
        "bpm_weight": public["bpm_weight"],
        "drop_uncertain": public["drop_uncertain"],
    }


class _Aq6PromotionProvider(S7Provider):
    domain = AQ6_DOMAIN
    materializer_id = "synthetic.aq6.config"
    materializer_version = "1.0.0"

    def __init__(self, inputs: dict[str, Any]):
        super().__init__()
        self.inputs = inputs
        self.payload = {
            "config/promotion.json": json.dumps(inputs, sort_keys=True, separators=(",", ":"))
            + "\n"
        }

    def validate_plan(self, manifest, result):
        return (
            result["current_candidate"] == manifest["current_candidate"]
            and manifest["materializer"]["inputs"] == self.inputs
        )

    def materialize(self, inputs):
        assert inputs == self.inputs
        self.calls += 1
        return self.payload

    def validate_candidate(self, worktree, contract_id):
        assert contract_id == "synthetic.regression.v1"
        assert (worktree / "config/promotion.json").read_text() == self.payload[
            "config/promotion.json"
        ]
        self.validations += 1
        return True


class _Aq6PostMergeProvider(PostMergeProvider):
    domain = AQ6_DOMAIN

    def verify_candidate(self, worktree, candidate, contract_id, evidence_root):
        assert contract_id == "synthetic.post-merge.v1"
        head = git(worktree, "rev-parse", "HEAD")
        content = (worktree / "config/promotion.json").read_text(encoding="utf-8")
        expected = (
            self.expected_promoted_content
            if head == self.promoted_sha
            else "{}\n"
        )
        assert content == expected
        self.verify_calls.append((candidate["candidate_id"], head, contract_id))
        outcome = self.outcomes["promoted" if head == self.promoted_sha else "baseline"]
        return {
            "outcome": outcome,
            "evidence_fingerprint": fingerprint(
                {
                    "candidate": candidate["candidate_id"],
                    "content": content,
                    "outcome": outcome,
                }
            ),
            "reason_code": None if outcome == "PASS" else "synthetic_verification_failed",
        }


def _build_aq6_cycle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    theory_fixture_path: Path | None = None,
):
    """Wire the generic S9 composition with AQ6 domain-owned inputs only."""
    monkeypatch.setattr(closed_cycle.tempfile, "gettempdir", lambda: str(tmp_path))
    state_path = tmp_path / "host" / "quality-state.json"
    state_path.parent.mkdir()
    save_state_atomic(state_path, _fresh_aq6_state())
    attempt_path = tmp_path / "host" / "cycle-attempt.json"
    repo_root = tmp_path / "promotion-repo"
    s7_cache: dict[str, Any] = {}
    s8_cache: dict[str, Any] = {}
    repo_holder: dict[str, Any] = {}
    counters = {"calibration": 0, "locked": 0}
    observed_headless: list[dict[str, Any]] = []

    def calibration_inputs(*, state_path, state):
        counters["calibration"] += 1
        candidate_id = state["active_candidate"]["candidate_id"]
        baseline_id = state["baseline_candidate"]["candidate_id"]
        work = tmp_path / "domain" / Path(state_path).stem / f"{state['generation']}-{candidate_id}"
        work.mkdir(parents=True, exist_ok=True)
        output_path = work / "aq6-compare.json"
        request = _aq6_request(
            operation="compare",
            partition_role="calibration",
            partition_id=AQ6_PARTITION_ID,
            candidate_id=candidate_id,
            baseline_id=baseline_id,
        )

        return {
            "request": request,
            "bind_kwargs": _bind_kwargs(output_path, theory_fixture_path),
            "provider": _provider(),
            "decision_provider": _aq6_decision(
                output_path=output_path,
                candidate_id=candidate_id,
                baseline_id=baseline_id,
                locked=False,
                observed=observed_headless,
            ),
            "decision_provider_id": "aq6-s10-ranking-policy-v1",
        }

    def locked_inputs(*, state_path, state):
        counters["locked"] += 1
        candidate_id = state["active_candidate"]["candidate_id"]
        baseline_id = state["baseline_candidate"]["candidate_id"]
        work = tmp_path / "locked-domain"
        work.mkdir(exist_ok=True)
        output_path = work / "aq6-locked-compare.json"
        request = _aq6_request(
            operation="locked_evaluation",
            partition_role="holdout",
            partition_id="aq6-s10-holdout",
            candidate_id=candidate_id,
            baseline_id=baseline_id,
        )

        return {
            "request": request,
            "bind_kwargs": {"output_path": str(output_path)},
            "provider": _provider(),
            "decision_provider": _aq6_decision(
                output_path=output_path,
                candidate_id=candidate_id,
                baseline_id=baseline_id,
                locked=True,
                observed=observed_headless,
            ),
            "decision_provider_id": "aq6-s10-ranking-policy-v1",
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
            inputs = _promotion_payload(
                locked_result["current_candidate"]["candidate_id"],
                locked_result["current_candidate"]["config_fingerprint"],
            )
            provider = _Aq6PromotionProvider(inputs)

            class _CycleHost(S7Host):
                simulation_only = True

                def merge(self, number, expected_head_sha, method):
                    super().merge(number, expected_head_sha, method)
                    git(repo_root, "update-ref", "refs/remotes/origin/main", expected_head_sha)

            host = _CycleHost(repo_root, base)
            manifest = seal_s7(
                {
                    "document_type": "sample-brain.analysis-promotion-manifest.v1",
                    "artifact_version": "1.0.0",
                    "domain": locked_result["domain"],
                    "baseline_candidate": locked_result["baseline_candidate"],
                    "current_candidate": locked_result["current_candidate"],
                    "locked_result_fingerprint": locked_result["result_fingerprint"],
                    "decision_fingerprint": locked_result["decision"]["decision_fingerprint"],
                    "evidence_fingerprint": locked_result["decision"]["evidence"][
                        "evidence_fingerprint"
                    ],
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
                {
                    "provider": provider,
                    "host": host,
                    "base": base,
                    "manifest": manifest,
                    "repository": repository,
                    "worktree_root": tmp_path / "promotion-worktrees",
                    "attempt_root": tmp_path / "promotion-attempts",
                }
            )
            repo_holder["repo_root"] = repo_root
        return {key: value for key, value in s7_cache.items() if key != "base"}

    def post_merge_inputs(*, locked_result, promotion_manifest, promotion_attempt):
        provider = s8_cache.get("provider")
        if provider is None:
            provider = _Aq6PostMergeProvider()
            s8_cache["provider"] = provider
        provider.promoted_sha = promotion_attempt["merge_sha"]
        provider.expected_promoted_content = s7_cache["provider"].payload[
            "config/promotion.json"
        ]
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
                "evidence_fingerprint": locked_result["decision"]["evidence"][
                    "evidence_fingerprint"
                ],
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
                            "before_sha256": sha(
                                s7_cache["provider"].payload["config/promotion.json"]
                            ),
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

        class _CyclePostMergeHost(S8Host):
            simulation_only = True

        return {
            "plan": plan,
            "provider": provider,
            "repository": s7_cache["repository"],
            "host": _CyclePostMergeHost(repo_holder["repo_root"], promotion_attempt),
            "verification_root": tmp_path / "verification",
            "worktree_root": tmp_path / "s8-worktrees",
            "attempt_root": tmp_path / "s8-attempts",
            "baseline_state_path": tmp_path / "accepted-baseline.json",
        }

    return {
        "state_path": state_path,
        "attempt_path": attempt_path,
        "calibration_inputs": calibration_inputs,
        "locked_inputs": locked_inputs,
        "promotion_inputs": promotion_inputs,
        "post_merge_inputs": post_merge_inputs,
        "counters": counters,
        "s7_cache": s7_cache,
        "s8_cache": s8_cache,
        "observed_headless": observed_headless,
    }


def test_aq6_cycle_composes_generic_s5_s6_with_simulated_s7_s8_and_continuation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second-domain proof: the same generic composition runs for AQ6."""
    cycle = _build_aq6_cycle(tmp_path, monkeypatch)

    result = run_quality_cycle(
        state_path=cycle["state_path"],
        attempt_path=cycle["attempt_path"],
        calibration_inputs=cycle["calibration_inputs"],
        locked_inputs=cycle["locked_inputs"],
        promotion_inputs=cycle["promotion_inputs"],
        post_merge_inputs=cycle["post_merge_inputs"],
    )

    assert result["outcome_token"] == "AUTONOMOUS_QUALITY_LOOP_FIRST_CLOSED_CYCLE"
    assert result["production_authorized"] is False
    assert result["domain"] == AQ6_DOMAIN
    assert result["final_candidate"]["candidate_id"] == JUSTIFIED_ID
    assert result["final_candidate"]["config_fingerprint"] == _config_fp(JUSTIFIED_ID)

    # Deterministic iteration over the bounded AQ6 search space.
    assert tuple(result["candidate_history"]) == EXPECTED_ORDER

    # Exactly one locked TEST/HOLDOUT transition after the freeze.
    assert cycle["counters"]["locked"] == 1

    # Simulated repository governance only.
    assert cycle["s7_cache"]["host"].creates == 1
    assert cycle["s7_cache"]["host"].merges == 1
    assert result["evidence_classifications"]["repository_governance"] == (
        "INFRASTRUCTURE_SIMULATION"
    )
    assert result["evidence_classifications"]["domain_execution"] == (
        "REAL_SANITIZED_DOMAIN_EXECUTION"
    )

    # S8 acceptance plus LAST_KNOWN_GOOD lineage for the accepted candidate.
    assert result["accepted_baseline"]["candidate"]["candidate_id"] == JUSTIFIED_ID
    assert result["last_known_good"] is not None

    # Continuation from the accepted generation.
    assert result["continuation_ref"]["next_action"] == "continue_calibration"
    assert result["continuation_ref"]["candidate"]["candidate_id"] == BASELINE_ID


def test_aq6_freeze_binds_exact_candidate_config_and_search_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle = _build_aq6_cycle(tmp_path, monkeypatch)

    run_quality_cycle(
        state_path=cycle["state_path"],
        attempt_path=cycle["attempt_path"],
        calibration_inputs=cycle["calibration_inputs"],
        locked_inputs=cycle["locked_inputs"],
        promotion_inputs=cycle["promotion_inputs"],
        post_merge_inputs=cycle["post_merge_inputs"],
    )

    state = load_state(cycle["state_path"])
    provider = _provider()
    assert state["loop_status"] == "frozen"
    assert state["last_decision"]["next_action"] == "freeze_candidate"
    assert state["active_candidate"]["candidate_id"] == JUSTIFIED_ID
    assert state["active_candidate"]["config_fingerprint"] == _config_fp(JUSTIFIED_ID)
    assert state["search_space_id"] == provider.search_space_id
    assert state["search_space_version"] == provider.search_space_version
    assert state["search_space_fingerprint"] == provider.search_space_fingerprint()


def test_aq6_replay_does_not_duplicate_advancement_or_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle = _build_aq6_cycle(tmp_path, monkeypatch)
    inputs = {
        "state_path": cycle["state_path"],
        "attempt_path": cycle["attempt_path"],
        "calibration_inputs": cycle["calibration_inputs"],
        "locked_inputs": cycle["locked_inputs"],
        "promotion_inputs": cycle["promotion_inputs"],
        "post_merge_inputs": cycle["post_merge_inputs"],
    }

    first = run_quality_cycle(**inputs)
    second = run_quality_cycle(**inputs)

    assert second["result_fingerprint"] == first["result_fingerprint"]
    assert second["candidate_history"] == first["candidate_history"]
    assert cycle["counters"]["locked"] == 1
    assert cycle["s7_cache"]["host"].creates == 1
    assert cycle["s7_cache"]["host"].merges == 1
    assert cycle["s7_cache"]["provider"].calls == 1


def test_aq6_promotion_guard_rejects_non_simulation_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle = _build_aq6_cycle(tmp_path, monkeypatch)

    def unsafe_promotion_inputs(*, locked_result):
        inputs = dict(cycle["promotion_inputs"](locked_result=locked_result))
        inputs["repository"].simulation_only = False
        return inputs

    with pytest.raises(AnalysisQualityClosedCycleError, match="simulation-only"):
        run_quality_cycle(
            state_path=cycle["state_path"],
            attempt_path=cycle["attempt_path"],
            calibration_inputs=cycle["calibration_inputs"],
            locked_inputs=cycle["locked_inputs"],
            promotion_inputs=unsafe_promotion_inputs,
            post_merge_inputs=cycle["post_merge_inputs"],
        )


def test_aq6_preference_stays_not_required_and_no_pseudo_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle = _build_aq6_cycle(tmp_path, monkeypatch)

    result = run_quality_cycle(
        state_path=cycle["state_path"],
        attempt_path=cycle["attempt_path"],
        calibration_inputs=cycle["calibration_inputs"],
        locked_inputs=cycle["locked_inputs"],
        promotion_inputs=cycle["promotion_inputs"],
        post_merge_inputs=cycle["post_merge_inputs"],
    )

    assert result["production_authorized"] is False
    assert result["evidence_classifications"]["production_quality_claim"] is False

    # The real AQ6 execution keeps the preference plane NOT_REQUIRED and never
    # turns it into a fabricated ranking/decision signal.
    assert cycle["observed_headless"]
    for headless_result in cycle["observed_headless"]:
        planes = headless_result["domain_planes"]
        assert planes["preference"]["status"] == "NOT_REQUIRED"
        assert planes["preference"]["signal"] is None
        assert planes["ranking"]["mixed_into_aggregate_score"] is False
        assert planes["theory"]["hard_gate"] is True


def test_domains_differ_only_through_domain_owned_inputs() -> None:
    assert registered_search_space_domains() == ("aq1.tempo", "aq6.ranking")
    aq6 = default_search_space_provider("aq6.ranking")
    assert isinstance(aq6, Aq6HarmonicSearchSpaceProvider)
    assert aq6.search_space_id != default_search_space_provider(
        "aq1.tempo"
    ).search_space_id


def test_unknown_domain_fails_closed_in_the_generic_resolver() -> None:
    from src.analysis_quality_loop_supervisor import (
        AnalysisQualityLoopSupervisorError,
        _default_provider,
    )

    with pytest.raises(AnalysisQualityLoopSupervisorError, match="no default"):
        _default_provider("aq9.unknown")


# ---------------------------------------------------------------------------
# 5 — the theory hard gate cannot be averaged away into a ready outcome
# ---------------------------------------------------------------------------


def test_aq6_theory_gate_failure_blocks_the_reproducible_exit(tmp_path: Path) -> None:
    """Real AQ6 execution: a failing theory gate removes the reproducible exit."""
    import copy

    from src.analysis_headless_run import bind_adapter
    from src.aq6_harmonic_ranking_candidate_compare import is_reproducible

    output_path = tmp_path / "aq6-compare.json"
    adapter = bind_adapter(AQ6_ADAPTER_ID, output_path=output_path)
    request = _aq6_request(
        operation="compare",
        partition_role="calibration",
        partition_id=AQ6_PARTITION_ID,
        candidate_id=BASELINE_ID,
        baseline_id=BASELINE_ID,
    )

    result = adapter.run(request)

    assert result["run_status"] == "completed"
    draft = json.loads(output_path.read_text(encoding="utf-8"))
    assert is_reproducible(draft) is True

    doctored = copy.deepcopy(draft)
    doctored["candidates"][0]["theory_gate"]["pass"] = False

    assert is_reproducible(doctored) is False


def test_aq6_theory_gate_failure_holds_the_cycle_without_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A broken theory truth table can never reach a ready/promotion outcome."""
    truth_table_path = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "fixtures"
        / "aq6_harmonic_theory"
        / "truth_table_v1.json"
    )
    truth_table = json.loads(truth_table_path.read_text(encoding="utf-8"))
    truth_table["cells"][0]["relation"] = "transpose"
    doctored = tmp_path / "doctored_truth_table.json"
    doctored.write_text(
        json.dumps(truth_table, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    cycle = _build_aq6_cycle(tmp_path, monkeypatch, theory_fixture_path=doctored)

    result = run_quality_cycle(
        state_path=cycle["state_path"],
        attempt_path=cycle["attempt_path"],
        calibration_inputs=cycle["calibration_inputs"],
        locked_inputs=cycle["locked_inputs"],
        promotion_inputs=cycle["promotion_inputs"],
        post_merge_inputs=cycle["post_merge_inputs"],
    )

    assert result["status"] == "held"
    assert result["reason"] == "calibration_decision_not_actionable"
    assert cycle["observed_headless"]
    assert all(
        headless_result["run_status"] == "controlled_failure"
        for headless_result in cycle["observed_headless"]
    )
    assert cycle["s7_cache"] == {} or cycle["s7_cache"]["host"].creates == 0


# ---------------------------------------------------------------------------
# 9 — the locked evaluation stays bound to the frozen candidate
# ---------------------------------------------------------------------------


def test_aq6_locked_evaluation_rejects_a_candidate_that_is_not_frozen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle = _build_aq6_cycle(tmp_path, monkeypatch)

    def tampered_locked_inputs(*, state_path, state):
        inputs = dict(cycle["locked_inputs"](state_path=state_path, state=state))
        inputs["request"] = _aq6_request(
            operation="locked_evaluation",
            partition_role="holdout",
            partition_id="aq6-s10-holdout",
            candidate_id=BASELINE_ID,
            baseline_id=state["baseline_candidate"]["candidate_id"],
        )
        return inputs

    with pytest.raises(Exception, match="frozen identity mismatch"):
        run_quality_cycle(
            state_path=cycle["state_path"],
            attempt_path=cycle["attempt_path"],
            calibration_inputs=cycle["calibration_inputs"],
            locked_inputs=tampered_locked_inputs,
            promotion_inputs=cycle["promotion_inputs"],
            post_merge_inputs=cycle["post_merge_inputs"],
        )


# ---------------------------------------------------------------------------
# 11 — the simulated repository guard still rejects real Sample Brain promotion
# ---------------------------------------------------------------------------


def test_aq6_promotion_guard_rejects_real_sample_brain_self_promotion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cycle = _build_aq6_cycle(tmp_path, monkeypatch)

    def unsafe_promotion_inputs(*, locked_result):
        inputs = dict(cycle["promotion_inputs"](locked_result=locked_result))
        manifest = dict(inputs["manifest"])
        manifest["repository_id"] = "jannekbuengener/sample-brain"
        inputs["manifest"] = manifest
        return inputs

    with pytest.raises(AnalysisQualityClosedCycleError, match="self-promotion"):
        run_quality_cycle(
            state_path=cycle["state_path"],
            attempt_path=cycle["attempt_path"],
            calibration_inputs=cycle["calibration_inputs"],
            locked_inputs=cycle["locked_inputs"],
            promotion_inputs=unsafe_promotion_inputs,
            post_merge_inputs=cycle["post_merge_inputs"],
        )
