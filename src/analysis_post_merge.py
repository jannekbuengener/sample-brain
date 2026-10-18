"""S8: verify an S7 merge, accept baseline lineage, or forward-repair safely.

The module composes S6/S7 persistence. Repository merge is not baseline
acceptance. All host paths are invocation bindings and never enter portable
state.
"""

from __future__ import annotations

import copy
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Mapping, Protocol

from src.analysis_eval_artifact import assert_portable_value, fingerprint
from src.analysis_locked_holdout import _sync_entry, _write_atomic
from src.analysis_promotion import (
    GitRepository,
    PromotionError,
    _content,
    _eligible,
    _load as _load_promotion_attempt_state,
    _path,
    _policy_matches,
    _safe,
    _target,
    load_promotion_source,
    validate_manifest,
)
from src.analysis_promotion_host import InfrastructureError

PLAN_TYPE = "sample-brain.analysis-post-merge-plan.v1"
ATTEMPT_TYPE = "sample-brain.analysis-post-merge-attempt.v1"
BASELINE_TYPE = "sample-brain.analysis-baseline-lineage.v1"
VERSION = "1.0.0"

_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_OUTCOMES = {"PASS", "HOLD", "CONTROLLED_FAILURE", "FORBIDDEN_REGRESSION"}


class AnalysisPostMergeError(ValueError):
    """Invalid post-merge authority, lineage, policy or portable state."""


class PostMergeProvider(Protocol):
    domain: str
    verification_id: str
    verification_version: str
    recovery_materializer_id: str
    recovery_materializer_version: str

    def verify_candidate(
        self,
        worktree: Path,
        candidate: Mapping[str, str],
        contract_id: str,
        evidence_root: Path,
    ) -> Mapping[str, Any]: ...

    def validate_recovery_plan(
        self, plan: Mapping[str, Any], source: Mapping[str, Any]
    ) -> bool: ...

    def materialize_recovery(self, inputs: Mapping[str, Any]) -> Mapping[str, str]: ...

    def validate_recovery_candidate(self, worktree: Path, contract_id: str) -> bool: ...


class PostMergeHost(Protocol):
    repository_id: str

    def main_sha(self) -> str: ...
    def policy(self) -> dict[str, Any]: ...
    def verify_merge(self, number: int, head_sha: str, merge_sha: str) -> bool: ...
    def pushed_head(self, branch: str) -> str | None: ...
    def push(self, repository: GitRepository, branch: str, head_sha: str) -> None: ...
    def find_pr(self, branch: str) -> dict[str, Any] | None: ...
    def create_bounded_pr(
        self, branch: str, head_sha: str, base_sha: str, *, title: str, body: str
    ) -> dict[str, Any]: ...
    def snapshot(self, number: int) -> dict[str, Any]: ...
    def merge(self, number: int, expected_head_sha: str, method: str) -> None: ...


def _require(condition: object, message: str) -> None:
    if not condition:
        raise AnalysisPostMergeError(message)


