# AQ6 Harmonic Match Theory Truth Table + KPI Contract

**Status:** ACTIVE_SUPPORTING — theory correctness freeze for [#1015](https://github.com/jannekbuengener/sample-brain/issues/1015)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#948](https://github.com/jannekbuengener/sample-brain/issues/948) (AQ6), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED — consume, do not reopen):** [#943](https://github.com/jannekbuengener/sample-brain/issues/943) / AQ1 tempo claimability; [#944](https://github.com/jannekbuengener/sample-brain/issues/944) / AQ2 key/mode claimability  
**Product theory authority:** `docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md` §9 + live `src/workbench_harmony.py`  
**Executable regression surface:** `src/aq6_harmonic_theory_truth_table.py` + `tests/fixtures/aq6_harmonic_theory/truth_table_v1.json`  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) portable tokens; [#959](https://github.com/jannekbuengener/sample-brain/issues/959) semantic determinism. Ranking relevance freeze: [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016) / `docs/benchmarks/AQ6_HARMONIC_MATCH_RANKING_RELEVANCE_CONTRACT.md` (separate plane). Preference remains later.

## Architecture outcome

```text
AQ6_THEORY_TRUTH_TABLE_CONTRACT_FROZEN
```

This document freezes the **deterministic music-theory correctness plane** for Harmonic Match: exhaustive golden relations, pitch-shift suggestion semantics, fail-closed missing-evidence behavior, and theory KPIs. It does **not** authorize ranking-weight changes, UI/QML work, key/BPM detector changes, embeddings/ML, or human preference scoring.

Plane rule (normative):

```text
theoretical compatibility ≠ audio/statistical similarity ≠ subjective preference
```

No global “Harmonic Match quality” score may replace the theory metrics below. Ranking metrics live on a separate plane and must not rewrite theory truth.

## Ownership

| Concern | Owner |
|---|---|
| Theory relation vocabulary + exhaustive golden cells | this contract + executable truth table |
| Product Harmonic Match runtime | `src/workbench_harmony.py` (`determine_relation` / `rate_harmony` / `find_harmony_matches`) |
| Key string parse / root / mode normalization | `src/key_signature.py` (cite; do not redefine) |
| Upstream key/mode claimability evidence | AQ2 (#944) — consume eligibility/uncertainty; do not re-analyze |
| Upstream BPM / secondary score evidence | AQ1 (#943) — ranking-adjacent only; out of theory plane |
| Ranking relevance grades / Precision@K / NDCG | [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016) — separate plane; do not override theory |
| Ranking weights (0.75 / 0.25) / preference | later AQ6 slices — not this freeze |
| Portable domain tokens + eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Semantic determinism | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| Promotion thresholds / production semantic switch | future evidence-backed decision issues only |

## Non-goals

- no ranking-weight / 0.75 harmony / 0.25 BPM tuning
- no UI / QML changes
- no key / BPM / mode detector algorithm changes
- no embeddings / ML
- no human preference study
- no production semantic change beyond making the truth table executable for regression
- no default invented key or mode when evidence is missing
- no private audio / absolute host paths in committed artifacts
- no single opaque score mixing theory + ranking + preference

## Named identities

| Field | Value |
|---|---|
| `truth_table_id` | `sample-brain.aq6.harmonic-theory.truth-table.v1` |
| `document_type` | `sample-brain.aq6.harmonic-theory-kpi.v1` |
| `truth_table_version` | `1.0.0` |
| Supported modes | `maj`, `min` only |
| Supported roots | 12 sharp-normalized chromatic roots: `C C# D D# E F F# G G# A A# B` |
| Relation vocabulary | `direct`, `related`, `transpose`, `uncertain` (product enum values) |

## Domain tokens (#956)

| Token | Scope |
|---|---|
| `aq6.theory` | Deterministic music-theory relation / compatibility / pitch-shift correctness against the frozen truth table |
| `aq6.ranking` | Ranking-quality grades/KPIs — activated by [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016); **not** this theory freeze |
| `aq6.preference` | Reserved for later human preference slices — **not activated** by this freeze |

Do not invent an `aq6.quality` aggregate that collapses these planes.

## Shared KPI vocabulary (#942) — AQ6 theory selection

| #942 dimension | AQ6 theory (`aq6.theory`) |
|---|---|
| correctness | selected (relation classification accuracy; pitch-shift suggestion correctness) |
| coverage / abstention | selected (`UNCERTAIN` / fail-closed missing evidence is valid, not an automatic error) |
| error buckets / confusion | selected (incompatible FP; compatible FN; evidence-state buckets) |
| baseline-vs-candidate delta | methodology reserved for later relation-rule candidates; no thresholds here |
| robustness / metamorphic | selected (transposition invariance over all 12 roots) |
| determinism / reproducibility | consume #959 by reference; truth table generation must be bit-stable |
| runtime median/p95 | out of scope for theory plane |
| calibration | **HOLD / out of scope** (relations are discrete labels, not probabilities) |
| slice metrics | selected (by relation; by evidence_state; by compatibility) |

## Separation rule (normative)

1. Theory correctness is evaluated **only** against known/uncertain/missing **upstream key+mode evidence** — AQ6 does **not** re-detect key, mode, or BPM.
2. A high ranking score must **never** override an incompatible or uncertain theory cell.
3. `UNCERTAIN` is a valid theory outcome. It is not automatically a false negative.
4. Missing key, missing mode, unparseable key, or ineligible upstream claim → fail-closed: relation `uncertain`, compatibility `uncertain`, **no** default `maj`/`min`, **no** forced match.
5. BPM may participate in later ranking evaluation; it is **not** a theory-plane input.
6. No global Harmonic Match score may replace the theory KPI set.

## Upstream evidence feed (AQ1 / AQ2) — consume only

| Upstream state | Theory-plane behavior |
|---|---|
| Modeful eligible key (AQ2 claim or legacy modeful `row.key`) | Evaluable against truth table |
| Root-only key (`"G"`) / mode missing | `evidence_state=missing_mode` → `uncertain` / fail-closed |
| Missing / unparseable key | `evidence_state=missing_key` → `uncertain` / fail-closed |
| Invalid / ineligible V2 claim without modeful fallback | treated as insufficient evidence → `uncertain` |
| AQ1 BPM known/unknown | ignored on theory plane (ranking-adjacent only) |

AQ6 never invents a key or mode to force a `direct` / `related` / `transpose` label.

## Frozen relation rules (product-aligned)

Authority: `docs/product/02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md` §9 and live `determine_relation` / `_minimal_signed_shift`. This freeze captures **current** product semantics as regression truth until a separate evidence-backed production change.

Both source and target must be **modeful** (`maj`|`min`) for any non-`uncertain` relation.

| Relation | Rule | Compatibility |
|---|---|---|
| `direct` | Same enharmonic root **and** same known mode | `compatible` |
| `related` | Relative major/minor (opposite modes, minimal root distance = 3) **or** same-mode perfect fifth/fourth (signed root distance ∈ `{7,-5,5,-7}`) | `compatible` |
| `transpose` | Both modes known; not direct/related; minimal absolute root distance ∈ `{1,2,3}` | `compatible` |
| `uncertain` | Missing/unparseable key, missing mode, **or** modeful pair with no direct/related/transpose rule | see compatibility below |

### Compatibility overlay (theory KPI layer)

Product runtime still exposes only the four relation labels. For theory KPIs we additionally freeze:

| `compatibility` | When |
|---|---|
| `compatible` | relation ∈ `{direct, related, transpose}` |
| `incompatible` | both sides modeful **and** relation = `uncertain` (known keys, no allowed relation) |
| `uncertain` | any missing/insufficient evidence path (missing key, missing mode, unparseable) |

`UNCERTAIN` therefore splits into evidence-uncertain vs known-incompatible for metrics — without changing the runtime relation enum.

### Pitch-shift suggestion

| Relation | `pitch_shift_semitones` |
|---|---|
| `transpose` | Minimal signed chromatic distance from **reference root → candidate root**, range `-3..+3` (product `_minimal_signed_shift`, clamped) |
| `direct` / `related` / `uncertain` | `null` (no pitch-shift suggestion on theory/product path) |

Sign convention is product-aligned: distance is measured from reference to candidate (e.g. `Cmaj`→`Dmaj` = `+2`). Aligning candidate toward reference is the arithmetic negation; metrics score the **reported suggestion**, not a second convention.

### Symmetry / asymmetry (explicit)

| Property | Rule |
|---|---|
| Relation symmetry | For modeful pairs, `relation(A,B) == relation(B,A)` under this freeze |
| Pitch-shift antisymmetry | When both directions are `transpose`, `shift(A,B) == -shift(B,A)` |
| Evidence uncertainty | Missing-evidence cells are not required to be musically symmetric; they remain fail-closed `uncertain` |

## Exhaustive truth table

Identity: `sample-brain.aq6.harmonic-theory.truth-table.v1`

Machine-readable fixture: `tests/fixtures/aq6_harmonic_theory/truth_table_v1.json`  
Generator / KPI helpers: `src/aq6_harmonic_theory_truth_table.py`

### Cell coverage

1. **Modeful grid:** all ordered pairs of `(root × {maj,min}) × (root × {maj,min})` → `12 × 2 × 12 × 2 = 576` cells.
2. **Fail-closed evidence cells** (representative but required): missing source key, missing target key, root-only / missing mode on either side, unparseable key — each with expected `relation=uncertain`, `compatibility=uncertain`, `pitch_shift_semitones=null`.

Each cell records at least:

| Field | Meaning |
|---|---|
| `source_root` / `source_mode` | Reference key parts (`mode` may be `null`) |
| `target_root` / `target_mode` | Candidate key parts |
| `source_key` / `target_key` | Canonical strings (`Cmaj`, `C`, or `null`) |
| `relation` | `direct` \| `related` \| `transpose` \| `uncertain` |
| `compatibility` | `compatible` \| `incompatible` \| `uncertain` |
| `evidence_state` | `modeful` \| `missing_key` \| `missing_mode` \| `unparseable` |
| `pitch_shift_semitones` | `int` or `null` |
| `relation_symmetric_with_swap` | expected boolean for modeful pairs |
| `pitch_shift_antisymmetric_with_swap` | expected boolean when both sides transpose |

### Transposition invariance

For any modeful cell, shifting **both** roots by the same \(k \in \{0..11\}\) semitones (mod 12, sharp-normalized) must preserve `relation`, `compatibility`, and `pitch_shift_semitones`. Violations are first-class KPI failures.

## Theory KPIs (`aq6.theory`) — definitions only (no global score)

Report each metric separately. Do **not** combine into one Harmonic Match score.

| Metric | Definition | Notes |
|---|---|---|
| Relation classification accuracy | Fraction of evaluable cells where predicted `relation` equals frozen expected `relation` | Primary correctness |
| Incompatible false-positive rate | Fraction of frozen `compatibility=incompatible` cells predicted as `compatible` | Must stay 0 on the frozen product path |
| Compatible false-negative rate | Fraction of frozen `compatibility=compatible` cells predicted as not `compatible` | Distinct from evidence-`uncertain` |
| Pitch-shift suggestion correctness | Fraction of **`transpose` cells only** where predicted signed shift equals frozen shift | Sign + magnitude; non-transpose must still predict `null` (tracked separately as null-shift failures, not folded into this denominator) |
| Transposition invariance violations | Count/rate of modeful cells that change relation/compatibility/shift under simultaneous +k root rotation | Must be 0 |
| Evidence fail-closed rate | Fraction of missing/insufficient evidence cells that remain `uncertain`/`uncertain` with `null` shift | Forced matches are failures |

`UNCERTAIN` on evidence paths is **valid**. Count it as error only when the freeze requires a different label.

## Partition / determinism policy

| Role | Policy |
|---|---|
| Theory truth table | Single frozen identity `…truth-table.v1`; not a CALIBRATION/TEST audio split |
| Regeneration | Generator must reproduce the committed fixture byte-identically (stable key ordering) |
| Ranking / preference corpora | Later slices; must not mutate this table to improve ranking metrics |
| Private libraries | Reality check only; never rewrite public theory cells |

## Exit criteria (#1015)

- [x] Exhaustive 12-root × supported-modes truth table is versioned and testable
- [x] Unknown/missing evidence behavior is explicit and fail-closed
- [x] Transposition invariance and pitch-shift semantics are frozen
- [x] Theory metrics cannot be replaced by a ranking score
- [x] Current product relation vocabulary remains authoritative until a separate production change

```text
AQ6_THEORY_TRUTH_TABLE_CONTRACT_FROZEN
```

## Follow-on write-heads (out of scope here)

- [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016) — ranking KPI / relevance contract (separate plane) — **CLOSED / FROZEN**  
- [#1017](https://github.com/jannekbuengener/sample-brain/issues/1017) — measure current theory correctness baseline — see [`AQ6_HARMONIC_MATCH_THEORY_BASELINE.md`](AQ6_HARMONIC_MATCH_THEORY_BASELINE.md)
- [#1018](https://github.com/jannekbuengener/sample-brain/issues/1018) — measure current ranking + upstream-error propagation baseline — see [`AQ6_HARMONIC_MATCH_RANKING_BASELINE.md`](AQ6_HARMONIC_MATCH_RANKING_BASELINE.md)
