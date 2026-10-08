# AQ7 Synthetic Structure / Role / Drop Ground-Truth Corpus

**Status:** ACTIVE_SUPPORTING — synthetic structure/role/drop GT contract freeze for [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024)
**Class:** ACTIVE_SUPPORTING
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)
**Depends on:** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) / `docs/benchmarks/AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md` (CLOSED / binding)
**Related:** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) portable `record_id` join; [#957](https://github.com/jannekbuengener/sample-brain/issues/957) perturbation mechanics
**Tooling:** follow-up of #1024 — not implemented in this docs-only freeze (`src/aq7_structure_role_drop_schema.py`, `src/aq7_structure_role_drop_corpus.py`)

## Architecture outcome

```text
AQ7_STRUCTURE_ROLE_DROP_CORPUS_FROZEN
```

This slice freezes the **named synthetic corpus identity, three-plane GT schema, fixture matrix, leakage policy, BeatGrid provenance, and artifact layout** so later #1024 generator/schema/tests can implement against a fixed contract. It does **not** change StructureV1 / ArrangementClassifier, invent human labels for private audio, implement the generator, or set promotion gates.

Binding KPI/annotation semantics remain owned by `AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md` (#1023). This corpus document **does not redefine**: plane identities, role vocabulary, boundary ownership, drop semantics, boundary tolerance, annotation status, CALIBRATION/TEST firewall, or BeatGrid/HOLD semantics. Those rules are consumed by reference.

## Corpus strategy

Fully **synthetic**.

- No committed public or private audio binaries.
- Audio is generated deterministically at runtime under an external/temp work directory (outside the git repo root).
- Ground truth is generator-owned (`label_source: synthetic_deterministic`).
- Private owner tracks (including `ARRANGEMENT_PILOT_V1`) are never GT for this corpus id; they may remain descriptive reality-check only outside committed artifacts.

## Named corpus identity

| Field | Value |
|---|---|
| `corpus_id` | `sample-brain.aq7.structure-role-drop.synthetic.v1` |
| `document_type` | `sample-brain.aq7.structure-role-drop-corpus.v1` |
| `corpus_version` | `1.0.0` |
| `generator_id` | `sample-brain.aq7.structure-role-drop.generator.v1` |
| `generator_seed` | `1024001` |
| Default `sample_rate` | `44100` |
| Label source | `synthetic_deterministic` (generator-owned GT; not human annotation) |

Fixture IDs are portable and deterministic. Pattern:

```text
aq7-synth-<family>-<cal|test>-NNN
```

Examples: `aq7-synth-simple-clean-cal-001`, `aq7-synth-drop-at-boundary-test-001`.

- Identity is the fixture token itself — **no path-based identity**.
- Portable join key: `fixture_id` ↔ #956 `record_id`.
- Absolute host paths are forbidden in committed or portable GT/manifest artifacts.

### KPI contract lift (applied with #1024 delivery)

```text
AQ7_ANNOTATED_CORPUS = sample-brain.aq7.structure-role-drop.synthetic.v1
```

Wired in `AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md` and indexed in `docs/CANON_INDEX.md` as ACTIVE_SUPPORTING. KPI law (#1023) is unchanged; this resolves the corpus HOLD only.

## Ownership

| Concern | Owner |
|---|---|
| Synthetic fixture definitions, GT schema shape, generator seed/version, split membership | this corpus |
| Plane metrics, tolerance, ignore-mask, disagreement rules, partition firewall | `AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md` (#1023) |
| Portable eval envelope / `record_id` | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Perturbation mechanics | [#957](https://github.com/jannekbuengener/sample-brain/issues/957) |
| StructureV1 / ArrangementClassifier algorithms | out of scope |
| Promotion thresholds / production switch | future evidence-backed issues only |

## Non-goals

- no StructureV1 / ArrangementClassifier / SectionSignals / baseline / metric code changes
- no generator, schema module, or test implementation in this docs-only freeze
- no production switch or promotion thresholds
- no private audio / private paths / private pilot annotations in committed artifacts
- no pseudo-ground-truth from analyzer output (see Ground-truth independence)
- no role logic creating or moving boundaries
- no `drop_onset`-as-section-role semantics
- no committed WAV binaries in the repository
- no #1086 32-field semantics

## Three-plane contract (corpus shape)

Planes match #1023 domain tokens. Annotations are structurally distinct.

### Boundary (`aq7.boundary`)

- Primary coordinate: zero-based `bar_index`.
- Reference boundaries are **neutral** musical section transitions.
- Sections are half-open bar ranges `[start_bar, end_bar)` (see #1023 Segment-IoU policy).
- Roles **cannot** create or move boundaries.
- Track start/end define extent; scored internal boundaries follow #1023.

### Role (`aq7.role`)

Frozen vocabulary (binding from #1023):

`intro`, `groove`, `build`, `drop`, `breakdown`, `outro`, `unknown`.

- Role labels reference **existing** reference section IDs derived from reference boundaries.
- Semantic `unknown` means no concrete v1 role is defensible; it is **not** the same as annotation disagreement (`ambiguous` status — #1023).
- Role evaluation never changes section boundaries.

### Drop (`aq7.drop_event`)

- The only v1 event is `drop_onset`.
- Every annotated `drop_onset` references an **existing** reference boundary identity / bar position.
- Drop events **cannot** create boundaries.
- Event-eligible fixtures must state the full expected set, including an **explicit empty set** when there are zero drops.

## Annotation status

Per-plane / per-locus status vocabulary (binding from #1023):

| Status | Meaning |
|---|---|
| `adjudicated` | reviewed canonical reference accepted |
| `single_source` | one acceptable source, no disagreement evidence |
| `ambiguous` | unresolved disagreement or inherently unstable reference |
| `unavailable` | no defensible ground truth for this plane |

Disagreement, ignore-mask, and dependent-plane carry-over rules are **not** restated here; consume #1023 Annotation status / disagreement policy by reference.

## Timebase

- Primary matching coordinate: `bar_index` (zero-based).
- Optional `time_sec` only when derived from the fixture's **authored synthetic BeatGrid** with trustworthy provenance.
- Seconds remain secondary diagnostics only (#1023).
- This corpus does **not** adopt #1086 32-field semantics.

## BeatGrid provenance

Every fixture GT sidecar carries an explicit BeatGrid provenance block. Allowed values for this corpus:

| Provenance | Meaning |
|---|---|
| `authored_synthetic` | generator authored a deterministic synthetic BeatGrid used for bar↔time derivation |
| `missing` | no BeatGrid / time mapping is provided |
| `insufficient` | BeatGrid/timebase present but not trustworthy for scoring seconds (or bar mapping incomplete) |

Rules:

- Analyzer-predicted BeatGrid is **never** ground truth.
- Reference `bar_index` is corpus annotation truth.
- Fixtures that exercise BeatGrid HOLD paths use `missing` or `insufficient` explicitly (see `beatgrid_hold` in the TEST matrix).

## Fixture matrix (exactly 10)

Exactly **10** fixtures: **6 CALIBRATION** + **4 TEST**.

### CALIBRATION (`cal`)

| Family token | Intent |
|---|---|
| `simple_clean` | Clean neutral boundaries, clear concrete roles, optional simple drop set |
| `repeated_structure` | Repeated section topology with distinct portable identity |
| `near_boundary_tolerance` | Near ±1-bar boundary ambiguity / tolerance exercise (ignore-mask / adjudication provenance as needed) |
| `role_ambiguity_unknown` | Explicit semantic `unknown` role cases (not disagreement shortcuts) |
| `annotation_disagreement` | Annotation-status `ambiguous` loci with recorded spread/provenance for ignore-mask behavior |
| `over_segmentation_challenge` | Extra/dense boundary challenge relative to reference structure |

### TEST (`test`)

| Family token | Intent |
|---|---|
| `drop_at_boundary` | `drop_onset` correctly anchored to an existing reference boundary |
| `drop_not_boundary_owner` | Drop/event plane must not invent or own boundaries; roles/events stay distinct |
| `under_segmentation_challenge` | Missing/coarse boundary challenge relative to reference structure |
| `beatgrid_hold` | Explicit BeatGrid provenance `missing` or `insufficient`; HOLD / unknown timing paths without fabricating bars |

Fixture IDs (frozen membership tokens; NNN starts at `001` per family):

| Split | `fixture_id` |
|---|---|
| CALIBRATION | `aq7-synth-simple-clean-cal-001` |
| CALIBRATION | `aq7-synth-repeated-structure-cal-001` |
| CALIBRATION | `aq7-synth-near-boundary-tolerance-cal-001` |
| CALIBRATION | `aq7-synth-role-ambiguity-unknown-cal-001` |
| CALIBRATION | `aq7-synth-annotation-disagreement-cal-001` |
| CALIBRATION | `aq7-synth-over-segmentation-challenge-cal-001` |
| TEST | `aq7-synth-drop-at-boundary-test-001` |
| TEST | `aq7-synth-drop-not-boundary-owner-test-001` |
| TEST | `aq7-synth-under-segmentation-challenge-test-001` |
| TEST | `aq7-synth-beatgrid-hold-test-001` |

## Leakage policy

Frozen for this corpus id:

1. No `fixture_id` appears in both CALIBRATION and TEST.
2. No copy-with-offset of the same topology across splits.
3. No seed-mutated twins of the same topology placed in both CAL and TEST.
4. TEST is never tuning feedback (consume #1023 partition firewall).
5. GT-changing annotation or topology edits require a `corpus_version` bump and invalidate prior directly comparable holdout claims for changed fixtures.

## Artifact layout

Runtime work directory (external / temp; writing inside the git repo root is rejected by the future generator):

```text
<work_dir>/
  manifest.json
  audio/<fixture_id>.wav
  gt/<fixture_id>.json
```

Repository commits for the #1024 track:

| Now (this docs-only freeze) | Later (follow-up tasks under #1024) |
|---|---|
| this contract doc | schema module, generator, tests, KPI/CANON wiring when authorized |

Generated WAVs and runtime GT trees are **never** committed (`docs/DATA_AND_ARTIFACT_POLICY.md`).

## Schema (per-fixture GT sidecar — contract shape)

Exact JSON field names may be finalized by the schema module, but every fixture must preserve at least the following semantics:

```json
{
  "document_type": "sample-brain.aq7.structure-role-drop-corpus.v1",
  "corpus_id": "sample-brain.aq7.structure-role-drop.synthetic.v1",
  "corpus_version": "1.0.0",
  "generator_id": "sample-brain.aq7.structure-role-drop.generator.v1",
  "generator_seed": 1024001,
  "fixture_id": "aq7-synth-simple-clean-cal-001",
  "sample_rate": 44100,
  "split": "CALIBRATION",
  "label_source": "synthetic_deterministic",
  "family": "simple_clean",
  "beatgrid_provenance": {
    "status": "authored_synthetic",
    "note": "generator-authored synthetic grid; analyzer BeatGrid is never GT"
  },
  "boundaries": [
    {
      "boundary_id": "b1",
      "bar_index": 16,
      "time_sec": null,
      "annotation_status": "single_source"
    }
  ],
  "sections": [
    {
      "section_id": "s0",
      "start_bar": 0,
      "end_bar": 16,
      "role": "intro",
      "annotation_status": "single_source"
    }
  ],
  "drop_events": [],
  "drop_events_complete": true,
  "plane_status": {
    "aq7.boundary": "single_source",
    "aq7.role": "single_source",
    "aq7.drop_event": "single_source"
  },
  "join_key": {
    "analysis_eval_record_id": "aq7-synth-simple-clean-cal-001",
    "note": "fixture_id is the portable #956 record_id join key; no host paths"
  }
}
```

### Field rules

| Field | Rule |
|---|---|
| `fixture_id` | Stable portable token; equals #956 `record_id` join key; pattern `aq7-synth-<family>-<cal\|test>-NNN` |
| `split` | `CALIBRATION` or `TEST` (map to KPI DEVELOPMENT/CALIBRATION and TEST/HOLDOUT) |
| `label_source` | Always `synthetic_deterministic` for this corpus id |
| `boundaries` | Neutral internal boundaries; zero-based `bar_index`; optional `time_sec` only with authored synthetic BeatGrid |
| `sections` | Half-open `[start_bar, end_bar)`; role from frozen vocabulary; IDs reference boundary-derived sections |
| `drop_events` | Only `drop_onset`; each event references an existing `boundary_id` / bar; empty list allowed |
| `drop_events_complete` | Must be `true` for event-eligible fixtures (explicit empty set when zero drops) |
| `beatgrid_provenance.status` | One of `authored_synthetic`, `missing`, `insufficient` |
| `annotation_status` / `plane_status` | One of `adjudicated`, `single_source`, `ambiguous`, `unavailable` |
| Absolute paths | Forbidden in GT JSON and `manifest.json` |

A corpus `manifest.json` lists identity (`corpus_id`, `document_type`, `corpus_version`, `generator_id`, `generator_seed`), fixture membership by split, family tags, and plane support hooks without embedding host paths.

## Ground-truth independence

Ground truth for this corpus **must not** be derived from:

- `StructureV1` predicted boundaries/sections
- `ArrangementClassifier` predicted roles or events
- `SectionSignals` (or equivalent signal matrices) as labels
- analyzer-predicted BeatGrid / downbeats
- predicted `drop_onset` from the current classifier
- current analyzer thresholds or score cutoffs
- private pilot data (`ARRANGEMENT_PILOT_V1` or equivalent private tracks)

Synthetic audio may be designed so that a future analyzer *could* detect structure, but labels remain generator-authored annotation truth, not reverse-engineered analyzer dumps.

## Partition mapping

| Corpus `split` | KPI role (`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`) |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on `TEST`.

## Join keys (#956)

- Portable join key: `fixture_id` ↔ analysis-eval `record_id`
- Domain tokens when emitting eval artifacts: `aq7.boundary`, `aq7.role`, `aq7.drop_event`
- Never put absolute audio paths into portable envelopes; keep paths runtime-local only
- Do not collapse the three planes into one portable label

## Planned generator / schema surface (document only)

Not implemented in this docs-only freeze. Follow-up tasks under #1024 own:

```text
src/aq7_structure_role_drop_schema.py
src/aq7_structure_role_drop_corpus.py
  CORPUS_ID / DOCUMENT_TYPE / CORPUS_VERSION
  GENERATOR_ID / GENERATOR_SEED
  FIXTURE_MATRIX (6 CAL + 4 TEST)
  generate_aq7_structure_role_drop_corpus(work_dir, *, repo_root=None) -> CorpusManifest
```

Determinism target (when implemented): identical seed/version/fixture definitions → identical WAV bytes and canonical GT JSON.

## Exit vocabulary

Exactly one:

- `AQ7_STRUCTURE_ROLE_DROP_CORPUS_FROZEN` — named synthetic corpus id, three-plane schema contract, fixture matrix (6 CAL / 4 TEST), leakage policy, BeatGrid provenance, artifact layout, and GT-independence rules frozen; generator/schema/tests remain follow-up of #1024
- `AQ7_STRUCTURE_CORPUS_PARTIAL_HOLD` — partial freeze only; named blockers remain
- `AQ7_STRUCTURE_CORPUS_INSUFFICIENT` — corpus cannot be frozen without private audio or invented analyzer-derived labels

This docs-only task exits:

```text
AQ7_STRUCTURE_ROLE_DROP_CORPUS_FROZEN
```

Corpus **code** (schema module, generator, tests) and KPI/CANON lift of `AQ7_ANNOTATED_CORPUS` remain follow-up work under #1024. Issue #1024 stays OPEN until those slices complete under the authorized sequence.
