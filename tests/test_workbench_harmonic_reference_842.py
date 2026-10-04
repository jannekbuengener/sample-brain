"""#842 Harmonic Match reference eligibility / display-vs-domain contract.

Frozen after root-cause diagnosis on baseline 43780f9:
Owner symptom Browser ``G`` + panel ``auswertbaren Referenz-Key`` is
EXPECTED_INELIGIBLE for root-only product keys without an eligible modeful V2
claim. These tests lock that boundary and protect eligible V1/V2 paths.
No product-code fix in the freeze slice; do not weaken these assertions to
fabricate modeful keys from display text.
"""

from __future__ import annotations

from src.workbench_catalog import CatalogSampleRow
from src.workbench_controller import (
    WorkbenchKeyAnalysisClaim,
    WorkbenchRow,
    _catalog_row_for_cache_import,
)
from src.workbench_harmony import (
    HarmonicMatchLibraryController,
    find_harmony_matches,
    harmonic_match_key_for_row,
    is_harmonic_match_claim_eligible,
)
from src.workbench_library import CachedWorkbenchRow
from src.workbench_qml import Screen1QmlInteractionAdapter, _qml_row
from src.key_signature import parse_key_signature


def _claim(**kwargs) -> WorkbenchKeyAnalysisClaim:
    base = dict(
        key="Gmaj",
        mode="maj",
        contract_version=2,
        valid=True,
        matching_eligible=False,
        root_evidence_kind="joint_24_profile_pearson",
        mode_evidence_kind="third_contrast",
    )
    base.update(kwargs)
    return WorkbenchKeyAnalysisClaim(**base)


def _row(
    name: str,
    *,
    key: str | None = None,
    claim: WorkbenchKeyAnalysisClaim | None = None,
    bpm: float | None = 128.0,
) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=name,
        relative_path=f"{name}.wav",
        path=f"/synthetic/842/{name}.wav",
        bpm=bpm,
        key=key,
        key_conf=0.85 if key else None,
        loudness=-14.0,
        brightness=1800.0,
        sample_class="loop",
        pred_type="Pad",
        status="ok",
        key_analysis_claim=claim,
    )


def test_case_a_v1_modeful_reference_delivers_domain_matches() -> None:
    anchor = _row("a_ref", key="Gmaj")
    candidate = _row("a_cand", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)

    assert _qml_row(anchor).key == "Gmaj"
    assert harmonic_match_key_for_row(anchor) == "Gmaj"
    controller.set_anchor(anchor, [anchor, candidate])

    assert controller.results
    assert "Harmonic Matches" in controller.status
    assert find_harmony_matches is controller._finder


