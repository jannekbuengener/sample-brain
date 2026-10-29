---
name: sample-brain-skill-effectiveness
description: >
  Use when judging whether a repository-owned Sample Brain skill materially
  improves agent behavior versus the same task without that skill, or when
  schema/registry checks alone are being treated as proof of skill quality.
---
<!--
Canonical Skill Source: docs/skills/sample-brain-skill-effectiveness/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Last Verified: 2026-10-29
Drift Policy: Cursor mirrors must match this skill body.
-->

# Sample Brain Skill-Effectiveness Skill

## Purpose

Prove behavioral effectiveness of a repository-owned skill:

```text
BASELINE WITHOUT SKILL
-> OBSERVED FAILURE
-> SKILL-ENABLED RUN
-> BEHAVIORAL DELTA
-> VARIANTS / COUNTEREXAMPLES
-> EFFECTIVE | INEFFECTIVE | UNNECESSARY
```

Structural checks (file exists, mirror sync, registry entry) are separate and
**insufficient**. Do not claim `EFFECTIVE` from packaging alone.

**Standalone Guarantee:** `standalone: true`

## When To Use

- Authoring or revising a repository-owned skill and needing behavior proof
- Reviewing a skill PR that only shows structural/CI packaging evidence
- Comparing an existing skill against a new candidate under #1302-style programs

Do not use for product feature implementation, ARVP scoring, generic LLM
benchmarks, or replacing root-cause / code-review / product tests.

## Method

1. Classify `skill_type`: `discipline` | `technique` | `pattern` | `reference`
   (see `references/skill-types.md`).
2. Write scenario(s) with fixed task inputs; skill availability is the treatment.
3. Run **baseline first** without the skill. Record failure category verbatim.
4. Run the **same** scenario with the skill loaded. Record whether it loaded.
5. Score behavioral delta, positive/negative activation, transfer, overconstraint.
6. Emit the result contract (`references/result-schema.md`). Fail closed with
   `INCOMPLETE` when baseline is missing, inputs diverge, skill did not load,
   or only structural validation ran. `INCOMPLETE ≠ INEFFECTIVE`.
7. Validate with `scripts/evaluate_result.py` for deterministic contract checks.

Provider-neutral: Cursor subagents / local agents only. No mandatory cloud or
ChatGPT MCP. Details: `references/evaluation-method.md`.

## Output

```yaml
target_skill: <id>
target_revision: <sha>
skill_type: discipline | technique | pattern | reference
scenario_id: <id>
baseline: {ran: true, outcome: fail, failure_category: ..., notes: ...}
skill_enabled: {ran: true, skill_loaded: true, outcome: pass, notes: ...}
delta: {improved: true, material_change: true, summary: ...}
activation: {positive: used, negative: correctly_idle}
transfer: {variants_passed: 1, counterexamples_passed: 1, overconstraint: false}
verdict: EFFECTIVE | INEFFECTIVE | UNNECESSARY
```

No confidence percentages.

## Stop Conditions

- Baseline not captured before skill-enabled run → `INCOMPLETE` / `missing_baseline`
- Inputs not materially equivalent → `INCOMPLETE` / `inequivalent_inputs`
- Only structural validation available → `INCOMPLETE` / `structural_only`
- Evaluation would require private samples, secrets, or paid external judges → stop
- Scope expands into rewriting all skills or building a benchmark platform → stop

## Relationships

Does **not** replace: product tests, ARVP, code review, `sample-brain-root-cause`,
registry/mirror validation, or CI.

### Can Receive From

- Skill authoring / packaging work (#1308 path when present)
- Domain skill drafts under evaluation (#1303+ candidates)
- Capability/routing audits that need a behavioral follow-up

### Route If

| Condition | Target | Notes |
|-----------|--------|-------|
| `verdict=INEFFECTIVE` and skill still needed | skill author (minimal revise) | one bounded refine cycle |
| `verdict=UNNECESSARY` | stop / do not add skill | record evidence |
| packaging drift only | capability drift tools | not a substitute for this skill |
| product defect found during eval | `sample-brain-root-cause` | out of evaluator scope |

### When to STOP

- Evidence insufficient after reasonable local agent attempts (`INCOMPLETE`)
- Second refine cycle requested without new failure evidence
- Request asks for a generic multi-model leaderboard

### Cycle Rules

One bounded refine after first GREEN/RED pair. No infinite self-eval of this
evaluator against itself as a merge gate for its own first landing.
