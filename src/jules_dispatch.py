from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

API_BASE = "https://jules.googleapis.com/v1alpha"
REPO_OWNER = "jannekbuengener"
REPO_NAME = "sample-brain"
ENV_KEY = "JULES_API_KEY"
READ_ONLY_CHANGE_CLASS = "read_only"

AUTOMATION_AUTO_CREATE_PR = "AUTO_CREATE_PR"

# Private / non-transferable artifact markers (repo-external or untracked).
_FORBIDDEN_FILE_MARKERS = (
    ".wav",
    ".aiff",
    ".aif",
    ".flac",
    ".mp3",
    ".ogg",
    ".db",
    ".sqlite",
    ".sqlite3",
    "catalog.db",
    "data/catalog",
    "data/indexes",
    "data/embeddings",
    "data/models",
    ".pt",
    ".pth",
    ".safetensors",
    ".npy",
    ".npz",
    ".pkl",
    "model cache",
    "huggingface",
    ".venv",
    "reports/",
)

# Allowed Sample Brain dispatch statuses (subset of the contract surface).
DISPATCH_STATUSES = (
    "CREATED",
    "AWAITING_PLAN_APPROVAL",
    "IN_PROGRESS",
    "RESULT_READY",
    "PARTIAL",
    "BLOCKED",
    "FAILED",
)

# Jules states we understand. Anything else -> PARTIAL_PROTOCOL_DRIFT.
_KNOWN_JULES_STATES = {
    "PENDING",
    "AWAITING_PLAN_APPROVAL",
    "PLAN_APPROVED",
    "IN_PROGRESS",
    "RUNNING",
    "COMPLETED",
    "FAILED",
}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class JulesError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ContextRejected(JulesError):
    def __init__(self, message: str) -> None:
        super().__init__("BLOCKED", message)


class JulesHttpError(JulesError):
    def __init__(self, status: int, body: str, path: str) -> None:
        super().__init__(_http_status_to_code(status), f"HTTP {status} on {path}")
        self.status = status
        self.body = body
        self.path = path


class JulesTransportError(JulesError):
    def __init__(self, message: str, kind: str = "remote") -> None:
        super().__init__("BLOCKED_REMOTE", message)
        self.kind = kind


def _http_status_to_code(status: int) -> str:
    if status in (401, 403):
        return "BLOCKED_AUTH"
    if status == 429:
        return "BLOCKED_RATE_LIMIT"
    if 500 <= status < 600:
        return "BLOCKED_REMOTE"
    return "PARTIAL_PROTOCOL_DRIFT"


# ---------------------------------------------------------------------------
# Dispatch context
# ---------------------------------------------------------------------------


@dataclass
class DispatchContext:
    repo: str
    issue_number: int
    issue_url: str
    base_branch: str
    base_sha: str
    change_class: str
    goal: str
    acceptance_criteria: List[str] = field(default_factory=list)
    relevant_files: List[str] = field(default_factory=list)
    known_facts: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    minimum_validation: List[str] = field(default_factory=list)
    allow_pr: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo": self.repo,
            "issue_number": self.issue_number,
            "issue_url": self.issue_url,
            "base_branch": self.base_branch,
            "base_sha": self.base_sha,
            "change_class": self.change_class,
            "goal": self.goal,
            "acceptance_criteria": list(self.acceptance_criteria),
            "relevant_files": list(self.relevant_files),
            "known_facts": list(self.known_facts),
            "constraints": list(self.constraints),
            "minimum_validation": list(self.minimum_validation),
            "allow_pr": self.allow_pr,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DispatchContext":
        return cls(
            repo=str(data.get("repo", "")),
            issue_number=int(data.get("issue_number", 0)),
            issue_url=str(data.get("issue_url", "")),
            base_branch=str(data.get("base_branch", "")),
            base_sha=str(data.get("base_sha", "")),
            change_class=str(data.get("change_class", "")),
            goal=str(data.get("goal", "")),
            acceptance_criteria=list(data.get("acceptance_criteria", []) or []),
            relevant_files=list(data.get("relevant_files", []) or []),
            known_facts=list(data.get("known_facts", []) or []),
            constraints=list(data.get("constraints", []) or []),
            minimum_validation=list(data.get("minimum_validation", []) or []),
            allow_pr=bool(data.get("allow_pr", False)),
        )


# ---------------------------------------------------------------------------
# Redaction / validation
# ---------------------------------------------------------------------------

