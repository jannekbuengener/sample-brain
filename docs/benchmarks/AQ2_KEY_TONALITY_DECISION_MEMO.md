# AQ2 Key / Tonality Decision Memo (no production switch)

**Status:** ACTIVE_SUPPORTING — evidence-backed key/tonality decision for [#989](https://github.com/jannekbuengener/sample-brain/issues/989)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#944](https://github.com/jannekbuengener/sample-brain/issues/944) (AQ2), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED):** [#983](https://github.com/jannekbuengener/sample-brain/issues/983) KPI contract, [#985](https://github.com/jannekbuengener/sample-brain/issues/985) key/tonality baseline, [#987](https://github.com/jannekbuengener/sample-brain/issues/987) candidate compare (PR #988)

## Architecture outcome

```text
AQ2_KEY_TONALITY_DECISION_MEMO_RECORDED
```

This memo records an **evidence-backed product recommendation** for AQ2 key/mode/tonality choices from frozen upstream docs. It does **not** change key/mode algorithms, invent a continuous claim score, set numeric promotion gates, change Harmonic Match scoring, or switch production defaults.

## Evidence map

| Stage | Authority | Outcome token |
|---|---|---|
| Contract | [`AQ2_KEY_TONALITY_KPI_CONTRACT.md`](AQ2_KEY_TONALITY_KPI_CONTRACT.md) | `AQ2_KEY_TONALITY_KPI_CONTRACT_FROZEN` |
| Baseline | [`AQ2_KEY_TONALITY_BASELINE.md`](AQ2_KEY_TONALITY_BASELINE.md) | `AQ2_KEY_TONALITY_BASELINE_MEASURED` |
| Candidate compare | [`AQ2_KEY_CANDIDATE_COMPARE.md`](AQ2_KEY_CANDIDATE_COMPARE.md) | `AQ2_KEY_CANDIDATE_COMPARE_REPRODUCIBLE` |

Flow: **contract → baseline → compare → this decision**. Decisions cite those three surfaces only; anecdotes and private library checks are out of band.

## Partition / no-tuning-on-TEST

| FSLD split | AQ2 role | Decision use |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report; **no threshold discovery / no tuning** |

Inherited from the KPI contract and restated in baseline + compare. This memo does not invent gates from TEST/HOLDOUT.

## Separation: key correctness vs tonality claimability

Normative (KPI contract): `aq2.key` and `aq2.tonality` are **separate reporting planes**. Exact root / mode / full-key accuracy must never be inflated by silently dropping difficult mode cases, non-tonal material, or abstentions. Root-only success does not imply mode or full-key success. High tonal coverage does not imply low false-key-claim rate.

Measured baseline (TEST) makes the split concrete: root exact rates are moderate while mode/full-key exact rates and coverage are low, and `no_key` false-key-claim is essentially universal under the current claim surface. Candidate compare must be read on both planes — mode gains without claimability improvement are not a joint promotion proof.

## AUROC / calibration HOLD

```text
CONTINUOUS_CLAIM_SCORE = HOLD
AUROC_AUPRC = HOLD
CALIBRATION = HOLD
```

`key_conf` remains relative chroma-peak prominence evidence only ([`KEY_CONF_EVIDENCE.md`](KEY_CONF_EVIDENCE.md)). No continuous claim score is invented or promoted in this slice. Ranking/calibration metrics stay HOLD until a future scoped issue defines and promotes such a score.

## Recommendation

```text
KEEP_CURRENT_BASELINE_PATH
```

**Justification (brief):**

1. **Frozen contract** names the current public baseline as `extract_features` V1 / `mode_contrast_min=0.30` on FSLD eligibility (`root_evidence` / `mode_evidence` / `tonality`) with key vs tonality separation and AUROC/calibration HOLD ([`AQ2_KEY_TONALITY_KPI_CONTRACT.md`](AQ2_KEY_TONALITY_KPI_CONTRACT.md)).
2. **Measured baseline** records that path on CALIBRATION and TEST with explicit denominators; claimability gaps (near-100% false-key-claim on `no_key`) and low mode/full-key rates are visible without inventing thresholds ([`AQ2_KEY_TONALITY_BASELINE.md`](AQ2_KEY_TONALITY_BASELINE.md)).
3. **Candidate compare** on frozen TEST shows thin adapters do **not** dominate the baseline across **both** planes: `mode_contrast.0.10` raises mode/full-key exact and coverage without changing root exactness or false-key-claim; `mode_contrast.0.50` collapses mode coverage; `key_conf_gate.0.55` zeros tonal coverage (and false claims) on this prominence scale — useful claimability evidence, not a promotion candidate ([`AQ2_KEY_CANDIDATE_COMPARE.md`](AQ2_KEY_CANDIDATE_COMPARE.md) TEST table + non-promotional observation). CALIBRATION-only exploration and single-plane TEST gains are not a production promotion proof.

**Path B / adapter limits:** the #987 bake-off used Path B (`raw_source=baseline_predictions`) — shared root + third-contrast evidence from EVALUATED baseline prediction JSON, then in-tree mode-contrast / `key_conf` claim-gate adapters. It does **not** evaluate new key backends, V2 shadow / joint-profile paths, live re-extraction, or Harmonic Match scoring. Adapter knobs alone do not justify a production default change.

Alternative tokens considered and **not** chosen:

- `DEFER_PROMOTION` — redundant with keep-current once no candidate is promoted and production stays on the measured baseline path.
- `NEED_FURTHER_CANDIDATES` — may apply later if product quality work targets claimability backends, a continuous claim score, or non-adapter key/mode paths; it is not required to record this keep-current decision from the existing three-doc chain.

## Explicit non-action (this slice)

- **No production default change** (no switch of `MODE_CONTRAST_MIN`, claim gates, or key/mode backend defaults).
- No analyzer / key algorithm changes.
- No Harmonic Match scoring changes.
- No numeric promotion thresholds / gates invented from TEST/HOLDOUT.
- No invented continuous claim score / AUROC / calibration curves.
- No private audio or absolute host paths in committed artifacts.

## Exit vocabulary

Exactly one:

- `AQ2_KEY_TONALITY_DECISION_MEMO_RECORDED`
- `AQ2_KEY_TONALITY_DECISION_INSUFFICIENT_EVIDENCE`

This slice exits `AQ2_KEY_TONALITY_DECISION_MEMO_RECORDED` with recommendation `KEEP_CURRENT_BASELINE_PATH`, AUROC/calibration HOLD, key vs tonality separation preserved, and no production switch.
