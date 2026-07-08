from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CUE_PLAN = REPO_ROOT / "docs" / "WORKBENCH_CUE_METADATA_PLAN.md"


def test_workbench_cue_metadata_plan_documents_safety_and_fields():
    assert CUE_PLAN.is_file(), "cue metadata plan must exist"
    text = CUE_PLAN.read_text(encoding="utf-8")
    assert "cue_start_ms" in text
    assert "loop_start_ms" in text
    assert "never modified" in text.lower() or "never modifies" in text.lower()
    assert "workbench_library" in text
