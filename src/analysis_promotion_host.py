"""Optional git/gh host for S7; no dependency on cloud SDKs or core runtime."""

from __future__ import annotations

import json
import re
import subprocess
from functools import wraps
from pathlib import Path


class InfrastructureError(RuntimeError):
    """Unavailable or unknown host evidence; raw host output is never persisted."""


def _host_evidence(method):
    @wraps(method)
    def guarded(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except (KeyError, TypeError, IndexError, AttributeError) as exc:
            raise InfrastructureError("incomplete or malformed host evidence") from exc

    return guarded


def check_state(status, conclusion):
    if status in {"queued", "in_progress", "waiting", "pending", "requested"}:
        return "PENDING"
    if status != "completed":
        return "UNKNOWN"
    return {
        "success": "SUCCESS",
        "failure": "FAILED",
        "timed_out": "FAILED",
        "action_required": "FAILED",
        "cancelled": "CANCELLED",
    }.get(conclusion, "UNKNOWN")


class GhHost:
    """Authenticated gh CLI boundary. Inject a runner for deterministic tests.

    A runner accepts argv and returns stdout text. It must raise on failure.
    All subprocess calls have a timeout and never use a shell.
    """

    def __init__(self, repository_id, repository, *, runner=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository_id):
            raise ValueError("invalid repository identity")
        self.repository_id = repository_id
        self.repository = Path(repository)
        self.runner = runner or self._execute

    def _execute(self, args):
        return subprocess.run(
            args,
            cwd=self.repository,
            check=True,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=120,
        ).stdout

    def _call(self, args):
        try:
            return self.runner(args)
        except (OSError, subprocess.SubprocessError) as exc:
            raise InfrastructureError("host command unavailable or rejected") from exc

    def _json(self, endpoint, *, pages=False, extra=()):
        args = ["gh", "api", endpoint, *extra]
        if pages:
            args += ["--paginate", "--slurp"]
        try:
            return json.loads(self._call(args))
        except (ValueError, TypeError) as exc:
            raise InfrastructureError("invalid host JSON") from exc

    def _list(self, endpoint):
        pages = self._json(endpoint, pages=True)
        if not isinstance(pages, list) or not all(isinstance(p, list) for p in pages):
            raise InfrastructureError("incomplete paginated host evidence")
        return [item for page in pages for item in page]

    def _stream_list(self, endpoint):
        """Consume every array emitted by gh pagination, including one-page replies."""
        remaining = self._call(["gh", "api", endpoint, "--paginate"]).strip()
        if not remaining:
            raise InfrastructureError("missing paginated host evidence")
        values = []
        decoder = json.JSONDecoder()
        while remaining:
            try:
                page, end = decoder.raw_decode(remaining)
            except ValueError as exc:
                raise InfrastructureError("invalid paginated host JSON") from exc
            if not isinstance(page, list):
                raise InfrastructureError("paginated host evidence must contain arrays")
            values.extend(page)
            remaining = remaining[end:].lstrip()
        return values

    @_host_evidence
    def main_sha(self):
        return self._json(f"repos/{self.repository_id}/git/ref/heads/main")["object"][
            "sha"
        ]

    @_host_evidence
    def policy(self):
        rules = self._stream_list(f"repos/{self.repository_id}/rules/branches/main")
        checks, methods, approvals = [], None, 0
        for rule in rules:
            kind, params = rule["type"], rule.get("parameters", {})
            if kind == "required_status_checks":
                for check in params["required_status_checks"]:
                    app = check.get("integration_id")
                    if not isinstance(app, int) or app <= 0:
                        raise InfrastructureError(
                            "required integration identity unknown"
                        )
                    checks.append({"name": check["context"], "app_id": app})
            elif kind == "pull_request":
                if (
                    params.get("required_reviewers")
                    or params.get("require_code_owner_review")
                    or params.get("require_last_push_approval")
                ):
                    raise InfrastructureError(
                        "unsupported review rule requires host evidence"
                    )
                approvals = max(
                    approvals, params.get("required_approving_review_count", 0)
                )
                allowed = set(params.get("allowed_merge_methods", ["squash", "rebase"]))
                methods = allowed if methods is None else methods & allowed
            elif kind not in {
                "deletion",
                "non_fast_forward",
                "required_linear_history",
            }:
                raise InfrastructureError("unsupported repository rule")
        if methods is None:
            raise InfrastructureError("PR governance rule missing")
        return {
            "required_checks": sorted(checks, key=lambda x: (x["name"], x["app_id"])),
            "merge_methods": sorted(methods),
            "required_approvals": approvals,
        }

    def pushed_head(self, branch):
        output = self._call(["git", "ls-remote", "origin", f"refs/heads/{branch}"])
        rows = output.strip().splitlines()
        if not rows:
            return None
        if len(rows) != 1:
            raise InfrastructureError("ambiguous remote branch")
        return rows[0].split()[0]

    def push(self, repository, branch, head_sha):
        if repository.head(branch) != head_sha:
            raise InfrastructureError("local head moved before push")
        self._call(["git", "push", "origin", f"{head_sha}:refs/heads/{branch}"])

    def _pr_identity(self, value):
        if value["base"]["repo"]["full_name"] != self.repository_id:
            raise InfrastructureError("PR base repository mismatch")
        return {
            "number": value["number"],
            "head_sha": value["head"]["sha"],
            "branch": value["head"]["ref"],
            "base": value["base"]["ref"],
            "repository_id": value["head"]["repo"]["full_name"],
        }

    @_host_evidence
    def find_pr(self, branch):
        owner = self.repository_id.split("/")[0]
        values = self._list(
            f"repos/{self.repository_id}/pulls?state=all&head={owner}:{branch}&base=main&per_page=100"
        )
        if len(values) > 1:
            raise InfrastructureError("duplicate promotion PRs")
        return self._pr_identity(values[0]) if values else None

    def create_bounded_pr(self, branch, head_sha, base_sha, *, title, body):
        # Caller supplies bounded portable prose; never include host output or paths.
        if not all(isinstance(value, str) and value.strip() for value in (title, body)):
            raise ValueError("PR title/body must be non-empty text")
        self._call(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                self.repository_id,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                title,
                "--body",
                body,
            ]
        )
        result = self.find_pr(branch)
        if result is None:
            raise InfrastructureError("created PR not yet visible")
        return result

    def create_pr(self, branch, head_sha, base_sha):
        return self.create_bounded_pr(
            branch,
            head_sha,
            base_sha,
            title=f"Promote frozen candidate ({branch.rsplit('/', 1)[-1]})",
            body=(
                "Bounded policy-controlled repository promotion.\n\n"
                f"Base: {base_sha}\nHead: {head_sha}\n\n"
                "S8 baseline acceptance remains separate."
            ),
        )

    def _threads(self, number):
        owner, name = self.repository_id.split("/")
        query = """query($owner:String!,$name:String!,$number:Int!,$cursor:String){
          repository(owner:$owner,name:$name){pullRequest(number:$number){
            reviewThreads(first:100,after:$cursor){nodes{id isResolved isOutdated}
              pageInfo{hasNextPage endCursor}}}}}"""
        nodes, cursor = [], None
        while True:
            args = [
                "-f",
                f"query={query}",
                "-f",
                f"owner={owner}",
                "-f",
                f"name={name}",
                "-F",
                f"number={number}",
            ]
            if cursor:
                args += ["-f", f"cursor={cursor}"]
            response = self._json("graphql", extra=args)
            if response.get("errors"):
                raise InfrastructureError("review thread evidence unavailable")
            connection = response["data"]["repository"]["pullRequest"]["reviewThreads"]
            nodes += connection["nodes"]
            info = connection["pageInfo"]
            if not info["hasNextPage"]:
                return nodes
            following = info["endCursor"]
            if not following or following == cursor:
                raise InfrastructureError("incomplete review thread pagination")
            cursor = following

    @_host_evidence
    def snapshot(self, number):
        prefix = f"repos/{self.repository_id}"
        pr = self._json(f"{prefix}/pulls/{number}")
        identity = self._pr_identity(pr)
        head = identity["head_sha"]
        pages = self._json(
            f"{prefix}/commits/{head}/check-runs?filter=latest&per_page=100", pages=True
        )
        checks = []
        for page in pages:
            for check in page["check_runs"]:
                if check.get("head_sha") != head:
                    raise InfrastructureError("check belongs to another head")
                checks.append(
                    {
                        "name": check["name"],
                        "app_id": check.get("app", {}).get("id"),
                        "state": check_state(
                            check.get("status"), check.get("conclusion")
                        ),
                    }
                )
        # Commit statuses cannot prove integration ID; retain UNKNOWN identity.
        for status in self._list(f"{prefix}/commits/{head}/statuses?per_page=100"):
            checks.append(
                {"name": status["context"], "app_id": None, "state": "UNKNOWN"}
            )
        feedback = []
        for kind, endpoint in (
            ("issue", f"issues/{number}/comments"),
            ("inline", f"pulls/{number}/comments"),
            ("review", f"pulls/{number}/reviews"),
        ):
            values = self._list(f"{prefix}/{endpoint}?per_page=100")
            for value in values:
                feedback.append(
                    {
                        "id": f"{kind}:{value['id']}",
                        "body": value.get("body") or "",
                        "updated_at": value.get(
                            "updated_at", value.get("submitted_at")
                        ),
                        "state": value.get("state"),
                        "commit_id": value.get("commit_id"),
                    }
                )
            if kind == "review":
                reviews = values
        threads = self._threads(number)
        for thread in threads:
            feedback.append(
                {
                    "id": f"thread:{thread['id']}",
                    "resolved": thread["isResolved"],
                    "outdated": thread["isOutdated"],
                }
            )
        latest = {}
        for review in reviews:
            if review.get("state") in {"APPROVED", "CHANGES_REQUESTED", "DISMISSED"}:
                latest[review["user"]["login"]] = review
        return {
            **identity,
            "open": pr["state"] == "open",
            "draft": pr["draft"],
            "mergeable": pr.get("mergeable") is True
            and pr.get("mergeable_state") == "clean",
            "checks": checks,
            "feedback": feedback,
            "unresolved_threads": sum(not t["isResolved"] for t in threads),
            "blocking_review": any(
                r["state"] == "CHANGES_REQUESTED" for r in latest.values()
            ),
            "approvals": sum(
                r["state"] == "APPROVED" and r["commit_id"] == head
                for r in latest.values()
            ),
            "merged": pr.get("merged") is True,
            "merge_sha": pr.get("merge_commit_sha"),
        }

    def merge(self, number, expected_head_sha, method):
        if method not in {"squash", "rebase"}:
            raise ValueError("unsupported merge method")
        self._call(
            [
                "gh",
                "pr",
                "merge",
                str(number),
                "--repo",
                self.repository_id,
                f"--{method}",
                "--match-head-commit",
                expected_head_sha,
            ]
        )

    @_host_evidence
    def verify_merge(self, number, head_sha, merge_sha):
        value = self._json(f"repos/{self.repository_id}/pulls/{number}")
        if not (
            value["merged"] is True
            and value["head"]["sha"] == head_sha
            and value.get("merge_commit_sha") == merge_sha
        ):
            return False
        self._call(["git", "fetch", "origin", "main"])
        self._call(["git", "cat-file", "-e", f"{merge_sha}^{{commit}}"])
        self._call(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                merge_sha,
                "refs/remotes/origin/main",
            ]
        )
        return True
