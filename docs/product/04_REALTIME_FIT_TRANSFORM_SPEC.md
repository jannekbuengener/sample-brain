# Realtime Fit & Transform Engine — Product Spec

**Issue:** [#92](https://github.com/jannekbuengener/sample-brain/issues/92)  
**Parent:** [#90](https://github.com/jannekbuengener/sample-brain/issues/90)  
**Depends on:** [`01_LIBRARY_INTELLIGENCE_SPEC.md`](01_LIBRARY_INTELLIGENCE_SPEC.md) (#94), [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) (#91)  
**Status:** Spec (docs-only); no transform runtime on `main`

This document defines how Sample Brain turns catalog samples into **synchronised, playable variants** — not raw file paths alone. Matching decides *what* fits; Transform produces *how* it sounds in context.

---

## 1. Purpose

A kick at 140 BPM in the library is not the same as a kick locked to the producer's 128 BPM track in C minor. The Transform pillar generates **variant-based recommendations**: pre-rendered or on-demand audio adapted to target BPM, key, and sync mode, ready for preview and drag-drop.

---

## 2. Core principle: variant-based recommendation

| Concept | Definition |
|---------|------------|
| **File-based** | Recommendation = original file path only |
| **Variant-based** | Recommendation = `(sample_id, transform_params)` → playable audio buffer or cache file |

Every sample may have **multiple variants** for the same session context (e.g. +2 semitones bar-locked, original BPM free preview).

---

## 3. Variant parameters

### 3.1 Target fields

| Field | Range / values | Notes |
|-------|----------------|-------|
| `target_bpm` | From track profile or user | Sync tempo to context |
| `semitone_shift` | **−12 to +12** | Product standard per #92 |
| `pitch_mode` | See §4 | DSP algorithm selection |
| `sync_mode` | See §4 | Grid/playback behaviour |
| `source_sample_id` | Catalog reference | Immutable link to Library metadata |

### 3.2 Preview / render / cache status

| Status | UI behaviour |
|--------|--------------|
| `pending` | Placeholder; queue background render |
| `rendering` | Progress indicator |
| `ready` | Playback allowed |
| `failed` | Show error; offer retry or fallback to dry file |
| `cached` | Fast replay from local cache (outside repo) |

Variants are **cacheable** under user-controlled paths per `docs/DATA_AND_ARTIFACT_POLICY.md` — never committed to git.

---

## 4. Pitch modes and sync modes (target)

### 4.1 Pitch modes

| Mode | Use case |
|------|----------|
| **Repitch** | Speed and pitch change together (classic DJ repitch) |
| **Time-Stretch** | Change tempo without pitch shift |
| **Pitch-Shift** | Change pitch without tempo change |
| **Formant-Safe** | Vocal/tonal material; preserve formants where possible |
| **Percussive** | Drums/transients; minimise phasing artifacts |
| **Tonal/Poly** | Harmonic loops and pads |
| **Texture/Dirty** | Creative degradation acceptable |

Technical library choice (rubberband, élastique, internal STFT, etc.) is **follow-up evaluation** — not decided in this spec.

### 4.2 Sync modes

| Mode | Behaviour |
|------|-----------|
| **Free Preview** | Original timing; no grid lock |
| **Bar-Locked** | Aligned to bar grid at target BPM |
| **Beat-Locked** | Aligned to beat grid |
| **One-Shot** | Single trigger; no loop sync |

---

## 5. Audio-thread safety

| Allowed in audio thread | Forbidden in audio thread |
|-------------------------|---------------------------|
| Playback of **prepared** variant buffers | Library scan |
| Read from render cache (mmap/file already open) | SQLite / DB queries |
| Simple gain/mute/fade on prepared data | ML inference |
| — | Heavy DSP render (pitch/time stretch) |
| — | Network or cloud calls |

**Rule:** Render and analyse **off the audio thread**; the plugin plays only finished or streaming-ready segments.

---

## 6. Shipped vs target

| Capability | Shipped on `main` | Target (product) |
|------------|-------------------|------------------|
| Variant model / cache schema | ❌ | ✅ |
| Background render worker | ❌ | ✅ async job queue |
| CLI variant preview | ❌ | Optional later (`variant render`) |
| Pitch/time DSP integration | ❌ | ✅ evaluated library |
| Plugin variant browser | ❌ | ✅ Workspace (#93) |
| Match → variant suggestion pipeline | ❌ | Matching hints + Transform params |

EPIC 6 “re-imagine” research in backlog overlaps conceptually; this pillar is the **product-facing** variant contract for VST-first delivery.

---

## 7. Boundaries vs other pillars

| Transform | Not Transform |
|-----------|---------------|
| Render playable variants from match results | Score BPM/key fit (#91) |
| Manage cache lifecycle and status | Extract sample features (#94) |
| Expose variant params to Workspace | Build track profile (#95) |
| Apply DSP off audio thread | Host arrangement / mixer (#93 non-goals) |

**Division of labour:**

```text
Matching  →  fit score + hints (semitone, half/double BPM)
Transform →  variant audio + cache state
Workspace →  preview UI, variant picker, drag-drop
```

---

## 8. Follow-up runtime slices

| Slice | Scope |
|-------|-------|
| DSP library spike | Evaluate 1–2 local libraries for stretch/pitch |
| Variant schema + cache API | In-memory + disk cache contract |
| `variant render` CLI (narrow) | Single sample + params → WAV in temp dir |
| Plugin integration | Workspace variant browser wired to cache |
| Advanced pitch/sync modes | After MVP repitch + time-stretch |

---

## 9. Acceptance mapping (Issue #92)

| Acceptance criterion | This spec |
|----------------------|-----------|
| Variant-based recommendation as product standard | §2 |
| −12/+12 semitone window documented | §3.1 |
| Pitch/sync modes captured as target | §4 |
| Technical library evaluation remains follow-up | §4.1, §8 |

**Implementation remains follow-up scope.**

---

## 10. References

- [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) — semitone/BPM hints
- [`05_VST_PRODUCING_WORKSPACE_SPEC.md`](05_VST_PRODUCING_WORKSPACE_SPEC.md) — variant browser UI
- `docs/PRODUCT_REQUIREMENTS.md` §5.2 — simple variant preview in product MVP
- `docs/TARGET_ARCHITECTURE.md` §10.5 — EPIC 6 re-imagine (related, narrower CLI research)
