# AQ7 StructureV1 Neutral Boundary Baseline (synthetic corpus)

**Status:** ACTIVE_SUPPORTING — measured current StructureV1 boundary/segmentation baseline for [#1025](https://github.com/jannekbuengener/sample-brain/issues/1025)
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#949](https://github.com/jannekbuengener/sample-brain/issues/949) (AQ7), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#1023](https://github.com/jannekbuengener/sample-brain/issues/1023) KPI contract, [#1024](https://github.com/jannekbuengener/sample-brain/issues/1024) frozen corpus  
**Normative KPI:** [`AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md`](AQ7_STRUCTURE_ROLE_DROP_KPI_CONTRACT.md)  
**Corpus:** [`AQ7_STRUCTURE_ROLE_DROP_CORPUS.md`](AQ7_STRUCTURE_ROLE_DROP_CORPUS.md) / `sample-brain.aq7.structure-role-drop.synthetic.v1`  
**Runner:** `python -m src.aq7_structure_boundary_baseline`

## Architecture outcome

```text
AQ7_STRUCTURE_BOUNDARY_BASELINE_PARTIAL_HOLD
```

This document records the **current** `StructureV1` neutral boundary/segmentation path against the frozen AQ7 KPI contract on the synthetic structure/role/drop corpus. It measures only the `aq7.boundary` plane. It does **not** evaluate ArrangementClassifier roles or `drop_onset`, change StructureV1 thresholds/features, set promotion gates, or switch production behavior.

`PARTIAL_HOLD` is honest: CALIBRATION and TEST boundary-eligible fixtures with authored synthetic BeatGrid provenance are fully measurable, while the frozen `beatgrid_hold` TEST fixture remains a BeatGrid/provenance HOLD (`missing`) and is not scored with invented timing.

## Scope

| In | Out |
|---|---|
| Current `src.structure_v1.StructureV1Analyzer` default config | ArrangementClassifier / role quality |
| Frozen #1024 corpus identity + GT boundaries | Drop-event quality |
| ±1-bar one-to-one matching from #1023 | Candidate tuning / compare (#1028) |
| CALIBRATION and TEST/HOLDOUT evidence (firewall) | Production default switch |
| BeatGrid/provenance honesty + HOLD paths | UI / Arrangement product work |

## Identities

| Field | Value |
|---|---|
| `document_type` | `sample-brain.aq7.structure-boundary-baseline.v1` |
| `schema_version` | `1.0.0` |
| `candidate_id` / baseline id | `structure_v1.baseline.v1` |
| `corpus_id` | `sample-brain.aq7.structure-role-drop.synthetic.v1` |
| `corpus_version` | `1.0.0` (frozen #1024) |
| StructureV1 surface | `src.structure_v1.StructureV1Analyzer.analyze_path` |
| StructureV1 config | default `StructureV1Config()` — no retuning |

## Partition mapping

| Corpus `split` | AQ7 KPI role |
|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION |
| `TEST` | TEST / HOLDOUT |

Do not tune on TEST/HOLDOUT. This slice is baseline measurement only.

## Matching semantics (#1023)

- Primary tolerance: `BOUNDARY_MATCH_TOLERANCE_BARS = 1`
- Deterministic one-to-one, order-preserving matching
- Maximize match count within tolerance; then minimize total absolute bar error
- Ties prefer earlier prediction, then earlier reference order/id
- Ambiguous reference loci use the frozen ignore-mask policy
- Reference boundaries are never taken from StructureV1 output

## BeatGrid / provenance

- Fixtures with corpus `beatgrid_provenance.status == authored_synthetic` receive an **evaluation-only** synthetic BeatGrid derived from audio duration + track end bar (authored tempo reconstruction). This does **not** use GT boundary bars to invent a grid and is not analyzer BeatGrid truth.
- Fixtures with `missing` / `insufficient` BeatGrid provenance are **HOLD**: StructureV1 is not forced with invented timing; boundary correctness for that record is `unknown`.
- Analyzer failures (`failed`, unusable `no_result` such as `DOWNBEATS_UNAVAILABLE` / `FEATURES_UNAVAILABLE`) are reported separately from BeatGrid provenance HOLDs.
- Usable empty prediction (`no_result` + `NO_BOUNDARY_CANDIDATE`) scores as an empty predicted set per #1023.

## How to run

Corpus audio/GT and JSON evidence stay **outside** the repository:

```powershell
python -m src.aq7_structure_boundary_baseline `
  --work-dir <external-directory>/aq7-structure-role-drop-corpus `
  --output <external-directory>/aq7-structure-boundary-baseline.json
```

Exact floats live in the external JSON. No private audio and no absolute host paths are committed.

## Measured baseline summary (rounded display)

Dual independent external workdirs produced identical semantic projections (`structure_v1.baseline.v1` on corpus `1.0.0`).

| Partition | P@1bar | R@1bar | F1 | support | FP | FN | med\|err\| bars | p95\|err\| bars | over-seg rate | under-seg rate | section-count abs err | segment IoU | coverage | BeatGrid HOLD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CALIBRATION | 0.343 | 0.923 | 0.500 | 13 | 23 | 1 | 0.0 | 0.45 | 1.0 | 0.0 | 3.67 | 0.705 | 1.0 | 0 |
| TEST/HOLDOUT | 0.360 | 1.000 | 0.529 | 9 | 16 | 0 | 0.0 | 0.0 | 1.0 | 0.0 | 5.33 | 0.780 | 1.0 | 1 |

Notes:

- High recall with lower precision / over-segmentation rate = 1.0 is a truthful current-StructureV1 characteristic on this synthetic pack (distractor accents + dense candidates), not a tuning target for this slice.
- Seconds error diagnostics are omitted at aggregate level when not uniformly trustworthy; bar coordinates remain primary.
- Runtime track-length buckets are HOLD (pack too small for #958 bucket p95 claims). External JSON may include single-pass per-fixture wall-time diagnostics; these are explicitly **not** #958 methodology-v1 cold/steady evidence.
- Determinism: a single CLI run records `determinism.status=not_measured`; equality is certified only when a second independent run supplies `prior_semantic` (as in the dual-workdir proof).

## Metrics reported (`aq7.boundary`)

- precision / recall / F1 at ±1 bar (micro over usable eligible records)
- support (eligible reference internal boundaries)
- matched / false-positive / missed counts
- median / p95 absolute bar error on matched pairs (pooled; #958 percentile helper)
- over-segmentation / under-segmentation record rates + section-count absolute error (macro mean)
- segment IoU weighted (when applicable)
- coverage / no-result / partial / BeatGrid HOLD counts
- per-fixture evidence + family buckets
- deterministic semantic repeatability (#959 by reference)
- runtime (#958 by reference; track-length buckets N/A/HOLD on this tiny synthetic pack when not meaningful)

## Production behavior

Settings toggle: `N/A` — evaluation harness only. No changes to `src/structure_v1.py` algorithms, thresholds, or defaults. No production switch.

## Provenance (#958 / #959 by reference)

Runtime methodology and semantic determinism are consumed by reference:

- [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / [`ANALYZER_RUNTIME_METHODOLOGY_V1.md`](ANALYZER_RUNTIME_METHODOLOGY_V1.md)
- [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / [`../ANALYZER_SEMANTIC_DETERMINISM_V1.md`](../ANALYZER_SEMANTIC_DETERMINISM_V1.md)

Reproducibility proof: identical corpus seed + frozen StructureV1 surface + matching semantic aggregates on two independent external workdirs.

## Non-goals

- no #1024 corpus mutation
- no ArrangementClassifier / role / drop evaluation
- no StructureV1 tuning
- no candidate compare (#1028)
- no diagnostics epic (#1027) beyond honest baseline failure visibility
- no committed WAVs
