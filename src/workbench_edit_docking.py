"""Python-owned Edit/Kit docking topology (#1070).

Owns bounded panel order, lock state, move/swap/reflow validation, persistence,
and typed intents. Does not own QML visuals, sample DnD, or musical session state.
Reuses #694 elastic ratios and #910 feature settings without replacing them.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
from typing import Any, Mapping

from .workbench_controller import workbench_state_dir

EDIT_DOCKING_SCHEMA_VERSION = 1
_EDIT_DOCKING_FILENAME = "edit_docking_topology.json"

EDIT_PANEL_LIBRARY = "library"
EDIT_PANEL_BROWSER = "browser"
EDIT_PANEL_HARMONY = "harmony"
EDIT_PANEL_LIVE_KIT = "live_kit"

EDIT_PANEL_IDS: frozenset[str] = frozenset(
    {
        EDIT_PANEL_LIBRARY,
        EDIT_PANEL_BROWSER,
        EDIT_PANEL_HARMONY,
        EDIT_PANEL_LIVE_KIT,
    }
)

CANONICAL_PANEL_ORDER: tuple[str, ...] = (
    EDIT_PANEL_LIBRARY,
    EDIT_PANEL_BROWSER,
    EDIT_PANEL_HARMONY,
    EDIT_PANEL_LIVE_KIT,
)

# Historical / foreign IDs that must never become docking targets.
REJECTED_PANEL_IDS: frozenset[str] = frozenset(
    {
        "arrangement",
        "live",
        "channel_rack",
        "rack",
        "step_sequencer",
    }
)

# Deterministic migration table: legacy id → Edit panel id or drop (None).
_LEGACY_PANEL_MIGRATION: Mapping[str, str | None] = {
    "livekit": EDIT_PANEL_LIVE_KIT,
    "channel_rack": None,
    "rack": None,
    "step_sequencer": None,
}

LOCK_LOCKED = "LOCKED"
LOCK_UNLOCKED = "UNLOCKED"
_LOCK_STATES: frozenset[str] = frozenset({LOCK_LOCKED, LOCK_UNLOCKED})

INTENT_PANEL_MOVE = "panel_move"
INTENT_PANEL_SWAP = "panel_swap"
INTENT_PANEL_REFLOW = "panel_reflow"
INTENT_RESIZE = "resize"
INTENT_COLLAPSE = "collapse"
INTENT_REVEAL = "reveal"
INTENT_SAMPLE_DRAG = "sample_drag"
INTENT_WAVEFORM_CLICK = "waveform_click"
INTENT_FOCUS = "focus"

INTENT_KINDS: frozenset[str] = frozenset(
    {
        INTENT_PANEL_MOVE,
        INTENT_PANEL_SWAP,
        INTENT_PANEL_REFLOW,
        INTENT_RESIZE,
        INTENT_COLLAPSE,
        INTENT_REVEAL,
        INTENT_SAMPLE_DRAG,
        INTENT_WAVEFORM_CLICK,
        INTENT_FOCUS,
    }
)

_DOCKING_MUTATION_KINDS: frozenset[str] = frozenset(
    {
        INTENT_PANEL_MOVE,
        INTENT_PANEL_SWAP,
        INTENT_PANEL_REFLOW,
    }
)


@dataclass(frozen=True)
class EditDockingMaterialization:
    """Which Edit panels are actually present/visible for topology participation."""

    library: bool = True
    browser: bool = True
    harmony: bool = False
    live_kit: bool = False

    def is_materialized(self, panel_id: str) -> bool:
        if panel_id == EDIT_PANEL_LIBRARY:
            return bool(self.library)
        if panel_id == EDIT_PANEL_BROWSER:
            return bool(self.browser)
        if panel_id == EDIT_PANEL_HARMONY:
            return bool(self.harmony)
        if panel_id == EDIT_PANEL_LIVE_KIT:
            return bool(self.live_kit)
        return False


@dataclass(frozen=True)
class EditDockingState:
    """Committed Edit topology + layout lock. Ratios remain in #694 preferences."""

    panel_order: tuple[str, ...] = CANONICAL_PANEL_ORDER
    lock_state: str = LOCK_LOCKED
    schema_version: int = EDIT_DOCKING_SCHEMA_VERSION


DEFAULT_EDIT_DOCKING_STATE = EditDockingState()


@dataclass(frozen=True)
class PanelMoveIntent:
    panel_id: str
    target_slot_id: str
    kind: str = INTENT_PANEL_MOVE


@dataclass(frozen=True)
class PanelSwapIntent:
    panel_a: str
    panel_b: str
    kind: str = INTENT_PANEL_SWAP


@dataclass(frozen=True)
class PanelReflowIntent:
    kind: str = INTENT_PANEL_REFLOW


