---
name: sample-brain-regression-gap
description: >
  Identify the smallest missing Sample Brain protection for a known defect and
  route it to test-first. Does not diagnose an unclear cause or write tests.
---
<!--
Canonical Skill Source: docs/skills/sample-brain-regression-gap/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Last Verified: 2026-08-09
Drift Policy: Cursor mirrors must match this skill body.
-->

# Sample Brain Regression-Gap Skill

## Purpose

Use this skill after a defect or confirmed cause to answer: which protection was
missing, so this behavior could occur or return? It identifies one narrow guard;
it does not write the test or implement the fix.

For a BPM display that exposes an unrounded raw value, the gap may be a UI or
formatting regression test that asserts the intended displayed representation.

## Required Context And Safety

Read `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md` and
`docs/DATA_AND_ARTIFACT_POLICY.md`, then the confirmed cause or defect evidence,
the relevant contract, existing nearby tests, and `tests/AGENTS.md`.

Do not read or use private tracks, samples, databases, caches, generated
artifacts, model caches, secrets, or environment-specific paths as repository
evidence. Any audio fixture proposed for a later test must be synthetic or public
and follow `tests/AGENTS.md`.

## Method

1. State the defect and confirmed root cause. If the cause remains unclear, do
   not infer a guard from speculation.
2. Inspect the smallest relevant existing test surface and contract.
3. Name the single most important missing protection using this taxonomy:
   `unit`, `contract`, `regression`, `integration`, `cli`, `sqlite`, `config`,
   `audio-fixture`, `ui`, or `smoke`.
4. Identify the likely target test path, what the guard protects, minimum
   validation, and the risk of omitting it.
5. Route the handoff without writing or changing tests.

## Output

```yaml
defect: <observed behavior>
root_cause: <confirmed cause or unknown>
missing_test_type: unit | contract | regression | integration | cli | sqlite | config | audio-fixture | ui | smoke | unknown
target_path_or_unknown: <path or unknown>
protects_against: <specific recurrence>
reason_missing: <why current protection is insufficient>
priority: P0 | P1 | P2
minimum_validation: <smallest relevant checks>
risk_if_skipped: <consequence>
next_recommended_step: sample-brain-test-first | sample-brain-root-cause
```

## Routing And Stop Conditions

- Cause insufficiently clear: route to `sample-brain-root-cause`.
- Guard clear: route to `sample-brain-test-first`; it writes and freezes the
  test before product code changes.
- A frozen test is suspected to be wrong: return
  `IMPLEMENTATION_BLOCKED_CONTRACT_OR_TEST_CONFLICT` from
  `sample-brain-test-first`. Do not redefine the frozen test here.
- The defect is not bounded, the target is unknown after reasonable inspection,
  or the task expands into test-suite redesign: stop and report what is missing.
- Do not write a test, change code, change dependencies, install models, or use
  private or generated data.

## Relationships

**Standalone Guarantee:** `standalone: true`

This skill runs independently with a confirmed defect or root cause. Other skill
outputs are optional context enhancements. Use this skill directly after identifying
a product-behavior defect.

### Can Receive From

- `sample-brain-root-cause` — confirmed cause handoff
- `sample-brain-code-reviewer` — code analysis
- `sample-brain-quality-gatekeeper` — quality/scope review
- `sample-brain-validation-evidence-analyst` — validation evidence

### Route If

| Condition | Target | Required | Notes |
|-----------|--------|----------|-------|
| `missing_product_guard_identified` | `sample-brain-test-first` | Yes | Guard identified; test-first writes and freezes test before implementation |
| `ci_only_gap` | `sample-brain-ci-debugger` | No | CI, tooling, or infrastructure gaps (not product defects) |
| `docs_only_gap` | `sample-brain-docs-sync-maintainer` | No | Documentation or contract gaps |
| `dependency_gap` | `sample-brain-dependency-upgrader` | No | Dependency or version gaps |
| `cause_unclear` | `sample-brain-root-cause` | No | Insufficient defect clarity; return to root-cause for refinement |
| `frozen_test_conflict` | `IMPLEMENTATION_BLOCKED_CONTRACT_OR_TEST_CONFLICT` | Yes | Suspected frozen test contradicts canonical documentation |

**Critical Note:** Regression gap identifies missing protection but does NOT write or
change tests. It routes to test-first only when the guard is clear and bounded.
Do not infer a guard from speculation.

### Next Recommended

For identified missing guard: `sample-brain-test-first` (enforces test freeze before implementation)

For gaps in other domains: specialized skill (CI, docs, dependency paths)

For unclear causes: `sample-brain-root-cause` (refine defect understanding)

### Optional External Routes

| External | Local Fallback | Notes |
|----------|----------------|-------|
| (None primary) | — | Internal routing sufficient; no declared external routes for this skill |

### When to STOP

- `IMPLEMENTATION_BLOCKED_CONTRACT_OR_TEST_CONFLICT`: Suspected frozen test
  contradicts canonical documentation or is technically infeasible.
- Defect is not bounded or target is unknown after reasonable inspection.
- Task expands into test-suite redesign or specification changes.
- Cause remains unclear after reasonable investigation (route back to root-cause).

### Cycle Rules

Forward loop to test-first only when guard is clear and bounded. Backward loop to
root-cause allowed when cause is unclear (refinement cycle). Cycles must be narrowing
and result in either a clear guard or a STOP condition; no ping-pong without progress.
