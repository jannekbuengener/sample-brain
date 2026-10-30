"""S7 behavioral contract: real isolated Git, synthetic payload, fake GitHub."""

import copy
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from src.analysis_eval_artifact import fingerprint
from src.analysis_locked_holdout import run_locked_holdout_transition
from tests.test_analysis_locked_holdout import frozen  # noqa: F401


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def seal(m):
    m["policy_fingerprint"] = fingerprint(m["policy"])
    m["change_fingerprint"] = fingerprint(m["changes"])
    m.pop("manifest_fingerprint", None)
    m["manifest_fingerprint"] = fingerprint(m)
    return m


class Provider:
    domain = "aq1.tempo"
    materializer_id = "synthetic.config"
    materializer_version = "1.0.0"

    def __init__(self):
        self.calls = 0
        self.validations = 0
        self.payload = {"config/promotion.json": '{"candidate":"frozen"}\n'}
        self.accept = True
        self.validation_ok = True

    def validate_plan(self, manifest, result):
        return self.accept

    def materialize(self, inputs):
        assert inputs == {"mode": "frozen"}
        self.calls += 1
        return self.payload

    def validate_candidate(self, worktree, contract_id):
        assert contract_id == "synthetic.regression.v1"
        assert (worktree / "config/promotion.json").read_text() == self.payload[
            "config/promotion.json"
        ]
        self.validations += 1
        return self.validation_ok


class Host:
    def __init__(self, repository, base):
        self.repository = repository
        self.base = base
        self.checks = [{"name": "required", "app_id": 15368, "state": "SUCCESS"}]
        self.required = [{"name": "required", "app_id": 15368}]
        self.pr = None
        self.creates = 0
        self.pushes = 0
        self.merges = 0
        self.head_override = None
        self.error = None
        self.feedback = []
        self.threads = 0
        self.blocking = False
        self.mergeable = True
        self.verified = True

    def main_sha(self):
        if self.error:
            from src.analysis_promotion_host import InfrastructureError

            raise InfrastructureError(self.error)
        return self.base

    def policy(self):
        return {
            "required_checks": self.required,
            "merge_methods": ["squash", "rebase"],
            "required_approvals": 0,
        }

    def pushed_head(self, branch):
        return self.pr["head_sha"] if self.pushes else None

    def push(self, repository, branch, head_sha):
        self.pushes += 1

    def find_pr(self, branch):
        return copy.deepcopy(self.pr)

    def create_pr(self, branch, head_sha, base_sha):
        self.creates += 1
        self.pr = {
            "number": 7,
            "branch": branch,
            "base": "main",
            "head_sha": head_sha,
            "repository_id": "example/repo",
        }
        return copy.deepcopy(self.pr)

    def snapshot(self, number):
        return {
            **self.pr,
            "head_sha": self.head_override or self.pr["head_sha"],
            "open": not bool(self.pr.get("merged")),
            "draft": False,
            "mergeable": self.mergeable,
            "checks": self.checks,
            "feedback": self.feedback,
            "unresolved_threads": self.threads,
            "blocking_review": self.blocking,
            "approvals": 0,
            "merged": self.pr.get("merged", False),
            "merge_sha": self.pr.get("merge_sha"),
        }

    def merge(self, number, expected_head_sha, method):
        assert method == "squash"
        assert expected_head_sha == self.pr["head_sha"]
        assert not self.head_override
        self.merges += 1
        self.pr.update(merged=True, merge_sha=expected_head_sha)

    def verify_merge(self, number, head_sha, merge_sha):
        return self.verified and self.pr["merged"] and merge_sha == head_sha