_ABS_WIN = re.compile(r"[A-Za-z]:\\[^\s\"'`]+")
_ABS_UNC = re.compile(r"\\\\[^\s\"'`]+")
_ABS_UNIX = re.compile(r"(?:/home/|/Users/|/root/|/etc/|/var/|/usr/|/opt/|/tmp/|/mnt/|/Volumes/)[^\s\"'`]*")
_ABS_GENERIC = re.compile(r"(?<=[\s\"'`])/[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)+")
_SECRET_ASSIGN = re.compile(
    r"(?i)\b([A-Za-z0-9_]*?(?:KEY|TOKEN|SECRET)[A-Za-z0-9_]*)\s*[=:]\s*\S+"
)


def redact(text: str, api_key: Optional[str] = None) -> str:
    """Remove secret values and private / absolute paths from arbitrary text."""
    if text is None:
        return ""
    out = text
    if api_key:
        out = out.replace(api_key, "<REDACTED_SECRET>")
    out = _SECRET_ASSIGN.sub(r"\1=<REDACTED_SECRET>", out)
    out = _ABS_WIN.sub("<REDACTED_PATH>", out)
    out = _ABS_UNC.sub("<REDACTED_PATH>", out)
    out = _ABS_UNIX.sub("<REDACTED_PATH>", out)
    out = _ABS_GENERIC.sub("<REDACTED_PATH>", out)
    return out


def _is_absolute_path(value: str) -> bool:
    if not value:
        return False
    if re.match(r"[A-Za-z]:[\\/]", value):
        return True
    if value.startswith("\\\\") or value.startswith("//"):
        return True
    if value.startswith("/"):
        return True
    return False


def _mentions_private_artifact(value: str) -> bool:
    low = value.lower().replace("\\", "/")
    return any(marker in low for marker in _FORBIDDEN_FILE_MARKERS)


def validate_context(ctx: DispatchContext, repo_root: Optional[str] = None) -> None:
    """Stop early if any required dispatch field or path is invalid."""
    required = {
        "repo": ctx.repo,
        "issue_number": ctx.issue_number,
        "issue_url": ctx.issue_url,
        "base_branch": ctx.base_branch,
        "base_sha": ctx.base_sha,
        "change_class": ctx.change_class,
        "goal": ctx.goal,
        "acceptance_criteria": ctx.acceptance_criteria,
        "relevant_files": ctx.relevant_files,
        "known_facts": ctx.known_facts,
        "minimum_validation": ctx.minimum_validation,
        "constraints": ctx.constraints,
    }
    for name, value in required.items():
        if value is None:
            raise ContextRejected(f"required field missing: {name}")
        if isinstance(value, str) and not value.strip():
            raise ContextRejected(f"required field empty: {name}")
        if isinstance(value, (list, tuple)) and len(value) == 0:
            raise ContextRejected(f"required field empty: {name}")

    if ctx.change_class != READ_ONLY_CHANGE_CLASS and ".." in ctx.base_branch:
        raise ContextRejected("base_branch must not escape repo")

    for path in ctx.relevant_files:
        if not isinstance(path, str) or not path.strip():
            raise ContextRejected("relevant_files must be non-empty strings")
        if _is_absolute_path(path):
            raise ContextRejected(f"absolute path not allowed: {path}")
        if path.startswith("/") or re.match(r"[A-Za-z]:", path):
            raise ContextRejected(f"absolute path not allowed: {path}")
        if ".." in path.split("/"):
            raise ContextRejected(f"path must stay inside repo: {path}")
        if _mentions_private_artifact(path):
            raise ContextRejected(f"private artifact path not allowed: {path}")


def requires_plan_approval(ctx: DispatchContext) -> bool:
    """Plan approval is driven by the change class, not by allow_pr."""
    return ctx.change_class != READ_ONLY_CHANGE_CLASS


# ---------------------------------------------------------------------------
# Prompt envelope
# ---------------------------------------------------------------------------


