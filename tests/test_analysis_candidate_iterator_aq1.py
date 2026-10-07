"""Real AQ1 search-space proof for #1064 W1 (bounded candidate iterator).

RED before GREEN: these tests define the AQ1 domain-owned provider contract and
prove advance / visited / exhaustion / firewall / identity guards against the
frozen W0 shared iterator. No loop driver. No TEST/HOLDOUT execution.
"""

from __future__ import annotations

import ast
import math
from pathlib import Path
from typing import Any

import pytest

from src.analysis_candidate_iterator import (
    AnalysisCandidateIteratorError,
    StaticSearchSpaceProvider,
    iterate_candidates,
    search_space_fingerprint,
    validate_result,
)
from src.analysis_eval_artifact import AnalysisEvalArtifactError
from src.aq_candidate_search_spaces.aq1_tempo import (
    SEARCH_SPACE_ID,
    SEARCH_SPACE_VERSION,
    Aq1TempoSearchSpaceProvider,
    pin_aq1_tempo_search_space,
)
from src.aq_headless_adapters.aq1_tempo_compare import (
    tempo_candidate_config_fingerprint,
)
from src.fsld_aq1_tempo_candidate_compare import (
    TEMPO_CANDIDATES,
    list_tempo_candidates,
)

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
AQ1_PROVIDER_PATH = SRC_ROOT / "aq_candidate_search_spaces" / "aq1_tempo.py"
AQ1_INIT_PATH = SRC_ROOT / "aq_candidate_search_spaces" / "__init__.py"

EXPECTED_ORDER = (
    "extract_features.bpm_normalization.none",
    "extract_features.bpm_normalization.heuristic",
    "extract_features.bpm_normalization.domain_110_170",
)


def _provider() -> Aq1TempoSearchSpaceProvider:
    return Aq1TempoSearchSpaceProvider()


def _members() -> list[dict[str, str]]:
    return _provider().ordered_members()


def _iterate(
    *,
    next_action: str = "continue_calibration",
    partition_role: str = "calibration",
    current_candidate_id: str | None = None,
    current_config_fingerprint: str | None = None,
    visited_candidate_ids: list[str] | None = None,
    search_space_fingerprint_override: str | None = None,
    provider: Aq1TempoSearchSpaceProvider | None = None,
) -> dict[str, Any]:
    space = provider or _provider()
    members = space.ordered_members()
    current_id = current_candidate_id or members[0]["candidate_id"]
    current_fp = current_config_fingerprint or members[0]["config_fingerprint"]
    visited = (
        list(visited_candidate_ids)
        if visited_candidate_ids is not None
        else [current_id]
    )
    return iterate_candidates(
        domain="aq1.tempo",
        next_action=next_action,
        partition_role=partition_role,
        provider=space,
        current_candidate_id=current_id,
        current_config_fingerprint=current_fp,
        visited_candidate_ids=visited,
        search_space_fingerprint=(
            search_space_fingerprint_override or space.search_space_fingerprint()
        ),
    )


def test_search_space_matches_real_aq1_set_and_declaration_order() -> None:
    provider = _provider()
    domain = list_tempo_candidates()
    assert tuple(c.candidate_id for c in domain) == EXPECTED_ORDER
    assert tuple(c.candidate_id for c in TEMPO_CANDIDATES) == EXPECTED_ORDER
    assert SEARCH_SPACE_ID == "aq1.tempo.candidate-search-space"
    assert SEARCH_SPACE_VERSION == "1.0.0"
    assert provider.search_space_id == SEARCH_SPACE_ID
    assert provider.search_space_version == SEARCH_SPACE_VERSION
    assert len(provider.ordered_members()) == len(TEMPO_CANDIDATES) == 3
    assert [m["candidate_id"] for m in provider.ordered_members()] == list(
        EXPECTED_ORDER
    )