def test_case_b_v2_modeful_claim_drives_matching_while_browser_shows_product_key() -> None:
    anchor = _row("b_ref", key=None, claim=_claim(key="Gmaj", mode="maj"))
    candidate = _row("b_cand", key="Cmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)

    assert is_harmonic_match_claim_eligible(anchor.key_analysis_claim) is True
    assert harmonic_match_key_for_row(anchor) == "Gmaj"
    assert _qml_row(anchor).key == "—"  # display uses product row.key only
    controller.set_anchor(anchor, [anchor, candidate])

    assert controller.results
    assert parse_key_signature(harmonic_match_key_for_row(anchor)).mode == "maj"


def test_case_c_root_only_product_key_is_expected_ineligible() -> None:
    """Owner-screenshot shape: visible G is root-only and correctly rejected."""
    anchor = _row("c_ref", key="G")
    candidate = _row("c_cand", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)

    assert _qml_row(anchor).key == "G"
    assert harmonic_match_key_for_row(anchor) == "G"
    assert parse_key_signature("G").mode is None
    controller.set_anchor(anchor, [anchor, candidate])

    assert controller.results == ()
    assert controller.status == "Harmonic Match benötigt einen auswertbaren Referenz-Key."


def test_case_c_does_not_fabricate_mode_from_display_string() -> None:
    anchor = _row("c_fabricate", key="G")
    display = _qml_row(anchor).key
    effective = harmonic_match_key_for_row(anchor)

    assert display == "G"
    assert effective == "G"
    assert effective not in {"Gmaj", "Gmin"}
    assert parse_key_signature(effective).mode is None


def test_case_d_invalid_and_malformed_claims_fail_closed() -> None:
    invalid = _row("d_invalid", key=None, claim=_claim(valid=False))
    malformed = _row("d_bad", key=None, claim=_claim(key="!!!", mode="maj"))
    candidate = _row("d_cand", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)

    for anchor in (invalid, malformed):
        assert is_harmonic_match_claim_eligible(anchor.key_analysis_claim) is False
        assert harmonic_match_key_for_row(anchor) is None
        controller.set_anchor(anchor, [anchor, candidate])
        assert controller.results == ()
        assert "auswertbaren Referenz-Key" in controller.status


def test_case_e_changing_reference_clears_stale_results() -> None:
    a = _row("e_a", key="Gmaj")
    b = _row("e_b", key="G")
    candidate = _row("e_cand", key="Gmaj")
    controller = HarmonicMatchLibraryController(finder=find_harmony_matches)

    controller.set_anchor(a, [a, candidate])
    assert controller.results
    controller.set_anchor(b, [b, candidate])

    assert controller.results == ()
    assert controller.anchor is b
    assert "auswertbaren Referenz-Key" in controller.status


def test_catalog_v2_modeful_claim_survives_catalog_projection() -> None:
    catalog = CatalogSampleRow(
        path="/synthetic/842/catalog.wav",
        relative_path="catalog.wav",
        display_name="catalog",
        size_bytes=8,
        duration=1.0,
        bpm=128.0,
        key=None,
        key_conf=None,
        loudness=-10.0,
        brightness=1200.0,
        sample_class="loop",
        pred_type="Pad",
        status="ok",
        key_claim="Gmaj",
        key_mode="maj",
        key_analysis_contract_version=2,
        key_claim_valid=True,
        key_matching_eligible=False,
        key_root_evidence_kind="joint_24_profile_pearson",
        key_mode_evidence_kind="third_contrast",
    )
    row = catalog.to_workbench_row()

    assert row.key is None
    assert row.key_analysis_claim is not None
    assert row.key_analysis_claim.key == "Gmaj"
    assert is_harmonic_match_claim_eligible(row.key_analysis_claim) is True
    assert harmonic_match_key_for_row(row) == "Gmaj"
    assert _qml_row(row).key == "—"


def test_library_cache_root_only_matches_owner_screenshot_shape() -> None:
    cached = CachedWorkbenchRow(
        original_path="/synthetic/842/cached.wav",
        relative_path="cached.wav",
        display_name="cached",
        size_bytes=8,
        mtime_ns=1,
        bpm=128.0,
        key="G",
        key_conf=0.4,
        loudness=-10.0,
        brightness=1200.0,
        sample_class="loop",
        pred_type="Pad",
        status="ok",
    )
    row = cached.to_workbench_row()

    assert row.key_analysis_claim is None
    assert _qml_row(row).key == "G"
    assert harmonic_match_key_for_row(row) == "G"


def test_catalog_import_helper_currently_drops_claim_transport() -> None:
    """Residual projection note: import path does not carry V2 claims today.

    This is not the owner-screenshot defect (root-only product key). Documented
    so a later scoped projection repair can target this boundary without
    inventing mode from display ``G``.
    """
    from pathlib import Path
    import tempfile

    source = CatalogSampleRow(
        path="/synthetic/842/import_src.wav",
        relative_path="import_src.wav",
        display_name="import_src",
        size_bytes=8,
        duration=1.0,
        bpm=128.0,
        key=None,
        key_conf=None,
        loudness=-10.0,
        brightness=1200.0,
        sample_class="loop",
        pred_type="Pad",
        status="ok",
        key_claim="Gmaj",
        key_mode="maj",
        key_analysis_contract_version=2,
        key_claim_valid=True,
        key_matching_eligible=False,
    ).to_workbench_row()
    assert source.key_analysis_claim is not None

    with tempfile.TemporaryDirectory() as tmp:
        imported = _catalog_row_for_cache_import(source, target_folder=Path(tmp))

    assert imported.key_analysis_claim is None
    assert imported.key is None
    assert harmonic_match_key_for_row(imported) is None


def test_fingerprint_tracks_effective_key_not_display_only() -> None:
    modeful = _row("fp_modeful", key=None, claim=_claim(key="Gmaj", mode="maj"))
    root_only = _row("fp_root", key="G")
    fp_modeful = Screen1QmlInteractionAdapter._harmonic_match_row_fingerprint(modeful)
    fp_root = Screen1QmlInteractionAdapter._harmonic_match_row_fingerprint(root_only)

    assert fp_modeful[1] == "Gmaj"
    assert fp_root[1] == "G"
    assert fp_modeful != fp_root


def test_matching_domain_not_duplicated_in_qml_source() -> None:
    from src.workbench_qml import QML_SOURCE

    assert "find_harmony_matches" not in QML_SOURCE
    assert "rate_harmony" not in QML_SOURCE
    assert "is_harmonic_match_claim_eligible" not in QML_SOURCE


def test_context_menu_harmonic_intent_remains_target_bound_not_qml_panel_alias() -> None:
    """#839/#840 remain; #843 Python open/retarget must not invent a QML alias API."""
    from src.workbench_qml import QML_SOURCE, Screen1QmlInteractionAdapter

    assert "contextHarmonicMatches" in QML_SOURCE
    assert "contextAddToKit" in QML_SOURCE
    assert hasattr(Screen1QmlInteractionAdapter, "request_context_harmonic_matches")
    assert hasattr(Screen1QmlInteractionAdapter, "request_context_add_to_kit")
    # QML must not grow a parallel openHarmonicMatchesPanel alias.
    assert "function openHarmonicMatchesPanel" not in QML_SOURCE
