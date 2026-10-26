"""Measurement event envelope and privacy validation (ADR-0006)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional


class PrivacyClass(str, Enum):
    LOCAL_ONLY = "local_only"
    EXPORT_SAFE = "export_safe"
    AGGREGATE_ONLY = "aggregate_only"


DOCUMENT_TYPE = "sample_brain.measurement_event"
SCHEMA_VERSION = "1.0.0"
SUPPORTED_EVENT_NAMES = frozenset({"pipeline.stage_finished", "match.query_finished"})
SUPPORTED_DOMAINS = frozenset({"pipeline", "match"})
SUPPORTED_STATUSES = frozenset({"ok", "error", "cancelled", "skipped"})

STAGE_FINISHED_ALLOWED_PROPS = frozenset(
    {"stage", "wall_ms", "items_ok", "items_skip", "items_fail"}
)
STAGE_FINISHED_ALLOWED_STAGES = frozenset({"analyze"})
MATCH_QUERY_FINISHED_ALLOWED_PROPS = frozenset({"wall_ms", "result_count"})

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

# UTC ISO-8601 with exactly 3 fractional milliseconds and 'Z' suffix
_UTC_MS_Z = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$")

# App metadata allowed keys (documented only)
_APP_ALLOWED_KEYS = frozenset({"app_version", "git_sha", "analyzer_version", "search_backend"})

# reason_code: stable machine codes, starts with uppercase letter, alnum/underscore, max 63 chars
_REASON_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

# Git SHA: None or 7-40 hex characters (case-insensitive)
_GIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,40}$")

# Safe token bounds: max 64 chars, no paths, no spaces, no equals
_SAFE_TOKEN_MAX_LEN = 64
_SAFE_TOKEN_FORBIDDEN = re.compile(r"[\s/\\=]")


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


def _utc_ms_z_ok(value: str) -> bool:
    if not _UTC_MS_Z.match(value):
        return False
    try:
        dt = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
        if dt.tzinfo is not None or value[-1] != "Z":
            return False
    except ValueError:
        return False
    return True


def _canonical_uuid4_ok(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError):
        return False
    return (
        parsed.version == 4
        and parsed.variant == uuid.RFC_4122
        and str(parsed) == value
    )


def _safe_token_ok(value: Optional[str]) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    if not value:
        return False
    if len(value) > _SAFE_TOKEN_MAX_LEN:
        return False
    if _SAFE_TOKEN_FORBIDDEN.search(value):
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
        if not _utc_ms_z_ok(event.occurred_at):
            return None
        if not _canonical_uuid4_ok(event.run_id):
            return None
        if event.session_id is not None:
            if not isinstance(event.session_id, str):
                return None
            if not _canonical_uuid4_ok(event.session_id):
                return None
        if event.domain not in SUPPORTED_DOMAINS:
            return None
        if not _privacy_ok(event.privacy_class):
            return None
        if event.status not in SUPPORTED_STATUSES:
            return None
        if event.reason_code is not None:
            if not isinstance(event.reason_code, str):
                return None
            if not _REASON_CODE_PATTERN.match(event.reason_code):
                return None
        if not isinstance(event.app, Mapping):
            return None
        # App metadata keys must be documented; values must be safe tokens (or None)
        for k, v in event.app.items():
            if k not in _APP_ALLOWED_KEYS:
                return None
            if not _safe_token_ok(v):
                return None
            if k == "git_sha" and v is not None and not _GIT_SHA_PATTERN.match(v):
                return None
        if not isinstance(event.props, Mapping):
            return None

        prop_keys = set(event.props.keys())
        if prop_keys & FORBIDDEN_PROP_KEYS:
            return None
        if event.event_name == "pipeline.stage_finished":
            if event.domain != "pipeline":
                return None
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
        elif event.event_name == "match.query_finished":
            if event.domain != "match":
                return None
            if prop_keys - MATCH_QUERY_FINISHED_ALLOWED_PROPS:
                return None
            for key in ("wall_ms", "result_count"):
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
