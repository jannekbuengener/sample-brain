# AQ3 Onset / Attack Decision Memo (no production switch)

**Status:** ACTIVE_SUPPORTING — evidence-backed onset/attack decision for [#999](https://github.com/jannekbuengener/sample-brain/issues/999)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#945](https://github.com/jannekbuengener/sample-brain/issues/945) (AQ3), [#942](https://github.com/jannekbuengener/sample-brain/issues/942) (program)  
**Depends on (CLOSED):** [#991](https://github.com/jannekbuengener/sample-brain/issues/991) KPI contract, [#993](https://github.com/jannekbuengener/sample-brain/issues/993) synthetic corpus, [#995](https://github.com/jannekbuengener/sample-brain/issues/995) onset/attack baseline, [#997](https://github.com/jannekbuengener/sample-brain/issues/997) candidate compare (PR [#998](https://github.com/jannekbuengener/sample-brain/pull/998))  
**Boundary:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680) owns Vocal/Beatbox → Pattern product/R&D. AQ3 owns **measurement quality of onset / attack / gesture timing only**.

## Architecture outcome

```text
AQ3_ONSET_ATTACK_DECISION_MEMO_RECORDED
```

This memo records an **evidence-backed product recommendation** for AQ3 onset/attack path choices from frozen upstream docs. It does **not** change onset/attack/gesture algorithms, set numeric promotion gates, switch production defaults, or reopen #680 product work.

## Evidence map

| Stage | Authority | Outcome token |
|---|---|---|
| Contract | [`AQ3_ONSET_GESTURE_KPI_CONTRACT.md`](AQ3_ONSET_GESTURE_KPI_CONTRACT.md) | `AQ3_ONSET_GESTURE_KPI_CONTRACT_FROZEN` |
| Corpus | [`AQ3_TIMING_CORPUS.md`](AQ3_TIMING_CORPUS.md) / `sample-brain.aq3.timing.synthetic.v1` | `AQ3_TIMING_CORPUS_FROZEN` |
| Baseline | [`AQ3_ONSET_ATTACK_BASELINE.md`](AQ3_ONSET_ATTACK_BASELINE.md) | `AQ3_ONSET_ATTACK_BASELINE_MEASURED` |
| Candidate compare | [`AQ3_ONSET_ATTACK_CANDIDATE_COMPARE.md`](AQ3_ONSET_ATTACK_CANDIDATE_COMPARE.md) | `AQ3_ONSET_ATTACK_CANDIDATE_COMPARE_REPRODUCIBLE` |

Flow: **contract → corpus → baseline → compare → this decision**. Decisions cite those four surfaces only; anecdotes and private library checks are out of band.

## Partition / no-tuning-on-TEST

| Corpus `split` | AQ3 role | Decision use |
|---|---|---|
| `CALIBRATION` | DEVELOPMENT / CALIBRATION | exploration narrative only |
| `TEST` | TEST / HOLDOUT | frozen evidence report; **no threshold discovery / no tuning** |

Inherited from the KPI contract and restated in corpus, baseline, and compare. This memo does not invent gates from TEST/HOLDOUT. Tolerance candidates (20 ms / 50 ms) remain corpus-owned constants, not promotion gates.

## Synthetic corpus limits vs human reality-check

`sample-brain.aq3.timing.synthetic.v1` is a **small deterministic synthetic** GT set (`label_source=synthetic_deterministic`, 4 clips, seed `993001`). It unblocks measurable baselines; it is **not** a substitute for human/reference annotations on difficult material.

| Limit | Status |
|---|---|
| Active thin buckets | `soft_attack`, `silence_leading`, `short_clip`, `simple_multi_onset` only |
| `layered_transient_dense` | HOLD stub — no GT clip in v1 |
| `noisy` | HOLD stub — no GT clip in v1 |
| Gesture plane | HOLD on CALIBRATION; PARTIAL on TEST (thin multi-onset) |
| Human-annotated reality-check | out of band — may diagnose later; must not set public promotion thresholds or enter committed artifacts with private paths/audio |

Synthetic keep-current evidence therefore applies to controlled clips under the frozen corpus identity. It does **not** claim human-grade onset/attack quality on layered/noisy material.

## Separation reminder (normative, inherited)

1. Event detection (`aq3.onset`), attack/cue suggestion (`aq3.attack`), and gesture/rhythm preservation (`aq3.gesture`) remain **separate reporting planes**.
2. Onset success does not imply attack-marker accuracy; attack accuracy does not imply gesture IOI/order quality.
3. AQ3 timing quality does not imply #680 sample retrieval, role clustering-as-selection, Rack mutation, or UI quality.

## Recommendation

```text
KEEP_CURRENT_BASELINE_PATH
```

**Justification (brief):**

1. **Frozen contract** separates onset / attack / gesture planes, partitions CALIBRATION vs TEST/HOLDOUT, and keeps #680 product scope out of AQ3 measurement ([`AQ3_ONSET_GESTURE_KPI_CONTRACT.md`](AQ3_ONSET_GESTURE_KPI_CONTRACT.md)).
2. **Synthetic corpus + measured baseline** record the current surfaces (`analyze_gesture_audio` / `suggest_attack_ms`) on `sample-brain.aq3.timing.synthetic.v1` with explicit denominators and tolerance candidates; gesture remains PARTIAL/HOLD where coverage is thin ([`AQ3_TIMING_CORPUS.md`](AQ3_TIMING_CORPUS.md), [`AQ3_ONSET_ATTACK_BASELINE.md`](AQ3_ONSET_ATTACK_BASELINE.md)).
3. **Candidate compare** on frozen TEST shows thin config adapters do **not** dominate `gesture_attack.baseline.v1` across planes: more-sensitive onset delta lowers CALIBRATION onset F1 without improving TEST; tighter gap matches baseline here; lower attack energy ratio worsens CALIBRATION attack abs error without improving TEST ([`AQ3_ONSET_ATTACK_CANDIDATE_COMPARE.md`](AQ3_ONSET_ATTACK_CANDIDATE_COMPARE.md) tables + non-promotional observation). CALIBRATION-only deltas are not a production promotion proof.

**Adapter / bake-off limits:** the #997 compare used thin keyword overrides over the **same** baseline surfaces (onset delta/gap; attack `energy_ratio`). It does **not** evaluate new onset backends, ML detectors, gesture redesigns, live production default changes, or #680 product paths. Adapter knobs alone do not justify a production default change.

Alternative tokens considered and **not** chosen:

- `DEFER_PROMOTION` — redundant with keep-current once no candidate is promoted and production stays on the measured baseline path.
- `NEED_FURTHER_CANDIDATES` — may apply later if product quality work targets new onset/attack backends, layered/noisy human annotations, or fuller gesture coverage; it is not required to record this keep-current decision from the existing four-doc chain.

## Explicit non-action (this slice)

- **No production default change** (no switch of gesture onset knobs, attack-suggest thresholds, or related analyzer defaults).
- No onset / attack / gesture algorithm changes.
- No numeric promotion thresholds / gates invented from TEST/HOLDOUT.
- **No #680 product work** (retrieval, clustering-as-selection, Rack mutation, microphone/UI).
- No private audio or absolute host paths in committed artifacts.

## Boundary vs #680

| Owned by AQ3 (this memo / #945) | Owned by #680 (not AQ3) |
|---|---|
| Evidence-backed keep-current recommendation for timing measurement path | Vocal/Beatbox → Pattern product/R&D |
| Citation of contract / corpus / baseline / compare | Sample retrieval / ranking for gesture roles |
| Explicit non-promotion of thin adapters | Sound-role clustering as selection authority; Rack / UI scope |

AQ3 may supply quality evidence that #680 consumes. This memo must not reopen or duplicate #680 workstreams.

## Exit vocabulary

Exactly one:

- `AQ3_ONSET_ATTACK_DECISION_MEMO_RECORDED`
- `AQ3_ONSET_ATTACK_DECISION_INSUFFICIENT_EVIDENCE`

This slice exits `AQ3_ONSET_ATTACK_DECISION_MEMO_RECORDED` with recommendation `KEEP_CURRENT_BASELINE_PATH`, synthetic-corpus limits and HOLD stubs acknowledged, #680 boundary preserved, and no production switch.
