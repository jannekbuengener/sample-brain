# Arrangement Confidence and Manual Override Contract v1

**Issue:** #241
**Parent:** #228
**Consumes:** #232 (Track Map v1), #238 (Role Vocabulary v1), #239 (Signal Matrix v1), #265 (StructureV1)
**Produces:** Contract for #240 (Arrangement Classifier)
**Machine-readable contract:** `arrangement_confidence_override_v1.json`
**Schema version:** 1.0.0
**Document type:** `sample_brain.arrangement_confidence_override`

---

This document defines the canonical v1 contract for how sample-brain represents confidence, status, manual overrides, and effective values for arrangement section roles and boundary events. It implements the **Confidence/Override Layer** from the three-layer separation defined in #238.

| Layer | Document | Emits | Must not emit |
|-------|----------|-------|---------------|
| **Neutral boundary layer** | StructureV1 (#265) | Neutral `analysis.timeline.sections` (bar-synchronous, no roles) | Any arrangement role or event label |
| **Arrangement role layer** | Arrangement Map (#240) | Section roles + boundary events from #238 vocabulary | New boundary positions, stem/CLAP labels as ground truth |
| **Confidence/override layer** | **#241 (this)** | Status, evidence accounting, manual overrides | Invented confidence, silent history overwrite |

**Core principle:** Boundary confidence and role confidence stay separate. A strong neutral boundary can still have role `unknown`; a strong role hint must not create a boundary.

---

## 1. Status Model

The status model expresses the state of an automatic analysis result for a section role or boundary event. It applies **independently** to roles and events.

### 1.1 Status Values

| Status | Meaning |
|--------|---------|
| `available` | Automatic analysis produced a complete, usable result for this section role or boundary event. |
| `uncertain` | Automatic analysis ran but produced a partial or ambiguous result (e.g., weak evidence, contradictory signals). The result is usable but not definitive. |
| `unknown` | **Valid, normal result** — evidence is missing, weak, contradictory, or outside the vocabulary. No dummy confidence is invented. |
| `unavailable` | Automatic analysis was not run, not requested, or could not be started (e.g., missing downbeats, component `not_run`). |
| `failed` | Automatic analysis was requested and attempted but errored. |

### 1.2 Status Rules

1. **Independence:** Status applies independently to section roles and boundary events. A section can have role status `available` while its `drop_onset` event has status `unavailable`.
2. **Boundary vs Role separation:** Boundary status (from StructureV1) and role status (from Arrangement Map) are separate fields. No shared universal confidence.
3. **Neutral boundary ≠ role certainty:** A neutral boundary may have status `available` (StructureV1 `ok`) while the following section role has status `unknown`.
4. **Role certainty ≠ boundary certainty:** A role status of `available` does not imply the underlying neutral boundary status is `available`.
5. **`unknown` is first-class:** Status `unknown` is a normal, valid result — not an error, not a fallback, not a "low confidence" placeholder. It carries `evidence_completeness` accounting for why.

---

## 2. Automatic Analysis Result

The **automatic result** is the original output from the Arrangement Map classifier (#240). It is **never deleted or invisibly replaced** by a manual override.

### 2.1 Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | `intro` \| `groove` \| `build` \| `drop` \| `breakdown` \| `outro` \| `unknown` | Yes | Automatically classified section role from #238 vocabulary. |
| `event` | `drop_onset` \| `null` | Yes | Automatically detected boundary event (separate from section role). |
| `status` | Status value (see §1.1) | Yes | Status of the automatic analysis for this role or event. |
| `evidence` | object | Yes | Per-signal evidence contributions from #239 signals. |
| `evidence.positive_signals` | string[] | Yes | Signal names from #239 that positively support this role/event. |
| `evidence.negative_signals` | string[] | Yes | Signal names from #239 that argue against this role/event. |
| `evidence.missing_signals` | string[] | Yes | Signal names from #239 that were nullable/unavailable for this section. |
| `evidence.contradictory_signals` | string[] | Yes | Signal names where positive/negative evidence both exist for different roles. |
| `provenance` | object | Yes | Source tracking: component, version, backend, config, timestamp. |
| `scores` | object | **No** | Optional per-role/event scores — only when semantics are explicitly defined. |

### 2.2 Scores (Optional)

Scores are **not universal confidence**. They are only included when **all** of the following are explicitly defined:
- Name
- Level: `boundary` / `role` / `event`
- Meaning
- Value range
- Provenance
- Calibration status (calibrated probability vs relative track score)
- Semantics of absent score

If score semantics cannot be defined reliably, the score field is **omitted entirely** — no placeholder values.

| Score Field | Level | Description |
|-------------|-------|-------------|
| `role_score` | role | Track-relative role scoring aggregate. Range/meaning defined by classifier. |
| `event_score` | event | Track-relative boundary event scoring. Range/meaning defined by classifier. |
| `boundary_quality` | boundary | Neutral boundary quality from StructureV1 (#265). Range 0–1 (relative strength). |

### 2.3 Automatic Result Rules

- Automatic result is **never deleted or invisibly replaced** by an override.
- Both section role and boundary event automatic results are tracked **separately**.
- Scores are optional; absent scores mean "not defined for this result", not "low confidence".
- The `evidence_completeness` signal from #239 accounts for missing/failed/weak/contradictory inputs.

---

## 3. Manual Override

An **explicit user correction** applied to a section role or boundary event.

### 3.1 Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `role` | `intro` \| `groove` \| `build` \| `drop` \| `breakdown` \| `outro` \| `unknown` \| `null` | **No** | User-specified section role override. Optional if overriding only event. |
| `event` | `drop_onset` \| `null` | **No** | User-specified boundary event override. Optional if overriding only role. |
| `author` | string \| `null` | **No** | Override author identifier. Nullable when not reliably available. |
| `timestamp_utc` | ISO 8601 \| `null` | **No** | Override timestamp. Nullable when not reliably available. |
| `reason` | string \| `null` | **No** | User-provided reason/note. Nullable. |
| `source` | `"manual"` | **Yes** | Fixed value `"manual"` to distinguish from automatic analysis. |

### 3.2 Override Rules

1. **Layer independence:** Override applies to section role **OR** boundary event **OR** both, independently.
2. **Role ≠ Event:** Role override and event override are separate; they do not imply each other.
3. **Nullable metadata:** `author`, `timestamp_utc`, `reason` are nullable — no fake values generated when unavailable.
4. **Non-destructive:** Override does not modify or delete the automatic result; both coexist.
5. **`unknown` override valid:** An override with `role: "unknown"` is valid — user explicitly asserts insufficient evidence.

---

## 4. Effective Value Policy

The **effective value** is the derived view used for display, export, and downstream consumption.

### 4.1 Resolution Rules

```
if valid manual override exists for layer (role or event):
    effective = manual override
else:
    effective = automatic analysis
```

### 4.2 Principles

- Automatic analysis result is **always preserved** and queryable.
- Manual override is **always preserved** and queryable separately.
- Effective value is a **derived view**, not a destructive replacement.
- Role effective value and event effective value are computed **independently**.
- **Override removal:** Removing a manual override causes effective to fall back to automatic analysis automatically; **no re-analysis is triggered**.

### 4.3 Examples

#### Example A: Secure boundary + `unknown` role
```
Automatic:  role="unknown", status="unknown", event=null, event_status="unavailable"
Override:   none
Effective:  role="unknown", event=null
```
StructureV1 detected a strong neutral boundary, but Arrangement Map evidence is insufficient for any specific role. The role is correctly `unknown` with `evidence_completeness` explaining why. No dummy confidence.

#### Example B: Automatic `groove` + manual override to `build`
```
Automatic:  role="groove", status="available", event=null
Override:   role="build", author="user1", reason="Energy rise feels like build not groove"
Effective:  role="build"
```
User correction takes effect. Automatic `groove` remains preserved in history.

#### Example C: Automatic `drop` preserved, effective becomes manual `groove`
```
Automatic:  role="drop", status="available", event="drop_onset", event_status="available"
Override:   role="groove", author="user1", reason="Not peak energy, more sustained"
Effective:  role="groove", event="drop_onset"
```
Role override applies; event (`drop_onset`) remains from automatic analysis. Both layers independent.

#### Example D: `drop_onset` event separate from section role
```
Automatic:  role="drop", status="available", event="drop_onset", event_status="available"
Override:   event=null, reason="No sharp onset detected, gradual entry"
Effective:  role="drop", event=null
```
User suppresses the event while keeping the section role. Event and role overrides are independent.

#### Example E: Override removed → automatic becomes effective again
```
Automatic:  role="build", status="available"
Override:   (previously existed, now removed)
Effective:  role="build"
```
No re-analysis needed. Original automatic result resumes as effective.

---

## 5. Boundary vs Role Uncertainty (Strict Separation)

This contract enforces the architectural separation between **neutral boundary certainty** (StructureV1) and **arrangement role/event certainty** (Arrangement Map).

| Aspect | Neutral Boundary Layer (StructureV1) | Arrangement Role Layer (Arrangement Map) |
|--------|--------------------------------------|------------------------------------------|
| **Artifact** | `analysis.timeline.sections` | `arrangement.sections[]`, `arrangement.events[]` |
| **Status values** | `ok`, `partial`, `no_result`, `failed` | `available`, `uncertain`, `unknown`, `unavailable`, `failed` |
| **Quality metric** | `boundary_quality` (0–1 relative strength) | `role_score`, `event_score` (optional, defined semantics) |
| **Emits** | Neutral section ranges, bar-synchronous | Section roles + boundary events from #238 vocab |
| **Must not emit** | Roles, events | New boundary positions, stem/CLAP as ground truth |

### Separation Rules

1. StructureV1 **never** emits roles or events.
2. Arrangement Map **never** moves neutral boundaries.
3. `drop_onset` references a neutral boundary position; it does not create one.
4. A `drop` section can exist without a `drop_onset` event (gradual entry).
5. A `drop_onset` event can exist without a following `drop` role if evidence is contradictory (event emits with `status: "partial"`).
6. **No single universal confidence field bridges both layers.**

---

## 6. Score / Confidence Policy

**No universal `confidence` field is defined or required.**

### Rules

1. **Numerical scores are optional** — only included when ALL semantics are explicitly defined (name, level, meaning, range, provenance, calibration, absent semantics).
2. **If score semantics cannot be defined reliably, omit the field entirely** — no placeholder values.
3. **Scores from different levels (boundary vs role vs event) are never combined** into a single value.
4. **Missing score never implies low confidence** — it means "not defined for this result".
5. The `evidence_completeness` signal from #239 accounts for missing/failed/weak/contradictory inputs **instead of inventing a confidence number**.

---

## 7. Machine-Readable Contract

The normative machine-readable contract is `arrangement_confidence_override_v1.json` (schema version `1.0.0`, document type `sample_brain.arrangement_confidence_override`).

It defines:
- Status model values and definitions
- Automatic result schema (with evidence, provenance, optional scores)
- Manual override schema (with nullable metadata)
- Effective value policy (with executable examples)
- Boundary vs role separation rules
- Score/confidence policy
- Versioning rules
- Acceptance mapping to issues #238, #239, #240, #265

---

## 8. Versioning

| Increment | Triggers |
|-----------|----------|
| **MAJOR** | Status model value changes; automatic result/override field structure changes; effective value policy logic changes; boundary/role separation rules changes |
| **MINOR** | Documentation clarifications; non-breaking JSON additions (new optional fields with defaults); additional examples |
| **PATCH** | Typo fixes; cross-reference corrections |

---

## 9. Acceptance Mapping (Issue #241)

| #241 Criterion | Covered By |
|----------------|------------|
| Status model defined | §1, JSON `status_model` |
| `unknown` first-class, no dummy confidence | §1.1, §1.2, §6, JSON `status_model.rules` |
| Automatic vs manual separated | §2, §3, JSON `automatic_result`, `manual_override` |
| Effective value policy | §4, JSON `effective_value_policy` |
| Boundary vs role uncertainty separated | §5, JSON `boundary_vs_role_uncertainty` |
| No universal confidence invented | §6, JSON `score_confidence_policy` |
| Machine-readable contract + tests | This JSON + `test_arrangement_confidence_override_v1.py` |
| Compatible with #238/#239/#240/#265 | Cross-references in header; field enums matching #238 vocabulary |

---

## 10. Related Documents

| Document | Role |
|----------|------|
| `arrangement_confidence_override_v1.json` | Machine-readable contract (normative for tests) |
| `ARRANGEMENT_ROLE_VOCABULARY_V1.md` | Role/event vocabulary (§2, §3) |
| `ARRANGEMENT_SIGNAL_MATRIX_V1.md` | Signal definitions and evidence accounting |
| `TRACK_MAP_V1.md` | Neutral Track Map contract (boundary layer) |
| `STRUCTURE_V1.md` | Neutral boundary backend contract |
| Issue #228 | Meta: Musical Structure & Techno Arrangement |
| Issue #238 | Role vocabulary |
| Issue #239 | Signal matrix |
| Issue #240 | Heuristic classifier (consumes this contract) |
| Issue #265 | StructureV1 (boundary layer) |

---

## 11. Non-Goals (v1)

- No classification rules, thresholds, or weights (belongs to #240)
- No boundary detection (belongs to #265)
- No CLAP, stem, or All-In-One label requirements
- No genre sub-typing
- No `transition` section role
- No invented universal confidence scores
- No UI implementation
- No asset generation