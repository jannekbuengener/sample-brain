"""Shared capability registry / routing / drift helpers (stdlib only)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

REGISTRY_PATH = ROOT / "docs" / "operations" / "CAPABILITY_REGISTRY.json"
KPI_CONTRACT_PATH = ROOT / "docs" / "operations" / "KPI_CONTRACT.json"
OPERATIONS_README = ROOT / "docs" / "operations" / "README.md"
SKILL_ROUTING_PATH = ROOT / ".cursor" / "rules" / "skill-routing.mdc"
SB_SKILLS_PATH = ROOT / "SB.VERFUEGBARE.SKILLS.md"
AGENT_LIST_PATH = ROOT / "SB.AGENT.LIST.json"
HISTORICAL_SKILLS_LISTE = ROOT / "SB.VERFUEGBARE.SKILLS_LISTE_2026-08-09.md"
DOCS_SKILLS_DIR = ROOT / "docs" / "skills"
CURSOR_SKILLS_DIR = ROOT / ".cursor" / "skills"
CURSOR_AGENTS_DIR = ROOT / ".cursor" / "agents"

VALID_TYPES = frozenset(
    {"skill", "agent", "workflow", "helper", "external-tool", "operator-only"}
)
VALID_LIFECYCLES = frozenset({"active", "on-demand", "historical", "parked"})
VALID_SOURCE_KINDS = frozenset({"local", "external", "operator"})

BEGIN_MARKER = "<!-- BEGIN GENERATED CAPABILITY ROUTING -->"
END_MARKER = "<!-- END GENERATED CAPABILITY ROUTING -->"

_SURFACE_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_YAML_FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_registry(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    return load_json(base / "docs" / "operations" / "CAPABILITY_REGISTRY.json")


def load_kpi_contract(root: Path | None = None) -> dict[str, Any]:
    base = root or ROOT
    return load_json(base / "docs" / "operations" / "KPI_CONTRACT.json")


def capability_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in registry.get("capabilities", [])}


def normalize_skill_contract_body(text: str) -> str:
    """Strip surface HTML metadata comments; keep YAML frontmatter + body comparable."""
    without_comments = _SURFACE_COMMENT_RE.sub("", text)
    # Normalize newlines and trim trailing whitespace per line for stable compare.
    lines = [line.rstrip() for line in without_comments.replace("\r\n", "\n").split("\n")]
    # Collapse runs of blank lines (comment removal often leaves an extra blank).
    collapsed: list[str] = []
    blank = False
    for line in lines:
        if not line.strip():
            if blank:
                continue
            blank = True
            collapsed.append("")
        else:
            blank = False
            collapsed.append(line)
    while collapsed and not collapsed[0].strip():
        collapsed.pop(0)
    while collapsed and not collapsed[-1].strip():
        collapsed.pop()
    return "\n".join(collapsed) + "\n"


def extract_generated_block(text: str) -> str | None:
    start = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end < start:
        return None
    return text[start : end + len(END_MARKER)]


def replace_generated_block(text: str, generated_block: str) -> str:
    existing = extract_generated_block(text)
    if existing is None:
        if not text.endswith("\n"):
            text += "\n"
        return text + "\n" + generated_block + "\n"
    start = text.find(BEGIN_MARKER)
    end = text.find(END_MARKER) + len(END_MARKER)
    return text[:start] + generated_block + text[end:]


def _display_name(cap_id: str) -> str:
    return f"`{cap_id}`"


def render_generated_routing_block(registry: dict[str, Any]) -> str:
    routing = registry.get("routing", {})
    matrix = routing.get("priority_a_matrix", [])
    priority_b = routing.get("priority_b_matrix", [])
    chains = routing.get("default_chains", [])
    special = routing.get("special_routes", {})

    lines: list[str] = [BEGIN_MARKER, ""]
    lines.append("## Routing-Matrix")
    lines.append("")
    lines.append("| Situation | Capability |")
    lines.append("|-----------|------------|")
    for row in matrix:
        caps = ", ".join(_display_name(c) for c in row["capability_ids"])
        if row.get("note"):
            caps = f"{caps} {row['note']}"
        lines.append(f"| {row['situation']} | {caps} |")

    lines.append("")
    lines.append("## Security-Workflow-Audit (Priorität B, nur gezielt)")
    lines.append("")
    lines.append(
        "Nur bei **explizitem** Security-/CI-Audit-Auftrag. "
        "Keine Auto-Änderung ohne separaten Auftrag."
    )
    lines.append("")
    lines.append(
        "Priority B skills come from the external Anthropic-Cybersecurity-Skills "
        "package (not copied into this repo)."
    )
    lines.append("")
    lines.append("| Thema | Skill |")
    lines.append("|-------|-------|")
    for row in priority_b:
        caps = ", ".join(_display_name(c) for c in row["capability_ids"])
        lines.append(f"| {row['situation']} | {caps} |")

    lines.append("")
    lines.append("## Default-Reihenfolge")
    lines.append("")
    lines.append("1. Priorität A (täglicher Workflow)")
    lines.append("2. Priorität B nur bei explizitem Security-Auftrag")
    lines.append("3. Priorität C (Snyk, ZAP, DevSecOps-Meta) nicht als Default")
    lines.append("")
    lines.append("Die lokale Reihenfolge ist verbindlich fuer Sample-Brain-spezifische Arbeit:")
    lines.append("")
    lines.append("```text")
    for chain in chains:
        lines.append(chain)
    lines.append("```")
    lines.append("")

    visual = special.get("screen1_visual_acceptance", {})
    if visual:
        lines.append("## Screen-1 Visual Acceptance")
        lines.append("")
        lines.append(visual.get("summary", ""))
        lines.append("")
        lines.append("Sequence:")
        lines.append("")
        lines.append("```text")
        for step in visual.get("sequence", []):
            lines.append(step)
        lines.append("```")
        lines.append("")
        lines.append("Status values: " + ", ".join(f"`{s}`" for s in visual.get("statuses", [])))
        lines.append("")
        lines.append(
            "No AI pixel judge. Owner visual judgment is not replaced by automated tests."
        )
        lines.append("")

    hygiene = special.get("repository_hygiene", {})
    if hygiene:
        lines.append("## Repository Hygiene")
        lines.append("")
        lines.append(hygiene.get("summary", ""))
        lines.append("")
        for item in hygiene.get("authorities", []):
            lines.append(f"- {item}")
        lines.append("")
        lines.append(
            f"Not an active hygiene authority: `{hygiene.get('not_authority', 'docs/ISSUE_BACKLOG.md')}` "
            "(HISTORICAL_LEDGER only)."
        )
        lines.append("")

    parked = special.get("parked_tracks", {})
    if parked:
        lines.append("## Parked Tracks (do not auto-route)")
        lines.append("")
        lines.append(parked.get("summary", ""))
        lines.append("")
        for track in parked.get("tracks", []):
            lines.append(f"- {track}")
        lines.append("")
        lines.append(
            f"Reactivation: `{parked.get('reactivation', 'explicit_owner_go')}` only."
        )
        lines.append("")

    typing = special.get("capability_typing_notes", [])
    if typing:
        lines.append("## Capability typing notes")
        lines.append("")
        for note in typing:
            lines.append(f"- {note}")
        lines.append("")

    lines.append(
        "Machine routing authority: `docs/operations/CAPABILITY_REGISTRY.json`. "
        "Do not hand-edit this generated block; regenerate via "
        "`python tools/generate_capability_views.py`."
    )
    lines.append("")
    lines.append(END_MARKER)
    return "\n".join(lines)


def apply_generated_views(root: Path | None = None) -> dict[str, str]:
    base = root or ROOT
    registry = load_registry(base)
    block = render_generated_routing_block(registry)
    updated: dict[str, str] = {}
    for rel in (
        ".cursor/rules/skill-routing.mdc",
        "SB.VERFUEGBARE.SKILLS.md",
    ):
        path = base / rel
        text = path.read_text(encoding="utf-8")
        new_text = replace_generated_block(text, block)
        if not new_text.endswith("\n"):
            new_text += "\n"
        path.write_text(new_text, encoding="utf-8", newline="\n")
        updated[rel] = new_text
    return updated


def _require_fields(cap: dict[str, Any], fields: list[str], problems: list[str]) -> None:
    cid = cap.get("id", "<missing-id>")
    for field in fields:
        if field not in cap:
            problems.append(f"capability {cid}: missing field {field}")


def validate_registry_schema(registry: dict[str, Any], root: Path | None = None) -> list[str]:
    base = root or ROOT
    problems: list[str] = []
    if registry.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    caps = registry.get("capabilities")
    if not isinstance(caps, list) or not caps:
        problems.append("capabilities must be a non-empty list")
        return problems

    seen: set[str] = set()
    for cap in caps:
        if not isinstance(cap, dict):
            problems.append("capability entry is not an object")
            continue
        _require_fields(
            cap,
            [
                "id",
                "type",
                "purpose",
                "problem_solved",
                "trigger",
                "inputs",
                "outputs",
                "authority",
                "mutation_level",
                "dependencies",
                "fallback",
                "canonical_source",
                "source_kind",
                "repo_areas",
                "validation",
                "lifecycle",
                "linked_kpis",
            ],
            problems,
        )
        cid = cap.get("id")
        if not isinstance(cid, str) or not cid:
            problems.append("capability id must be a non-empty string")
            continue
        if cid in seen:
            problems.append(f"duplicate capability id: {cid}")
        seen.add(cid)
        ctype = cap.get("type")
        if ctype not in VALID_TYPES:
            problems.append(f"{cid}: invalid type {ctype!r}")
        life = cap.get("lifecycle")
        if life not in VALID_LIFECYCLES:
            problems.append(f"{cid}: invalid lifecycle {life!r}")
        sk = cap.get("source_kind")
        if sk not in VALID_SOURCE_KINDS:
            problems.append(f"{cid}: invalid source_kind {sk!r}")

        problems.extend(_validate_canonical_source(cap, base))

    routing = registry.get("routing")
    if not isinstance(routing, dict):
        problems.append("routing object required")
    else:
        special = routing.get("special_routes", {})
        visual = special.get("screen1_visual_acceptance", {})
        statuses = set(visual.get("statuses", []))
        required_status = {
            "VISUAL_ACCEPT_PENDING",
            "VISUAL_ACCEPT_PASS",
            "VISUAL_ACCEPT_FAIL",
        }
        if not required_status.issubset(statuses):
            problems.append("screen1_visual_acceptance missing required status values")
        parked = special.get("parked_tracks", {})
        if parked.get("reactivation") != "explicit_owner_go":
            problems.append("parked_tracks.reactivation must be explicit_owner_go")
        hygiene = special.get("repository_hygiene", {})
        if "ISSUE_BACKLOG" not in str(hygiene.get("not_authority", "")):
            problems.append("repository_hygiene must deny ISSUE_BACKLOG as authority")

    return problems


def _validate_canonical_source(cap: dict[str, Any], root: Path) -> list[str]:
    problems: list[str] = []
    cid = cap["id"]
    sk = cap.get("source_kind")
    ctype = cap.get("type")
    source = cap.get("canonical_source")
    authority = str(cap.get("authority", ""))

    if sk == "local":
        if ctype == "workflow" and source in {"NOT_APPLICABLE", "EXTERNAL"}:
            return problems
        if not isinstance(source, str) or not source or source in {"EXTERNAL", "NOT_APPLICABLE"}:
            problems.append(f"{cid}: local capability requires real canonical_source path")
            return problems
        path = root / source
        if not path.is_file():
            problems.append(f"{cid}: missing local canonical_source {source}")
            return problems
        if ctype == "agent" and not source.startswith(".cursor/agents/"):
            problems.append(f"{cid}: agent canonical_source must be under .cursor/agents/")
        if ctype == "skill" and not source.startswith("docs/skills/"):
            problems.append(f"{cid}: local skill canonical_source must be under docs/skills/")
        if ctype == "helper" and not (
            source.startswith("tools/") or source == "SB.VERFUEGBARE.SKILLS_LISTE_2026-08-09.md"
        ):
            problems.append(
                f"{cid}: helper canonical_source must be under tools/ "
                "(or the frozen historical skills liste)"
            )
        return problems

    if sk == "external":
        if ctype not in {"external-tool", "skill"}:
            problems.append(f"{cid}: external source_kind expects external-tool or skill type")
        if "external" not in authority.lower() and ctype != "external-tool":
            problems.append(f"{cid}: external capability authority must mark external")
        if isinstance(source, str) and source not in {"EXTERNAL", "NOT_APPLICABLE"}:
            # Must not pretend a missing local file is the source of truth.
            if not source.startswith("external:") and (root / source).is_file() is False:
                # Allow external: prefix or EXTERNAL sentinel only.
                if source != "EXTERNAL":
                    problems.append(
                        f"{cid}: external capability must not pretend local path SoT ({source})"
                    )
        if source not in {"EXTERNAL", "NOT_APPLICABLE"} and not str(source).startswith(
            "external:"
        ):
            problems.append(
                f"{cid}: external canonical_source must be EXTERNAL, NOT_APPLICABLE, or external:..."
            )
        if cap.get("lifecycle") not in {"active", "on-demand", "historical", "parked"}:
            problems.append(f"{cid}: external lifecycle invalid")
        if not cap.get("fallback"):
            problems.append(f"{cid}: external capability requires fallback/boundary")
        return problems

    if sk == "operator":
        if ctype != "operator-only":
            problems.append(f"{cid}: operator source_kind requires type operator-only")
        if "operator" not in authority.lower() and "chatgpt" not in authority.lower():
            problems.append(f"{cid}: operator-only authority must be explicit")
        if not cap.get("fallback"):
            problems.append(f"{cid}: operator-only capability requires worker fallback")
        # Must not require private MCP for workers in fallback text.
        fb = str(cap.get("fallback", "")).lower()
        if "required" in fb and "mcp" in fb:
            problems.append(f"{cid}: fallback must not require private MCP for workers")
        return problems

    problems.append(f"{cid}: unhandled source_kind {sk!r}")
    return problems


def validate_agent_authority(registry: dict[str, Any], root: Path | None = None) -> list[str]:
    base = root or ROOT
    problems: list[str] = []
    agents_dir = base / ".cursor" / "agents"
    real_agents = {
        p.stem
        for p in agents_dir.glob("sample-brain-*.md")
        if p.is_file() and not p.name.startswith("_") and p.name != "README_SAMPLE_BRAIN_CURSOR_AGENTS.md"
    }
    # Also include files that match sample-brain-*.md only - README doesn't match.

    registry_agents = {
        c["id"] for c in registry.get("capabilities", []) if c.get("type") == "agent"
    }
    for cid in sorted(registry_agents):
        path = agents_dir / f"{cid}.md"
        if not path.is_file():
            problems.append(f"registry agent missing file: {cid}")
        if cid not in real_agents:
            problems.append(f"registry agent not in .cursor/agents: {cid}")

    list_path = base / "SB.AGENT.LIST.json"
    if not list_path.is_file():
        problems.append("SB.AGENT.LIST.json missing")
        return problems
    agent_list = load_json(list_path)
    list_ids = [a.get("id") for a in agent_list.get("agents", [])]
    if len(list_ids) != len(set(list_ids)):
        problems.append("SB.AGENT.LIST.json has duplicate agent ids")
    for lid in list_ids:
        if not lid:
            problems.append("SB.AGENT.LIST.json has empty agent id")
            continue
        if lid not in real_agents:
            problems.append(f"SB.AGENT.LIST agent missing real file: {lid}")
        if lid not in registry_agents:
            problems.append(f"SB.AGENT.LIST agent missing from registry: {lid}")
        cap = next((c for c in registry["capabilities"] if c["id"] == lid), None)
        if cap and cap.get("type") != "agent":
            problems.append(f"{lid}: registry type must be agent")

    for rid in sorted(registry_agents):
        if rid not in list_ids:
            problems.append(f"registry agent missing from SB.AGENT.LIST.json: {rid}")

    # Phantom / missing: every real sample-brain agent file should be inventoried.
    for aid in sorted(real_agents):
        if aid not in registry_agents:
            problems.append(f"real agent not registered: {aid}")
        if aid not in list_ids:
            problems.append(f"real agent missing from SB.AGENT.LIST.json: {aid}")

    return problems


def validate_skill_mirrors(root: Path | None = None) -> list[str]:
    base = root or ROOT
    problems: list[str] = []
    docs_dir = base / "docs" / "skills"
    cursor_dir = base / ".cursor" / "skills"
    if not docs_dir.is_dir():
        problems.append("docs/skills missing")
        return problems
    for skill_dir in sorted(p for p in docs_dir.iterdir() if p.is_dir()):
        canon = skill_dir / "SKILL.md"
        mirror = cursor_dir / skill_dir.name / "SKILL.md"
        if not canon.is_file():
            problems.append(f"missing canon skill: {canon.relative_to(base)}")
            continue
        if not mirror.is_file():
            problems.append(f"missing cursor skill mirror: {mirror.relative_to(base)}")
            continue
        left = normalize_skill_contract_body(canon.read_text(encoding="utf-8"))
        right = normalize_skill_contract_body(mirror.read_text(encoding="utf-8"))
        if left != right:
            problems.append(f"skill mirror contract drift: {skill_dir.name}")
    return problems


def validate_generated_views(registry: dict[str, Any], root: Path | None = None) -> list[str]:
    base = root or ROOT
    problems: list[str] = []
    expected = render_generated_routing_block(registry)
    for rel in (".cursor/rules/skill-routing.mdc", "SB.VERFUEGBARE.SKILLS.md"):
        path = base / rel
        if not path.is_file():
            problems.append(f"missing view: {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        block = extract_generated_block(text)
        if block is None:
            problems.append(f"{rel}: missing generated capability routing markers")
            continue
        if block != expected:
            problems.append(f"{rel}: generated block does not match registry render")
        # Outside block must not claim historical liste is active authority.
        outside = text.replace(block, "")
        if "SKILLS_LISTE_2026-08-09" in outside:
            lowered = outside.lower()
            if "historical" not in lowered and "frozen" not in lowered:
                problems.append(f"{rel}: historical skills liste referenced without frozen/historical marker")
            if re.search(
                r"skills_liste_2026-08-09[^\n]{0,80}active routing authority",
                lowered,
            ) and "not active" not in lowered:
                problems.append(f"{rel}: historical skills liste referenced as authority")
    return problems


def validate_private_mcp_boundary(registry: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for cap in registry.get("capabilities", []):
        blob = json.dumps(cap, ensure_ascii=True).lower()
        if "sk-" in blob or "token" in blob and "tokenizer" not in blob:
            # Avoid false positives on "mutation" etc.; check explicit secret patterns.
            if re.search(r"sk-[a-z0-9]+", blob) or "bearer " in blob:
                problems.append(f"{cap.get('id')}: possible secret material in registry")
        if cap.get("type") == "operator-only":
            fb = str(cap.get("fallback", "")).lower()
            if "private mcp" in fb and "required" in fb:
                problems.append(f"{cap.get('id')}: private MCP must not be worker-required")
        # Worker-facing skills must not require private MCP.
        if cap.get("source_kind") == "local" and "private mcp" in blob and "required" in blob:
            problems.append(f"{cap.get('id')}: local capability must not require private MCP")
    return problems


def validate_parked_and_hygiene_surfaces(root: Path | None = None) -> list[str]:
    base = root or ROOT
    problems: list[str] = []
    bootloader = (base / "SB.BOOTLOADER.md").read_text(encoding="utf-8")
    # Hygiene row must not list ISSUE_BACKLOG as authority.
    for line in bootloader.splitlines():
        if "Repository Hygiene" in line and "ISSUE_BACKLOG" in line:
            problems.append(
                "SB.BOOTLOADER.md still routes Repository Hygiene via ISSUE_BACKLOG"
            )
    registry = load_registry(base)
    block = render_generated_routing_block(registry)
    if "do not auto-route" not in block.lower() and "Parked Tracks" not in block:
        problems.append("generated routing missing parked tracks section")
    if "VISUAL_ACCEPT_PENDING" not in block:
        problems.append("generated routing missing visual acceptance statuses")
    if "ISSUE_BACKLOG" in block and "Not an active hygiene authority" not in block:
        problems.append("generated hygiene denial missing")
    # ci-debugger must be typed as agent in typing notes or chains context.
    typing_notes = registry.get("routing", {}).get("special_routes", {}).get(
        "capability_typing_notes", []
    )
    if not any("sample-brain-ci-debugger" in n and "agent" in n.lower() for n in typing_notes):
        problems.append("capability typing notes must state ci-debugger is an agent")
    return problems


def validate_historical_liste_not_active_authority(root: Path | None = None) -> list[str]:
    base = root or ROOT
    problems: list[str] = []
    registry = load_registry(base)
    for cap in registry.get("capabilities", []):
        if cap.get("id") == "sb-verfuegbare-skills-liste-2026-08-09":
            if cap.get("lifecycle") != "historical":
                problems.append("skills liste capability must be lifecycle=historical")
    for rel in (
        "docs/operations/README.md",
        ".cursor/rules/skill-routing.mdc",
        "SB.VERFUEGBARE.SKILLS.md",
        "docs/SKILL_INTEGRATION_PLAN.md",
    ):
        path = base / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if "SKILLS_LISTE_2026-08-09" in text:
            # Must be marked historical / frozen / not authority nearby.
            if not re.search(
                r"SKILLS_LISTE_2026-08-09[^\n]{0,120}(historical|frozen|not .+authority|HISTORICAL)",
                text,
                re.IGNORECASE,
            ) and not re.search(
                r"(historical|frozen|HISTORICAL|not an? active)[^\n]{0,120}SKILLS_LISTE_2026-08-09",
                text,
                re.IGNORECASE,
            ):
                problems.append(f"{rel}: skills liste mentioned without historical/frozen marker")
    return problems


def collect_capability_drift(root: Path | None = None) -> list[str]:
    base = root or ROOT
    problems: list[str] = []
    registry_path = base / "docs" / "operations" / "CAPABILITY_REGISTRY.json"
    if not registry_path.is_file():
        return ["missing docs/operations/CAPABILITY_REGISTRY.json"]
    if not (base / "docs" / "operations" / "KPI_CONTRACT.json").is_file():
        problems.append("missing docs/operations/KPI_CONTRACT.json")
    if not (base / "docs" / "operations" / "README.md").is_file():
        problems.append("missing docs/operations/README.md")

    registry = load_registry(base)
    problems.extend(validate_registry_schema(registry, base))
    problems.extend(validate_agent_authority(registry, base))
    problems.extend(validate_skill_mirrors(base))
    problems.extend(validate_generated_views(registry, base))
    problems.extend(validate_private_mcp_boundary(registry))
    problems.extend(validate_parked_and_hygiene_surfaces(base))
    problems.extend(validate_historical_liste_not_active_authority(base))

    # Absolute path / secret leak scan on tracked ops artifacts.
    for rel in (
        "docs/operations/CAPABILITY_REGISTRY.json",
        "docs/operations/KPI_CONTRACT.json",
        "docs/operations/README.md",
    ):
        text = (base / rel).read_text(encoding="utf-8")
        if re.search(r"[A-Za-z]:\\Users\\", text) or "/home/" in text:
            problems.append(f"{rel}: contains private absolute path pattern")
        if re.search(r"sk-[A-Za-z0-9]{10,}", text):
            problems.append(f"{rel}: contains token-like secret pattern")

    return problems


def count_duplicate_authority_surfaces(root: Path | None = None) -> int:
    """DERIVABLE: surfaces that still claim independent routing matrix authority."""
    base = root or ROOT
    count = 0
    # After migration, only registry is authority; views are generated.
    # Count as duplicate if a view is missing generated markers (hand-maintained).
    for rel in (".cursor/rules/skill-routing.mdc", "SB.VERFUEGBARE.SKILLS.md"):
        path = base / rel
        if path.is_file() and extract_generated_block(path.read_text(encoding="utf-8")) is None:
            count += 1
    return count
