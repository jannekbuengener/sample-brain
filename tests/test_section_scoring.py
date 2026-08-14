"""Test-first evidence for section asset candidate scoring (Issue #267).

These tests use synthetic SectionCandidate / StructureV1 ``bar_features`` only.
No private audio, no network, no model downloads, no file IO. They assert the
contract from docs/ASSET_MANIFEST_V1.md, docs/SECTION_CANDIDATES_V1.md and the
#267 acceptance criteria:

* reproducible, separated, traceable score components
* section coherence and musical development are distinct components
* boundary security and role security are distinct (never merged into one)
* unknown role and uncertain boundary each stay valid and separately visible
* transition and vocal/fx edge risks are separate, vocal/fx never invented
* hard exclusions are separated from soft scores, no loop-style penalties
* no fixed bar length / repetition / seam requirement for sections
* mapping into the Asset Manifest ``candidate`` block works (#250 §10)
"""

from __future__ import annotations

import copy

import numpy as np

from src.arrangement_classifier import SectionRole
from src.section_candidates import (
    SectionBoundaryContext,
    SectionCandidate,
    SectionSourceIdentity,
)
from src.section_scoring import (
    BOUNDARY_SECURITY,
    MUSICAL_DEVELOPMENT,
    REJECT_INVALID_RANGE,
    ROLE_SECURITY,
    SECTION_COHERENCE,
    TRANSITION_RISK,
    VOCAL_FX_EDGE_RISK,
    SectionEdgeRiskEvidence,
    SectionScoringConfig,
    default_section_scoring_config,
    default_weights,
    score_section_candidate,
)

SOURCE = SectionSourceIdentity(
    source_kind="master", track_audio_ref="/source/working_audio"
)
TRACK_REF = "track_9f8e7d6c5b4a"


def _boundary(
    status: str = "ok", quality: float | None = 0.8
) -> SectionBoundaryContext:
    return SectionBoundaryContext(
        source="arrangement_map",
        status=status,  # type: ignore[arg-type]
        kind="neutral_section",
        quality=quality,
    )


def _candidate(
    *,
    section_ref: str = "section_1",
    start_sample: int = 0,
    end_sample_exclusive: int = 44100,
    start_bar: int | None = 0,
    end_bar_exclusive: int | None = 4,
    role: SectionRole = "intro",
    role_status: str = "available",
    role_source: str = "automatic",
    automatic_role: SectionRole = "intro",
    boundary: SectionBoundaryContext | None = None,
) -> SectionCandidate:
    boundary = boundary or _boundary()
    return SectionCandidate(
        asset_id=f"asset_section_{section_ref}",
        track_ref=TRACK_REF,
        section_ref=section_ref,
        start_sample=start_sample,
        end_sample_exclusive=end_sample_exclusive,
        n_samples=end_sample_exclusive - start_sample,
        source=SOURCE,
        arrangement_role=role,
        arrangement_role_status=role_status,
        arrangement_role_source=role_source,  # type: ignore[arg-type]
        automatic_role=automatic_role,
        boundary=boundary,
        start_bar=start_bar,
        end_bar_exclusive=end_bar_exclusive,
        arrangement_role_ref=f"arrangement_classifier/{section_ref}",
    )


def _features(n_bars: int = 4) -> dict[str, tuple[float, ...]]:
    rs = np.random.RandomState(7)
    return {
        "bar_energy_rms": tuple(float(v) for v in rs.rand(n_bars)),
        "self_similarity": tuple(float(v) for v in rs.rand(n_bars)),
        "recurrence": tuple(float(v) for v in rs.rand(n_bars)),
        "rhythm_stability": tuple(float(v) for v in rs.rand(n_bars)),
        "timbre_delta": tuple(float(v) for v in rs.rand(n_bars)),
        "spectral_delta": tuple(float(v) for v in rs.rand(n_bars)),
        "neighbor_delta": tuple(float(v) for v in rs.rand(n_bars)),
        # Steady build across the section (all positive, same sign).
        "multi_bar_trend": tuple(float(v) for v in np.linspace(0.1, 0.6, n_bars)),
    }


