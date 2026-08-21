# Harmonic & Rhythmic Matching — Product Spec

**Issue:** [#91](https://github.com/jannekbuengener/sample-brain/issues/91)  
**Parent:** [#90](https://github.com/jannekbuengener/sample-brain/issues/90)  
**Depends on:** [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md) (#94)  
**Status:** Fit v1 runtime via `src/matching.py`; advanced harmony/profile extensions remain follow-up scope

This document defines how Sample Brain scores **musical fit** between catalog samples and a target context (track BPM, key, desired type). It does not perform audio analysis or variant rendering.

---

## 1. Purpose

Producers need samples that **fit the current musical context** — tempo, tonality, and role (kick, pad, loop, etc.). The Matching pillar consumes Library Intelligence outputs and produces ranked fit results with explainable reasons.

---

## 2. Inputs and outputs

### 2.1 Inputs

| Input | Source pillar | Required |
|-------|---------------|----------|
| Sample BPM | Library (`features.bpm`) | for BPM scoring |
| Sample key | Library (`features.key`) | optional |
| Sample type | Library (`features.pred_type`) | optional |
| Target BPM | Context / user / CLI | **required** |
| Target key | Context / user / CLI | optional |
| Desired type | Context / user / CLI | optional |

Future: groove character, loop length — **not on `main`**.

### 2.2 Outputs

| Output | Description |
|--------|-------------|
| Ranked match list | Samples ordered by fit |
| Per-dimension breakdown | BPM, key, type plus fail-closed groove status; score, status, weight, active flag, reason, source ref |
| `total_score` | Weighted aggregate over active dimensions only, clamped to `[0, 1]` |
| `reasons` | Human-readable explanation strings |
| `bpm_relation` | `direct`, `half_time`, `double_time`, or `no_result` |
| `tempo_multiplier` | Musical BPM interpretation (`1.0`, `2.0`, `0.5`), not a DSP playback-rate instruction |
| `semitone_hint` | Smallest deterministic pitch-class shift in `-5..+6`; tritone tie is `+6` |
| Groove status | `no_result` with `GROOVE_EVIDENCE_UNAVAILABLE` until canonical groove evidence exists |
| Fit-score weights | Fixed v1 weights: BPM `0.5`, key `0.3`, type `0.2` |

---

## 3. Shipped runtime (`src/matching.py`)

CLI: `sample-brain match --target-bpm <bpm> [--target-key <key>] [--desired-type <type>] [--limit <n>]`

### 3.1 `MatchProfile`

| Field | Default | Notes |
|-------|---------|-------|
| `target_bpm` | required | Must be finite and > 0 |
| `target_key` | None | Optional filter dimension |
| `desired_type` | None | Case-insensitive exact match on `pred_type` |
| `limit` | 10 | Top-N results |
| `bpm_tolerance` | 8.0 | Linear decay window (BPM units) |

### 3.2 Scoring functions (Fit v1)

**BPM (`score_bpm_match`):**

- Direct tempo: linear decay within `bpm_tolerance`.
- Half-time fit: `sample_bpm * 2` vs target, score × `HALF_DOUBLE_PENALTY` (0.9).
- Double-time fit: `sample_bpm / 2` vs target, score × 0.9.
- Best positive path wins and is exposed as structured `bpm_relation` plus `tempo_multiplier`.
- `tempo_multiplier` describes the musical interpretation of source BPM, not a DSP playback-rate instruction.
- Missing/invalid BPM is `no_result` and does not enter the aggregate denominator.

**Key (`score_key_match`):**

- Reuses `src.key_signature.parse_key_signature` and `key_distance_semitones`; `matching.py` owns no second parser.
- Same root remains the cautious v1 compatibility rule; known major/minor mismatch scores 0.
- `semitone_hint` is the smallest signed pitch-class shift in `-5..+6`, with tritone deterministically `+6`.
- Missing/unparseable keys and known major/minor mismatch produce no semitone hint.
- **No** Camelot, relative key, or circle-of-fifths compatibility is activated.

**Type (`score_type_match`):**

- Exact case-insensitive match on `pred_type` vs `desired_type`.

**Groove:**

- No Library/DB schema is added in v1. Without canonical groove evidence the dimension is `no_result`, inactive, and carries `GROOVE_EVIDENCE_UNAVAILABLE`.

**Total score:**

- Fixed weights remain BPM 0.5, key 0.3, type 0.2.
- Only dimensions with usable candidate evidence are active and participate in the denominator; missing/invalid dimensions do not silently penalize the candidate.
- Each dimension exposes score/status/weight/active/reason/source-ref so the aggregate remains explainable.

### 3.3 Data loading

`load_match_candidates()` joins `samples` ⋈ `features` (analyzed samples only).

---

## 4. Gap matrix — issue scope vs `main`

| #91 scope item | Spec status | Runtime (`matching.py`) | Gap |
|----------------|-------------|-------------------------|-----|
| Key compatibility | Defined | Canonical parser reuse; cautious same-root/mode behavior | No relative key / Camelot / open-key rules by design |
| BPM compatibility | Defined | Linear decay + tolerance | ✅ v1 |
| Half-/double-time detection | Defined | Structured relation + musical tempo multiplier | ✅ v1 |
| Semitone suggestions | Defined | Deterministic `-5..+6`; fail-closed on mode mismatch | ✅ v1 |
| Groove / loop-length fit | Defined | Explicit `no_result`, excluded from score | Blocked on canonical groove evidence |
| Harmony rules (Camelot, etc.) | Candidates only | Not activated | Evidence/research required before productization |
| Fit-score contract | v1 fixed weights | Per-dimension status/weight/active/source + bounded aggregate | Configurable profiles remain follow-up |
| Fit-to-track **and** fit-to-sample | Required | fit-to-track via `MatchProfile` | fit-to-sample (reference sample as context) remains follow-up |
| Explainability | Required | `reasons` + structured dimension breakdown + hints | ✅ v1 |

---

## 5. Target matching contract (not shipped)

### 5.1 Key compatibility levels (target)

| Level | Rule | Example |
|-------|------|---------|
| Exact | Same root + mode | `Cmaj` + `Cmaj` |
| Relative | Relative major/minor | `Am` fits `Cmaj` |
| Dominant / fifth | Circle-of-fifths neighbours | TBD weights |
| Camelot / Open Key | DJ notation mapping | Optional profile backend |

Harmony rule set is **configurable per profile** — no default until evidence-backed.

### 5.2 Groove and loop-length (target)

Requires Library extensions (groove descriptor, bar count). Matching consumes:

- Loop duration vs target bar length at context BPM.
- Onset density / swing proxy from Library analysis.

**Status:** not in `features` table today.

### 5.3 Fit-score API (target)

```text
total_score = Σ (weight_i × score_i) / Σ weight_i   for active dimensions i
```

- Weights from profile YAML.
- Scores in [0, 1] per dimension.
- `reasons` and optional `hints[]` (semitone, half/double BPM).

### 5.4 Fit-to-sample mode (target)

Use a reference `sample_id` as context: copy its BPM/key/type as implicit targets. Enables “find compatible layers for this loop.”

---

## 6. Boundaries

| Matching pillar | Not matching |
|-----------------|--------------|
| Score catalog samples vs target profile | Extract features from audio |
| Rank and explain fit | Build track profile from host |
| Suggest transposition/tempo fit | Render pitch/time variants |
| Consume `features.*` | Write FL Browser tags |

---

## 7. Follow-up runtime slices

| Slice | Scope |
|-------|-------|
| Configurable match weights | Profile keys + `MatchProfile` |
| Relative key scoring | Extend `score_key_match` only after evidence-backed rule selection |
| `--reference-sample` CLI | Fit-to-sample mode |
| Groove/loop-length dimension | Blocked on canonical Library groove/bar evidence |
| Plugin integration | Workspace pillar consumes the Fit v1 API |

---

## 8. Acceptance mapping (Issue #91)

| Acceptance criterion | This spec |
|----------------------|-----------|
| Matching pillar clearly separated from analysis | §6 |
| Inputs and outputs named | §2 |
| Fit-to-track and fit-to-sample considered | §2.1, §5.4 |
| Implementation remains follow-up | §4, §7 |

---

## 9. Workbench Harmonie-Finder (issue #213, shipped UI)

A second `ttk.Notebook` page in the Workbench (`src/workbench_harmony.py`, `find_harmony_matches`) finds **musically related already-loaded `WorkbenchRow`s** against a chosen reference. It is a local, similarity-style convenience feature — **not** the configurable target matching contract from §5.

- Reuses the canonical key parser `src/key_signature.py` (`parse_key_signature`, `format_key_signature`).
- Relation groups: **Direkt** (same root + known mode), **Verwandt** (relative major/minor, or fifth/fourth with same mode — both modes known), **Transpose** (±3 semitones, both modes known), **Unsicher** (missing/unknown mode).
- Unknown mode stays cautious: same root with one or both modes unknown is **Unsicher**, never Direkt. No relative/fifth/fourth claim without both modes known.
- Pitch-shift hint limited to `-3..+3` semitones, shown only when a defined harmony relationship exists. No rendering.
- Scoring: `total_score = 0.75 * harmony + 0.25 * BPM`, reusing `src/matching.py` BPM scoring. Reference excluded from results; in-memory key override only (never mutates row/DB).
- Similar-V1 (`src/matching.py` / `compute_workbench_similar_suggestions`) is unchanged.

## 10. References

- `src/matching.py`, `tests/test_matching.py`, CLI `match` in `src/cli.py`
- [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md)
- `docs/PRODUCT_REQUIREMENTS.md` §5.2 (basis matching in product MVP)
