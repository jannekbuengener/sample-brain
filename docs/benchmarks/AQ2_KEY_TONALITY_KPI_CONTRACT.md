# AQ2 Key, Mode & Tonality KPI / Benchmark Contract

**Status:** ACTIVE_SUPPORTING — KPI/benchmark freeze for [#983](https://github.com/jannekbuengener/sample-brain/issues/983)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#944](https://github.com/jannekbuengener/sample-brain/issues/944) (AQ2), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` (domain tokens + portable envelope); [#957](https://github.com/jannekbuengener/sample-brain/issues/957) / `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md` (transform mechanics); [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / `docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md` (runtime methodology); [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / `docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md` (semantic determinism). AQ8 foundation issues are **CLOSED/MERGED** — reuse, do not reopen.

Historical supporting evidence (not current KPI authority): `docs/benchmarks/KEY_CONF_EVIDENCE.md` (#72) — documents that `key_conf` is chroma-peak prominence, **not** a calibrated probability.

## Architecture outcome

```text
AQ2_KEY_TONALITY_KPI_CONTRACT_FROZEN
```

This document freezes **what AQ2 measures and how evidence is partitioned** before any key algorithm change, claimability threshold, or candidate bake-off. It does **not** authorize analyzer changes, Harmonic Match scoring changes, or production switches.

FSLD public-path eligibility (`root_evidence` / `mode_evidence` / `tonality`) plus the existing current-analyzer eval surfaces are sufficient to freeze key-correctness and tonality-claimability **definitions**. Continuous claim-score ranking metrics (AUROC/AUPRC) and confidence-as-probability calibration remain **HOLD** until a continuous claim score is explicitly defined and promoted.

## Ownership

| Concern | Owner |
|---|---|
| AQ2 key + tonality metric definitions / eligibility | this contract |
| Public key / tonality baseline path (FSLD evidence fields) | this contract + existing FSLD eval docs/runner |
| FSLD ground-truth field semantics | `docs/benchmarks/FSLD_HUMAN_MANIFEST.md` |
| Current-analyzer key metric computation (baseline runner) | `src/fsld_current_analyzer_eval.py` (`key_root`, `full_key`) |
| Portable domain tokens + eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Perturbation mechanics / provenance | [#957](https://github.com/jannekbuengener/sample-brain/issues/957) |
| Runtime cold/steady methodology | [#958](https://github.com/jannekbuengener/sample-brain/issues/958) |
| Semantic determinism / cache equivalence | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| Key / mode algorithms | out of scope here (`src/analyze.py`, key-analysis surfaces remain current) |
| Promotion thresholds / production switch | future evidence-backed decision issues only |
| Harmonic Match scoring | out of scope (AQ6 / #948); compatibility-only later |

## Non-goals

- no analyzer / key algorithm changes
- no production switch
- no promotion thresholds or numeric gates
- no Harmonic Match scoring changes
- no private audio, local DBs, or absolute host paths in committed evidence
- no mislabeling of relative evidence (`key_conf`, chroma prominence) as calibrated probability
- no single global “analysis quality” score across AQ domains
- no invention of a continuous claim score in this freeze

## Shared KPI vocabulary (#942) — AQ2 selection

Every #942 shared dimension is either **selected** for AQ2 or explicitly **out of scope / HOLD** here:

| #942 dimension | AQ2 key (`aq2.key`) | AQ2 tonality (`aq2.tonality`) |
|---|---|---|
| correctness | selected (root / mode / full-key) | selected (claim vs abstain vs false claim) |
| coverage / abstention | selected (usable prediction on eligible material) | selected (first-class claimability metrics) |
| error buckets / confusion | selected (diagnostic root/mode buckets; definitions only) | selected (false-key-claim / forced-guess diagnostics) |
| baseline-vs-candidate delta | methodology reserved; no thresholds here | same |
| robustness / metamorphic | expectations only (§ Transform expectations); mechanics → #957 | same |
| determinism / reproducibility | consume #959 by reference | consume #959 by reference |
| runtime median/p95 | consume #958 by reference | consume #958 by reference |
| calibration (confidence-as-probability) | **HOLD / out of scope** until a continuous claim score is explicitly promoted | **HOLD / out of scope** until that score exists |
| slice metrics | selected (e.g. MA vs SA; evidence sub-populations) | selected (tonal vs `no_key`; evidence sub-populations) |

## Domain tokens (#956)

Portable `domain` tokens for analysis-eval artifacts:

| Token | Scope |
|---|---|
| `aq2.key` | Tonal root, mode, and full-key correctness on eligible records |
| `aq2.tonality` | Whether / when Sample Brain should claim a key at all (claimability, abstention, false-key-claim) |

The common envelope in `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` stays domain-neutral. Domain metric semantics remain owned by this AQ2 contract. Do not encode AQ2 thresholds into the shared envelope.

## Separation rule (normative)

1. **Key correctness and tonality claimability are separate reporting planes.**
2. Exact root / mode / full-key accuracy must **never** be inflated by silently dropping difficult mode cases, non-tonal material, or abstentions without explicit denominator semantics.
3. Root-only success does **not** imply mode or full-key success.
4. A high coverage rate does **not** imply low false-key-claim rate (and vice versa).
5. Relative analyzer evidence (`key_conf`, chroma prominence, template scores) must **not** be reported as calibrated probability / confidence unless an explicitly promoted continuous claim score exists.
6. Missing evidence is `HOLD` / unknown — never a fabricated zero that looks like perfect abstention or perfect accuracy.

## Public baseline dataset path

| Item | Authority |
|---|---|
| Dataset path | FSLD human-manifest evaluation surface (`docs/benchmarks/FSLD_HUMAN_MANIFEST.md`, `docs/benchmarks/FSLD_CURRENT_ANALYZER_EVAL.md`) |
| Key-root eligibility | `ground_truth.tonality == "tonal"` **and** `root_evidence == "known"` |
| Mode eligibility (mode-on-mode-known) | tonal + `mode_evidence == "known"` (mode correctness denominator) |
| Full-key eligibility | tonal + `root_evidence == "known"` **and** `mode_evidence == "known"` |
| Tonality / claimability labels | `ground_truth.tonality` (`tonal` vs `no_key`) plus evidence fields; see FSLD human-manifest contract |
| Analyzer call (current baseline runner) | `extract_features(...)` via `src/fsld_current_analyzer_eval.py` — predicts `predicted_key_root` / `predicted_key_mode` / `predicted_key` without changing key semantics |
| Output policy | external untracked JSON only; never commit private audio or local absolute paths |
| Unavailable audio | `PUBLIC_AUDIO_NOT_AVAILABLE_LOCALLY` — do not treat as a 0% quality baseline |

`KEY_CONF_EVIDENCE.md` remains **HISTORICAL/supporting** for the meaning of `key_conf` (prominence, not probability). It is not a substitute for the FSLD public key/tonality baseline.

Closed historical public-first work (#594 / #595 / #596 / #598) is evidence to reuse, not to reopen.

## Key correctness KPI (`aq2.key`)

### Selected correctness metrics

Report with **explicit denominators**. Existing FSLD current-analyzer surfaces already expose `key_root` and `full_key`; mode-on-mode-known is defined here even if a later runner slice adds a dedicated aggregate.

| Metric family | Eligible denominator | Definition notes |
|---|---|---|
| Exact root accuracy | tonal + `root_evidence=known` | fraction where predicted root equals label root among eligible; also report `predicted` coverage on that denominator |
| Mode accuracy (mode-on-mode-known) | tonal + `mode_evidence=known` | fraction where predicted mode equals label mode among eligible; do **not** silently require root match unless reporting a joint metric |
| Full-key accuracy | tonal + `root_evidence=known` + `mode_evidence=known` | fraction where predicted root **and** mode both match |
| Per-root / per-mode confusion | same as the metric being sliced | optional slice tables; keep MA (`annotation_tier=ma`) and SA (`sa`) separate as in the current eval |
| Coverage / abstention on key-eligible material | matching eligibility set | share with no usable root and/or mode prediction; exclusions remain explicit status records |

Root correctness must not be improved on paper by excluding mode-difficult cases from the root denominator without stating that exclusion. Full-key remains the joint metric; root and mode remain separately reportable.

### Diagnostic confusion buckets — definitions only

These buckets are **diagnostic**, not promotion gates. No numeric thresholds are set here. A later classifier may implement them; this freeze only names the classes.

Assume pitch-class roots on the chromatic circle (C…B) and modes in `{major, minor}` where both sides are mode-known.

| Bucket | Meaning (predicted vs label) |
|---|---|
| `exact` | same root and (when mode-known) same mode |
| `relative` | relative major/minor pair (same diatonic collection; root differs by ±3 semitones with opposite mode — e.g. C major ↔ A minor) |
| `parallel` | same root, opposite mode (e.g. C major ↔ C minor) |
| `fifth` | root differs by +7 semitones (perfect fifth up), mode compared separately when known |
| `fourth` | root differs by +5 semitones (perfect fourth up / fifth down), mode compared separately when known |
| `semitone_neighbor` | root differs by ±1 semitone |
| `other` | any other mismatch not covered above |
| `missing_prediction` | eligible label but no usable predicted root/mode for the metric under evaluation |

When mode is unknown on either side, report root-distance buckets without claiming relative/parallel mode semantics. Do not collapse these diagnostics into a single opaque “key error” score for AQ2 gates.

## Tonality / claimability KPI (`aq2.tonality`)

Claimability answers: **should Sample Brain claim a key at all?** It is not the same as “was the claimed key correct?”

| Metric family | Denominator / notes |
|---|---|
| Coverage rate | share of intended claimable/tonal material that yields a key claim (usable root, and mode when the claim surface requires it) |
| Abstention rate | share that yields no key claim / explicit abstain on material where a decision is expected |
| False-key-claim rate | among `ground_truth.tonality == "no_key"` (or explicitly non-claimable / insufficient-evidence material), share where the system **claims** a key anyway |
| Selective full-key accuracy vs coverage | joint view: correctness on claimed subset **and** coverage/abstention — never one without the other |
| Threshold stability CALIBRATION → TEST | methodology reserved; no thresholds frozen here |
| AUROC / AUPRC for tonal vs no-key | **HOLD** until a continuous claim score is explicitly defined and promoted (see Confidence) |

Forced guesses that inflate key accuracy by never abstaining are an AQ2 failure mode, not a success.

## Confidence / continuous claim score — HOLD

| Surface | Status |
|---|---|
| `key_conf` (chroma peak prominence) | relative evidence only — **not** calibrated probability (`docs/benchmarks/KEY_CONF_EVIDENCE.md`) |
| Other relative template / prominence scores | same rule unless explicitly redefined |
| Continuous claim score for ranking / AUROC / AUPRC | **HOLD** — not defined in this freeze |
| Brier / reliability / calibration curves | **HOLD** — only if a score is later promoted to calibrated confidence |

Do not invent a claim score inside this contract. When a future scoped issue defines one, AUROC/AUPRC and calibration metrics become selectable under #942; until then report them as HOLD / unknown.

## Partition policy

| Role | Policy |
|---|---|
| DEVELOPMENT / CALIBRATION | tuning, exploration, threshold discovery — never the sole promotion proof |
| TEST / HOLDOUT | frozen evaluation; **no tuning on TEST/HOLDOUT** |

FSLD human-manifest splits use `CALIBRATION` and `TEST` (`docs/benchmarks/FSLD_HUMAN_MANIFEST.md`). Treat FSLD `CALIBRATION` as the DEVELOPMENT/CALIBRATION role and FSLD `TEST` as TEST/HOLDOUT for AQ2 key/tonality baselines.

Private library material may be a reality check only. It must not set public promotion thresholds and must not enter committed artifacts with private paths or audio.

## Eligibility / abstention

| Material | Expected AQ2 behavior |
|---|---|
| Tonal + `root_evidence=known` | eligible for exact-root metrics |
| Tonal + `mode_evidence=known` | eligible for mode-on-mode-known metrics |
| Tonal + root+mode known | eligible for full-key metrics |
| `tonality=no_key` | eligible for false-key-claim / abstention-on-non-tonal metrics; **not** for key-correctness denominators |
| Tonal but root/mode `unknown` / `conflicting` / `missing` | retain for claimability / evidence slices; exclude from the corresponding correctness denominator with an explicit reason |
| Missing public audio for an otherwise eligible record | status evidence (`audio_missing` / equivalent); not a zero-error success |
| Controlled analyzer failure | explicit failure/exclusion status; never coerce to numeric zero |

Coverage and abstention rates are first-class AQ2 metrics, not afterthoughts.

## Transform expectations (#957) — expectations only

Mechanics and provenance live in `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md`. AQ2 only declares **semantic expectations** (no tolerances, no gates):

| #957 transform | AQ2 key / tonality expectation |
|---|---|
| `gain` | **invariant** — stable key claim / abstention should survive |
| `peak_normalize` | **invariant** |
| `to_mono` / `to_stereo` | **invariant** where channel conversion is musically irrelevant |
| `resample` | **invariant** for claimed root/mode (within resampling fidelity limits to be set later) |
| `pad_silence` / `trim` | **invariant** for key claim where the tonal content remains representative; edge cases remain explicit exclusions later |
| `pitch_shift` by `N` semitones | **transforming** — claimed root should rotate by `N` pitch classes; mode should be preserved where musically valid |
| `time_stretch` | **invariant** for key claim (pitch-preserving stretch must not change root/mode claim) |

Unsupported or unsafe transforms remain fail-closed under #957. Do not approximate them inside AQ2.

## Operational / determinism dimensions (by reference)

| Dimension | Authority | AQ2 use |
|---|---|---|
| Runtime median / p95 (cold vs steady) | #958 / `ANALYZER_RUNTIME_METHODOLOGY_V1.md` | report for key/mode path; no SLA in this freeze |
| Semantic repeatability / cache equivalence | #959 / `ANALYZER_SEMANTIC_DETERMINISM_V1.md` | identical input + decision-relevant config → comparable semantic projection |
| Portable export | #956 / `SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` | carry AQ2 observations without private paths |

Missing/failed/timeout runs remain explicit evidence — never fabricated `0` ms or perfect scores.

## Evidence reuse (do not reopen)

| Surface | Role |
|---|---|
| FSLD manifest + current-analyzer eval | public key/tonality baseline path (`root_evidence` / `mode_evidence` / `tonality`) |
| `src/fsld_current_analyzer_eval.py` | existing `key_root` / `full_key` metric surfaces |
| `docs/benchmarks/KEY_CONF_EVIDENCE.md` | historical proof that `key_conf` is prominence, not probability |
| Closed #594 / #595 / #596 / #598 | historical public-first key/tonality validation + abstention evidence |
| Closed #956–#960 under #950 | reusable AQ8 foundation; cite, do not reopen |

## Exit vocabulary

Exactly one:

- `AQ2_KEY_TONALITY_KPI_CONTRACT_FROZEN` — key correctness + tonality claimability definitions, FSLD eligibility, partitions, diagnostic buckets, and #957 expectations frozen; AUROC/AUPRC + confidence calibration may remain HOLD without a continuous claim score
- `AQ2_KPI_CONTRACT_INSUFFICIENT` — freeze cannot be stated from available public contracts/evidence

This slice exits `AQ2_KEY_TONALITY_KPI_CONTRACT_FROZEN`: FSLD evidence fields and existing current-analyzer eval surfaces suffice for the KPI contract; continuous claim-score ranking/calibration remain HOLD by design.