@dataclass(frozen=True)
class CollapseIntent:
    panel_id: str
    kind: str = INTENT_COLLAPSE


@dataclass(frozen=True)
class RevealIntent:
    panel_id: str
    kind: str = INTENT_REVEAL


@dataclass(frozen=True)
class ResizeIntent:
    kind: str = INTENT_RESIZE


@dataclass(frozen=True)
class SampleDragIntent:
    kind: str = INTENT_SAMPLE_DRAG


@dataclass(frozen=True)
class WaveformClickIntent:
    kind: str = INTENT_WAVEFORM_CLICK


@dataclass(frozen=True)
class FocusIntent:
    kind: str = INTENT_FOCUS


@dataclass(frozen=True)
class EditDockingApplyResult:
    accepted: bool
    state: EditDockingState
    intent_kind: str
    reason: str | None = None


def edit_docking_topology_path(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Path:
    base = state_dir if state_dir is not None else workbench_state_dir(env=env)
    return Path(base) / _EDIT_DOCKING_FILENAME


def set_edit_docking_lock(state: EditDockingState, lock_state: str) -> EditDockingState:
    if not isinstance(state, EditDockingState):
        raise TypeError("state must be EditDockingState")
    if lock_state not in _LOCK_STATES:
        raise ValueError(f"lock_state must be one of {sorted(_LOCK_STATES)}")
    return replace(state, lock_state=lock_state)


def active_panel_order(
    state: EditDockingState,
    *,
    materialization: EditDockingMaterialization,
) -> tuple[str, ...]:
    """Materialized-only order; hidden panels leave no phantom slots."""
    order = tuple(state.panel_order)
    return tuple(
        panel_id
        for panel_id in order
        if panel_id in EDIT_PANEL_IDS and materialization.is_materialized(panel_id)
    )


def active_slot_assignments(
    state: EditDockingState,
    *,
    materialization: EditDockingMaterialization,
) -> dict[str, str]:
    """Contiguous edit_slot_N → panel_id for materialized panels only."""
    active = active_panel_order(state, materialization=materialization)
    return {f"edit_slot_{index}": panel_id for index, panel_id in enumerate(active)}


def apply_edit_docking_intent(
    state: EditDockingState,
    intent: Any,
    *,
    features: Any,
    materialization: EditDockingMaterialization,
    musical_session: Any | None = None,
) -> EditDockingApplyResult:
    """Apply a typed intent. Docking mutations never touch musical_session."""
    del musical_session  # Explicit non-owner: topology must not mutate session.
    if not isinstance(state, EditDockingState):
        raise TypeError("state must be EditDockingState")
    if not isinstance(materialization, EditDockingMaterialization):
        raise TypeError("materialization must be EditDockingMaterialization")

    kind = str(getattr(intent, "kind", "") or "")
    if kind not in INTENT_KINDS:
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=kind or "unknown",
            reason="unknown_intent",
        )

    # Non-docking intents: accepted passthrough; topology unchanged.
    if kind not in _DOCKING_MUTATION_KINDS:
        return EditDockingApplyResult(
            accepted=True,
            state=state,
            intent_kind=kind,
            reason="non_docking_passthrough",
        )

    if not _docking_feature_enabled(features):
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=kind,
            reason="feature_disabled",
        )
    if state.lock_state != LOCK_UNLOCKED:
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=kind,
            reason="layout_locked",
        )

    if kind == INTENT_PANEL_MOVE:
        return _apply_panel_move(state, intent, materialization=materialization)
    if kind == INTENT_PANEL_SWAP:
        return _apply_panel_swap(state, intent, materialization=materialization)
    if kind == INTENT_PANEL_REFLOW:
        # Reflow is a pure compact of preferred order against materialization;
        # preferred order itself is unchanged (no phantom rewrite).
        return EditDockingApplyResult(
            accepted=True,
            state=state,
            intent_kind=kind,
            reason="reflow_noop_preferred_order",
        )
    return EditDockingApplyResult(
        accepted=False,
        state=state,
        intent_kind=kind,
        reason="unsupported_docking_intent",
    )


