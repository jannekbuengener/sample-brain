# AQ3 Synthetic Onset & Attack Timing Ground-Truth Corpus

**Status:** ACTIVE_SUPPORTING — synthetic timing GT freeze for [#993](https://github.com/jannekbuengener/sample-brain/issues/993)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#945](https://github.com/jannekbuengener/sample-brain/issues/945) (AQ3), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#991](https://github.com/jannekbuengener/sample-brain/issues/991) / `docs/benchmarks/AQ3_ONSET_GESTURE_KPI_CONTRACT.md` (CLOSED)  
**Related:** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) portable `record_id` join; [#957](https://github.com/jannekbuengener/sample-brain/issues/957) perturbation mechanics  
**Tooling:** `src/aq3_timing_corpus.py`

## Architecture outcome

```text
AQ3_TIMING_CORPUS_FROZEN
```

This slice freezes a **small deterministic synthetic** onset/attack timing ground-truth corpus so AQ3 can run measurable baselines. It does **not** change onset/gesture algorithms, invent human labels for private audio, or set promotion gates.

## Named corpus identity

| Field | Value |
|---|---|
| `corpus_id` | `sample-brain.aq3.timing.synthetic.v1` |
| `document_type` | `sample-brain.aq3.timing-corpus.v1` |
| `corpus_version` | `1.0.0` |
| `generator_seed` | `993001` |
| Default `sample_rate` | `44100` |
| Label source | `synthetic_deterministic` (generator-owned GT; not human annotation) |

KPI contract lift (narrow):

```text
AQ3_PUBLIC_ANNOTATED_TIMING_CORPUS = sample-brain.aq3.timing.synthetic.v1
```

This is a **synthetic annotated** corpus. It unblocks measurable AQ3 baselines on controlled material. It is **not** a claim that soft-attack / layered / noisy human reality-check annotations exist, and it must not set public promotion thresholds by itself.

## Ownership

| Concern | Owner |
|---|---|
| Synthetic clip definitions, GT schema, generator seed/version | this corpus |
| Timing tolerance **candidates** (e.g. 20 ms / 50 ms) | this corpus (constants only — not gates) |
| AQ3 metric definitions / plane separation | `AQ3_ONSET_GESTURE_KPI_CONTRACT.md` |
| Portable eval envelope / `record_id` | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Onset / attack / gesture algorithms | out of scope |
| Promotion thresholds / production switch | future evidence-backed issues only |

## Non-goals

- no onset / attack / gesture algorithm changes
- no production switch or promotion thresholds
- no private audio / private paths in committed artifacts
- no invented human labels for private libraries
- no committed WAV binaries in the repository
- no #680 product work

## Artifact policy

Audio and GT sidecars are generated **at runtime** under an external/temp work directory via `generate_aq3_timing_corpus(work_dir=...)`.

- Writing corpus audio **inside the git repo root is rejected**.
- Committed audio binaries remain forbidden (`docs/DATA_AND_ARTIFACT_POLICY.md`).
- Only generator code, schema docs, and tests are versioned.

## Schema (per-clip GT sidecar)

Each clip writes `audio/<clip_id>.wav` and `gt/<clip_id>.json`.

```json
{
  "document_type": "sample-brain.aq3.timing-corpus.v1",
  "corpus_id": "sample-brain.aq3.timing.synthetic.v1",
  "corpus_version": "1.0.0",
  "generator_seed": 993001,
  "clip_id": "aq3-synth-silence-leading-cal-001",
  "sample_rate": 44100,
  "duration_ms": 1000.0,
  "onset_times_ms": [250.0],
  "attack_marker_ms": 250.0,
  "buckets": ["silence_leading"],
  "split": "CALIBRATION",
  "label_source": "synthetic_deterministic",
  "join_key": {
    "analysis_eval_record_id": "aq3-synth-silence-leading-cal-001",
    "note": "clip_id is the portable #956 record_id join key; no host paths"
  }
}
```

### Field rules

| Field | Rule |
|---|---|
| `clip_id` | Stable portable token; equals #956 `record_id` join key |
| `sample_rate` | Integer Hz (corpus default 44100) |
| `onset_times_ms` | Sorted non-decreasing list of onset times in milliseconds |
| `attack_marker_ms` | Optional single attack/cue marker (ms); omit/`null` when not applicable |
| `buckets` | One or more bucket tags from the active/HOLD vocabulary |
| `split` | `CALIBRATION` or `TEST` (map to KPI DEVELOPMENT/CALIBRATION and TEST/HOLDOUT) |
| `label_source` | Always `synthetic_deterministic` for this corpus id |
| Absolute paths | Forbidden in GT JSON |

A corpus `manifest.json` lists identity, tolerance candidates, HOLD stubs, and clip membership without embedding host paths.

## Active buckets (thin coverage)

| Bucket | Meaning in this corpus | Coverage |
|---|---|---|
| `soft_attack` | Gradual energy rise; single soft onset + attack marker | ≥1 clip |
| `silence_leading` | Leading silence before first hard transient | ≥1 clip |
| `short_clip` | Duration near practical minima (`very_short` KPI sense) | ≥1 clip |
| `simple_multi_onset` | Multiple hard clicks at known times | ≥1 clip |

Both `CALIBRATION` and `TEST` splits are present across the active set.

## HOLD stubs (documented, not generated)

| Bucket | Status |
|---|---|
| `layered_transient_dense` | HOLD — no synthetic GT clip in v1 |
| `noisy` | HOLD — no synthetic GT clip in v1 |

These remain slice-metric definitions from the KPI contract. v1 does not invent believable layered/noisy human-grade labels.

## Timing tolerance candidates (corpus-owned constants)

Frozen as **candidates only** (not promotion gates):

| Constant | Values |
|---|---|
| `TOLERANCE_CANDIDATES_MS` | `20`, `50` |

Report any future P/R/F1 or within-tolerance rate with an explicit window. Do not treat these candidates as merge or production gates.

## Partition mapping

| Corpus `split` | KPI role (`AQ3_ONSET_GESTURE_KPI_CONTRACT.md`) |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on `TEST`.

## Join keys (#956)

- Portable join key: `clip_id` ↔ analysis-eval `record_id`
- Domain tokens when emitting eval artifacts: `aq3.onset`, `aq3.attack`, `aq3.gesture` as appropriate
- Never put absolute audio paths into portable envelopes; keep paths runtime-local only

## Generator surface

```text
src/aq3_timing_corpus.py
  CORPUS_ID / DOCUMENT_TYPE / CORPUS_VERSION / GENERATOR_SEED
  TOLERANCE_CANDIDATES_MS
  ACTIVE_BUCKETS / HOLD_BUCKETS
  generate_aq3_timing_corpus(work_dir, *, repo_root=None) -> CorpusManifest
```

Determinism: identical seed/version/clip definitions → identical WAV bytes and canonical GT JSON.

## Exit vocabulary

Exactly one:

- `AQ3_TIMING_CORPUS_FROZEN` — named synthetic corpus id, schema, generator, tolerance candidates, and thin active-bucket coverage frozen; layered/noisy remain HOLD stubs
- `AQ3_TIMING_CORPUS_INSUFFICIENT` — corpus cannot be frozen without private audio or invented human labels

This slice exits `AQ3_TIMING_CORPUS_FROZEN`.
