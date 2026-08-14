# Arrangement Pilot v1

## Scope and privacy

This pilot ran the existing local-only arrangement path against four private
tracks and compared the output with the supplied human listening reference.
The report uses only `track_01` through `track_04`. It contains no audio,
source filenames, paths, hashes, caches, or raw runtime payloads.

The evidence is descriptive pilot evidence, not a quality benchmark or a
production-readiness claim.

## Runtime

The pilot worktree started from `163c26d6f4f4d97e7b759c1e6861597bf9e01b16`
and used:

```text
canonical mono WAV -> BeatGrid -> StructureV1 -> SectionSignalsAssembler
-> ArrangementClassifier -> Arrangement Map
```

All four runs used the `librosa` fallback. It supplied beats but no observed
downbeats, so StructureV1 used its explicit `infer_4_4_from_beats` policy.
Every StructureV1 result was consequently `partial`; the report does not treat
the inferred bar grid as observed downbeats.

The pilot exposed a contract regression: `bar_loudness_delta` was required by
the classifier but absent from StructureV1's public bar evidence. This slice
adds the existing-contract derivation from bar-synchronous RMS energy before
the results below were re-run. It is not a pilot-specific heuristic change.

For boundary observations, a reference start is called *near* when its nearest
neutral boundary is within three seconds. This is a descriptive aid only, not
a ground-truth tolerance. The human `groove` reference is a four-bar excerpt;
where it starts at the same time as `build`, the two role labels are explicitly
ambiguous for a single automatic section.

## Track results

| Track | Boundary finding | Role finding at human reference starts | `drop_onset` | Unknown / uncertain | Primary error class |
| --- | --- | --- | --- | --- | --- |
| `track_01` | The starts of groove/build, drop, and outro were near; breakdown was about 11 s early. | The classifier produced `intro` at the coincident groove/build start and `groove` at drop, breakdown, and outro. | Missing. | Arrangement status `uncertain` because StructureV1 was partial; no role was forced from missing signal evidence. | `wrong_role` |
| `track_02` | Groove/build, breakdown, and outro were near; the closest drop boundary was about 10 s early. | Breakdown and outro matched. The coincident groove/build start was `unknown`; drop was `groove`. | Missing. | The `unknown` at the coincident groove/build reference is a defensible abstention; it is not counted as a forced role. | `missing_drop_onset` |
| `track_03` | Groove/build, breakdown, and drop were near; no useful outro boundary was found (nearest about 88 s early). | Groove and drop matched. Breakdown was `unknown`; outro was `groove`. | Missing. | The breakdown abstention is retained as `unknown`; cause beyond the inferred grid is unclear from the available evidence. | `missing_boundary` |
| `track_04` | Groove/build, breakdown, drop, and outro were all near. | Groove and outro matched; breakdown was `outro` and drop was `groove`. | Missing. | Results remain `uncertain` at track level because the bar grid was inferred. | `wrong_role` |

## Aggregated findings

- Tracks executed through the complete production path: 4/4.
- BeatGrid/bar grid: all four used `librosa` with inferred 4/4 bars; none had
  observed downbeats.
- Boundaries: 13 of 16 distinct non-initial human reference starts had a
  nearest neutral boundary within the descriptive three-second window. The
  remaining failures were a roughly 10 s offset, an 11 s offset, and a missing
  useful outro boundary.
- Roles: the classifier produced useful matches for selected groove, drop,
  breakdown, and outro references, but it also confused high-energy drop and
  breakdown/outro contexts. Coincident groove/build starts are intentionally
  not treated as a clean role-error benchmark.
- Events: no automatic `drop_onset` was emitted for any of the four manually
  marked drops. The recurring error class is `missing_drop_onset`.
- `unknown` remained available as an honest result. No `transition` role was
  emitted or required to preserve the v1 contract in these four runs.

## Conclusion and follow-ups

The v1 path now carries the required loudness-delta evidence end to end and can
produce non-`unknown` roles on inferred bar grids. It is not sufficiently
reliable on this small private collection to claim production readiness:
`drop_onset` recall is absent, and role/context mistakes remain.

The pilot required one small, contract-aligned fix for the missing public
`bar_loudness_delta` series. It does not tune weights or thresholds to these
tracks. A separate follow-up is appropriate for inferred-bar-grid and
`drop_onset` quality only after deduplication; optional CLAP and all-in-one
comparison scopes remain outside this pilot.