@pytest.fixture
def setup(tmp_path, frozen):
    from src.analysis_promotion import GitRepository

    frozen.update(
        decision_token="PROMOTION_CANDIDATE_IDENTIFIED",
        next_action="handoff_promotion_controller",
    )
    result = run_locked_holdout_transition(**frozen)["result"]
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Synthetic Fixture")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "core.autocrlf", "false")
    (root / "config").mkdir()
    (root / "config/promotion.json").write_text("{}\n", newline="\n")
    git(root, "add", "config/promotion.json")
    git(root, "commit", "-m", "synthetic baseline")
    base = git(root, "rev-parse", "HEAD")
    git(root, "update-ref", "refs/remotes/origin/main", base)
    git(root, "remote", "add", "origin", "https://github.com/example/repo.git")
    provider = Provider()
    manifest = seal(
        {
            "document_type": "sample-brain.analysis-promotion-manifest.v1",
            "artifact_version": "1.0.0",
            "domain": result["domain"],
            "baseline_candidate": result["baseline_candidate"],
            "current_candidate": result["current_candidate"],
            "locked_result_fingerprint": result["result_fingerprint"],
            "decision_fingerprint": result["decision"]["decision_fingerprint"],
            "evidence_fingerprint": result["decision"]["evidence"][
                "evidence_fingerprint"
            ],
            "expected_base_sha": base,
            "repository_id": "example/repo",
            "allowed_paths": ["config/promotion.json"],
            "forbidden_paths": ["private"],
            "materializer": {
                "id": provider.materializer_id,
                "version": provider.materializer_version,
                "inputs": {"mode": "frozen"},
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
    return dict(
        source_state_path=frozen["state_path"],
        manifest=manifest,
        provider=provider,
        repository=GitRepository(root),
        host=Host(root, base),
        worktree_root=tmp_path / "worktrees",
        attempt_root=tmp_path / "attempts",
    )


def run(setup, **kw):
    from src.analysis_promotion import run_promotion

    return run_promotion(**setup, **kw)


def test_success_isolated_exact_sha_and_replay(setup):
    before = git(setup["repository"].path, "rev-parse", "HEAD")
    result = run(setup)
    assert result["status"] == "merged"
    assert result["merge_sha"] == result["head_sha"] == result["pr_head_sha"]
    assert result["repository_merge_eligible"] is True
    assert result["production_authorized"] is False
    assert result["changed_paths"] == ["config/promotion.json"]
    assert result["change_fingerprint"] == setup["manifest"]["change_fingerprint"]
    assert result["validation_refs"] == ["synthetic.regression.v1"]
    assert result["pushed_head_sha"] == result["head_sha"]
    assert result["observed_checks"][0]["state"] == "SUCCESS"
    assert git(setup["repository"].path, "rev-parse", "HEAD") == before
    assert git(setup["repository"].path, "status", "--porcelain") == ""
    assert (
        json.loads(next(setup["attempt_root"].rglob("attempt.json")).read_text())
        == result
    )
    assert str(setup["worktree_root"]) not in json.dumps(result)
    assert run(setup) == result
    assert setup["provider"].calls == setup["provider"].validations == 1
    assert setup["host"].creates == setup["host"].pushes == setup["host"].merges == 1


@pytest.mark.parametrize(
    "state", ["FAILED", "PENDING", "MISSING", "UNKNOWN", "CANCELLED"]
)
def test_non_success_never_merges_and_resume_does_not_repeat(setup, state):
    setup["host"].checks[0]["state"] = state
    first = run(setup)
    assert first["status"] == "hold"
    assert first["observed_checks"][0]["state"] == state
    assert setup["host"].merges == 0
    setup["host"].checks[0]["state"] = "SUCCESS"
    assert run(setup)["status"] == "merged"
    assert setup["provider"].calls == setup["host"].creates == 1


@pytest.mark.parametrize(
    "checks",
    [
        [],
        [{"name": "required", "app_id": 9, "state": "SUCCESS"}],
        [{"name": "required", "app_id": 15368, "state": "SUCCESS"}] * 2,
    ],
)
def test_missing_wrong_app_or_duplicate_check_is_not_success(setup, checks):
    setup["host"].checks = checks
    assert run(setup)["status"] == "hold"
    assert setup["host"].merges == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("artifact_version", "9.0.0"),
        ("expected_base_sha", "b" * 40),
        ("locked_result_fingerprint", "c" * 64),
        ("decision_fingerprint", "c" * 64),
        ("evidence_fingerprint", "c" * 64),
        ("current_candidate", {"candidate_id": "wrong"}),
        ("allowed_paths", ["../outside"]),
        ("allowed_paths", ["C:/private/config"]),
        ("allowed_paths", ["config\\alias"]),
        ("allowed_paths", [".github/workflows/run.yml"]),
        ("materializer", {"id": "missing", "version": "1.0.0", "inputs": {}}),
    ],
)
def test_manifest_rejection_before_mutation(setup, field, value):
    setup["manifest"][field] = value
    seal(setup["manifest"])
    with pytest.raises(ValueError):
        run(setup)
    assert setup["provider"].calls == 0
    assert not setup["worktree_root"].exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "merge_method",
        "policy_fingerprint",
        "manifest_fingerprint",
        "secret",
        "local_path",
    ],
)
def test_policy_fingerprints_and_privacy(setup, mutation):
    m = setup["manifest"]
    if mutation == "merge_method":
        m["policy"]["merge_method"] = "admin"
        seal(m)
    elif mutation in {"policy_fingerprint", "manifest_fingerprint"}:
        m[mutation] = "f" * 64
    else:
        m["materializer"]["inputs"][mutation] = (
            "token=do-not-publish" if mutation == "secret" else "C:/private/samples.wav"
        )
        seal(m)
    with pytest.raises(ValueError):
        run(setup)
    assert setup["provider"].calls == 0


