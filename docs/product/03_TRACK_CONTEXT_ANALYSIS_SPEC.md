# Track Context Analysis — Product Spec

**Runtime issue:** [#467](https://github.com/jannekbuengener/sample-brain/issues/467)  
**Origin spec:** [#95](https://github.com/jannekbuengener/sample-brain/issues/95)  
**Consumes:** existing Track Map / `context_analyze` evidence  
**Feeds:** Matching (#465) and Prepared Fit Variants (#466)  
**Status:** Track Context Profile v1 runtime contract

Track Context Profile v1 is the VST-independent composition layer between existing Track Map evidence and downstream musical matching. It does **not** create a second analyzer, score candidates, render fit variants, or require a catalog DB.

---

## 1. Purpose

A producer-selected audio source already has a portable Track Map contract from `src/context_analyze.py`. Track Context Profile v1 projects that evidence into a smaller machine-readable context object for matching and later producing workflows.

Core flow:

```text
selected audio
    ↓
existing cached Context Analyzer
    ↓
Track Map
    ↓
Track Context Profile v1
    ↓
Matching / later Prepared Fit Variants
```

The profile must remain deterministic, explainable, DB-free, host-independent, and safe to serialize without private absolute paths.

---

## 2. Canonical v1 contract

```text
document_type: sample_brain.track_context_profile
schema_version: 1.0.0

source
status

bpm
key
energy
spectrum
groove
arrangement
desired_layers

provenance
```

Each evidence-bearing component exposes:

```text
status
value and/or evidence
source_ref
reason_code when partial/unavailable
```

Allowed status semantics are compatible with existing Track Map evidence: `ok`, `partial`, `no_result`, `not_run`, and `failed` where appropriate.

---

## 3. Evidence mapping

### 3.1 BPM

Reuse `analysis.musical.bpm` from Track Map without re-analysis.

Canonical profile reference:

```text
track_map:/analysis/musical/bpm
```

### 3.2 Key

Reuse `analysis.musical.key` exactly enough to preserve root, mode, confidence/evidence, and partial mode state. A `MODE_UNRESOLVED` source remains partial; the profile must not invent a mode.

### 3.3 Energy

V1 reuses current loudness evidence from `analysis.audio_summary.loudness`.

Current Context Analyzer provides global RMS/loudness, not a complete arrangement-energy contour. Therefore an otherwise valid global loudness mapping is deliberately:

```text
status = partial
reason_code = GLOBAL_LOUDNESS_ONLY
```

Timeline/section energy can extend the profile later only when explicit existing evidence is supplied; this issue does not add a new energy analyzer.

### 3.4 Spectrum

Reuse `analysis.audio_summary.brightness` / mean spectral centroid. No new broad spectral pipeline is introduced for v1.

### 3.5 Groove

Groove is populated only from explicitly supplied deterministic beat/onset/grid evidence. Without it:

```text
status = no_result
reason_code = GROOVE_EVIDENCE_UNAVAILABLE
```

No groove score or new DB columns are created here.

### 3.6 Arrangement

Arrangement/section information is consumed only when existing evidence is explicitly supplied. Otherwise:

```text
status = no_result
reason_code = ARRANGEMENT_EVIDENCE_UNAVAILABLE
```

No new deconstruction run is forced by the profile composer.

### 3.7 Desired layers

V1 does not create missing-layer hypotheses heuristically. It may carry explicit deterministic evidence supplied by another component; otherwise:

```text
status = no_result
reason_code = DESIRED_LAYER_EVIDENCE_UNAVAILABLE
```

A future Missing-Layer engine requires its own evidence-backed scope.

---

## 4. Portable source identity and privacy

The profile projects only portable source identity fields from Track Map, such as:

- file name
- size
- content hash
- audio properties
- portable source reference

Absolute local paths are never copied into the profile. Optional evidence containing absolute Windows, UNC, or POSIX filesystem paths fails closed with `NON_PORTABLE_EVIDENCE`.

Canonical JSON-pointer-style evidence references such as `/analysis/timeline/beats` remain valid provenance references and are not treated as filesystem paths.

No private sample audio, DB, index, cache, or model artifact belongs in the repository.

---

## 5. Runtime API

The narrow runtime lives in `src/track_context.py`.

Primary functions:

```python
build_track_context_profile(track_map, optional_evidence=None)
analyze_track_context(path, optional_evidence=None, ...)
```

`build_track_context_profile(...)` is a pure composition step over existing evidence.

`analyze_track_context(...)` delegates to `analyze_context_file_cached(...)`, then builds the profile. It does not initialize or mutate the catalog DB and does not introduce a second audio-analysis stack.

Cache hit/miss/disabled evidence may be carried in profile provenance.

---

## 6. Profile status

The top-level profile status is derived from the four core evidence groups:

```text
bpm
key
energy
spectrum
```

Optional Groove/Arrangement/Desired-Layers `no_result` states do not make an otherwise usable core profile fail.

Because global loudness is intentionally only partial Energy evidence, a normal v1 profile can correctly have top-level `partial` status even when BPM, Key, Loudness, and Brightness were successfully analyzed.

---

## 7. Boundaries

Track Context Profile v1 does:

- reuse Track Map/context analysis
- expose machine-readable BPM/Key/Energy/Spectrum
- preserve uncertainty and provenance
- consume optional existing Groove/Arrangement/Layer evidence
- fail closed on unavailable or non-portable evidence

It does **not**:

- compute candidate fit scores (#465)
- generate prepared audio variants (#466)
- add a DB schema
- add a DSP dependency
- build a Missing-Layer AI/heuristic engine
- require plugin, DAW, host transport, or UI integration
- run heavy analysis in an audio thread

---

## 8. Validation contract

Focused tests use synthetic/fixture Track Maps and must cover at least:

- BPM and Key mapping
- Key mode partial preservation
- global Loudness → partial Energy
- Brightness → Spectrum
- absent Groove/Arrangement/Desired Layers → honest `no_result`
- optional existing evidence consumption
- absolute-path redaction/fail-closed behavior
- canonical JSON evidence references
- deterministic serialization
- malformed Track Map failure
- delegation to cached Context Analyzer
- propagation of analyzer failures

No private audio fixture is required.

---

## 9. VST / host boundary

VST3 and host integration are parked outside this campaign under #469. Track Context Profile v1 has no VST, plugin shell, browser UI, host-sync, preview, drag/drop, or packaging dependency.

Any later workspace/plugin path consumes this Core contract rather than reimplementing its musical evidence logic.

---

## 10. References

- `src/context_analyze.py` — existing DB-free Track Map analysis and cache path
- [`02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md`](02_HARMONIC_RHYTHMIC_MATCHING_SPEC.md) — downstream Musical Fit contract
- [`04_REALTIME_FIT_TRANSFORM_SPEC.md`](04_REALTIME_FIT_TRANSFORM_SPEC.md) — downstream prepared transform contract
- [#467](https://github.com/jannekbuengener/sample-brain/issues/467) — Track Context Profile v1 runtime slice
- [#469](https://github.com/jannekbuengener/sample-brain/issues/469) — parked VST3 meta scope
