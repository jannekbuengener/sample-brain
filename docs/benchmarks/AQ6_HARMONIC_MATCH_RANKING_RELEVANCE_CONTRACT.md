# AQ6 Harmonic Match Ranking Relevance Contract + Sanitized Candidate Set

**Status:** ACTIVE_SUPPORTING — ranking relevance freeze for [#1016](https://github.com/jannekbuengener/sample-brain/issues/1016)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#948](https://github.com/jannekbuengener/sample-brain/issues/948) (AQ6), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED — consume, do not reopen):** [#1015](https://github.com/jannekbuengener/sample-brain/issues/1015) theory truth table / `docs/benchmarks/AQ6_HARMONIC_MATCH_THEORY_KPI_CONTRACT.md`  
**Upstream evidence (consume only):** AQ2 (#944) key/mode claimability; AQ1 (#943) tempo/BPM secondary evidence  
**Executable surface:** `src/aq6_harmonic_ranking_relevance.py` + `tests/fixtures/aq6_harmonic_ranking/relevance_benchmark_v1.json`  
**Related (by reference only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) portable tokens; [#959](https://github.com/jannekbuengener/sample-brain/issues/959) semantic determinism; [#1017](https://github.com/jannekbuengener/sample-brain/issues/1017) theory baseline measurement (separate plane).

## Architecture outcome

```text
AQ6_RANKING_RELEVANCE_BENCHMARK_FROZEN
```

This document freezes the **ranking-quality relevance plane** for Harmonic Match: graded labels, Precision@K / MRR@K / NDCG@K / Top-K false-positive denominators, a sanitized synthetic candidate/query set, and CALIBRATION vs TEST/HOLDOUT leakage policy. It does **not** authorize ranking-weight changes, production ranking changes, UI/QML work, key/BPM detector changes, embeddings/ML, private library commits, or human preference scoring.

Plane rule (normative):

```text
theoretical compatibility ≠ ranking relevance ≠ subjective preference
```

Theory truth remains owned by #1015. Subjective preference remains a later optional plane. Current product weights (`0.75` harmony / `0.25` BPM) are **measurement targets**, not ground truth.

## Ownership

| Concern | Owner |
|---|---|
| Graded ranking relevance + ranking KPIs | this contract + executable benchmark |
| Exhaustive theory relation / compatibility GT | #1015 / `aq6.theory` — cite; never override |
| Product Harmonic Match runtime scoring | `src/workbench_harmony.py` (`rate_harmony` / `find_harmony_matches`) — measure only |
| Upstream key/mode claimability | AQ2 (#944) — consume eligibility/uncertainty |
| Upstream BPM / secondary score evidence | AQ1 (#943) — secondary ranking evidence only |
| Human preference | later optional plane — **not** ranking ground truth |
| Portable domain tokens + eval envelope | [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |
| Semantic determinism | [#959](https://github.com/jannekbuengener/sample-brain/issues/959) |
| Weight tuning / production switch | future evidence-backed decision issues only |

## Non-goals

- no weight tuning / no change to `0.75` / `0.25`
- no product ranking / relation semantic change
- no UI / QML changes
- no key / BPM / mode detector algorithm changes
- no embeddings / ML
- no private library or absolute host paths in committed artifacts
- no human preference study in this freeze
- no collapse of theory truth into ranking grades
- no single opaque “Harmonic Match quality” score

## Named identities

| Field | Value |
|---|---|
| `benchmark_id` | `sample-brain.aq6.harmonic-ranking.relevance.v1` |
| `document_type` | `sample-brain.aq6.harmonic-ranking-relevance.v1` |
| `benchmark_version` | `1.0.0` |
| Domain token | `aq6.ranking` (activated by this freeze) |
| Theory authority (cite only) | `sample-brain.aq6.harmonic-theory.truth-table.v1` |
| Label source | `synthetic_theory_aligned_graded_v1` |

## Domain tokens (#956)

| Token | Scope |
|---|---|
| `aq6.theory` | Owned by #1015 — deterministic relation / compatibility / pitch-shift correctness |
| `aq6.ranking` | **Activated here** — graded relevance + ranking KPIs against the frozen candidate/query set |
| `aq6.preference` | Reserved — human preference; **not** activated |

Do not invent an `aq6.quality` aggregate that collapses these planes.

## Separation rule (normative)

1. Every candidate row carries **distinct** fields: `theory_relation` / `theory_compatibility` (from #1015 `classify_theory_pair`) **and** `relevance_grade` / `ranking_eligible` (this plane).
2. A high product `total_score` must **never** rewrite theory truth or invent a positive relevance grade for known-incompatible or evidence-uncertain pairs.
3. Missing / unparseable key or missing mode → `ranking_eligible=false`; do **not** score as graded certainty.
4. Missing BPM is secondary evidence: label `bpm_evidence` explicitly; never treat missing BPM as a certain tempo match when evaluating ranking quality.
5. Human preference labels are out of scope; they must not backfill ranking grades.
6. Report Precision@K, MRR@K, NDCG@K, Top-K FP, coverage/abstention separately — no global blended score.

## Frozen relevance grades

Grades are **judged ranking relevance**, aligned to theory compatibility classes for this synthetic public set. They are not the product `total_score` and not preference votes.

| `relevance_grade` | Meaning | Typical theory cell |
|---|---|---|
| `3` | Highest relevance — same key/mode | `direct` + `compatible` |
| `2` | Strong relevance — relative / fifth-fourth family | `related` + `compatible` |
| `1` | Partial relevance — small pitch-shift useful | `transpose` + `compatible` |
| `0` | Not relevant — known incompatible | `uncertain` + `incompatible` |
| `null` + `ranking_eligible=false` | Abstain / not in graded denominators | evidence `uncertain` (missing key/mode/unparseable) |

### Binary relevance for Precision@K / MRR@K

| Convention | Rule |
|---|---|
| Relevant | `ranking_eligible=true` **and** `relevance_grade >= 1` |
| Non-relevant hard negative | `ranking_eligible=true` **and** `relevance_grade == 0` |
| Excluded from graded denominators | `ranking_eligible=false` |

### NDCG@K

Uses graded gains `2^grade - 1` for eligible candidates with non-null grades. Ineligible candidates are omitted from ideal and predicted gain lists for that query (abstention), not forced to gain 0 as if judged irrelevant.

## Ranking KPIs (`aq6.ranking`) — definitions only

| Metric | Definition | Denominator notes |
|---|---|---|
| Precision@K | \|Top-K ∩ Relevant\| / K | Relevant = grade ≥ 1 among eligible; pad missing ranks as non-hits |
| MRR@K | Reciprocal rank of first relevant item within Top-K (0 if none) | Same relevant definition |
| NDCG@K | DCG@K / IDCG@K with graded gains | Eligible graded candidates only |
| Top-K false-positive rate | \|Top-K ∩ (grade==0)\| / K | Eligible hard negatives only |
| Coverage / abstention | Fraction of queries with ≥1 eligible relevant; fraction of candidates marked ineligible | Report separately |
| Rank stability / ties | Deferred methodology note for later baseline slices; not a promotion gate here |

Default evaluation cutoffs frozen for this identity: **K ∈ {1, 3, 5}**.

## BPM secondary evidence

| `bpm_evidence` | Meaning |
|---|---|
| `known` | Both reference and candidate expose finite BPM > 0 |
| `missing_reference` | Reference BPM missing/invalid |
| `missing_candidate` | Candidate BPM missing/invalid |
| `missing_both` | Both missing/invalid |

Rules:

- BPM may influence product `total_score` today; ranking **labels** do not treat BPM proximity as theory truth.
- Missing BPM must remain labeled; evaluators must not silently invent a tempo match.
- Queries in this freeze include both BPM-known and BPM-missing cases so secondary evidence is measurable.

## Sanitized candidate / query set

Identity: `sample-brain.aq6.harmonic-ranking.relevance.v1`

Machine-readable fixture: `tests/fixtures/aq6_harmonic_ranking/relevance_benchmark_v1.json`  
Generator / KPI helpers: `src/aq6_harmonic_ranking_relevance.py`

### Coverage requirements (frozen)

Each of the following must appear in at least one query’s candidate pool:

| Case | Requirement |
|---|---|
| DIRECT | eligible grade `3` |
| RELATED | eligible grade `2` |
| TRANSPOSE | eligible grade `1` |
| Incompatible | eligible grade `0` |
| UNCERTAIN evidence | `ranking_eligible=false` (missing key and/or missing mode) |
| BPM known | `bpm_evidence=known` on reference+candidate |
| BPM missing | at least one query or candidate with non-`known` `bpm_evidence` |

All keys/BPM values and synthetic ids are public/synthetic. Paths are relative synthetic tokens only (for example `synthetic/aq6_ranking/...`). No private audio binaries.

### Row fields (minimum)

| Field | Plane |
|---|---|
| `synthetic_id` | ranking set identity |
| `key` / `bpm` | upstream evidence inputs (may be null) |
| `key_evidence` | `modeful` \| `missing_key` \| `missing_mode` \| `unparseable` |
| `bpm_evidence` | see table above |
| `theory_relation` / `theory_compatibility` | #1015 — must match `classify_theory_pair` |
| `relevance_grade` | this plane (`0..3` or null) |
| `ranking_eligible` | this plane (boolean) |

## Partition / leakage policy

| Partition | Role |
|---|---|
| `CALIBRATION` | Exploration / later weight-candidate measurement only |
| `TEST` | Locked evaluation; not for threshold discovery or weight fitting |
| `HOLDOUT` | Locked final check; never fed back into tuning |

Leakage rules:

1. A `query_id` appears in exactly one partition.
2. The same `(reference synthetic_id, candidate synthetic_id)` pair must not appear under two partitions with conflicting grades.
3. TEST/HOLDOUT labels must not be edited to improve a CALIBRATION-tuned ranking score.
4. Theory truth-table cells (#1015) are not partition-split; ranking partitions must not mutate theory cells.
5. Private producer libraries may be used later as an out-of-band reality check only; they never rewrite this public freeze.

## Measurement of current product ranking (allowed, read-only)

Later baseline slices may score live `rate_harmony` / `find_harmony_matches` output against this freeze. This slice freezes labels and metric definitions only. Measuring current weights is permitted; changing them is not.

## Exit criteria (#1016)

- [x] Relevance grades and denominators are frozen
- [x] Candidate/query set covers compatible, incompatible, and uncertain evidence states
- [x] Theory truth and ranking relevance are distinct fields/contracts
- [x] Partition/leakage policy is reproducible
- [x] No private asset or local path is committed

```text
AQ6_RANKING_RELEVANCE_BENCHMARK_FROZEN
```

Alternate exits (not selected): `AQ6_RANKING_BENCHMARK_PARTIAL_HOLD`, `AQ6_RANKING_BENCHMARK_INSUFFICIENT`.

## Follow-on write-heads (out of scope here)

- [#1017](https://github.com/jannekbuengener/sample-brain/issues/1017) — measure current theory correctness baseline (theory plane)
- Later AQ6 ranking baseline / weight-candidate slices — measure against this freeze; no production switch without separate evidence-backed decision
