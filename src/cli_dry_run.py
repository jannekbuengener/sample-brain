"""Shared structured preview contract for headless CLI ``--dry-run`` (#487).

Contract: validate → inspect/discover/plan → emit preview → stop before the
first persistent write. Never write-then-rollback.
"""

from __future__ import annotations

import json
from typing import Any, Mapping

DRY_RUN_CONTRACT_VERSION = "sample-brain-cli-dry-run/v1"


def build_dry_run_preview(
    *,
    command: str,
    action: str,
    target_kind: str,
    planned_mutations: Mapping[str, Any] | list[Any],
    skipped_or_prevented_writes: list[str],
    validation: Mapping[str, Any] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build a machine-readable dry-run preview payload."""
    preview: dict[str, Any] = {
        "action": action,
        "command": command,
        "contract_version": DRY_RUN_CONTRACT_VERSION,
        "dry_run": True,
        "planned_mutations": planned_mutations,
        "skipped_or_prevented_writes": list(skipped_or_prevented_writes),
        "target_kind": target_kind,
        "validation": dict(validation or {"status": "ok"}),
        "write_performed": False,
    }
    preview.update(extra)
    return preview


def emit_dry_run_preview(preview: Mapping[str, Any]) -> None:
    """Print the dry-run preview as stable JSON on stdout."""
    print(json.dumps(dict(preview), indent=2, sort_keys=True, allow_nan=False))


__all__ = [
    "DRY_RUN_CONTRACT_VERSION",
    "build_dry_run_preview",
    "emit_dry_run_preview",
]
