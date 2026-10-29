---
name: sample-brain-skill-authoring
description: >
  Use when creating, revising, packaging, registering, validating, or retiring a
  repository-owned Sample Brain skill, or when an agent is about to edit
  .cursor/skills, docs/skills, CAPABILITY_REGISTRY, or generated skill-routing
  views for a new/changed skill. Not for ordinary product bugs, QML features,
  or generic Cursor skill tutorials outside Sample Brain packaging.
---
<!--
Canonical Skill Source: docs/skills/sample-brain-skill-authoring/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Last Verified: 2026-10-29
Drift Policy: Cursor mirrors must match this skill body.
-->

# Sample Brain Skill-Authoring Skill

## Purpose

Sample Brain-specific glue for the skill lifecycle:

```text
OBSERVED REUSABLE FAILURE/NEED
-> REUSE CHECK
-> BASELINE WITHOUT SKILL
-> MINIMAL SKILL DESIGN
-> CANONICAL PACKAGE
-> OPTIONAL RESOURCES/SCRIPTS
-> CURSOR MIRROR
-> CAPABILITY REGISTRY
-> ROUTING (generate views)
-> BEHAVIORAL EFFECTIVENESS
-> DRIFT / LIFECYCLE VALIDATION
-> ACTIVE | ON-DEMAND | HISTORICAL
```

Does **not** replace generic Superpowers / Cursor skill-writing methodology.
Reuses TDD and progressive-disclosure ideas; encodes SB canon, mirrors,
registry, routing, standalone, and drift rules.

**Standalone Guarantee:** `standalone: true`  
Does **not** require `sample-brain-skill-effectiveness` (#1304) or any other
skill at runtime. Prefer that evaluator when available; otherwise run
RED/GREEN/variants manually.

## When To Use

- New repository-owned skill under `docs/skills/`
- Material edit to an existing SB skill (triggers, outputs, lifecycle, package)
- Packaging/register/routing work for skills
- Retiring or marking a skill historical

## Non-Triggers

- Ordinary product bugfix / feature implementation
- One-off docs or test edits that are not a reusable agent workflow
- Mechanical invariants better enforced by schema/linter/test/generator
- External expertise already covered (add SB glue only if adaptation is real)
- ChatGPT operator plugins / private MCP (not repository worker skills)

## Primary Rule

**No new or material skill edit without observing baseline first.**

## Decisions

| Question | Options |
|----------|---------|
| Reuse | `REUSE EXISTING` \| `EXTEND EXISTING` \| `CREATE NEW` \| `DO NOT CREATE` |
| Skill type | `discipline` \| `technique` \| `pattern` \| `reference` |
| Lifecycle | live enums only: `active` \| `on-demand` \| `historical` \| `parked` |
| Mirror surfaces | Cursor `.cursor/skills/` only unless loader need proven |

`DO NOT CREATE` is valid and desirable.

## Compact Workflow

1. **Observe need** — name the reusable agent failure; capture baseline without the skill.
2. **Reuse check** — search `docs/skills/`, registry, external skills, AGENTS/canon, deterministic tools. Decide reuse/extend/create/do-not-create.
3. **Minimal design** — id `sample-brain-<domain>-<capability>`; description = when-to-load (triggers/symptoms), not a step dump; match guidance form to failure (pressure / recipe / required fields / IF-THEN).
4. **Canonical package** — edit `docs/skills/<id>/SKILL.md` first. Keep purpose/trigger/decisions/workflow/output/stop/relationships inline. Split large refs/scripts only when size/reuse justifies (see `references/progressive-disclosure.md`).
5. **Cursor mirror** — copy body to `.cursor/skills/<id>/SKILL.md`; identify canonical source; never primary-edit the mirror.
6. **No unjustified mirrors** — do not add `.claude`, `.codex`, OpenCode, Gemini skill trees without verified loader need.
7. **Registry once** — add exactly one capability in `docs/operations/CAPABILITY_REGISTRY.json`. Map candidate/active/on-demand/retired language onto live enums (`historical` for retired).
8. **Routing** — update `routing.priority_a_matrix` / `default_chains` only as needed; run `python tools/generate_capability_views.py`. Never hand-edit generated blocks in `.cursor/rules/skill-routing.mdc` or `SB.VERFUEGBARE.SKILLS.md`.
9. **Behavior proof** — positive activation, negative activation, baseline-vs-skill delta, transfer/variant, counterexample; discipline skills need pressure. Use #1304 when stable; else manual RED/GREEN.
10. **Deterministic checks** — reuse `check_capability_drift.py` / `check_canon_drift.py` / skill contract tests; run `scripts/check_authoring_package.py` for package shape. Automate mechanical rules before adding prose.
11. **Promote / retire** — promotion needs proven need + behavior improvement + package/registry green + no duplicate. Retirement: stop active routing, set `lifecycle: historical`, keep necessary historical refs clearly marked.

## Output Contract

```yaml
need: <observed failure>
reuse_decision: REUSE EXISTING | EXTEND EXISTING | CREATE NEW | DO NOT CREATE
skill_id: <id or null>
skill_type: discipline | technique | pattern | reference | null
trigger: <when to load>
non_trigger: <when idle>
canonical_source: docs/skills/<id>/SKILL.md | null
optional_resources: [<paths>]
behavior_scenarios: [positive, negative, variant, counterexample]
registry_routing_impact: <summary>
lifecycle: active | on-demand | historical | parked | n/a
validation_evidence: <commands/paths>
exit_decision: PROCEED | DO NOT CREATE | STOP
```

## Stop Conditions

- Baseline not observed before material skill edit
- Duplicate of existing capability without genuine SB adaptation
- Request to build a second registry or skill package manager
- Unsupported multi-harness mirrors without loader evidence
- Mandatory predecessor chains that violate `standalone: true`
- Infinite self-authoring recursion after one self-audit pass
- Private samples, secrets, machine-local paths, or mandatory cloud judges

## Relationships

### Can Receive From

- Observed agent packaging failures / #1302 program issues
- Optional effectiveness results from `sample-brain-skill-effectiveness` when present
- Capability/routing audit findings that need a packaging fix

### Route If

| Condition | Target | Notes |
|-----------|--------|-------|
| Behavior delta still unproven after package green | `sample-brain-skill-effectiveness` (optional) or manual RED/GREEN | suggestion only |
| Product defect found while authoring | `sample-brain-root-cause` | out of authoring scope |
| Registry/view drift only | `tools-check-capability-drift` | not a substitute for behavior proof |
| `DO NOT CREATE` | STOP | record evidence |

### Optional External

- Cursor `create-skill` / Superpowers writing-skills for generic structure only
- Never copy wholesale into this repo

### When to STOP

- Reuse check says do not create
- One self-hosting audit pass completed with defects repaired
- Scope expands into rewriting all skills

### Cycle Rules

One bounded refine after first GREEN/RED packaging pair. No infinite
self-rewrite loops. Relationships suggest; they do not authorize action.