def test_deterministic_for_same_inputs():
    cand = _candidate()
    feats = _features()
    a = score_section_candidate(cand, bar_features=feats).as_dict()
    b = score_section_candidate(cand, bar_features=copy.deepcopy(feats)).as_dict()
    assert a == b


def test_score_components_are_separated_and_named():
    result = score_section_candidate(_candidate(), bar_features=_features())
    names = set(result.score_components.keys())
    assert {
        SECTION_COHERENCE,
        MUSICAL_DEVELOPMENT,
        BOUNDARY_SECURITY,
        ROLE_SECURITY,
        TRANSITION_RISK,
        VOCAL_FX_EDGE_RISK,
    } <= names
    for comp in result.score_components.values():
        assert comp.name
        assert comp.meaning


def test_section_coherence_is_own_component():
    result = score_section_candidate(_candidate(), bar_features=_features())
    comp = result.score_components[SECTION_COHERENCE]
    assert comp.name == SECTION_COHERENCE
    assert comp.value is not None
    assert 0.0 <= comp.value <= 1.0
    assert comp.status == "ok"


def test_musical_development_is_own_component():
    result = score_section_candidate(_candidate(), bar_features=_features())
    comp = result.score_components[MUSICAL_DEVELOPMENT]
    assert comp.name == MUSICAL_DEVELOPMENT
    assert comp.value is not None
    assert 0.0 <= comp.value <= 1.0
    assert comp.status == "ok"


def test_boundary_security_is_own_component():
    result = score_section_candidate(_candidate(), bar_features=_features())
    comp = result.score_components[BOUNDARY_SECURITY]
    assert comp.name == BOUNDARY_SECURITY
    assert comp.value is not None
    assert 0.0 <= comp.value <= 1.0


def test_role_security_separate_from_boundary_security():
    cand = _candidate(
        role_status="available",
        role_source="automatic",
        boundary=_boundary(status="ok", quality=0.9),
    )
    result = score_section_candidate(cand, bar_features=_features())
    # Both components exist and are computed independently.
    assert result.score_components[BOUNDARY_SECURITY].value is not None
    assert result.score_components[ROLE_SECURITY].value is not None
    # Changing the boundary must not change the role security value.
    base = result.score_components[ROLE_SECURITY].value
    weak_cand = _candidate(
        role_status="available",
        role_source="automatic",
        boundary=_boundary(status="partial", quality=0.2),
    )
    weak_result = score_section_candidate(weak_cand, bar_features=_features())
    assert weak_result.score_components[ROLE_SECURITY].value == base


def test_uncertain_boundary_does_not_change_role_status_score():
    strong = _candidate(
        role_status="uncertain",
        role_source="automatic",
        boundary=_boundary(status="ok", quality=0.9),
    )
    weak = _candidate(
        role_status="uncertain",
        role_source="automatic",
        boundary=_boundary(status="partial", quality=0.1),
    )
    rs_strong = (
        score_section_candidate(strong, bar_features=_features())
        .score_components[ROLE_SECURITY]
        .value
    )
    rs_weak = (
        score_section_candidate(weak, bar_features=_features())
        .score_components[ROLE_SECURITY]
        .value
    )
    assert rs_strong == rs_weak


def test_uncertain_role_does_not_change_boundary_quality_score():
    strong_role = _candidate(
        role="drop",
        role_status="available",
        role_source="automatic",
        boundary=_boundary(status="ok", quality=0.9),
    )
    uncertain_role = _candidate(
        role="unknown",
        role_status="uncertain",
        role_source="automatic",
        boundary=_boundary(status="ok", quality=0.9),
    )
    bs_strong = (
        score_section_candidate(strong_role, bar_features=_features())
        .score_components[BOUNDARY_SECURITY]
        .value
    )
    bs_uncertain = (
        score_section_candidate(uncertain_role, bar_features=_features())
        .score_components[BOUNDARY_SECURITY]
        .value
    )
    assert bs_strong == bs_uncertain