@pytest.mark.parametrize(
    "what", ["result", "claim", "state", "missing_result", "wrong_action"]
)
def test_s6_committed_chain_required(setup, what):
    state = Path(setup["source_state_path"])
    path = (
        state
        if what == "state"
        else state.with_name(
            state.name
            + (".locked-claim.json" if what == "claim" else ".locked-result.json")
        )
    )
    if what == "missing_result":
        path.unlink()
    else:
        data = json.loads(path.read_text())
        if what == "wrong_action":
            data["decision"]["next_action"] = "require_human_governance"
        else:
            data["domain"] = "other"
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        run(setup)
    assert setup["provider"].calls == 0


@pytest.mark.parametrize("ignored", [False, True])
def test_dirty_source_protected(setup, ignored):
    root = setup["repository"].path
    if ignored:
        (root / ".git/info/exclude").write_text("untracked-private\n")
    p = root / "untracked-private"
    p.write_text("preserve")
    with pytest.raises(ValueError, match="clean|dirty"):
        run(setup)
    assert p.read_text() == "preserve"
    assert setup["provider"].calls == 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"outside.py": "bad"},
        {"config/promotion.json": "wrong"},
        {"config/promotion.json": "\x00binary"},
        {"config/promotion.json": 'path = "C:/private/user/file"'},
        {"config/promotion.json": "api_key=private"},
    ],
)
def test_payload_guard_before_push(setup, payload):
    setup["provider"].payload = payload
    result = run(setup)
    assert result["status"] == "controlled_failure"
    assert setup["host"].pushes == setup["host"].creates == 0


def test_domain_rejects_semantics_without_mutation(setup):
    setup["provider"].accept = False
    with pytest.raises(ValueError):
        run(setup)
    assert setup["provider"].calls == 0


def test_validation_failure_is_persisted_without_push(setup):
    setup["provider"].validation_ok = False
    assert run(setup)["status"] == "controlled_failure"
    assert setup["host"].pushes == 0


@pytest.mark.parametrize(
    "condition",
    ["base", "head", "rules", "threads", "blocking", "mergeable", "feedback"],
)
def test_live_drift_and_review_gates_fail_closed(setup, condition):
    host = setup["host"]
    host.checks[0]["state"] = "PENDING"
    run(setup)
    host.checks[0]["state"] = "SUCCESS"
    if condition == "base":
        host.base = "b" * 40
    if condition == "head":
        host.head_override = "c" * 40
    if condition == "rules":
        host.required.append({"name": "new", "app_id": 1})
    if condition == "threads":
        host.threads = 1
    if condition == "blocking":
        host.blocking = True
    if condition == "mergeable":
        host.mergeable = False
    if condition == "feedback":
        host.feedback = [{"id": "issue:1", "body": "review", "updated_at": "now"}]
    assert run(setup)["status"] == "hold"
    assert host.merges == 0


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/example/repo.git",
        "https://github.com/example/repo",
        "git@github.com:example/repo.git",
    ],
)
def test_origin_accepts_expected_github_remote(remote):
    from src.analysis_promotion import origin_matches_repository

    assert origin_matches_repository(remote, "example/repo") is True


@pytest.mark.parametrize(
    "remote",
    [
        "https://x-access-token:ghs_exampletokenvalue@github.com/example/repo.git",
        "https://x-access-token:ghs_exampletokenvalue@github.com/example/repo",
        "https://token-only@github.com/example/repo.git",
        "https://user:pass@github.com/example/repo.git",
    ],
)
def test_origin_accepts_same_remote_with_injected_userinfo(remote):
    from src.analysis_promotion import origin_matches_repository

    assert origin_matches_repository(remote, "example/repo") is True


