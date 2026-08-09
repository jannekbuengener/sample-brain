<!--
Canonical Skill Source: docs/skills/sample-brain-issue-to-session-plan/SKILL.md
Surface: docs (canonical)
Sync Status: canonical
Last Verified: 2026-08-09
Drift Policy: Cursor mirrors must match this skill body.
-->
---
name: sample-brain-issue-to-session-plan
description: >
  Turn one Sample Brain GitHub issue into a current, small, test-first session
  plan without treating an open issue as authorization to implement.
---

# Sample Brain Issue-To-Session-Plan Skill

## Purpose

Use this skill to turn one GitHub issue into a small, current work plan. An open
issue is a work candidate, not automatic authorization to implement. The plan
must identify the smallest useful slice and its blockers before any product
change begins.

## Required Context And Safety

Before reading beyond the target issue, read current repository governance,
`docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md`, and
`docs/DATA_AND_ARTIFACT_POLICY.md`. Then inspect the target issue, parent issue
when present, direct dependencies, materially relevant open PRs, the current
`main` state, existing implementation, and existing tests.

Read only the additional documentation needed to ground the issue. Do not widen
the search to adjacent work without an explicit dependency. Tracked
repository-local paths in the current Sample-Brain checkout are allowed for
read-only planning, including repo-relative documentation, product code, and
tests. Do not read private local files outside the repository, user-specific
absolute paths without explicit relevance and approval, private tracks, samples,
databases, caches, generated artifacts, secrets, model caches, or other
environment-specific files outside the tracked repository canon. Do not create
files, tests, code, issues, or PR changes merely because this skill produced a
plan.

## Method

1. Restate the issue outcome and acceptance criteria in current repository
   terms. Mark missing or contradictory requirements as unconfirmed.
2. Determine the applicable canonical documentation, current implementation,
   existing tests, direct dependencies, and relevant open PRs.
3. Define one small slice, likely affected paths, explicit non-goals, blockers,
   and a minimum validation set.
4. For any implementation slice, require this fixed sequence:

```text
DOCS_GATE -> TEST_GATE -> TEST_FREEZE -> IMPLEMENTATION -> CHECKS
```

5. Route implementation through `sample-brain-test-first`. Do not bypass the
   sequence even when the issue seems small or well specified.

## Output

```yaml
issue: <number or URL>
goal: <concrete outcome>
canonical_docs: []
current_state: <implementation and test evidence>
direct_dependencies: []
relevant_open_prs: []
small_slice: <bounded work>
likely_paths: []
must_not_touch: []
blockers: []
test_first_sequence: DOCS_GATE -> TEST_GATE -> TEST_FREEZE -> IMPLEMENTATION -> CHECKS
minimum_validation: []
next_recommended_step: sample-brain-test-first | planning_blocked
```

## Stop Conditions

- The issue, acceptance criteria, dependency, or canonical documentation is
  missing, contradictory, or too vague: return `planning_blocked` and name the
  needed evidence.
- Current `main`, a relevant PR, or existing tests change the intended slice:
  narrow or stop; do not plan against stale assumptions.
- The plan expands into unrelated issues, refactors, dependencies, models,
  private data, or generated artifacts: stop and remove that expansion.
- An issue requests runtime implementation but no test-first path can be named:
  stop before implementation.

## Relationship To Other Skills

```text
new feature or issue -> this skill -> sample-brain-test-first
unclear bug with product-behavior cause -> sample-brain-root-cause -> sample-brain-regression-gap -> sample-brain-test-first
unclear bug with CI, tooling, or infrastructure cause -> sample-brain-root-cause -> jMerta/ci-fix and sample-brain-ci-debugger
unclear bug with documentation or contract cause -> sample-brain-root-cause -> jMerta/docs-sync; sample-brain-test-first only for a later approved product-code change
known defect -> sample-brain-regression-gap -> sample-brain-test-first
```

Issue `#233` is a valid future input: this skill may identify its documented
one-shot analysis scope and direct dependencies, but it does not implement it.
