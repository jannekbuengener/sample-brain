# VST-first Producing Workspace — Product Spec

**Issue:** [#93](https://github.com/jannekbuengener/sample-brain/issues/93)  
**Parent:** [#90](https://github.com/jannekbuengener/sample-brain/issues/90)  
**Depends on:** All prior pillar specs (#94–#92, #95)  
**Status:** Spec (docs-only); no VST3 plugin on `main`

This document defines the **first product body**: a VST3 browser/assistant plugin (standalone app later) that surfaces library intelligence, matching, context, and variants in the DAW workflow.

---

## 1. Purpose

Sample Brain's primary interface is not the CLI or FL Browser tag export — it is an **in-DAW producing assistant** where producers browse, preview, filter, and drag samples without leaving the host. The Workspace pillar integrates the SQLite-backed core into a focused UI while respecting realtime safety rules.

---

## 2. Product bodies

| Body | Priority | Notes |
|------|----------|-------|
| **VST3 browser/assistant plugin** | First | Primary product incarnation |
| **CLAP plugin** | Optional later | Same core; format adapter |
| **Standalone producing app** | Later | Same core; adds session/playlist-style UX without DAW |

All bodies share:

- Local SQLite catalog (Library)
- Matching and search services
- Transform variant cache
- Track context profile (session-scoped)

No cloud account or sync required for core flows.

---

## 3. UI / workflow target

### 3.1 Sample browser

| Feature | Description |
|---------|-------------|
| Grid / list view | Browse catalog with sort and pagination |
| Waveform + playhead | Visual preview of selected sample or variant |
| Filter | BPM, key, type, tags, duration |
| Text / semantic search | CLI `search` capabilities exposed in UI |
| Similar samples | Vector + metadata hybrid (EPIC 2 + Matching) |

### 3.2 Session workflow

| Feature | Description |
|---------|-------------|
| **Collections / favorites** | User-curated sets (local DB or profile) |
| **Project basket** | Samples staged for current session |
| **Track context panel** | Shows/edits track profile (#95) |
| **Variant browser** | Lists BPM-locked / key-shifted variants (#92) |
| **Drag & drop** | Audio or MIDI into host DAW |

### 3.3 Integration points

```text
┌─────────────────────────────────────────┐
│           VST3 Workspace UI              │
│  Browse │ Preview │ Context │ Variants  │
└─────────┬───────────┬─────────┬─────────┘
          │           │         │
    Library #94   Context #95  Transform #92
          │           │         │
          └──── Matching #91 ──┘
                    │
              SQLite catalog (local)
```

---

## 4. Host boundaries

| Rule | Detail |
|------|--------|
| **VST3 first** | Primary plugin standard |
| **FL Studio** | First target host for smoke and UX validation |
| **Not FL-only** | Any VST3-capable DAW is a valid host |
| **No FL Browser dependency** | `export_fl` CLI remains legacy/fallback |
| **No FL reverse engineering** | No FLP parsing; public host APIs only |

CLAP support is optional and does not block VST3 MVP.

---

## 5. Shipped vs target

| Capability | Shipped on `main` | Target (product) |
|------------|-------------------|------------------|
| CLI pipeline (scan/analyze/search/match) | ✅ data foundation | Shared backend |
| VST3 plugin binary | ❌ | ✅ MVP |
| Plugin UI (browser/preview) | ❌ | ✅ |
| Drag & drop to host | ❌ | ✅ |
| Collections / project basket | ❌ | ✅ |
| Variant browser | ❌ | ✅ |
| Standalone app | ❌ | Post-MVP |
| FastAPI local service (EPIC 4) | ❌ | Optional; not required for VST3 MVP |

---

## 6. Non-goals (Workspace pillar)

| Non-goal | Rationale |
|----------|-----------|
| DAW replacement | No full mixer, arrangement timeline, or mastering |
| Sample editor | No destructive waveform editing suite |
| Cloud marketplace / sync | Local-first product |
| Generative composition | Library intelligence only |
| Heavy work in audio thread | See Transform §5, Context §5 |

---

## 7. Realtime / threading model (summary)

- **UI thread:** browsing, selection, profile edit, job dispatch
- **Background workers:** search, variant render, context analyze
- **Audio thread:** play prepared buffers only (pre-rendered variants or original file segments)

Aligns with PRD §5.3 and parent #90 governance.

---

## 8. Follow-up runtime slices

| Slice | Scope |
|-------|-------|
| VST3 shell / JUCE spike | Empty plugin + host smoke |
| Catalog read API (in-process) | Plugin reads SQLite read-only |
| Browser UI v0 | List + preview wired to catalog |
| Drag-drop proof | One host (FL) validated |
| Context + match panel | Wire track profile to filters |
| Standalone app research | Post-VST3; reuse core DLL/module |

---

## 9. Acceptance mapping (Issue #93)

| Acceptance criterion | This spec |
|----------------------|-----------|
| Workspace pillar clearly defined | §1–3 |
| Plugin and standalone share core | §2 |
| FL first host, not hard dependency | §4 |
| Technical implementation follow-up | §5, §8 |

**Implementation remains follow-up scope.**

---

## 10. References

- [`03_TRACK_CONTEXT_ANALYSIS_SPEC.md`](03_TRACK_CONTEXT_ANALYSIS_SPEC.md)
- [`04_REALTIME_FIT_TRANSFORM_SPEC.md`](04_REALTIME_FIT_TRANSFORM_SPEC.md)
- `docs/PRODUCT_REQUIREMENTS.md` §5.2 — product MVP table
- `docs/TARGET_ARCHITECTURE.md` §10.2 — VST-first workspace target
- `docs/DAW_INTEGRATION_SPEC.md` — VST3 product tiers vs FL export fallback
