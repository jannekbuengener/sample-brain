<!--
Evaluation-only fixture skill for sample-brain-skill-effectiveness.
NOT an active production capability. Do not register in CAPABILITY_REGISTRY
routing matrices. Do not add a Cursor production mirror for this fixture.
-->
---
name: eval-only-cite-git-sha
description: >
  Use when producing a Sample Brain diagnosis or review handoff that must bind
  findings to the exact repository revision under inspection.
---

# Eval-Only Cite Git SHA (Fixture)

## Purpose

Evaluation fixture (technique). Force diagnosis outputs to cite the current
repository Git SHA so revision-bound claims are auditable.

```text
INSPECT -> READ HEAD SHA -> CITE SHA IN HANDOFF -> FINDINGS
```

## Required Output Shape

Every diagnosis handoff MUST include:

```yaml
inspected_revision: <40-char-or-abbreviated-git-sha>
findings: []
```

If HEAD SHA cannot be read, say `inspected_revision: unknown` and stop inventing
a SHA.

## Non-Activation

Do not use for pure documentation spelling edits, changelog prose, or tasks
that do not make revision-bound technical claims.

## Boundaries

- Fixture only for effectiveness evaluation under #1304
- Not a replacement for `sample-brain-root-cause`
- No private paths, secrets, or product implementation
