# AQ4 Synthetic Classification Ground-Truth Corpus

**Status:** ACTIVE_SUPPORTING — synthetic classification GT freeze for [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) / `docs/benchmarks/AQ4_CLASSIFICATION_KPI_CONTRACT.md` (CLOSED)  
**Related:** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) portable `record_id` join; [#957](https://github.com/jannekbuengener/sample-brain/issues/957) perturbation mechanics  
**Tooling:** `src/aq4_classification_corpus.py`

## Architecture outcome

```text
AQ4_CLASSIFICATION_CORPUS_FROZEN
```

This slice freezes a **small deterministic synthetic** classification ground-truth corpus with **separate** `sample_class` and `pred_type` labels so AQ4 can run measurable baselines. It does **not** change classify/analyze algorithms, invent human labels for private audio, collapse the two taxonomies, or set promotion gates.

## Named corpus identity

| Field | Value |
|---|---|
| `corpus_id` | `sample-brain.aq4.classification.synthetic.v1` |
| `document_type` | `sample-brain.aq4.classification-corpus.v1` |
| `corpus_version` | `1.0.0` |
| `generator_seed` | `1021001` |
| Default `sample_rate` | `44100` |
| Label source | `synthetic_deterministic` (generator-owned GT; not human annotation) |

KPI contract lift (narrow):

```text
AQ4_LABELED_PUBLIC_CLASSIFICATION_CORPUS = sample-brain.aq4.classification.synthetic.v1
```

This is a **synthetic labeled** corpus. It unblocks measurable AQ4 baselines on controlled material. It is **not** a claim that human-labeled public/sanitized libraries exist. A separate human-labeled public corpus may remain HOLD until a future scoped adoption issue.

## Ownership

| Concern | Owner |
|---|---|
| Synthetic clip definitions, GT schema, generator seed/version | this corpus |
| Eligible `sample_class` / `pred_type` label sets for this corpus id | this corpus |
| AQ4 metric definitions / plane separation | `AQ4_CLASSIFICATION_KPI_CONTRACT.md` |
| Portable eval envelope / `record_id` | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Duration `sample_class` / rule+kNN `pred_type` algorithms | out of scope |
| Promotion thresholds / production switch | future evidence-backed issues only |

## Non-goals

- no classify / analyze algorithm changes
- no production switch or promotion thresholds
- no private audio / private paths in committed artifacts
- no invented human labels for private libraries
- no collapse of `sample_class` into `pred_type` (or the reverse)
- no committed WAV binaries in the repository
- no consumer safety-gate implementation

## Artifact policy

Audio and GT sidecars are generated **at runtime** under an external/temp work directory via `generate_aq4_classification_corpus(work_dir=...)`.

- Writing corpus audio **inside the git repo root is rejected**.
- Committed audio binaries remain forbidden (`docs/DATA_AND_ARTIFACT_POLICY.md`).
- Only generator code, schema docs, and tests are versioned.

## Schema (per-clip GT sidecar)

Each clip writes `audio/<clip_id>.wav` and `gt/<clip_id>.json`.

```json
{
  "document_type": "sample-brain.aq4.classification-corpus.v1",
  "corpus_id": "sample-brain.aq4.classification.synthetic.v1",
  "corpus_version": "1.0.0",
  "generator_seed": 1021001,
  "clip_id": "aq4-synth-kick-oneshot-cal-001",
  "sample_rate": 44100,
  "duration_ms": 200.0,
  "sample_class": "oneshot",
  "pred_type": "Kick",
  "label_status": "clear",
  "split": "CALIBRATION",
  "label_source": "synthetic_deterministic",
  "join_key": {
    "analysis_eval_record_id": "aq4-synth-kick-oneshot-cal-001",
    "note": "clip_id is the portable #956 record_id join key; no host paths"
  }
}
```

### Field rules

| Field | Rule |
|---|---|
| `clip_id` | Stable portable token; equals #956 `record_id` join key |
| `sample_rate` | Integer Hz (corpus default 44100) |
| `duration_ms` | Designed duration in milliseconds |
| `sample_class` | Separate binary/structural plane: `loop`, `oneshot`, `ambiguous`, or `unknown` |
| `pred_type` | Separate semantic plane: eligible classify-aligned label or `unknown` |
| `label_status` | `clear`, `ambiguous`, or `unknown` — uncertain labels stay explicit |
| `split` | `CALIBRATION` or `TEST` (map to KPI DEVELOPMENT/CALIBRATION and TEST/HOLDOUT) |
| `label_source` | Always `synthetic_deterministic` for this corpus id |
| Absolute paths | Forbidden in GT JSON |

A corpus `manifest.json` lists identity, eligible labels, support counts, HOLD notes, and clip membership without embedding host paths.

## Eligible labels (thin freeze)

### `sample_class` (`aq4.sample_class`)

| Label | Role in this corpus |
|---|---|
| `oneshot` | Clear short structural class (designed duration ≤ 1.2 s) |
| `loop` | Clear longer structural class (designed duration > 1.2 s) |
| `ambiguous` | Explicit uncertain structural label (near duration boundary; not forced) |
| `unknown` | Explicit abstain / no usable structural label |

### `pred_type` (`aq4.pred_type`)

Thin set aligned with current `rule_type` core surfaces in `src/classify.py`:

`Kick`, `Snare`, `HiHat-Closed`, `Impact`, `Drone`, `Pad`, `Loop`, `OneShot`, `Drum Loop`, `FX`, plus explicit `unknown`.

Descriptor companions (`Bright`, `Dark`, `Punchy`, `Atmospheric`) are **not** primary `pred_type` GT in v1.

## Active coverage (thin)

| Plane | Coverage requirement |
|---|---|
| `sample_class` | ≥1 clear `oneshot`, ≥1 clear `loop`; ≥1 `ambiguous` or `unknown` |
| `pred_type` | ≥1 clip for each of a thin core subset spanning oneshot-oriented and loop-oriented labels |
| Splits | Both `CALIBRATION` and `TEST` present |
| Leakage | Each `clip_id` appears in exactly one split; no shared clip membership across partitions by construction |

Support counts are emitted in `manifest.json` under `support_counts` for `sample_class`, `pred_type`, and `split`.

## HOLD stubs (documented, not required in v1 audio)

| Item | Status |
|---|---|
| Human-labeled public/sanitized classification corpus | HOLD — separate from this synthetic id |
| Descriptor multi-label GT (`Bright`/`Dark`/…) | HOLD — not primary GT in v1 |
| Private-library reality-check labels | HOLD — must not enter committed artifacts |

## Partition mapping

| Corpus `split` | KPI role (`AQ4_CLASSIFICATION_KPI_CONTRACT.md`) |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on `TEST`. CALIBRATION/TEST leakage is forbidden by construction: unique `clip_id`s, disjoint split membership, distinct designed waveforms.

## Join keys (#956)

- Portable join key: `clip_id` ↔ analysis-eval `record_id`
- Domain tokens when emitting eval artifacts: `aq4.sample_class`, `aq4.pred_type`
- Never put absolute audio paths into portable envelopes; keep paths runtime-local only
- Do not collapse the two taxonomy fields into one portable label

## Separation reminder

1. `sample_class` and `pred_type` remain separate fields and separate reporting planes.
2. Correct `pred_type` does not imply correct `sample_class` (and vice versa).
3. Generator-owned synthetic labels are not fabricated private-audio human annotations.

## Generator surface

```text
src/aq4_classification_corpus.py
  CORPUS_ID / DOCUMENT_TYPE / CORPUS_VERSION / GENERATOR_SEED
  SAMPLE_CLASS_LABELS / PRED_TYPE_LABELS
  generate_aq4_classification_corpus(work_dir, *, repo_root=None) -> CorpusManifest
```

Determinism: identical seed/version/clip definitions → identical WAV bytes and canonical GT JSON.

## Exit vocabulary

Exactly one:

- `AQ4_CLASSIFICATION_CORPUS_FROZEN` — named synthetic corpus id, schema, generator, thin dual-taxonomy coverage, partition/leakage rules, and support-count hooks frozen; human-labeled public corpus may remain HOLD separately
- `AQ4_CLASSIFICATION_CORPUS_INSUFFICIENT` — corpus cannot be frozen without private audio or invented human labels

This slice exits `AQ4_CLASSIFICATION_CORPUS_FROZEN`.