def test_config_fingerprints_reuse_aq1_authority() -> None:
    provider = _provider()
    for member, candidate in zip(
        provider.ordered_members(), TEMPO_CANDIDATES, strict=True
    ):
        authority_fp = tempo_candidate_config_fingerprint(candidate.candidate_id)
        assert member["candidate_id"] == candidate.candidate_id
        assert member["config_fingerprint"] == authority_fp
        assert len(member["config_fingerprint"]) == 64


def test_search_space_fingerprint_deterministic_and_repeatable_provider() -> None:
    a = _provider()
    b = _provider()
    fp_a = a.search_space_fingerprint()
    fp_b = b.search_space_fingerprint()
    assert fp_a == fp_b
    assert fp_a == search_space_fingerprint(
        search_space_id=a.search_space_id,
        search_space_version=a.search_space_version,
        ordered_members=a.ordered_members(),
    )
    assert a.ordered_members() == b.ordered_members()
    assert len(fp_a) == 64


def test_continue_calibration_selects_first_unvisited_in_domain_order() -> None:
    members = _members()
    result = _iterate(
        current_candidate_id=members[0]["candidate_id"],
        current_config_fingerprint=members[0]["config_fingerprint"],
        visited_candidate_ids=[members[0]["candidate_id"]],
    )
    assert result["iterator_effect"] == "advance"
    assert result["next_action"] == "continue_calibration"
    assert result["next_candidate"] == members[1]
    assert result["next_candidate"]["candidate_id"] == EXPECTED_ORDER[1]
    assert result["next_candidate"]["candidate_id"] not in [members[0]["candidate_id"]]
    assert result["next_candidate"]["config_fingerprint"] == (
        tempo_candidate_config_fingerprint(EXPECTED_ORDER[1])
    )
    assert result["production_authorized"] is False


def test_visited_current_skips_to_next_real_candidate() -> None:
    members = _members()
    result = _iterate(
        current_candidate_id=members[0]["candidate_id"],
        current_config_fingerprint=members[0]["config_fingerprint"],
        visited_candidate_ids=[members[0]["candidate_id"]],
    )
    assert result["next_candidate"]["candidate_id"] == members[1]["candidate_id"]


def test_multiple_visited_selects_first_remaining_in_domain_order() -> None:
    members = _members()
    result = _iterate(
        current_candidate_id=members[1]["candidate_id"],
        current_config_fingerprint=members[1]["config_fingerprint"],
        visited_candidate_ids=[
            members[0]["candidate_id"],
            members[1]["candidate_id"],
        ],
    )
    assert result["iterator_effect"] == "advance"
    assert result["next_candidate"] == members[2]
    assert result["next_candidate"]["candidate_id"] not in {
        members[0]["candidate_id"],
        members[1]["candidate_id"],
    }


def test_full_exhaustion_no_wraparound_no_fake_candidate() -> None:
    members = _members()
    result = _iterate(
        current_candidate_id=members[2]["candidate_id"],
        current_config_fingerprint=members[2]["config_fingerprint"],
        visited_candidate_ids=[m["candidate_id"] for m in members],
    )
    assert result["iterator_effect"] == "exhausted"
    assert "next_candidate" not in result
    assert result["production_authorized"] is False
    # Same inputs → same exhaustion fingerprint (deterministic terminate).
    again = _iterate(
        current_candidate_id=members[2]["candidate_id"],
        current_config_fingerprint=members[2]["config_fingerprint"],
        visited_candidate_ids=[m["candidate_id"] for m in members],
    )
    assert again == result
    assert again["result_fingerprint"] == result["result_fingerprint"]


def test_same_inputs_same_result_fingerprint() -> None:
    members = _members()
    kwargs = dict(
        current_candidate_id=members[0]["candidate_id"],
        current_config_fingerprint=members[0]["config_fingerprint"],
        visited_candidate_ids=[members[0]["candidate_id"]],
    )
    assert _iterate(**kwargs) == _iterate(**kwargs)


