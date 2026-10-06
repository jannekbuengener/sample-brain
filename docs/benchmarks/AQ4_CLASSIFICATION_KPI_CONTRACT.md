# AQ4 Sample classification, type & tag KPI / Benchmark Contract

**Status:** ACTIVE_SUPPORTING — KPI/benchmark freeze for [#1001](https://github.com/jannekbuengener/sample-brain/issues/1001)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (AQ4), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Related product / ownership (not AQ4 measurement authority):** [#936](https://github.com/jannekbuengener/sample-brain/issues/936) / `docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md` (Rack user-channel resolver ownership); [#171](https://github.com/jannekbuengener/sample-brain/issues/171) / [#173](https://github.com/jannekbuengener/sample-brain/issues/173) (auto-metadata consumers); [#920](https://github.com/jannekbuengener/sample-brain/issues/920) / `docs/LOOP_ROW_PLAYBACK_CONTRACT.md` (loop-row playback semantics that *consume* `sample_class`).  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` (domain tokens + portable envelope); [#957](https://github.com/jannekbuengener/sample-brain/issues/957) / `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md` (transform mechanics); [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / `docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md` (runtime methodology); [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / `docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md` (semantic determinism). AQ8 foundation issues are **CLOSED/MERGED** — reuse, do not reopen.

Current analysis surfaces (read-only context for this freeze; not changed here): `src/analyze.py` (`_duration_class` → `features.class` / Workbench `sample_class` binary `loop`/`oneshot`), `src/classify.py` (`rule_type` + optional kNN override → `features.pred_type`).

## Architecture outcome

```text
AQ4_CLASSIFICATION_KPI_CONTRACT_FROZEN
```

This document freezes **what AQ4 measures, how binary structural class stays separate from semantic type/tags, and how evidence is partitioned** before any taxonomy change, threshold work, or candidate bake-off. It does **not** authorize classify/analyze algorithm changes, Rack ownership changes, or production switches.

There is **no** frozen labeled public/sanitized Sample Brain classification benchmark corpus in-repo for AQ4 scoring. Metric **definitions**, taxonomy separation, eligibility, partitions, dataset-health checks, and #957 expectations are frozen here; measurable correctness baselines remain **HOLD** until a public/sanitized/synthetic labeled corpus is adopted under a separate scoped issue.

## Ownership

| Concern | Owner |
|---|---|
| AQ4 `sample_class` / `pred_type` / tag metric definitions / eligibility | this contract |
| Labeled public/sanitized/synthetic classification corpus adoption | future scoped issue under [#946](https://github.com/jannekbuengener/sample-brain/issues/946) (not this freeze) |
| Portable domain tokens + eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Perturbation mechanics / provenance | [#957](https://github.com/jannekbuengener/sample-brain/issues/957) |
| Runtime cold/steady methodology | [#958](https://github.com/jannekbuengener/sample-brain/issues/958) |
| Semantic determinism / cache equivalence | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| Duration `sample_class` / rule+kNN `pred_type` algorithms | out of scope here (current surfaces remain as-is) |
| Rack user-channel classification *ownership* / injection | [#936](https://github.com/jannekbuengener/sample-brain/issues/936) — consumes measured quality; does not own AQ4 metrics |
| Promotion thresholds / production switch | future evidence-backed decision issues only |
| Consumer safety gates (Rack / auto-metadata / auto-loop / auto-attack) | **future dependents** — listed below; not implemented or gated here |

## Non-goals

- no classify / analyze algorithm changes
- no production switch
- no promotion thresholds or numeric gates
- no ML mandate (deterministic/classical methods remain preferred until evidence shows otherwise)
- no session / persistence redesign
- no invented / fabricated human labels or private-audio “public” baseline
- no collapse of `sample_class` into `pred_type` (or the reverse)
- no silent playback authority from filename/folder text
- no consumer safety-gate implementation in this slice
- no single global “analysis quality” score across AQ domains

## Shared KPI vocabulary (#942) — AQ4 selection

Every #942 shared dimension is either **selected** for AQ4 or explicitly **out of scope / HOLD** here:

| #942 dimension | AQ4 sample_class (`aq4.sample_class`) | AQ4 pred_type / tags (`aq4.pred_type`) |
|---|---|---|
| correctness | selected when labeled corpus exists; else HOLD for measurable baseline | selected when labeled corpus exists; else HOLD |
| coverage / abstention | selected (unknown / abstain / no-result policy) | selected (unknown / abstain / class coverage) |
| error buckets / confusion | selected (binary confusion; definitions) | selected (per-class confusion; high-impact FP slices) |
| baseline-vs-candidate delta | methodology reserved; no thresholds here | same — baseline duration-only vs rule vs optional kNN **separately** |
| robustness / metamorphic | expectations only (§ Transform expectations); mechanics → #957 | same |
| determinism / reproducibility | consume #959 by reference | consume #959 by reference |
| runtime median/p95 | consume #958 by reference | consume #958 by reference |
| calibration (confidence-as-probability) | **HOLD / out of scope** (binary class has no calibrated score today) | **HOLD** — rule/kNN sigmoid-like scores are **not** calibrated probability unless explicitly promoted |
| slice metrics | selected (ambiguous duration band; support slices) | selected (per-class support; high-impact consumer classes) |

## Domain tokens (#956)

Portable `domain` tokens for analysis-eval artifacts:

| Token | Scope |
|---|---|
| `aq4.sample_class` | Binary/structural class: `loop` vs `oneshot` (and explicit unknown/abstain when introduced) |
| `aq4.pred_type` | Semantic primary type / autotype label (e.g. Kick, Snare, HiHat-Closed, Impact, Drone, Pad, Loop, OneShot, Drum Loop, FX) and related multi-tag / descriptor evaluation when labeled |

Secondary descriptor tags produced by current rules (`Bright`, `Dark`, `Punchy`, `Atmospheric`) are **not** a third collapsed taxonomy with `sample_class`. When evaluated, report them under `aq4.pred_type` as an explicit multi-label / descriptor slice — never as a substitute for binary `sample_class`, and never as a silent rewrite of the primary `pred_type` label.

The common envelope in `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` stays domain-neutral. Domain metric semantics remain owned by this AQ4 contract. Do not encode AQ4 thresholds into the shared envelope.

## Separation rule (normative)

1. **`sample_class` (loop/oneshot) and `pred_type` / semantic tags are separate taxonomies and separate reporting planes.**
2. Correct `pred_type` does **not** imply correct `sample_class` (and vice versa).
3. Do **not** collapse the two into one label space for gates, baselines, or portable `domain` tokens.
4. Current production surfaces keep the split: duration-derived class in analyze (`features.class` / Workbench `sample_class`) vs rule/kNN primary label in `features.pred_type`.
5. Do **not** silently infer playback or Rack authority from filename/folder text when scoring AQ4 or when interpreting consumer risk.
6. Missing labeled public corpus evidence is `HOLD` / unknown — never a fabricated zero that looks like perfect precision, perfect abstention, or perfect balance.
7. Baseline paths must be reported **separately**: duration-only `sample_class`, rule-only `pred_type`, and optional kNN-override `pred_type` — never a single blended “autotype quality” number that hides which path produced the label.

## Taxonomy freeze (definitions for metrics; not a product rename)

### Binary / structural (`aq4.sample_class`)

| Label | Current surface meaning (context only) |
|---|---|
| `oneshot` | duration-derived class when duration ≤ 1.2 s (`src/analyze.py` `_duration_class`) |
| `loop` | duration-derived class when duration > 1.2 s |
| `unknown` / abstain | **policy reserved** — not currently emitted by `_duration_class`; if introduced, must be an explicit outcome with first-class coverage metrics |

The 1.2 s threshold is **current-surface context**, not a promotion gate frozen here. Threshold changes require a later evidence-backed decision under #946.

### Semantic primary types (`aq4.pred_type`)

Core labels currently preferred by `rule_type` (order preserved from `src/classify.py`):

`Kick`, `Snare`, `HiHat-Closed`, `Impact`, `Drone`, `Pad`, `Loop`, `OneShot`, `Drum Loop`, with fallback `FX` (oneshot path) or `Loop` (loop path) when no core tag matches.

Descriptor companions (`Bright`, `Dark`, `Punchy`, `Atmospheric`) may appear in the rule tag list but only the primary `pred` is written to `features.pred_type` today. Benchmarks that evaluate descriptors must state that multi-label slice explicitly.

Taxonomy **eligibility** for a future corpus must freeze which labels are in-scope before computing metrics. Expanding or renaming classes is out of scope for this freeze.

## Public / sanitized / synthetic corpus policy

### Status

```text
AQ4_LABELED_PUBLIC_CLASSIFICATION_CORPUS = HOLD
```

There is **no** frozen labeled public or sanitized Sample Brain classification benchmark corpus in-repo for AQ4 scoring. FSLD human-manifest fields used by AQ1/AQ2 do **not** supply `sample_class` / `pred_type` ground truth. Runtime existence of `src/analyze.py` / `src/classify.py` does **not** satisfy AQ4 correctness KPI.

This contract therefore:

- **owns** metric definitions, plane separation, partitions, dataset-health checks, confidence HOLD, and #957 expectations;
- **does not** invent private-audio human labels or fabricated baseline scores;
- **does not** treat optional local kNN seed CSVs (may contain machine-local paths) as a public gate corpus.

### Eligibility for a future corpus (definitions only)

A future scoped adoption issue must freeze at least:

| Requirement | Notes |
|---|---|
| Label planes | separate `sample_class` and `pred_type` (and optional multi-tag descriptors) columns / fields |
| Label provenance | public reference, sanitized redistributable, and/or deterministic synthetic — never private paths in committed artifacts |
| Unknown / ambiguous policy | explicit uncertain-label accounting; do not force a class |
| Join keys | compatible with #956 portable `record_id`s |
| Partition | DEVELOPMENT/CALIBRATION vs TEST/HOLDOUT |
| Leakage policy | duplicate / near-duplicate checks across partitions |
| Synthetic role | may unblock controlled structural tests; not a silent substitute for human semantic labels on hard classes |

Private library material and local seed lists may be a **reality check only**. They must not set public promotion thresholds and must not enter committed artifacts with private paths or audio.

## Binary / structural class KPI (`aq4.sample_class`)

### Metrics to activate when labeled corpus exists

Report with **explicit denominators**:

| Metric family | Definition notes |
|---|---|
| Per-class precision / recall / F1 | for `loop` and `oneshot` (and `unknown` if emitted) |
| Macro-F1 | unweighted mean of per-class F1 on the eligible label set |
| Balanced accuracy | mean of per-class recall; preferred companion when class support is imbalanced |
| Confusion matrix | predicted × label; keep abstain/unknown as explicit rows/columns when present |
| Ambiguous / unknown coverage | share with explicit abstain / unknown when that outcome exists |
| False-positive rates for high-impact class | especially wrong `loop` vs `oneshot` where Rack / loop-row / point-trigger consumers differ |

Aggregates that hide one class behind overall accuracy alone are incomplete for AQ4.

## Semantic type / tag KPI (`aq4.pred_type`)

### Metrics to activate when labeled corpus exists

| Metric family | Definition notes |
|---|---|
| Macro-F1 | **primary aggregate** for multi-class `pred_type` |
| Per-class precision / recall / F1 | for each eligible semantic label |
| Confusion matrix | predicted × label; report high-confusion pairs explicitly |
| Class coverage / abstention | share with no usable `pred_type` / explicit unknown on material where a decision is expected |
| False-positive rates for high-impact classes | Kick, Snare, and other classes consumed by browsing, auto-metadata, or playback-adjacent filters — FP is first-class, not only FN |
| Top-N accuracy | **only if** the product surface under test actually exposes ranked alternatives; current `pred_type` write path is single-label — default **out of scope** unless a ranked surface is under evaluation |
| Multi-label / descriptor slice | optional; report separately from primary `pred_type`; never replace binary `sample_class` metrics |

Forced guesses that inflate coverage by never abstaining are an AQ4 failure mode, not a success.

### Baseline path separation (methodology)

When measuring current surfaces, report separately:

| Path | Surface context |
|---|---|
| Duration-only `sample_class` | `src/analyze.py` `_duration_class` |
| Rule-only `pred_type` | `src/classify.py` `rule_type` primary tag (kNN disabled) |
| Optional kNN override `pred_type` | `write_autotype_to_db(use_knn=True)` when seeds/embeddings exist |

Do not blend rule and kNN into one unlabeled “autotype” score for promotion evidence.

## Dataset health (first-class)

Report whenever a labeled AQ4 corpus (or candidate corpus) is used:

| Check | Notes |
|---|---|
| Class balance | support/count per `sample_class` and per `pred_type` label |
| Support floors | call out labels with insufficient support for stable per-class F1 |
| Duplicate / near-duplicate leakage | same or near-identical audio (or identical content hash) across DEVELOPMENT/CALIBRATION and TEST/HOLDOUT |
| Uncertain-label accounting | human disagreement / ambiguous labels retained as explicit status — not silently majority-forced into TEST |
| Path / filename leakage | do not score models that read private paths; committed evidence must remain path-safe under #956 |

Missing health evidence is HOLD / unknown — not an implied clean corpus.

## Confidence / calibration — HOLD

| Surface | Status |
|---|---|
| Rule-based `pred_type` | no calibrated probability today |
| kNN `confidence` (`_sigmoid` of aggregated similarity) | relative ranking aid for override threshold only — **not** calibrated probability |
| Continuous claim score for AQ4 | **HOLD** — not defined in this freeze |
| Brier / reliability / calibration curves | **HOLD** — only if a score is later explicitly promoted to calibrated confidence |

Do not treat existing sigmoid-like kNN scores as calibrated probability. Do not invent a claim score inside this contract. When a future scoped issue promotes one, calibration metrics become selectable under #942; until then report them as HOLD / unknown.

## Partition policy

| Role | Policy |
|---|---|
| DEVELOPMENT / CALIBRATION | tuning, exploration, threshold / taxonomy discovery — never the sole promotion proof |
| TEST / HOLDOUT | frozen evaluation; **no tuning on TEST/HOLDOUT** |

When a public/sanitized/synthetic AQ4 corpus is adopted, its split labels must map explicitly onto these roles (same discipline as FSLD `CALIBRATION` → DEVELOPMENT/CALIBRATION and `TEST` → TEST/HOLDOUT for AQ1/AQ2).

Private library material may be a reality check only. It must not set public promotion thresholds and must not enter committed artifacts with private paths or audio.

## Eligibility / abstention

| Material | Expected AQ4 behavior |
|---|---|
| Labeled binary class material | eligible for `aq4.sample_class` correctness when corpus active |
| Labeled semantic type material | eligible for `aq4.pred_type` correctness when corpus active |
| Ambiguous / uncertain human labels | retain as uncertain; do not force into correctness denominators without stating the policy |
| Insufficient evidence for a semantic type | may abstain / unknown — not a forced `FX`/`Loop` success for KPI purposes when abstention is the product-correct outcome |
| Missing public audio for an otherwise eligible record | status evidence (`audio_missing` / equivalent); not a zero-error success |
| Controlled analyzer / classify failure | explicit failure/exclusion status; never coerce to numeric zero |

Coverage and abstention / unknown rates are first-class AQ4 metrics, not afterthoughts.

## Transform expectations (#957) — expectations only

Mechanics and provenance live in `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md`. AQ4 only declares **semantic expectations** where classification semantics justify invariance (no tolerances, no gates). Issue #1001 explicitly calls out gain / channel / resample where semantics justify:

| #957 transform | AQ4 `sample_class` expectation | AQ4 `pred_type` expectation |
|---|---|---|
| `gain` | **invariant** — binary class should not flip from level alone | **invariant** where type semantics are level-independent |
| `peak_normalize` | **invariant** | **invariant** where type semantics are level-independent |
| `to_mono` / `to_stereo` | **invariant** where channel conversion is musically irrelevant | **invariant** where irrelevant |
| `resample` | **invariant** for duration-derived class within resampling fidelity limits to be set later | **invariant** for type claim within later fidelity limits |
| `pad_silence` / `trim` | **may transform** duration-derived `sample_class` when pad/trim crosses the duration boundary — annotations/labels must follow the transformed duration policy | type claim **invariant** only when the sonic identity remains representative; edge cases remain explicit exclusions later |
| `pitch_shift` | **invariant** for binary class | **invariant** for type where pitch-only change should not rename the instrument/role class (domain-specific exceptions later) |
| `time_stretch` | **may transform** duration-derived class if duration crosses the structural threshold | **invariant** for type where stretch preserves role identity; duration-sensitive rule features must be evaluated against transformed labels |

Unsupported or unsafe transforms remain fail-closed under #957. Do not approximate them inside AQ4.

## Operational / determinism dimensions (by reference)

| Dimension | Authority | AQ4 use |
|---|---|---|
| Runtime median / p95 (cold vs steady) | #958 / `ANALYZER_RUNTIME_METHODOLOGY_V1.md` | report for analyze class path and classify rule/kNN paths; no SLA in this freeze |
| Semantic repeatability / cache equivalence | #959 / `ANALYZER_SEMANTIC_DETERMINISM_V1.md` | identical input + decision-relevant config → comparable `sample_class` / `pred_type` projection |
| Portable export | #956 / `SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` | carry AQ4 observations without private paths |

Missing/failed/timeout runs remain explicit evidence — never fabricated `0` ms or perfect F1.

## Consumer safety gates — future dependents only

These consumers may **depend on** AQ4 evidence later. They are **not** implemented, thresholded, or owned by this freeze:

| Consumer / risk | Why AQ4 evidence matters | Ownership remains |
|---|---|---|
| Rack playback eligibility / point-trigger vs loop-row | wrong `sample_class` can change audible playback path | #936 / #920 / Rack runtime issues |
| Auto-metadata classification consumers | wrong `pred_type` / tags pollute browsing and export metadata | #171 / #173 (and related) |
| Auto-loop / auto-attack adjacent flows | false-positive structural or semantic class can trigger unsafe automation | product/architecture issues that consume AQ4; not this contract |
| Filename/folder text as playback authority | explicitly **disallowed** as a silent success path | #936 authority + AQ4 guardrail |

List = dependency notice only. No numeric FP gates, no wiring changes, and no promotion of consumer thresholds in this slice.

## Evidence reuse (do not reopen)

| Surface | Role |
|---|---|
| `src/analyze.py` `_duration_class` | current binary class surface (baseline candidate later) |
| `src/classify.py` `rule_type` / optional kNN | current semantic type surface (baseline candidates later, reported separately) |
| `docs/USER_CHANNEL_CLASSIFICATION_AUTHORITY.md` | Rack ownership boundary; consumes classification quality, does not redefine AQ4 metrics |
| `docs/benchmarks/ANALYZER_PORTABLE_OUTPUT_BASELINE.md` | portable-output notes for classification strings |
| Closed #956–#960 under #950 | reusable AQ8 foundation; cite, do not reopen |

## Exit vocabulary

Exactly one:

- `AQ4_CLASSIFICATION_KPI_CONTRACT_FROZEN` — `sample_class` vs `pred_type` separation, metric definitions, partitions, dataset-health checks, confidence HOLD, #957 expectations, and consumer-gate dependency list frozen; labeled public/sanitized corpus may remain HOLD for measurable baselines
- `AQ4_KPI_CONTRACT_INSUFFICIENT` — freeze cannot be stated from available program contracts / surface reality

This slice exits `AQ4_CLASSIFICATION_KPI_CONTRACT_FROZEN` with:

```text
AQ4_LABELED_PUBLIC_CLASSIFICATION_CORPUS = HOLD
```

Corpus adoption for measurable baselines is a future scoped issue under [#946](https://github.com/jannekbuengener/sample-brain/issues/946).