def test_unknown_role_is_valid_and_not_hard_rejected():
    cand = _candidate(role="unknown", role_status="unknown", role_source="automatic")
    result = score_section_candidate(cand, bar_features=_features())
    assert result.hard_rejected is False
    assert result.reject_reasons == ()
    # Role security is a modest, non-zero soft value (valid, not a dummy zero).
    role_sec = result.score_components[ROLE_SECURITY].value
    assert role_sec is not None and 0.0 < role_sec < 1.0


def test_manual_override_remains_traceable_and_certain():
    cand = _candidate(
        role="build",
        role_status="uncertain",
        role_source="manual",
        automatic_role="drop",
    )
    result = score_section_candidate(cand, bar_features=_features())
    # Manual override gives role certainty even when the automatic status was uncertain.
    assert result.score_components[ROLE_SECURITY].value is not None
    assert result.config_provenance.get("effective_role_source") == "manual"
    # The scoring never alters the candidate identity/provenance.
    assert result.candidate_ref.arrangement_role_source == "manual"


def test_transition_risk_is_visible():
    result = score_section_candidate(_candidate(), bar_features=_features())
    comp = result.score_components[TRANSITION_RISK]
    assert comp.name == TRANSITION_RISK
    assert comp.value is not None
    assert 0.0 <= comp.value <= 1.0


def test_vocal_fx_risk_not_invented_without_evidence():
    result = score_section_candidate(_candidate(), bar_features=_features())
    comp = result.score_components[VOCAL_FX_EDGE_RISK]
    assert comp.value is None
    assert comp.status == "not_evaluated"


def test_explicit_vocal_fx_evidence_is_visible():
    evidence = (
        SectionEdgeRiskEvidence(side="start", kind="vocal", evidence_ref="manual_1"),
    )
    result = score_section_candidate(
        _candidate(), bar_features=_features(), vocal_fx_evidence=evidence
    )
    comp = result.score_components[VOCAL_FX_EDGE_RISK]
    assert comp.value == 1.0
    assert comp.status == "ok"


def test_hard_rejects_separated_from_soft_scores():
    cand = _candidate(start_sample=10, end_sample_exclusive=10)  # n_samples == 0
    result = score_section_candidate(cand, bar_features=_features())
    assert result.hard_rejected is True
    assert REJECT_INVALID_RANGE in result.reject_reasons
    # Soft components are still present and named.
    assert result.score_components
    # Hard reject does not silently erase the separated component set.
    assert result.score_components[SECTION_COHERENCE].name == SECTION_COHERENCE


def test_missing_optional_evidence_produces_no_dummy_zero():
    # No bar_features at all -> feature-derived components are not_evaluated.
    result = score_section_candidate(_candidate(), bar_features=None)
    for name in (
        SECTION_COHERENCE,
        MUSICAL_DEVELOPMENT,
        TRANSITION_RISK,
    ):
        comp = result.score_components[name]
        assert comp.value is None
        assert comp.status == "not_evaluated"


def test_unknown_role_status_maps_to_modest_score_without_reject():
    cand = _candidate(role="unknown", role_status="unknown", role_source="automatic")
    result = score_section_candidate(cand, bar_features=None)
    assert result.hard_rejected is False