def test_wrong_search_space_fingerprint_rejected() -> None:
    with pytest.raises(AnalysisCandidateIteratorError, match="search_space_fingerprint"):
        _iterate(search_space_fingerprint_override="f" * 64)


def test_pin_accepts_correct_identity_rejects_wrong_id_version_fingerprint() -> None:
    provider = pin_aq1_tempo_search_space(
        search_space_id=SEARCH_SPACE_ID,
        search_space_version=SEARCH_SPACE_VERSION,
        search_space_fingerprint=_provider().search_space_fingerprint(),
    )
    assert provider.search_space_id == SEARCH_SPACE_ID

    with pytest.raises(AnalysisCandidateIteratorError, match="search_space_id"):
        pin_aq1_tempo_search_space(search_space_id="aq1.tempo.wrong-id")

    with pytest.raises(AnalysisCandidateIteratorError, match="search_space_version"):
        pin_aq1_tempo_search_space(search_space_version="9.9.9")

    with pytest.raises(AnalysisCandidateIteratorError, match="search_space_fingerprint"):
        pin_aq1_tempo_search_space(search_space_fingerprint="0" * 64)


def test_unknown_current_candidate_rejected() -> None:
    members = _members()
    with pytest.raises(
        AnalysisCandidateIteratorError, match="current candidate|not a member"
    ):
        _iterate(
            current_candidate_id="aq1.tempo.unknown_candidate",
            current_config_fingerprint=members[0]["config_fingerprint"],
            visited_candidate_ids=["aq1.tempo.unknown_candidate"],
        )


def test_wrong_current_config_fingerprint_rejected() -> None:
    members = _members()
    with pytest.raises(AnalysisCandidateIteratorError, match="config_fingerprint"):
        _iterate(
            current_candidate_id=members[0]["candidate_id"],
            current_config_fingerprint="0" * 64,
            visited_candidate_ids=[members[0]["candidate_id"]],
        )


def test_selected_candidate_is_search_space_member_with_authority_fp() -> None:
    members = _members()
    result = _iterate(
        current_candidate_id=members[0]["candidate_id"],
        current_config_fingerprint=members[0]["config_fingerprint"],
        visited_candidate_ids=[members[0]["candidate_id"]],
    )
    next_id = result["next_candidate"]["candidate_id"]
    assert next_id in {m["candidate_id"] for m in members}
    assert result["next_candidate"]["config_fingerprint"] == (
        tempo_candidate_config_fingerprint(next_id)
    )


def test_test_holdout_validation_external_check_cannot_advance() -> None:
    for role in ("test", "holdout", "validation", "external_check"):
        with pytest.raises(
            AnalysisCandidateIteratorError, match="partition|tunable|firewall"
        ):
            _iterate(partition_role=role, next_action="continue_calibration")


def test_terminal_next_actions_emit_no_next_candidate() -> None:
    cases = [
        ("freeze_candidate", "freeze"),
        ("keep_baseline_and_stop", "stop"),
        ("defer_for_evidence", "hold"),
        ("require_human_governance", "stop"),
        ("stop_controlled_failure", "controlled_failure"),
    ]
    for next_action, effect in cases:
        result = _iterate(next_action=next_action)
        assert result["iterator_effect"] == effect
        assert "next_candidate" not in result
        assert result["next_action"] == next_action
        assert result["production_authorized"] is False


def test_development_continue_calibration_advances() -> None:
    members = _members()
    result = _iterate(
        partition_role="development",
        current_candidate_id=members[0]["candidate_id"],
        current_config_fingerprint=members[0]["config_fingerprint"],
        visited_candidate_ids=[members[0]["candidate_id"]],
    )
    assert result["iterator_effect"] == "advance"
    assert result["next_candidate"] == members[1]


