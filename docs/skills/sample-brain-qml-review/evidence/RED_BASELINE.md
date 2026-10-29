# RED baseline — `sample-brain-qml-review` (#1303)

**Status:** recorded before the skill existed  
**Inputs:** `tests/fixtures/qml_review/red_stale_delegate_index.qml`  
**Capability set used:** generic code-review habits only (no `sample-brain-qml-review`)  
**Repo head at capture:** live `main` at handoff / branch start for #1303

## Scenario

Review a Screen-1-shaped ListView delegate that caches `index` into
`cachedSampleIndex` and later calls `toggleFavorite(cachedSampleIndex)` from a
Timer after `pressAndHold`, with `reuseItems: true`.

## What a generic review noticed

- File is synthetic QML with `reuseItems: true` (recognized as virtualization).
- Immediate `selectRow(index)` on click looks normal for ListView.
- Timer delay of 250ms looks like ordinary UX debounce.
- No obvious Python syntax / type / security issues (fixture is QML-only).

## What was missed (the gap)

1. **Stale visual index as product authority.**
   `property int cachedSampleIndex: index` treats a transient virtualized
   delegate index as stable sample identity across a delayed command path.
   After pool/reuse or model filter/sort, `toggleFavorite(cachedSampleIndex)`
   can hit the wrong row. Sample Brain requires Python to own sample identity;
   QML may only hand off an index at the moment of intent, or better a stable
   id already resolved by the model/adapter.

2. **Incomplete `ListView.onPooled` hygiene.**
   The pooled handler is empty aside from a comment. Generic review treated
   “handler present” as fine and did not require clearing cached identity /
   deferred command state.

3. **Misclassification.**
   The delayed favorite path was classified as “debounce UX”, not
   `DELEGATE_IDENTITY_AS_AUTHORITY` / authority-boundary risk.

## False positives from the generic pass

None material. The miss was under-detection, not over-flagging.

## Rationalization observed

“Using `index` in ListView delegates is idiomatic Qt Quick, so caching it for a
short Timer is fine.” That rationalization is exactly what the specialist skill
must interrupt for Sample Brain.

## Verdict of RED pass

`GENERIC_REVIEW_INCOMPLETE` — meaningful QML/authority defect not held.

## Same inputs required for GREEN

GREEN must re-review the **same** fixture path without renaming the defect in
the prompt, and must emit a finding for the cached-index / delayed-command path.
