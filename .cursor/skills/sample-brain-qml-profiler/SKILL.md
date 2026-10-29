<!--
Canonical Skill Source: docs/skills/sample-brain-qml-profiler/SKILL.md
Surface: cursor
Sync Status: mirror-of-docs
Last Verified: 2026-10-29
Drift Policy: Cursor mirrors must match this skill body.
-->
---
name: sample-brain-qml-profiler
description: >
  Use when investigating Sample Brain PySide6 / Qt Quick / QML runtime
  performance — laggy Browser scroll, delegate churn, waveform cost, hover or
  frame spikes, Loader creation, binding storms, or Python↔QML bridge traffic —
  and you must measure a reproducible user action before guessing a QML cause.
---

# Sample Brain QML Profiler Skill

## Purpose

Reproducible profiling of Sample Brain's PySide6 / Qt Quick / QML runtime with
**source-mapped** hotspots. Distinguish measured cost from plausible suspicion.

Central rule:

```text
MEASURE FIRST → LOCATE → HYPOTHESIZE → VERIFY
```

Not:

```text
UI feels slow → guess QML cause → rewrite code
```

Architecture contract (never dilute):

```text
Python/Core/Controller/Audio/Catalog = authoritative
QML                                 = projection / presentation / typed intent
```

Visible lag does **not** assign ownership. Cost may live in bindings, delegates,
rendering, layout, waveforms, Python callbacks, bridge traffic, controllers, or
resource loading.

**Standalone Guarantee:** `standalone: true`

## When To Activate

Activate for performance investigation that materially involves Screen-1 /
Workbench QML or the Python↔QML boundary, especially:

- Browser scrolling / ListView delegate churn
- waveform-heavy row surfaces
- hover / animation / frame spikes
- Loader / component creation
- suspected binding reevaluation storms
- high-rate Python↔QML bridge traffic
- hidden/offscreen work defeating virtualization
- layout / geometry loops
- interaction latency under representative (synthetic) Library sizes

Do **not** activate for:

- generic Python CPU profiling with no QML/bridge surface
- native hard-realtime audio callback profiling (separate ownership)
- product Browser/QML rewrites as the first move
- ARVP / product evaluation scoring
- continuous production telemetry / SaaS

If activation is unclear, prefer a short non-activation note over a speculative
optimization plan.

## Method

```text
REPRODUCIBLE USER ACTION
→ VERIFY LIVE PROFILING TOOLING
→ CAPTURE BOUNDED TRACE
→ IDENTIFY DOMINANT COST CATEGORY
→ MAP COST TO QML/PYTHON SOURCE
→ FORM EVIDENCE-BACKED HYPOTHESIS
→ SMALLEST CONTROL / EXPERIMENT
→ HOTSPOT_PROVEN | NO_ACTIONABLE_HOTSPOT | PROFILE_INCONCLUSIVE
```

### 1. Reproduction contract (mandatory)

Every useful profile starts with a reproducible user action. Record:

| Field | Example |
|-------|---------|
| Build / Git SHA | `git rev-parse HEAD` |
| Surface | `screen1.browserList` |
| Precondition | Library revealed; synthetic N rows loaded |
| Dataset / scale | synthetic / repo-safe only — no private samples/DBs |
| Exact user action | scroll `contentY` 0→max then burst |
| Capture window | short warm-up → interaction → short cool-down |
| Observed symptom | stutter during scroll burst |

Do not profile “the app generally feels slow.”

### 2. Live tool discovery (mandatory)

Run before encoding commands:

```bash
python docs/skills/sample-brain-qml-profiler/scripts/qml_profiler_summarize.py discover
```

Decision tree (follow live output; do not hardcode versions):

1. **Existing `qmlprofiler` CLI** on PATH → may capture `.qtd` if compatible
   with the running Qt major.
2. Else **PySide6 `qmltooling` profiler plugins** + `QQmlDebuggingEnabler` → use
   only when you can actually attach/capture; do not pretend a missing CLI
   exists.
3. Else **repo / local instrumentation** — bounded Python timings, delegate
   create/destroy counters, bridge call counters for the exact interaction
   (research precedent: `src/workbench_waveform_research.py`; adapt pattern,
   do not treat that research ListView as Screen-1 Browser proof).
4. **Helper summarize/map only** — never build a new profiler; never install a
   second Qt SDK solely to satisfy an external skill.

Live baseline (example, re-verify each session): Sample Brain PySide6 wheels
often ship profiler **plugins** without shipping `qmlprofiler.exe`. External
`qt-qml-profiler` CMake/`QT_QML_DEBUG` assumptions do **not** transfer.

### 3. Bounded capture

Prefer:

```text
short warm-up → exact interaction → short cool-down
```

Emit a Sample Brain capture JSON (`schema: sample_brain_qml_profile_v1`) with
`reproduction`, `tool`, `events[]`, and `confounders[]`. Event categories where
tooling supports them:

| Category | Notes |
|----------|-------|
| `frame_render` | frame / scene / paint / animation |
| `binding` | evaluation exists ≠ material cost |
| `delegate_lifecycle` | create/destroy vs intended virtualization |
| `layout` | geometry / anchors loops |
| `js_qml` | JS / signal handlers |
| `resource_waveform` | image / waveform / pixmap |
| `python_bridge` | frequency, payload, sync blocking |
| `memory` | growth ≠ warm-up labeled as leak |

If you already have a Qt Creator `.qtd`, the helper can parse a minimal 2D
subset — still attach a reproduction contract.

### 4. Summarize + source map

```bash
python docs/skills/sample-brain-qml-profiler/scripts/qml_profiler_summarize.py summarize \
  path/to/capture.json
```

Source mapping rules:

- Map to repo paths / component markers when unique.
- Mark `ambiguous` / `unresolved` / `qt_internal_or_empty` honestly.
- **Do not invent line certainty.**

### 5. Evidence classes (always separate)

| Class | Meaning |
|-------|---------|
| `MEASURED` | from the bounded capture / counters |
| `HYPOTHESIS` | causal story consistent with MEASURED |
| `VERIFY` | smallest next control / experiment |

Do not promote HYPOTHESIS to proven without VERIFY (or clear measured dominance
already mapped).

### 6. Controls (local, disposable)

Examples: disable nonessential path; reduced workload; diagnostic reuse
compare; remove instrumentation overhead; baseline vs candidate; temporary
local visual bypass; bridge call-count compare. **Do not commit throwaway
hacks.**

No universal thresholds (e.g. “>16 ms always bug”) without Sample Brain
budgets. Compare baseline / candidate / relative dominant costs.

### 7. Verdicts

| Verdict | When |
|---------|------|
| `HOTSPOT_PROVEN` | dominant measured cost mapped to source/component |
| `NO_ACTIONABLE_HOTSPOT` | bounded evidence shows no actionable dominant cost |
| `PROFILE_INCONCLUSIVE` | insufficient / unstable / unmapped / confounded evidence |

`PROFILE_INCONCLUSIVE` is for weak evidence — **not** merely a wrong theory.
Do not invent a performance bug to justify product work.

## Output contract

Compact YAML-like report (helper can emit). Include:

```yaml
reproduction: {...}
tool: {...}
trace_scope: ...
measured_hotspots: [...]
hypothesis: {...}   # or null
confounders: [...]
next_experiment: {...}
verdict: HOTSPOT_PROVEN | NO_ACTIONABLE_HOTSPOT | PROFILE_INCONCLUSIVE
```

No confidence percentages. Prefer sanitized summaries over bulky raw traces.
Never embed private sample paths, DB contents, credentials, or unrelated
machine-local secrets.

Progressive detail: `references/tool-discovery.md`,
`references/output-contract.md`.

## Stop Conditions / routing

- Hotspot proven but causal chain still unclear → `sample-brain-root-cause`
- Durable protection needed after proven defect →
  `sample-brain-regression-gap` → `sample-brain-test-first`
  (and `sample-brain-qml-component-test` only if that skill is available)
- Substantial product optimization / Browser rewrite → document + stop; out of
  scope for this skill
- Missing reproduction or tooling → `PROFILE_INCONCLUSIVE`, do not optimize

## Relationships

**Standalone Guarantee:** `standalone: true`

### Can Receive From

- vague UI lag reports (after forcing a reproduction contract)
- `sample-brain-root-cause` — when cause may be performance-shaped
- `sample-brain-qml-review` — when review flags a suspected hot path
  (optional; never required)

### Route If

| Condition | Target | Required |
|-----------|--------|----------|
| `hotspot_proven_cause_unclear` | `sample-brain-root-cause` | Yes |
| `known_perf_defect_needs_guard` | `sample-brain-regression-gap` | Yes |
| `approved_perf_repair` | `sample-brain-test-first` | Yes |
| `product_rewrite_requested` | STOP / plan separately | Yes |

### When to STOP

- `NO_ACTIONABLE_HOTSPOT` or `PROFILE_INCONCLUSIVE` reported honestly
- Would require private runtime libraries/audio/DBs as evidence
- Would require installing a second Qt toolchain or new profiler product

### Cycle Rules

Do not loop optimize → re-profile → optimize without a new reproduction or
control. Re-enter after a focused VERIFY experiment or a changed surface.

## Quality Boundaries

This skill must not:

- build a new profiler or continuous telemetry/SaaS
- rewrite Browser/QML as part of skill execution
- profile native hard-realtime audio callbacks unless separately owned
- ship a generic Python profiling handbook
- optimize without measured evidence
- invent universal frame budgets
- suppress warnings or hide confounders
- depend on MCP preflight / ChatGPT-only tooling
- treat preceding QML skills (#1303–#1306) as mandatory predecessors
