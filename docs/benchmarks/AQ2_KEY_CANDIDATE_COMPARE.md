# AQ2 Key/Mode Candidate Comparison (FSLD)

**Status:** ACTIVE_SUPPORTING — reproducible candidate comparison for [#987](https://github.com/jannekbuengener/sample-brain/issues/987)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#944](https://github.com/jannekbuengener/sample-brain/issues/944) (AQ2), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on:** [#983](https://github.com/jannekbuengener/sample-brain/issues/983) KPI contract, [#985](https://github.com/jannekbuengener/sample-brain/issues/985) key/tonality baseline  
**Normative KPI contract:** [`AQ2_KEY_TONALITY_KPI_CONTRACT.md`](AQ2_KEY_TONALITY_KPI_CONTRACT.md)  
**Baseline surface:** [`AQ2_KEY_TONALITY_BASELINE.md`](AQ2_KEY_TONALITY_BASELINE.md) / `python -m src.fsld_current_analyzer_eval`  
**Compare runner:** `python -m src.fsld_aq2_key_candidate_compare`

## Architecture outcome

```text
AQ2_KEY_CANDIDATE_COMPARE_REPRODUCIBLE
```

(or `AQ2_KEY_CANDIDATE_COMPARE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE` when neither live public audio nor baseline prediction JSON is available)

This document freezes a **small, fair key/mode candidate set** and a **reproducible comparison harness** on the FSLD public baseline. It does **not** promote a candidate, set numeric gates, invent a continuous claim score, change Harmonic Match scoring, or switch production defaults.

AUROC / AUPRC and confidence-as-probability calibration remain **HOLD**.

## Non-goals

- no production switch / no promotion thresholds
- no TEST/HOLDOUT threshold discovery or tuning
- no Harmonic Match scoring changes
- no invented continuous claim score / AUROC / calibration curves
- no private audio or absolute host paths in committed artifacts
- no broad `analyze.py` rewrite beyond declared thin adapters
- no reopening closed AQ8 foundation issues (#956–#959); reuse by reference

## Candidate identity (frozen ≤4)

All candidates share the **same** chroma-peak root from `src.analyze.extract_features` (V1). They differ only by thin adapters over already-persisted third-contrast mode energies and optional `key_conf` claim gating.

| `candidate_id` | `mode_contrast_min` | `key_conf_min` | Identity notes |
|---|---:|---:|---|
| `extract_features.key_v1.mode_contrast.0.30` | `0.30` | — | AQ2 baseline path (`MODE_CONTRAST_MIN`) |
| `extract_features.key_v1.mode_contrast.0.10` | `0.10` | — | Same energies; more permissive mode commit |
| `extract_features.key_v1.mode_contrast.0.50` | `0.50` | — | Same energies; more conservative mode abstention |
| `extract_features.key_v1.key_conf_gate.0.55` | `0.30` | `0.55` | Baseline mode + withhold claim when `key_conf < CONF_KEY_MIN` (export threshold; relative prominence, not probability) |

No V2 shadow / joint-profile backend is in this bake-off (would require a separate live prediction path). No other key backends are in scope.

### Scoring rule (normative)

1. Shared raw root + third-contrast evidence is always obtained from `extract_features` with `mode_contrast_min=0.30` recorded (live **or** an EVALUATED baseline prediction artifact).
2. Each candidate’s reported mode is recomputed from `native_evidence.key_mode_evidence` third-contrast energies at the candidate threshold.
3. The `key_conf_gate.0.55` candidate additionally nulls root/mode/key when `key_conf < 0.55`.
4. AQ2 metrics reuse `src.fsld_current_analyzer_eval` helpers: `key_root`, `key_mode`, `full_key`, `key_confusion`, `tonality` (explicit denominators). Tempo is out of this compare artifact.
5. `auroc_auprc` / `calibration` remain `HOLD` on every tonality plane.
6. Do not invent thresholds from TEST/HOLDOUT.

## Partition policy

| FSLD split | AQ2 role | Allowed use in this slice |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration / comparison narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report once; **no threshold discovery** |

## How to run

Public FSL10K audio and JSON outputs stay **outside** the repository. The runner rejects in-repo outputs (same policy as the baseline runner).

### Path A — live audio (preferred when available)

```powershell
python -m src.fsld_aq2_key_candidate_compare `
  --audio-root <FSL10K-audio-root> `
  --split CALIBRATION `
  --output <external-directory>/aq2-key-compare-calibration.json

python -m src.fsld_aq2_key_candidate_compare `
  --audio-root <FSL10K-audio-root> `
  --split TEST `
  --output <external-directory>/aq2-key-compare-test.json
```

Live path analyzes each present `.wav` once via `extract_features`, then applies the four in-tree adapters. Missing audio / analysis failure semantics match the baseline runner (`PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` when no record analyzes successfully).

### Path B — baseline prediction JSON (reproducible without re-analysis)

When live public audio is unavailable, reuse an external EVALUATED artifact from `python -m src.fsld_current_analyzer_eval` (must be V1 / `mode_contrast_min=0.30` predictions with `native_evidence`):

```powershell
python -m src.fsld_aq2_key_candidate_compare `
  --baseline-predictions <external>/aq2-key-tonality-calibration.json `
  --split CALIBRATION `
  --output <external-directory>/aq2-key-compare-calibration.json

python -m src.fsld_aq2_key_candidate_compare `
  --baseline-predictions <external>/aq2-key-tonality-test.json `
  --split TEST `
  --output <external-directory>/aq2-key-compare-test.json
```

Exactly one of `--audio-root` or `--baseline-predictions` is required.

## Artifact schema (compare)

| Field | Notes |
|---|---|
| `document_type` | `sample_brain.fsld_aq2_key_candidate_compare` |
| `schema_version` | `1.0.0` |
| `split` | `CALIBRATION` or `TEST` |
| `run_status` | `EVALUATED` or `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` |
| `manifest_sha256` | verified frozen FSLD human-manifest digest |
| `raw_source` | `live_extract_features` or `baseline_predictions` |
| `auroc_auprc_status` | always `HOLD` in this slice |
| `calibration_status` | always `HOLD` in this slice |
| `candidates[]` | frozen registry entries + per-candidate `metrics.<ma\|sa>.{key_root,key_mode,full_key,key_confusion,tonality}` |
| `records[]` | shared per-sample rows with raw root/mode evidence (no absolute host paths) |

## AQ8 reuse (by reference)

| Closed surface | Reuse here |
|---|---|
| #956 analysis-eval envelope | domain tokens `aq2.key` / `aq2.tonality`; no new ARVP thresholds |
| #957 perturbation contract | not executed in this slice; expectations remain in the KPI contract |
| #958 runtime methodology | optional cold/steady timing remains out of band for this compare artifact |
| #959 semantic determinism | identical inputs + candidate config → comparable key/tonality projections |

## Measured summary (portable)

Public baseline prediction artifacts from [#985](https://github.com/jannekbuengener/sample-brain/issues/985) were available externally for both splits (EVALUATED `sample_brain.fsld_current_analyzer_eval` records with V1 / `mode_contrast_min=0.30`). Candidate metrics were derived by applying the in-tree adapters (Path B / `raw_source=baseline_predictions`). Live FSL10K audio re-analysis was not required for this adapter bake-off. No absolute host paths and no private audio are committed. No candidate is promoted.

Rounded display values below; exact floats live in the external compare JSON.

### CALIBRATION → DEVELOPMENT/CALIBRATION (exploration)

| Candidate | Tier | root exact | mode exact | full exact | mode cov | tonal cov | false-key-claim |
|---|---|---:|---:|---:|---:|---:|---:|
| mode_contrast.0.30 | MA | 0.700 (14/20) | 0.438 (7/16) | 0.143 (2/14) | 0.500 | 1.000 | 1.000 (19/19) |
| mode_contrast.0.30 | SA | 0.609 (14/23) | 0.167 (3/18) | 0.167 (3/18) | 0.278 | 1.000 | 0.968 (30/31) |
| mode_contrast.0.10 | MA | 0.700 (14/20) | 0.562 (9/16) | 0.286 (4/14) | 0.625 | 1.000 | 1.000 (19/19) |
| mode_contrast.0.10 | SA | 0.609 (14/23) | 0.389 (7/18) | 0.333 (6/18) | 0.611 | 1.000 | 0.968 (30/31) |
| mode_contrast.0.50 | MA | 0.700 (14/20) | 0.062 (1/16) | 0.071 (1/14) | 0.062 | 1.000 | 1.000 (19/19) |
| mode_contrast.0.50 | SA | 0.609 (14/23) | 0.056 (1/18) | 0.056 (1/18) | 0.056 | 1.000 | 0.968 (30/31) |
| key_conf_gate.0.55 | MA | 0.000 (0/20) | 0.000 (0/16) | 0.000 (0/14) | 0.000 | 0.000 | 0.000 (0/19) |
| key_conf_gate.0.55 | SA | 0.000 (0/23) | 0.000 (0/18) | 0.000 (0/18) | 0.000 | 0.000 | 0.000 (0/31) |

### TEST → TEST/HOLDOUT (frozen evidence; no tuning)

| Candidate | Tier | root exact | mode exact | full exact | mode cov | tonal cov | false-key-claim |
|---|---|---:|---:|---:|---:|---:|---:|
| mode_contrast.0.30 | MA | 0.612 (52/85) | 0.123 (7/57) | 0.100 (5/50) | 0.246 | 1.000 | 1.000 (78/78) |
| mode_contrast.0.30 | SA | 0.472 (42/89) | 0.127 (9/71) | 0.085 (6/71) | 0.169 | 1.000 | 1.000 (122/122) |
| mode_contrast.0.10 | MA | 0.612 (52/85) | 0.298 (17/57) | 0.220 (11/50) | 0.561 | 1.000 | 1.000 (78/78) |
| mode_contrast.0.10 | SA | 0.472 (42/89) | 0.352 (25/71) | 0.239 (17/71) | 0.493 | 1.000 | 1.000 (122/122) |
| mode_contrast.0.50 | MA | 0.612 (52/85) | 0.053 (3/57) | 0.020 (1/50) | 0.140 | 1.000 | 1.000 (78/78) |
| mode_contrast.0.50 | SA | 0.472 (42/89) | 0.042 (3/71) | 0.028 (2/71) | 0.042 | 1.000 | 1.000 (122/122) |
| key_conf_gate.0.55 | MA | 0.000 (0/85) | 0.000 (0/57) | 0.000 (0/50) | 0.000 | 0.000 | 0.000 (0/78) |
| key_conf_gate.0.55 | SA | 0.000 (0/89) | 0.000 (0/71) | 0.000 (0/71) | 0.000 | 0.000 | 0.000 (0/122) |

Observation (non-promotional): on frozen TEST, lowering mode contrast to `0.10` raises mode/full-key exact rates and coverage without changing root exactness or false-key-claim (root still always claimed). Raising to `0.50` collapses mode coverage. Applying `CONF_KEY_MIN=0.55` as a hard claim gate abstains on essentially all FSLD rows on this prominence scale (zero tonal coverage / zero false claims) — useful claimability evidence, not a promotion candidate. No threshold is derived from TEST/HOLDOUT. AUROC/calibration remain HOLD.

## Exit vocabulary

Exactly one:

- `AQ2_KEY_CANDIDATE_COMPARE_REPRODUCIBLE`
- `AQ2_KEY_CANDIDATE_COMPARE_BLOCKED_PUBLIC_AUDIO_UNAVAILABLE`
- `AQ2_KEY_CANDIDATE_COMPARE_INCOMPLETE`

This slice exits `AQ2_KEY_CANDIDATE_COMPARE_REPRODUCIBLE` for CALIBRATION and TEST with AUROC/calibration HOLD.
