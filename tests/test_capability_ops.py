from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import capability_lib as caplib  # noqa: E402


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_registry_schema_unique_ids_and_types() -> None:
    registry = caplib.load_registry(ROOT)
    problems = caplib.validate_registry_schema(registry, ROOT)
    assert problems == []
    ids = [c["id"] for c in registry["capabilities"]]
    assert len(ids) == len(set(ids))
    assert {c["type"] for c in registry["capabilities"]} <= caplib.VALID_TYPES


def test_local_canonical_sources_exist_external_do_not_require_files() -> None:
    registry = caplib.load_registry(ROOT)
    for cap in registry["capabilities"]:
        if cap["source_kind"] == "local" and cap["type"] != "workflow":
            assert (ROOT / cap["canonical_source"]).is_file(), cap["id"]
        if cap["source_kind"] == "external":
            assert str(cap["canonical_source"]).startswith("external:") or cap[
                "canonical_source"
            ] in {"EXTERNAL", "NOT_APPLICABLE"}
            assert cap.get("fallback")
            # Must not fail merely because a local package path is absent.
            fake = ROOT / "does-not-exist" / "jMerta" / "missing.md"
            assert not fake.is_file()


def test_agent_authority_no_phantoms() -> None:
    registry = caplib.load_registry(ROOT)
    assert caplib.validate_agent_authority(registry, ROOT) == []
    ci = next(c for c in registry["capabilities"] if c["id"] == "sample-brain-ci-debugger")
    assert ci["type"] == "agent"


def test_generated_block_matches_registry_render() -> None:
    registry = caplib.load_registry(ROOT)
    assert caplib.validate_generated_views(registry, ROOT) == []
    expected = caplib.render_generated_routing_block(registry)
    for rel in (".cursor/rules/skill-routing.mdc", "SB.VERFUEGBARE.SKILLS.md"):
        block = caplib.extract_generated_block((ROOT / rel).read_text(encoding="utf-8"))
        assert block == expected


def test_generator_is_deterministic(tmp_path: Path) -> None:
    # Copy minimal tree pieces needed for apply_generated_views
    for rel in (
        "docs/operations/CAPABILITY_REGISTRY.json",
        ".cursor/rules/skill-routing.mdc",
        "SB.VERFUEGBARE.SKILLS.md",
    ):
        src = ROOT / rel
        dest = tmp_path / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    first = caplib.apply_generated_views(tmp_path)
    second = caplib.apply_generated_views(tmp_path)
    assert first == second
    block = caplib.extract_generated_block(first["SB.VERFUEGBARE.SKILLS.md"])
    assert block is not None
    assert "as_of" not in block
    assert "BEGIN GENERATED CAPABILITY ROUTING" in block


def test_skill_mirror_header_only_vs_body_drift(tmp_path: Path) -> None:
    docs = tmp_path / "docs" / "skills" / "demo"
    cursor = tmp_path / ".cursor" / "skills" / "demo"
    docs.mkdir(parents=True)
    cursor.mkdir(parents=True)
    body = (
        "---\nname: demo\ndescription: x\n---\n\n# Demo\n\nContract line.\n"
    )
    (docs / "SKILL.md").write_text(
        "<!--\nSurface: docs\n-->\n" + body,
        encoding="utf-8",
    )
    (cursor / "SKILL.md").write_text(
        body.replace("# Demo", "<!--\nSurface: cursor\n-->\n# Demo"),
        encoding="utf-8",
    )
    assert caplib.validate_skill_mirrors(tmp_path) == []

    (cursor / "SKILL.md").write_text(
        body.replace("Contract line.", "Contract line CHANGED."),
        encoding="utf-8",
    )
    problems = caplib.validate_skill_mirrors(tmp_path)
    assert any("skill mirror contract drift: demo" in p for p in problems)


def test_private_mcp_not_worker_required() -> None:
    registry = caplib.load_registry(ROOT)
    assert caplib.validate_private_mcp_boundary(registry) == []
    op = next(c for c in registry["capabilities"] if c["id"] == "private-chatgpt-mcp")
    assert op["type"] == "operator-only"
    assert "never a worker blocker" in op["fallback"].lower() or "never" in op["fallback"].lower()


def test_parked_and_visual_accept_present() -> None:
    assert caplib.validate_parked_and_hygiene_surfaces(ROOT) == []
    registry = caplib.load_registry(ROOT)
    block = caplib.render_generated_routing_block(registry)
    assert "VISUAL_ACCEPT_PENDING" in block
    assert "VISUAL_ACCEPT_PASS" in block
    assert "VISUAL_ACCEPT_FAIL" in block
    # Screen 2 (#675/#678) reactivated by Owner-GO; Screen 3 remains parked.
    assert "Screen 3 #679" in block
    assert "#675/#678" not in block
    assert "explicit_owner_go" in block


def test_issue_backlog_not_live_hygiene_authority() -> None:
    boot = (ROOT / "SB.BOOTLOADER.md").read_text(encoding="utf-8")
    for line in boot.splitlines():
        if "Repository Hygiene" in line:
            assert "ISSUE_BACKLOG" not in line
    registry = caplib.load_registry(ROOT)
    hygiene = registry["routing"]["special_routes"]["repository_hygiene"]
    assert "ISSUE_BACKLOG" in hygiene["not_authority"]


def test_snapshot_unknown_when_github_forced_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    snap = _load_module("capability_snapshot", TOOLS / "capability_snapshot.py")
    monkeypatch.setattr(snap, "_gh_available", lambda: False)
    payload = snap.build_snapshot()
    assert payload["source_state"]["github"] == "unavailable"
    assert payload["kpis"]["repair_rounds_per_pr"]["status"] == "unknown"
    assert payload["kpis"]["repair_rounds_per_pr"]["value"] is None
    assert payload["kpis"]["canon_contradiction_count"]["status"] == "measured"
    assert isinstance(payload["kpis"]["canon_contradiction_count"]["value"], int)


def test_tracked_ops_artifacts_have_no_private_paths() -> None:
    for rel in (
        "docs/operations/CAPABILITY_REGISTRY.json",
        "docs/operations/KPI_CONTRACT.json",
        "docs/operations/README.md",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert ":\\Users\\" not in text
        assert "/home/" not in text


def test_capability_checker_cli_pass() -> None:
    checker = _load_module("check_capability_drift", TOOLS / "check_capability_drift.py")
    assert checker.main() == 0


def test_external_capability_missing_local_file_does_not_fail_schema() -> None:
    registry = json.loads(
        (ROOT / "docs/operations/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8")
    )
    # Ensure jMerta entry validates even though no local skill file exists.
    jm = next(c for c in registry["capabilities"] if c["id"] == "jMerta/ci-fix")
    assert not (ROOT / "docs/skills/jMerta/ci-fix/SKILL.md").exists()
    problems = caplib._validate_canonical_source(jm, ROOT)
    assert problems == []
