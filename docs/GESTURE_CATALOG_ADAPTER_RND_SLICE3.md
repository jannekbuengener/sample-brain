# Gesture Catalog Adapter R&D — Slice 3 (#680 / #886)

**Status:** R&D contract frozen; implementation delivered. See post-implementation result.

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)
**Child:** [#886](https://github.com/jannekbuengener/sample-brain/issues/886)
**Dependencies (DONE):** [#827](https://github.com/jannekbuengener/sample-brain/issues/827), [#882](https://github.com/jannekbuengener/sample-brain/issues/882) / `docs/GESTURE_LIBRARY_RANKING_RND_SLICE2.md`

## Goal

Bind #882 ranking to real catalog feature rows via one small **read-only** adapter. Ranking math stays exclusively in `#882`.

```text
catalog.db (read-only)
  → load_gesture_library_candidates(...)
  → tuple[LibraryCandidate, ...]
  → rank_gesture_library_candidates(...)   # unchanged #882
  → tuple[ClusterRanking, ...]
```

## Live foundation (verified on `origin/main` @ `84e5dfa3`)

| Surface | Fact |
|---------|------|
| Ranking | `src/gesture_library_ranking.py` — `LibraryCandidate` + `rank_gesture_library_candidates` authoritative; **do not modify** |
| Catalog fields | `samples.id`, `samples.path`; `features.class`, `loudness`, `brightness`, `mfcc_mean` |
| MFCC storage | `mfcc_mean` = 13×`float32` BLOB from analyze |
| Workbench seam | `src/workbench_catalog.py` read-only but **no `mfcc_mean`**; WorkbenchRow/QML coupled |
| Concurrent PR | [#884](https://github.com/jannekbuengener/sample-brain/pull/884) QML/footer + `docs/CANON_INDEX.md` — **do not touch** |

## Ownership decision: dedicated R&D adapter (A)

**Chosen:** `src/gesture_catalog_adapter.py` — smallest ownership without UI/Workbench coupling.

**Rejected for this slice:** extending `workbench_catalog` / `CatalogSampleRow` (missing MFCC; UI contract expansion).
**Rejected:** reusing `classify.py` row loop (owns writes).

## Public seam (smallest clear form)

Module: `src/gesture_catalog_adapter.py` (absent at TEST_FREEZE).

```text
load_gesture_library_candidates(
    catalog_path: Path | str | None = None,
) -> tuple[LibraryCandidate, ...]

rank_gesture_against_catalog(
    analysis: GestureAnalysis,
    catalog_path: Path | str | None = None,
    *,
    top_n: int = 5,
) -> tuple[ClusterRanking, ...]
```

Both seams earn their place:

1. **`load_gesture_library_candidates`** — pure projection (testable without gesture audio).
2. **`rank_gesture_against_catalog`** — thin composition only: load → call `#882` ranker. No ranking duplication.

No status-enum API salad. Fail-soft unavailable cases return empty tuples / empty `#882` rankings.

### Composition contract (mandatory)

`rank_gesture_against_catalog` **must**:

1. `candidates = load_gesture_library_candidates(catalog_path)`
2. `return rank_gesture_library_candidates(analysis, candidates, top_n=top_n)`

No copy/paste of median prototype, RMS→dBFS, z-score, L2, Top-N, or tie-break.

`top_n <= 0` → propagate `#882` `ValueError` (fail-closed API misuse).

## Sample-id authority

| Source | Rule |
|--------|------|
| Catalog | `samples.id` is the stable DB identity |
| `#882` | `LibraryCandidate.sample_id: str` |
| Freeze | `sample_id = str(samples.id)` (decimal, no padding) |

**Not** identity: path, display name, filename, relpath.
`path` may be passed only as optional reference (`LibraryCandidate.path`).

## MFCC decoding (exact)

```text
mfcc_mean BLOB → np.frombuffer(blob, dtype=np.float32)
```

Valid only when blob present, decodable, **exactly 13** values, **all finite**.

Malformed → exclude/fail-closed for that row. **No** padding, truncation, or NaN imputation.

## Required feature row (productive candidate)

All required:

- features row present
- `class == "oneshot"`
- `loudness` finite
- `brightness` finite
- `mfcc_mean` valid MFCC13 (above)
- sample id valid (`samples.id` integer-convertible / present)
- path valid non-empty string (existing catalog path contract)

Invalid rows are skipped deterministically. One broken row must not crash the catalog load.

## Read-only guarantee

Prefer SQLite URI `file:<path>?mode=ro` (same family as `workbench_catalog`).

Forbidden against the user catalog: `init_db()`, schema migration, `INSERT`/`UPDATE`/`DELETE`/`CREATE`, PRAGMA writes.

Tests must prove table set and feature contents unchanged after adapter calls.

## Fail-soft contract (`load_gesture_library_candidates`)

| Condition | Result |
|-----------|--------|
| catalog missing / not a file | `()` |
| catalog unreadable | `()` |
| missing required tables | `()` |
| empty DB | `()` |
| valid DB, zero eligible candidates | `()` |

No crash for ordinary unavailable/invalid-catalog cases.

## Order / determinism

- SQL row order is semantically irrelevant.
- Projection returns candidates in **ascending numeric `samples.id` order** (then `sample_id=str(id)`).
- Final ranking authority remains `#882` (distance → `sample_id` tie-break). Projection order must not change ranking semantics.

## Quality / evidence boundary

| Label | Meaning |
|-------|---------|
| MEASURED | projected fields, MFCC length, deterministic load/rank outputs |
| HEURISTIC | same onset-window vs full-file feature mismatch as `#882` |
| NOT YET CLAIMED | producer-quality match, drum roles, musical correctness, confidence |

## R&D exit (after later implementation)

Exactly one of: `CATALOG_ADAPTER_VIABLE` | `CATALOG_ADAPTER_INSUFFICIENT` | `INSUFFICIENT_EVIDENCE`

Viable means only: real catalog schema can be safely and deterministically projected into the `#882` candidate/ranking seam — **not** producer-quality validation.

Seconds→musical-time remains a separate later decision. Parent `#680` stays OPEN.

## Acceptance tests

See `tests/test_gesture_catalog_adapter_886.py`.

## Non-goals

No ranking algorithm/weight changes, embeddings/CLAP/vector search, Pattern/Channel/Trigger, BPM/seconds→beats/quantization, QML/UI, DB migration/writes, drum labels, auto-accept rank 1, producer-quality claim, `#884` / `docs/CANON_INDEX.md` edits.

## Post-implementation result

| Field | Value |
|-------|-------|
| Implementation seam | `src/gesture_catalog_adapter.py` — `load_gesture_library_candidates` + `rank_gesture_against_catalog` |
| Measured tests | Focused `tests/test_gesture_catalog_adapter_886.py`: **30 passed**; `#882`: **23 passed**; Slice-1: **9 passed**; protected Workbench/analyze/DB/Pattern/Channel group: **129 passed** (161 with `#882`+Slice-1) |
| Read-only evidence | Temp catalog mtime + table/feature snapshots unchanged across load+rank (frozen test 21) |
| R&D EXIT | `CATALOG_ADAPTER_VIABLE` |
| Quality claim | `CATALOG_INTEGRATION_ONLY — PRODUCER_QUALITY_NOT_VALIDATED` |
