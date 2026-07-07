# Track Context Analysis — Product Spec

**Issue:** [#95](https://github.com/jannekbuengener/sample-brain/issues/95)  
**Parent:** [#90](https://github.com/jannekbuengener/sample-brain/issues/90)  
**Depends on:** [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md) (#94)  
**Status:** Spec (docs-only); no dedicated runtime on `main`

This document defines how Sample Brain derives a **track profile** from the current song context — a marked audio file, stem, or loop — and uses it as input for search, matching, and recommendations. It does not scan libraries, score fit, or render variants.

---

## 1. Purpose

Producers work from an **active musical context**: the loop they are building on, a stem from the arrangement, or a reference clip. Track Context Analysis turns that audio into a structured **track profile** so Matching and Workspace can suggest compatible samples and layers without manual re-entry of BPM, key, and role.

---

## 2. Inputs

| Input | MVP (target) | Later |
|-------|--------------|-------|
| Marked audio file (user-selected path) | ✅ primary | — |
| Loop or one-shot from library | ✅ | — |
| Stem / bounce from project folder | ✅ | — |
| Host DAW context (transport BPM/key, playhead region) | ❌ | Host integration via VST3 |
| MIDI or project file parsing | ❌ | Out of scope |

Context sources must work **offline** and **local-first** — no cloud upload.

---

## 3. Outputs

### 3.1 Track profile (primary)

Structured object consumed by Matching (#91) and Workspace (#93):

| Field | Description | Source (target) |
|-------|-------------|-----------------|
| `bpm` | Tempo of context audio | Reuse Library analyze pipeline on context file |
| `key` | Tonal centre | Reuse Library key extraction + confidence |
| `energy` | Envelope / loudness dynamics (verse vs drop proxy) | RMS contour, segment stats |
| `spectrum` | Spectral character summary | Brightness, band energy ratios |
| `groove` | Rhythmic feel descriptor | Onset density, swing proxy (TBD in implementation) |
| `arrangement_role` | Intro, verse, chorus, drop, bridge, fill, etc. | Heuristic / rules (MVP: optional or coarse) |
| `desired_layers` | User-stated or inferred layers to find | UI selection + missing-layer hypotheses |

### 3.2 Missing-layer hypotheses

Ranked suggestions for what the track might still need, e.g.:

- Toploop, atmos, fill, transition, bass, vocal, percussion layer, impact

Hypotheses are **assistive**, not authoritative — the producer confirms or overrides in Workspace.

---

## 4. Shipped vs target

| Capability | Shipped on `main` | Target (product) |
|------------|-------------------|------------------|
| Analyze arbitrary audio file (BPM, key, features) | ✅ via `analyze` on catalog | ✅ reuse for context file |
| Dedicated track-profile model / storage | ❌ | ✅ session or project-scoped profile |
| Context from marked file in plugin UI | ❌ | ✅ VST3 Workspace |
| Host transport BPM/key injection | ❌ | Later host API |
| Missing-layer hypothesis engine | ❌ | ✅ rule/heuristic MVP |
| Arrangement-role detection | ❌ | ✅ coarse MVP |

CLI today can analyze samples already in the catalog; **ad-hoc context file analysis** without prior scan is a follow-up runtime slice.

---

## 5. VST / realtime boundaries

| Rule | Rationale |
|------|-----------|
| No heavy analysis in the audio thread | Product principle (#90, PRD §5.3) |
| Context analysis runs **asynchronously** or **before** preview/session use | Background worker or pre-session step |
| Plugin UI shows profile fields and lets user edit/confirm | Human override required for low-confidence fields |
| Prepared profile only passed to Matching/Transform schedulers | Decouple analysis from playback |

The audio thread may read **cached profile values** and play prepared previews — never run librosa, DB queries, or ML inference inline.

---

## 6. Boundaries vs other pillars

| Track Context | Not Track Context |
|---------------|-------------------|
| Derive BPM/key/energy/groove from context audio | Library-wide scan/index (#94) |
| Build track profile for session | Compute fit scores (#91) |
| Suggest missing layers (hypotheses) | Render pitch/time variants (#92) |
| Feed search/ranking inputs | Browser UI, drag-drop (#93) |

**Data flow (target):**

```text
Context audio  →  Track profile  →  Matching / Search / Workspace
                         ↑
              Library analyze primitives (reuse, not duplicate)
```

---

## 7. MVP context sources (realistic)

1. **User picks a file** — loop, stem, or reference WAV/FLAC from disk (outside or inside library roots).
2. **User picks a catalog sample** — `sample_id` from SQLite; features already in `features` table.
3. **Manual overrides** — user sets BPM/key/role when analysis confidence is low.

Host-driven context (FL transport, selected playlist clip) is **post-MVP** and documented as extension point only.

---

## 8. Follow-up runtime slices

| Slice | Scope |
|-------|-------|
| `context analyze <path>` CLI | One-shot profile JSON for a file not in catalog |
| Session profile store | Ephemeral or project-persisted profile (not committed to repo) |
| Missing-layer rules v1 | Keyword + feature heuristics |
| Plugin context picker | Workspace integrates profile into filter/match defaults |
| Host API spike | FL Studio / VST3 host parameter read (research) |

---

## 9. Acceptance mapping (Issue #95)

| Acceptance criterion | This spec |
|----------------------|-----------|
| Track context as own product pillar | §1, §6 |
| MVP context sources realistically described | §2, §7 |
| Host/realtime boundaries documented | §5 |
| Recommendation engine can derive follow-ups | §3, §8 |

**Implementation remains follow-up scope.**

---

## 10. References

- [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md) — feature extraction reuse
- [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) — consumes profile as `MatchProfile` input
- `src/analyze.py` — current analysis primitives
- `docs/PRODUCT_REQUIREMENTS.md` §5.2 — track context marked “later” for product MVP