def test_origin_rejects_different_owner():
    from src.analysis_promotion import origin_matches_repository

    assert (
        origin_matches_repository("https://github.com/other/repo.git", "example/repo")
        is False
    )
    assert (
        origin_matches_repository(
            "https://x-access-token:tok@github.com/other/repo.git", "example/repo"
        )
        is False
    )


def test_origin_rejects_different_repository():
    from src.analysis_promotion import origin_matches_repository

    assert (
        origin_matches_repository(
            "https://github.com/example/other.git", "example/repo"
        )
        is False
    )
    assert (
        origin_matches_repository(
            "https://x-access-token:tok@github.com/example/other.git", "example/repo"
        )
        is False
    )


def test_origin_rejects_different_host():
    from src.analysis_promotion import origin_matches_repository

    assert (
        origin_matches_repository(
            "https://gitlab.com/example/repo.git", "example/repo"
        )
        is False
    )
    assert (
        origin_matches_repository(
            "https://x-access-token:tok@evil.example/example/repo.git", "example/repo"
        )
        is False
    )
    assert (
        origin_matches_repository(
            "https://x-access-token:tok@github.com.evil/example/repo.git",
            "example/repo",
        )
        is False
    )
    assert (
        origin_matches_repository(
            "http://github.com/example/repo.git", "example/repo"
        )
        is False
    )


def test_preflight_accepts_credential_rewritten_origin(setup):
    from src.analysis_promotion import PromotionError

    root = setup["repository"].path
    # Simulate Cloud Agent insteadOf / credential injection on an otherwise
    # identical GitHub remote without weakening host/owner/repo identity.
    git(
        root,
        "remote",
        "set-url",
        "origin",
        "https://x-access-token:ghs_exampletokenvalue@github.com/example/repo.git",
    )
    setup["repository"].preflight(setup["manifest"])
    git(root, "remote", "set-url", "origin", "https://github.com/other/repo.git")
    with pytest.raises(PromotionError, match="origin repository mismatch"):
        setup["repository"].preflight(setup["manifest"])


def test_explicit_review_disposition_is_bound_to_head_and_snapshot(setup):
    host = setup["host"]
    host.feedback = [{"id": "issue:1", "body": "review", "updated_at": "now"}]
    first = run(setup)
    evidence = {
        "head_sha": first["head_sha"],
        "feedback_fingerprint": fingerprint(host.feedback),
        "dispositions": {"issue:1": "EXPLAINED"},
    }
    wrong = {**evidence, "head_sha": "0" * 40}
    assert run(setup, review_evidence=wrong)["status"] == "hold"
    assert run(setup, review_evidence=evidence)["status"] == "merged"


def test_infrastructure_error_is_sanitized_and_resumable(setup):
    setup["host"].checks[0]["state"] = "PENDING"
    run(setup)
    setup["host"].error = "auth failure token=do-not-record C:/private"
    result = run(setup)
    assert result["status"] == "infrastructure_hold"
    assert "do-not-record" not in json.dumps(result)
    setup["host"].error = None
    setup["host"].checks[0]["state"] = "SUCCESS"
    assert run(setup)["status"] == "merged"


def test_lost_pr_response_reconciles_without_duplicate(setup):
    host = setup["host"]
    original = host.create_pr

    def lost(*args):
        original(*args)
        from src.analysis_promotion_host import InfrastructureError

        raise InfrastructureError("lost response")

    host.create_pr = lost
    assert run(setup)["status"] == "infrastructure_hold"
    host.create_pr = original
    assert run(setup)["status"] == "merged"
    assert host.creates == 1


def test_lost_merge_response_reconciles_without_duplicate(setup):
    host = setup["host"]
    original = host.merge

    def lost(*args):
        original(*args)
        from src.analysis_promotion_host import InfrastructureError

        raise InfrastructureError("lost merge response")

    host.merge = lost
    assert run(setup)["status"] == "infrastructure_hold"
    host.merge = original
    assert run(setup)["status"] == "merged"
    assert host.merges == 1


def test_unverified_merge_never_reports_success(setup):
    setup["host"].verified = False
    assert run(setup)["status"] != "merged"
    assert setup["host"].merges == 1
    setup["host"].verified = True
    assert run(setup)["status"] == "merged"
    assert setup["host"].merges == 1


