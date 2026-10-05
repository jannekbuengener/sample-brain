# Sample Brain Operations Front Door

**Status:** ACTIVE OPERATIONS FRONT DOOR  
**Issue:** #719  
**Not product canon.** Product truth remains [`docs/CANON_INDEX.md`](../CANON_INDEX.md).

This page is the AI-readable entry point for capabilities, routing, and process KPIs.

## Authority split

| Concern | Authority |
|---|---|
| Product / architecture / parked product tracks | [`docs/CANON_INDEX.md`](../CANON_INDEX.md) |
| Capabilities / routing / process KPIs | [`CAPABILITY_REGISTRY.json`](CAPABILITY_REGISTRY.json) |
| KPI definitions | [`KPI_CONTRACT.json`](KPI_CONTRACT.json) |
| Agent contracts | [`.cursor/agents/*.md`](../../.cursor/agents/) |
| Skill bodies | [`docs/skills/*/SKILL.md`](../skills/) |
| Skill mirrors | [`.cursor/skills/*/SKILL.md`](../../.cursor/skills/) (mirrors only) |
| Agent inventory view | [`SB.AGENT.LIST.json`](../../SB.AGENT.LIST.json) (not a second agent authority) |

## Quick answers

### 1. Which capabilities exist?
Read [`CAPABILITY_REGISTRY.json`](CAPABILITY_REGISTRY.json) `capabilities[]`.

### 2. Where is the authority?
Capability/routing facts: the registry.  
Generated views (`.cursor/rules/skill-routing.mdc`, `SB.VERFUEGBARE.SKILLS.md`) are derived inside marked blocks only.

### 3. How do I route a task?
1. Classify the slice.
2. Use registry `routing.priority_a_matrix` / `default_chains` / `special_routes`.
3. Or read the generated block in `.cursor/rules/skill-routing.mdc`.

### 4. Which KPIs exist?
[`KPI_CONTRACT.json`](KPI_CONTRACT.json). Classifications: MEASURED, DERIVABLE, UNKNOWN, NOT_APPLICABLE, REJECT.

### 5. How do I get the current snapshot?
```bash
python tools/capability_snapshot.py
```
Stdout JSON only. Do not commit snapshot output as “current numbers”.

### 6. Which values are UNKNOWN?
Any KPI with `classification: UNKNOWN` in the contract, and any snapshot field with `"status": "unknown"` (including when `gh` is unavailable). UNKNOWN stays UNKNOWN — never invent `0`.

### 7. Where is process friction tracked?
- Evidence-backed model: issue #718 closeout comment
- Live drift: `python tools/check_capability_drift.py`
- Snapshot includes `skill_contract_gap_count` and related local KPIs

### 8. What is operator-only?
`private-chatgpt-mcp` (`type: operator-only`). Private MCP is **never** a worker requirement. Workers use repo/git/`gh`/helpers.

### 9. What is parked?
Registry `routing.special_routes.parked_tracks`:
- Screen 3 #679

Parked-track entries must point to a currently live parked/HOLD authority; closed,
deleted, completed-research, or reactivated issues must not remain as routing blocks.

Reactivation requires **explicit Owner GO**. When a listed track is reactivated,
the same governance closeout must update `CAPABILITY_REGISTRY.json` and regenerate
the derived routing views before workers resume automatic routing. GitHub-live
reactivation is immediate truth; a stale parked-track mirror is a drift defect,
not a reason to re-park the work.

### 10. Where is the product canon?
[`docs/CANON_INDEX.md`](../CANON_INDEX.md)

## Screen-1 visual acceptance

For UI/QML visual work:

```text
automated validation
-> visual fixture/runtime evidence
-> AGENT VISUAL ACCEPTANCE
-> VISUAL_ACCEPT_PASS | VISUAL_ACCEPT_FAIL
```

Agents own technical/runtime/visual acceptance (fixtures, screenshots, MCP/UI
automation, plugins, skills, reviewers). `VISUAL_ACCEPT_PENDING` means agent
evidence is still incomplete — not an Owner wait state. Owner does not run
operative acceptance loops. Automated tests alone are not sufficient.

## Repository hygiene

Authorities:
- live worktree/branch state
- `docs/DATA_AND_ARTIFACT_POLICY.md`
- agent `sample-brain-repository-auditor`

`docs/ISSUE_BACKLOG.md` is a **HISTORICAL_LEDGER**, not live hygiene/routing authority.

## Historical / frozen

`SB.VERFUEGBARE.SKILLS_LISTE_2026-08-09.md` is historical/frozen and not active routing authority.

## Commands

```bash
python tools/generate_capability_views.py
python tools/check_capability_drift.py
python tools/capability_snapshot.py
python tools/check_canon_drift.py
```

## Privacy

No private MCP endpoints/tokens, no personal absolute paths, no samples/DB/audio, no product telemetry in registry, KPI contract, or snapshot.