def build_prompt(ctx: DispatchContext) -> str:
    lines: List[str] = []
    lines.append("REPOSITORY")
    lines.append(ctx.repo)
    lines.append("")
    lines.append("ISSUE")
    lines.append(f"#{ctx.issue_number} ({ctx.issue_url})")
    lines.append("")
    lines.append("BASE")
    lines.append(f"branch: {ctx.base_branch}")
    lines.append(f"sha: {ctx.base_sha}")
    lines.append("")
    lines.append("GOAL")
    lines.append(ctx.goal)
    lines.append("")
    lines.append("ACCEPTANCE")
    for crit in ctx.acceptance_criteria:
        lines.append(f"- {crit}")
    lines.append("")
    lines.append("RELEVANT REPO FACTS")
    for fact in ctx.known_facts:
        lines.append(f"- {fact}")
    if ctx.relevant_files:
        lines.append("Relevant repo-relative paths:")
        for path in ctx.relevant_files:
            lines.append(f"  {path}")
    lines.append("")
    lines.append("ALLOWED SCOPE")
    for constraint in ctx.constraints:
        lines.append(f"- {constraint}")
    lines.append("")
    lines.append("MUST NOT TOUCH")
    lines.append("- private samples, audio, databases, caches, model weights")
    lines.append("- any path outside the repository")
    lines.append("- governance, security, or CI configuration")
    lines.append("")
    lines.append("VALIDATION")
    for check in ctx.minimum_validation:
        lines.append(f"- {check}")
    lines.append("")
    lines.append("SAFETY")
    lines.append("- no secret values are present in this task")
    lines.append("- no private local paths are referenced")
    lines.append("")
    lines.append("DELIVERABLE")
    lines.append("- implement the requested slice")
    lines.append("- add or update the relevant tests")
    lines.append("- a branch and pull request are allowed")
    lines.append("- do not finalize the pull request")
    lines.append("- do not conclude the linked issue")
    lines.append("- report the pull request URL and a concise result")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------


class JulesTransport:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base: str = API_BASE,
        timeout: float = 30.0,
    ) -> None:
        self.api_key = api_key
        self.base = base.rstrip("/")
        self.timeout = timeout

    def request(
        self, method: str, path: str, body: Optional[dict] = None
    ) -> dict:
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-Goog-Api-Key"] = self.api_key
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:  # pragma: no cover - network
            raw = exc.read().decode("utf-8", errors="replace")
            raise JulesHttpError(exc.code, raw, path) from exc
        except urllib.error.URLError as exc:  # pragma: no cover - network
            raise JulesTransportError(f"transport error: {exc.reason}") from exc
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - network
            raise JulesTransportError(f"invalid json: {exc}") from exc


# ---------------------------------------------------------------------------
# Source resolution
# ---------------------------------------------------------------------------


def fetch_sources(transport: JulesTransport) -> List[dict]:
    resp = transport.request("GET", "/sources")
    return list(resp.get("sources", []) or [])


def match_source(sources: List[dict]) -> Optional[str]:
    for source in sources:
        repo = source.get("githubRepo") or {}
        owner = repo.get("owner")
        name = repo.get("repo")
        if owner == REPO_OWNER and name == REPO_NAME:
            return source.get("name") or source.get("id")
    return None


def resolve_source(transport: JulesTransport) -> str:
    sources = fetch_sources(transport)
    source_id = match_source(sources)
    if not source_id:
        raise JulesError(
            "BLOCKED_SOURCE_NOT_CONNECTED",
            "Sample Brain source not connected to Jules",
        )
    return source_id


# ---------------------------------------------------------------------------
# Session operations
# ---------------------------------------------------------------------------


def build_create_payload(ctx: DispatchContext, source_id: str) -> dict:
    payload: Dict[str, Any] = {
        "sourceContext": {
            "source": source_id,
            "githubRepoContext": {"startingBranch": ctx.base_branch},
        },
        "prompt": build_prompt(ctx),
        "requirePlanApproval": requires_plan_approval(ctx),
    }
    if ctx.allow_pr:
        payload["automationMode"] = AUTOMATION_AUTO_CREATE_PR
    return payload


def create_session(
    transport: JulesTransport, ctx: DispatchContext, source_id: str
) -> dict:
    return transport.request("POST", "/sessions", build_create_payload(ctx, source_id))


def _session_id(session_id: str) -> str:
    """Return the bare session id the API path expects.

    The create response uses the full resource name ``sessions/{id}``, but the
    read/approve/message endpoints expect the bare ``{id}`` segment.
    """
    return session_id.split("/", 1)[1] if session_id.startswith("sessions/") else session_id


def get_session(transport: JulesTransport, session_id: str) -> dict:
    return transport.request("GET", f"/sessions/{_session_id(session_id)}")


