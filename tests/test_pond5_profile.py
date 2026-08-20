from __future__ import annotations

import json

import pytest

from src.config_loader import ConfigError
from src.pond5_profile import profile_hold_reasons, resolve_pond5_profile


def _config() -> dict:
    return {
        "pond5": {
            "contributor": {
                "composer": "Example Composer",
                "ipi": None,
                "pro": None,
                "publisher": None,
                "copyright_owner": "Example Owner",
            },
            "rights": {
                "ownership_authorized": True,
                "third_party_elements_cleared_for_resale": True,
                "cleared_for_sampling": False,
            },
            "listing": {"default_price_usd": 25},
        }
    }


def test_valid_profile_resolves_manual_values():
    result = resolve_pond5_profile(_config())

    assert result["document_type"] == "sample_brain.pond5_profile"
    assert result["schema_version"] == "1.0.0"
    assert result["contributor"]["composer"] == {
        "status": "ok",
        "value": "Example Composer",
        "source_ref": "pond5_profile_config",
    }
    assert result["rights"]["cleared_for_sampling"]["value"] is False
    assert result["listing"]["price"]["value"] == 25.0


def test_missing_optional_values_remain_unknown():
    result = resolve_pond5_profile({"pond5": {}})

    assert result["contributor"]["ipi"]["status"] == "unknown"
    assert result["contributor"]["ipi"]["value"] is None
    assert result["listing"]["price"]["status"] == "unknown"


def test_per_track_override_wins_over_profile_default():
    result = resolve_pond5_profile(
        _config(),
        per_track_overrides={
            "contributor": {"composer": "Track Composer"},
            "rights": {"cleared_for_sampling": True},
            "listing": {"default_price_usd": 30},
        },
    )

    assert result["contributor"]["composer"]["value"] == "Track Composer"
    assert result["contributor"]["composer"]["source_ref"] == "pond5_per_track_override"
    assert result["rights"]["cleared_for_sampling"]["value"] is True
    assert result["listing"]["price"]["value"] == 30.0


def test_explicit_false_rights_value_is_not_unknown():
    cfg = _config()
    cfg["pond5"]["rights"]["ownership_authorized"] = False

    result = resolve_pond5_profile(cfg)

    assert result["rights"]["ownership_authorized"] == {
        "status": "ok",
        "value": False,
        "source_ref": "pond5_profile_config",
    }
    assert "OWNERSHIP_NOT_AUTHORIZED" in profile_hold_reasons(result)


def test_explicit_null_override_remains_unknown_and_wins():
    result = resolve_pond5_profile(
        _config(),
        per_track_overrides={"contributor": {"composer": None}},
    )

    assert result["contributor"]["composer"]["status"] == "unknown"
    assert result["contributor"]["composer"]["source_ref"] == "pond5_per_track_override"
    assert "COMPOSER_MISSING" in profile_hold_reasons(result)


def test_missing_required_manual_values_fail_closed_as_hold_reasons():
    result = resolve_pond5_profile({"pond5": {}})

    assert profile_hold_reasons(result) == [
        "COMPOSER_MISSING",
        "OWNERSHIP_AUTHORIZATION_UNRESOLVED",
        "THIRD_PARTY_CLEARANCE_UNRESOLVED",
        "SAMPLING_POLICY_UNSET",
    ]


def test_cleared_for_sampling_false_is_resolved_not_blocking():
    result = resolve_pond5_profile(_config())

    assert "SAMPLING_POLICY_UNSET" not in profile_hold_reasons(result)
    assert profile_hold_reasons(result) == []


def test_invalid_contributor_type_is_rejected():
    cfg = _config()
    cfg["pond5"]["contributor"]["composer"] = 123

    with pytest.raises(ConfigError, match="composer"):
        resolve_pond5_profile(cfg)


def test_invalid_rights_type_is_rejected():
    cfg = _config()
    cfg["pond5"]["rights"]["ownership_authorized"] = "yes"

    with pytest.raises(ConfigError, match="ownership_authorized"):
        resolve_pond5_profile(cfg)


def test_profile_output_contains_no_machine_local_path_from_unrelated_config():
    cfg = _config()
    cfg["library_roots"] = [r"C:\\Users\\Private\\Samples"]
    cfg["database"] = {"path": r"D:\\Private\\catalog.db"}

    result = resolve_pond5_profile(cfg)
    serialized = json.dumps(result, sort_keys=True)

    assert "C:\\\\Users" not in serialized
    assert "D:\\\\Private" not in serialized
    assert "catalog.db" not in serialized


def test_profile_does_not_accept_track_map_or_semantic_fallbacks():
    cfg = {
        "pond5": {},
        "track_map": {"composer": "Invented"},
        "semantic": {"copyright_owner": "Invented"},
    }

    result = resolve_pond5_profile(cfg)

    assert result["contributor"]["composer"]["status"] == "unknown"
    assert result["contributor"]["copyright_owner"]["status"] == "unknown"