def test_production_authorized_false_on_advance_and_exhaustion() -> None:
    members = _members()
    advance = _iterate(
        visited_candidate_ids=[members[0]["candidate_id"]],
        current_candidate_id=members[0]["candidate_id"],
        current_config_fingerprint=members[0]["config_fingerprint"],
    )
    exhausted = _iterate(
        visited_candidate_ids=[m["candidate_id"] for m in members],
        current_candidate_id=members[2]["candidate_id"],
        current_config_fingerprint=members[2]["config_fingerprint"],
    )
    assert advance["production_authorized"] is False
    assert exhausted["production_authorized"] is False


def test_no_private_paths_in_iterator_result() -> None:
    result = _iterate()
    blob = repr(result)
    assert "/Users/" not in blob
    assert "/home/" not in blob
    assert "C:\\" not in blob
    assert "C:/" not in blob
    poisoned = dict(result)
    poisoned["leak"] = "/home/private/secret.wav"
    with pytest.raises(
        (AnalysisCandidateIteratorError, AnalysisEvalArtifactError),
        match="absolute/private path|path is forbidden|portable",
    ):
        validate_result(poisoned)


def test_nan_inf_fail_closed_in_portable_result() -> None:
    result = _iterate()
    for bad in (float("nan"), float("inf"), float("-inf")):
        poisoned = dict(result)
        poisoned["bad_metric"] = bad
        with pytest.raises(
            (AnalysisCandidateIteratorError, AnalysisEvalArtifactError),
            match="non-finite|NaN|Inf|portable|finite",
        ):
            validate_result(poisoned)
        assert not math.isfinite(bad)


def test_no_arvp_import_in_aq1_search_space_modules() -> None:
    for path in (AQ1_PROVIDER_PATH, AQ1_INIT_PATH):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("arvp")
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("arvp")


def test_provider_does_not_redefine_or_resort_tempo_candidates() -> None:
    """Guard: provider must project TEMPO_CANDIDATES order, not invent IDs."""
    source = AQ1_PROVIDER_PATH.read_text(encoding="utf-8")
    assert "TEMPO_CANDIDATES" in source or "list_tempo_candidates" in source
    assert "tempo_candidate_config_fingerprint" in source
    # Must not hardcode a reordered candidate id list as authority.
    assert "sorted(" not in source


def test_mismatched_candidate_config_pair_fail_closed_via_static_forgery() -> None:
    """A forged pair that is not the AQ1 authority pair must not advance."""
    real = _members()
    forged = [
        {
            "candidate_id": real[0]["candidate_id"],
            # Wrong fingerprint for a real candidate id (#1058/#1061 hardening).
            "config_fingerprint": "ab" * 32,
        },
        real[1],
        real[2],
    ]
    forged_provider = StaticSearchSpaceProvider(
        search_space_id=SEARCH_SPACE_ID,
        search_space_version=SEARCH_SPACE_VERSION,
        ordered_members=forged,
    )
    # Domain provider itself must not emit this forgery.
    assert _provider().ordered_members()[0]["config_fingerprint"] != "ab" * 32
    with pytest.raises(AnalysisCandidateIteratorError, match="config_fingerprint"):
        iterate_candidates(
            domain="aq1.tempo",
            next_action="continue_calibration",
            partition_role="calibration",
            provider=forged_provider,
            current_candidate_id=real[0]["candidate_id"],
            current_config_fingerprint=real[0]["config_fingerprint"],
            visited_candidate_ids=[real[0]["candidate_id"]],
            search_space_fingerprint=forged_provider.search_space_fingerprint(),
        )


def test_1060_decision_next_actions_are_consumable_inputs() -> None:
    """Boundary: #1060/#1043 next_action identities plug into the iterator."""
    from src.analysis_automation_decision import NEXT_ACTIONS

    assert "continue_calibration" in NEXT_ACTIONS
    for action in sorted(NEXT_ACTIONS):
        if action == "continue_calibration":
            result = _iterate(next_action=action)
            assert result["iterator_effect"] in {"advance", "exhausted"}
        else:
            result = _iterate(next_action=action)
            assert "next_candidate" not in result
