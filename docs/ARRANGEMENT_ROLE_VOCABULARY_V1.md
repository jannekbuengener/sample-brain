# Arrangement Role Vocabulary v1

**Issue:** #238
**Parent:** #228
**Consumes:** #239 (Arrangement Signal Matrix v1), #232 (Track Map v1), #265 (StructureV1)
**Machine-readable contract:** `arrangement_role_vocabulary_v1.json`
**Schema version:** 1.0.0
**Document type:** `sample_brain.arrangement_role_vocabulary`

---

This document defines the canonical v1 vocabulary for Techno arrangement roles and events. It is the authoritative reference for #241 (confidence/override contract) and #240 (heuristic classifier). It does not implement classification rules, thresholds, or boundary detection.

---

## 1. Layer Separation (Binding)

| Layer | Document | Emits | Must not emit |
|-------|----------|-------|---------------|
| **Neutral boundary layer** | StructureV1 (#265) | Neutral `analysis.timeline.sections` (bar-synchronous, no roles) | Any arrangement role or event label |
| **Arrangement role layer** | Arrangement Map (#240) | Section roles + boundary events from this vocabulary | New boundary positions, stem/CLAP labels as ground truth |
| **Confidence/override layer** | #241 | Status, evidence accounting, manual overrides | Invented confidence, silent history overwrite |

**Boundary confidence and role confidence stay separate.** A strong neutral boundary can still have role `unknown`; a strong role hint must not create a boundary.

---

## 2. Section Roles (Core Vocabulary)

Exactly seven section roles. No genre sub-types. No additional roles without a separate canonical decision.

| Role | Canonical Name | Musical Function | Typical Track Position | Positive Signals (from #239) | Negative Signals (from #239) | Typical Confusions / Ambiguity | Allowed Neighbor Roles | Must Not Derive From Name |
|------|----------------|------------------|------------------------|-------------------------------|------------------------------|--------------------------------|------------------------|---------------------------|
| **intro** | `intro` | Track opening, establishing groove elements gradually | Early (first 1–4 sections) | `relative_track_position`, `multi_bar_trend` (rising energy/onsets), optional `semantic_role_hint` | `bar_energy_rms`, `low_end_share`, `onset_density`, `stem_drum_activity`, `stem_bass_activity`, low `evidence_completeness` | Can resemble a short `build` or sparse `groove` | `groove`, `build`, `unknown` | "Intro" ≠ always first section; not all first sections are `intro` |
| **groove** | `groove` | Stable, repeating main rhythmic/low-end section (core dancefloor material) | Middle (often longest span) | `bar_energy_rms`, `low_end_share`, `onset_density`, `rhythm_stability`, `self_similarity`, `recurrence`, optional stem activity, optional `semantic_role_hint` | `relative_track_position` (extremes), `bar_loudness_delta`, `timbre_delta`, `spectral_delta`, `novelty`, `neighbor_delta`, `multi_bar_trend`, low `evidence_completeness` | Can be confused with `drop` if energy is high; with `build` if stability is not yet established | `intro`, `build`, `drop`, `breakdown`, `outro`, `unknown` | "Groove" ≠ only 4/4; not all stable sections are `groove` |
| **build** | `build` | Rising tension, increasing energy/onset density/spectral brightness toward a drop | Pre-drop (often 1–4 bars before `drop`) | `bar_loudness_delta`, `onset_density`, `timbre_delta`, `spectral_delta`, `neighbor_delta`, `multi_bar_trend` (rising), optional `semantic_role_hint` | `relative_track_position` (late track), stable `rhythm_stability`, `self_similarity`, `recurrence`, low `evidence_completeness` | Can resemble late `intro` or early `drop` if transition is sharp | `intro`, `groove`, `drop`, `unknown` | "Build" ≠ always 8/16 bars; not all rising sections are `build` |
| **drop** | `drop` | High-energy climax, full low-end + rhythmic density, functional peak | After `build`, often repeated | `bar_energy_rms`, `bar_loudness_delta`, `low_end_share`, `onset_density`, `rhythm_stability`, `spectral_delta`, `self_similarity`, `recurrence`, optional stem activity, optional `semantic_role_hint` | `relative_track_position` (very early/late), `multi_bar_trend`, low `evidence_completeness` | Can resemble high-energy `groove`; boundary with following `breakdown`/`groove` can be ambiguous | `build`, `groove`, `breakdown`, `outro`, `unknown` | "Drop" ≠ single event; `drop_onset` is the entry event, `drop` is the section |
| **breakdown** | `breakdown` | Reduced energy, textural/timbral focus, rhythmic suspension | Post-drop or mid-track contrast | `timbre_delta`, `novelty`, `neighbor_delta`, optional `semantic_role_hint` | `relative_track_position` (extremes), `bar_energy_rms`, `bar_loudness_delta`, `low_end_share`, `onset_density`, `rhythm_stability`, `self_similarity`, `recurrence`, optional stem activity, low `evidence_completeness` | Can resemble sparse `intro` or `outro`; timbral shift without energy drop is ambiguous | `drop`, `groove`, `build`, `outro`, `unknown` | "Breakdown" ≠ always quiet; not all low-energy sections are `breakdown` |
| **outro** | `outro` | Track closing, energy/element reduction toward end | Late (last 1–4 sections) | `relative_track_position`, `neighbor_delta` (falling), `multi_bar_trend` (falling energy/onsets), optional `semantic_role_hint` | `bar_energy_rms`, `bar_loudness_delta`, `onset_density`, `rhythm_stability`, `spectral_delta`, optional `stem_bass_activity`, low `evidence_completeness` | Can resemble late `breakdown` or fading `groove` | `breakdown`, `groove`, `unknown` | "Outro" ≠ always final section; not all final sections are `outro` |
| **unknown** | `unknown` | **Valid, normal result** — evidence is missing, weak, contradictory, or outside vocabulary | Any position | `evidence_completeness` showing missing/failed/weak/contradictory inputs | (none — it is the absence of positive evidence) | Default when no role reaches sufficient evidence; not an error | All roles | "Unknown" ≠ failure; not a placeholder for "could not decide"; no dummy confidence needed |

---

## 3. Boundary Events (Separate from Section Roles)

| Event | Canonical Name | Definition | Musical Meaning | Positive Signals | Negative Signals | Relation to Section Roles |
|-------|----------------|------------|-----------------|------------------|------------------|---------------------------|
| **drop_onset** | `drop_onset` | Entry into a `drop` section at a specific neutral boundary | The moment the drop "hits" — sharp energy/timbre/spectral rise | `bar_loudness_delta`, `timbre_delta`, `spectral_delta`, `novelty`, `neighbor_delta` | `self_similarity`, `recurrence`, low `evidence_completeness` | **Not a section role.** Emitted at a boundary *between* sections. The section *after* this boundary is `drop`. A `drop` section can exist without a detected `drop_onset` (e.g., gradual entry). |

**No other events in v1.** Additional events (e.g., `breakdown_onset`, `build_onset`) are deferred until a canonical need is established.

---

## 4. Transition Decision (Explicit)

**`transition` is NOT a core section role in v1.**

- **Reason:** "Transition" is a relational property between two sections (e.g., `build→drop`, `drop→breakdown`), not a standalone functional section with a stable musical definition in Techno. Its duration, signal profile, and boundaries are inconsistent across tracks.
- **Modeling:** Transition character is captured by:
  - Boundary events (`drop_onset` at `build→drop`)
  - Neighbor deltas and novelty at boundaries (from #239)
  - Role sequence in the Arrangement Map (e.g., `build` followed by `drop`)
- **Future:** If a later pilot (#242) reveals a consistent, classifiable "transition section" with distinct signals, it may be added in v2 with a new schema version.

---

## 5. Unknown Policy (Fully Defined)

`unknown` is a **first-class, normal result** — not an error, not a fallback, not a "low confidence" placeholder.

| Condition | Outcome |
|-----------|---------|
| Evidence is missing (signals `not_run`/`failed`/`no_result`) | `unknown` |
| Evidence is contradictory (positive and negative signals for multiple roles) | `unknown` |
| Evidence is weak (no role reaches track-relative threshold) | `unknown` |
| Section falls outside the seven-role vocabulary | `unknown` |
| Manual override applies (per #241) | Override role (with history preserved) |

**No dummy confidence value is ever invented for `unknown`.** The Arrangement Map emits `role: "unknown"` with `evidence_completeness` accounting for why.

---

## 6. Three-Layer Boundary/Role/Event Separation (Explicit)

| Layer | Artifact | Example | Source |
|-------|----------|---------|--------|
| **1. Neutral boundary** | StructureV1 section boundary at bar 32 | `analysis.timeline.sections.items[2] = {id: "section_3", start_sec: 64.0, end_sec: 96.0}` | #265 |
| **2. Section role** | Arrangement Map assigns `drop` to that section | `arrangement.sections[2].role = "drop"` | #240 |
| **3. Boundary event** | Arrangement Map emits `drop_onset` at the *start* of that section | `arrangement.events[] = {type: "drop_onset", boundary_sec: 64.0, role_after: "drop"}` | #240 |

**Rules:**
- StructureV1 (#265) **never** emits roles or events.
- Arrangement Map (#240) **never** moves neutral boundaries.
- `drop_onset` references a neutral boundary position; it does not create one.
- A `drop` section can exist without a `drop_onset` event (gradual entry).
- A `drop_onset` event can exist without a following `drop` role if evidence is contradictory (event emits with `status: "partial"`).

---

## 7. Signal Reference (from #239)

Roles and events reference measurable, bar-synchronous signals defined in the Arrangement Signal Matrix v1 (#239). This vocabulary does not define thresholds, weights, or classification logic — only which signals semantically support or argue against each role/event.

| Role/Event | Primary Positive Signal Groups | Primary Negative Signal Groups |
|------------|--------------------------------|--------------------------------|
| `intro` | `beat_downbeat_reference` (position), `multi_bar_trends` | `energy_loudness`, `low_end`, `onsets`, `drum_bass_activity`, `missing_data` |
| `groove` | `energy_loudness`, `low_end`, `onsets`, `rhythmic_stability`, `self_similarity`, `recurrence` | `beat_downbeat_reference` (extremes), `energy_loudness` (delta), `timbre_changes`, `spectral_changes`, `novelty`, `before_after_differences`, `multi_bar_trends`, `missing_data` |
| `build` | `energy_loudness` (delta), `onsets`, `timbre_changes`, `spectral_changes`, `before_after_differences`, `multi_bar_trends` | `beat_downbeat_reference` (late), `rhythmic_stability`, `self_similarity`, `recurrence`, `missing_data` |
| `drop` | `energy_loudness`, `energy_loudness` (delta), `low_end`, `onsets`, `rhythmic_stability`, `spectral_changes`, `self_similarity`, `recurrence` | `beat_downbeat_reference` (extremes), `multi_bar_trends`, `missing_data` |
| `breakdown` | `timbre_changes`, `novelty`, `before_after_differences` | `beat_downbeat_reference` (extremes), `energy_loudness`, `energy_loudness` (delta), `low_end`, `onsets`, `rhythmic_stability`, `self_similarity`, `recurrence`, `drum_bass_activity`, `missing_data` |
| `outro` | `beat_downbeat_reference` (position), `before_after_differences`, `multi_bar_trends` | `energy_loudness`, `energy_loudness` (delta), `onsets`, `rhythmic_stability`, `spectral_changes`, `drum_bass_activity`, `missing_data` |
| `unknown` | `missing_data` | `semantic_optional` |
| `drop_onset` | `energy_loudness` (delta), `timbre_changes`, `spectral_changes`, `novelty`, `before_after_differences` | `self_similarity`, `recurrence`, `missing_data` |

**No universal Techno thresholds.** All signals are track-relative (percentiles, median/MAD z-scores, local deltas, relative shares, rolling trends).

---

## 8. Non-Goals (v1)

- No classification rules, thresholds, or weights
- No boundary detection (belongs to #265)
- No CLAP, stem, or All-In-One label requirements
- No genre sub-typing (e.g., "minimal_drop", "hard_groove")
- No `transition` section role
- No invented confidence scores
- No asset generation

---

## 9. Acceptance Mapping (Issue #238)

| #238 Criterion | Covered By |
|----------------|------------|
| Role vocabulary v1 documented | Sections 2, 3, 4, 5 |
| Section roles and boundary events separated | Sections 2, 3, 6 |
| `drop` and `drop_onset` clearly distinguished | Sections 2, 3, 6 |
| `unknown` fully defined | Section 5 |
| `transition` decision explicit, not silently enforced | Section 4 |
| Contract usable for #239/#240 | Sections 2, 3, 6, 7; machine-readable JSON |

---

## 10. Related Documents

| Document | Role |
|----------|------|
| `arrangement_role_vocabulary_v1.json` | Machine-readable contract (normative for tests) |
| `ARRANGEMENT_SIGNAL_MATRIX_V1.md` | Signal definitions and role-signal mapping |
| `TRACK_MAP_V1.md` | Neutral Track Map contract (boundary layer) |
| `STRUCTURE_V1.md` | Neutral boundary backend contract |
| Issue #228 | Meta: Musical Structure & Techno Arrangement |
| Issue #239 | Track Map signals for arrangement roles |
| Issue #241 | Confidence and manual override contract |
| Issue #240 | Heuristic classifier implementation |

---

## 11. Versioning

- **Schema version:** `1.0.0` (this document and JSON)
- **Document type:** `sample_brain.arrangement_role_vocabulary`
- **MAJOR** increment: role vocabulary changes (add/remove/rename roles or events)
- **MINOR** increment: documentation clarifications, signal reference updates, non-breaking JSON additions
- **PATCH** increment: typo fixes, cross-reference corrections

The JSON contract is the normative machine-readable source. This Markdown is the human-readable companion.