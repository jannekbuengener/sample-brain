# AQ5 Similarity search, retrieval & ranking KPI / Benchmark Contract

**Status:** ACTIVE_SUPPORTING — KPI/benchmark freeze for [#1038](https://github.com/jannekbuengener/sample-brain/issues/1038)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#947](https://github.com/jannekbuengener/sample-brain/issues/947) (AQ5), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Related evidence (cite, do not reopen as live authority):** [#73](https://github.com/jannekbuengener/sample-brain/issues/73) / ADR-0005 / `docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md` (Tier-A/Tier-B relevance campaign); `docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md` (ANN/backend vs NumPy overlap + operational latency — separate plane).  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) / `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` (domain tokens + portable envelope); [#957](https://github.com/jannekbuengener/sample-brain/issues/957) / `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md` (transform mechanics); [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / `docs/benchmarks/ANALYZER_RUNTIME_METHODOLOGY_V1.md` (runtime methodology); [#959](https://github.com/jannekbuengener/sample-brain/issues/959) / `docs/ANALYZER_SEMANTIC_DETERMINISM_V1.md` (semantic determinism). AQ8 foundation issues are **CLOSED/MERGED** — reuse, do not reopen.

Current search surfaces (read-only context for this freeze; not changed here): `src/search.py` / `collect_search_hits()`, `src/search_eval.py`, `src/benchmark_search_quality.py`, `src/hybrid_rank.py`, `src/search_filters.py`, NumPy index path, optional sqlite-vec / ANN backends, CLAP embed path when `[clap]` is available.

## Architecture outcome

```text
AQ5_RETRIEVAL_KPI_CONTRACT_FROZEN
```

This document freezes **what AQ5 measures, how retrieval quality stays separate from ranking stability and from operational latency/size, and how evidence is partitioned** before candidate bake-offs, ANN/index promotion, or embedding algorithm work. It does **not** authorize embedding/ANN algorithm changes, production backend switches, or promotion thresholds.

Metric **definitions**, plane separation, query-family slice policy, label / hard-negative / leakage policy, ANN-vs-reference methodology, partitions, and #958/#959 consumption are frozen here. Existing Tier-A / Tier-B suites and sqlite-vec gate evidence remain **evidence by reference**. A future scoped **vNext relevance contract / corpus adoption** issue may name a frozen query+label identity for measurable baselines; until then, reuse ADR-0005 fixtures and published evidence without inventing private query text or private labels.

## Ownership

| Concern | Owner |
|---|---|
| AQ5 retrieval / ranking metric definitions / plane separation / eligibility | this contract |
| Tier-A / Tier-B suite schema + harness vocabulary | ADR-0005 + `src/search_eval.py` / `src/benchmark_search_quality.py` (cite; do not redefine here) |
| Published relevance evidence | `docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md` (#73 campaign) |
| ANN / backend overlap + operational latency evidence | `docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md` (ADR-0004 gates; separate plane) |
| Portable domain tokens + eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Perturbation mechanics / provenance | [#957](https://github.com/jannekbuengener/sample-brain/issues/957) |
| Runtime cold/steady methodology | [#958](https://github.com/jannekbuengener/sample-brain/issues/958) |
| Semantic determinism / cache equivalence | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| Embedding / ANN / hybrid ranking algorithms | out of scope here (current surfaces remain as-is) |
| Promotion thresholds / production backend switch | future evidence-backed decision issues only |
| Graded relevance / NDCG denominators | **HOLD** until graded labels exist under a scoped corpus issue |

## Non-goals

- no embedding / ANN / hybrid ranking algorithm changes
- no production backend switch (NumPy remains default until a separate evidence-backed decision)
- no promotion thresholds or numeric gates in this freeze
- no single opaque score that mixes relevance and latency
- no private samples, private query text, local DBs, or absolute host paths in committed evidence
- no invented graded labels solely to unlock NDCG
- no collapse of semantic model quality into ANN approximation quality
- no ML mandate (metadata / classical ranking remain allowed when sufficient)
- no single global “analysis quality” score across AQ domains

## Shared KPI vocabulary (#942) — AQ5 selection

Every #942 shared dimension is either **selected** for AQ5 or explicitly **out of scope / HOLD** here:

| #942 dimension | AQ5 retrieval (`aq5.retrieval`) | AQ5 ranking stability (`aq5.ranking`) |
|---|---|---|
| correctness | selected (P@K, R@K, MRR, HitRate, hard-negative FP; NDCG when graded) | selected as regression / equivalence metrics vs frozen baseline or reference path |
| coverage / abstention | selected (query failure / empty-result / must-recall miss rates) | selected (rankable vs non-comparable ties / missing hits) |
| error buckets / confusion | selected (failure buckets from `search_eval`; hard-negative leaks) | selected (rank displacement; Top-K set diffs) |
| baseline-vs-candidate delta | methodology reserved; no thresholds here | same — report per plane, never opaque-combine with latency |
| robustness / metamorphic | expectations only (§ Transform expectations); mechanics → #957 | same where ranking identity should survive |
| determinism / reproducibility | consume #959 by reference | consume #959 by reference (tie behavior included) |
| runtime median/p95 | **separate operational plane** — consume #958 + sqlite-vec gate methodology by reference; never fold into relevance | same — operational only |
| calibration (confidence-as-probability) | **HOLD / out of scope** (search scores are ranking aids, not calibrated probabilities unless explicitly promoted later) | same |
| slice metrics | selected (query-family × mode) | selected (same slices for stability deltas) |

## Domain tokens (#956)

Portable `domain` tokens for analysis-eval artifacts:

| Token | Scope |
|---|---|
| `aq5.retrieval` | Relevance / hit-set quality against labeled relevant sets (and hard negatives): P@K, R@K, MRR, HitRate, hard-negative FP; NDCG only with graded labels |
| `aq5.ranking` | Ranking stability / regression / backend-equivalence: Top-K overlap, rank displacement, deterministic tie behavior, ANN vs NumPy reference agreement on identical query sets |

Operational latency / index size / rebuild time are **not** folded into either token as a relevance substitute. When portable artifacts need a runtime observation, use #958 methodology and keep `domain` semantics owned by the emitting plane (or a clearly labeled operational metric_id) — never invent a combined `aq5.quality_latency` score.

The common envelope in `docs/benchmarks/SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` stays domain-neutral. Domain metric semantics remain owned by this AQ5 contract. Do not encode AQ5 thresholds into the shared envelope.

## Separation rule (normative)

1. **Retrieval quality, ranking stability, and operational latency/size are separate reporting planes.**
2. Latency gains may **not** hide ranking or relevance regressions.
3. Approximate-index / ANN quality must be compared to a **reference search path** (default: NumPy exact / current reference) on identical query sets — never declared “good enough” from speed alone.
4. Do **not** collapse semantic embedding/model quality into ANN/index approximation quality (report model path and index path separately when both change).
5. Do **not** publish a single opaque number that mixes relevance and latency (or mixes retrieval and ranking stability into one unlabeled “search quality” score for promotion).
6. Missing graded labels → NDCG is `HOLD` / unknown — never fabricate grades or treat binary relevance as graded.
7. Missing evidence is `HOLD` / unknown — never a fabricated zero that looks like perfect precision, perfect recall, or perfect backend overlap.

## Evidence reuse (do not reopen)

| Surface | Role |
|---|---|
| ADR-0005 | Tier-A/Tier-B evaluation decision, metrics vocabulary, golden suite schema |
| `docs/benchmarks/SEARCH_QUALITY_EVIDENCE.md` | Measured Tier-A + Tier-B campaign evidence (#73 / #219 consolidation) |
| `tests/fixtures/search_quality/golden_v1.yaml` | Tier-A pipeline regression suite (deterministic vectors) |
| `tests/fixtures/search_quality/golden_v2_clap.yaml` | Tier-B CLAP suite (text + audio; synthetic fixtures) |
| `docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md` | Backend overlap@k vs NumPy + latency/size operational evidence |
| `src/search_eval.py` failure buckets | Reporting taxonomy: `success`, `negative_leak_top5`, `zero_precision_at_5`, `zero_mrr`, `must_recall_fail`, `error` |
| Closed #956–#960 under #950 | reusable AQ8 foundation; cite, do not reopen |

Historical Tier-B phase sections inside SEARCH_QUALITY_EVIDENCE remain historical development notes; the final 6/6 campaign is the current evidence snapshot for relevance. Vocal production-claim `HOLD` in that evidence file is **evidence status**, not a reason to skip evaluating the `vocal_no_vocal` family under this contract.

## Retrieval quality KPI (`aq5.retrieval`)

### Default K values

Report at **K ∈ {1, 5, 10}** unless a scoped suite freezes a different set. Suite default `topk` (ADR-0005: often 10) must be stated in run metadata. When MRR is reported from a harness with fixed `topk`, label it **MRR@K** consistently (as SEARCH_QUALITY_EVIDENCE does for Tier-B).

### Selected metrics

| Metric | Definition notes | Activation |
|---|---|---|
| Precision@K (P@K) | \|Top-K ∩ Relevant\| / K | selected |
| Recall@K (R@K) | \|Top-K ∩ Relevant\| / \|Relevant\| when \|Relevant\| > 0 | selected when relevant-set cardinality is known |
| MRR / MRR@K | Mean reciprocal rank of the first relevant hit | selected |
| HitRate@K | Fraction of queries with ≥1 relevant in Top-K (single-target / success-rate style) | selected where single-target or “any hit” success is the product question |
| Hard-negative FP rate | Fraction of queries (or mean count) where a declared hard negative appears in Top-K (e.g. top-5 leak) | selected when `negative_sample_ids` (or equivalent) exist |
| NDCG@K | Graded discounted cumulative gain normalized by ideal ranking | **HOLD** unless graded relevance labels exist for the suite |

Aggregates: mean over queries; **always also report per query-family slice and per mode** (text / audio / vector / filter / hybrid as applicable). Aggregate-only tables are incomplete for AQ5.

### Modes (evidence planes, not collapsed)

| Mode | Context |
|---|---|
| Tier-A `vector` | Deterministic embedding regression (pipeline / filter / hybrid wiring) |
| Tier-B `text` | Text-to-sample semantic relevance (CLAP when available) |
| Tier-B `audio` | Audio-to-audio semantic relevance |
| Filter / hybrid | Metadata filter compliance and hybrid rerank effects — report separately from pure semantic ranking |

Do not blend text and audio into one unlabeled “CLAP quality” number when comparing candidates.

## Ranking stability / regression KPI (`aq5.ranking`)

Report separately from retrieval relevance:

| Metric family | Definition notes |
|---|---|
| Top-K overlap vs frozen baseline / reference | set overlap of result IDs at K (e.g. overlap@10 used in sqlite-vec gates) |
| Rank displacement for relevant items | change in rank position for each labeled relevant ID vs baseline/reference |
| Deterministic tie behavior | identical inputs + decision-relevant config → comparable ordered projection (#959) |
| Backend equivalence | ANN/sqlite-vec/quantized path vs NumPy reference on **identical** query sets and catalog — semantic model held fixed when measuring approximation |

Backend equivalence answers “does the index approximate the reference ranking?” — not “is the embedding model relevant?” Those questions stay on separate planes.

## Query-family slices

Maintain metrics **per producer-relevant query family**, not aggregate only. Canonical Tier-B families (ADR-0005 / golden_v2) by reference:

| Family token | Notes |
|---|---|
| `kick_snare_perc` | drums / percussion |
| `riser_impact` | transitions / impacts |
| `pad_texture` | pads / textures |
| `vocal_no_vocal` | vocal presence / absence (fixtures may be proxies; production-claim HOLD in evidence does not remove the slice) |
| `dry_wet` | processing wetness |
| `genre_mood` | scene / mood language |
| `audio_to_audio` | report as mode=`audio` (and class × mode rows), not only a collapsed aggregate |

Tier-A suites may use cluster / filter / hybrid query IDs; when mapping to AQ5 slices, state the mapping explicitly or report Tier-A IDs as their own slice axis. Optional text `query_style` groupings (keyword / natural_language / exclusion) remain **reporting slices only** — they must not change ranking or invent gates in this freeze.

## ANN vs NumPy reference equivalence methodology

Authority for measured backend gates and methodology: `docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md` (ADR-0004). AQ5 freezes the **interpretation rule**:

1. Hold the **embedding / catalog / query set** fixed when measuring index approximation.
2. Compare approximate path (sqlite-vec / quantized / future ANN) to the **NumPy reference** (or the explicitly frozen reference path named in the run).
3. Report **overlap@K** (and Precision@1 vs reference when used) on the ranking plane (`aq5.ranking`).
4. Report **latency p50/p95/(p99 when justified), rebuild time, DB/index size, memory** on the **operational** plane only.
5. A latency PASS with an overlap FAIL is **not** an AQ5 relevance success and must not be summarized as one score.
6. Default production backend remains **NumPy** until a separate evidence-backed promotion decision — this contract does not switch backends.

## Label / hard-negative / leakage policy

| Policy | Rule |
|---|---|
| Relevant labels | `relevant_sample_ids` (or equivalent) required for evaluatable queries; non-empty for scored queries |
| Hard negatives | `negative_sample_ids` optional but must not overlap relevant; when present, Top-K appearance is first-class FP evidence |
| Graded labels | required for NDCG; absent → NDCG HOLD |
| Partition leakage | same query ID, same audio fixture, or near-duplicate catalog items must not cross DEVELOPMENT/CALIBRATION ↔ TEST/HOLDOUT without explicit documentation |
| Path leakage | reject private absolute paths in suites; portable `fixture_name` / runtime WAVs only in committed fixtures |
| Private query text | do not commit private producer queries unless sanitized and explicitly approved; private libraries are reality-check only |
| Benchmark leakage | do not tune thresholds or labels on TEST/HOLDOUT; do not train/adapt embeddings on holdout queries |
| Uncertain labels | retain as uncertain; do not force into relevant sets to inflate recall |

Private library / producer reality-check queries may inform future suite design. They must not set public promotion thresholds and must not enter committed artifacts with private paths, audio, or unsanitized query text.

## Partition policy

| Role | Policy |
|---|---|
| DEVELOPMENT / CALIBRATION | suite exploration, label curation, threshold discovery — never the sole promotion proof |
| TEST / HOLDOUT | frozen evaluation; **no tuning on TEST/HOLDOUT** |

Existing ADR-0005 Tier-A/Tier-B fixtures are the current public/synthetic evaluation surfaces. When a future scoped issue adopts a named AQ5 vNext relevance corpus, its split labels must map explicitly onto these roles.

## Operational latency / size (separate plane)

Report when measuring search backends or library-scale runs — **never as a substitute for `aq5.retrieval` / `aq5.ranking`**:

| Metric | Notes |
|---|---|
| Query latency p50 / p95 | p99 only when workload size justifies it |
| Index build / rebuild time | documented; budgets are future decision issues |
| Index / database size | bytes |
| Memory | where material |
| Coverage / query failure rate | empty results, harness errors, backend unavailable |

Methodology for cold vs steady analyzer-style timing: consume [#958](https://github.com/jannekbuengener/sample-brain/issues/958) / `ANALYZER_RUNTIME_METHODOLOGY_V1.md` where applicable. Search-backend microbenchmarks may continue to use the sqlite-vec harness protocol documented in SQLITE_VEC_GATE_EVIDENCE — still operational-only for AQ5.

Missing/failed/timeout runs remain explicit evidence — never fabricated `0` ms or perfect overlap.

## Eligibility / abstention

| Material | Expected AQ5 behavior |
|---|---|
| Labeled relevant-set queries | eligible for `aq5.retrieval` correctness metrics |
| Queries with hard negatives | eligible for hard-negative FP reporting |
| Graded-label queries | eligible for NDCG; otherwise NDCG HOLD |
| Backend comparison on identical sets | eligible for `aq5.ranking` equivalence metrics |
| Optional CLAP unavailable / offline | explicit skip / unavailable status — not a zero-relevance success |
| Controlled search / embed failure | explicit failure/exclusion status; never coerce to numeric zero |
| Empty result when hits are expected | coverage / failure evidence, not silent success |

## Transform expectations (#957) — expectations only

Mechanics and provenance live in `docs/ANALYZER_PERTURBATION_FIXTURE_CONTRACT.md`. AQ5 only declares **semantic expectations** where retrieval identity justifies invariance (no tolerances, no gates):

| #957 transform | AQ5 retrieval / ranking expectation |
|---|---|
| `gain` / `peak_normalize` | **invariant** ranking identity for audio-to-audio queries where level alone should not reorder semantics |
| `to_mono` / `to_stereo` | **invariant** where channel conversion is musically irrelevant to the query intent |
| `resample` | **invariant** within later fidelity limits for the same semantic query |
| `pad_silence` / `trim` | **may transform** if the audible identity or fixture window changes; treat as explicit exclusion or relabel later |
| `pitch_shift` / `time_stretch` | **may transform** semantic neighbors; do not assume invariance without a scoped metamorphic suite |

Unsupported or unsafe transforms remain fail-closed under #957. Do not approximate them inside AQ5.

## Operational / determinism dimensions (by reference)

| Dimension | Authority | AQ5 use |
|---|---|---|
| Runtime median / p95 (cold vs steady) | #958 / `ANALYZER_RUNTIME_METHODOLOGY_V1.md` | operational plane for search/embed paths; no SLA in this freeze |
| Semantic repeatability / cache equivalence | #959 / `ANALYZER_SEMANTIC_DETERMINISM_V1.md` | identical input + decision-relevant config → comparable hit-list / rank projection |
| Portable export | #956 / `SAMPLE_BRAIN_ANALYSIS_EVAL_V1.md` | carry AQ5 observations without private paths |
| Backend latency / size microbench | SQLITE_VEC_GATE_EVIDENCE | operational + ranking-overlap evidence; still no opaque combine |

## HOLD stubs (explicit)

| Item | Status |
|---|---|
| NDCG@K / graded relevance | **HOLD** until graded labels exist under a scoped corpus/suite issue |
| Confidence / score calibration for search ranks | **HOLD** — cosine / hybrid scores are not calibrated probabilities |
| Named AQ5 vNext relevance corpus id beyond ADR-0005 fixtures | **future scoped adoption** — not invented here; current fixtures remain evidence surfaces |
| Production promotion thresholds / backend switch | **out of scope** — separate decision issues only |
| Vocal production-claim from Tier-B proxies | evidence `HOLD` in SEARCH_QUALITY_EVIDENCE — slice still measured; no production claim authorized by this contract |

## Exit vocabulary

Exactly one:

- `AQ5_RETRIEVAL_KPI_CONTRACT_FROZEN` — retrieval vs ranking vs operational plane separation, selected metrics (P@K, R@K, MRR, HitRate, hard-negative FP; NDCG HOLD without grades), query-family slices, ANN-vs-NumPy methodology, label/leakage policy, domain tokens, partitions, and #958/#959 consumption frozen; no algorithm or production switch
- `AQ5_KPI_CONTRACT_INSUFFICIENT` — freeze cannot be stated from available program contracts / surface reality

This slice exits `AQ5_RETRIEVAL_KPI_CONTRACT_FROZEN`. NDCG remains HOLD without graded labels. Existing ADR-0005 / SEARCH_QUALITY_EVIDENCE / SQLITE_VEC_GATE_EVIDENCE surfaces are reused by reference; a future scoped issue may adopt a named vNext relevance corpus without reopening this metric-definition freeze.
