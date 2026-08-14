# Loop Scoring v1 — Reproducible Musical-Usability Scoring

**Issue:** [#252](https://github.com/jannekbuengener/sample-brain/issues/252)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230)
**Depends on:** [#251](https://docs/LOOP_CANDIDATES_V1.md) (Loop Candidates), [#250](https://docs/ASSET_MANIFEST_V1.md) (Asset Manifest v1)
**Module:** `src/loop_scoring.py`
**Tests:** `tests/test_loop_scoring.py`
**Status:** implemented

This document describes the deterministic loop-candidate scoring delivered for
#252. It consumes a loop candidate from #251 plus the candidate's monophonic
waveform slice and returns **separated, traceable score components** plus
**hard-exclusion reasons**. It is the companion scoring step that decides which
4/8/16-bar candidates from #251 are musically usable *before* any rendering (#253).

---

## 1. What is practically scored

For every candidate we compute a small, independent set of physical/signal
metrics from the waveform slice only. Nothing is estimated from BPM, no model
is downloaded, no audio is mutated, and no crossfade is applied.

The scoring is **pure and deterministic**: the same `(candidate, waveform,
config)` always produces the same result, which makes it reproducible and
testable. The waveform slice is expected to be the exact half-open sample
interval `[start_sample, end_sample_exclusive)` from the candidate on the #234
canonical timebase.

---

## 2. Score components

Each component has an explicit name, a value, a value range, a documented
meaning, and a status. Components with missing evidence are reported with
`status != "ok"` and `value is None` — **no dummy zeros are invented**.

| Component | Range | Meaning |
|-----------|-------|---------|
| `seam_continuity` | `[0, 1]` | End-to-start loop continuity; higher = smoother seam, less likely to click when repeated. |
| `internal_stability` | `[0, 1]` | Consistency of bar energy across the loop; higher = steadier internal repetition. |
| `groove_stability` | `[0, 1]` | Similarity of per-bar onset/groove patterns; higher = more consistent rhythm. |
| `energy_distribution` | `[0, 1]` | Dynamic spread of energy across the loop; higher = more energetic variation, lower = flatter. |
| `edge_silence_risk` | `[0, 1]` | Risk that the loop edges are silent/near-silent; higher = more likely dead start or end. |
| `transition_bleed_risk` | `[0, 1]` | Risk from crossing a neutral section boundary inside the loop (transition bleed); `1.0` when a crossing is present, else `0.0`. |
| `vocal_fx_edge_risk` | `[0, 1]` | Risk from explicit vocal/FX edge evidence; set **only** when real evidence is supplied, otherwise `not_evaluated` (never invented). |

### 2.1 End-to-start seam (separate check)

The seam is evaluated explicitly and separately from all other metrics:

- The first and last `edge_window_ms` of the candidate are compared (small,
  configurable window; default **5 ms**).
- A deterministic discontinuity metric combines an amplitude/RMS gap and a
  shape (cosine) gap between the end edge and the start edge.
- Result: `seam_continuity = 1 - discontinuity`, clipped to `[0, 1]`.
- A **bad seam can trigger a hard exclusion** (see §4). A good seam is never
  silently "repaired" with a crossfade.

No crossfade is ever applied and no audio is modified.

### 2.2 Internal stability, groove, energy (separate and visible)

- **Internal stability** splits the loop into its `bar_count` bars (the
  candidate is bar-aligned on real downbeats) and measures how consistent the
  per-bar RMS energy is.
- **Groove stability** derives a per-bar onset pattern from the rectified
  difference envelope and measures the cosine similarity between consecutive
  bars.
- **Energy distribution** measures the dynamic spread of the RMS envelope
  sampled across the whole loop.

Each is reported independently so a downstream consumer can see *why* a loop
scores the way it does; none is folded into a single opaque number.

---

## 3. Status handling for missing evidence

- If no waveform is supplied (`waveform is None`), the result is
  `status = "no_evidence"`; all components are `not_evaluated` with `value None`,
  no hard exclusion, and no invented values.
- Invalid inputs (wrong waveform length vs `candidate.n_samples`, non-finite
  samples) **fail closed** with `ValueError` rather than being silently
  corrected.
- `vocal_fx_edge_risk` is `not_evaluated` unless explicit
  `LoopEdgeRiskEvidence` is passed in.

---

## 4. Hard exclusions vs soft scores

Hard exclusions are reported **separately** from the numeric scores, in
`reject_reasons`. This lets downstream consumers distinguish "low score" from
"invalid / unusable".

| Reason code | Trigger |
|-------------|---------|
| `SEAM_DISCONTINUITY` | `seam_continuity < seam_hard_min_continuity` (configurable). |
| `EDGE_SILENCE` | start or end edge RMS below `silence_edge_rms_max`. |
| `TOO_QUIET` | overall loop RMS below `min_loop_rms`. |

When any hard reason fires, `hard_rejected = True` and the manifest candidate
status becomes `rejected`. The soft score components are still populated so the
decision remains fully traceable.

A `transition_bleed_risk` of `1.0` **does not** by itself hard-reject a
candidate — it is surfaced as a risk for the human/pilot to weigh.

---

## 5. Transition bleed

Transition bleed reuses the neutral section-crossing evidence already carried by
the #251 candidate (`boundary.section_crossing.crosses`). If the loop straddles
a neutral arrangement boundary, `transition_bleed_risk = 1.0`. This is kept
separate from the seam metric and from vocal/FX risk so the three transition
concerns never blur together.

---

## 6. Vocal / FX evidence and missing-evidence behavior

There is **no vocal or FX detection** in this slice. Vocal/FX edge risk is
asserted **only** when the caller passes explicit `LoopEdgeRiskEvidence`
(e.g. from a manual review or a later model). Without such evidence the
component is `not_evaluated` and no positive or negative judgement is invented.

---

## 7. Source-specific configuration

All physical metrics are shared across `master`, `stem`, and `producer_group`
sources (technical stems and producer groups are never equated). However,
thresholds and weights can be configured **per `source_kind`** via
`LoopScoringConfig.source_kind_thresholds`. This lets, for example, a producer
group tolerate a different seam tolerance than a master without changing the
shared metric math. No producer-group generation (#268) is performed here.

---

## 8. Configurable, provisional thresholds

All thresholds live in `LoopScoringConfig` / `LoopScoringThresholds` and are
fully overridable:

- `edge_window_ms` (default 5.0)
- `seam_hard_min_continuity` (default 0.35)
- `silence_edge_rms_max` (default 1e-3)
- `min_loop_rms` (default 5e-3)
- `weights` for the optional summary score

**No final global thresholds are frozen in this contract.** These defaults
exist so v1 is reproducible and testable, but they are explicitly provisional
and must be calibrated from real evidence in the Techno pilot **#256** before
being treated as a global truth. Changing a threshold reproducibly changes the
decision (covered by tests).

An optional `summary_score` is provided as a **documented, deterministic,
weighted** combination of the soft components minus the risk penalties. It is
clearly a heuristic ranking aid, not a universal musical truth, and the
individual components are always retained.

---

## 9. Asset Manifest mapping (#250 §10)

`LoopScoreResult.as_candidate_dict()` returns a block that maps cleanly to the
Asset Manifest v1 `candidate` extension point:

- `status`: `candidate` or `rejected`
- `score_components`: per-component `{name, value, range, meaning, status}`
- `excluded`: mirrors `hard_rejected`
- `reject_reasons`: required when `excluded` is true

The `rendering` status of the candidate stays `not_rendered`; this slice never
produces audio or any Section-score fields (#267).

---

## 10. Non-goals (explicit scope boundaries)

- No Section scoring — that is #267.
- No audio rendering, crossfades, or reanalysis — #253 / #254.
- No Section candidates — #266. No producer-group generation — #268.
- No new vocal/FX models; no invented evidence.
- No final global thresholds before #256.
- Loop scoring stays fully separate from Section scoring.

---

## 11. Acceptance mapping (Issue #252)

| #252 criterion | This module |
|----------------|-------------|
| Reproducible score components | Pure deterministic core; same input → same result (tested). |
| Bad seams can reject a candidate | `SEAM_DISCONTINUITY` hard reject (tested). |
| Transition / vocal / FX edge problems visible | `transition_bleed_risk`, `vocal_fx_edge_risk` (status-based; tested). |
| Loop rules not applied to sections | Separate module; no Section fields produced. |
| No default crossfade masks bad seams | No crossfade anywhere; seam only evaluated/quarantined. |
| Thresholds stay configurable until #256 | All in `LoopScoringConfig`, provisional (tested). |

---

## 12. Related documents

- [Loop Candidates v1](LOOP_CANDIDATES_V1.md) (#251) — candidate generation.
- [Asset Manifest v1](ASSET_MANIFEST_V1.md) (#250) — `candidate` / `score_components` contract.
- [Canonical Audio & Timebase](CANON_AUDIO_TIMEBASE.md) (#234) — sample timebase.
- [StructureV1 Boundary Backend](STRUCTURE_V1.md) (#265) — neutral section crossing evidence.
- Section Scoring v1 (#267), Rendering (#253), Techno Pilot (#256) — downstream.
