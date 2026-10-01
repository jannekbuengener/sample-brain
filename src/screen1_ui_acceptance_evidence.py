"""Evidence storage for Screen-1 UI acceptance — always outside the repo."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]{1,80}$")


def default_evidence_root() -> Path:
    override = os.environ.get("SAMPLE_BRAIN_UI_ACCEPTANCE_EVIDENCE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".sample-brain" / "ui-acceptance").resolve()


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    return f"screen1-{stamp}"


def create_run_dir(run_id: str | None = None, *, root: Path | None = None) -> Path:
    rid = run_id or new_run_id()
    if not _SAFE_RUN_ID.match(rid):
        raise ValueError(f"unsafe run_id: {rid!r}")
    base = root or default_evidence_root()
    path = (base / rid).resolve()
    if root is None and not str(path).startswith(str(base)):
        raise ValueError("evidence path escaped evidence root")
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def assert_outside_repo(evidence_dir: Path, repo_root: Path) -> None:
    evidence = evidence_dir.resolve()
    repo = repo_root.resolve()
    try:
        evidence.relative_to(repo)
    except ValueError:
        return
    raise ValueError(f"evidence_dir must be outside repo: {evidence}")
