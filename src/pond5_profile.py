"""Local contributor and rights defaults for Pond5 readiness.

This module resolves manual-only Pond5 facts from an already resolved Sample
Brain profile plus optional per-track overrides. It never inspects audio,
Track Map, semantic analysis, or network state.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
import math
from typing import Any

from .config_loader import ConfigError


POND5_PROFILE_DOCUMENT_TYPE = "sample_brain.pond5_profile"
POND5_PROFILE_SCHEMA_VERSION = "1.0.0"

_CONTRIBUTOR_FIELDS = (
    "composer",
    "ipi",
    "pro",
    "publisher",
    "copyright_owner",
)
_RIGHTS_FIELDS = (
    "ownership_authorized",
    "third_party_elements_cleared_for_resale",
    "cleared_for_sampling",
)

_PROFILE_SOURCE_REF = "pond5_profile_config"
_OVERRIDE_SOURCE_REF = "pond5_per_track_override"
_UNKNOWN_SOURCE_REF = "pond5_unknown"


def resolve_pond5_profile(
    config: Mapping[str, object],
    *,
    per_track_overrides: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Resolve portable Pond5 contributor/rights values.

    Precedence is deterministic: explicit per-track override > profile value >
    unknown. ``False`` is preserved as an explicit rights decision. ``None``
    remains unresolved and is never replaced with an inferred value.
    """

    if not isinstance(config, Mapping):
        raise ConfigError("resolved config must be a mapping")
    pond5 = config.get("pond5", {})
    if pond5 is None:
        pond5 = {}
    if not isinstance(pond5, Mapping):
        raise ConfigError("pond5 config must be a mapping")

    overrides = {} if per_track_overrides is None else per_track_overrides
    if not isinstance(overrides, Mapping):
        raise ConfigError("per-track Pond5 overrides must be a mapping")

    contributor_cfg = _mapping_or_empty(pond5.get("contributor"), "pond5.contributor")
    rights_cfg = _mapping_or_empty(pond5.get("rights"), "pond5.rights")
    listing_cfg = _mapping_or_empty(pond5.get("listing"), "pond5.listing")
    contributor_overrides = _mapping_or_empty(
        overrides.get("contributor"), "per_track_overrides.contributor"
    )
    rights_overrides = _mapping_or_empty(
        overrides.get("rights"), "per_track_overrides.rights"
    )
    listing_overrides = _mapping_or_empty(
        overrides.get("listing"), "per_track_overrides.listing"
    )

    contributor = {
        field: _resolve_string_field(field, contributor_cfg, contributor_overrides)
        for field in _CONTRIBUTOR_FIELDS
    }
    rights = {
        field: _resolve_bool_field(field, rights_cfg, rights_overrides)
        for field in _RIGHTS_FIELDS
    }
    listing = {
        "price": _resolve_price_field(listing_cfg, listing_overrides),
    }

    return {
        "document_type": POND5_PROFILE_DOCUMENT_TYPE,
        "schema_version": POND5_PROFILE_SCHEMA_VERSION,
        "contributor": contributor,
        "rights": rights,
        "listing": listing,
        "provenance": {
            "sources": {
                _OVERRIDE_SOURCE_REF: {
                    "kind": "manual_policy",
                    "origin": "per_track_override",
                },
                _PROFILE_SOURCE_REF: {
                    "kind": "local_config_profile",
                    "origin": "profile",
                },
                _UNKNOWN_SOURCE_REF: {
                    "kind": "manual_policy",
                    "origin": "unknown",
                },
            }
        },
    }


def profile_hold_reasons(profile: Mapping[str, object]) -> list[str]:
    """Return deterministic #450 readiness blockers without legal inference.

    This helper only checks whether the manual facts required by the v1 Pond5
    contract are resolved. Full technical/listing readiness remains #451.
    """

    contributor = _mapping_or_empty(profile.get("contributor"), "contributor")
    rights = _mapping_or_empty(profile.get("rights"), "rights")
    reasons: list[str] = []

    composer = _mapping_or_empty(contributor.get("composer"), "contributor.composer")
    if composer.get("status") != "ok":
        reasons.append("COMPOSER_MISSING")

    for field, missing_code, denied_code in (
        (
            "ownership_authorized",
            "OWNERSHIP_AUTHORIZATION_UNRESOLVED",
            "OWNERSHIP_NOT_AUTHORIZED",
        ),
        (
            "third_party_elements_cleared_for_resale",
            "THIRD_PARTY_CLEARANCE_UNRESOLVED",
            "THIRD_PARTY_CLEARANCE_DENIED",
        ),
    ):
        item = _mapping_or_empty(rights.get(field), f"rights.{field}")
        if item.get("status") != "ok":
            reasons.append(missing_code)
        elif item.get("value") is not True:
            reasons.append(denied_code)

    sampling = _mapping_or_empty(
        rights.get("cleared_for_sampling"), "rights.cleared_for_sampling"
    )
    if sampling.get("status") != "ok":
        reasons.append("SAMPLING_POLICY_UNSET")

    return reasons


def _resolve_string_field(
    field: str,
    profile: Mapping[str, object],
    overrides: Mapping[str, object],
) -> dict[str, object]:
    value, source_ref = _selected_value(field, profile, overrides)
    if value is None:
        return _manual_value(None, "unknown", source_ref)
    if not isinstance(value, str):
        raise ConfigError(f"pond5 contributor field {field} must be a string or null")
    normalized = value.strip()
    if not normalized:
        raise ConfigError(f"pond5 contributor field {field} must not be blank")
    return _manual_value(normalized, "ok", source_ref)


def _resolve_bool_field(
    field: str,
    profile: Mapping[str, object],
    overrides: Mapping[str, object],
) -> dict[str, object]:
    value, source_ref = _selected_value(field, profile, overrides)
    if value is None:
        return _manual_value(None, "unknown", source_ref)
    if not isinstance(value, bool):
        raise ConfigError(f"pond5 rights field {field} must be boolean or null")
    return _manual_value(value, "ok", source_ref)


def _resolve_price_field(
    profile: Mapping[str, object], overrides: Mapping[str, object]
) -> dict[str, object]:
    key = "default_price_usd"
    value, source_ref = _selected_value(key, profile, overrides)
    if value is None:
        return _manual_value(None, "unknown", source_ref)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError("pond5 listing.default_price_usd must be numeric or null")
    normalized = float(value)
    if not math.isfinite(normalized) or normalized < 0:
        raise ConfigError("pond5 listing.default_price_usd must be finite and >= 0")
    return _manual_value(normalized, "ok", source_ref)


def _selected_value(
    field: str,
    profile: Mapping[str, object],
    overrides: Mapping[str, object],
) -> tuple[object, str]:
    if field in overrides:
        return deepcopy(overrides[field]), _OVERRIDE_SOURCE_REF
    if field in profile:
        return deepcopy(profile[field]), _PROFILE_SOURCE_REF
    return None, _UNKNOWN_SOURCE_REF


def _manual_value(value: object, status: str, source_ref: str) -> dict[str, object]:
    return {
        "status": status,
        "value": value,
        "source_ref": source_ref,
    }


def _mapping_or_empty(value: object, label: str) -> Mapping[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigError(f"{label} must be a mapping")
    return value


__all__ = ["profile_hold_reasons", "resolve_pond5_profile"]
