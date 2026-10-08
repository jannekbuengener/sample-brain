# AQ4 Classification Diagnostics — Error Buckets + Consumer Safety Evidence

**Status:** ACTIVE_SUPPORTING — diagnostics / evidence for [#1005](https://github.com/jannekbuengener/sample-brain/issues/1005)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED):** [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) residual baseline acceptance (consumes [#1032](https://github.com/jannekbuengener/sample-brain/issues/1032) harness), [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001) KPI, [#1021](https://github.com/jannekbuengener/sample-brain/issues/1021) corpus  
**Normative KPI:** [`AQ4_CLASSIFICATION_KPI_CONTRACT.md`](AQ4_CLASSIFICATION_KPI_CONTRACT.md)  
**Corpus:** [`AQ4_CLASSIFICATION_CORPUS.md`](AQ4_CLASSIFICATION_CORPUS.md) / `sample-brain.aq4.classification.synthetic.v1`  
**Baseline surface:** [`AQ4_CLASSIFICATION_BASELINE.md`](AQ4_CLASSIFICATION_BASELINE.md) / `python -m src.aq4_classification_baseline`  
**Related (CLOSED, not substitutes for this slice):** [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) compare, [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036) decision memo  
**Related product / ownership (not AQ4 measurement authority):** [#936](https://github.com/jannekbuengener/sample-brain/issues/936) / `docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md`; [#920](https://github.com/jannekbuengener/sample-brain/issues/920) / `docs/LOOP_ROW_PLAYBACK_CONTRACT.md`; [#171](https://github.com/jannekbuengener/sample-brain/issues/171) / [#173](https://github.com/jannekbuengener/sample-brain/issues/173) / `docs/WORKBENCH_AUTO_METADATA_PLAN.md`

## Architecture outcome

```text
AQ4_CLASSIFICATION_DIAGNOSTICS_PARTIAL_HOLD
```

This document turns the measured AQ4 baseline into **explainable failure buckets** and **consumer-risk evidence** with honest HOLDs. Taxonomies stay separate. It does **not** change classify/analyze algorithms, set promotion thresholds, switch production defaults, implement consumer gates, mandate ML, or reopen closed [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) / [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) / [#1036](https://github.com/jannekbuengener/sample-brain/issues/1036).

`PARTIAL_HOLD` is intentional: dominant measured buckets are enumerated with support, but thin per-class support (often `n=1`) blocks durable consumer FP-rate claims and prevents inventing promotion-ready candidate hypotheses for [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006).

## Evidence source (authoritative for this slice)

| Item | Value |
|---|---|
| Corpus id | `sample-brain.aq4.classification.synthetic.v1` |
| `corpus_version` | `1.0.0` |
| `generator_seed` | `1021001` |
| Clip count | 10 |
| Baseline `candidate_id` | `classification.baseline.v1` |
| Repro command | `python -m src.aq4_classification_baseline --work-dir <external>/aq4-classification-corpus --output <external>/aq4-classification-baseline.json` |
| Repro exit | `AQ4_CLASSIFICATION_BASELINE_MEASURED` |
| External JSON | not committed (repo policy); tables below are portable summaries |

Authoritative plane metrics for diagnostics are taken from a **fresh external rerun** of the frozen baseline harness on current `main` (identical seed / corpus id). Narrative miss pairs in older baseline prose that disagree with this rerun (and with [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) notes) are **not** used as bucket evidence. This slice does not edit the baseline document or reopen [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003).

## Taxonomy separation (normative)

1. **`sample_class`** (`aq4.sample_class`, duration-derived) and **`pred_type`** (`aq4.pred_type_rule`) remain separate planes with separate denominators.
2. Correct `pred_type` does **not** imply correct `sample_class` (and vice versa).
3. Do **not** blend planes into one “autotype quality” score or joint confusion matrix.
4. Uncertain labels (`ambiguous` / `unknown`) stay outside clear-label P/R/F1 denominators.

## Dataset health / thin-corpus warning (prominent)

| Plane | Support (corpus-wide) |
|---|---|
| `sample_class` | oneshot 4, loop 4, ambiguous 1, unknown 1 |
| `pred_type` | Kick / Snare / HiHat-Closed / Impact / Drone / Pad / Loop / OneShot / Drum Loop / unknown — **1 each** |
| Split | CALIBRATION 5, TEST 5 |

**Consequence:** almost every semantic class has support `1`. Observed misses are real (`MEASURED FAILURE`) but **do not** authorize class-FP rates, consumer safety guarantees, or promotion thresholds. Distinguish:

| Token | Meaning |
|---|---|
| `MEASURED FAILURE` | clear-eligible clip with GT ≠ prediction |
| `MEASURED NO_FAILURE_WITH_LIMITED_SUPPORT` | zero clear errors on a plane/slice, but support too thin for “safe” claims |
| `UNKNOWN` | no eligible evidence for that claim |
| `HOLD` | cannot form a durable rate / gate from current corpus |

## Plane summary (clear-eligible only)

### `aq4.sample_class`

| Split | Clear / uncertain | macro-F1 | bal-acc | Clear misses |
|---|---:|---:|---:|---|
| CALIBRATION | 4 / 1 | 1.000 | 1.000 | 0 |
| TEST | 4 / 1 | 1.000 | 1.000 | 0 |

Coverage ≈ 1.0; abstention ≈ 0.0 (surfaces nearly always emit a label).

Ambiguous boundary clip (`duration_sec=1.2`, `label_status=ambiguous`) predicts `oneshot` via ≤1.2 s rule — **uncertain accounting**, not a clear-label error.

### `aq4.pred_type_rule`

| Split | Clear / uncertain | macro-F1 | Clear misses |
|---|---:|---:|---|
| CALIBRATION | 4 / 1 | 0.500 | 2 / 4 |
| TEST | 4 / 1 | 0.750 | 1 / 4 |

### `aq4.pred_type_knn`

```text
HOLD
```

Reason (unchanged from [#1003](https://github.com/jannekbuengener/sample-brain/issues/1003) / baseline): optional kNN override is not reproducible on the synthetic corpus without seed embeddings / private library paths. No fabricated kNN metrics. No ML mandate.

## Error buckets — `sample_class`

| bucket | support | observed error count/rate | severity | affected plane | downstream relevance | evidence confidence |
|---|---:|---|---|---|---|---|
| `loop → oneshot` (clear) | clear loop: 2 CAL + 2 TEST | **0** / `MEASURED NO_FAILURE_WITH_LIMITED_SUPPORT` | low on this corpus | `aq4.sample_class` | Rack loop-row vs point-trigger (#920) | low (n≤2/split) |
| `oneshot → loop` (clear) | clear oneshot: 2 CAL + 2 TEST | **0** / `MEASURED NO_FAILURE_WITH_LIMITED_SUPPORT` | low on this corpus | `aq4.sample_class` | same | low (n≤2/split) |
| `ambiguous duration-boundary` | 1 (CAL, uncertain) | not scored as clear error; predicts `oneshot` at 1.2 s | medium product risk if treated as clear GT | `aq4.sample_class` | boundary policy for consumers near oneshot_max | HOLD for rates |
| `unknown structural label` | 1 (TEST, uncertain) | predicts `oneshot`; excluded from clear denom | medium if consumers ignore unknown | `aq4.sample_class` | fail-closed consumers should not treat as GT | HOLD |
| coverage / abstention gap | 10 clips | coverage 1.0 / abstention 0.0 | medium — no abstain path today | `aq4.sample_class` | forced labels into consumers | measured behavior; safety HOLD |

**Not claimed:** “sample_class is safe for Rack playback.” Zero clear misses on 8 clear clips ≠ consumer gate.

## Error buckets — `pred_type`

Only pairs with **measured** clear-eligible misses are bucketed. Classes with no clear-eligible clip in a split are not invented.

| bucket | support | observed error count/rate | severity | affected plane | downstream relevance | evidence confidence |
|---|---:|---|---|---|---|---|
| `Drum Loop → Loop` | Drum Loop clear: 1 (CAL) | **1 / 1** `MEASURED FAILURE` | medium (semantic collapse to generic Loop) | `aq4.pred_type_rule` | auto-loop eligibility treats Loop/Drum Loop similarly in plan; browsing tags polluted | low (n=1) |
| `Pad → Drone` | Pad clear: 1 (CAL) | **1 / 1** `MEASURED FAILURE` | medium (texture/sustain confusion) | `aq4.pred_type_rule` | auto-loop plan excludes Pad/Drone from v1 loop fill — wrong tag still pollutes metadata | low (n=1) |
| `Impact → Snare` | Impact clear: 1 (TEST) | **1 / 1** `MEASURED FAILURE` | medium (oneshot percussion confusion) | `aq4.pred_type_rule` | auto-attack plan excludes Kick/Snare/Impact from v1 auto-fill; wrong tag still pollutes browse/export | low (n=1) |
| Kick / Snare / HiHat-Closed / Loop / Drone (clear correct) | 1 each where present | **0** misses on those clips | n/a | `aq4.pred_type_rule` | does **not** prove class safety | `MEASURED NO_FAILURE_WITH_LIMITED_SUPPORT` |
| `unknown → Snare` (uncertain) | 1 (TEST) | not scored as clear error; emits Snare | medium if consumers treat unknown as Snare | `aq4.pred_type_rule` | auto-metadata / browse | HOLD |
| Kick↔other drum confusion (beyond measured) | Kick clear: 1 correct | **UNKNOWN** as a family rate | — | `aq4.pred_type_rule` | — | HOLD — do not invent |
| FX / Impact / texture family (beyond Impact→Snare) | Impact only | only Impact→Snare measured | — | `aq4.pred_type_rule` | — | HOLD beyond that pair |
| abstention | all clear | abstention_rate 0.0 | medium — forced tags | `aq4.pred_type_rule` | no “unknown” escape for clear GT misses | measured |

### Measured miss inventory (clip ids only; no host paths)

| clip_id | split | GT `pred_type` | predicted | GT `sample_class` | predicted |
|---|---|---|---|---|---|
| `aq4-synth-drum-loop-cal-001` | CALIBRATION | Drum Loop | Loop | loop | loop (ok) |
| `aq4-synth-pad-loop-cal-001` | CALIBRATION | Pad | Drone | loop | loop (ok) |
| `aq4-synth-impact-oneshot-test-001` | TEST | Impact | Snare | oneshot | oneshot (ok) |

Note the **cross-plane pattern**: all three measured `pred_type` failures keep correct `sample_class`. Aggregate macro-F1 must not hide that; planes stay separate.

## Consumer safety evidence (risk only — no ownership takeover)

AQ4 diagnostics state **what classification evidence shows**. Architecture / wiring remains with existing owners (#936 / #920 / #171 / #173 and related). No FP thresholds are set here.

### Rack playback eligibility (point-trigger vs loop-row)

```text
CONSUMER: Rack playback eligibility / loop-row vs point-trigger
CLASSIFICATION INPUT: sample_class (loop | oneshot) via library resolver (#936); not pred_type
FAILURE MODE: oneshot↔loop flip changes audible path (NATURAL_CYCLE_REPEAT vs point trigger per #920)
MEASURABLE NOW: clear sample_class confusion on synthetic corpus (0 clear flips observed)
EVIDENCE: clear sample_class macro-F1 1.0 on 4+4 clips; ambiguous 1.2 s boundary emits oneshot (uncertain)
RISK: product-relevant near duration boundary; not quantified as FP rate
GATE STATUS: HOLD_INSUFFICIENT_SUPPORT
OWNER: #936 / #920 / Rack runtime — not this slice
```

### Auto-loop

```text
CONSUMER: Auto-loop metadata (#172 / WORKBENCH_AUTO_METADATA_PLAN)
CLASSIFICATION INPUT: pred_type in {Loop, Drum Loop} or sample_class=loop fallback; excludes Pad/Drone/Atmospheric
FAILURE MODE: wrong Loop/Drum Loop/Pad/Drone tags change auto-loop eligibility or exclude set
MEASURABLE NOW: Drum Loop→Loop (still loop-eligible); Pad→Drone (both excluded from v1 auto-loop)
EVIDENCE: measured pred_type misses above; support 1 each
RISK: metadata/browse pollution certain on those clips; auto-loop *behavior* delta for Drum Loop→Loop is limited by plan treating both as loop-eligible
GATE STATUS: PARTIAL_HOLD
OWNER: #171 / #172 plan + follow-on implementation issues — not this slice
```

### Auto-attack / auto-metadata OneShot cue

```text
CONSUMER: Auto-attack / cue for OneShot (#173 / WORKBENCH_AUTO_METADATA_PLAN)
CLASSIFICATION INPUT: pred_type == OneShot or sample_class=oneshot fallback; Kick/Snare/HiHat/Impact excluded from v1 auto-fill
FAILURE MODE: Impact→Snare keeps exclusion from auto-attack; wrong tag still pollutes browse/export; unknown→Snare if treated as clear would mis-tag
MEASURABLE NOW: Impact→Snare measured (n=1); unknown→Snare uncertain only
EVIDENCE: TEST clear Impact miss; unknown clip excluded from clear denom
RISK: metadata pollution; auto-attack path likely unchanged for Impact→Snare under v1 exclude list
GATE STATUS: PARTIAL_HOLD
OWNER: #171 / #173 — not this slice
```

### Filename / folder text as playback authority

```text
CONSUMER: Filename/folder text used as silent playback authority
CLASSIFICATION INPUT: path text (disallowed as silent success per AQ4 KPI + #936)
FAILURE MODE: text override bypasses measured class evidence
MEASURABLE NOW: NOT_APPLICABLE on synthetic corpus (no path-authority bake-off in AQ4 harness)
EVIDENCE: KPI guardrail only
RISK: process/product risk if consumers ignore guardrail
GATE STATUS: NOT_APPLICABLE
OWNER: #936 authority + AQ4 guardrail
```

### Measurable vs HOLD rollup

| GATE STATUS | Consumers |
|---|---|
| MEASURABLE | *(none for durable FP-rate gates on this corpus)* |
| PARTIAL_HOLD | Auto-loop; Auto-attack/auto-metadata |
| HOLD_INSUFFICIENT_SUPPORT | Rack playback eligibility FP-rate gate |
| NOT_APPLICABLE | Filename/folder silent playback authority (policy, not measured here) |

## Candidate hypotheses for #1006

[#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) already compared thin duration (`oneshot_max` 1.0 / 1.5) and brightness (`bright_min=4000`) adapters on the same corpus. Those adapters **did not** recover Pad / Drum Loop / Impact misses and did not dominate `classification.baseline.v1`.

Given:

- every measured `pred_type` miss has support `1`;
- clear `sample_class` has **no** measured clear-label miss to target;
- thin adapters already failed to justify promotion;

this diagnostics slice does **not** invent additional candidate identities for [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006).

```text
NO_JUSTIFIED_CANDIDATE_HYPOTHESIS
```

Interpretation for downstream [#1006](https://github.com/jannekbuengener/sample-brain/issues/1006) / [#1007](https://github.com/jannekbuengener/sample-brain/issues/1007) (formal reconciliation later — not performed here):

- Reuse the existing [#1034](https://github.com/jannekbuengener/sample-brain/issues/1034) compare harness as historical bake-off evidence.
- Do **not** require a new candidate set solely to give #1006 work.
- A justified #1006 exit may be `AQ4_CLASSIFICATION_CANDIDATE_COMPARE_NO_JUSTIFIED_CANDIDATE` once #1006 formally consumes this hypothesis token (Owner/process of #1006 — out of scope here).
- Richer rules / public seeds / human-labeled corpus remain **future** evidence programs, not #1005 candidates.

### Failure modes retained as non-candidate diagnostics (not hypotheses)

These are evidence for humans and for #1006/#1007 reconciliation text — **not** frozen candidate ids:

| Observed failure | Plane | Why not a #1006 candidate now |
|---|---|---|
| Drum Loop → Loop | `pred_type` | n=1; any dedicated rule that flips only this clip overfits synthetic audio |
| Pad → Drone | `pred_type` | n=1; brightness adapter already tried (#1034) without recovery |
| Impact → Snare | `pred_type` | n=1 TEST miss; brightness adapter did not recover (#1034) |

## #1034 / #1036 reconciliation note (evidence only)

| Closed slice | What is reusable | What #1005 adds |
|---|---|---|
| #1034 compare | Reproducible thin-adapter harness + non-promotional observation that adapters do not dominate baseline | Explicit error-bucket taxonomy, support, severity, and `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS` derived from measured buckets (compare lacked a dedicated diagnostics plane) |
| #1036 decision | `KEEP_CURRENT_BASELINE_PATH` from contract/corpus/baseline/compare | Consumer-risk HOLD matrix + thin-corpus tokens; does **not** rewrite or reopen #1036. Formal decision update (if any) belongs to #1007 after #1006 |

#1005 does **not** reopen #1034/#1036 and does not change their production non-action.

## Non-goals (this slice)

- no classify / analyze algorithm or threshold changes
- no production switch / promotion gates
- no Rack / session / auto-metadata implementation
- no new taxonomy
- no kNN reconstruction
- no ML / embedding mandate
- no private audio, absolute host paths, or committed WAV/JSON corpus dumps
- no edits to closed #1003 baseline scope
- no #1006 candidate implementation

## Exit vocabulary

Exactly one:

- `AQ4_CLASSIFICATION_ERROR_BUCKETS_EXPLAINED`
- `AQ4_CLASSIFICATION_DIAGNOSTICS_PARTIAL_HOLD`
- `AQ4_CLASSIFICATION_DIAGNOSTICS_INSUFFICIENT`

This slice exits `AQ4_CLASSIFICATION_DIAGNOSTICS_PARTIAL_HOLD`: measured buckets and consumer-risk mapping are documented with support, planes stay separate, kNN HOLD is preserved, and candidate guidance is explicitly `NO_JUSTIFIED_CANDIDATE_HYPOTHESIS` because thin synthetic support cannot honestly justify new bake-off identities beyond the already-closed #1034 adapters.
