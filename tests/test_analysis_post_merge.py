"""S8 contract: merged promotion -> verified baseline or governed forward repair."""

from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_locked_holdout import run_locked_holdout_transition
from src.analysis_promotion import GitRepository, run_promotion
from tests.test_analysis_locked_holdout import frozen  # noqa: F401
from tests.test_analysis_promotion import Host as S7Host
from tests.test_analysis_promotion import Provider as S7Provider
from tests.test_analysis_promotion import seal as seal_s7


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def seal_plan(plan: dict) -> dict:
    recovery = plan["recovery"]
    recovery["change_fingerprint"] = fingerprint(recovery["changes"])
    recovery["policy_fingerprint"] = fingerprint(recovery["policy"])
    plan.pop("plan_fingerprint", None)
    plan["plan_fingerprint"] = fingerprint(plan)
    return plan


class PostMergeProvider:
    domain = "aq1.tempo"
    verification_id = "synthetic.post-merge"
    verification_version = "1.0.0"
    recovery_materializer_id = "synthetic.recovery"
    recovery_materializer_version = "1.0.0"

    def __init__(self):
        self.outcomes: dict[str, str] = {"baseline": "PASS", "promoted": "PASS"}
        self.verify_calls: list[tuple[str, str, str]] = []
        self.recovery_calls = 0
        self.recovery_validations = 0
        self.recovery_ok = True
        self.promoted_sha: str | None = None

    def verify_candidate(self, worktree, candidate, contract_id, evidence_root):
        assert contract_id == "synthetic.post-merge.v1"
        candidate_id = candidate["candidate_id"]
        head = git(Path(worktree), "rev-parse", "HEAD")
        content = (Path(worktree) / "config/promotion.json").read_text(encoding="utf-8")
        expected = '{"candidate":"frozen"}\n' if head == self.promoted_sha else "{}\n"
        assert content == expected
        self.verify_calls.append((candidate_id, head, contract_id))
        outcome = self.outcomes["promoted" if head == self.promoted_sha else "baseline"]
        return {
            "outcome": outcome,
            "evidence_fingerprint": fingerprint(
                {"candidate": candidate_id, "content": content, "outcome": outcome}
            ),
            "reason_code": None
            if outcome == "PASS"
            else "synthetic_verification_failed",
        }

    def validate_recovery_plan(self, plan, source):
        return self.recovery_ok

    def materialize_recovery(self, inputs):
        assert inputs == {"mode": "last-known-good"}
        self.recovery_calls += 1
        return {"config/promotion.json": "{}\n"}

    def validate_recovery_candidate(self, worktree, contract_id):
        assert contract_id == "synthetic.recovery.v1"
        assert (Path(worktree) / "config/promotion.json").read_text(
            encoding="utf-8"
        ) == "{}\n"
        self.recovery_validations += 1
        return True


