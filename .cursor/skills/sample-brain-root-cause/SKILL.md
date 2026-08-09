---
name: sample-brain-root-cause
description: >
  Isolate and evidence the cause of a concrete Sample Brain symptom before
  proposing a minimal fix plan. Does not implement a fix or write tests.
---
<!--
Canonical Skill Source: docs/skills/sample-brain-root-cause/SKILL.md
Surface: cursor
Sync Status: mirrored-from-canon
Last Verified: 2026-08-09
Drift Policy: Cursor mirrors must match this skill body.
-->

# Sample Brain Root-Cause Skill

## Purpose

Use this skill for a concrete symptom that must be understood before it is
fixed. Follow this order:

```text
SYMPTOM -> HYPOTHESES -> EVIDENCE -> ROOT CAUSE -> MINIMAL FIX PLAN
```

For example, a displayed BPM of `129.73` may originate in analysis, storage,
retrieval, or presentation. Do not propose rounding until the responsible
boundary is proven.

This skill does not implement product changes or write tests. After a confirmed
cause, route to `sample-brain-regression-gap`, then to
`sample-brain-test-first` before implementation.

## When To Use

- A reproducible wrong value, error, unexpected CLI result, failed check, or
  suspected contract/data-flow defect has an unclear cause.
- A previous fix changed the symptom without explaining why it occurred.
- A defect affects BPM, key, audio analysis, track deconstruction, stems, loops
  or sections, sample library, search, matching, workbench, preview, rendering,
  SQLite, FL Studio export, CLI, config, CI/tests, or an optional model backend.

Do not use for a new feature plan or to implement a fix.

## Required Context And Safety

Read `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md` and
`docs/DATA_AND_ARTIFACT_POLICY.md` before investigation. Read the affected
contract, implementation, tests, issue, and relevant open PRs only when they
materially affect the symptom.

Do not automatically read private working memory, logs, local databases,
caches, generated artifacts, model caches, secrets, private tracks, or sample
audio. Evidence must not require private files. A synthetic reproducible audio
fixture is acceptable when needed and permitted by the artifact policy.

## Method

1. State the observed symptom, expected behavior, reproduction, affected area,
   and current Git SHA.
2. List plausible hypotheses across input, analysis, storage, query, contract,
   formatting, configuration, and optional backend boundaries.
3. Confirm or reject each hypothesis with evidence. Prefer a reproducible test,
   concrete file and line, Git SHA, CLI/test output, schema/query, JSON contract,
   log, or synthetic fixture.
4. Name one root cause only when the evidence distinguishes it from the symptom.
5. Propose the smallest reversible fix plan without changing code or tests.

## Delegation

This skill owns synthesis. Reuse existing read-only agents for analysis only:

| Situation | Preferred agent |
|-----------|-----------------|
| CI failure or flaky check | `sample-brain-ci-debugger` |
| Code or diff behavior | `sample-brain-code-reviewer` |
| Documentation or contract drift | `sample-brain-docs-sync-maintainer` |
| Boundary or data-flow question | `sample-brain-system-architect` |
| Final scope and check review | `sample-brain-quality-gatekeeper` |

Do not create duplicate agents. An implementation engineer is not a substitute
for this investigation.

## Output

Return this small handoff, leaving unsupported fields as `unknown`:

```yaml
symptom: <observed behavior>
hypotheses: []
evidence: []
root_cause: <proven cause or unknown>
minimal_fix_plan: <description only>
residual_risk: <risk or unknown>
next_recommended_step: sample-brain-regression-gap | ROOT_CAUSE_INCONCLUSIVE
```

## Stop Conditions

- Evidence does not prove a cause: return `ROOT_CAUSE_INCONCLUSIVE` and name
  the exact missing evidence.
- The symptom is not reproducible or bounded: request a tighter reproduction.
- The proposed work expands beyond a minimal fix plan: stop and narrow scope.
- Private data, generated artifacts, secrets, runtime mutation, dependency
  changes, or model installation would be required: stop and report the boundary.

## Handoff

```text
confirmed cause -> sample-brain-regression-gap -> sample-brain-test-first
inconclusive cause -> collect only the named evidence, then rerun this skill
```