@contextmanager
def _exclusive_lock(path: Path, identity: str, *, message: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise AnalysisPostMergeError(message) from exc
    try:
        with handle:
            handle.write(identity)
            handle.flush()
            os.fsync(handle.fileno())
        _sync_entry(path)
        yield
    finally:
        path.unlink(missing_ok=True)


def _hex(value: object, pattern: re.Pattern[str] = _HEX64) -> str:
    _require(
        isinstance(value, str) and pattern.fullmatch(value),
        "invalid fingerprint or SHA",
    )
    return str(value)


def _candidate(value: object, field: str) -> dict[str, str]:
    _require(isinstance(value, Mapping), f"{field} must be a mapping")
    _require(set(value) == {"candidate_id", "config_fingerprint"}, f"invalid {field}")
    candidate_id = value.get("candidate_id")
    _require(
        isinstance(candidate_id, str) and _ID.fullmatch(candidate_id),
        f"invalid {field}",
    )
    config = _hex(value.get("config_fingerprint"))
    return {"candidate_id": candidate_id, "config_fingerprint": config}


def _reason(value: object) -> str | None:
    if value is None:
        return None
    _require(isinstance(value, str) and _ID.fullmatch(value), "invalid reason code")
    return value


def _portable_copy(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        assert_portable_value(value)
    except Exception as exc:
        raise AnalysisPostMergeError("non-portable post-merge value") from exc
    _safe(value)
    return json.loads(json.dumps(value))


def _promotion_inputs(
    *,
    source_state_path: str | os.PathLike[str],
    promotion_manifest: Mapping[str, Any],
    promotion_provider: Any,
    promotion_attempt_path: str | os.PathLike[str],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    result = load_promotion_source(source_state_path)
    manifest = validate_manifest(dict(promotion_manifest), result, promotion_provider)
    attempt = _load_promotion_attempt_state(Path(promotion_attempt_path), manifest)
    _require(
        attempt["phase"] == "merged"
        and attempt["status"] == "merged"
        and attempt["repository_merge_eligible"] is True
        and isinstance(attempt["pr_number"], int)
        and attempt["pr_number"] > 0
        and attempt["head_sha"] == attempt["pr_head_sha"] == attempt["pushed_head_sha"]
        and attempt["merge_sha"] is not None,
        "S7 attempt is not a committed successful merge",
    )
    _hex(attempt["head_sha"], _HEX40)
    _hex(attempt["merge_sha"], _HEX40)
    _require(
        attempt["production_authorized"] is False, "invalid S7 production authority"
    )
    return result, manifest, attempt


def _validate_recovery(
    recovery: object, *, merge_sha: str, repository_id: str, provider: Any
) -> dict[str, Any]:
    _require(isinstance(recovery, Mapping), "recovery plan must be a mapping")
    required = {
        "expected_base_sha",
        "allowed_paths",
        "forbidden_paths",
        "materializer",
        "changes",
        "change_fingerprint",
        "validation",
        "policy",
        "policy_fingerprint",
    }
    _require(set(recovery) == required, "invalid recovery fields")
    value = _portable_copy(recovery)
    _require(
        value["expected_base_sha"] == merge_sha,
        "recovery base differs from promoted merge",
    )
    _hex(value["expected_base_sha"], _HEX40)

    allowed = value["allowed_paths"]
    forbidden = value["forbidden_paths"]
    _require(
        isinstance(allowed, list)
        and 0 < len(allowed) <= 100
        and all(isinstance(path, str) for path in allowed)
        and len({path.lower() for path in allowed}) == len(allowed),
        "invalid recovery path allowlist",
    )
    _require(isinstance(forbidden, list), "invalid recovery forbidden paths")
    for path in forbidden:
        _path(path, protected=False)
    for path in allowed:
        _path(path)
        _require(
            not any(
                path.lower() == blocked.lower()
                or path.lower().startswith(blocked.lower() + "/")
                for blocked in forbidden
            ),
            "forbidden recovery path",
        )

    changes = value["changes"]
    _require(
        isinstance(changes, dict) and set(changes) == set(allowed),
        "exact recovery changes required",
    )
    for change in changes.values():
        _require(
            isinstance(change, dict)
            and set(change) == {"before_sha256", "after_sha256"},
            "invalid recovery change",
        )
        if change["before_sha256"] is not None:
            _hex(change["before_sha256"])
        _hex(change["after_sha256"])
        _require(
            change["before_sha256"] != change["after_sha256"], "empty recovery change"
        )
    _require(
        fingerprint(changes) == value["change_fingerprint"],
        "recovery change fingerprint mismatch",
    )

    materializer = value["materializer"]
    _require(
        isinstance(materializer, dict)
        and set(materializer) == {"id", "version", "inputs"}
        and isinstance(materializer["inputs"], dict),
        "invalid recovery materializer",
    )
    _require(
        provider.recovery_materializer_id == materializer["id"]
        and provider.recovery_materializer_version == materializer["version"],
        "unknown recovery materializer",
    )
    validation = value["validation"]
    _require(
        isinstance(validation, list)
        and validation
        and len(set(validation)) == len(validation)
        and all(isinstance(item, str) and _ID.fullmatch(item) for item in validation),
        "invalid recovery validation contract",
    )
    policy = value["policy"]
    _require(
        isinstance(policy, dict)
        and set(policy)
        == {"version", "required_checks", "merge_method", "review_gate"},
        "invalid recovery repository policy",
    )
    _require(
        policy["version"] == VERSION
        and policy["merge_method"] in {"squash", "rebase"}
        and policy["review_gate"] == "all_feedback_dispositioned.v1",
        "unsupported recovery repository policy",
    )
    checks = policy["required_checks"]
    _require(
        isinstance(checks, list) and checks and len(checks) <= 100,
        "recovery checks missing",
    )
    for check in checks:
        _require(
            isinstance(check, dict)
            and set(check) == {"name", "app_id"}
            and isinstance(check["name"], str)
            and check["name"].strip()
            and type(check["app_id"]) is int
            and check["app_id"] > 0,
            "invalid recovery required check",
        )
    _require(
        len({(c["name"], c["app_id"]) for c in checks}) == len(checks),
        "duplicate recovery checks",
    )
    _require(
        fingerprint(policy) == value["policy_fingerprint"],
        "recovery policy fingerprint mismatch",
    )
    _require(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository_id),
        "invalid repository identity",
    )
    return value


def validate_plan(
    plan: Mapping[str, Any],
    *,
    source: Mapping[str, Any],
    promotion_manifest: Mapping[str, Any],
    promotion_attempt: Mapping[str, Any],
    provider: PostMergeProvider,
) -> dict[str, Any]:
    keys = {
        "document_type",
        "artifact_version",
        "domain",
        "promotion_manifest_fingerprint",
        "promotion_attempt_fingerprint",
        "locked_result_fingerprint",
        "decision_fingerprint",
        "evidence_fingerprint",
        "merge_sha",
        "previous_baseline_candidate",
        "promoted_candidate",
        "repository_id",
        "verification",
        "recovery",
        "plan_fingerprint",
    }
    _require(
        isinstance(plan, Mapping) and set(plan) == keys,
        "invalid post-merge plan fields",
    )
    value = _portable_copy(plan)
    _require(
        value["document_type"] == PLAN_TYPE and value["artifact_version"] == VERSION,
        "unsupported post-merge plan version",
    )
    _require(
        fingerprint({k: v for k, v in value.items() if k != "plan_fingerprint"})
        == value["plan_fingerprint"],
        "post-merge plan fingerprint mismatch",
    )
    for key in (
        "promotion_manifest_fingerprint",
        "promotion_attempt_fingerprint",
        "locked_result_fingerprint",
        "decision_fingerprint",
        "evidence_fingerprint",
        "plan_fingerprint",
    ):
        _hex(value[key])
    _hex(value["merge_sha"], _HEX40)
    _require(
        value["domain"] == source["domain"] == provider.domain
        and value["previous_baseline_candidate"] == source["baseline_candidate"]
        and value["promoted_candidate"] == source["current_candidate"],
        "post-merge candidate lineage mismatch",
    )
    _candidate(value["previous_baseline_candidate"], "previous_baseline_candidate")
    _candidate(value["promoted_candidate"], "promoted_candidate")
    _require(
        value["promotion_manifest_fingerprint"]
        == promotion_manifest["manifest_fingerprint"]
        and value["promotion_attempt_fingerprint"]
        == promotion_attempt["state_fingerprint"]
        and value["locked_result_fingerprint"] == source["result_fingerprint"]
        and value["decision_fingerprint"] == source["decision"]["decision_fingerprint"]
        and value["evidence_fingerprint"]
        == source["decision"]["evidence"]["evidence_fingerprint"]
        and value["merge_sha"] == promotion_attempt["merge_sha"]
        and value["repository_id"] == promotion_manifest["repository_id"],
        "post-merge lineage mismatch",
    )
    verification = value["verification"]
    _require(
        isinstance(verification, dict)
        and set(verification) == {"id", "version", "contracts"}
        and verification["id"] == provider.verification_id
        and verification["version"] == provider.verification_version
        and isinstance(verification["contracts"], list)
        and verification["contracts"]
        and len(set(verification["contracts"])) == len(verification["contracts"])
        and all(
            isinstance(item, str) and _ID.fullmatch(item)
            for item in verification["contracts"]
        ),
        "invalid post-merge verification policy",
    )
    value["recovery"] = _validate_recovery(
        value["recovery"],
        merge_sha=value["merge_sha"],
        repository_id=value["repository_id"],
        provider=provider,
    )
    _require(
        provider.validate_recovery_plan(
            copy.deepcopy(value),
            {
                "source": copy.deepcopy(dict(source)),
                "promotion_manifest": copy.deepcopy(dict(promotion_manifest)),
                "promotion_attempt": copy.deepcopy(dict(promotion_attempt)),
            },
        )
        is True,
        "domain rejected post-merge recovery plan",
    )
    return value


def _verification_ref(
    *,
    repository_sha: str,
    candidate: Mapping[str, str],
    contract_id: str,
    result: Mapping[str, Any],
) -> dict[str, Any]:
    _require(isinstance(result, Mapping), "verification result must be a mapping")
    _require(
        set(result) == {"outcome", "evidence_fingerprint", "reason_code"},
        "invalid verification result",
    )
    outcome = result["outcome"]
    _require(outcome in _OUTCOMES, "unknown verification outcome")
    evidence = _hex(result["evidence_fingerprint"])
    reason = _reason(result["reason_code"])
    payload = {
        "repository_sha": _hex(repository_sha, _HEX40),
        "candidate": _candidate(candidate, "verification.candidate"),
        "contract_id": contract_id,
        "outcome": outcome,
        "evidence_fingerprint": evidence,
        "reason_code": reason,
    }
    _portable_copy(payload)
    payload["verification_fingerprint"] = fingerprint(payload)
    return payload


def _all_pass(refs: list[dict[str, Any]]) -> bool:
    return bool(refs) and all(ref["outcome"] == "PASS" for ref in refs)


def _safe_detached_verify(
    *,
    repository: GitRepository,
    repository_sha: str,
    candidate: Mapping[str, str],
    plan: Mapping[str, Any],
    provider: PostMergeProvider,
    worktree: Path,
    evidence_root: Path,
) -> list[dict[str, Any]]:
    _require(not worktree.exists(), "foreign verification worktree exists")
    repository.git("cat-file", "-e", f"{repository_sha}^{{commit}}")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    repository.git("worktree", "add", "--detach", str(worktree), repository_sha)
    clean = False
    try:
        _require(repository.head("HEAD") != "", "repository unavailable")
        _require(
            repository.git("rev-parse", "HEAD", cwd=worktree) == repository_sha,
            "verification worktree SHA mismatch",
        )
        _require(
            not repository.git(
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--ignored=matching",
                cwd=worktree,
            ),
            "verification worktree not clean",
        )
        refs = []
        evidence_root.mkdir(parents=True, exist_ok=True)
        for contract_id in plan["verification"]["contracts"]:
            result = provider.verify_candidate(
                worktree,
                copy.deepcopy(dict(candidate)),
                contract_id,
                evidence_root
                / fingerprint({"sha": repository_sha, "contract": contract_id}),
            )
            refs.append(
                _verification_ref(
                    repository_sha=repository_sha,
                    candidate=candidate,
                    contract_id=contract_id,
                    result=result,
                )
            )
        _require(
            not repository.git(
                "status",
                "--porcelain",
                "--untracked-files=all",
                "--ignored=matching",
                cwd=worktree,
            ),
            "verification modified repository state",
        )
        clean = True
        return refs
    finally:
        if worktree.exists() and clean:
            repository.git("worktree", "remove", str(worktree))


def _baseline_ref(
    *,
    domain: str,
    candidate: Mapping[str, str],
    repository_sha: str,
    verification_refs: list[Mapping[str, Any]],
    policy_fingerprint: str,
    source_fingerprint: str,
) -> dict[str, Any]:
    _require(
        _all_pass([dict(ref) for ref in verification_refs]),
        "baseline reference requires PASS verification",
    )
    payload = {
        "domain": domain,
        "candidate": _candidate(candidate, "baseline.candidate"),
        "repository_sha": _hex(repository_sha, _HEX40),
        "verification_fingerprints": [
            _hex(ref["verification_fingerprint"]) for ref in verification_refs
        ],
        "policy_fingerprint": _hex(policy_fingerprint),
        "source_fingerprint": _hex(source_fingerprint),
    }
    payload["baseline_fingerprint"] = fingerprint(payload)
    return payload


def _validate_baseline_ref(value: object, domain: str) -> dict[str, Any]:
    _require(isinstance(value, Mapping), "baseline reference must be a mapping")
    keys = {
        "domain",
        "candidate",
        "repository_sha",
        "verification_fingerprints",
        "policy_fingerprint",
        "source_fingerprint",
        "baseline_fingerprint",
    }
    _require(
        set(value) == keys and value["domain"] == domain, "invalid baseline reference"
    )
    normalized = {
        "domain": domain,
        "candidate": _candidate(value["candidate"], "baseline.candidate"),
        "repository_sha": _hex(value["repository_sha"], _HEX40),
        "verification_fingerprints": [
            _hex(item) for item in value["verification_fingerprints"]
        ],
        "policy_fingerprint": _hex(value["policy_fingerprint"]),
        "source_fingerprint": _hex(value["source_fingerprint"]),
    }
    _require(
        normalized["verification_fingerprints"], "baseline verification refs missing"
    )
    _require(
        fingerprint(normalized) == value["baseline_fingerprint"],
        "baseline fingerprint mismatch",
    )
    normalized["baseline_fingerprint"] = value["baseline_fingerprint"]
    return normalized


def _baseline_state(
    *,
    domain: str,
    current: Mapping[str, Any],
    last_known_good: Mapping[str, Any] | None,
    generation: int,
    source_plan_fingerprint: str,
    source_promotion_attempt_fingerprint: str,
) -> dict[str, Any]:
    _require(type(generation) is int and generation >= 0, "invalid baseline generation")
    payload = {
        "document_type": BASELINE_TYPE,
        "artifact_version": VERSION,
        "domain": domain,
        "current": _validate_baseline_ref(current, domain),
        "last_known_good": None
        if last_known_good is None
        else _validate_baseline_ref(last_known_good, domain),
        "generation": generation,
        "source_plan_fingerprint": _hex(source_plan_fingerprint),
        "source_promotion_attempt_fingerprint": _hex(
            source_promotion_attempt_fingerprint
        ),
    }
    _portable_copy(payload)
    payload["state_fingerprint"] = fingerprint(payload)
    return payload


def validate_baseline_lineage(value: Mapping[str, Any]) -> dict[str, Any]:
    _require(isinstance(value, Mapping), "baseline lineage must be a mapping")
    keys = {
        "document_type",
        "artifact_version",
        "domain",
        "current",
        "last_known_good",
        "generation",
        "source_plan_fingerprint",
        "source_promotion_attempt_fingerprint",
        "state_fingerprint",
    }
    _require(
        set(value) == keys
        and value["document_type"] == BASELINE_TYPE
        and value["artifact_version"] == VERSION,
        "invalid baseline lineage schema",
    )
    normalized = _baseline_state(
        domain=value["domain"],
        current=value["current"],
        last_known_good=value["last_known_good"],
        generation=value["generation"],
        source_plan_fingerprint=value["source_plan_fingerprint"],
        source_promotion_attempt_fingerprint=value[
            "source_promotion_attempt_fingerprint"
        ],
    )
    _require(
        normalized["state_fingerprint"] == value["state_fingerprint"],
        "baseline lineage fingerprint mismatch",
    )
    return normalized


def load_baseline_lineage(path: str | os.PathLike[str]) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnalysisPostMergeError("missing or corrupt baseline lineage") from exc
    return validate_baseline_lineage(value)


def save_baseline_lineage(
    path: str | os.PathLike[str], value: Mapping[str, Any]
) -> dict[str, Any]:
    if "state_fingerprint" in value:
        validated = validate_baseline_lineage(value)
    else:
        required = {
            "document_type",
            "artifact_version",
            "domain",
            "current",
            "last_known_good",
            "generation",
            "source_plan_fingerprint",
            "source_promotion_attempt_fingerprint",
        }
        _require(
            set(value) == required
            and value.get("document_type") == BASELINE_TYPE
            and value.get("artifact_version") == VERSION,
            "invalid unsealed baseline lineage schema",
        )
        validated = _baseline_state(
            domain=value["domain"],
            current=value["current"],
            last_known_good=value["last_known_good"],
            generation=value["generation"],
            source_plan_fingerprint=value["source_plan_fingerprint"],
            source_promotion_attempt_fingerprint=value[
                "source_promotion_attempt_fingerprint"
            ],
        )
    _write_atomic(Path(path), validated)
    return validated


def _new_recovery(plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "branch": f"recovery/{plan['plan_fingerprint'][:24]}",
        "changed_paths": [],
        "validation_refs": [],
        "head_sha": None,
        "pushed_head_sha": None,
        "pr_number": None,
        "pr_head_sha": None,
        "observed_checks": [],
        "repository_merge_eligible": False,
        "merge_sha": None,
        "phase": "not_started",
    }


def _new_attempt(
    plan: Mapping[str, Any], promotion_attempt: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "document_type": ATTEMPT_TYPE,
        "artifact_version": VERSION,
        "attempt_id": plan["plan_fingerprint"],
        "plan_fingerprint": plan["plan_fingerprint"],
        "promotion_attempt_fingerprint": promotion_attempt["state_fingerprint"],
        "merge_sha": promotion_attempt["merge_sha"],
        "baseline_generation_start": None,
        "baseline_before_fingerprint": None,
        "baseline_verification_refs": [],
        "promoted_verification_refs": [],
        "recovery_verification_refs": [],
        "accepted_baseline_fingerprint": None,
        "last_known_good_fingerprint": None,
        "invalid_promotion": False,
        "recovery": _new_recovery(plan),
        "phase": "prepared",
        "status": "running",
        "reason": None,
        "production_authorized": False,
    }


def _save_attempt(path: Path, state: dict[str, Any]) -> dict[str, Any]:
    state.pop("state_fingerprint", None)
    _portable_copy(state)
    state["state_fingerprint"] = fingerprint(state)
    _write_atomic(path, state)
    return state


def _load_attempt(
    path: Path, plan: Mapping[str, Any], promotion_attempt: Mapping[str, Any]
) -> dict[str, Any]:
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise AnalysisPostMergeError("missing or corrupt S8 attempt") from exc
    _require(isinstance(state, dict), "S8 attempt must be a mapping")
    payload = {key: value for key, value in state.items() if key != "state_fingerprint"}
    _require(
        set(payload) == set(_new_attempt(plan, promotion_attempt)),
        "invalid S8 attempt schema",
    )
    _portable_copy(state)
    _require(
        fingerprint(payload) == state.get("state_fingerprint"),
        "S8 attempt fingerprint mismatch",
    )
    expected = _new_attempt(plan, promotion_attempt)
    for key in (
        "document_type",
        "artifact_version",
        "attempt_id",
        "plan_fingerprint",
        "promotion_attempt_fingerprint",
        "merge_sha",
        "production_authorized",
    ):
        _require(state[key] == expected[key], "S8 attempt lineage mismatch")
    _require(
        state["production_authorized"] is False,
        "production authorization must remain false",
    )
    return state


def _recovery_manifest(plan: Mapping[str, Any]) -> dict[str, Any]:
    recovery = plan["recovery"]
    return {
        "expected_base_sha": recovery["expected_base_sha"],
        "repository_id": plan["repository_id"],
        "allowed_paths": recovery["allowed_paths"],
        "forbidden_paths": recovery["forbidden_paths"],
        "materializer": recovery["materializer"],
        "changes": recovery["changes"],
        "change_fingerprint": recovery["change_fingerprint"],
        "validation": recovery["validation"],
        "policy": recovery["policy"],
    }


def _recovery_identity(
    state: Mapping[str, Any], snapshot: Mapping[str, Any], plan: Mapping[str, Any]
) -> bool:
    recovery = state["recovery"]
    return (
        snapshot["head_sha"] == recovery["head_sha"]
        and snapshot["branch"] == recovery["branch"]
        and snapshot["repository_id"] == plan["repository_id"]
        and snapshot["base"] == "main"
        and snapshot["number"] == recovery["pr_number"]
    )


def _advance_recovery(
    *,
    state_path: Path,
    state: dict[str, Any],
    plan: Mapping[str, Any],
    provider: PostMergeProvider,
    repository: GitRepository,
    host: PostMergeHost,
    worktree: Path,
    review_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    recovery = state["recovery"]
    manifest = _recovery_manifest(plan)

    def save(
        *,
        phase: str | None = None,
        status: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if phase is not None:
            state["phase"] = phase
        if status is not None:
            state["status"] = status
        state["reason"] = reason
        return _save_attempt(state_path, state)

    def hold(reason: str, *, status: str = "hold") -> dict[str, Any]:
        recovery["repository_merge_eligible"] = False
        return save(status=status, reason=reason)

    if recovery["phase"] == "merging":
        snapshot = host.snapshot(recovery["pr_number"])
        if snapshot["merged"] is True and _recovery_identity(state, snapshot, plan):
            merge_sha = snapshot.get("merge_sha")
            if isinstance(merge_sha, str) and _HEX40.fullmatch(merge_sha):
                recovery["merge_sha"] = merge_sha
                if (
                    host.verify_merge(
                        recovery["pr_number"], recovery["head_sha"], merge_sha
                    )
                    is True
                ):
                    recovery["phase"] = "merged"
                    recovery["repository_merge_eligible"] = True
                    return save(phase="recovery_merged", status="running")
        return hold("uncertain_recovery_merge_requires_reconciliation")

    if host.main_sha() != plan["merge_sha"] and recovery["phase"] not in {
        "merged",
        "verifying_recovery",
        "verified",
    }:
        return hold("recovery_base_moved")
    if not _policy_matches(manifest, host.policy()):
        return hold("recovery_policy_changed")

    if recovery["phase"] in {
        "materializing",
        "validating",
        "committing",
        "creating_pr",
    }:
        return hold("uncertain_recovery_execution_requires_reconciliation")

    if recovery["phase"] == "not_started":
        repository.preflight(manifest)
        _require(not worktree.exists(), "foreign recovery worktree exists")
        refs = repository.git(
            "for-each-ref", "--format=%(refname)", f"refs/heads/{recovery['branch']}"
        )
        _require(not refs, "foreign recovery branch exists")
        repository.create_worktree(worktree, recovery["branch"], plan["merge_sha"])
        repository.validate_worktree(worktree, recovery["branch"])
        repository.baseline(worktree, manifest)
        recovery["phase"] = "materializing"
        save(phase="recovery_materializing")
        payload = provider.materialize_recovery(
            copy.deepcopy(plan["recovery"]["materializer"]["inputs"])
        )
        _require(
            isinstance(payload, Mapping)
            and set(payload) == set(manifest["allowed_paths"]),
            "recovery payload differs from allowlist",
        )
        encoded = {name: _content(text) for name, text in payload.items()}
        for name, raw in encoded.items():
            _require(
                __import__("hashlib").sha256(raw).hexdigest()
                == manifest["changes"][name]["after_sha256"],
                "recovery content differs from frozen plan",
            )
        for name, raw in encoded.items():
            target = _target(worktree, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        recovery["changed_paths"] = repository.diff_guard(worktree, manifest)
        recovery["phase"] = "materialized"
        save(phase="recovery_materialized")

    repository.validate_worktree(worktree, recovery["branch"])
    if recovery["phase"] == "materialized":
        repository.diff_guard(worktree, manifest)
        recovery["phase"] = "validating"
        save(phase="recovery_validating")
        for contract_id in manifest["validation"]:
            _require(
                provider.validate_recovery_candidate(worktree, contract_id) is True,
                "recovery focused validation failed",
            )
            recovery["validation_refs"].append(contract_id)
        repository.diff_guard(worktree, manifest)
        recovery["phase"] = "validated"
        save(phase="recovery_validated")

    if recovery["phase"] == "validated":
        repository.diff_guard(worktree, manifest)
        recovery["phase"] = "committing"
        save(phase="recovery_committing")
        repository.git("add", "--", *manifest["allowed_paths"], cwd=worktree)
        repository.git(
            "commit",
            "-m",
            f"Forward repair invalid promotion {plan['plan_fingerprint']}",
            cwd=worktree,
        )
        recovery["head_sha"] = repository.git("rev-parse", "HEAD", cwd=worktree)
        repository.diff_guard(worktree, manifest, committed=True)
        recovery["phase"] = "committed"
        save(phase="recovery_committed")

    if recovery["phase"] == "committed":
        _require(
            repository.head(recovery["branch"]) == recovery["head_sha"],
            "recovery branch head changed",
        )
        remote = host.pushed_head(recovery["branch"])
        _require(
            remote in {None, recovery["head_sha"]}, "recovery remote branch differs"
        )
        if remote is None:
            host.push(repository, recovery["branch"], recovery["head_sha"])
        recovery["pushed_head_sha"] = recovery["head_sha"]
        recovery["phase"] = "pushed"
        save(phase="recovery_pushed")

    if recovery["phase"] == "pushed":
        pr = host.find_pr(recovery["branch"])
        if pr is None:
            pr = host.create_bounded_pr(
                recovery["branch"],
                recovery["head_sha"],
                plan["merge_sha"],
                title=f"Forward repair invalid analysis promotion ({plan['plan_fingerprint'][:12]})",
                body="Bounded S8 forward repair to the verified last-known-good analysis baseline.",
            )
        recovery["pr_number"] = pr["number"]
        _require(_recovery_identity(state, pr, plan), "recovery PR identity mismatch")
        recovery["pr_head_sha"] = pr["head_sha"]
        recovery["phase"] = "pr_open"
        save(phase="recovery_pr_open")

    _require(recovery["phase"] == "pr_open", "unknown recovery phase")
    policy = host.policy()
    if not _policy_matches(manifest, policy):
        return hold("recovery_policy_changed")
    snapshot = host.snapshot(recovery["pr_number"])
    eligible, observed = _eligible(
        recovery, manifest, snapshot, policy, review_evidence
    )
    recovery["observed_checks"] = observed
    recovery["pr_head_sha"] = snapshot["head_sha"]
    if not eligible:
        return hold("recovery_final_head_gates_not_satisfied")
    if host.main_sha() != plan["merge_sha"] or host.policy() != policy:
        return hold("recovery_base_or_policy_changed_before_merge")
    final = host.snapshot(recovery["pr_number"])
    eligible, observed = _eligible(recovery, manifest, final, policy, review_evidence)
    recovery["observed_checks"] = observed
    if not eligible:
        return hold("recovery_final_head_changed_before_merge")
    recovery["repository_merge_eligible"] = True
    recovery["phase"] = "merging"
    save(phase="recovery_merging")
    host.merge(
        recovery["pr_number"], recovery["head_sha"], manifest["policy"]["merge_method"]
    )
    merged = host.snapshot(recovery["pr_number"])
    _require(
        _recovery_identity(state, merged, plan), "recovery merged PR identity mismatch"
    )
    _require(
        merged["merged"] is True
        and isinstance(merged["merge_sha"], str)
        and _HEX40.fullmatch(merged["merge_sha"]),
        "recovery merge evidence incomplete",
    )
    recovery["merge_sha"] = merged["merge_sha"]
    _require(
        host.verify_merge(
            recovery["pr_number"], recovery["head_sha"], recovery["merge_sha"]
        )
        is True,
        "recovery merge not verified",
    )
    recovery["phase"] = "merged"
    recovery["repository_merge_eligible"] = True
    return save(phase="recovery_merged", status="running")


def run_post_merge(
    *,
    source_state_path,
    promotion_manifest,
    promotion_provider,
    promotion_attempt_path,
    plan,
    provider: PostMergeProvider,
    repository: GitRepository,
    host: PostMergeHost,
    verification_root,
    worktree_root,
    attempt_root,
    baseline_state_path,
    review_evidence=None,
):
    """Advance one durable S8 verification/acceptance/recovery attempt."""
    source, promotion_manifest, promotion_attempt = _promotion_inputs(
        source_state_path=source_state_path,
        promotion_manifest=promotion_manifest,
        promotion_provider=promotion_provider,
        promotion_attempt_path=promotion_attempt_path,
    )
    plan = validate_plan(
        plan,
        source=source,
        promotion_manifest=promotion_manifest,
        promotion_attempt=promotion_attempt,
        provider=provider,
    )
    _require(
        getattr(host, "repository_id", plan["repository_id"]) == plan["repository_id"],
        "host repository identity mismatch",
    )
    if hasattr(host, "repository"):
        _require(
            Path(host.repository).resolve() == repository.path,
            "host checkout differs from post-merge repository",
        )

    attempt_dir = Path(attempt_root).resolve() / plan["plan_fingerprint"]
    verification_root = Path(verification_root).resolve()
    worktree_root = Path(worktree_root).resolve()
    baseline_path = Path(baseline_state_path).resolve()
    for local in (attempt_dir, verification_root, worktree_root, baseline_path.parent):
        _require(
            not local.is_relative_to(repository.path),
            "S8 host storage must be outside repository",
        )
    state_path = attempt_dir / "attempt.json"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_lock = Path(str(baseline_path) + ".lock")
    attempt_lock = attempt_dir / "execution.lock"

    with _exclusive_lock(
        baseline_lock,
        plan["plan_fingerprint"],
        message="baseline lineage already executing or orphan baseline lock requires reconciliation",
    ):
        if not state_path.exists() and baseline_path.exists():
            existing_baseline = load_baseline_lineage(baseline_path)
            _require(
                existing_baseline["domain"] == plan["domain"]
                and existing_baseline["current"]["candidate"]
                == plan["previous_baseline_candidate"]
                and existing_baseline["current"]["repository_sha"]
                == promotion_manifest["expected_base_sha"],
                "baseline generation or lineage advanced beyond this promotion",
            )
        if state_path.exists():
            state = _load_attempt(state_path, plan, promotion_attempt)
        else:
            state = _new_attempt(plan, promotion_attempt)

        with _exclusive_lock(
            attempt_lock,
            plan["plan_fingerprint"],
            message="S8 attempt already executing or orphan lock requires reconciliation",
        ):
            if state_path.exists():
                state = _load_attempt(state_path, plan, promotion_attempt)
            else:
                _save_attempt(state_path, state)
            return _advance_post_merge(
                state_path=state_path,
                state=state,
                source=source,
                promotion_manifest=promotion_manifest,
                promotion_attempt=promotion_attempt,
                plan=plan,
                provider=provider,
                repository=repository,
                host=host,
                verification_root=verification_root,
                worktree_root=worktree_root,
                baseline_path=baseline_path,
                review_evidence=review_evidence,
            )


def _advance_post_merge(
    *,
    state_path: Path,
    state: dict[str, Any],
    source: Mapping[str, Any],
    promotion_manifest: Mapping[str, Any],
    promotion_attempt: Mapping[str, Any],
    plan: Mapping[str, Any],
    provider: PostMergeProvider,
    repository: GitRepository,
    host: PostMergeHost,
    verification_root: Path,
    worktree_root: Path,
    baseline_path: Path,
    review_evidence: Mapping[str, Any] | None,
) -> dict[str, Any]:
    def save(
        *,
        phase: str | None = None,
        status: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        if phase is not None:
            state["phase"] = phase
        if status is not None:
            state["status"] = status
        state["reason"] = reason
        return _save_attempt(state_path, state)

    def hold(reason: str, *, status: str = "hold") -> dict[str, Any]:
        return save(status=status, reason=reason)

    try:
        if state["status"] in {"accepted", "recovered"}:
            try:
                terminal_baseline = load_baseline_lineage(baseline_path)
            except AnalysisPostMergeError:
                return hold("terminal_baseline_invalid", status="controlled_failure")
            expected_candidate = (
                plan["promoted_candidate"]
                if state["status"] == "accepted"
                else plan["previous_baseline_candidate"]
            )
            expected_repository_sha = (
                plan["merge_sha"]
                if state["status"] == "accepted"
                else state["recovery"]["merge_sha"]
            )
            terminal_ok = (
                terminal_baseline["domain"] == plan["domain"]
                and terminal_baseline["current"]["candidate"] == expected_candidate
                and terminal_baseline["current"]["repository_sha"]
                == expected_repository_sha
                and terminal_baseline["generation"]
                == state["baseline_generation_start"] + 1
                and terminal_baseline["current"]["baseline_fingerprint"]
                == state["accepted_baseline_fingerprint"]
                and terminal_baseline["last_known_good"] is not None
                and terminal_baseline["last_known_good"]["baseline_fingerprint"]
                == state["last_known_good_fingerprint"]
                and terminal_baseline["source_plan_fingerprint"]
                == plan["plan_fingerprint"]
                and terminal_baseline["source_promotion_attempt_fingerprint"]
                == promotion_attempt["state_fingerprint"]
            )
            if not terminal_ok:
                return hold("terminal_baseline_invalid", status="controlled_failure")
            return state
        if state["status"] == "controlled_failure":
            return state
        if state["phase"] in {
            "verifying_baseline",
            "verifying_promoted",
            "verifying_recovery",
        }:
            return hold("uncertain_verification_requires_reconciliation")

        live_main = host.main_sha()
        if state["phase"] in {"prepared", "baseline_ready", "promoted_verified"}:
            if live_main != plan["merge_sha"]:
                return hold("promotion_merge_not_live")
            if (
                host.verify_merge(
                    promotion_attempt["pr_number"],
                    promotion_attempt["head_sha"],
                    promotion_attempt["merge_sha"],
                )
                is not True
            ):
                return hold("promotion_merge_not_live")

        baseline: dict[str, Any] | None = None
        if baseline_path.exists():
            baseline = load_baseline_lineage(baseline_path)
            _require(
                baseline["domain"] == plan["domain"], "baseline lineage domain mismatch"
            )

            # The baseline artifact is the atomic authority. If the process died
            # after writing it but before advancing the attempt phase, adopt only
            # the exact state that the interrupted phase was permitted to write.
            if state["phase"] == "accepting":
                _require(
                    baseline["current"]["candidate"] == plan["promoted_candidate"]
                    and baseline["current"]["repository_sha"] == plan["merge_sha"]
                    and baseline["generation"] == state["baseline_generation_start"] + 1
                    and baseline["last_known_good"] is not None
                    and baseline["last_known_good"]["candidate"]
                    == plan["previous_baseline_candidate"]
                    and baseline["last_known_good"]["repository_sha"]
                    == promotion_manifest["expected_base_sha"],
                    "accepted baseline reconciliation mismatch",
                )
                state["accepted_baseline_fingerprint"] = baseline["current"][
                    "baseline_fingerprint"
                ]
                state["last_known_good_fingerprint"] = baseline["last_known_good"][
                    "baseline_fingerprint"
                ]
                return save(phase="accepted", status="accepted")

            if state["phase"] == "accepting_recovery":
                _require(
                    baseline["current"]["candidate"]
                    == plan["previous_baseline_candidate"]
                    and baseline["current"]["repository_sha"]
                    == state["recovery"]["merge_sha"]
                    and baseline["generation"] == state["baseline_generation_start"] + 1
                    and baseline["last_known_good"] is not None
                    and baseline["last_known_good"]["candidate"]
                    == plan["previous_baseline_candidate"]
                    and baseline["last_known_good"]["repository_sha"]
                    == promotion_manifest["expected_base_sha"],
                    "recovered baseline reconciliation mismatch",
                )
                state["accepted_baseline_fingerprint"] = baseline["current"][
                    "baseline_fingerprint"
                ]
                state["last_known_good_fingerprint"] = baseline["last_known_good"][
                    "baseline_fingerprint"
                ]
                return save(phase="recovered", status="recovered")

            if state["phase"] == "bootstrapping_baseline":
                _require(
                    baseline["current"]["candidate"]
                    == plan["previous_baseline_candidate"]
                    and baseline["current"]["repository_sha"]
                    == promotion_manifest["expected_base_sha"]
                    and baseline["generation"] == 0
                    and baseline["last_known_good"] is None,
                    "bootstrapped baseline reconciliation mismatch",
                )
                state["baseline_before_fingerprint"] = baseline["state_fingerprint"]
                state["baseline_generation_start"] = baseline["generation"]
                state["last_known_good_fingerprint"] = baseline["current"][
                    "baseline_fingerprint"
                ]
                save(phase="baseline_ready")

            _require(
                baseline["current"]["candidate"] == plan["previous_baseline_candidate"]
                and baseline["current"]["repository_sha"]
                == promotion_manifest["expected_base_sha"],
                "baseline lineage does not match promotion previous baseline",
            )
            if state["baseline_before_fingerprint"] is None:
                state["baseline_before_fingerprint"] = baseline["state_fingerprint"]
                state["baseline_generation_start"] = baseline["generation"]
                state["last_known_good_fingerprint"] = baseline["current"][
                    "baseline_fingerprint"
                ]
                save()
            else:
                _require(
                    baseline["state_fingerprint"]
                    == state["baseline_before_fingerprint"]
                    and baseline["generation"] == state["baseline_generation_start"],
                    "baseline generation or lineage changed",
                )

        if baseline is None:
            if state["phase"] == "prepared":
                save(phase="verifying_baseline")
                refs = _safe_detached_verify(
                    repository=repository,
                    repository_sha=promotion_manifest["expected_base_sha"],
                    candidate=plan["previous_baseline_candidate"],
                    plan=plan,
                    provider=provider,
                    worktree=worktree_root
                    / f"verify-baseline-{plan['plan_fingerprint'][:16]}",
                    evidence_root=verification_root / "baseline",
                )
                state["baseline_verification_refs"] = refs
                if not _all_pass(refs):
                    return save(
                        phase="baseline_verification_failed",
                        status="hold",
                        reason="last_known_good_not_verified",
                    )
                previous = _baseline_ref(
                    domain=plan["domain"],
                    candidate=plan["previous_baseline_candidate"],
                    repository_sha=promotion_manifest["expected_base_sha"],
                    verification_refs=refs,
                    policy_fingerprint=plan["plan_fingerprint"],
                    source_fingerprint=promotion_attempt["state_fingerprint"],
                )
                baseline = _baseline_state(
                    domain=plan["domain"],
                    current=previous,
                    last_known_good=None,
                    generation=0,
                    source_plan_fingerprint=plan["plan_fingerprint"],
                    source_promotion_attempt_fingerprint=promotion_attempt[
                        "state_fingerprint"
                    ],
                )
                save(phase="bootstrapping_baseline")
                save_baseline_lineage(baseline_path, baseline)
                state["baseline_before_fingerprint"] = baseline["state_fingerprint"]
                state["baseline_generation_start"] = 0
                state["last_known_good_fingerprint"] = previous["baseline_fingerprint"]
                save(phase="baseline_ready")
            elif state["phase"] == "baseline_verification_failed":
                return state
            elif state["phase"] == "bootstrapping_baseline" and baseline_path.exists():
                baseline = load_baseline_lineage(baseline_path)
                _require(
                    baseline["current"]["candidate"]
                    == plan["previous_baseline_candidate"],
                    "bootstrapped baseline mismatch",
                )
                state["baseline_before_fingerprint"] = baseline["state_fingerprint"]
                state["baseline_generation_start"] = baseline["generation"]
                state["last_known_good_fingerprint"] = baseline["current"][
                    "baseline_fingerprint"
                ]
                save(phase="baseline_ready")
            else:
                return hold("baseline_lineage_reconciliation_required")

        if state["phase"] == "baseline_ready":
            save(phase="verifying_promoted")
            refs = _safe_detached_verify(
                repository=repository,
                repository_sha=plan["merge_sha"],
                candidate=plan["promoted_candidate"],
                plan=plan,
                provider=provider,
                worktree=worktree_root
                / f"verify-promoted-{plan['plan_fingerprint'][:16]}",
                evidence_root=verification_root / "promoted",
            )
            state["promoted_verification_refs"] = refs
            if _all_pass(refs):
                save(phase="promoted_verified")
            else:
                state["invalid_promotion"] = True
                save(
                    phase="recovery_required",
                    status="running",
                    reason="post_merge_verification_failed",
                )

        if state["phase"] == "promoted_verified":
            if host.main_sha() != plan["merge_sha"]:
                return hold("main_moved_before_baseline_acceptance")
            current_baseline = load_baseline_lineage(baseline_path)
            _require(
                current_baseline["state_fingerprint"]
                == state["baseline_before_fingerprint"]
                and current_baseline["generation"]
                == state["baseline_generation_start"],
                "baseline generation or lineage changed before acceptance",
            )
            promoted = _baseline_ref(
                domain=plan["domain"],
                candidate=plan["promoted_candidate"],
                repository_sha=plan["merge_sha"],
                verification_refs=state["promoted_verification_refs"],
                policy_fingerprint=plan["plan_fingerprint"],
                source_fingerprint=promotion_attempt["state_fingerprint"],
            )
            accepted = _baseline_state(
                domain=plan["domain"],
                current=promoted,
                last_known_good=current_baseline["current"],
                generation=current_baseline["generation"] + 1,
                source_plan_fingerprint=plan["plan_fingerprint"],
                source_promotion_attempt_fingerprint=promotion_attempt[
                    "state_fingerprint"
                ],
            )
            save(phase="accepting")
            save_baseline_lineage(baseline_path, accepted)
            state["accepted_baseline_fingerprint"] = promoted["baseline_fingerprint"]
            state["last_known_good_fingerprint"] = current_baseline["current"][
                "baseline_fingerprint"
            ]
            return save(phase="accepted", status="accepted")

        if state["phase"] == "accepting":
            accepted = load_baseline_lineage(baseline_path)
            _require(
                accepted["current"]["candidate"] == plan["promoted_candidate"]
                and accepted["current"]["repository_sha"] == plan["merge_sha"]
                and accepted["generation"] == state["baseline_generation_start"] + 1,
                "accepted baseline reconciliation mismatch",
            )
            state["accepted_baseline_fingerprint"] = accepted["current"][
                "baseline_fingerprint"
            ]
            state["last_known_good_fingerprint"] = accepted["last_known_good"][
                "baseline_fingerprint"
            ]
            return save(phase="accepted", status="accepted")

        if state["phase"] in {
            "recovery_required",
            "recovery_materializing",
            "recovery_materialized",
            "recovery_validating",
            "recovery_validated",
            "recovery_committing",
            "recovery_committed",
            "recovery_pushed",
            "recovery_pr_open",
            "recovery_merging",
            "recovery_merged",
        }:
            current_baseline = load_baseline_lineage(baseline_path)
            _require(
                current_baseline["state_fingerprint"]
                == state["baseline_before_fingerprint"],
                "baseline lineage changed during recovery",
            )
            if (
                state["recovery"]["phase"] == "not_started"
                and host.main_sha() != plan["merge_sha"]
            ):
                return hold("recovery_base_moved")
            if state["recovery"]["phase"] != "merged":
                _advance_recovery(
                    state_path=state_path,
                    state=state,
                    plan=plan,
                    provider=provider,
                    repository=repository,
                    host=host,
                    worktree=worktree_root
                    / f"recovery-{plan['plan_fingerprint'][:24]}",
                    review_evidence=review_evidence,
                )
                if state["recovery"]["phase"] != "merged":
                    return state
            save(phase="verifying_recovery", status="running")
            refs = _safe_detached_verify(
                repository=repository,
                repository_sha=state["recovery"]["merge_sha"],
                candidate=current_baseline["current"]["candidate"],
                plan=plan,
                provider=provider,
                worktree=worktree_root
                / f"verify-recovery-{plan['plan_fingerprint'][:16]}",
                evidence_root=verification_root / "recovery",
            )
            state["recovery_verification_refs"] = refs
            if not _all_pass(refs):
                return save(
                    phase="recovery_verification_failed",
                    status="controlled_failure",
                    reason="repaired_repository_verification_failed",
                )
            if host.main_sha() != state["recovery"]["merge_sha"]:
                return hold("main_moved_before_recovery_acceptance")
            recovered_ref = _baseline_ref(
                domain=plan["domain"],
                candidate=current_baseline["current"]["candidate"],
                repository_sha=state["recovery"]["merge_sha"],
                verification_refs=refs,
                policy_fingerprint=plan["plan_fingerprint"],
                source_fingerprint=promotion_attempt["state_fingerprint"],
            )
            recovered_baseline = _baseline_state(
                domain=plan["domain"],
                current=recovered_ref,
                last_known_good=current_baseline["current"],
                generation=current_baseline["generation"] + 1,
                source_plan_fingerprint=plan["plan_fingerprint"],
                source_promotion_attempt_fingerprint=promotion_attempt[
                    "state_fingerprint"
                ],
            )
            save(phase="accepting_recovery", status="running")
            save_baseline_lineage(baseline_path, recovered_baseline)
            state["accepted_baseline_fingerprint"] = recovered_ref[
                "baseline_fingerprint"
            ]
            state["last_known_good_fingerprint"] = current_baseline["current"][
                "baseline_fingerprint"
            ]
            return save(phase="recovered", status="recovered")

        if state["phase"] == "recovered":
            return state
        raise AnalysisPostMergeError("unknown S8 attempt phase")
    except InfrastructureError:
        return hold("host_infrastructure_unavailable", status="infrastructure_hold")
    except (
        PromotionError,
        AnalysisPostMergeError,
        OSError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return hold(
            "post_merge_or_recovery_validation_failed", status="controlled_failure"
        )


__all__ = [
    "ATTEMPT_TYPE",
    "BASELINE_TYPE",
    "PLAN_TYPE",
    "VERSION",
    "AnalysisPostMergeError",
    "PostMergeHost",
    "PostMergeProvider",
    "load_baseline_lineage",
    "run_post_merge",
    "save_baseline_lineage",
    "validate_baseline_lineage",
    "validate_plan",
]
