# Producer Group Manifest v1 — Canonical Contract

**Issue:** [#268](https://github.com/jannekbuengener/sample-brain/issues/268)
**Parent:** [#230](https://github.com/jannekbuengener/sample-brain/issues/230) — Asset / Stem candidate sources
**Depends on:** [#244](https://github.com/jannekbuengener/sample-brain/issues/244) (Technical Stem Manifest), [#246](https://github.com/jannekbuengener/sample-brain/issues/246) (stem separation run)
**Status on issue tracker:** `OPEN` / contract + deterministic logic merged on a feature branch; **private pilot NOT yet run** (see §10)
**Schema version:** `1.0.0`
**Document type:** `sample_brain.producer_group`
**Implementation:** `src/producer_groups.py`

This document defines the canonical, portable **Producer Group Manifest v1** contract for Sample Brain. It describes how the technical stems from #244/#249 (`drums`, `bass`, `vocals`, `other`) are turned into musically usable **producer groups** (`kick_bass`, `drums`, `melodic`, `vocal`, `atmos_fx`) for loop and section candidates.

---

## 1. Purpose

Technical stems are raw separation outputs. They are the raw materials for downstream producer-oriented assets. Producer groups are a *musical re-grouping* of those technical stems, defined so that #255 (stem-based asset candidate generation) can consume them as additional loop/section sources that share the master timebase.

This contract is **derivation only**. It does **not** invent a new stem-separation model and it does **not** promise a perfect reconstruction of original mixer tracks.

---

## 2. Design Principles

| Principle | Rule |
|-----------|------|
| **No new separation** | The contract only applies documented, deterministic DSP helpers to existing technical stems. No trained separation model is added. |
| **Standard technical kinds** | Input vocabulary is strictly `"drums"`, `"bass"`, `"vocals"`, `"other"` (from #244). |
| **Timebase traceability** | Every group stays on the shared #234 sample timebase (`AudioTimebase`): same `sample_rate_hz` and `n_samples` as the master/stems. |
| **Status transparency** | Every group reports `ok`, `partial`, or `no_result`. Missing/unusable inputs are never fabricated. |
| **`no_result` is valid** | When a group cannot be derived, it is reported honestly with a `reason_code`. |
| **No naive bassline** | Low-frequency content alone is NEVER promoted to a bassline. |

---

## 3. Producer Group Vocabulary & Derivation Rules

| Group | Technical stems used | Components | Mask / selection rule | Summation | Status |
|-------|----------------------|------------|-----------------------|-----------|--------|
| `kick_bass` | `drums`, `bass` | kick attack/body (from `drums`), musical bassline (from `bass`) | kick = onset-gated envelope on the `drums` low band; bassline = `bass` stem (identity) | `kick_component + bass_stem` | `ok` (or `no_result` if no usable `bass`) |
| `drums` | `drums` | non-kick percussion | `1 - kick_gate` applied to `drums` | `drums * (1 - kick_gate)` | `ok` (or `no_result`) |
| `vocal` | `vocals` | vocal | identity | `vocals` | `ok` (or `no_result`) |
| `melodic` | `other` | melodic harmonic proxy | `hpss` harmonic component of `other` | `hpss_harmonic(other)` | `partial` (best-effort proxy; or `no_result`) |
| `atmos_fx` | `other` | atmos/fx percussive proxy | `hpss` percussive component of `other` | `hpss_percussive(other)` | `partial` (best-effort proxy; or `no_result`) |

---

## 4. Hard Rule — `kick_bass` is NOT `drums + bass`

> `kick_bass = (kick attack/body extracted from the drums stem) + (the actual musical bassline from the bass stem)`
>
> `kick_bass != drums + bass`

The kick is isolated by an **onset-gated envelope** over the low band of the `drums` stem: the kick attack/body is kept, the rest of the drums is suppressed. The bassline is the **separated `bass` stem** (a musical source-separation output), **not** a low-pass of the drums' low end.

Consequence: if no usable `bass` stem exists (absent or below the audible RMS threshold), `kick_bass` is reported as `no_result`. The kick envelope may be inspected internally, but it is **never emitted as a finished `kick_bass` group**. A low-frequency rumble in the drums stem does **not** become a bassline.

---

## 5. Low Frequency Is Not Automatically a Bassline

The contract explicitly forbids treating low-frequency content as a bassline. Only the separated `bass` stem counts as the musical bassline. Any residual low end in `drums`/`other` is never promoted to `kick_bass` or `bass`.

---

## 6. Top-Level Manifest Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `document_type` | string | yes | Must be `"sample_brain.producer_group"`. |
| `schema_version` | string | yes | `"1.0.0"`. |
| `group_kind` | string | yes | One of `kick_bass`, `drums`, `melodic`, `vocal`, `atmos_fx`. |
| `group_id` | string | yes | Deterministic portable id (e.g. `pg_<track_ref>_<kind>`). No UUID/timestamp. |
| `group_ref` | string | yes | Portable ref (e.g. `producergroup_<kind>`). |
| `status` | string | yes | `ok`, `partial`, or `no_result`. |
| `timebase` | object | yes | `{ sample_rate_hz, n_samples }` — must match the master/stems. |
| `technical_stems` | array | yes | Technical stem kinds actually used (subset of `drums/bass/vocals/other`). |
| `components` | array | yes (ok/partial) | Per-component `{ stem_kind, role, mask }`. Absent for `no_result`. |
| `masks` | string | yes | Human-readable selection/mask rule. |
| `summation` | string | yes (ok/partial) | How components are combined. Empty for `no_result`. |
| `processing` | array | yes | Ordered processing steps applied. |
| `track_ref` | string | no | Portable track id (content hash) when known. |
| `reason_code` | string | yes (no_result) | Stable code: `MISSING_SOURCE_STEM`, `MISSING_BASSLINE`, `SILENT_INPUT_SKIPPED`. |

---

## 7. Status Model

* `ok` — group derived and musically usable (e.g. `vocal`, `drums`, `kick_bass` with a usable bass stem).
* `partial` — derived via a best-effort proxy that is explicitly **not** a guaranteed split (e.g. `melodic`/`atmos_fx` from `other` via HPSS). Documented as a proxy.
* `no_result` — cannot be derived (missing/unusable source). Reported honestly with `reason_code`. Never fabricated.

---

## 8. Determinism & Helper Logic

All steps are deterministic (no randomness):

* **Kick envelope** (`extract_kick_envelope`): Butterworth low-pass on `drums`, moving-average envelope, adaptive onset detection via local-median threshold, exponential gain decay after each onset. Suppresses non-kick drums.
* **`melodic` / `atmos_fx` proxy**: standard `librosa.effects.hpss` harmonic/percussive split of `other`. Documented as a best-effort proxy, not a lead/synth/atmos separation.

---

## 9. Plug-in to #250 / #255

Each group exposes `producer_group_id`, `producer_group_ref`, `group_kind`, and `technical_stems`. These map directly into the existing `producer_group` `source_kind` used by `loop_candidates.LoopSourceIdentity` and `asset_renderer.RenderRequest` (`source_identity`). #255 consumes groups **only when status is `ok` or a clearly documented `partial`**, and keeps the master path independent when no stems/groups are available.

---

## 10. Pilot Evidence (this session)

> **PARTIAL_IMPLEMENTATION / PILOT_PENDING.**

The deterministic contract, helper logic, validation, and tests (`tests/test_producer_groups.py`) are implemented and green. The **private listen-test pilot** required by #268 (a `GO | NO-GO | FOLLOW-UP` verdict per group on real private stems) was **NOT executed in this session** because the private pilot audio is not reachable here (bootloader forbids reading sample audio).

Until that pilot runs, each group's real-world acceptance remains open. The contract itself is complete and testable with synthetic fixtures. No `GO` is claimed for the private pilot.

---

## 11. Acceptance Mapping (Issue #268)

| #268 criterion | This document / code |
|----------------|----------------------|
| `kick_bass` = kick + musical bassline, not `drums + bass` | §4; `tests/test_producer_groups.py::test_kick_bass_not_equal_drums_plus_bass` |
| Low-freq content not auto-bassline | §5; `test_low_freq_rumble_not_bassline` |
| Components/processing traceable per group | §6; `test_components_processing_traceable` |
| `no_result` is valid | §7; `test_no_result_when_source_missing`, `validate_producer_group_manifest` |
| Pilot ends with GO/NO-GO/FOLLOW-UP per group | §10 — pending private pilot |

---

## 12. References

* Technical Stem Manifest v1 — `docs/STEM_MANIFEST_V1.md`, `src/stem_cache.py`
* Canonical Working Audio & Timebase — `docs/CANON_AUDIO_TIMEBASE.md`, `src/canon_audio.py`
* Asset Manifest v1 — `docs/ASSET_MANIFEST_V1.md` (#250)
* Stem-based asset candidate generation — issue #255
