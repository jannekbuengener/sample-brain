# Prepared Fit Variants — Product Spec

**Runtime issue:** [#466](https://github.com/jannekbuengener/sample-brain/issues/466)  
**Origin spec:** [#92](https://github.com/jannekbuengener/sample-brain/issues/92)  
**Consumes:** Musical Fit hints from #465 or explicit transform parameters  
**Status:** Prepared Fit Variant v1 Core contract

Prepared Fit Variants turn an existing local audio source plus explicit musical transform parameters into a deterministic, cacheable WAV variant. V1 is deliberately **VST-/Workspace-/DB-independent** and runs before playback, never in an audio thread.

---

## 1. Purpose

Matching decides what fits. Prepared Fit Variants render how a selected sample should be adapted for a target context.

```text
source audio + explicit transform params
                  ↓
        Prepared Fit Variant v1
                  ↓
      local regenerable cache
                  ↓
      later preview / workspace
```

The runtime lives in `src/fit_variants.py` and reuses the repository's existing `librosa`, `soundfile`, SHA-256 content identity, and cache patterns. No new DSP dependency is introduced.

---

## 2. Canonical v1 contract

Portable manifest:

```text
document_type: sample_brain.fit_variant
schema_version: 1.0.0

variant_id
status
source_hash
transform
backend
audio_properties
output
provenance
```

Runtime result statuses:

| Status | Meaning |
|---|---|
| `ready` | Variant was rendered successfully. |
| `cached` | Existing variant passed identity + output-hash validation and was reused. |
| `no_result` | Required musical evidence is unavailable; no render is attempted. |
| `failed` | Invalid input, unreadable audio, invalid cache location, or render failure. |

`output_path` may exist on the in-process result for immediate use, but absolute cache paths are never serialized into the portable manifest.

---

## 3. Transform parameters

V1 accepts:

```text
source_bpm: positive finite BPM or null
target_bpm: positive finite BPM or null
tempo_multiplier: positive finite number, default 1.0
semitone_shift: integer -12..+12
```

`tempo_multiplier` consumes the machine-readable half/double-time evidence already emitted by Matching (#465).

The effective source tempo is:

```text
effective_source_bpm = source_bpm * tempo_multiplier
```

When target tempo is present:

```text
render_rate = target_bpm / effective_source_bpm
```

This distinction matters for half/double-time matches. Example: a 64 BPM source with Matching `tempo_multiplier=2.0` already represents an effective 128 BPM interpretation, so targeting 128 BPM produces `render_rate=1.0`, not an accidental 2× speed-up.

When no target BPM is requested, tempo rendering is bypassed with `render_rate=1.0`. A pitch-only variant therefore does not require BPM evidence.

---

## 4. DSP scope and order

V1 deliberately implements one narrow prepared path:

1. tempo adaptation via existing `librosa.effects.time_stretch`
2. semitone pitch shift via existing `librosa.effects.pitch_shift`
3. deterministic Float32 WAV output via `soundfile`

DSP order is recorded in provenance as:

```text
[tempo_adaptation, pitch_shift]
```

The source file is never mutated.

Advanced formant-safe, percussive, tonal/poly, dirty/texture, repitch-specific, beat-locked, bar-locked, and host-synchronised modes remain follow-up scope after evidence.

---

## 5. Deterministic variant identity

`variant_id` is SHA-256 over canonical sorted JSON containing:

- Prepared Fit Variant contract version
- SHA-256 source-content identity
- normalized transform parameters
- concrete DSP backend identity/version

No timestamp, absolute path, DB identifier, UI state, or runtime cache directory participates in identity.

Equivalent source content + equivalent transform parameters + equivalent backend produce the same variant ID. A source-content change, parameter change, backend-version change, or contract-version change produces a different identity.

---

## 6. Local cache and idempotent reuse

Default cache resolution follows the existing local/regenerable pattern:

```text
CLI/API override
→ SAMPLE_BRAIN_FIT_VARIANT_CACHE_DIR
→ platform user-local cache/sample-brain/fit-variants
```

Each variant owns one directory named by `variant_id`:

```text
<variant_id>/
  prepared.wav
  manifest.json
```

A cache hit is accepted only when all of the following match:

- document type and schema version
- variant ID
- source hash
- normalized transform parameters
- backend identity/version
- output file exists
- actual output SHA-256 equals manifest output hash

Missing, malformed, or stale cache evidence causes a safe re-render rather than silent reuse.

A cache path inside any Git worktree fails closed with `CACHE_INSIDE_GIT_REPO`; generated audio/cache manifests must remain outside the repository.

---

## 7. Matching → Transform boundary

`variant_params_from_match(...)` translates the already-shipped #465 `MatchResult` machine-readable fields:

```text
match.bpm             → source_bpm
explicit target BPM   → target_bpm
match.tempo_multiplier → tempo_multiplier
match.semitone_hint    → semitone_shift
```

`prepare_fit_variant_from_match(...)` proves that boundary end-to-end without moving Matching logic into Transform.

Transform does not rescore BPM, Key, Type, Groove, or total fit.

---

## 8. Fail-closed behavior

Stable v1 reason/error codes include:

- `SOURCE_NOT_FOUND`
- `INVALID_SOURCE_BPM`
- `INVALID_TARGET_BPM`
- `SOURCE_BPM_UNAVAILABLE`
- `INVALID_TEMPO_MULTIPLIER`
- `INVALID_SEMITONE_SHIFT`
- `CACHE_INSIDE_GIT_REPO`
- `AUDIO_READ_FAILED`
- `RENDER_FAILED`

A target BPM without known source BPM returns `no_result` instead of inventing tempo evidence. Invalid finite/range constraints fail before rendering.

---

## 9. Privacy and artifact boundary

Portable manifest evidence contains content hashes, transform parameters, backend identity, relative output reference, audio properties, and provenance only.

It does not contain:

- absolute source paths
- absolute cache paths
- private sample content
- DB paths or catalog rows
- model caches or weights
- VST/DAW/host state

Tests generate synthetic audio in temporary directories. No private audio fixture is required or committed.

---

## 10. Audio-thread and product boundary

Prepared Fit Variants are an offline/prepared Core operation. Heavy time-stretch/pitch-shift work is explicitly outside an audio thread.

V1 does **not** implement:

- VST3/plugin shell
- host transport sync
- Workspace/browser UI
- preview scheduling
- drag/drop
- DB schema or persistence requirement
- background job framework
- network/cloud render
- Matching algorithm changes
- complete pitch/sync mode catalog

Those consumers may use the prepared file and portable manifest later without reimplementing identity/cache/DSP semantics.

---

## 11. Validation contract

Focused synthetic-audio tests cover:

- deterministic identity and cache hit
- source/parameter changes changing identity
- target-BPM frame-length behavior
- correct half/double-time effective source BPM semantics
- zero-shift/no-tempo sample preservation
- semitone pitch evidence
- channel/sample-rate preservation
- invalid BPM/semitone paths
- target BPM without source BPM → `no_result`
- pitch-only path without BPM
- missing source failure
- no absolute paths in manifest
- cache-inside-Git rejection
- stale output-hash re-render
- original source bytes unchanged
- #465 `MatchResult` → prepared variant integration

Broader repository CI remains authoritative for integration safety.

---

## 12. References

- `src/fit_variants.py` — Prepared Fit Variant v1 runtime
- `src/matching.py` — #465 machine-readable BPM relation, tempo multiplier and semitone hint
- `src/content_hash.py` — SHA-256 content identity
- `src/track_analysis_cache.py` — existing local/regenerable cache precedent
- `src/asset_renderer.py` — existing deterministic render/provenance precedent
- [#466](https://github.com/jannekbuengener/sample-brain/issues/466) — runtime slice
- [#92](https://github.com/jannekbuengener/sample-brain/issues/92) — original product specification
