from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CUE_PLAN = REPO_ROOT / "docs" / "WORKBENCH_CUE_METADATA_PLAN.md"
LOOP_EDIT_PLAN = REPO_ROOT / "docs" / "WORKBENCH_LOOP_EDIT_PLAN.md"
ATTACK_EDIT_PLAN = REPO_ROOT / "docs" / "WORKBENCH_ATTACK_EDIT_PLAN.md"


def test_workbench_cue_metadata_plan_documents_safety_and_fields():
    assert CUE_PLAN.is_file(), "cue metadata plan must exist"
    text = CUE_PLAN.read_text(encoding="utf-8")
    assert "cue_start_ms" in text
    assert "loop_start_ms" in text
    assert "never modified" in text.lower() or "never modifies" in text.lower()
    assert "workbench_library" in text


def test_workbench_loop_edit_plan_documents_bindings_and_recommendation():
    assert LOOP_EDIT_PLAN.is_file(), "loop edit plan must exist"
    text = LOOP_EDIT_PLAN.read_text(encoding="utf-8")
    assert "Right-click" in text or "right-click" in text
    assert "Shift" in text
    assert "loop_start_ms" in text
    assert "never" in text.lower() and "modif" in text.lower()
    assert "Loop-edit mode" in text or "loop-edit mode" in text.lower()


def test_workbench_gui_smoke_doc_exists():
    smoke_doc = REPO_ROOT / "docs" / "WORKBENCH_GUI_SMOKE.md"
    assert smoke_doc.is_file(), "GUI smoke status doc must exist"
    text = smoke_doc.read_text(encoding="utf-8")
    assert "workbench" in text.lower()
    assert "never modif" in text.lower() or "unchanged" in text.lower()
    assert "#117" in text or "117" in text


def test_workbench_catalog_unification_plan_documents_two_databases():
    plan = REPO_ROOT / "docs" / "WORKBENCH_CATALOG_UNIFICATION_PLAN.md"
    assert plan.is_file(), "catalog unification plan must exist"
    text = plan.read_text(encoding="utf-8")
    assert "workbench_library" in text
    assert "catalog" in text.lower()
    assert "never modif" in text.lower() or "unchanged" in text.lower() or "not happen" in text.lower()
    assert "#117" in text or "117" in text


def test_workbench_catalog_readonly_bridge_plan_documents_read_only_safety():
    plan = REPO_ROOT / "docs" / "WORKBENCH_CATALOG_READONLY_BRIDGE_PLAN.md"
    assert plan.is_file(), "catalog readonly bridge plan must exist"
    text = plan.read_text(encoding="utf-8")
    assert "SAMPLE_BRAIN_DB_PATH" in text
    assert "read-only" in text.lower() or "readonly" in text.lower()
    assert "never modif" in text.lower() or "no writes" in text.lower()
    assert "features" in text
    assert "cue" in text.lower()
    assert "#117" in text or "117" in text


def test_workbench_loop_playback_plan_documents_repeat_scope():
    plan = REPO_ROOT / "docs" / "WORKBENCH_LOOP_PLAYBACK_PLAN.md"
    assert plan.is_file(), "loop playback plan must exist"
    text = plan.read_text(encoding="utf-8")
    assert "loop_start_ms" in text or "loop region" in text.lower()
    assert "never modif" in text.lower() or "unchanged" in text.lower()
    assert "once" in text.lower() or "repeat" in text.lower()
    assert "#117" in text or "117" in text


def test_workbench_attack_edit_plan_documents_bindings_and_recommendation():
    assert ATTACK_EDIT_PLAN.is_file(), "attack edit plan must exist"
    text = ATTACK_EDIT_PLAN.read_text(encoding="utf-8")
    assert "attack_ms" in text
    assert "cue_start_ms" in text
    assert "never" in text.lower() and "modif" in text.lower()
    assert "Attack-edit mode" in text or "attack-edit mode" in text.lower()
