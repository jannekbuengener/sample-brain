"""Pure Harmonic Match eligibility / claim-key adapter (#669).

These helpers must exist and remain unwired from rate_harmony / controller.
"""

from __future__ import annotations

from dataclasses import replace

from src.workbench_controller import WorkbenchKeyAnalysisClaim, WorkbenchRow
from src.workbench_harmony import (
    HarmonyRelation,
    harmonic_match_key_for_row,
    is_harmonic_match_claim_eligible,
    rate_harmony,
)


def _claim(
    *,
    key: str = "Cmaj",
    mode: str | None = "maj",
    contract_version: int | None = 2,
    valid: bool = True,
    matching_eligible: bool = False,
    root_evidence_kind: str | None = "joint_24_profile_pearson",
    mode_evidence_kind: str | None = "third_contrast",
) -> WorkbenchKeyAnalysisClaim:
    return WorkbenchKeyAnalysisClaim(
        key=key,
        mode=mode,
        contract_version=contract_version,
        valid=valid,
        matching_eligible=matching_eligible,
        root_evidence_kind=root_evidence_kind,
        mode_evidence_kind=mode_evidence_kind,
    )


def _row(
    name: str,
    *,
    key: str | None = None,
    key_conf: float | None = None,
    claim: WorkbenchKeyAnalysisClaim | None = None,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=f"/synthetic/{name}.wav",
        bpm=128.0,
        key=key,
        key_conf=key_conf,
        loudness=-20.0,
        brightness=2000.0,
        sample_class="loop",
        pred_type="kick",
        status="ok",
        key_analysis_claim=claim,
    )


class TestIsHarmonicMatchClaimEligible:
    def test_v2_modeful_maj_valid_is_eligible(self):
        assert is_harmonic_match_claim_eligible(_claim(key="Cmaj", mode="maj")) is True

    def test_v2_modeful_min_valid_is_eligible(self):
        assert is_harmonic_match_claim_eligible(_claim(key="Amin", mode="min")) is True

    def test_v2_root_only_not_eligible(self):
        claim = _claim(key="G", mode=None)
        assert is_harmonic_match_claim_eligible(claim) is False

    def test_v2_mode_none_not_eligible(self):
        claim = _claim(key="Cmaj", mode=None)
        assert is_harmonic_match_claim_eligible(claim) is False

    def test_invalid_claim_not_eligible(self):
        claim = _claim(valid=False)
        assert is_harmonic_match_claim_eligible(claim) is False

    def test_unknown_contract_not_eligible(self):
        claim = _claim(contract_version=99)
        assert is_harmonic_match_claim_eligible(claim) is False

    def test_malformed_key_not_eligible(self):
        claim = _claim(key="!!!", mode="maj")
        assert is_harmonic_match_claim_eligible(claim) is False

    def test_claim_mode_key_mismatch_not_eligible(self):
        claim = _claim(key="Cmaj", mode="min")
        assert is_harmonic_match_claim_eligible(claim) is False

    def test_missing_claim_not_eligible(self):
        assert is_harmonic_match_claim_eligible(None) is False

    def test_v1_claim_not_auto_eligible(self):
        claim = _claim(contract_version=None, matching_eligible=True)
        assert is_harmonic_match_claim_eligible(claim) is False

    def test_matching_eligible_false_does_not_block_v2(self):
        claim = _claim(matching_eligible=False)
        assert claim.matching_eligible is False
        assert is_harmonic_match_claim_eligible(claim) is True

    def test_no_key_conf_required_for_v2(self):
        # Eligibility is claim-only; WorkbenchRow.key_conf is intentionally absent.
        claim = _claim(key="Dmaj", mode="maj")
        row = _row("v2", key=None, key_conf=None, claim=claim)
        assert row.key_conf is None
        assert is_harmonic_match_claim_eligible(row.key_analysis_claim) is True

    def test_evidence_kinds_do_not_affect_eligibility(self):
        claim = _claim(
            root_evidence_kind="ignored_kind",
            mode_evidence_kind="also_ignored",
        )
        assert is_harmonic_match_claim_eligible(claim) is True


class TestHarmonicMatchKeyForRow:
    def test_v2_modeful_adapter_returns_claim_key(self):
        claim = _claim(key="Cmaj", mode="maj")
        row = _row("v2", key=None, key_conf=None, claim=claim)
        assert harmonic_match_key_for_row(row) == "Cmaj"

    def test_v2_root_only_returns_none(self):
        claim = _claim(key="G", mode=None)
        row = _row("v2-root", key=None, key_conf=None, claim=claim)
        assert harmonic_match_key_for_row(row) is None

    def test_missing_claim_v1_modeful_uses_row_key(self):
        row = _row("v1", key="Cmaj", key_conf=0.8, claim=None)
        assert harmonic_match_key_for_row(row) == "Cmaj"

    def test_missing_claim_v1_root_only_uses_row_key(self):
        row = _row("v1-root", key="C", key_conf=0.5, claim=None)
        assert harmonic_match_key_for_row(row) == "C"

    def test_missing_claim_and_key_none_returns_none(self):
        row = _row("empty", key=None, key_conf=None, claim=None)
        assert harmonic_match_key_for_row(row) is None

    def test_non_v2_claim_falls_back_to_product_key(self):
        claim = _claim(contract_version=None, matching_eligible=True, key="Cmaj", mode="maj")
        row = _row("v1-claim", key="Cmaj", key_conf=0.9, claim=claim)
        assert is_harmonic_match_claim_eligible(claim) is False
        assert harmonic_match_key_for_row(row) == "Cmaj"

    def test_v2_withheld_product_key_no_raw_fallback(self):
        claim = _claim(key="Amin", mode="min")
        row = _row("v2", key=None, key_conf=None, claim=claim)
        assert row.key is None
        assert harmonic_match_key_for_row(row) == "Amin"

    def test_shared_helper_usable_for_anchor_and_candidate(self):
        claim = _claim(key="Fmaj", mode="maj")
        anchor = _row("anchor", key=None, claim=claim)
        candidate = _row("cand", key=None, claim=claim)
        assert harmonic_match_key_for_row(anchor) == "Fmaj"
        assert harmonic_match_key_for_row(candidate) == "Fmaj"

    def test_helpers_do_not_mutate_row_or_claim(self):
        claim = _claim(key="Gmaj", mode="maj", matching_eligible=False)
        row = _row("immutable", key=None, key_conf=None, claim=claim)
        before = replace(claim)
        assert is_harmonic_match_claim_eligible(row.key_analysis_claim) is True
        assert harmonic_match_key_for_row(row) == "Gmaj"
        assert row.key is None
        assert row.key_conf is None
        assert row.key_analysis_claim == before
        assert row.key_analysis_claim.matching_eligible is False


class TestEligibilityActivatesHarmony:
    def test_rate_harmony_uses_eligible_v2_claim_when_product_key_none(self):
        claim = _claim(key="Cmaj", mode="maj")
        candidate = _row("v2-cand", key=None, key_conf=None, claim=claim)
        reference = _row("ref", key="Cmaj", key_conf=0.8, claim=None)
        assert harmonic_match_key_for_row(candidate) == "Cmaj"
        suggestion = rate_harmony(reference, candidate)
        assert suggestion.relation is HarmonyRelation.DIRECT
