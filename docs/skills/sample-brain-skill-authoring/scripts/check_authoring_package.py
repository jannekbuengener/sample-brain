#!/usr/bin/env python3
"""Deterministic package-shape checks for Sample Brain skill authoring.

Mechanical invariants only. Does not judge behavioral effectiveness.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

VALID_LIFECYCLES = frozenset({"active", "on-demand", "historical", "parked"})
UNSUPPORTED_MIRROR_HINTS = (
    ".claude/skills",
    ".codex/skills",
    ".opencode/skills",
    ".gemini/skills",
)
WORKFLOW_DUMP_MARKERS = (
    "BASELINE WITHOUT SKILL",
    "OBSERVED REUSABLE FAILURE",
    "CAPABILITY REGISTRY",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _body_from_heading(text: str) -> str:
    idx = text.find("\n# ")
    if idx == -1:
        idx = text.find("# ")
        if idx == -1:
            return text.strip()
        return text[idx:].strip()
    return text[idx + 1 :].strip()


def _frontmatter(text: str) -> str:
    parts = text.split("---", 2)
    if len(parts) < 3:
        return ""
    return parts[1]


def check_package(root: Path, skill_id: str, *, require_registry: bool = True) -> list[str]:
    problems: list[str] = []
    canon = root / "docs" / "skills" / skill_id / "SKILL.md"
    mirror = root / ".cursor" / "skills" / skill_id / "SKILL.md"

    if not canon.is_file():
        problems.append(f"missing canonical source: {canon.relative_to(root).as_posix()}")
        return problems
    if not mirror.is_file():
        problems.append(f"missing Cursor mirror: {mirror.relative_to(root).as_posix()}")

    canon_text = canon.read_text(encoding="utf-8")
    if mirror.is_file():
        mirror_text = mirror.read_text(encoding="utf-8")
        if f"Canonical Skill Source: docs/skills/{skill_id}/SKILL.md" not in mirror_text:
            problems.append("mirror missing Canonical Skill Source pointer")
        if _body_from_heading(canon_text) != _body_from_heading(mirror_text):
            problems.append("canonical and mirror skill bodies diverge")

    front = _frontmatter(canon_text)
    if "description:" not in front:
        problems.append("frontmatter missing description")
    else:
        # Description should be trigger-oriented; reject full algorithm dumps.
        dump_hits = [m for m in WORKFLOW_DUMP_MARKERS if m in front]
        if dump_hits:
            problems.append(
                "description looks like a workflow dump; markers=" + ",".join(dump_hits)
            )
        if "Use when" not in front and "when" not in front.lower():
            problems.append("description should encode when-to-load triggers")

    if "standalone: true" not in canon_text:
        problems.append("skill must declare standalone: true")
    if "## Relationships" not in canon_text:
        problems.append("skill must include ## Relationships")

    lowered = canon_text.lower()
    for hint in UNSUPPORTED_MIRROR_HINTS:
        # Allow mentioning the prohibition; flag instructions to create them.
        if f"copy this skill into {hint}" in lowered or f"add {hint}" in lowered:
            problems.append(f"skill instructs creating unsupported mirror {hint}")

    for surface in (".claude/skills", ".codex/skills"):
        if (root / surface / skill_id / "SKILL.md").is_file():
            problems.append(f"unsupported mirror present: {surface}/{skill_id}/SKILL.md")

    if require_registry:
        registry_path = root / "docs" / "operations" / "CAPABILITY_REGISTRY.json"
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        matches = [c for c in registry.get("capabilities", []) if c.get("id") == skill_id]
        if len(matches) == 0:
            problems.append("skill missing from CAPABILITY_REGISTRY.json")
        elif len(matches) > 1:
            problems.append("skill registered more than once in CAPABILITY_REGISTRY.json")
        else:
            cap = matches[0]
            if cap.get("canonical_source") != f"docs/skills/{skill_id}/SKILL.md":
                problems.append("registry canonical_source mismatch")
            life = cap.get("lifecycle")
            if life not in VALID_LIFECYCLES:
                problems.append(f"invalid lifecycle {life!r}")
            if life == "historical":
                # Historical must not appear as an active priority_a route target alone.
                routing = registry.get("routing", {})
                for row in routing.get("priority_a_matrix", []):
                    ids = row.get("capability_ids") or []
                    if skill_id in ids:
                        problems.append(
                            "historical skill must not appear in priority_a_matrix"
                        )

    readme = root / "docs" / "skills" / "README.md"
    if readme.is_file() and skill_id not in readme.read_text(encoding="utf-8"):
        problems.append("docs/skills/README.md does not list skill")

    return problems


def check_red_fixture(root: Path) -> list[str]:
    """Assert the recorded RED fixture still demonstrates mirror-only failure."""
    problems: list[str] = []
    base = (
        root
        / "docs"
        / "skills"
        / "sample-brain-skill-authoring"
        / "fixtures"
        / "red-mirror-only-path-hint"
    )
    bad_mirror = base / ".cursor" / "skills" / "sample-brain-path-hint" / "SKILL.md"
    if not bad_mirror.is_file():
        problems.append("RED fixture missing defective mirror skill")
    canon = base / "docs" / "skills" / "sample-brain-path-hint" / "SKILL.md"
    if canon.is_file():
        problems.append("RED fixture unexpectedly includes canonical docs/skills package")
    text = bad_mirror.read_text(encoding="utf-8") if bad_mirror.is_file() else ""
    front = _frontmatter(text)
    if "export SAMPLE_BRAIN_DB_PATH" not in front and "Create a temp directory" not in front:
        problems.append("RED fixture description no longer looks like a workflow dump")
    if ".claude/skills" not in text:
        problems.append("RED fixture lost unsupported-mirror instruction signal")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--skill-id", default="sample-brain-skill-authoring")
    parser.add_argument("--skip-registry", action="store_true")
    parser.add_argument("--check-red-fixture", action="store_true")
    args = parser.parse_args(argv)

    root = args.root or _repo_root()
    problems = check_package(
        root, args.skill_id, require_registry=not args.skip_registry
    )
    if args.check_red_fixture:
        problems.extend(check_red_fixture(root))

    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        return 1
    print(f"PASS: authoring package ok for {args.skill_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