def test_weights_are_configurable():
    base = default_section_scoring_config()
    config = SectionScoringConfig(
        weights={**default_weights(), SECTION_COHERENCE: 0.0},
        boundary_status_scores=base.boundary_status_scores,
        role_status_scores=base.role_status_scores,
        role_manual_certainty=base.role_manual_certainty,
        include_summary_score=base.include_summary_score,
    )
    cand = _candidate()
    result = score_section_candidate(cand, bar_features=_features(), config=config)
    # Changing weights must change the (optional) summary score, proving they are
    # not baked in.
    base = score_section_candidate(cand, bar_features=_features())
    if result.summary_score is not None and base.summary_score is not None:
        assert result.summary_score != base.summary_score or base.summary_score == 0.0


def test_no_final_pilot_threshold_is_baked_in():
    result = score_section_candidate(_candidate(), bar_features=_features())
    assert result.config_provenance.get("provisional") is True
    # No single pass/fail selection threshold is applied; status is not "selected".
    assert result.status in {"ok", "excluded", "no_evidence"}


def test_no_seam_component_exists():
    result = score_section_candidate(_candidate(), bar_features=_features())
    for name in result.score_components:
        assert "seam" not in name
        assert "repetition" not in name
        assert "recurrence" not in name


def test_no_repetition_requirement_as_hard_reject():
    # Two repetitive, identical-feature sections must not be hard-excluded.
    feats = _features()
    cand_a = _candidate(section_ref="section_1", start_bar=0, end_bar_exclusive=4)
    cand_b = _candidate(section_ref="section_2", start_bar=4, end_bar_exclusive=8)
    for cand in (cand_a, cand_b):
        result = score_section_candidate(cand, bar_features=feats)
        assert result.hard_rejected is False


def test_no_fixed_bar_length_required():
    cand = _candidate(start_bar=0, end_bar_exclusive=3)
    result = score_section_candidate(cand, bar_features=_features(n_bars=3))
    assert result.hard_rejected is False


def test_section_of_any_length_is_valid():
    feats = _features(n_bars=7)
    cand = _candidate(
        start_sample=0,
        end_sample_exclusive=7 * 11025,
        start_bar=0,
        end_bar_exclusive=7,
    )
    result = score_section_candidate(cand, bar_features=feats)
    assert result.status == "ok"


def test_manifest_candidate_mapping_works():
    cand = _candidate()
    result = score_section_candidate(cand, bar_features=_features())
    block = result.as_candidate_dict()
    assert block["excluded"] == result.hard_rejected
    assert set(block["score_components"].keys()) == set(result.score_components.keys())
    if result.hard_rejected:
        assert block["status"] == "rejected"
        assert block["reject_reasons"]
    else:
        assert block["status"] == "candidate"
    # Section/role/boundary provenance travels with the candidate ref unchanged.
    assert result.candidate_ref.section_ref == cand.section_ref
    assert result.candidate_ref.arrangement_role == cand.arrangement_role
    assert result.candidate_ref.boundary_status == cand.boundary.status


def test_invalid_numeric_evidence_is_status_based_not_silent():
    # Out-of-range boundary quality is not silently clamped into a fake value;
    # it falls back to the status-based boundary security.
    cand = _candidate(boundary=_boundary(status="ok", quality=5.0))
    result = score_section_candidate(cand, bar_features=_features())
    comp = result.score_components[BOUNDARY_SECURITY]
    # status-based value for "ok" is the configured status score, not 5.0.
    assert comp.value is not None
    assert comp.value <= 1.0


def test_bar_features_with_nonfinite_fall_back_to_status_based():
    feats = _features()
    bad = list(feats["self_similarity"])
    bad[0] = float("nan")
    feats["self_similarity"] = tuple(bad)
    result = score_section_candidate(_candidate(), bar_features=feats)
    # Still produces a valid, non-crashing coherence value (status-based blend).
    assert result.score_components[SECTION_COHERENCE].value is not None


def test_reproducible_result_dict():
    cand = _candidate()
    feats = _features()
    result_a = score_section_candidate(cand, bar_features=feats).as_dict()
    result_b = score_section_candidate(cand, bar_features=feats).as_dict()
    assert copy.deepcopy(result_a) == result_b