class S8Host:
    repository_id = "example/repo"

    def __init__(self, repository: Path, s7_attempt: dict):
        self.repository = repository
        self.main = s7_attempt["merge_sha"]
        self.s7_attempt = s7_attempt
        self.required = [{"name": "required", "app_id": 15368}]
        self.checks = [{"name": "required", "app_id": 15368, "state": "SUCCESS"}]
        self.recovery_pr = None
        self.pushes = 0
        self.creates = 0
        self.merges = 0
        self.mergeable = True
        self.feedback = []
        self.threads = 0
        self.blocking = False
        self.error = None

    def main_sha(self):
        if self.error:
            from src.analysis_promotion_host import InfrastructureError

            raise InfrastructureError("sanitized host failure")
        return self.main

    def policy(self):
        return {
            "required_checks": copy.deepcopy(self.required),
            "merge_methods": ["squash", "rebase"],
            "required_approvals": 0,
        }

    def verify_merge(self, number, head_sha, merge_sha):
        if number == self.s7_attempt["pr_number"]:
            return (
                head_sha == self.s7_attempt["head_sha"]
                and merge_sha == self.s7_attempt["merge_sha"]
                and git(
                    self.repository,
                    "merge-base",
                    "--is-ancestor",
                    merge_sha,
                    "refs/remotes/origin/main",
                )
                == ""
            )
        return bool(
            self.recovery_pr
            and self.recovery_pr.get("merged")
            and self.recovery_pr["head_sha"] == head_sha
            and self.recovery_pr["merge_sha"] == merge_sha
            and self.main == merge_sha
        )

    def pushed_head(self, branch):
        return (
            self.recovery_pr["head_sha"] if self.pushes and self.recovery_pr else None
        )

    def push(self, repository, branch, head_sha):
        assert repository.head(branch) == head_sha
        self.pushes += 1

    def find_pr(self, branch):
        return copy.deepcopy(self.recovery_pr)

    def create_bounded_pr(self, branch, head_sha, base_sha, *, title, body):
        self.creates += 1
        self.recovery_pr = {
            "number": 8,
            "branch": branch,
            "base": "main",
            "head_sha": head_sha,
            "repository_id": self.repository_id,
        }
        return copy.deepcopy(self.recovery_pr)

    def snapshot(self, number):
        assert self.recovery_pr and number == self.recovery_pr["number"]
        return {
            **self.recovery_pr,
            "open": not self.recovery_pr.get("merged", False),
            "draft": False,
            "mergeable": self.mergeable,
            "checks": copy.deepcopy(self.checks),
            "feedback": copy.deepcopy(self.feedback),
            "unresolved_threads": self.threads,
            "blocking_review": self.blocking,
            "approvals": 0,
            "merged": self.recovery_pr.get("merged", False),
            "merge_sha": self.recovery_pr.get("merge_sha"),
        }

    def merge(self, number, expected_head_sha, method):
        assert self.recovery_pr and number == self.recovery_pr["number"]
        assert method == "squash"
        assert expected_head_sha == self.recovery_pr["head_sha"]
        self.merges += 1
        self.recovery_pr.update(merged=True, merge_sha=expected_head_sha)
        self.main = expected_head_sha
        git(
            self.repository, "update-ref", "refs/remotes/origin/main", expected_head_sha
        )


