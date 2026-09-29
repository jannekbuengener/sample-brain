"""Deterministic local-folder export for Screen-1 Live Kit (#728).

Reads :class:`LiveKitState` only. Copies assigned source audio byte-identically
into a portable folder tree with a relative ``manifest.json``. Never mutates
sources or kit state. Fail-closed for empty kits and existing destinations.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

LIVE_KIT_EXPORT_DIR_NAME = "Sample Brain Live Kit"
LIVE_KIT_EXPORT_SCHEMA_VERSION = 1
LIVE_KIT_EXPORT_KIT_TYPE = "sample_brain_live_kit"
LIVE_KIT_EXPORT_TYPE = "local_folder"

_WINDOWS_RESERVED = frozenset(
    {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{i}" for i in range(1, 10)),
        *(f"lpt{i}" for i in range(1, 10)),
    }
)
_UNSAFE_CHARS = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class LiveKitExportResult:
    ok: bool
    export_path: Path | None = None
    error_code: str | None = None
    error_message: str | None = None
    assigned_count: int = 0
    empty_count: int = 0


@dataclass(frozen=True)
class _PlannedSlot:
    group: str
    slot: str
    group_index: int
    slot_index: int
    group_folder: str
    assigned: bool
    display_name: str | None
    source_path: Path | None
    export_relpath: str | None
    bpm: float | None = None
    key: str | None = None
    pred_type: str | None = None


def _failure(
    code: str,
    message: str,
    *,
    assigned_count: int = 0,
    empty_count: int = 0,
) -> LiveKitExportResult:
    return LiveKitExportResult(
        ok=False,
        error_code=code,
        error_message=message,
        assigned_count=assigned_count,
        empty_count=empty_count,
    )


def _slugify(value: str) -> str:
    text = value.strip().casefold()
    text = text.replace("+", " ").replace("/", " ").replace("\\", " ")
    text = _UNSAFE_CHARS.sub("-", text).strip("-")
    if not text:
        text = "item"
    # Only the bare reserved device name is unsafe on Windows (e.g. "con.wav").
    if text in _WINDOWS_RESERVED:
        text = f"_{text}"
    return text


def _group_folder_name(group_index: int, group: str) -> str:
    return f"{group_index:02d}_{_slugify(group)}"


def _slot_filename(slot_index: int, slot: str, source_path: Path) -> str:
    stem = _slugify(source_path.stem)
    suffix = source_path.suffix.casefold()
    if not suffix.startswith("."):
        suffix = f".{suffix}" if suffix else ".wav"
    suffix_body = re.sub(r"[^a-z0-9]", "", suffix[1:])
    suffix = f".{suffix_body}" if suffix_body else ".wav"
    return f"{slot_index:02d}_{_slugify(slot)}__{stem}{suffix}"


def _snapshot_assignments(state: LiveKitState) -> list[_PlannedSlot]:
    planned: list[_PlannedSlot] = []
    for group_index, (group, slots) in enumerate(LIVE_KIT_SLOT_MAPPING, start=1):
        group_folder = _group_folder_name(group_index, group)
        for slot_index, slot in enumerate(slots, start=1):
            row = state.assignment_for(group, slot)
            if row is None:
                planned.append(
                    _PlannedSlot(
                        group=group,
                        slot=slot,
                        group_index=group_index,
                        slot_index=slot_index,
                        group_folder=group_folder,
                        assigned=False,
                        display_name=None,
                        source_path=None,
                        export_relpath=None,
                    )
                )
                continue
            source_path = Path(row.path)
            filename = _slot_filename(slot_index, slot, source_path)
            relpath = f"audio/{group_folder}/{filename}"
            planned.append(
                _PlannedSlot(
                    group=group,
                    slot=slot,
                    group_index=group_index,
                    slot_index=slot_index,
                    group_folder=group_folder,
                    assigned=True,
                    display_name=row.display_name or source_path.name,
                    source_path=source_path,
                    export_relpath=relpath,
                    bpm=row.bpm,
                    key=row.key,
                    pred_type=row.pred_type,
                )
            )
    return planned


def _validate_sources(planned: list[_PlannedSlot]) -> LiveKitExportResult | None:
    for item in planned:
        if not item.assigned or item.source_path is None:
            continue
        path = item.source_path
        if not path.exists():
            return _failure(
                "SOURCE_MISSING",
                "Eine zugewiesene Quelldatei fehlt. Export abgebrochen.",
            )
        if not path.is_file():
            return _failure(
                "SOURCE_NOT_FILE",
                "Eine zugewiesene Quelle ist keine normale Datei. Export abgebrochen.",
            )
        try:
            with path.open("rb") as handle:
                handle.read(1)
        except OSError:
            return _failure(
                "SOURCE_UNREADABLE",
                "Eine zugewiesene Quelldatei ist nicht lesbar. Export abgebrochen.",
            )
    return None


def _validate_destination(destination_parent: Path) -> LiveKitExportResult | None:
    try:
        parent = destination_parent.expanduser()
    except (OSError, RuntimeError, ValueError):
        return _failure(
            "DESTINATION_INVALID",
            "Zielordner ist ungültig. Export abgebrochen.",
        )
    if not parent.exists() or not parent.is_dir():
        return _failure(
            "DESTINATION_INVALID",
            "Zielordner ist ungültig oder existiert nicht. Export abgebrochen.",
        )
    probe = parent / ".sample-brain-live-kit-export-probe"
    try:
        with probe.open("wb") as handle:
            handle.write(b"ok")
        probe.unlink(missing_ok=True)
    except OSError:
        probe.unlink(missing_ok=True)
        return _failure(
            "DESTINATION_NOT_WRITABLE",
            "Zielordner ist nicht beschreibbar. Export abgebrochen.",
        )
    return None


def _ensure_no_internal_collisions(planned: list[_PlannedSlot]) -> LiveKitExportResult | None:
    seen: set[str] = set()
    for item in planned:
        if item.export_relpath is None:
            continue
        if item.export_relpath in seen:
            return _failure(
                "INTERNAL_COLLISION",
                "Interner Namenskonflikt im Exportplan. Export abgebrochen.",
            )
        seen.add(item.export_relpath)
    return None


def _build_manifest(planned: list[_PlannedSlot]) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    current_group: str | None = None
    current_entry: dict[str, Any] | None = None
    for item in planned:
        if item.group != current_group:
            current_group = item.group
            current_entry = {
                "name": item.group,
                "folder": item.group_folder,
                "slots": [],
            }
            groups.append(current_entry)
        assert current_entry is not None
        slot_entry: dict[str, Any] = {
            "group": item.group,
            "slot": item.slot,
            "assigned": item.assigned,
            "display_name": item.display_name,
            "audio_path": item.export_relpath,
        }
        if item.assigned:
            if item.bpm is not None:
                slot_entry["bpm"] = item.bpm
            if item.key:
                slot_entry["key"] = item.key
            if item.pred_type:
                slot_entry["pred_type"] = item.pred_type
        current_entry["slots"].append(slot_entry)
    return {
        "schema_version": LIVE_KIT_EXPORT_SCHEMA_VERSION,
        "kit_type": LIVE_KIT_EXPORT_KIT_TYPE,
        "export_type": LIVE_KIT_EXPORT_TYPE,
        "groups": groups,
    }


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)


def export_live_kit(
    state: LiveKitState,
    destination_parent: Path | str,
) -> LiveKitExportResult:
    """Export a Live Kit snapshot to ``<destination_parent>/Sample Brain Live Kit``.

    Empty kits are rejected. Partial kits are allowed. Sources are copied
    byte-identically after full validation into a staging directory, then
    moved into place only on complete success.
    """
    planned = _snapshot_assignments(state)
    assigned = [item for item in planned if item.assigned]
    empty_count = len(planned) - len(assigned)
    assigned_count = len(assigned)

    if assigned_count == 0:
        return _failure(
            "EMPTY_KIT",
            "Live Kit ist leer. Export nicht möglich.",
            assigned_count=0,
            empty_count=empty_count,
        )

    source_error = _validate_sources(planned)
    if source_error is not None:
        return LiveKitExportResult(
            ok=False,
            error_code=source_error.error_code,
            error_message=source_error.error_message,
            assigned_count=assigned_count,
            empty_count=empty_count,
        )

    parent = Path(destination_parent)
    destination_error = _validate_destination(parent)
    if destination_error is not None:
        return LiveKitExportResult(
            ok=False,
            error_code=destination_error.error_code,
            error_message=destination_error.error_message,
            assigned_count=assigned_count,
            empty_count=empty_count,
        )

    collision_error = _ensure_no_internal_collisions(planned)
    if collision_error is not None:
        return LiveKitExportResult(
            ok=False,
            error_code=collision_error.error_code,
            error_message=collision_error.error_message,
            assigned_count=assigned_count,
            empty_count=empty_count,
        )

    final_root = parent / LIVE_KIT_EXPORT_DIR_NAME
    if final_root.exists():
        return _failure(
            "OUTPUT_EXISTS",
            "Exportordner existiert bereits. Bitte einen anderen Zielordner wählen.",
            assigned_count=assigned_count,
            empty_count=empty_count,
        )

    staging: Path | None = None
    try:
        staging = Path(
            tempfile.mkdtemp(
                prefix=".sample-brain-live-kit-export-",
                dir=str(parent),
            )
        )
        audio_root = staging / "audio"
        for item in planned:
            if not item.assigned or item.source_path is None or item.export_relpath is None:
                continue
            target = staging / Path(item.export_relpath)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item.source_path, target)

        for group_index, (group, _slots) in enumerate(LIVE_KIT_SLOT_MAPPING, start=1):
            (audio_root / _group_folder_name(group_index, group)).mkdir(
                parents=True, exist_ok=True
            )

        manifest = _build_manifest(planned)
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=False) + "\n",
            encoding="utf-8",
        )

        if final_root.exists():
            _remove_tree(staging)
            return _failure(
                "OUTPUT_EXISTS",
                "Exportordner existiert bereits. Bitte einen anderen Zielordner wählen.",
                assigned_count=assigned_count,
                empty_count=empty_count,
            )

        os.replace(staging, final_root)
        staging = None
    except OSError:
        if staging is not None:
            _remove_tree(staging)
        if final_root.exists():
            _remove_tree(final_root)
        return _failure(
            "EXPORT_FAILED",
            "Export fehlgeschlagen. Es wurde keine Ausgabe belassen.",
            assigned_count=assigned_count,
            empty_count=empty_count,
        )

    return LiveKitExportResult(
        ok=True,
        export_path=final_root,
        assigned_count=assigned_count,
        empty_count=empty_count,
    )


__all__ = [
    "LIVE_KIT_EXPORT_DIR_NAME",
    "LIVE_KIT_EXPORT_KIT_TYPE",
    "LIVE_KIT_EXPORT_SCHEMA_VERSION",
    "LIVE_KIT_EXPORT_TYPE",
    "LiveKitExportResult",
    "export_live_kit",
]
