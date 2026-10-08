"""Live Kits track-package registration + explicit Open seam (#1099).

Owns a dedicated Live Kits listing scope for validated track packages.
Registration never activates Active Track. Explicit Open validates then
hands off to ``WorkbenchSession.bind_active_track_package`` (#1098).

Package rows are a separate entity kind — never WorkbenchRow / sample paths.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Literal

from .track_package import (
    OUTCOME_CORRUPT_OR_UNSUPPORTED,
    OUTCOME_MISSING_MEDIA,
    OUTCOME_OPEN,
    OUTCOME_PATH_ESCAPE_REJECTED,
    OUTCOME_WRITE_FAILED,
    TrackPackageResult,
    open_track_package,
    validate_track_package,
)
from .workbench_controller import WorkbenchRow, workbench_state_dir
from .workbench_live_kit import LiveKitState
from .workbench_session import WorkbenchSession

SCOPE_LIVE_KITS = "live_kits"
ENTITY_KIND_TRACK_PACKAGE: Literal["track_package"] = "track_package"

OUTCOME_READY = "ready"
OUTCOME_REGISTER_CONFLICT = "register_conflict"

REGISTRY_FILENAME = "live_kits_registry.json"
REGISTRY_SCHEMA_VERSION = 1

_SAFE_FAIL_MESSAGES = {
    OUTCOME_CORRUPT_OR_UNSUPPORTED: "Track package is corrupt or unsupported.",
    OUTCOME_MISSING_MEDIA: "Track package media is missing.",
    OUTCOME_PATH_ESCAPE_REJECTED: "Track package media path escape rejected.",
    OUTCOME_REGISTER_CONFLICT: "Registry slot already claimed by another track.",
    OUTCOME_WRITE_FAILED: "Live Kits registry could not be persisted.",
    OUTCOME_READY: "Track package registered.",
    OUTCOME_OPEN: "Track package opened.",
}


class PackageEntityError(TypeError):
    """Raised when a track-package row is used on a sample-only path."""


@dataclass(frozen=True)
class LiveKitPackageRow:
    """Listable Live Kits package entity — not a sample / WorkbenchRow."""

    track_id: str
    package_root: Path
    display_name: str
    status: str
    entity_kind: Literal["track_package"] = ENTITY_KIND_TRACK_PACKAGE


@dataclass(frozen=True)
class LiveKitsRegisterResult:
    outcome: str
    entry: LiveKitPackageRow | None = None
    message: str | None = None


@dataclass(frozen=True)
class LiveKitsOpenResult:
    outcome: str
    track_id: str | None = None
    package_root: Path | None = None
    message: str | None = None
    manifest_track_id: str | None = None


def _safe_message(outcome: str, fallback: str | None = None) -> str:
    if fallback and ":\\" not in fallback and "/Users/" not in fallback:
        # Still refuse absolute-looking Windows / Unix home paths.
        if not (len(fallback) >= 2 and fallback[1] == ":"):
            text = fallback.strip()
            if text and not Path(text).is_absolute():
                return text
    return _SAFE_FAIL_MESSAGES.get(outcome, "Track package operation failed.")


def require_sample_row(entity: object) -> WorkbenchRow:
    """Fail closed when a package row is passed into sample-only APIs."""
    if isinstance(entity, LiveKitPackageRow):
        raise PackageEntityError(
            "Track package rows cannot enter sample audition or assignment paths."
        )
    if getattr(entity, "entity_kind", None) == ENTITY_KIND_TRACK_PACKAGE:
        raise PackageEntityError(
            "Track package rows cannot enter sample audition or assignment paths."
        )
    if not isinstance(entity, WorkbenchRow):
        raise PackageEntityError(
            "Sample paths require a WorkbenchRow, not a package entity."
        )
    return entity


def audition_sample_row(entity: object) -> WorkbenchRow:
    """Sample Audition gate — package rows never enter PCM/waveform audition."""
    return require_sample_row(entity)


def assign_sample_to_kit(
    kit: LiveKitState,
    group: str,
    slot: str,
    entity: object,
) -> None:
    """Add-to-Kit / sample assignment gate — rejects package rows."""
    row = require_sample_row(entity)
    kit.assign(group, slot, row)


def replace_sample_assignment(
    kit: LiveKitState,
    group: str,
    slot: str,
    entity: object,
) -> None:
    """Replace-slot gate — same package-row rejection as assign."""
    assign_sample_to_kit(kit, group, slot, entity)


def registry_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / REGISTRY_FILENAME


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    text = json.dumps(dict(payload), indent=2, sort_keys=True) + "\n"
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _display_name_for(package_root: Path, track_id: str) -> str:
    name = package_root.name.strip()
    return name or track_id


class LiveKitsRegistry:
    """Deterministic Live Kits package listing (register ≠ open)."""

    scope: str = SCOPE_LIVE_KITS

    def __init__(
        self,
        *,
        state_dir: Path | None = None,
        env: Mapping[str, str] | None = None,
    ) -> None:
        self._state_dir = state_dir
        self._env = env
        self._entries: dict[str, LiveKitPackageRow] = {}
        self._load()

    def _path(self) -> Path:
        return registry_path(state_dir=self._state_dir, env=self._env)

    def _load(self) -> None:
        path = self._path()
        try:
            raw = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            self._entries = {}
            return
        except (OSError, UnicodeError):
            self._entries = {}
            return
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            self._entries = {}
            return
        if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            self._entries = {}
            return
        if data.get("scope") != SCOPE_LIVE_KITS:
            self._entries = {}
            return
        packages = data.get("packages")
        if not isinstance(packages, list):
            self._entries = {}
            return
        loaded: dict[str, LiveKitPackageRow] = {}
        for item in packages:
            if not isinstance(item, dict):
                continue
            track_id = item.get("track_id")
            root_text = item.get("package_root")
            status = item.get("status", OUTCOME_READY)
            display_name = item.get("display_name")
            entity_kind = item.get("entity_kind", ENTITY_KIND_TRACK_PACKAGE)
            if entity_kind != ENTITY_KIND_TRACK_PACKAGE:
                continue
            if not isinstance(track_id, str) or not track_id.strip():
                continue
            if not isinstance(root_text, str) or not root_text.strip():
                continue
            if not isinstance(status, str) or not status.strip():
                continue
            try:
                root = Path(root_text)
            except (OSError, ValueError, TypeError):
                continue
            name = (
                display_name.strip()
                if isinstance(display_name, str) and display_name.strip()
                else _display_name_for(root, track_id.strip())
            )
            loaded[track_id.strip()] = LiveKitPackageRow(
                track_id=track_id.strip(),
                package_root=root,
                display_name=name,
                status=status.strip(),
            )
        self._entries = loaded

    def _persist(self) -> None:
        packages = [
            {
                "entity_kind": row.entity_kind,
                "track_id": row.track_id,
                "package_root": str(row.package_root),
                "display_name": row.display_name,
                "status": row.status,
            }
            for row in self.list_packages()
        ]
        _atomic_write_json(
            self._path(),
            {
                "schema_version": REGISTRY_SCHEMA_VERSION,
                "scope": SCOPE_LIVE_KITS,
                "packages": packages,
            },
        )

    def list_packages(self) -> tuple[LiveKitPackageRow, ...]:
        """Deterministic listing ordered by track_id."""
        return tuple(
            self._entries[key] for key in sorted(self._entries.keys())
        )

    def register(self, package_root: Path | str) -> LiveKitsRegisterResult:
        """Dock a valid package under Live Kits without activating Active Track."""
        root = Path(package_root).resolve(strict=False)
        validated = validate_track_package(root)
        if validated.outcome != OUTCOME_OPEN or validated.track_id is None:
            outcome = validated.outcome
            if outcome == OUTCOME_OPEN:
                outcome = OUTCOME_CORRUPT_OR_UNSUPPORTED
            return LiveKitsRegisterResult(
                outcome=outcome,
                message=_safe_message(outcome, validated.message),
            )

        track_id = validated.track_id
        # Conflict: package root already claimed by a different track_id.
        for existing in self._entries.values():
            if existing.track_id == track_id:
                continue
            if existing.package_root.resolve(strict=False) == root:
                return LiveKitsRegisterResult(
                    outcome=OUTCOME_REGISTER_CONFLICT,
                    entry=existing,
                    message=_safe_message(OUTCOME_REGISTER_CONFLICT),
                )

        entry = LiveKitPackageRow(
            track_id=track_id,
            package_root=root,
            display_name=_display_name_for(root, track_id),
            status=OUTCOME_READY,
        )
        previous = self._entries.get(track_id)
        self._entries[track_id] = entry
        try:
            self._persist()
        except OSError:
            if previous is None:
                self._entries.pop(track_id, None)
            else:
                self._entries[track_id] = previous
            return LiveKitsRegisterResult(
                outcome=OUTCOME_WRITE_FAILED,
                entry=previous,
                message=_safe_message(OUTCOME_WRITE_FAILED),
            )
        return LiveKitsRegisterResult(
            outcome=OUTCOME_READY,
            entry=entry,
            message=_safe_message(OUTCOME_READY),
        )

    def _root_claim_conflict(
        self,
        *,
        package_root: Path,
        track_id: str,
    ) -> LiveKitPackageRow | None:
        """Return prior registration when root is claimed by a different track_id."""
        resolved = package_root.resolve(strict=False)
        for existing in self._entries.values():
            if existing.track_id == track_id:
                continue
            if existing.package_root.resolve(strict=False) == resolved:
                return existing
        return None

    def open_package(
        self,
        package_root: Path | str,
        *,
        session: WorkbenchSession,
    ) -> LiveKitsOpenResult:
        """Explicit Open: validate, then bind exactly one Active Track via #1098."""
        root = Path(package_root)
        # Fail-closed pre-check (also surfaces missing_media / path_escape / corrupt).
        precheck = open_track_package(root)
        if precheck.outcome != OUTCOME_OPEN or precheck.track_id is None:
            outcome = precheck.outcome
            if outcome == OUTCOME_OPEN:
                outcome = OUTCOME_CORRUPT_OR_UNSUPPORTED
            return LiveKitsOpenResult(
                outcome=outcome,
                track_id=precheck.track_id,
                package_root=root,
                message=_safe_message(outcome, precheck.message),
                manifest_track_id=precheck.track_id,
            )

        # Preserve prior registration + Active Track when root is already claimed.
        conflict = self._root_claim_conflict(
            package_root=root,
            track_id=precheck.track_id,
        )
        if conflict is not None:
            return LiveKitsOpenResult(
                outcome=OUTCOME_REGISTER_CONFLICT,
                track_id=conflict.track_id,
                package_root=conflict.package_root,
                message=_safe_message(OUTCOME_REGISTER_CONFLICT),
                manifest_track_id=precheck.track_id,
            )

        # Persist registry listing before Active Track bind so a registry write
        # failure cannot report Open failure after activation already succeeded.
        track_id = precheck.track_id
        resolved = root.resolve(strict=False)
        previous = self._entries.get(track_id)
        self._entries[track_id] = LiveKitPackageRow(
            track_id=track_id,
            package_root=resolved,
            display_name=_display_name_for(resolved, track_id),
            status=OUTCOME_READY,
        )
        try:
            self._persist()
        except OSError:
            if previous is None:
                self._entries.pop(track_id, None)
            else:
                self._entries[track_id] = previous
            return LiveKitsOpenResult(
                outcome=OUTCOME_WRITE_FAILED,
                track_id=track_id,
                package_root=root,
                message=_safe_message(OUTCOME_WRITE_FAILED),
                manifest_track_id=track_id,
            )

        bound: TrackPackageResult = session.bind_active_track_package(root)
        if bound.outcome != OUTCOME_OPEN:
            # #1098 owner preserves Active Track on failure; registry may already
            # list the package as ready (register ≠ activate — honest).
            return LiveKitsOpenResult(
                outcome=bound.outcome,
                track_id=bound.track_id,
                package_root=root,
                message=_safe_message(bound.outcome, bound.message),
                manifest_track_id=bound.track_id,
            )

        return LiveKitsOpenResult(
            outcome=OUTCOME_OPEN,
            track_id=bound.track_id,
            package_root=bound.package_root,
            message=_safe_message(OUTCOME_OPEN),
            manifest_track_id=bound.track_id,
        )


__all__ = [
    "ENTITY_KIND_TRACK_PACKAGE",
    "OUTCOME_READY",
    "OUTCOME_REGISTER_CONFLICT",
    "OUTCOME_WRITE_FAILED",
    "PackageEntityError",
    "REGISTRY_FILENAME",
    "REGISTRY_SCHEMA_VERSION",
    "SCOPE_LIVE_KITS",
    "LiveKitPackageRow",
    "LiveKitsOpenResult",
    "LiveKitsRegisterResult",
    "LiveKitsRegistry",
    "assign_sample_to_kit",
    "audition_sample_row",
    "registry_path",
    "replace_sample_assignment",
    "require_sample_row",
]
