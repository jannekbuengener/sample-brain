"""Measurement event envelope and privacy validation (ADR-0006)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class PrivacyClass(str, Enum):
    LOCAL_ONLY = "local_only"
    EXPORT_SAFE = "export_safe"
    AGGREGATE_ONLY = "aggregate_only"


DOCUMENT_TYPE = "sample_brain.measurement_event"
SCHEMA_VERSION = "1.0.0"
SUPPORTED_EVENT_NAMES = frozenset({"pipeline.stage_finished"})
SUPPORTED_DOMAINS = frozenset({"pipeline"})
SUPPORTED_STATUSES = frozenset({"ok", "error", "cancelled", "skipped"})

STAGE_FINISHED_ALLOWED_PROPS = frozenset(
    {"stage", "wall_ms", "items_ok", "items_skip", "items_fail"}
)
STAGE_FINISHED_ALLOWED_STAGES = frozenset({"analyze"})

FORBIDDEN_PROP_KEYS = frozenset(
    {
        "path",
        "relpath",
        "file_path",
        "audio_path",
        "sample_path",
        "filename",
        "file_name",
        "title",
        "folder",
        "folder_name",
        "dirname",
        "library_root",
        "library_roots",
        "query",
        "prompt",
        "sample_id",
        "source_hash",
        "content_hash",
        "hash",
        "embedding",
        "embeddings",
        "waveform",
        "audio",
        "user",
        "username",
        "user_name",
        "host",
        "hostname",
        "machine",
        "machine_name",
        "device_id",
        "device_name",
        "api_key",
        "token",
        "secret",
        "message",
        "exception",
        "traceback",
        "error_message",
    }
)

_PRIVATE_PATH = re.compile(
    r"(?:^[A-Za-z]:[\\/]|^\\\\|^/(?:home|Users|root|mnt|Volumes|tmp)/)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MeasurementEvent:
    document_type: str
    schema_version: str
    event_name: str
    event_version: int
    occurred_at: str
    run_id: str
    session_id: Optional[str]
    domain: str
    privacy_class: PrivacyClass | str
    status: str
    reason_code: Optional[str]
    app: Mapping[str, Any]
    props: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        privacy = (
            self.privacy_class.value
            if isinstance(self.privacy_class, PrivacyClass)
            else str(self.privacy_class)
        )
        return {
            "document_type": self.document_type,
            "schema_version": self.schema_version,
            "event_name": self.event_name,
            "event_version": self.event_version,
            "occurred_at": self.occurred_at,
            "run_id": self.run_id,
            "session_id": self.session_id,
            "domain": self.domain,
            "privacy_class": privacy,
            "status": self.status,
            "reason_code": self.reason_code,
            "app": dict(self.app),
            "props": dict(self.props),
        }


def _privacy_ok(value: PrivacyClass | str) -> bool:
    if isinstance(value, PrivacyClass):
        return True
    try:
        PrivacyClass(str(value))
    except ValueError:
        return False
    return True


def _props_contain_path_leak(props: Mapping[str, Any]) -> bool:
    for value in props.values():
        if isinstance(value, str) and _PRIVATE_PATH.search(value):
            return True
    return False


def validate_event(event: MeasurementEvent) -> Optional[MeasurementEvent]:
    """Return the event if valid, else None (caller must drop — never raise)."""
    try:
        if event.document_type != DOCUMENT_TYPE:
            return None
        if event.schema_version != SCHEMA_VERSION:
            return None
        if event.event_name not in SUPPORTED_EVENT_NAMES:
            return None
        if not isinstance(event.event_version, int) or event.event_version < 1:
            return None
        if not event.occurred_at or not isinstance(event.occurred_at, str):
            return None
        if not event.run_id or not isinstance(event.run_id, str):
            return None
        if event.session_id is not None and not isinstance(event.session_id, str):
            return None
        if event.domain not in SUPPORTED_DOMAINS:
            return None
        if not _privacy_ok(event.privacy_class):
            return None
        if event.status not in SUPPORTED_STATUSES:
            return None
        if event.reason_code is not None and not isinstance(event.reason_code, str):
            return None
        if not isinstance(event.app, Mapping):
            return None
        if not isinstance(event.props, Mapping):
            return None

        prop_keys = set(event.props.keys())
        if prop_keys & FORBIDDEN_PROP_KEYS:
            return None
        if event.event_name == "pipeline.stage_finished":
            if prop_keys - STAGE_FINISHED_ALLOWED_PROPS:
                return None
            stage = event.props.get("stage")
            if stage not in STAGE_FINISHED_ALLOWED_STAGES:
                return None
            for key in ("wall_ms", "items_ok", "items_skip", "items_fail"):
                if key not in event.props:
                    return None
                value = event.props[key]
                if not isinstance(value, int) or isinstance(value, bool):
                    return None
                if value < 0:
                    return None
        if _props_contain_path_leak(event.props):
            return None
        return event
    except Exception:
        return None