def test_empty_non_mapping_overrides_are_rejected():
    with pytest.raises(ConfigError, match="overrides must be a mapping"):
        resolve_pond5_profile(_config(), per_track_overrides=[])  # type: ignore[arg-type]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_default_price_is_rejected(value: float):
    cfg = _config()
    cfg["pond5"]["listing"]["default_price_usd"] = value

    with pytest.raises(ConfigError, match="finite"):
        resolve_pond5_profile(cfg)


def test_hold_reasons_reject_malformed_ok_composer_value():
    result = resolve_pond5_profile(_config())
    result["contributor"]["composer"] = {"status": "ok", "value": None}

    assert "COMPOSER_MISSING" in profile_hold_reasons(result)


def test_hold_reasons_reject_malformed_ok_sampling_value():
    result = resolve_pond5_profile(_config())
    result["rights"]["cleared_for_sampling"] = {"status": "ok", "value": None}

    assert "SAMPLING_POLICY_UNSET" in profile_hold_reasons(result)


@pytest.mark.parametrize(
    ("field", "value", "expected_reason"),
    [
        ("ownership_authorized", None, "OWNERSHIP_AUTHORIZATION_UNRESOLVED"),
        ("ownership_authorized", "yes", "OWNERSHIP_AUTHORIZATION_UNRESOLVED"),
        ("ownership_authorized", False, "OWNERSHIP_NOT_AUTHORIZED"),
        ("ownership_authorized", True, None),
        (
            "third_party_elements_cleared_for_resale",
            None,
            "THIRD_PARTY_CLEARANCE_UNRESOLVED",
        ),
        (
            "third_party_elements_cleared_for_resale",
            "yes",
            "THIRD_PARTY_CLEARANCE_UNRESOLVED",
        ),
        (
            "third_party_elements_cleared_for_resale",
            False,
            "THIRD_PARTY_CLEARANCE_DENIED",
        ),
        ("third_party_elements_cleared_for_resale", True, None),
    ],
)
def test_hold_reasons_classify_deserialized_rights_values(
    field: str, value: object, expected_reason: str | None
):
    result = resolve_pond5_profile(_config())
    result["rights"][field] = {
        "status": "ok",
        "value": value,
        "source_ref": "pond5_profile_config",
    }

    reasons = profile_hold_reasons(result)

    if expected_reason is None:
        assert not any(
            reason in reasons
            for reason in (
                "OWNERSHIP_AUTHORIZATION_UNRESOLVED",
                "OWNERSHIP_NOT_AUTHORIZED",
                "THIRD_PARTY_CLEARANCE_UNRESOLVED",
                "THIRD_PARTY_CLEARANCE_DENIED",
            )
        )
    else:
        assert expected_reason in reasons


@pytest.mark.parametrize(
    ("section", "field", "hold_reason"),
    [
        ("contributor", "composer", "COMPOSER_MISSING"),
        ("rights", "ownership_authorized", "OWNERSHIP_AUTHORIZATION_UNRESOLVED"),
        (
            "rights",
            "third_party_elements_cleared_for_resale",
            "THIRD_PARTY_CLEARANCE_UNRESOLVED",
        ),
        ("rights", "cleared_for_sampling", "SAMPLING_POLICY_UNSET"),
    ],
)
@pytest.mark.parametrize(
    ("source_ref", "source_origin", "should_hold"),
    [
        (None, None, True),
        ("pond5_missing_source", None, True),
        ("pond5_wrong_origin", "unknown", True),
        ("pond5_profile_config", None, False),
        ("pond5_per_track_override", None, False),
    ],
)
def test_hold_reasons_require_resolved_allowed_manual_source(
    section: str,
    field: str,
    hold_reason: str,
    source_ref: str | None,
    source_origin: str | None,
    should_hold: bool,
):
    result = resolve_pond5_profile(_config())
    item = result[section][field]
    if source_ref is None:
        item.pop("source_ref")
    else:
        item["source_ref"] = source_ref
    if source_origin is not None:
        result["provenance"]["sources"][source_ref] = {"origin": source_origin}

    reasons = profile_hold_reasons(result)

    assert (hold_reason in reasons) is should_hold


def test_provenance_sources_are_portable_and_origin_explicit():
    result = resolve_pond5_profile(_config())
    sources = result["provenance"]["sources"]

    assert sources["pond5_profile_config"]["origin"] == "profile"
    assert sources["pond5_per_track_override"]["origin"] == "per_track_override"
    assert sources["pond5_unknown"]["origin"] == "unknown"
    assert "path" not in json.dumps(sources, sort_keys=True).lower()
