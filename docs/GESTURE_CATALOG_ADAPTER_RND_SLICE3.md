# Gesture Catalog Adapter R&D — Slice 3 (#680 / #886)

**Status:** R&D contract frozen at DOCS_GATE / TEST_GATE. Product module not implemented in this gate run.

**Parent:** [#680](https://github.com/jannekbuengener/sample-brain/issues/680)
**Child:** [#886](https://github.com/jannekbuengener/sample-brain/issues/886)
**Dependencies (DONE):** [#827](https://github.com/jannekbuengener/sample-brain/issues/827), [#882](https://github.com/jannekbuengener/sample-brain/issues/882) / `docs/GESTURE_LIBRARY_RANKING_RND_SLICE2.md`

## Goal

Bind the delivered #882 ranking seam to **real existing catalog feature rows** through one small **read-only** adapter:

```text
catalog.db (read-only)
  → catalog feature projection
  → tuple[LibraryCandidate, ...]
  → rank_gesture_library_candidates(...)   # unchanged #882 seam
  → tuple[ClusterRanking, ...]
```

No ranking-math changes. No Pattern / Channel / Trigger mutation. No producer-quality claim.

## Live foundation (verified on `origin/main` @ `84e5dfa3`)

### Ranking (#882)

- Module: `src/gesture_library_ranking.py`
- Input: frozen `LibraryCandidate{sample_id:str, path, audio_class, loudness, brightness, mfcc13}`
- Public: `rank_gesture_library_candidates(analysis, candidates, *, top_n=5) -> tuple[ClusterRanking, ...]`
- Core remains SQLite-independent and authoritative — **this slice must not modify it**

### Catalog schema (`src/db.py` / analyze)

- `samples.id`, `samples.path`
- `features.class`, `features.loudness`, `features.brightness`, `features.mfcc_mean`
- `mfcc_mean` stored as **13×`float32` BLOB** (`np.mean(mfcc, axis=1).astype(np.float32).tobytes()`)
- Decode contract (same family as `classify.rule_type`): `np.frombuffer(blob, dtype=np.float32)` → length **13**, all finite

### Workbench catalog seam (`src/workbench_catalog.py`)

- Read-only SELECT projection for Workbench/UI
- Projects `loudness`, `brightness`, `class` — **does not project `mfcc_mean`**
- Couples toward `WorkbenchRow` / QML browser surfaces

### Concurrent open PR

- [#884](https://github.com/jannekbuengener/sample-brain/pull/884) touches `src/workbench_qml.py`, program-chrome/footer docs, **`docs/CANON_INDEX.md`**, related QML tests
- This slice **must not** touch those paths (including `docs/CANON_INDEX.md`)

## DOCS_GATE ownership decision: **A — dedicated R&D adapter**

| Option | Verdict |
|--------|---------|
| **A. Small own R&D catalog adapter** | **Chosen** — projects only fields required by `LibraryCandidate`; read-only SQLite; no Workbench/QML coupling |
| B. Reuse/extend `workbench_catalog` / `CatalogSampleRow` | Rejected for this slice — missing `mfcc_mean`; expanding it would widen UI/Workbench contracts without need |
| B′. Reuse `classify.py` row loop | Rejected — owns writes (`UPDATE features.pred_type`); not a read-only reusable projection seam |

Reuse without ownership expansion: same tables/columns and the same float32 MFCC decode convention as analyze/classify. No second catalog system.

## Public seam (to implement after TEST_FREEZE)

Module: `src/gesture_catalog_adapter.py` (not present at TEST_FREEZE).

```text
project_library_candidates_from_catalog(
    catalog_path: Path | str | None = None,
) -> CatalogCandidateProjection

rank_gesture_against_catalog(
    analysis: GestureAnalysis,
    catalog_path: Path | str | None = None,
    *,
    top_n: int = 5,
) -> CatalogGestureRankResult
```

### Result contracts

```text
CatalogCandidateProjection (frozen)
  status: str   # ok | missing_catalog | unreadable | empty
  candidates: tuple[LibraryCandidate, ...]
  excluded_count: int   # rows seen but excluded (missing/malformed/non-oneshot/…)

CatalogGestureRankResult (frozen)
  status: str   # same vocabulary as projection status when projection fails;
                # when projection status is ok|empty, ranking proceeds and status stays that value
  candidates: tuple[LibraryCandidate, ...]
  rankings: tuple[ClusterRanking, ...]   # from #882 ranker only
  excluded_count: int
```

### Status semantics (fail soft / fail closed)

| Condition | `status` | `candidates` | `rankings` |
|-----------|----------|--------------|------------|
| Path missing / not a file | `missing_catalog` | `()` | `()` |
| File present but unreadable / not a catalog | `unreadable` | `()` | `()` |
| Readable catalog, zero eligible oneshots | `empty` | `()` | #882 empty-pool rankings for clusters in `analysis` (or `()` if analysis has no events) |
| ≥1 eligible candidate | `ok` | projected tuple | #882 rankings |

`top_n <= 0` → propagate #882 fail-closed (`ValueError`) from the ranker; adapter must not swallow it.

## Frozen projection rules

1. **Read-only** SQLite URI `mode=ro` (same family as `workbench_catalog`). No writes, no schema migration, no `CREATE`/`ALTER`.
2. SQL projects only: `samples.id`, `samples.path`, `features.class`, `features.loudness`, `features.brightness`, `features.mfcc_mean` via `samples` LEFT JOIN `features`.
3. **Identity:** `LibraryCandidate.sample_id = str(int(samples.id))` (decimal, no padding). Path may be copied as `path` (optional for distance math).
4. **Eligible row** requires all of:
   - features row present (`features.sample_id` not NULL)
   - `class == "oneshot"`
   - `loudness` and `brightness` finite floats
   - `mfcc_mean` blob decodes to exactly 13 finite `float32` values
5. Exclude (count in `excluded_count`) when: missing features, loop/other class, NULL/non-finite loudness/brightness, MFCC missing/wrong byte length/non-finite.
6. **No ranking math** in the adapter: normalization, L2, Top-N, tie-break stay exclusively in `rank_gesture_library_candidates`.
7. SQL/fetch order must not affect semantic ranking (#882 already canonicalizes by `sample_id`); projection output should still be deterministic — freeze **sort projected candidates by `sample_id` ascending** before return.
8. Do not mutate `GestureAnalysis` / onset times / cluster IDs.
9. No embeddings, CLAP, search backends, Workbench/QML imports, Pattern/Channel/Trigger creation, BPM/seconds→beats/quantization.
10. Optional local-catalog evidence outside repo only; never commit private paths/DBs/audio.

## Quality labels

| Label | What |
|-------|------|
| MEASURED | Projected field values, MFCC decode length, excluded_count, deterministic ranking identity/distances via #882 |
| HEURISTIC | Same window-mismatch caveat as #882 (onset-window vs full-file catalog features) |
| NOT YET CLAIMED | Producer-quality match, drum-role naming, musical correctness, calibrated confidence |

## R&D exit (after implementation + evidence)

Exactly one of:

- `CATALOG_ADAPTER_VIABLE`
- `CATALOG_ADAPTER_INSUFFICIENT`
- `INSUFFICIENT_EVIDENCE`

Synthetic temp-DB tests prove the projection/composition contract; they cannot alone prove producer-quality retrieval on a private library.

If viable, **source-seconds → musical-time** remains a **separate later decision** before any Pattern Core mutation. Parent #680 stays OPEN.

## Acceptance tests

See `tests/test_gesture_catalog_adapter_886.py` (frozen at TEST_FREEZE).

## Non-goals

No #882 ranking algorithm changes, embeddings/vector search, Pattern/Channel/Trigger, BPM/quantize/seconds→beats, QML/UI/mic, DB schema/migrations, catalog writes, Kick/Snare/Hat naming, auto-accept rank 1, Arrangement/Screen 3, `docs/CANON_INDEX.md` / #884 paths.
