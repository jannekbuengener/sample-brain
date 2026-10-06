# AQ1 Tempo Decision Memo (no production switch)

**Status:** ACTIVE_SUPPORTING — evidence-backed tempo decision for [#981](https://github.com/jannekbuengener/sample-brain/issues/981)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#943](https://github.com/jannekbuengener/sample-brain/issues/943) (AQ1), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED):** [#973](https://github.com/jannekbuengener/sample-brain/issues/973) KPI contract, [#975](https://github.com/jannekbuengener/sample-brain/issues/975) tempo baseline, [#977](https://github.com/jannekbuengener/sample-brain/issues/977) candidate compare (PR #980)

## Architecture outcome

```text
AQ1_TEMPO_DECISION_MEMO_RECORDED
```

This memo records an **evidence-backed product recommendation** for AQ1 tempo choices from frozen upstream docs. It does **not** change analyzer algorithms, set numeric promotion gates, or switch production defaults.

## Evidence map

| Stage | Authority | Outcome token |
|---|---|---|
| Contract | [`AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md`](AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md) | `AQ1_TEMPO_BEATGRID_KPI_CONTRACT_FROZEN` |
| Baseline | [`AQ1_TEMPO_BASELINE.md`](AQ1_TEMPO_BASELINE.md) | `AQ1_TEMPO_BASELINE_MEASURED` |
| Candidate compare | [`AQ1_TEMPO_CANDIDATE_COMPARE.md`](AQ1_TEMPO_CANDIDATE_COMPARE.md) | `AQ1_TEMPO_CANDIDATE_COMPARE_REPRODUCIBLE` |

Flow: **contract → baseline → compare → this decision**. Decisions cite those three surfaces only; anecdotes and private library checks are out of band.

## Partition / no-tuning-on-TEST

| FSLD split | AQ1 role | Decision use |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report; **no threshold discovery / no tuning** |

Inherited from the KPI contract and restated in baseline + compare. This memo does not invent gates from TEST/HOLDOUT.

## Half / double visibility

Normative: octave-/metre-normalized diagnostics must **never** hide raw `classify_bpm_error` half/double buckets (KPI contract separation rule). The AQ1 baseline path uses `extract_features(..., bpm_normalization="none")` so relation rates stay visible. Candidate compare scores folded modes against labels while keeping `none` as the raw-visibility reference.

## Recommendation

```text
KEEP_CURRENT_BASELINE_PATH
```

**Justification (brief):**

1. **Frozen contract** names the current baseline as `bpm_normalization="none"` for public FSLD tempo scoring and half/double visibility ([`AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md`](AQ1_TEMPO_BEATGRID_KPI_CONTRACT.md)).
2. **Measured baseline** records that path on CALIBRATION and TEST with relation buckets intact ([`AQ1_TEMPO_BASELINE.md`](AQ1_TEMPO_BASELINE.md)).
3. **Candidate compare** on frozen TEST shows neither `heuristic` nor `domain_110_170` dominates `none` across accuracy bands and relation buckets ([`AQ1_TEMPO_CANDIDATE_COMPARE.md`](AQ1_TEMPO_CANDIDATE_COMPARE.md) TEST table + non-promotional observation). CALIBRATION-only mild band gains are not a promotion proof.

**Path B compare limitations:** the #977 bake-off used Path B (`raw_source=baseline_predictions`) — shared raw BPM from EVALUATED baseline prediction JSON, then in-tree `normalize_bpm` adapters. It does **not** evaluate new beat backends, ML tempo models, or live re-extraction. Adapter folds alone do not justify a production default change.

Alternative tokens considered and **not** chosen:

- `DEFER_PROMOTION` — redundant with keep-current given TEST non-dominance of folds.
- `NEED_FURTHER_CANDIDATES` — may apply later if product quality work targets new backends; it is not required to record this keep-current decision from the existing three-doc chain.

## BeatGrid correctness HOLD

```text
BEATGRID_PUBLIC_ANNOTATION_CORPUS = HOLD
```

AQ1 timing-domain completion for **grid** remains blocked: there is no frozen public beat/downbeat annotation corpus. BPM-only success does not imply BeatGrid correctness. Runtime existence of `src/beat_grid.py` does not close AQ1 BeatGrid KPI. A separate scoped issue is required before BeatGrid correctness claims.

## Explicit non-action (this slice)

- **No production default change** (no switch of `bpm_normalization` or BeatGrid backend defaults).
- No analyzer / BeatGrid algorithm changes.
- No numeric promotion thresholds / gates invented from TEST/HOLDOUT.
- No private audio or absolute host paths in committed artifacts.

## Exit vocabulary

Exactly one:

- `AQ1_TEMPO_DECISION_MEMO_RECORDED`
- `AQ1_TEMPO_DECISION_INSUFFICIENT_EVIDENCE`

This slice exits `AQ1_TEMPO_DECISION_MEMO_RECORDED` with recommendation `KEEP_CURRENT_BASELINE_PATH`, BeatGrid correctness HOLD, and no production switch.
