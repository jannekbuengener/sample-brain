"""Local workflow-observer paths (outside repo)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_ENV = "SAMPLE_BRAIN_WORKFLOW_OBSERVER_DIR"
DEFAULT_REL = ("sample-brain", "workflow-observer")


def default_root() -> Path:
    override = os.environ.get(ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local).joinpath(*DEFAULT_REL)
    return Path.home().joinpath("AppData", "Local", *DEFAULT_REL)


class ObserverPaths:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_root()

    @property
    def db(self) -> Path:
        return self.root / "workflow.sqlite3"

    @property
    def spool_dir(self) -> Path:
        return self.root / "spool"

    @property
    def fl_spool(self) -> Path:
        return self.spool_dir / "fl-events.jsonl"

    @property
    def win_spool(self) -> Path:
        return self.spool_dir / "windows-events.jsonl"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def health(self) -> Path:
        return self.state_dir / "health.json"

    @property
    def pid_file(self) -> Path:
        return self.state_dir / "recorder.pid"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def log_file(self) -> Path:
        return self.logs_dir / "recorder.log"

    def ensure(self) -> None:
        for d in (self.root, self.spool_dir, self.state_dir, self.logs_dir):
            d.mkdir(parents=True, exist_ok=True)