def get_activities(transport: JulesTransport, session_id: str) -> List[dict]:
    out: List[dict] = []
    page_token: Optional[str] = None
    while True:
        path = f"/sessions/{_session_id(session_id)}/activities"
        if page_token:
            path += f"?pageToken={urllib.parse.quote(page_token, safe='')}"
        try:
            resp = transport.request("GET", path)
        except JulesHttpError as exc:
            # A brand-new session with no activities yet returns 404 from the
            # real API (the collection is empty). Treat that as "no activities".
            if exc.status == 404:
                break
            raise
        out.extend(list(resp.get("activities", []) or []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def approve_plan(transport: JulesTransport, session_id: str) -> dict:
    return transport.request("POST", f"/sessions/{_session_id(session_id)}:approvePlan", {})


def send_message(transport: JulesTransport, session_id: str, text: str) -> dict:
    clean = redact(text)
    return transport.request(
        "POST", f"/sessions/{_session_id(session_id)}:sendMessage", {"message": clean}
    )


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------


def _extract_pr_url(resp: dict) -> Optional[str]:
    pr = resp.get("pullRequest")
    if isinstance(pr, dict):
        return pr.get("url") or pr.get("htmlUrl")
    if isinstance(resp.get("pullRequestUrl"), str):
        return resp["pullRequestUrl"]
    return None


def _extract_plan_id(resp: dict) -> Optional[str]:
    plan = resp.get("plan")
    if isinstance(plan, dict):
        return plan.get("id") or plan.get("name")
    if isinstance(resp.get("planId"), str):
        return resp["planId"]
    return None


def normalize_dispatch(
    jules_state: Optional[str],
    pr_url: Optional[str] = None,
    session_id: Optional[str] = None,
    plan_id: Optional[str] = None,
) -> dict:
    state = (jules_state or "").upper()
    if state in ("COMPLETED",):
        status = "RESULT_READY"
    elif state in ("PENDING", "QUEUED"):
        status = "CREATED"
    elif state == "AWAITING_PLAN_APPROVAL":
        status = "AWAITING_PLAN_APPROVAL"
    elif state in (
        "PLANNING",
        "PLAN_APPROVED",
        "IN_PROGRESS",
        "RUNNING",
        "AWAITING_USER_FEEDBACK",
        "PAUSED",
    ):
        status = "IN_PROGRESS"
    elif state == "FAILED":
        status = "FAILED"
    elif state == "":
        status = "CREATED"
    else:
        status = "PARTIAL_PROTOCOL_DRIFT"
    return {
        "dispatch_status": status,
        "jules_state": jules_state,
        "session": session_id,
        "plan_id": plan_id,
        "pull_request_url": pr_url,
        "error_code": None if status != "PARTIAL_PROTOCOL_DRIFT" else "PARTIAL_PROTOCOL_DRIFT",
    }


def _error_result(
    exc: JulesError, session_id: Optional[str] = None, partial_if_session: bool = False
) -> dict:
    status = exc.code
    if partial_if_session and session_id and exc.code == "BLOCKED_REMOTE":
        status = "PARTIAL"
    elif exc.code == "BLOCKED":
        status = "BLOCKED"
    return {
        "dispatch_status": status,
        "jules_state": None,
        "session": session_id,
        "plan_id": None,
        "pull_request_url": None,
        "error_code": exc.code,
    }


# ---------------------------------------------------------------------------
# High-level commands
# ---------------------------------------------------------------------------


def run_dispatch(
    transport: JulesTransport, ctx: DispatchContext, repo_root: Optional[str] = None
) -> dict:
    validate_context(ctx, repo_root)
    if not transport.api_key:
        return _error_result(JulesError("BLOCKED_AUTH", "API key not configured"))
    try:
        source_id = resolve_source(transport)
    except JulesError as exc:
        return _error_result(exc)
    try:
        resp = create_session(transport, ctx, source_id)
    except JulesError as exc:
        return _error_result(exc)
    session_id = resp.get("name") or resp.get("id")
    state = resp.get("state")
    pr_url = _extract_pr_url(resp)
    plan_id = _extract_plan_id(resp)
    # No automatic approval is performed here.
    return normalize_dispatch(state, pr_url, session_id, plan_id)


def run_status(transport: JulesTransport, session_id: str) -> dict:
    if not transport.api_key:
        return _error_result(JulesError("BLOCKED_AUTH", "API key not configured"), session_id)
    try:
        resp = get_session(transport, session_id)
    except JulesError as exc:
        return _error_result(exc, session_id, partial_if_session=True)
    state = resp.get("state")
    pr_url = _extract_pr_url(resp)
    plan_id = _extract_plan_id(resp)
    return normalize_dispatch(state, pr_url, session_id, plan_id)


def run_activities(transport: JulesTransport, session_id: str) -> dict:
    if not transport.api_key:
        return _error_result(JulesError("BLOCKED_AUTH", "API key not configured"), session_id)
    try:
        activities = get_activities(transport, session_id)
    except JulesError as exc:
        return _error_result(exc, session_id, partial_if_session=True)
    latest_state = None
    pr_url = None
    plan_id = None
    for activity in activities:
        atype = activity.get("type")
        if atype == "planGenerated":
            plan_id = activity.get("planId") or plan_id
        elif atype == "sessionCompleted":
            latest_state = "COMPLETED"
            pr = activity.get("pullRequest") or activity.get("output", {}).get("pullRequest")
            if isinstance(pr, dict):
                pr_url = pr.get("url") or pr_url
        elif atype == "sessionFailed":
            latest_state = "FAILED"
    if latest_state is None:
        latest_state = "IN_PROGRESS"
    result = normalize_dispatch(latest_state, pr_url, session_id, plan_id)
    result["activities"] = activities
    return result


def run_approve(transport: JulesTransport, session_id: str) -> dict:
    if not transport.api_key:
        return _error_result(JulesError("BLOCKED_AUTH", "API key not configured"), session_id)
    try:
        approve_plan(transport, session_id)
    except JulesError as exc:
        return _error_result(exc, session_id)
    return {
        "dispatch_status": "IN_PROGRESS",
        "jules_state": "PLAN_APPROVED",
        "session": session_id,
        "plan_id": None,
        "pull_request_url": None,
        "error_code": None,
    }


def run_message(transport: JulesTransport, session_id: str, text: str) -> dict:
    if not transport.api_key:
        return _error_result(JulesError("BLOCKED_AUTH", "API key not configured"), session_id)
    try:
        send_message(transport, session_id, text)
    except JulesError as exc:
        return _error_result(exc, session_id)
    return {
        "dispatch_status": "IN_PROGRESS",
        "jules_state": None,
        "session": session_id,
        "plan_id": None,
        "pull_request_url": None,
        "error_code": None,
    }


def run_doctor(transport: Optional[JulesTransport] = None) -> dict:
    key = os.environ.get(ENV_KEY)
    out: Dict[str, Any] = {
        "auth_configured": bool(key),
        "source_connected": False,
        "source": None,
    }
    if not key:
        return out
    if transport is None:
        transport = JulesTransport(api_key=key)
    try:
        sources = fetch_sources(transport)
        source_id = match_source(sources)
        if source_id:
            out["source_connected"] = True
            out["source"] = source_id
    except JulesError:
        # Only safe status is reported; no body, key, or path leakage.
        out["source_connected"] = False
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _read_stdin() -> str:
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jules_dispatch",
        description="Sample Brain Jules dispatch helper (stdlib only).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("doctor", help="Check auth and Sample Brain source.")

    p_dispatch = sub.add_parser("dispatch", help="Dispatch a context from stdin JSON.")
    p_dispatch.add_argument("--repo-root", default=None)

    p_status = sub.add_parser("status", help="Read a session.")
    p_status.add_argument("--session", required=True)

    p_activities = sub.add_parser("activities", help="Read session activities.")
    p_activities.add_argument("--session", required=True)

    p_approve = sub.add_parser("approve", help="Approve a pending plan.")
    p_approve.add_argument("--session", required=True)

    p_message = sub.add_parser("message", help="Send a follow-up message from stdin.")
    p_message.add_argument("--session", required=True)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    api_key = os.environ.get(ENV_KEY)
    transport = JulesTransport(api_key=api_key)

    if args.command == "doctor":
        result = run_doctor(transport)
    elif args.command == "dispatch":
        raw = _read_stdin()
        if not raw.strip():
            result = _error_result(JulesError("BLOCKED", "no DispatchContext on stdin"))
        else:
            ctx = DispatchContext.from_dict(json.loads(raw))
            result = run_dispatch(transport, ctx, repo_root=args.repo_root)
    elif args.command == "status":
        result = run_status(transport, args.session)
    elif args.command == "activities":
        result = run_activities(transport, args.session)
    elif args.command == "approve":
        result = run_approve(transport, args.session)
    elif args.command == "message":
        text = _read_stdin()
        result = run_message(transport, args.session, text)
    else:  # pragma: no cover - argparse enforces choices
        parser.error("unknown command")
        return 2

    sys.stdout.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