def test_foreign_attempt_state_cannot_be_resealed_or_restarted(setup):
    setup["host"].checks[0]["state"] = "PENDING"
    run(setup)
    state_path = next(setup["attempt_root"].rglob("attempt.json"))
    value = json.loads(state_path.read_text())
    value["head_sha"] = "a" * 40
    state_path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        run(setup)
    assert setup["provider"].calls == 1


def test_diff_guard_after_validation_detects_unexpected_file(setup):
    original = setup["provider"].validate_candidate

    def extra(worktree, contract):
        original(worktree, contract)
        (worktree / "unexpected.txt").write_text("unexpected")
        return True

    setup["provider"].validate_candidate = extra
    assert run(setup)["status"] == "controlled_failure"
    assert setup["host"].pushes == 0


def test_head_moves_between_gate_reads_never_merges(setup):
    host = setup["host"]
    original = host.snapshot
    reads = []

    def moved(number):
        reads.append(number)
        result = original(number)
        if len(reads) > 1:
            result["head_sha"] = "d" * 40
        return result

    host.snapshot = moved
    assert run(setup)["status"] == "hold"
    assert host.merges == 0


def test_interrupted_materializer_never_dispatches_twice(setup):
    def interrupted(inputs):
        setup["provider"].calls += 1
        raise KeyboardInterrupt()

    setup["provider"].materialize = interrupted
    with pytest.raises(KeyboardInterrupt):
        run(setup)
    assert run(setup)["status"] == "hold"
    assert setup["provider"].calls == 1


def test_ambiguous_pr_creation_is_not_blindly_retried(setup):
    host = setup["host"]

    def lost(*args):
        host.creates += 1
        from src.analysis_promotion_host import InfrastructureError

        raise InfrastructureError("uncertain create")

    host.create_pr = lost
    assert run(setup)["status"] == "infrastructure_hold"
    assert run(setup)["status"] == "hold"
    assert host.creates == 1


def test_merge_conflict_never_reports_merged(setup):
    def conflict(*args):
        from src.analysis_promotion_host import InfrastructureError

        raise InfrastructureError("merge conflict")

    setup["host"].merge = conflict
    assert run(setup)["status"] == "infrastructure_hold"
    assert run(setup)["status"] == "hold"
    assert setup["host"].pr.get("merged") is None


@pytest.mark.parametrize("condition", ["held", "legacy", "keep", "failure", "nonpass"])
def test_valid_resealed_nonpromotion_source_is_rejected(setup, condition):
    from src.analysis_automation_decision import decision_semantic_fingerprint

    path = Path(setup["source_state_path"])
    result_path = path.with_name(path.name + ".locked-result.json")
    claim_path = path.with_name(path.name + ".locked-claim.json")
    result = json.loads(result_path.read_text())
    claim = json.loads(claim_path.read_text())
    decision = result["decision"]
    if condition == "legacy":
        decision.update(
            artifact_version="1.0.0", next_action="require_human_governance"
        )
    elif condition == "keep":
        decision.update(
            decision_token="KEEP_CURRENT_BASELINE_PATH",
            next_action="keep_baseline_and_stop",
        )
    elif condition in {"held", "failure"}:
        decision.update(
            decision_status="hold" if condition == "held" else "controlled_failure",
            decision_token=None,
            next_action="defer_for_evidence"
            if condition == "held"
            else "stop_controlled_failure",
        )
        decision["evidence"]["gate_decision"]["verdict"] = "HOLD"
    else:
        decision["evidence"]["gate_decision"]["verdict"] = "FAIL"
    decision["decision_fingerprint"] = decision_semantic_fingerprint(decision)
    result["terminal_status"] = decision["decision_status"]
    claim.update(
        gate_verdict=decision["evidence"]["gate_decision"]["verdict"],
        decision_token=decision["decision_token"],
        next_action=decision["next_action"],
    )
    result["invocation_fingerprint"] = fingerprint(claim)
    result.pop("result_fingerprint")
    result["result_fingerprint"] = fingerprint(result)
    result_path.write_text(json.dumps(result))
    claim_path.write_text(json.dumps(claim))
    setup["manifest"].update(
        locked_result_fingerprint=result["result_fingerprint"],
        decision_fingerprint=decision["decision_fingerprint"],
    )
    seal(setup["manifest"])
    with pytest.raises(ValueError):
        run(setup)
    assert setup["provider"].calls == 0