def save_edit_docking_state(
    state: EditDockingState,
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> bool:
    if not isinstance(state, EditDockingState):
        raise TypeError("state must be EditDockingState")
    normalized = _normalize_state_or_default(state.panel_order, state.lock_state)
    path_file = edit_docking_topology_path(state_dir=state_dir, env=env)
    body = {
        "schema_version": EDIT_DOCKING_SCHEMA_VERSION,
        "lock_state": normalized.lock_state,
        "panel_order": list(normalized.panel_order),
    }
    try:
        path_file.parent.mkdir(parents=True, exist_ok=True)
        path_file.write_text(
            json.dumps(body, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def load_edit_docking_state(
    *,
    state_dir: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> EditDockingState:
    path_file = edit_docking_topology_path(state_dir=state_dir, env=env)
    if not path_file.is_file():
        return DEFAULT_EDIT_DOCKING_STATE
    try:
        raw = json.loads(path_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return DEFAULT_EDIT_DOCKING_STATE
    if not isinstance(raw, dict):
        return DEFAULT_EDIT_DOCKING_STATE
    version = raw.get("schema_version")
    if type(version) is not int or version != EDIT_DOCKING_SCHEMA_VERSION:
        return DEFAULT_EDIT_DOCKING_STATE
    lock_state = raw.get("lock_state")
    panel_order = raw.get("panel_order")
    if lock_state not in _LOCK_STATES:
        return DEFAULT_EDIT_DOCKING_STATE
    if not isinstance(panel_order, list):
        return DEFAULT_EDIT_DOCKING_STATE
    migrated = _migrate_panel_order(panel_order)
    if migrated is None:
        return DEFAULT_EDIT_DOCKING_STATE
    return EditDockingState(
        panel_order=migrated,
        lock_state=str(lock_state),
        schema_version=EDIT_DOCKING_SCHEMA_VERSION,
    )


def _docking_feature_enabled(features: Any) -> bool:
    value = getattr(features, "workspace_panel_docking_enabled", False)
    return value is True


def _apply_panel_move(
    state: EditDockingState,
    intent: PanelMoveIntent,
    *,
    materialization: EditDockingMaterialization,
) -> EditDockingApplyResult:
    panel_id = str(getattr(intent, "panel_id", "") or "")
    target_slot = str(getattr(intent, "target_slot_id", "") or "")
    if panel_id in REJECTED_PANEL_IDS or panel_id not in EDIT_PANEL_IDS:
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=INTENT_PANEL_MOVE,
            reason="invalid_panel",
        )
    if not materialization.is_materialized(panel_id):
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=INTENT_PANEL_MOVE,
            reason="panel_not_materialized",
        )

    active = list(active_panel_order(state, materialization=materialization))
    if panel_id not in active:
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=INTENT_PANEL_MOVE,
            reason="panel_not_active",
        )
    if not target_slot.startswith("edit_slot_"):
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=INTENT_PANEL_MOVE,
            reason="invalid_slot",
        )
    try:
        target_index = int(target_slot.removeprefix("edit_slot_"))
    except ValueError:
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=INTENT_PANEL_MOVE,
            reason="invalid_slot",
        )
    if target_index < 0 or target_index >= len(active):
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=INTENT_PANEL_MOVE,
            reason="invalid_slot",
        )

    source_index = active.index(panel_id)
    if source_index == target_index:
        return EditDockingApplyResult(
            accepted=True,
            state=state,
            intent_kind=INTENT_PANEL_MOVE,
            reason="already_at_target",
        )

    # Bounded magnetic move: remove from source and insert at target (reflow).
    # Explicit exchange remains PanelSwapIntent.
    moving = active.pop(source_index)
    active.insert(target_index, moving)
    new_order = _merge_active_into_preferred(state.panel_order, tuple(active))
    new_state = replace(state, panel_order=new_order)
    return EditDockingApplyResult(
        accepted=True,
        state=new_state,
        intent_kind=INTENT_PANEL_MOVE,
        reason=None,
    )


def _apply_panel_swap(
    state: EditDockingState,
    intent: PanelSwapIntent,
    *,
    materialization: EditDockingMaterialization,
) -> EditDockingApplyResult:
    panel_a = str(getattr(intent, "panel_a", "") or "")
    panel_b = str(getattr(intent, "panel_b", "") or "")
    for panel_id in (panel_a, panel_b):
        if panel_id in REJECTED_PANEL_IDS or panel_id not in EDIT_PANEL_IDS:
            return EditDockingApplyResult(
                accepted=False,
                state=state,
                intent_kind=INTENT_PANEL_SWAP,
                reason="invalid_panel",
            )
        if not materialization.is_materialized(panel_id):
            return EditDockingApplyResult(
                accepted=False,
                state=state,
                intent_kind=INTENT_PANEL_SWAP,
                reason="panel_not_materialized",
            )

    active = list(active_panel_order(state, materialization=materialization))
    if panel_a not in active or panel_b not in active:
        return EditDockingApplyResult(
            accepted=False,
            state=state,
            intent_kind=INTENT_PANEL_SWAP,
            reason="panel_not_active",
        )
    if panel_a == panel_b:
        return EditDockingApplyResult(
            accepted=True,
            state=state,
            intent_kind=INTENT_PANEL_SWAP,
            reason="identical_panels",
        )

    index_a = active.index(panel_a)
    index_b = active.index(panel_b)
    active[index_a], active[index_b] = active[index_b], active[index_a]
    new_order = _merge_active_into_preferred(state.panel_order, tuple(active))
    return EditDockingApplyResult(
        accepted=True,
        state=replace(state, panel_order=new_order),
        intent_kind=INTENT_PANEL_SWAP,
        reason=None,
    )