@pytest.fixture
def s8_setup(tmp_path, frozen):
    frozen.update(
        decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
        next_action="handoff_promotion_controller",
    )
    locked = run_locked_holdout_transition(**frozen)["result"]

    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Synthetic Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    (root / "config").mkdir()
    (root / "config/promotion.json").write_text("{}\n", encoding="utf-8", newline="\n")
    git(root, "add", "config/promotion.json")
    git(root, "commit", "-m", "synthetic baseline")
    base = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", base)
    git(root, "remote", "add", "origin", "https://github.com/example/repo.git")

    promotion_provider = S7Provider()
    promotion_manifest = seal_s7(
        {
            "document_type": "sample-brain.analysis-promotion-manifest.v1",
            "artifact_version": "1.0.0",
            "domain": locked["domain"],
            "baseline_candidate": locked["baseline_candidate"],
            "current_candidate": locked["current_candidate"],
            "locked_result_fingerprint": locked["result_fingerprint"],
            "decision_fingerprint": locked["decision"]["decision_fingerprint"],
            "evidence_fingerprint": locked["decision"]["evidence"][
                "evidence_fingerprint"
            ],
            "expected_base_sha": base,
            "repository_id": "example/repo",
            "allowed_paths": ["config/promotion.json"],
            "forbidden_paths": ["private"],
            "materializer": {
                "id": promotion_provider.materializer_id,
                "version": promotion_provider.materializer_version,
                "inputs": {"mode": "frozen"},
            },
            "changes": {
                "config/promotion.json": {
                    "before_sha256": sha("{}\n"),
                    "after_sha256": sha('{"candidate":"frozen"}\n'),
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
    promotion_attempt_root = tmp_path / "promotion-attempts"
    promotion_host = S7Host(root, base)
    promotion_attempt = run_promotion(
        source_state_path=frozen["state_path"],
        manifest=promotion_manifest,
        provider=promotion_provider,
        repository=GitRepository(root),
        host=promotion_host,
        worktree_root=tmp_path / "promotion-worktrees",
        attempt_root=promotion_attempt_root,
    )
    assert promotion_attempt["status"] == "merged"
    git(root, "update-ref", "refs/remotes/origin/main", promotion_attempt["merge_sha"])

    provider = PostMergeProvider()
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
            "domain": locked["domain"],
            "promotion_manifest_fingerprint": promotion_manifest[
                "manifest_fingerprint"
            ],
            "promotion_attempt_fingerprint": promotion_attempt["state_fingerprint"],
            "locked_result_fingerprint": locked["result_fingerprint"],
            "decision_fingerprint": locked["decision"]["decision_fingerprint"],
            "evidence_fingerprint": locked["decision"]["evidence"][
                "evidence_fingerprint"
            ],
            "merge_sha": promotion_attempt["merge_sha"],
            "previous_baseline_candidate": locked["baseline_candidate"],
            "promoted_candidate": locked["current_candidate"],
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
                        "before_sha256": sha('{"candidate":"frozen"}\n'),
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
    promotion_attempt_path = next(promotion_attempt_root.rglob("attempt.json"))
    return {
        "source_state_path": frozen["state_path"],
        "promotion_manifest": promotion_manifest,
        "promotion_provider": promotion_provider,
        "promotion_attempt_path": promotion_attempt_path,
        "plan": plan,
        "provider": provider,
        "repository": GitRepository(root),
        "host": S8Host(root, promotion_attempt),
        "verification_root": tmp_path / "verification",
        "worktree_root": tmp_path / "s8-worktrees",
        "attempt_root": tmp_path / "s8-attempts",
        "baseline_state_path": tmp_path / "accepted-baseline.json",
    }


def run_s8(setup, **kwargs):
    from src.analysis_post_merge import run_post_merge

    return run_post_merge(**setup, **kwargs)


def baseline_state(setup):
    from src.analysis_post_merge import load_baseline_lineage

    return load_baseline_lineage(setup["baseline_state_path"])


def test_success_verifies_exact_merge_and_atomically_accepts_new_baseline(s8_setup):
    result = run_s8(s8_setup)
    assert result["status"] == "accepted"
    assert result["merge_sha"] == s8_setup["plan"]["merge_sha"]
    assert result["production_authorized"] is False
    state = baseline_state(s8_setup)
    assert state["generation"] == 1
    assert state["current"]["candidate"] == s8_setup["plan"]["promoted_candidate"]
    assert state["current"]["repository_sha"] == s8_setup["plan"]["merge_sha"]
    assert (
        state["last_known_good"]["candidate"]
        == s8_setup["plan"]["previous_baseline_candidate"]
    )
    assert (
        state["last_known_good"]["repository_sha"]
        == s8_setup["promotion_manifest"]["expected_base_sha"]
    )
    assert len(s8_setup["provider"].verify_calls) == 2
    assert s8_setup["host"].creates == s8_setup["host"].merges == 0


def test_success_replay_is_idempotent_and_does_not_verify_or_advance_twice(s8_setup):
    first = run_s8(s8_setup)
    calls = list(s8_setup["provider"].verify_calls)
    second = run_s8(s8_setup)
    assert second == first
    assert s8_setup["provider"].verify_calls == calls
    assert baseline_state(s8_setup)["generation"] == 1


@pytest.mark.parametrize(
    "outcome", ["HOLD", "CONTROLLED_FAILURE", "FORBIDDEN_REGRESSION"]
)
def test_nonpass_promoted_candidate_is_never_accepted_and_recovers_lkg(
    s8_setup, outcome
):
    promoted = s8_setup["plan"]["promoted_candidate"]["candidate_id"]
    s8_setup["provider"].outcomes["promoted"] = outcome
    result = run_s8(s8_setup)
    assert result["status"] == "recovered"
    state = baseline_state(s8_setup)
    assert (
        state["current"]["candidate"] == s8_setup["plan"]["previous_baseline_candidate"]
    )
    assert result["invalid_promotion"] is True
    assert result["recovery"]["merge_sha"] is not None
    assert s8_setup["host"].creates == s8_setup["host"].merges == 1
    assert (
        s8_setup["provider"].recovery_calls
        == s8_setup["provider"].recovery_validations
        == 1
    )
    assert (
        s8_setup["provider"].verify_calls[-1][0]
        == s8_setup["plan"]["previous_baseline_candidate"]["candidate_id"]
    )


def test_failed_baseline_bootstrap_holds_without_automatic_recovery(s8_setup):
    baseline = s8_setup["plan"]["previous_baseline_candidate"]["candidate_id"]
    s8_setup["provider"].outcomes["baseline"] = "HOLD"
    result = run_s8(s8_setup)
    assert result["status"] == "hold"
    assert result["reason"] == "last_known_good_not_verified"
    assert not s8_setup["baseline_state_path"].exists()
    assert s8_setup["host"].creates == s8_setup["host"].merges == 0


@pytest.mark.parametrize(
    "mutation",
    ["attempt", "merge", "candidate", "evidence", "plan_fingerprint", "recovery_path"],
)
def test_lineage_and_plan_mismatches_fail_before_domain_verification(
    s8_setup, mutation
):
    if mutation == "attempt":
        value = json.loads(Path(s8_setup["promotion_attempt_path"]).read_text())
        value["merge_sha"] = "a" * 40
        Path(s8_setup["promotion_attempt_path"]).write_text(json.dumps(value))
    elif mutation == "merge":
        s8_setup["plan"]["merge_sha"] = "b" * 40
        seal_plan(s8_setup["plan"])
    elif mutation == "candidate":
        s8_setup["plan"]["promoted_candidate"] = {
            "candidate_id": "wrong",
            "config_fingerprint": "c" * 64,
        }
        seal_plan(s8_setup["plan"])
    elif mutation == "evidence":
        s8_setup["plan"]["evidence_fingerprint"] = "d" * 64
        seal_plan(s8_setup["plan"])
    elif mutation == "plan_fingerprint":
        s8_setup["plan"]["plan_fingerprint"] = "e" * 64
    else:
        s8_setup["plan"]["recovery"]["allowed_paths"] = [".github/workflows/bad.yml"]
        seal_plan(s8_setup["plan"])
    with pytest.raises(ValueError):
        run_s8(s8_setup)
    assert s8_setup["provider"].verify_calls == []


def test_live_main_must_contain_s7_merge_before_verification(s8_setup):
    s8_setup["host"].main = s8_setup["promotion_manifest"]["expected_base_sha"]
    result = run_s8(s8_setup)
    assert result["status"] == "hold"
    assert result["reason"] == "promotion_merge_not_live"
    assert s8_setup["provider"].verify_calls == []


def test_stale_baseline_generation_cannot_be_overwritten(s8_setup):
    first = run_s8(s8_setup)
    assert first["status"] == "accepted"
    other = copy.deepcopy(baseline_state(s8_setup))
    other["generation"] += 1
    other.pop("state_fingerprint")
    from src.analysis_post_merge import save_baseline_lineage

    save_baseline_lineage(s8_setup["baseline_state_path"], other)
    attempt = next(Path(s8_setup["attempt_root"]).rglob("attempt.json"))
    attempt.unlink()
    with pytest.raises(ValueError, match="baseline|generation|lineage"):
        run_s8(s8_setup)


def test_recovery_requires_failed_merge_still_be_exact_live_main(s8_setup):
    promoted = s8_setup["plan"]["promoted_candidate"]["candidate_id"]
    s8_setup["provider"].outcomes["promoted"] = "FORBIDDEN_REGRESSION"
    original = s8_setup["provider"].verify_candidate

    def move_main_after_promoted(*args, **kwargs):
        value = original(*args, **kwargs)
        candidate = args[1]
        if candidate["candidate_id"] == promoted:
            s8_setup["host"].main = "f" * 40
        return value

    s8_setup["provider"].verify_candidate = move_main_after_promoted
    result = run_s8(s8_setup)
    assert result["status"] == "hold"
    assert result["reason"] == "recovery_base_moved"
    assert s8_setup["host"].creates == 0


def test_recovery_required_check_must_be_success(s8_setup):
    promoted = s8_setup["plan"]["promoted_candidate"]["candidate_id"]
    s8_setup["provider"].outcomes["promoted"] = "HOLD"
    s8_setup["host"].checks[0]["state"] = "PENDING"
    first = run_s8(s8_setup)
    assert first["status"] == "hold"
    assert first["reason"] == "recovery_final_head_gates_not_satisfied"
    assert s8_setup["host"].merges == 0
    s8_setup["host"].checks[0]["state"] = "SUCCESS"
    assert run_s8(s8_setup)["status"] == "recovered"
    assert s8_setup["host"].creates == s8_setup["host"].merges == 1


def test_recovery_replay_does_not_create_duplicate_pr_or_merge(s8_setup):
    promoted = s8_setup["plan"]["promoted_candidate"]["candidate_id"]
    s8_setup["provider"].outcomes["promoted"] = "CONTROLLED_FAILURE"
    first = run_s8(s8_setup)
    assert first["status"] == "recovered"
    second = run_s8(s8_setup)
    assert second == first
    assert s8_setup["host"].creates == s8_setup["host"].merges == 1
    assert s8_setup["provider"].recovery_calls == 1


def test_host_failure_is_redacted_and_resumable(s8_setup):
    s8_setup["host"].error = "token=never-persist C:/private"
    result = run_s8(s8_setup)
    assert result["status"] == "infrastructure_hold"
    assert "never-persist" not in json.dumps(result)
    assert "C:/private" not in json.dumps(result)
    s8_setup["host"].error = None
    assert run_s8(s8_setup)["status"] == "accepted"


def test_portable_s8_state_contains_no_host_paths(s8_setup):
    result = run_s8(s8_setup)
    raw = json.dumps(result)
    for path in (
        s8_setup["verification_root"],
        s8_setup["worktree_root"],
        s8_setup["attempt_root"],
        s8_setup["repository"].path,
    ):
        assert str(path) not in raw


def test_recovery_payload_cannot_escape_allowlist_or_leak_secret(s8_setup):
    promoted = s8_setup["plan"]["promoted_candidate"]["candidate_id"]
    s8_setup["provider"].outcomes["promoted"] = "HOLD"
    s8_setup["provider"].materialize_recovery = lambda inputs: {
        "config/promotion.json": "token=do-not-publish"
    }
    result = run_s8(s8_setup)
    assert result["status"] == "controlled_failure"
    assert s8_setup["host"].pushes == s8_setup["host"].creates == 0


def test_restart_reconciles_bootstrap_baseline_written_before_attempt_phase_commit(
    s8_setup, monkeypatch
):
    import src.analysis_post_merge as post_merge

    real_save = post_merge._save_attempt
    interrupted = {"done": False}

    def crash_after_baseline_write(path, state):
        if state.get("phase") == "baseline_ready" and not interrupted["done"]:
            interrupted["done"] = True
            raise KeyboardInterrupt()
        return real_save(path, state)

    monkeypatch.setattr(post_merge, "_save_attempt", crash_after_baseline_write)
    with pytest.raises(KeyboardInterrupt):
        run_s8(s8_setup)
    assert s8_setup["baseline_state_path"].exists()

    monkeypatch.setattr(post_merge, "_save_attempt", real_save)
    result = run_s8(s8_setup)
    assert result["status"] == "accepted"
    assert baseline_state(s8_setup)["generation"] == 1


def test_restart_reconciles_accepted_baseline_written_before_attempt_commit(
    s8_setup, monkeypatch
):
    import src.analysis_post_merge as post_merge

    real_save = post_merge._save_attempt
    interrupted = {"done": False}

    def crash_after_acceptance_write(path, state):
        if state.get("phase") == "accepted" and not interrupted["done"]:
            interrupted["done"] = True
            raise KeyboardInterrupt()
        return real_save(path, state)

    monkeypatch.setattr(post_merge, "_save_attempt", crash_after_acceptance_write)
    with pytest.raises(KeyboardInterrupt):
        run_s8(s8_setup)
    accepted = baseline_state(s8_setup)
    assert accepted["generation"] == 1

    monkeypatch.setattr(post_merge, "_save_attempt", real_save)
    result = run_s8(s8_setup)
    assert result["status"] == "accepted"
    assert baseline_state(s8_setup)["generation"] == 1


def test_lost_recovery_merge_response_reconciles_without_duplicate_merge(s8_setup):
    from src.analysis_promotion_host import InfrastructureError

    s8_setup["provider"].outcomes["promoted"] = "FORBIDDEN_REGRESSION"
    host = s8_setup["host"]
    real_merge = host.merge
    lost = {"done": False}

    def lose_response(*args):
        real_merge(*args)
        if not lost["done"]:
            lost["done"] = True
            raise InfrastructureError("lost recovery merge response")

    host.merge = lose_response
    first = run_s8(s8_setup)
    assert first["status"] == "infrastructure_hold"
    assert host.merges == 1

    host.merge = real_merge
    second = run_s8(s8_setup)
    assert second["status"] == "recovered"
    assert host.merges == 1


def test_recovery_rebinds_verified_baseline_authority_to_recovery_merge_sha(s8_setup):
    s8_setup["provider"].outcomes["promoted"] = "FORBIDDEN_REGRESSION"
    original_base = s8_setup["promotion_manifest"]["expected_base_sha"]

    result = run_s8(s8_setup)
    assert result["status"] == "recovered"
    recovery_sha = result["recovery"]["merge_sha"]

    state = baseline_state(s8_setup)
    assert state["generation"] == 1
    assert (
        state["current"]["candidate"] == s8_setup["plan"]["previous_baseline_candidate"]
    )
    assert state["current"]["repository_sha"] == recovery_sha
    assert state["last_known_good"] is not None
    assert (
        state["last_known_good"]["candidate"]
        == s8_setup["plan"]["previous_baseline_candidate"]
    )
    assert state["last_known_good"]["repository_sha"] == original_base
    assert state["current"]["verification_fingerprints"] == [
        ref["verification_fingerprint"] for ref in result["recovery_verification_refs"]
    ]


def test_restart_reconciles_recovered_baseline_written_before_attempt_commit(
    s8_setup, monkeypatch
):
    import src.analysis_post_merge as post_merge

    s8_setup["provider"].outcomes["promoted"] = "FORBIDDEN_REGRESSION"
    real_save = post_merge._save_attempt
    interrupted = {"done": False}

    def crash_after_recovered_baseline_write(path, state):
        if state.get("phase") == "recovered" and not interrupted["done"]:
            interrupted["done"] = True
            raise KeyboardInterrupt()
        return real_save(path, state)

    monkeypatch.setattr(
        post_merge, "_save_attempt", crash_after_recovered_baseline_write
    )
    with pytest.raises(KeyboardInterrupt):
        run_s8(s8_setup)
    recovered = baseline_state(s8_setup)
    assert recovered["generation"] == 1
    assert (
        recovered["current"]["repository_sha"]
        != s8_setup["promotion_manifest"]["expected_base_sha"]
    )

    monkeypatch.setattr(post_merge, "_save_attempt", real_save)
    result = run_s8(s8_setup)
    assert result["status"] == "recovered"
    assert baseline_state(s8_setup)["generation"] == 1


def test_promoted_acceptance_rechecks_live_main_after_verification(s8_setup):
    provider = s8_setup["provider"]
    host = s8_setup["host"]
    original = provider.verify_candidate

    def move_main_after_promoted(*args, **kwargs):
        value = original(*args, **kwargs)
        head = git(Path(args[0]), "rev-parse", "HEAD")
        if head == provider.promoted_sha:
            host.main = "d" * 40
        return value

    provider.verify_candidate = move_main_after_promoted
    result = run_s8(s8_setup)
    assert result["status"] == "hold"
    assert result["reason"] == "main_moved_before_baseline_acceptance"
    state = baseline_state(s8_setup)
    assert state["generation"] == 0
    assert (
        state["current"]["repository_sha"]
        == s8_setup["promotion_manifest"]["expected_base_sha"]
    )


def test_recovery_acceptance_rechecks_live_main_after_repair_verification(s8_setup):
    provider = s8_setup["provider"]
    host = s8_setup["host"]
    provider.outcomes["promoted"] = "FORBIDDEN_REGRESSION"
    original = provider.verify_candidate
    original_base = s8_setup["promotion_manifest"]["expected_base_sha"]

    def move_main_after_recovery_replay(*args, **kwargs):
        value = original(*args, **kwargs)
        head = git(Path(args[0]), "rev-parse", "HEAD")
        if head not in {provider.promoted_sha, original_base}:
            host.main = "e" * 40
        return value

    provider.verify_candidate = move_main_after_recovery_replay
    result = run_s8(s8_setup)
    assert result["status"] == "hold"
    assert result["reason"] == "main_moved_before_recovery_acceptance"
    state = baseline_state(s8_setup)
    assert state["generation"] == 0
    assert state["current"]["repository_sha"] == original_base


def test_committed_acceptance_replay_fails_closed_if_baseline_artifact_missing(
    s8_setup,
):
    assert run_s8(s8_setup)["status"] == "accepted"
    s8_setup["baseline_state_path"].unlink()
    result = run_s8(s8_setup)
    assert result["status"] == "controlled_failure"
    assert result["reason"] == "terminal_baseline_invalid"


def test_committed_recovery_replay_fails_closed_if_baseline_artifact_corrupt(s8_setup):
    s8_setup["provider"].outcomes["promoted"] = "FORBIDDEN_REGRESSION"
    assert run_s8(s8_setup)["status"] == "recovered"
    s8_setup["baseline_state_path"].write_text("{}", encoding="utf-8")
    result = run_s8(s8_setup)
    assert result["status"] == "controlled_failure"
    assert result["reason"] == "terminal_baseline_invalid"


def test_baseline_authority_lock_blocks_concurrent_distinct_s8_attempt(s8_setup):
    lock = Path(str(s8_setup["baseline_state_path"]) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("foreign-attempt", encoding="utf-8")

    with pytest.raises(ValueError, match="baseline.*executing|baseline.*lock"):
        run_s8(s8_setup)
    assert s8_setup["provider"].verify_calls == []
    assert lock.exists()
