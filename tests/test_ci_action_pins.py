from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parents[1] / ".github" / "workflows"
USES_RE = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)", re.MULTILINE)
IMMUTABLE_ACTION_RE = re.compile(r"^[^@]+@[0-9a-f]{40}$")


def test_third_party_workflow_actions_are_pinned_to_commit_shas() -> None:
    workflow_files = sorted(
        [*WORKFLOWS_DIR.glob("*.yml"), *WORKFLOWS_DIR.glob("*.yaml")]
    )
    assert workflow_files, "expected GitHub Actions workflow files"

    unpinned: list[str] = []
    for workflow in workflow_files:
        text = workflow.read_text(encoding="utf-8")
        for action_ref in USES_RE.findall(text):
            if action_ref.startswith("./"):
                continue
            if not IMMUTABLE_ACTION_RE.fullmatch(action_ref):
                unpinned.append(f"{workflow.name}: {action_ref}")

    assert not unpinned, "third-party Actions must use immutable 40-char SHAs:\n" + "\n".join(unpinned)
