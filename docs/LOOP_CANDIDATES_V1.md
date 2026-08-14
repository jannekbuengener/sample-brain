# Loop Candidates v1 — Bar-Aligned 4/8/16-Bar Generation

**Issue:** [#251](https://github.com/jannekbuengener/sample-brain/issues/251)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230)
**Depends on:** [#236](https://github.com/jannekbuengener/sample-brain/issues/236) (BeatGrid), [#250](https://github.com/jannekbuengener/sample-brain/issues/250) (Asset Manifest v1)
**Module:** `src/loop_candidates.py`
**Tests:** `tests/test_loop_candidates.py`
**Status:** implemented

This document describes the deterministic loop-candidate generator delivered
for #251. It produces reproducible 4-, 8-, and 16-bar loop candidates from
**real BeatGrid downbeat sample indices only**. It does not estimate bar
lengths from BPM, normal beats, or seconds, and it does not render audio.

---

## 1. Practical meaning

A loop candidate is a half-open sample interval `[start_sample, end_sample_exclusive)`
that is bounded on both sides by **real downbeats** from the BeatGrid result. The
generator enumerates, for every bar count in `{4, 8, 16}` and every valid start
downbeat, the window that ends at the downbeat `bar_count` bars later. Because
both endpoints are genuine downbeats, the loop is musically aligned to the
track's real bar grid on the shared #234 sample timebase.

The output is intentionally **candidates only**: no quality scoring (#252), no
section semantics (#266), no audio rendering (#253). Each candidate carries
neutral section-boundary crossing context so that later steps can decide what to
do with loops that straddle an arrangement boundary.

---

## 2. The 4/8/16-bar rule

For each `bar_count` in `(4, 8, 16)` and each start index `i` into the real
downbeat array:

```
end_index = i + bar_count
if end_index < len(downbeats):
    start_sample        = downbeats[i]
    end_sample_exclusive = downbeats[end_index]
    # emit candidate
```

- `start_bar = i` (inclusive, zero-based on the downbeat grid).
- `end_bar_exclusive = i + bar_count`.
- `bar_count ∈ {4, 8, 16}` exactly.
- A candidate is emitted **only if** `end_index` is a real downbeat inside the
  grid. No candidate is created when the window would run past the last real
  downbeat.

---

## 3. Real downbeats are mandatory

The primary rhythm source is **exclusively** `BeatGridResult.downbeats.sample_indices`
(or an equivalent explicitly supplied real downbeat grid). The generator never:

- derives bars from `BeatGridResult.beats`,
- estimates `bar_count * BPM-derived duration`,
- estimates `bar_count * estimated_bar_samples`,
- treats the track end as a synthetic final downbeat,
- converts normal beats into downbeats.

If the current librosa fallback returns `DOWNBEATS_UNAVAILABLE` (its
`downbeats.status == "no_result"`), the generator returns a status-based
result with **no candidates**. This is correct behavior, not a failure: without
real downbeats there is nothing authoritative to align a loop to.

---

## 4. Sample timebase & half-open range

All boundaries are integer sample indices on the #234 canonical timebase
(`AudioTimebase`). Seconds are derived only and never authoritative.

- `range.start_sample` is inclusive.
- `range.end_sample_exclusive` is exclusive (the sample immediately after the loop).
- `n_samples = end_sample_exclusive - start_sample`.

This reuses the `AudioRange` half-open semantics from #234. Invalid ranges are
rejected by consumers (fail-closed); the generator itself only ever emits
intervals whose endpoints are two distinct real downbeats.

---

## 5. Boundary-crossing marking (context, not score)

Optional StructureV1 section-boundary evidence may be supplied. For each
candidate, internal section boundaries that fall **strictly inside**
`(start_sample, end_sample_exclusive)` are recorded as a crossing:

- `boundary.section_crossing.crosses` is `True` when at least one internal
  boundary exists.
- `boundary.section_crossing.crossed_sample_indices` lists those sample indices.
- A boundary that sits **exactly** at `start_sample` or at `end_sample_exclusive`
  is **not** an internal crossing.

Crossing is **context only**. The generator never rejects, scores, or otherwise
penalizes a candidate for crossing a section boundary. The musical usability
decision belongs to #252. No generic `confidence` field is invented.

---

## 6. Source identity is preserved

Each candidate carries a `LoopSourceIdentity` mirroring the #250
`source.source_kind` vocabulary:

- `master` → `track_audio_ref` (defaults to `/source/working_audio`).
- `stem` → `stem_id` + `stem_ref`.
- `producer_group` → `producer_group_id` + `producer_group_ref`.

Technical stems and producer groups are never equated or substituted. The
generator only forwards this identity; it does not fabricate audio or hashes
(audio identity is supplied by the caller / Track Map).

---

## 7. Status behavior on missing downbeats

| Input state | Result status | reason_code | Candidates |
|-------------|---------------|-------------|------------|
| Real downbeats present, enough for ≥1 window | `ok` | `None` | enumerated |
| `downbeats.status == "no_result"` (`DOWNBEATS_UNAVAILABLE`) | `no_result` | `DOWNBEATS_UNAVAILABLE` | none |
| `downbeats.status == "failed"` | `failed` | `DOWNBEATS_FAILED` | none |
| Real downbeats present but too few for any window | `no_result` | `INSUFFICIENT_DOWNBEATS` | none |
| Non-monotonic / invalid downbeat grid | `failed` | `INVALID_DOWNBEAT_GRID` | none |

Missing optional StructureV1 evidence does **not** block generation. Invalid
inputs are never silently corrected (fail-closed).

---

## 8. Mapping to Asset Manifest v1 (#250)

`LoopCandidate.as_manifest_dict()` returns the manifest-mappable subset this
module owns:

- `asset_kind = "loop"`
- `source` → identity block per Section 5.
- `range` → `start_sample`, `end_sample_exclusive`, `n_samples`.
- `loop.bars` → `start_bar`, `end_bar_exclusive`, `bar_count`;
  `loop.downbeat_start_sample = range.start_sample`; `loop.bar_grid_ref`.
- `boundary` → `source = beat_grid`, `status = ok`, `kind = bar_grid`,
  plus the section-crossing context.
- `candidate.status = "candidate"`, `excluded = false` (no scores preempted).
- `rendering.status = "not_rendered"`.

The full Asset Manifest (audio hashes, provenance registry, analysis block) is
assembled by later steps (#253 / #255); this module only fills the
loop/range/boundary/candidate extension points from #250 §16.

---

## 9. Non-goals (explicitly out of scope for #251)

- No BPM × seconds approximation — bars come from the real downbeat grid only.
- No loop seam / quality scoring — that is #252.
- No section candidates — that is #266.
- No audio rendering, crossfades, or reanalysis — #253 / #254.
- No producer-group or stem generation — #268 / #255.
- No new dependencies or workflows.

---

## 10. Acceptance mapping (Issue #251)

| #251 criterion | This module |
|----------------|-------------|
| 4/8/16-bar candidates are reproducible | Deterministic enumeration; same input → same candidates and order. |
| Each candidate begins and ends on real downbeat indices | `start_sample = downbeats[i]`, `end_sample_exclusive = downbeats[i + N]`. |
| Start/end samples are integer, on shared timebase | Integer sample indices; half-open `AudioRange`. |
| No time-based BPM approximation | Only `downbeats.sample_indices` consumed. |
| Candidates conform to #250 | `as_manifest_dict()` maps to #250 loop fields. |
| Section crossing marked, not evaluated | `boundary.section_crossing`. |
| Master/stem/producer_group preserved | `LoopSourceIdentity`. |
| Missing downbeats → no candidate | Status-based `no_result` / `failed`. |

---

## 11. Related documents

- [Asset Manifest v1](ASSET_MANIFEST_V1.md) (#250) — loop/range/boundary contract.
- [Canonical Audio & Timebase](CANON_AUDIO_TIMEBASE.md) (#234) — sample timebase, half-open range.
- [BeatGrid backend adapter](BEATGRID_BACKEND.md) (#236) — downbeat source.
- [StructureV1 Boundary Backend](STRUCTURE_V1.md) (#265) — neutral section boundaries (crossing context).