def _merge_active_into_preferred(
    preferred: tuple[str, ...] | list[str],
    active: tuple[str, ...],
) -> tuple[str, ...]:
    """Rewrite preferred order so materialized relative order matches ``active``.

    Hidden panels keep their relative positions between active anchors without
    inventing phantom slots in the active projection.
    """
    preferred_list = [panel_id for panel_id in preferred if panel_id in EDIT_PANEL_IDS]
    # Drop duplicates fail-closed already handled upstream; still guard.
    seen: set[str] = set()
    deduped: list[str] = []
    for panel_id in preferred_list:
        if panel_id in seen:
            continue
        seen.add(panel_id)
        deduped.append(panel_id)

    active_set = set(active)
    active_iter = iter(active)
    merged: list[str] = []
    for panel_id in deduped:
        if panel_id in active_set:
            merged.append(next(active_iter))
        else:
            merged.append(panel_id)
    # Append any active panels missing from preferred (should not happen).
    remaining = [panel_id for panel_id in active if panel_id not in merged]
    merged.extend(remaining)
    # Ensure every canonical panel remains representable for restart restore.
    for panel_id in CANONICAL_PANEL_ORDER:
        if panel_id not in merged:
            merged.append(panel_id)
    return tuple(merged)


def _migrate_panel_order(raw_order: list[Any]) -> tuple[str, ...] | None:
    migrated: list[str] = []
    seen: set[str] = set()
    for item in raw_order:
        if not isinstance(item, str):
            return None
        token = item.strip()
        if not token:
            return None
        if token in _LEGACY_PANEL_MIGRATION:
            mapped = _LEGACY_PANEL_MIGRATION[token]
            if mapped is None:
                continue
            token = mapped
        if token in REJECTED_PANEL_IDS:
            continue
        if token not in EDIT_PANEL_IDS:
            return None
        if token in seen:
            return None
        seen.add(token)
        migrated.append(token)
    if not migrated:
        return None
    for panel_id in CANONICAL_PANEL_ORDER:
        if panel_id not in seen:
            migrated.append(panel_id)
            seen.add(panel_id)
    return tuple(migrated)


def _normalize_state_or_default(
    panel_order: tuple[str, ...] | list[str],
    lock_state: str,
) -> EditDockingState:
    if lock_state not in _LOCK_STATES:
        return DEFAULT_EDIT_DOCKING_STATE
    if not isinstance(panel_order, (tuple, list)):
        return DEFAULT_EDIT_DOCKING_STATE
    migrated = _migrate_panel_order(list(panel_order))
    if migrated is None:
        return DEFAULT_EDIT_DOCKING_STATE
    return EditDockingState(
        panel_order=migrated,
        lock_state=lock_state,
        schema_version=EDIT_DOCKING_SCHEMA_VERSION,
    )


__all__ = [
    "CANONICAL_PANEL_ORDER",
    "DEFAULT_EDIT_DOCKING_STATE",
    "EDIT_DOCKING_SCHEMA_VERSION",
    "EDIT_PANEL_BROWSER",
    "EDIT_PANEL_HARMONY",
    "EDIT_PANEL_IDS",
    "EDIT_PANEL_LIBRARY",
    "EDIT_PANEL_LIVE_KIT",
    "INTENT_KINDS",
    "INTENT_COLLAPSE",
    "INTENT_FOCUS",
    "INTENT_PANEL_MOVE",
    "INTENT_PANEL_REFLOW",
    "INTENT_PANEL_SWAP",
    "INTENT_RESIZE",
    "INTENT_REVEAL",
    "INTENT_SAMPLE_DRAG",
    "INTENT_WAVEFORM_CLICK",
    "LOCK_LOCKED",
    "LOCK_UNLOCKED",
    "REJECTED_PANEL_IDS",
    "CollapseIntent",
    "EditDockingApplyResult",
    "EditDockingMaterialization",
    "EditDockingState",
    "FocusIntent",
    "PanelMoveIntent",
    "PanelReflowIntent",
    "PanelSwapIntent",
    "RevealIntent",
    "ResizeIntent",
    "SampleDragIntent",
    "WaveformClickIntent",
    "active_panel_order",
    "active_slot_assignments",
    "apply_edit_docking_intent",
    "edit_docking_topology_path",
    "load_edit_docking_state",
    "save_edit_docking_state",
    "set_edit_docking_lock",
]
