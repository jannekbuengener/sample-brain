# AQ1 Tempo & BeatGrid KPI / Benchmark Contract

**Status:** ACTIVE_SUPPORTING — KPI/benchmark freeze for [#973](https://github.com/jannekbuengener/sample-brain/issues/973)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#943](https://github.com/jannekbuengener/sample-brain/issues/943) (AQ1), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` (domain tokens + portable envelope); [#957](https://github.com/jannekbuengener/sample-brain/issues/957) / `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md` (transform mechanics); [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / `docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md` (runtime methodology); [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / `docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md` (semantic determinism). AQ8 foundation issues are **CLOSED/MERGED** — reuse, do not reopen.

## Architecture outcome

```text
AQ1_TEMPO_BEATGRID_KPI_CONTRACT_FROZEN
```

This document freezes **what AQ1 measures and how evidence is partitioned** before any algorithm change, threshold, or candidate bake-off. It does **not** authorize analyzer changes or production switches.

BeatGrid correctness metrics are **conditionally HOLD** until a public timed beat/downbeat annotation corpus is adopted under a separate scoped issue. Missing BeatGrid annotations are documented as HOLD — never fabricated.

## Ownership

| Concern | Owner |
|---|---|
| AQ1 tempo + BeatGrid metric definitions / eligibility | this contract |
| Half/double/ambiguous/outlier bucket semantics | `src/bpm_evidence.classify_bpm_error` (authoritative ratios) |
| Public tempo baseline path (FSLD, `bpm_evidence=known`) | this contract + existing FSLD eval docs/runner |
| Portable domain tokens + eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Perturbation mechanics / provenance | [#957](https://github.com/jannekbuengener/sample-brain/issues/957) |
| Runtime cold/steady methodology | [#958](https://github.com/jannekbuengener/sample-brain/issues/958) |
| Semantic determinism / cache equivalence | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| BPM / BeatGrid algorithms | out of scope here (`src/analyze.py`, `src/beat_grid.py` remain current surfaces) |
| Promotion thresholds / production switch | future evidence-backed decision issues only |

## Non-goals

- no analyzer / BeatGrid algorithm changes
- no production switch
- no promotion thresholds or numeric gates
- no candidate bake-off harness in this slice
- no private audio, local DBs, or absolute host paths in committed evidence
- no invented BeatGrid annotation corpus
- no single global “analysis quality” score across AQ domains

## Shared KPI vocabulary (#942) — AQ1 selection

Every #942 shared dimension is either **selected** for AQ1 or explicitly **out of scope** here:

| #942 dimension | AQ1 tempo (`aq1.tempo`) | AQ1 BeatGrid (`aq1.beat_grid`) |
|---|---|---|
| correctness | selected | selected when public annotations exist; else HOLD |
| coverage / abstention | selected | selected (eligible vs abstain / no-result) |
| error buckets / confusion | selected (`classify_bpm_error`) | selected when annotations exist (missing/extra beat, etc.) |
| baseline-vs-candidate delta | methodology reserved; no thresholds here | same |
| robustness / metamorphic | expectations only (§ Transform expectations); mechanics → #957 | same |
| determinism / reproducibility | consume #959 by reference | consume #959 by reference |
| runtime median/p95 | consume #958 by reference | consume #958 by reference |
| calibration (confidence-as-probability) | **out of scope** for AQ1 tempo/grid | **out of scope** |
| slice metrics | selected (e.g. MA vs SA; eligible sub-populations) | selected when annotations exist |

## Domain tokens (#956)

Portable `domain` tokens for analysis-eval artifacts:

| Token | Scope |
|---|---|
| `aq1.tempo` | BPM / tempo scalar predictions and relation buckets |
| `aq1.beat_grid` | Beat / downbeat timing series when ground truth exists |

The common envelope in `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` stays domain-neutral. Domain metric semantics remain owned by this AQ1 contract. Do not encode AQ1 thresholds into the shared envelope.

## Separation rule (normative)

1. **Tempo KPI and BeatGrid KPI are separate reporting planes.**
2. BPM-only success does **not** imply beat-grid correctness.
3. Octave-/metre-normalized diagnostic scores may be reported as **extra** diagnostics, but must **never** hide raw half/double errors from `classify_bpm_error`.
4. Missing BeatGrid annotation evidence is `HOLD` / unknown — never numeric zero fabricated as “perfect alignment”.

## Tempo KPI (`aq1.tempo`)

### Public baseline dataset path

| Item | Authority |
|---|---|
| Dataset path | FSLD human-manifest evaluation surface (`docs/benchmarks/FSLD_HUMAN_MANIFEST.md`, `docs/benchmarks/FSLD_CURRENT_ANALYZER_EVAL.md`) |
| Tempo eligibility | only records with `bpm_evidence=known` and finite positive label BPM |
| Analyzer call (current baseline runner) | `extract_features(..., bpm_normalization="none")` — preserves raw BPM visibility |
| Output policy | external untracked JSON only; never commit private audio or local absolute paths |
| Unavailable audio | `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` — do not treat as a 0% quality baseline |

Synthetic half/double evidence in `docs/benchmarks/BPM_HALF_DOUBLE_EVIDENCE.md` remains **HISTORICAL/supporting evidence** for bucket behavior and harness design. It is not a substitute for the FSLD public tempo baseline.

### Selected tempo metrics

Report on the eligible tempo set (`bpm_evidence=known`):

| Metric family | Definition notes |
|---|---|
| Absolute BPM error | mean / median / p95 of `\|predicted − label\|` (finite predicted only) |
| Relative BPM error | mean / median / p95 of `\|predicted − label\| / label` |
| Accuracy within ±0.5 / ±1 / ±2 BPM | fraction of eligible records with finite predicted BPM inside the band |
| Half-time error rate | `classify_bpm_error == "half"` / eligible |
| Double-time error rate | `classify_bpm_error == "double"` / eligible |
| Ambiguous rate | `ambiguous` / eligible |
| Outlier rate | `outlier` / eligible (includes non-positive / missing prediction per classifier) |
| Coverage / abstention / no-result | share of intended tempo-eligible material with no usable prediction, plus explicit exclusion reasons for non-periodic / one-shot material |

Aggregates that omit half/double buckets are incomplete for AQ1. Relation rates must remain visible even when absolute error looks small after naive octave folding.

### Error buckets — freeze by reference

Authoritative classifier: `src/bpm_evidence.classify_bpm_error`.

| Class | Ratio `actual / label` (authoritative constants in module) | Meaning |
|---|---|---|
| `correct` | `[0.95, 1.05]` | within ±5% of label |
| `half` | `[0.45, 0.55]` | ~half-time |
| `double` | `[1.90, 2.10]` | ~double-time |
| `ambiguous` | `(0.2, 5.0)` excluding the bands above | plausible BPM, not correct/half/double |
| `outlier` | otherwise, or non-positive / missing actual, or non-positive label | wild / unavailable |

Do not redefine these ratios in AQ1 docs independently of `classify_bpm_error`. Diagnostic octave-normalized scores are optional add-ons only.

## BeatGrid KPI (`aq1.beat_grid`) — conditional HOLD

### Status

```text
BEATGRID_PUBLIC_ANNOTATION_CORPUS = HOLD
```

There is **no** frozen public Sample Brain beat/downbeat annotation corpus in-repo for AQ1 scoring. This contract therefore **lists** BeatGrid metrics for later activation but does **not** claim measurable BeatGrid correctness baselines, invent annotations, or pretend private library timing is a public gate.

Activation requires a separate scoped issue that freezes:

- public/reference timed beat and/or downbeat annotations;
- timing tolerance(s);
- join keys compatible with #956 portable `record_id`s;
- DEVELOPMENT/CALIBRATION vs TEST/HOLDOUT partition for that corpus.

Until then: report BeatGrid KPI status as HOLD / unknown. Runtime existence of `src/beat_grid.py` does not satisfy BeatGrid correctness KPI.

### Metrics to activate when annotations exist

| Metric family | Notes |
|---|---|
| Beat precision / recall / F1 | at a frozen timing tolerance (tolerance not set here) |
| Median + p95 absolute beat timing error (ms) | against annotated beat times |
| Beat phase / alignment error | relative to annotated grid |
| Downbeat precision / recall / F1 | when downbeat annotations exist |
| Bar-start / downbeat alignment error | when applicable |
| Missing / extra beat rate | over- and under-detection |

Operational BeatGrid signals (fallback frequency, backend identity) may still be observed under #958/#959 without claiming correctness against annotations.

## Partition policy

| Role | Policy |
|---|---|
| DEVELOPMENT / CALIBRATION | tuning, exploration, threshold discovery — never the sole promotion proof |
| TEST / HOLDOUT | frozen evaluation; **no tuning on TEST/HOLDOUT** |

FSLD human-manifest splits use `CALIBRATION` and `TEST` (`docs/benchmarks/FSLD_HUMAN_MANIFEST.md`). Treat FSLD `CALIBRATION` as the DEVELOPMENT/CALIBRATION role and FSLD `TEST` as TEST/HOLDOUT for AQ1 tempo baselines.

Private library material may be a reality check only. It must not set public promotion thresholds and must not enter committed artifacts with private paths or audio.

## Eligibility / abstention

| Material | Expected AQ1 behavior |
|---|---|
| Periodic material with known tempo labels (`bpm_evidence=known`) | eligible for tempo correctness metrics |
| One-shots / non-periodic / no defined tempo | may **abstain** or be excluded with an explicit reason — do not fabricate tempo to force a score |
| Missing public audio for an otherwise eligible record | status evidence (`audio_missing` / equivalent); not a zero-error success |
| Controlled analyzer failure | explicit failure/exclusion status; never coerce to numeric zero |

Coverage and abstention rates are first-class AQ1 metrics, not afterthoughts.

## Transform expectations (#957) — expectations only

Mechanics and provenance live in `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md`. AQ1 only declares **semantic expectations** (no tolerances, no gates):

| #957 transform | AQ1 tempo expectation | AQ1 BeatGrid expectation |
|---|---|---|
| `gain` | **invariant** (tempo claim should survive) | **invariant** when grid KPI is active |
| `peak_normalize` | **invariant** | **invariant** when active |
| `to_mono` / `to_stereo` | **invariant** where channel conversion is musically irrelevant | **invariant** when active |
| `resample` | **invariant** for tempo scalar (within resampling fidelity limits to be set later) | timing series must stay comparable on a shared timebase; exact tolerance later |
| `pad_silence` / `trim` | tempo scalar **invariant**; absolute beat times **transform** (shift) when grid KPI is active | grid times **transform** with pad/trim; relative intervals may remain invariant |
| `pitch_shift` | **invariant** for tempo (pitch-only) | **invariant** for relative beat spacing when active |
| `time_stretch` | **transforming** — expected BPM scales with stretch rate; half/double buckets evaluated against transformed label | **transforming** — beat times scale with stretch; annotations must be transformed consistently |

Unsupported or unsafe transforms remain fail-closed under #957. Do not approximate them inside AQ1.

## Operational / determinism dimensions (by reference)

| Dimension | Authority | AQ1 use |
|---|---|---|
| Runtime median / p95 (cold vs steady) | #958 / `ANALYZER_RUNTIME_METHODOLOGY_V1.md` | report for tempo path and BeatGrid backends; no SLA in this freeze |
| Fallback frequency / backend identity | current BeatGrid surfaces + #958 provenance | operational evidence only |
| Semantic repeatability / cache equivalence | #959 / `ANALYZER_SEMANTIC_DETERMINISM_V1.md` | identical input + decision-relevant config → comparable semantic projection |
| Portable export | #956 / `SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` | carry AQ1 observations without private paths |

Missing/failed/timeout runs remain explicit evidence — never fabricated `0` ms or perfect scores.

## Evidence reuse (do not reopen)

| Surface | Role |
|---|---|
| `classify_bpm_error` + `docs/benchmarks/BPM_HALF_DOUBLE_EVIDENCE.md` | bucket authority + synthetic octave-error evidence |
| FSLD manifest + current-analyzer eval | public tempo baseline path (`bpm_evidence=known`) |
| Closed #594 / #595 / #596 (and related) | historical public-first key/tempo validation evidence |
| Closed #956–#960 under #950 | reusable AQ8 foundation; cite, do not reopen |

## Exit vocabulary

Exactly one:

- `AQ1_TEMPO_BEATGRID_KPI_CONTRACT_FROZEN` — tempo KPI + partitions + buckets frozen; BeatGrid metrics listed with annotation corpus HOLD is allowed
- `AQ1_KPI_CONTRACT_INSUFFICIENT` — tempo freeze cannot be stated from available public contracts/evidence
- `BLOCKED_BY_MISSING_BEAT_ANNOTATION_CORPUS` — **only** if tempo freeze itself cannot proceed without BeatGrid annotations (not the default path)

This slice exits `AQ1_TEMPO_BEATGRID_KPI_CONTRACT_FROZEN` with BeatGrid correctness metrics on HOLD for lack of a public annotation corpus.
