<!--
Canonical Skill Source: docs/skills/sample-brain-qml-review/SKILL.md
Surface: docs (canonical)
Sync Status: canonical
Last Verified: 2026-10-29
Drift Policy: Cursor mirrors must match this skill body.
-->
---
name: sample-brain-qml-review
description: >
  Use when reviewing Sample Brain changes that materially contain PySide6,
  Qt Quick or QML behavior, especially bindings, delegates, virtualization,
  layout, gesture arbitration, lifecycle or Python↔QML authority boundaries.
---

# Sample Brain QML Review Skill

## Purpose

High-signal specialist review for Sample Brain PySide6 / Qt Quick / QML
surfaces. Catch QML-specific defects that generic code review routinely misses.
Do not implement fixes, rewrite product UI, or move authority into QML.

Architecture contract (never dilute):

```text
Python/Core = musical / session / audio / persistence / product authority
QML         = projection + typed user intent + local presentation state
```

## When To Activate

Activate when the review surface materially includes any of:

- `.qml` files or embedded `QML_SOURCE` / Qt Quick markup in Python
- PySide6 QML bridge / interaction-adapter behavior tied to QML
- delegates, `reuseItems` / virtualization, Loader/component lifecycle
- binding, anchors/layout, pointer/focus/keyboard gesture arbitration
- QML↔Python authority boundaries

Do **not** activate for pure:

- Python domain / SQLite / analysis / DSP / CLI-only / docs-only changes
- native audio internals with no QML surface

If activation is unclear, prefer a short non-activation note over a shallow
generic QML lecture.

## Method

```text
SCOPE + ARCHITECTURE CONTRACT
→ DETERMINISTIC CHECKS
→ QML-SPECIFIC SEMANTIC REVIEW
→ FINDINGS WITH LOCATION + WHY + FIX DIRECTION
→ PASS | HOLD
```

### 1. Scope + architecture contract

Name the files/diff under review. Restate the Python↔QML ownership boundary.
Stop and return `NOT_ACTIVATED` when the surface is not QML-material.

### 2. Deterministic checks

Run the repository helper when reviewing file paths:

```bash
python docs/skills/sample-brain-qml-review/scripts/qml_review_scan.py --json <paths>
```

Treat helper output as **mechanical evidence only**, not as ownership proof.
The helper may report structural signals such as `STALE_CACHED_DELEGATE_INDEX`
or `BINDING_BREAK_ASSIGNMENT`. It must **not** decide Python↔QML product
authority via token/keyword heuristics. Optional `qmllint` runs only when a
live binary is available for the active PySide6/Qt stack; if unavailable,
continue — semantic review must not depend on it.

### 3. QML-specific semantic review

Prioritize failure classes proven by Sample Brain baseline evidence. Authority
and ownership classes are **agent judgment**:

| Category | Look for |
|----------|----------|
| `DELEGATE_IDENTITY_AS_AUTHORITY` | Visual/`index` identity used as sample/product authority after reuse, filter, sort, or deferred command (helper may only flag mechanical `STALE_CACHED_DELEGATE_INDEX`) |
| `BINDING_BREAK_ASSIGNMENT` | Imperative `width`/`height`/`x`/`y` writes that replace live bindings |
| `QML_SHADOW_AUTHORITY` | QML-local mutation of musical/session fields that Python owns (BPM/key/tempo/transport) — semantic only; not helper-tokenized |
| `DELEGATE_STALE_STATE` | Missing `ListView.onPooled` / reuse cleanup for hover, drag, deferred commands |
| `SIGNAL_COMMAND_FEEDBACK` | Handler loops or duplicate intent emission into Python |
| `HF_PATH_PYTHON_CHATTER` | Synchronous heavy work or avoidable Python round-trips on hover/scroll paths |
| `TIMER_AS_TRANSPORT` | Timer/Animation treated as musical clock/transport authority |

Do not mechanically ban every imperative assignment, every Loader, every
anchor, or every Python call. Context and semantics decide. Do not invent
confidence percentages.

### 4. Findings + verdict

Each finding must include:

```text
SEVERITY: HIGH|MEDIUM|LOW
LOCATION: path:line
CATEGORY: <category>
WHY: <why this is a QML/Qt risk>
AUTHORITY: <boundary involved, or n/a>
REPAIR: <concrete direction, not a patch dump>
EVIDENCE: <helper/qmllint/excerpt>
```

Overall:

- `HOLD` — one or more material findings
- `PASS` — QML-material review completed without material findings
- `NOT_ACTIVATED` — surface is not QML-material

## Stop Conditions

- Cause of a user-visible symptom is still unknown → stop; use
  `sample-brain-root-cause` first.
- Defect is known but protection is missing → hand to
  `sample-brain-regression-gap` (then `sample-brain-test-first`).
- Review would require changing product code inside this skill → stop; report
  findings only.
- Private samples, DBs, indexes, caches, credentials, or machine-local paths
  would be needed as evidence → stop; use synthetic fixtures only.

## Relationships

**Standalone Guarantee:** `standalone: true`

### Can Receive From

- generic code review — when the diff turns out QML-material
- `sample-brain-code-reviewer` — optional deeper read-only pass
- `sample-brain-issue-to-session-plan` — when a QML review slice is planned

### Route If

| Condition | Target | Required | Notes |
|-----------|--------|----------|-------|
| `cause_unknown` | `sample-brain-root-cause` | Yes | Do not invent root cause from style nits |
| `known_defect_needs_guard` | `sample-brain-regression-gap` | Yes | Protection before repair |
| `approved_qml_repair` | `sample-brain-test-first` | Yes | Implementation is out of scope here |
| `non_qml_surface` | generic code review / `NOT_ACTIVATED` | Yes | Do not force QML review |

### When to STOP

- `NOT_ACTIVATED` on non-QML surfaces
- `HOLD` with findings reported (repair is a separate skill/route)
- Evidence would require private runtime data

### Cycle Rules

No loop that re-runs this skill after `sample-brain-test-first` merely to
rubber-stamp the same diff. Re-enter only when the QML surface materially
changed.

## Quality Boundaries

This skill must not:

- auto-edit product code or “just fix” findings
- move Python authority into QML
- promote Timer/Animation to musical/transport authority
- report generic style preferences as bugs
- treat every imperative assignment, Loader, or Python↔QML call as a defect
