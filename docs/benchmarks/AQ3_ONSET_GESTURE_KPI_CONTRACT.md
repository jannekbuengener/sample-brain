# AQ3 Onset, Transient & Gesture timing KPI / Benchmark Contract

**Status:** ACTIVE_SUPPORTING — KPI/benchmark freeze for [#991](https://github.com/jannekbuengener/sample-brain/issues/991)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#945](https://github.com/jannekbuengener/sample-brain/issues/945) (AQ3), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Boundary:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680) owns Vocal/Beatbox → Pattern product/R&D (retrieval, clustering-as-product, Rack mutation, UI). AQ3 owns **measurement quality of onset / attack / gesture timing only** — do not duplicate #680 product scope.  
**Related product history (not AQ3 authority):** [#171](https://github.com/jannekbuengener/sample-brain/issues/171) / [#173](https://github.com/jannekbuengener/sample-brain/issues/173) auto-metadata attack/cue flow.  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` (domain tokens + portable envelope); [#957](https://github.com/jannekbuengener/sample-brain/issues/957) / `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md` (transform mechanics); [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / `docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md` (runtime methodology); [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / `docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md` (semantic determinism). AQ8 foundation issues are **CLOSED/MERGED** — reuse, do not reopen.

Current analysis surfaces (read-only context for this freeze; not changed here): `src/workbench_attack_suggest.py` (`suggest_attack_ms` / `AttackSuggestion`), `src/gesture_analysis.py` (`analyze_gesture_audio` / `_detect_onset_times` / `GestureEvent`).

## Architecture outcome

```text
AQ3_ONSET_GESTURE_KPI_CONTRACT_FROZEN
```

This document freezes **what AQ3 measures, how the three timing planes separate, and how evidence is partitioned** before any onset/gesture algorithm change, tolerance freeze, or candidate bake-off. It does **not** authorize analyzer changes, #680 product work, or production switches.

Public/synthetic **annotated** onset / attack / gesture timing corpora are **HOLD** for measurable correctness baselines until a separate scoped issue adopts them. Metric **definitions**, eligibility, partitions, difficult buckets, and #957 expectations may still freeze without inventing annotations or fabricating corpus numbers.

## Ownership

| Concern | Owner |
|---|---|
| AQ3 onset / attack / gesture metric definitions / eligibility | this contract |
| Timing tolerance windows (ms) for precision/recall/F1 | **to-be-frozen** under a later benchmark-owned slice — not invented here |
| Public/synthetic annotated corpus adoption | future scoped issue; until then HOLD for measurable baselines |
| Portable domain tokens + eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Perturbation mechanics / provenance | [#957](https://github.com/jannekbuengener/sample-brain/issues/957) |
| Runtime cold/steady methodology | [#958](https://github.com/jannekbuengener/sample-brain/issues/958) |
| Semantic determinism / cache equivalence | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| Onset / attack / gesture algorithms | out of scope here (current surfaces remain as-is) |
| #680 Pattern Core / retrieval / Rack / UI | **out of scope** — product R&D, not AQ3 measurement |
| Promotion thresholds / production switch | future evidence-backed decision issues only |

## Non-goals

- no onset / attack / gesture algorithm changes
- no production switch
- no promotion thresholds or numeric gates
- no invented timing tolerances presented as frozen numbers
- no invented / fabricated annotated corpus or private-audio “public” baseline
- no #680 product duplication (sample retrieval, role clustering-as-selection, Rack mutation, microphone/UI)
- no hidden quantization policy as an AQ3 success criterion
- no forced event when evidence is insufficient
- no single global “analysis quality” score across AQ domains

## Shared KPI vocabulary (#942) — AQ3 selection

Every #942 shared dimension is either **selected** for AQ3 or explicitly **out of scope / HOLD** here:

| #942 dimension | AQ3 onset (`aq3.onset`) | AQ3 attack (`aq3.attack`) | AQ3 gesture (`aq3.gesture`) |
|---|---|---|---|
| correctness | selected when public/synthetic annotations exist; else HOLD for measurable baseline | selected when attack-marker annotations exist; else HOLD | selected when multi-event / interval annotations exist; else HOLD |
| coverage / abstention | selected (no-result / empty / too_short / unreadable) | selected (abstain on ambiguous material) | selected (empty / too_short / unreadable; event-count coverage) |
| error buckets / confusion | selected (missed / duplicate / soft-vs-hard; definitions) | selected (early/late; false attack on silence/noise) | selected (order break; interval/shape error classes) |
| baseline-vs-candidate delta | methodology reserved; no thresholds here | same | same |
| robustness / metamorphic | expectations only (§ Transform expectations); mechanics → #957 | same | same |
| determinism / reproducibility | consume #959 by reference | consume #959 by reference | consume #959 by reference |
| runtime median/p95 | consume #958 by reference | consume #958 by reference | consume #958 by reference |
| calibration (confidence-as-probability) | **out of scope** (heuristic labels such as attack `confidence` strings are relative evidence only) | **out of scope** until an explicitly promoted continuous score exists | **out of scope** |
| slice metrics | selected (difficult buckets below) | selected (same buckets + attack-specific slices) | selected (same buckets + multi-event slices) |

## Domain tokens (#956)

Portable `domain` tokens for analysis-eval artifacts:

| Token | Scope |
|---|---|
| `aq3.onset` | Multi-event / onset detection timing series and detection rates |
| `aq3.attack` | Single attack / cue marker suggestion against reference attack time |
| `aq3.gesture` | Gesture/rhythm preservation: intervals, timing shape, projected trigger timing, event order |

The common envelope in `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` stays domain-neutral (it already cites `aq3.onset` as an example token). Domain metric semantics remain owned by this AQ3 contract. Do not encode AQ3 thresholds into the shared envelope.

## Separation rule (normative)

1. **Event detection, attack/cue suggestion, and gesture/rhythm preservation are separate reporting planes.**
2. Onset detection success does **not** imply attack-marker accuracy.
3. Attack-marker accuracy does **not** imply gesture interval / shape / order preservation.
4. Gesture timing quality does **not** imply sound-role clustering, retrieval ranking, or Pattern Core composition quality (#680 / AQ5 / related product surfaces).
5. Timing correctness is separate from sound-role clustering and retrieval quality.
6. Missing annotation evidence is `HOLD` / unknown — never a fabricated zero that looks like perfect timing, perfect recall, or perfect abstention.
7. Do not force an event when evidence is insufficient; abstention / empty / no-result remain first-class outcomes.

## Public / synthetic corpus policy — HOLD for measurable baselines

### Status

```text
AQ3_PUBLIC_ANNOTATED_TIMING_CORPUS = HOLD
```

There is **no** frozen public Sample Brain annotated onset / attack-marker / multi-event gesture timing corpus in-repo for AQ3 scoring. FSLD and other public analyzer baselines used by AQ1/AQ2 do **not** currently supply timed onset/attack/gesture ground truth for these planes.

This contract therefore:

- **freezes** metric definitions, plane separation, partitions, difficult buckets, and #957 expectations;
- **does not** claim measurable correctness baselines;
- **does not** invent annotations, synthetic “fake corpus” scores, or private-library gates.

Activation of measurable baselines requires a separate scoped issue that freezes at least:

- public and/or synthetic annotated ground truth (attack-marker set separate from multi-event gesture set);
- timing tolerance window(s) (benchmark-owned; see below);
- join keys compatible with #956 portable `record_id`s;
- DEVELOPMENT/CALIBRATION vs TEST/HOLDOUT partition for that corpus.

Private library or human reality-check cases may later support diagnosis only. They must not set public promotion thresholds and must not enter committed artifacts with private paths or audio.

Runtime existence of `src/workbench_attack_suggest.py` or `src/gesture_analysis.py` does **not** satisfy AQ3 correctness KPI.

### Synthetic corpus note

Synthetic fixtures (deterministic clicks, padded silence, gain-scaled copies) are allowed later as **controlled** materials under #957 and a future corpus issue. They are not a substitute for human/reference annotations on soft-attack / layered / noisy buckets, and must not be presented as a completed public annotated corpus in this freeze.

## Timing tolerances — to-be-frozen

Precision / recall / F1 and within-tolerance accuracy require explicit timing windows (examples discussed in #945 include 20 ms / 50 ms). Exact tolerances are **benchmark-owned later**.

| Item | Status in this freeze |
|---|---|
| Candidate windows (e.g. 20 ms, 50 ms) | named as **to-be-frozen** candidates only |
| Authoritative tolerance set | **not** set here — do not treat examples as gates |
| Reporting rule once frozen | state the window with every P/R/F1 or within-tolerance rate; never omit the window |

Do not invent fake corpus numbers or pretend a tolerance is frozen by writing it into a baseline table in this slice.

## Event detection KPI (`aq3.onset`)

### Metrics to activate when annotations exist

Report with **explicit denominators** and a stated timing tolerance once that tolerance is frozen:

| Metric family | Definition notes |
|---|---|
| Onset precision / recall / F1 | at a frozen timing tolerance window (tolerance **to-be-frozen**) |
| Median + p95 absolute onset timing error (ms) | against annotated onset times (matched pairs under the tolerance policy) |
| Missed-onset rate | annotated onsets without a matched prediction |
| Duplicate / extra-onset rate | predictions without a matched annotation |
| Event-count absolute / relative error | `|predicted_count − label_count|` and relative form where label_count > 0 |
| Coverage / no-result rate | share of intended eligible material with empty / no usable onset series, plus explicit status (`empty`, `too_short`, `unreadable`, controlled failure) |

Aggregates that hide missed vs duplicate errors behind a single opaque score are incomplete for AQ3.

## Attack / cue suggestion KPI (`aq3.attack`)

Separate **single-marker** attack/cue benchmark from multi-event gesture detection. Current Workbench surface context: `suggest_attack_ms` returns at most one suggested `attack_ms` with relative `confidence` / `reason` strings — those strings are **not** calibrated probabilities.

### Metrics to activate when attack-marker annotations exist

| Metric family | Definition notes |
|---|---|
| Absolute attack-marker error (ms) | `|predicted_attack_ms − label_attack_ms|` among comparable claims |
| Within-tolerance accuracy | fraction inside a frozen ms window (window **to-be-frozen**) |
| Early-vs-late error distribution | signed error; report early and late rates/magnitudes separately |
| False attack on silence / noise tails | claims on material labeled silence-leading / non-attack / insufficient evidence |
| Abstention quality on ambiguous material | rate of explicit no-suggestion / low-evidence outcomes where forcing a cue would be wrong |

A high within-tolerance rate that never abstains on soft/ambiguous attacks is an AQ3 failure mode, not a success.

## Gesture / rhythm preservation KPI (`aq3.gesture`)

Gesture KPI evaluates whether a detected or projected event series preserves the **timing structure** of a source gesture. It does **not** score library sample choice, cluster→sample binding, or Rack write semantics (#680).

### Metrics to activate when multi-event / interval annotations (or projected-trigger labels) exist

| Metric family | Definition notes |
|---|---|
| Inter-onset-interval (IOI) error | absolute/relative error on successive intervals after alignment policy is frozen |
| Normalized timing-shape error | shape/spacing error independent of global time offset (offset-invariant comparison; exact formulation later) |
| Projected trigger timing error | error of projected triggers relative to source gesture times when a projection surface is under test |
| Event-order preservation | whether event sequence order matches reference after matching; order breaks are first-class failures |

Quantization to a musical grid is **out of scope** as a silent default success criterion for AQ3. If a future product chooses quantization, that policy must be an explicit labeled evaluation mode — not hidden inside gesture KPI.

## Difficult buckets — definitions only

These buckets are **definitions for slice metrics**, not promotion gates and not a claim that labeled corpora already exist.

| Bucket | Meaning |
|---|---|
| `soft_attack` | gradual / weak energy rise; attack time ambiguous relative to hard transients |
| `layered_transient_dense` | overlapping or closely spaced transients; high duplicate/miss risk |
| `silence_leading` | leading silence or long pre-roll before the first real event/attack |
| `noisy` | low SNR / competing noise that can create false onsets |
| `very_short` | clip duration near or below practical analysis minima (gesture path already exposes `too_short`) |

Report AQ3 metrics per bucket when labels exist. Benchmark-wide averages alone are insufficient under #942.

## Partition policy

| Role | Policy |
|---|---|
| DEVELOPMENT / CALIBRATION | tuning, exploration, threshold / tolerance discovery — never the sole promotion proof |
| TEST / HOLDOUT | frozen evaluation; **no tuning on TEST/HOLDOUT** |

When a public/synthetic AQ3 corpus is adopted, its split labels must map explicitly onto these roles (same discipline as FSLD `CALIBRATION` → DEVELOPMENT/CALIBRATION and `TEST` → TEST/HOLDOUT for AQ1/AQ2).

Private library material may be a reality check only. It must not set public promotion thresholds and must not enter committed artifacts with private paths or audio.

## Eligibility / abstention

| Material | Expected AQ3 behavior |
|---|---|
| Annotated multi-event material | eligible for `aq3.onset` / `aq3.gesture` correctness when corpus active |
| Annotated single attack-marker material | eligible for `aq3.attack` correctness when corpus active |
| Silence / empty / below-minimum duration | may return empty / `too_short` / abstain — not forced fake onsets |
| Ambiguous soft attack | may abstain or low-evidence claim; forcing a cue to inflate coverage is a failure mode |
| Missing public audio for an otherwise eligible record | status evidence (`audio_missing` / equivalent); not a zero-error success |
| Controlled analyzer failure / unreadable | explicit failure/exclusion status; never coerce to numeric zero |

Coverage and abstention / no-result rates are first-class AQ3 metrics, not afterthoughts.

## Transform expectations (#957) — expectations only

Mechanics and provenance live in `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md`. AQ3 only declares **semantic expectations** (no tolerances, no gates). Issue #991 explicitly calls out gain, pad/trim silence, and resample/channel:

| #957 transform | AQ3 onset expectation | AQ3 attack expectation | AQ3 gesture expectation |
|---|---|---|---|
| `gain` | **invariant** for detection/timing claims that should survive level change | **invariant** for attack marker (within later fidelity limits) | **invariant** for relative intervals / order |
| `peak_normalize` | **invariant** | **invariant** | **invariant** for relative timing structure |
| `to_mono` / `to_stereo` | **invariant** where channel conversion is musically irrelevant | **invariant** where irrelevant | **invariant** where irrelevant |
| `resample` | timing series must stay comparable on a shared timebase; exact tolerance later | attack time comparable on shared timebase | intervals/shape comparable on shared timebase |
| `pad_silence` / `trim` | absolute onset times **transform** (shift/crop); relative structure may remain invariant after annotation transform | absolute attack marker **transforms** with pad/trim | absolute times **transform**; IOI / normalized shape may remain invariant when annotations are transformed consistently |
| `pitch_shift` | **invariant** for timing (pitch-only) | **invariant** for attack time | **invariant** for intervals/order |
| `time_stretch` | **transforming** — onset times scale with stretch; annotations must be transformed consistently | **transforming** — attack time scales | **transforming** — intervals scale; shape comparison uses transformed labels |

Unsupported or unsafe transforms remain fail-closed under #957. Do not approximate them inside AQ3.

## Operational / determinism dimensions (by reference)

| Dimension | Authority | AQ3 use |
|---|---|---|
| Runtime median / p95 (cold vs steady), preferably by clip length | #958 / `ANALYZER_RUNTIME_METHODOLOGY_V1.md` | report for attack-suggest and gesture/onset paths; no SLA in this freeze |
| Semantic repeatability / cache equivalence | #959 / `ANALYZER_SEMANTIC_DETERMINISM_V1.md` | identical input + decision-relevant config → comparable semantic projection (onset times / attack_ms / event series) |
| Portable export | #956 / `SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` | carry AQ3 observations without private paths |

Missing/failed/timeout runs remain explicit evidence — never fabricated `0` ms or perfect P/R/F1.

## Boundary vs #680 (normative)

| Owned by AQ3 (#945 / this contract) | Owned by #680 (not AQ3) |
|---|---|
| Onset / attack / gesture **timing measurement** quality | Vocal/Beatbox → Pattern product/R&D flow |
| Metric definitions, partitions, buckets, robustness expectations | Sample retrieval / ranking for gesture roles |
| Evidence usable **by** attack/cue and gesture consumers | Sound-role clustering as selection authority |
| | Rack / Pattern mutation, UI, microphone capture product scope |

AQ3 may supply quality evidence that #680 consumes. AQ3 must not reopen or duplicate #680's product workstreams.

## Evidence reuse (do not reopen)

| Surface | Role |
|---|---|
| `src/workbench_attack_suggest.py` | current single-marker attack/cue suggestion surface (baseline candidate later) |
| `src/gesture_analysis.py` | current multi-event onset + gesture event surface (baseline candidate later) |
| `docs/benchmarks/ANALYZER_PORTABLE_OUTPUT_BASELINE.md` | portable-output caveats for gesture fail-soft zeros |
| Closed #956–#960 under #950 | reusable AQ8 foundation; cite, do not reopen |
| #680 R&D docs / slices | product context only; not AQ3 measurement authority |

## Exit vocabulary

Exactly one:

- `AQ3_ONSET_GESTURE_KPI_CONTRACT_FROZEN` — onset / attack / gesture metric definitions, plane separation, partitions, difficult buckets, and #957 expectations frozen; annotated corpus may remain HOLD for measurable baselines; timing tolerances remain to-be-frozen
- `AQ3_KPI_CONTRACT_INSUFFICIENT` — freeze cannot be stated from available program contracts / surface reality

This slice exits `AQ3_ONSET_GESTURE_KPI_CONTRACT_FROZEN` with `AQ3_PUBLIC_ANNOTATED_TIMING_CORPUS = HOLD` (definitions freeze allowed; no measurable baseline claimed).
