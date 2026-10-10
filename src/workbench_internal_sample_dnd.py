"""Python-owned internal Sample drag contract for Edit/Kit (#1072).

Owns typed descriptors, sample resolution, visible Live-Kit target validation,
Add/Replace routing onto existing kit seams, feature gating, and delivery-id
replay protection. Does not own QML drag visuals (#1073), panel docking (#1070),
or external file DnD (#768).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

from .live_kits_registry import assign_sample_to_kit, replace_sample_assignment
from .workbench_controller import WorkbenchRow
from .workbench_live_kit import LIVE_KIT_SLOT_MAPPING, LiveKitState

KIND_INTERNAL_SAMPLE = "internal_sample"
KIND_INTERNAL_SAMPLE_DROP = "internal_sample_drop"

TARGET_LIVE_KIT_ASSIGNMENT = "live_kit_assignment"

SOURCE_BROWSER = "browser"
SOURCE_HARMONY = "harmony"
_SOURCE_SURFACES: frozenset[str] = frozenset({SOURCE_BROWSER, SOURCE_HARMONY})

_REJECTED_TARGET_KINDS: frozenset[str] = frozenset(
    {
        "arrangement",
        "live",
        "channel_rack",
        "rack",
        "step_sequencer",
        "panel_move",
        "external_file_drop",
        "unknown_surface",
    }
)

_FOREIGN_PAYLOAD_KINDS: frozenset[str] = frozenset(
    {
        "panel_move",
        "panel_swap",
        "panel_reflow",
        "external_file_drop",
        "resize",
        "collapse",
        "reveal",
        "waveform_click",
        "focus",
    }
)

_SLOTS_BY_GROUP: dict[str, tuple[str, ...]] = dict(LIVE_KIT_SLOT_MAPPING)


@dataclass(frozen=True)
class InternalSampleDescriptor:
    """Source-independent Sample identity for internal Edit drag."""

    relative_path: str
    source_surface: str
    kind: str = KIND_INTERNAL_SAMPLE

    def as_transport_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "relative_path": self.relative_path,
            "source_surface": self.source_surface,
        }


@dataclass(frozen=True)
class LiveKitAssignmentTarget:
    """Visible Edit Live-Kit assignment target identity."""

    group: str
    slot: str
    visible: bool = True
    kind: str = TARGET_LIVE_KIT_ASSIGNMENT


@dataclass(frozen=True)
class InternalSampleDropIntent:
    descriptor: InternalSampleDescriptor
    target: LiveKitAssignmentTarget
    delivery_id: str
    kind: str = KIND_INTERNAL_SAMPLE_DROP


@dataclass(frozen=True)
class InternalSampleDropResult:
    accepted: bool
    mutation: str | None = None
    reason: str | None = None
    evidence: str | None = None
    intent_kind: str = KIND_INTERNAL_SAMPLE_DROP


@dataclass
class InternalSampleDropSession:
    """In-process replay guard for identical delivery ids."""

    applied_delivery_ids: set[str] = field(default_factory=set)


# Process-owned default so replay protection cannot be silently disabled.
_PROCESS_DROP_SESSION = InternalSampleDropSession()


@dataclass(frozen=True)
class SampleResolution:
    """Catalog resolution outcome without leaking private absolute paths."""

    row: WorkbenchRow | None = None
    reason: str | None = None


def _normalize_relative_path(value: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("~"):
        return None
    parts = PurePosixPath(text).parts
    if not parts or any(part in ("", ".", "..") for part in parts):
        return None
    return "/".join(parts)


def _feature_enabled(features: Any) -> bool:
    return getattr(features, "internal_sample_dnd_enabled", False) is True


def descriptor_from_row(
    row: WorkbenchRow,
    *,
    source_surface: str,
    features: Any,
) -> InternalSampleDescriptor | None:
    """Build a typed descriptor when the feature is ON; otherwise inert."""
    if not _feature_enabled(features):
        return None
    if source_surface not in _SOURCE_SURFACES:
        return None
    if not isinstance(row, WorkbenchRow):
        return None
    relative = _normalize_relative_path(row.relative_path)
    if relative is None:
        return None
    return InternalSampleDescriptor(
        relative_path=relative,
        source_surface=source_surface,
    )


def parse_internal_sample_descriptor(payload: Any) -> InternalSampleDescriptor | None:
    """Parse a typed internal Sample descriptor; foreign payloads fail closed."""
    if isinstance(payload, InternalSampleDescriptor):
        if payload.kind != KIND_INTERNAL_SAMPLE:
            return None
        relative = _normalize_relative_path(payload.relative_path)
        if relative is None or payload.source_surface not in _SOURCE_SURFACES:
            return None
        return InternalSampleDescriptor(
            relative_path=relative,
            source_surface=payload.source_surface,
        )

    if isinstance(payload, Mapping):
        kind = payload.get("kind")
        if kind in _FOREIGN_PAYLOAD_KINDS:
            return None
        if kind != KIND_INTERNAL_SAMPLE:
            return None
        relative = _normalize_relative_path(str(payload.get("relative_path") or ""))
        source_surface = payload.get("source_surface")
        if relative is None or source_surface not in _SOURCE_SURFACES:
            return None
        return InternalSampleDescriptor(
            relative_path=relative,
            source_surface=str(source_surface),
        )

    kind = getattr(payload, "kind", None)
    if kind in _FOREIGN_PAYLOAD_KINDS or kind == "panel_move":
        return None
    return None


def parse_internal_sample_drop_intent(payload: Any) -> InternalSampleDropIntent | None:
    """Parse a full drop intent; reject docking/file payloads fail-closed."""
    if isinstance(payload, InternalSampleDropIntent):
        if payload.kind != KIND_INTERNAL_SAMPLE_DROP:
            return None
        if not isinstance(payload.delivery_id, str) or not payload.delivery_id.strip():
            return None
        descriptor = parse_internal_sample_descriptor(payload.descriptor)
        if descriptor is None:
            return None
        target = payload.target
        if not isinstance(target, LiveKitAssignmentTarget):
            return None
        return InternalSampleDropIntent(
            descriptor=descriptor,
            target=target,
            delivery_id=payload.delivery_id.strip(),
        )

    if isinstance(payload, Mapping):
        kind = payload.get("kind")
        if kind in _FOREIGN_PAYLOAD_KINDS:
            return None
        if kind not in (KIND_INTERNAL_SAMPLE_DROP, KIND_INTERNAL_SAMPLE):
            return None
        descriptor = parse_internal_sample_descriptor(
            {
                "kind": KIND_INTERNAL_SAMPLE,
                "relative_path": payload.get("relative_path"),
                "source_surface": payload.get("source_surface"),
            }
            if kind == KIND_INTERNAL_SAMPLE
            else payload.get("descriptor")
        )
        if descriptor is None:
            return None
        raw_target = payload.get("target")
        if not isinstance(raw_target, Mapping):
            return None
        delivery_id = payload.get("delivery_id")
        if not isinstance(delivery_id, str) or not delivery_id.strip():
            return None
        target_kind = str(raw_target.get("kind") or TARGET_LIVE_KIT_ASSIGNMENT)
        return InternalSampleDropIntent(
            descriptor=descriptor,
            target=LiveKitAssignmentTarget(
                group=str(raw_target.get("group") or ""),
                slot=str(raw_target.get("slot") or ""),
                visible=bool(raw_target.get("visible", True)),
                kind=target_kind,
            ),
            delivery_id=delivery_id.strip(),
        )

    kind = getattr(payload, "kind", None)
    if kind in _FOREIGN_PAYLOAD_KINDS:
        return None
    return None


def list_visible_live_kit_targets(
    *,
    features: Any,
    live_kit_materialized: bool,
    visible_slot_keys: Sequence[tuple[str, str]] = (),
) -> tuple[LiveKitAssignmentTarget, ...]:
    """Discover eligible visible Live-Kit targets when the feature is ON."""
    if not _feature_enabled(features):
        return ()
    if not live_kit_materialized:
        return ()
    targets: list[LiveKitAssignmentTarget] = []
    for group, slot in visible_slot_keys:
        if group not in _SLOTS_BY_GROUP:
            continue
        if slot not in _SLOTS_BY_GROUP[group]:
            continue
        targets.append(
            LiveKitAssignmentTarget(
                group=group,
                slot=slot,
                visible=True,
            )
        )
    return tuple(targets)


def resolve_sample_from_catalog(
    descriptor: InternalSampleDescriptor,
    catalog: Sequence[WorkbenchRow],
) -> SampleResolution:
    """Resolve descriptor identity against a provided row catalog.

    Ambiguous relative_path matches fail closed. Missing files fail closed.
    Absolute paths are never returned in ``reason``.
    """
    needle = _normalize_relative_path(descriptor.relative_path)
    if needle is None:
        return SampleResolution(reason="unresolvable_sample")
    matches: list[WorkbenchRow] = []
    for row in catalog:
        if not isinstance(row, WorkbenchRow):
            continue
        candidate = _normalize_relative_path(row.relative_path)
        if candidate == needle:
            matches.append(row)
    if not matches:
        return SampleResolution(reason="unresolvable_sample")
    if len(matches) > 1:
        return SampleResolution(reason="ambiguous_sample")
    row = matches[0]
    try:
        if not Path(row.path).expanduser().is_file():
            return SampleResolution(reason="unresolvable_sample")
    except (OSError, ValueError, TypeError):
        return SampleResolution(reason="unresolvable_sample")
    return SampleResolution(row=row)


def _rollback_kit_slot(
    kit: LiveKitState,
    group: str,
    slot: str,
    prior: WorkbenchRow | None,
) -> None:
    """Restore a slot without re-entering assign/notify failure paths."""
    # Direct storage write: assign() may itself be the failing seam (or its
    # on_assignment_changed notifier). Rollback must not re-enter either.
    kit._assignments[group][slot] = prior


def apply_internal_sample_drop(
    intent: InternalSampleDropIntent,
    *,
    kit: LiveKitState,
    catalog: Sequence[WorkbenchRow],
    features: Any,
    live_kit_materialized: bool,
    visible_slot_keys: Sequence[tuple[str, str]],
    session: InternalSampleDropSession | None = None,
) -> InternalSampleDropResult:
    """Validate and route one internal Sample drop onto Live Kit Add/Replace."""
    drop_session = session if session is not None else _PROCESS_DROP_SESSION
    if not isinstance(intent, InternalSampleDropIntent):
        return InternalSampleDropResult(
            accepted=False,
            reason="invalid_intent",
            evidence="Drop intent was not typed.",
        )
    if getattr(intent, "kind", None) != KIND_INTERNAL_SAMPLE_DROP:
        return InternalSampleDropResult(
            accepted=False,
            reason="invalid_intent",
            evidence="Drop intent kind was rejected.",
        )
    if not _feature_enabled(features):
        return InternalSampleDropResult(
            accepted=False,
            reason="feature_disabled",
            evidence="Internal Sample drag is disabled.",
        )

    delivery_id = intent.delivery_id.strip() if isinstance(intent.delivery_id, str) else ""
    if not delivery_id:
        return InternalSampleDropResult(
            accepted=False,
            reason="invalid_intent",
            evidence="Drop delivery id is required.",
        )

    if delivery_id in drop_session.applied_delivery_ids:
        return InternalSampleDropResult(
            accepted=True,
            mutation=None,
            reason="duplicate_delivery",
            evidence="Identical drop delivery was already applied.",
        )

    descriptor = parse_internal_sample_descriptor(intent.descriptor)
    if descriptor is None:
        return InternalSampleDropResult(
            accepted=False,
            reason="invalid_descriptor",
            evidence="Sample descriptor was rejected.",
        )

    target = intent.target
    if not isinstance(target, LiveKitAssignmentTarget):
        return InternalSampleDropResult(
            accepted=False,
            reason="invalid_target",
            evidence="Drop target was rejected.",
        )
    if (
        target.kind != TARGET_LIVE_KIT_ASSIGNMENT
        or target.kind in _REJECTED_TARGET_KINDS
    ):
        return InternalSampleDropResult(
            accepted=False,
            reason="invalid_target",
            evidence="Only visible Live Kit assignment targets are accepted.",
        )
    if target.group not in _SLOTS_BY_GROUP or target.slot not in _SLOTS_BY_GROUP[target.group]:
        return InternalSampleDropResult(
            accepted=False,
            reason="invalid_target",
            evidence="Live Kit slot identity is invalid.",
        )

    # Authoritative visibility: transport visible flag alone cannot authorize.
    authoritative = list_visible_live_kit_targets(
        features=features,
        live_kit_materialized=live_kit_materialized,
        visible_slot_keys=visible_slot_keys,
    )
    authorized_keys = {(item.group, item.slot) for item in authoritative}
    if (
        not live_kit_materialized
        or not target.visible
        or (target.group, target.slot) not in authorized_keys
    ):
        return InternalSampleDropResult(
            accepted=False,
            reason="hidden_target",
            evidence="Live Kit assignment target is not visible.",
        )

    resolution = resolve_sample_from_catalog(descriptor, catalog)
    if resolution.row is None:
        reason = resolution.reason or "unresolvable_sample"
        evidence = (
            "Sample identity is ambiguous."
            if reason == "ambiguous_sample"
            else "Sample is no longer available for assignment."
        )
        return InternalSampleDropResult(
            accepted=False,
            reason=reason,
            evidence=evidence,
        )
    resolved = resolution.row

    prior = kit.assignment_for(target.group, target.slot)
    occupied = prior is not None
    mutation = "replace" if occupied else "assign"
    try:
        if occupied:
            replace_sample_assignment(kit, target.group, target.slot, resolved)
        else:
            assign_sample_to_kit(kit, target.group, target.slot, resolved)
    except Exception:
        _rollback_kit_slot(kit, target.group, target.slot, prior)
        return InternalSampleDropResult(
            accepted=False,
            reason="mutation_failed",
            evidence="Live Kit assignment could not be completed.",
        )

    drop_session.applied_delivery_ids.add(delivery_id)

    return InternalSampleDropResult(
        accepted=True,
        mutation=mutation,
        reason=None,
        evidence=None,
    )


__all__ = [
    "KIND_INTERNAL_SAMPLE",
    "KIND_INTERNAL_SAMPLE_DROP",
    "SOURCE_BROWSER",
    "SOURCE_HARMONY",
    "TARGET_LIVE_KIT_ASSIGNMENT",
    "InternalSampleDescriptor",
    "InternalSampleDropIntent",
    "InternalSampleDropResult",
    "InternalSampleDropSession",
    "LiveKitAssignmentTarget",
    "SampleResolution",
    "apply_internal_sample_drop",
    "descriptor_from_row",
    "list_visible_live_kit_targets",
    "parse_internal_sample_descriptor",
    "parse_internal_sample_drop_intent",
    "resolve_sample_from_catalog",
]
