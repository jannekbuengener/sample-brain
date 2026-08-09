<!--
Canonical Skill Source: docs/skills/sample-brain-test-first/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Last Verified: 2026-08-09
Drift Policy: Cursor mirrors must match the canonical skill body.
-->
---
name: sample-brain-test-first
description: >
  Enforce documentation, tests, test freeze, implementation, and checks for
  significant Sample Brain product changes.
---

# Sample Brain Test-First Skill

## Purpose

Use this repository contract before any significant product-code change. It
does not replace planning, bug-triage, CI-fix, docs-sync, commit, or PR skills.
It fixes the implementation order:

```text
DOCS -> TESTS -> TEST FREEZE -> IMPLEMENTATION -> CHECKS
```

No phase may be skipped.

## DOCS_GATE

Before implementation, read the canonical sources that define the slice. Use
the applicable issue and acceptance criteria, `docs/SYSTEM_REQUIREMENTS.md`,
`docs/TARGET_ARCHITECTURE.md`, feature or contract documents,
`tests/AGENTS.md`, existing behavior tests, and affected API, JSON, or SQLite
contracts. For future track deconstruction work, this includes
`docs/TRACK_MAP_V1.md` when applicable.

The documentation must determine the intended behavior. If it is missing,
contradictory, or leaves acceptance criteria unclear, stop with
`IMPLEMENTATION_BLOCKED_DOCUMENTATION_REQUIRED`. Do not change product code.

## TEST_GATE

Write the relevant tests from the fixed documentation before product code. Test
the requested behavior, important failures, protected existing behavior, and
affected contracts, rather than fitting tests to the current implementation.
New tests may initially be red; behavior already correctly supported may be
green.

Choose the smallest useful types:

- Unit test
- Contract or schema test
- CLI test
- Error-path test
- Config or profile test
- SQLite or database test
- Integration test
- Regression test
- Audio-fixture test

Audio fixtures must be synthetic or public. Do not commit private tracks or
samples. If required tests do not exist, stop with
`IMPLEMENTATION_BLOCKED_TESTS_REQUIRED`.

## TEST_FREEZE

When product implementation begins, the tests defined in TEST_GATE are frozen.
Do not weaken assertions, change expected values to fit wrong code, delete a
test, skip a test, add `xfail`, manipulate fixtures to hide a failure, reduce
acceptance criteria, remove edge cases, or reinterpret tests only to become
green.

## IMPLEMENTATION_GATE

After the freeze, a red frozen test means:

```text
FROZEN TEST RED -> INSPECT AND FIX CODE
```

Inspect the new implementation first, then directly affected existing product
code, then their integration. Only then investigate a possible contract or
test inconsistency.

If a frozen test contradicts canonical documentation, the documentation
contradicts itself, the test requires technically impossible behavior, or the
acceptance criteria are demonstrably wrong, stop with
`IMPLEMENTATION_BLOCKED_CONTRACT_OR_TEST_CONFLICT`. Report the test, canon,
specific conflict, and recommended change. Do not change a frozen test or the
canon without explicit approval.

## CHECKS_GATE

After implementation, run new focused tests, relevant regression tests, and
the required repository checks. For database tests, use an isolated
`SAMPLE_BRAIN_DB_PATH`; do not create tracked runtime artifacts.

All required checks green: `IMPLEMENTATION_GREEN`.

A frozen test remains red: `IMPLEMENTATION_FAILED_CODE_NEEDS_FIX`. Return to
IMPLEMENTATION_GATE; do not bypass TEST_FREEZE.

## Brandherd Rule

Before implementation, documentation and tests are fixed. During
implementation, product code is the primary movable variable. When a
predefined test turns red, the first fire to investigate is the implementation.
Do not move documentation, tests, and code together merely to make a test
pass.

## Statuses

- `IMPLEMENTATION_GREEN`
- `IMPLEMENTATION_BLOCKED_DOCUMENTATION_REQUIRED`
- `IMPLEMENTATION_BLOCKED_TESTS_REQUIRED`
- `IMPLEMENTATION_BLOCKED_CONTRACT_OR_TEST_CONFLICT`
- `IMPLEMENTATION_FAILED_CODE_NEEDS_FIX`

## Scope Boundaries

This skill applies to Sample Brain domains including audio analysis, BPM and
key detection, track deconstruction, stems, loops, sections, sample-library
work, search, matching, workbench, preview, rendering, SQLite, FL Studio
export, and optional model backends. It does not authorize runtime changes,
dependencies, models, private data, or audio processing by itself.
