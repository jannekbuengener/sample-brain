from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CUE_PLAN = REPO_ROOT / "docs" / "WORKBENCH_CUE_METADATA_PLAN.md"
LOOP_EDIT_PLAN = REPO_ROOT / "docs" / "WORKBENCH_LOOP_EDIT_PLAN.md"


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
