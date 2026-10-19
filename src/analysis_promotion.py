"""S7: bounded domain payload → isolated Git/PR → exact-head governed merge.

This optional tool composes S6 persistence and #956 identity helpers. Providers
are trusted domain code; a manifest never becomes executable code or a command.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Mapping, Protocol

from src.analysis_eval_artifact import assert_portable_value, fingerprint
from src.analysis_locked_holdout import (
    _sync_entry,
    _write_atomic,
    validate_locked_result,
)
from src.analysis_promotion_host import InfrastructureError
from src.analysis_quality_loop_state import load_state

MANIFEST_TYPE = "sample-brain.analysis-promotion-manifest.v1"
ATTEMPT_TYPE = "sample-brain.analysis-promotion-attempt.v1"
VERSION = "1.0.0"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_HEX40 = re.compile(r"[0-9a-f]{40}")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SECRET = re.compile(
    r"(?i)(?:gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]+|sk-[A-Za-z0-9]{16,}|-----BEGIN .*PRIVATE KEY|(?:password|credential|api[_-]?key|token|secret)\s*[\"']?\s*[:=]\s*[\"']?[^\s\"']+)"
)
_LOCAL = re.compile(
    r"(?i)(?:[A-Z]:[\\/]|\\\\[^\s]+|file://|(?:^|[\s\"'=:(])/(?!/)[^\s\"']+)"
)
_PROTECTED_PARTS = {
    ".git",
    ".github",
    ".ssh",
    ".aws",
    ".codex",
    ".cursor",
    ".venv",
    "__pycache__",
    "private",
    "secrets",
    "credentials",
    "cache",
    "caches",
    "models",
    "indexes",
    "embeddings",
    "reports",
    "logs",
}
_PROTECTED_NAMES = {
    "security.md",
    "codeowners",
    ".gitleaks.toml",
    "agents.md",
    ".env",
    "shared.working.memory.md",
}
_TEXT_EXTENSIONS = {
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".txt",
    ".md",
    ".py",
}


class PromotionError(ValueError):
    """Invalid authority, provenance, bounded change or durable state."""


class PromotionProvider(Protocol):
    domain: str
    materializer_id: str
    materializer_version: str

    def validate_plan(
        self, manifest: Mapping[str, Any], locked_result: Mapping[str, Any]
    ) -> bool: ...
    def materialize(self, inputs: Mapping[str, Any]) -> Mapping[str, str]: ...
    def validate_candidate(self, worktree: Path, contract_id: str) -> bool: ...


class PromotionHost(Protocol):
    def main_sha(self) -> str: ...
    def policy(self) -> dict: ...
    def pushed_head(self, branch: str) -> str | None: ...
    def push(self, repository: GitRepository, branch: str, head_sha: str) -> None: ...
    def find_pr(self, branch: str) -> dict | None: ...
    def create_pr(self, branch: str, head_sha: str, base_sha: str) -> dict: ...
    def snapshot(self, number: int) -> dict: ...
    def merge(self, number: int, expected_head_sha: str, method: str) -> None: ...
    def verify_merge(self, number: int, head_sha: str, merge_sha: str) -> bool: ...


def _require(condition, message):
    if not condition:
        raise PromotionError(message)


def _hex(value, pattern=_HEX64):
    _require(
        isinstance(value, str) and pattern.fullmatch(value),
        "invalid fingerprint or SHA",
    )


def _path(value, *, protected=True):
    _require(isinstance(value, str) and value and len(value) <= 240, "invalid path")
    parts = value.split("/")
    _require(
        all(
            re.fullmatch(r"[A-Za-z0-9_.-]+", p)
            and p not in {".", ".."}
            and not p.endswith((".", " "))
            and not re.fullmatch(
                r"(?i)(?:con|prn|aux|nul|com[0-9]|lpt[0-9])(?:\..*)?", p
            )
            for p in parts
        ),
        "invalid portable path",
    )
    if protected:
        _require(
            not any(p.lower() in _PROTECTED_PARTS for p in parts)
            and parts[-1].lower() not in _PROTECTED_NAMES
            and not parts[-1].lower().startswith(".env.")
            and Path(value).suffix.lower() in _TEXT_EXTENSIONS,
            "forbidden private, binary or governance path",
        )
    return value


def _safe(value):
    assert_portable_value(value)
    if isinstance(value, str):
        _require(
            not _SECRET.search(value) and not _LOCAL.search(value),
            "private or secret content",
        )
    elif isinstance(value, Mapping):
        for key, child in value.items():
            _safe(key)
            _safe(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _safe(child)


def _content(value):
    _require(
        isinstance(value, str) and len(value.encode("utf-8")) <= 100_000,
        "bounded UTF-8 text required",
    )
    _require(
        not any(ord(c) < 32 and c not in "\n\r\t" for c in value),
        "binary text forbidden",
    )
    _safe(value)
    return value.encode("utf-8")


def _read(path):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        _require(isinstance(value, dict), "document must be an object")
        return value
    except (OSError, ValueError) as exc:
        raise PromotionError("missing or invalid committed document") from exc


def load_promotion_source(source_state_path):
    """Read only a complete committed S6 invocation against its unchanged freeze."""
    path = Path(source_state_path)
    state = load_state(path)
    result = validate_locked_result(
        _read(path.with_name(path.name + ".locked-result.json"))
    )
    claim = _read(path.with_name(path.name + ".locked-claim.json"))
    decision = result["decision"]
    _require(
        state["loop_status"] == "frozen"
        and state["last_decision"]["next_action"] == "freeze_candidate",
        "source must be frozen",
    )
    expected_claim = {
        "freeze_state_fingerprint": state["state_fingerprint"],
        "request_fingerprint": result["request_fingerprint"],
        "evidence_fingerprint": decision["evidence"]["evidence_fingerprint"],
        "gate_verdict": "PASS",
        "decision_token": "PROMOTION_CANDIDATE_IDENTIFIED",
        "next_action": "handoff_promotion_controller",
    }
    _require(
        claim == expected_claim
        and fingerprint(claim) == result["invocation_fingerprint"],
        "committed claim provenance mismatch",
    )
    _require(
        result["freeze_state_fingerprint"] == state["state_fingerprint"]
        and result["domain"] == state["domain"]
        and result["baseline_candidate"] == state["baseline_candidate"]
        and result["current_candidate"] == state["active_candidate"],
        "committed freeze identity mismatch",
    )
    _require(
        decision["artifact_version"] == "1.1.0"
        and decision["decision_status"] == "ready"
        and decision["decision_token"] == "PROMOTION_CANDIDATE_IDENTIFIED"
        and decision["next_action"] == "handoff_promotion_controller"
        and decision["evidence"]["gate_decision"]["verdict"] == "PASS"
        and decision["partition"]["role"] in {"test", "holdout"}
        and decision["production_authorized"] is False,
        "S6 input is not eligible for promotion",
    )
    return result


def validate_manifest(manifest, result, provider):
    keys = {
        "document_type",
        "artifact_version",
        "domain",
        "baseline_candidate",
        "current_candidate",
        "locked_result_fingerprint",
        "decision_fingerprint",
        "evidence_fingerprint",
        "expected_base_sha",
        "repository_id",
        "allowed_paths",
        "forbidden_paths",
        "materializer",
        "changes",
        "change_fingerprint",
        "validation",
        "policy",
        "policy_fingerprint",
        "manifest_fingerprint",
    }
    _require(
        isinstance(manifest, dict) and set(manifest) == keys, "invalid manifest fields"
    )
    _safe(manifest)
    _require(
        manifest["document_type"] == MANIFEST_TYPE
        and manifest["artifact_version"] == VERSION,
        "unknown manifest version",
    )
    for key in keys:
        if key.endswith("fingerprint"):
            _hex(manifest[key])
    _hex(manifest["expected_base_sha"], _HEX40)
    _require(
        re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", manifest["repository_id"]),
        "invalid repository identity",
    )
    _require(
        fingerprint({k: v for k, v in manifest.items() if k != "manifest_fingerprint"})
        == manifest["manifest_fingerprint"],
        "manifest fingerprint mismatch",
    )
    for key in ("domain", "baseline_candidate", "current_candidate"):
        _require(manifest[key] == result[key], "manifest candidate identity mismatch")
    _require(
        manifest["locked_result_fingerprint"] == result["result_fingerprint"]
        and manifest["decision_fingerprint"]
        == result["decision"]["decision_fingerprint"]
        and manifest["evidence_fingerprint"]
        == result["decision"]["evidence"]["evidence_fingerprint"],
        "manifest evidence mismatch",
    )
    allowed, forbidden = manifest["allowed_paths"], manifest["forbidden_paths"]
    _require(
        isinstance(allowed, list)
        and 0 < len(allowed) <= 100
        and all(isinstance(p, str) for p in allowed)
        and len({p.lower() for p in allowed}) == len(allowed),
        "invalid path allowlist",
    )
    _require(isinstance(forbidden, list), "invalid forbidden paths")
    for path in forbidden:
        _path(path, protected=False)
    for path in allowed:
        _path(path)
        _require(
            not any(
                path.lower() == p.lower() or path.lower().startswith(p.lower() + "/")
                for p in forbidden
            ),
            "forbidden path",
        )
    changes = manifest["changes"]
    _require(
        isinstance(changes, dict) and set(changes) == set(allowed),
        "exact change allowlist required",
    )
    for change in changes.values():
        _require(
            isinstance(change, dict)
            and set(change) == {"before_sha256", "after_sha256"},
            "invalid change",
        )
        if change["before_sha256"] is not None:
            _hex(change["before_sha256"])
        _hex(change["after_sha256"])
        _require(change["before_sha256"] != change["after_sha256"], "empty change")
    _require(
        fingerprint(changes) == manifest["change_fingerprint"],
        "change fingerprint mismatch",
    )
    materializer = manifest["materializer"]
    _require(
        isinstance(materializer, dict)
        and set(materializer) == {"id", "version", "inputs"}
        and isinstance(materializer["inputs"], dict),
        "missing materializer",
    )
    _require(
        provider.domain == manifest["domain"]
        and provider.materializer_id == materializer["id"]
        and provider.materializer_version == materializer["version"],
        "unknown materializer identity",
    )
    validation = manifest["validation"]
    _require(
        isinstance(validation, list)
        and validation
        and len(set(validation)) == len(validation)
        and all(isinstance(x, str) and _ID.fullmatch(x) for x in validation),
        "invalid validation contract",
    )
    policy = manifest["policy"]
    _require(
        isinstance(policy, dict)
        and set(policy)
        == {"version", "required_checks", "merge_method", "review_gate"},
        "invalid policy",
    )
    _require(
        policy["version"] == VERSION
        and policy["merge_method"] in {"squash", "rebase"}
        and policy["review_gate"] == "all_feedback_dispositioned.v1",
        "unsupported merge policy",
    )
    checks = policy["required_checks"]
    _require(
        isinstance(checks, list) and checks and len(checks) <= 100,
        "required checks missing",
    )
    for check in checks:
        _require(
            isinstance(check, dict)
            and set(check) == {"name", "app_id"}
            and isinstance(check["name"], str)
            and check["name"].strip()
            and type(check["app_id"]) is int
            and check["app_id"] > 0,
            "invalid required check",
        )
    _require(
        len({(c["name"], c["app_id"]) for c in checks}) == len(checks),
        "duplicate required checks",
    )
    _require(
        fingerprint(policy) == manifest["policy_fingerprint"],
        "policy fingerprint mismatch",
    )
    _require(
        provider.validate_plan(
            json.loads(json.dumps(manifest)), json.loads(json.dumps(result))
        )
        is True,
        "domain rejected promotion plan",
    )
    return json.loads(json.dumps(manifest))


class GitRepository:
    def __init__(self, path):
        self.path = Path(path).resolve()

    def git(self, *args, cwd=None):
        try:
            return subprocess.run(
                [
                    "git",
                    "-c",
                    "core.fsmonitor=false",
                    "-C",
                    str(cwd or self.path),
                    *args,
                ],
                check=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise PromotionError("Git operation rejected or unavailable") from exc

    def head(self, ref="HEAD"):
        return self.git("rev-parse", "--verify", ref)

    def preflight(self, manifest):
        _require(
            not self.git(
                "status", "--porcelain", "--untracked-files=all", "--ignored=matching"
            ),
            "source repository must be clean, including ignored files",
        )
        _require(
            self.head("refs/remotes/origin/main") == manifest["expected_base_sha"],
            "repository baseline moved",
        )
        remote = self.git("remote", "get-url", "origin")
        identity = manifest["repository_id"]
        _require(
            remote
            in {
                f"https://github.com/{identity}",
                f"https://github.com/{identity}.git",
                f"git@github.com:{identity}.git",
            },
            "origin repository mismatch",
        )

    def create_worktree(self, path, branch, base):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git("worktree", "add", "-b", branch, str(path), base)

    def validate_worktree(self, path, branch):
        _require(
            path.is_dir() and self.git("branch", "--show-current", cwd=path) == branch,
            "isolated worktree identity mismatch",
        )
        _require(
            Path(self.git("rev-parse", "--show-toplevel", cwd=path)).resolve()
            == path.resolve(),
            "worktree root mismatch",
        )
        _require(
            Path(
                self.git(
                    "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=path
                )
            ).resolve()
            == Path(
                self.git("rev-parse", "--path-format=absolute", "--git-common-dir")
            ).resolve(),
            "foreign worktree",
        )

    def baseline(self, path, manifest):
        for name, change in manifest["changes"].items():
            target = _target(path, name)
            before = change["before_sha256"]
            _require(
                not target.exists() if before is None else target.is_file(),
                "baseline file missing or unexpectedly exists",
            )
            if before is not None:
                mode = self.git("ls-files", "--stage", "--", name, cwd=path).split()
                _require(
                    mode and mode[0] in {"100644", "100755"},
                    "unsupported baseline file mode",
                )
                _require(
                    hashlib.sha256(target.read_bytes()).hexdigest() == before,
                    "baseline content differs from frozen change",
                )

    def diff_guard(self, path, manifest, *, committed=False):
        base = manifest["expected_base_sha"]
        paths = set(
            self.git(
                "diff", "--name-only", "--no-renames", base, "--", cwd=path
            ).splitlines()
        )
        untracked = set(
            self.git(
                "ls-files", "--others", "--exclude-standard", cwd=path
            ).splitlines()
        )
        ignored = set(
            self.git(
                "ls-files", "--others", "--ignored", "--exclude-standard", cwd=path
            ).splitlines()
        )
        _require(
            paths | untracked | ignored == set(manifest["allowed_paths"]),
            "diff path set differs from exact allowlist",
        )
        for entry in self.git(
            "diff", "--raw", "--no-renames", base, "--", cwd=path
        ).splitlines():
            metadata, name = entry.split("\t", 1)
            before_mode, after_mode = metadata.split()[:2]
            before_mode = before_mode.removeprefix(":")
            expected_mode = (
                "100644"
                if manifest["changes"][name]["before_sha256"] is None
                else before_mode
            )
            _require(
                after_mode == expected_mode and after_mode in {"100644", "100755"},
                "unexpected candidate file mode",
            )
        for name, change in manifest["changes"].items():
            target = _target(path, name)
            _require(target.is_file(), "expected candidate file missing")
            raw = target.read_bytes()
            _content(raw.decode("utf-8"))
            _require(
                hashlib.sha256(raw).hexdigest() == change["after_sha256"],
                "candidate content identity mismatch",
            )
        # Reject executable-bit/type changes, symlinks and submodules as well.
        self.git("diff", "--check", base, cwd=path)
        if committed:
            _require(
                not self.git(
                    "status",
                    "--porcelain",
                    "--untracked-files=all",
                    "--ignored=matching",
                    cwd=path,
                ),
                "committed worktree changed",
            )
            _require(
                self.git("rev-parse", "HEAD^", cwd=path) == base,
                "candidate must be one bounded commit on frozen base",
            )
            for name, change in manifest["changes"].items():
                try:
                    blob = subprocess.run(
                        ["git", "-C", str(path), "show", f"HEAD:{name}"],
                        check=True,
                        capture_output=True,
                        timeout=120,
                    ).stdout
                except (OSError, subprocess.SubprocessError) as exc:
                    raise PromotionError(
                        "committed candidate content unavailable"
                    ) from exc
                _require(
                    hashlib.sha256(blob).hexdigest() == change["after_sha256"],
                    "committed content differs from validated candidate",
                )
        return sorted(paths | untracked)

    def commit(self, path, manifest):
        self.git("add", "--", *manifest["allowed_paths"], cwd=path)
        self.git(
            "commit",
            "-m",
            f"Promote frozen candidate {manifest['manifest_fingerprint']}",
            cwd=path,
        )
        return self.git("rev-parse", "HEAD", cwd=path)


def _target(root, name):
    target = root / name
    _require(
        not any(p.is_symlink() for p in [target, *target.parents] if p != root.parent),
        "symlink path forbidden",
    )
    _require(target.resolve().is_relative_to(root.resolve()), "path escaped worktree")
    return target


def _checks(manifest, snapshot):
    observed = []
    for required in manifest["policy"]["required_checks"]:
        matches = [
            c
            for c in snapshot["checks"]
            if c.get("name") == required["name"]
            and c.get("app_id") == required["app_id"]
        ]
        state = (
            "MISSING"
            if not matches
            else matches[0].get("state")
            if len(matches) == 1
            else "UNKNOWN"
        )
        if state not in {
            "SUCCESS",
            "FAILED",
            "PENDING",
            "MISSING",
            "UNKNOWN",
            "CANCELLED",
        }:
            state = "UNKNOWN"
        observed.append({**required, "state": state})
    return observed


def _policy_matches(manifest, live):
    wanted = {(c["name"], c["app_id"]) for c in manifest["policy"]["required_checks"]}
    actual = {(c["name"], c["app_id"]) for c in live["required_checks"]}
    return (
        wanted == actual
        and len(actual) == len(live["required_checks"])
        and manifest["policy"]["merge_method"] in live["merge_methods"]
    )


def _identity(state, snapshot, manifest):
    return (
        snapshot["head_sha"] == state["head_sha"]
        and snapshot["branch"] == state["branch"]
        and snapshot["repository_id"] == manifest["repository_id"]
        and snapshot["base"] == "main"
        and snapshot["number"] == state["pr_number"]
    )


def _eligible(state, manifest, snapshot, policy, review_evidence):
    observed = _checks(manifest, snapshot)
    feedback = snapshot["feedback"]
    reviewed = not feedback
    if feedback and isinstance(review_evidence, dict):
        dispositions = review_evidence.get("dispositions", {})
        reviewed = (
            review_evidence.get("head_sha") == state["head_sha"]
            and review_evidence.get("feedback_fingerprint") == fingerprint(feedback)
            and set(dispositions) == {f["id"] for f in feedback}
            and all(
                v in {"FIXED", "ANSWERED", "EXPLAINED", "NOT_APPLICABLE", "DUPLICATE"}
                for v in dispositions.values()
            )
        )
    eligible = (
        _identity(state, snapshot, manifest)
        and snapshot["open"] is True
        and snapshot["draft"] is False
        and snapshot["mergeable"] is True
        and snapshot["unresolved_threads"] == 0
        and snapshot["blocking_review"] is False
        and snapshot["approvals"] >= policy["required_approvals"]
        and reviewed
        and all(c["state"] == "SUCCESS" for c in observed)
    )
    return eligible, observed


def _new_state(manifest):
    identity = manifest["manifest_fingerprint"]
    return {
        "document_type": ATTEMPT_TYPE,
        "artifact_version": VERSION,
        "attempt_id": identity,
        "manifest_fingerprint": identity,
        "locked_result_fingerprint": manifest["locked_result_fingerprint"],
        "base_sha": manifest["expected_base_sha"],
        "branch": f"promotion/{identity[:24]}",
        "changed_paths": [],
        "change_fingerprint": manifest["change_fingerprint"],
        "validation_refs": [],
        "head_sha": None,
        "pushed_head_sha": None,
        "pr_number": None,
        "pr_head_sha": None,
        "required_checks": manifest["policy"]["required_checks"],
        "observed_checks": [],
        "repository_merge_eligible": False,
        "merge_sha": None,
        "phase": "prepared",
        "status": "running",
        "reason": None,
        "production_authorized": False,
    }


def _save(path, state):
    state.pop("state_fingerprint", None)
    _safe(state)
    state["state_fingerprint"] = fingerprint(state)
    _write_atomic(path, state)
    return state


def _load(path, manifest):
    state = _read(path)
    payload = {k: v for k, v in state.items() if k != "state_fingerprint"}
    _safe(state)
    _require(
        set(payload) == set(_new_state(manifest))
        and fingerprint(payload) == state.get("state_fingerprint"),
        "corrupt attempt fingerprint/schema",
    )
    expected = _new_state(manifest)
    for key in (
        "document_type",
        "artifact_version",
        "attempt_id",
        "manifest_fingerprint",
        "locked_result_fingerprint",
        "base_sha",
        "branch",
        "change_fingerprint",
        "required_checks",
        "production_authorized",
    ):
        _require(state[key] == expected[key], "attempt identity mismatch")
    _require(
        state["production_authorized"] is False,
        "production authorization must remain false",
    )
    _require(
        type(state["repository_merge_eligible"]) is bool, "invalid merge eligibility"
    )
    for key in ("head_sha", "pushed_head_sha", "pr_head_sha", "merge_sha"):
        if state[key] is not None:
            _hex(state[key], _HEX40)
    _require(
        state["changed_paths"] in ([], sorted(manifest["allowed_paths"])),
        "attempt changed paths mismatch",
    )
    _require(
        state["validation_refs"]
        == manifest["validation"][: len(state["validation_refs"])],
        "invalid validation evidence",
    )
    return state


def run_promotion(
    *,
    source_state_path,
    manifest,
    provider: PromotionProvider,
    repository: GitRepository,
    host: PromotionHost,
    worktree_root,
    attempt_root,
    review_evidence=None,
):
    """Advance/reconcile one durable attempt. No polling daemon or hidden retries."""
    result = load_promotion_source(source_state_path)
    manifest = validate_manifest(manifest, result, provider)
    _require(
        getattr(host, "repository_id", manifest["repository_id"])
        == manifest["repository_id"],
        "host repository identity mismatch",
    )
    if hasattr(host, "repository"):
        _require(
            Path(host.repository).resolve() == repository.path,
            "host checkout differs from promotion repository",
        )
    attempt_dir = Path(attempt_root).resolve() / manifest["manifest_fingerprint"]
    worktree = Path(worktree_root).resolve() / manifest["manifest_fingerprint"][:24]
    _require(
        not attempt_dir.is_relative_to(repository.path)
        and not worktree.is_relative_to(repository.path)
        and not attempt_dir.is_relative_to(worktree)
        and not worktree.is_relative_to(attempt_dir),
        "host storage must be isolated",
    )
    state_path = attempt_dir / "attempt.json"
    if state_path.exists():
        state = _load(state_path, manifest)
    else:
        repository.preflight(manifest)
        _require(not worktree.exists(), "foreign worktree already exists")
        refs = repository.git(
            "for-each-ref",
            "--format=%(refname)",
            f"refs/heads/promotion/{manifest['manifest_fingerprint'][:24]}",
        )
        _require(not refs, "foreign promotion branch already exists")
        state = _new_state(manifest)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    lock = attempt_dir / "execution.lock"
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise PromotionError(
            "attempt already executing or orphan lock requires reconciliation"
        ) from exc
    try:
        with handle:
            handle.write(manifest["manifest_fingerprint"])
            handle.flush()
            os.fsync(handle.fileno())
        _sync_entry(lock)
        # Re-read under the exclusive lease; never act on pre-lock state.
        if state_path.exists():
            state = _load(state_path, manifest)
        else:
            _save(state_path, state)
        return _advance(
            state_path,
            state,
            manifest,
            provider,
            repository,
            host,
            worktree,
            review_evidence,
            source_state_path,
        )
    finally:
        lock.unlink()


def _advance(
    path,
    state,
    manifest,
    provider,
    repository,
    host,
    worktree,
    review_evidence,
    source_state_path,
):
    def check_source():
        current = load_promotion_source(source_state_path)
        _require(
            current["result_fingerprint"] == manifest["locked_result_fingerprint"],
            "source evidence changed during promotion",
        )

    def save(phase=None, status="running", reason=None):
        if phase:
            state["phase"] = phase
        state.update(status=status, reason=reason)
        return _save(path, state)

    def hold(reason, status="hold"):
        state["repository_merge_eligible"] = False
        return save(status=status, reason=reason)

    try:
        if state["status"] == "controlled_failure":
            return state
        if state["phase"] == "merged":
            if (
                host.verify_merge(
                    state["pr_number"], state["head_sha"], state["merge_sha"]
                )
                is True
            ):
                if state["status"] == "merged":
                    return state
                state["repository_merge_eligible"] = True
                return save("merged", "merged")
            return hold("merge_verification_required")
        if state["phase"] == "merging":
            snapshot = host.snapshot(state["pr_number"])
            if snapshot["merged"] and _identity(state, snapshot, manifest):
                if not isinstance(snapshot["merge_sha"], str) or not _HEX40.fullmatch(
                    snapshot["merge_sha"]
                ):
                    return hold("merge_verification_required")
                state["merge_sha"] = snapshot["merge_sha"]
                if (
                    host.verify_merge(
                        state["pr_number"], state["head_sha"], state["merge_sha"]
                    )
                    is True
                ):
                    state["repository_merge_eligible"] = True
                    return save("merged", "merged")
            return hold("uncertain_merge_requires_reconciliation")
        if host.main_sha() != manifest["expected_base_sha"] or not _policy_matches(
            manifest, host.policy()
        ):
            return hold("base_or_policy_changed")
        repository.preflight(manifest)
        if state["phase"] in {"materializing", "validating", "preparing"}:
            return hold("uncertain_local_execution_requires_reconciliation")
        if state["phase"] == "prepared":
            save("preparing")
            repository.create_worktree(worktree, state["branch"], state["base_sha"])
            repository.validate_worktree(worktree, state["branch"])
            repository.baseline(worktree, manifest)
            save("materializing")
            payload = provider.materialize(
                json.loads(json.dumps(manifest["materializer"]["inputs"]))
            )
            _require(
                isinstance(payload, Mapping)
                and set(payload) == set(manifest["allowed_paths"]),
                "materializer payload differs from allowlist",
            )
            # Validate all payloads before the first write.
            encoded = {name: _content(text) for name, text in payload.items()}
            for name, raw in encoded.items():
                _require(
                    hashlib.sha256(raw).hexdigest()
                    == manifest["changes"][name]["after_sha256"],
                    "materializer candidate differs from frozen change",
                )
            check_source()
            for name, raw in encoded.items():
                target = _target(worktree, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)
            state["changed_paths"] = repository.diff_guard(worktree, manifest)
            save("materialized")
        repository.validate_worktree(worktree, state["branch"])
        if state["phase"] == "materialized":
            repository.diff_guard(worktree, manifest)
            save("validating")
            for contract_id in manifest["validation"]:
                _require(
                    provider.validate_candidate(worktree, contract_id) is True,
                    "focused validation failed",
                )
                state["validation_refs"].append(contract_id)
            repository.diff_guard(worktree, manifest)
            check_source()
            save("validated")
        if state["phase"] == "validated":
            repository.diff_guard(worktree, manifest)
            save("committing")
            state["head_sha"] = repository.commit(worktree, manifest)
            repository.diff_guard(worktree, manifest, committed=True)
            save("committed")
        elif state["phase"] == "committing":
            # Adopt only a fully committed exact change, never rerun an uncertain commit.
            repository.diff_guard(worktree, manifest, committed=True)
            state["head_sha"] = repository.head(state["branch"])
            save("committed")
        if state["phase"] in {"committed", "pushing"}:
            check_source()
            repository.diff_guard(worktree, manifest, committed=True)
            _require(
                repository.head(state["branch"]) == state["head_sha"],
                "committed branch head changed",
            )
            remote = host.pushed_head(state["branch"])
            _require(remote in {None, state["head_sha"]}, "remote branch head differs")
            if remote is None:
                save("pushing")
                host.push(repository, state["branch"], state["head_sha"])
            state["pushed_head_sha"] = state["head_sha"]
            save("pushed")
        if state["phase"] in {"pushed", "creating_pr"}:
            previous_phase = state["phase"]
            pr = host.find_pr(state["branch"])
            if pr is None:
                if previous_phase == "creating_pr":
                    return hold("uncertain_pr_creation_requires_reconciliation")
                save("creating_pr")
                pr = host.create_pr(
                    state["branch"], state["head_sha"], state["base_sha"]
                )
            state["pr_number"] = pr["number"]
            _require(_identity(state, pr, manifest), "PR identity differs from attempt")
            state["pr_head_sha"] = pr["head_sha"]
            save("pr_open")
        _require(state["phase"] == "pr_open", "unknown attempt phase")
        repository.diff_guard(worktree, manifest, committed=True)
        _require(
            repository.head(state["branch"]) == state["head_sha"],
            "local candidate head changed",
        )
        _require(
            state["validation_refs"] == manifest["validation"],
            "focused validation evidence missing",
        )
        policy = host.policy()
        if not _policy_matches(manifest, policy):
            return hold("policy_changed")
        snapshot = host.snapshot(state["pr_number"])
        eligible, observed = _eligible(
            state, manifest, snapshot, policy, review_evidence
        )
        state["observed_checks"] = observed
        state["pr_head_sha"] = snapshot["head_sha"]
        if not eligible:
            return hold("final_head_gates_not_satisfied")
        # A second observation catches moved heads and review/check/policy drift.
        if host.main_sha() != state["base_sha"] or host.policy() != policy:
            return hold("base_or_policy_changed_before_merge")
        final = host.snapshot(state["pr_number"])
        eligible, observed = _eligible(state, manifest, final, policy, review_evidence)
        state["observed_checks"] = observed
        if not eligible:
            return hold("final_head_changed_before_merge")
        check_source()
        state["repository_merge_eligible"] = True
        save("merging")
        host.merge(
            state["pr_number"], state["head_sha"], manifest["policy"]["merge_method"]
        )
        merged = host.snapshot(state["pr_number"])
        _require(_identity(state, merged, manifest), "merged PR head mismatch")
        if (
            merged["merged"] is not True
            or not isinstance(merged["merge_sha"], str)
            or not _HEX40.fullmatch(merged["merge_sha"])
        ):
            return hold("merge_verification_required")
        state["merge_sha"] = merged["merge_sha"]
        if (
            host.verify_merge(state["pr_number"], state["head_sha"], state["merge_sha"])
            is not True
        ):
            return hold("merge_verification_required")
        return save("merged", "merged")
    except InfrastructureError:
        return hold("host_infrastructure_unavailable", "infrastructure_hold")
    except (ValueError, OSError, KeyError, TypeError):
        return hold("candidate_or_repository_validation_failed", "controlled_failure")
