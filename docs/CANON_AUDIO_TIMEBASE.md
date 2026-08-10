# Canonical Working Audio & Shared Timebase

**Issue:** [#234](https://github.com/jannekbuengener/sample-brain/issues/234)
**Parent:** [#227](https://github.com/jannekbuengener/sample-brain/issues/227)
**Contract reference:** [TRACK_MAP_V1.md](TRACK_MAP_V1.md) §4–5

This document defines the canonical working-audio format and the authoritative
timebase for all track-level analyses. It is the foundation that #236
(BeatGrid) and #265 (StructureV1) build upon.

---

## 1. Canonical Working Format

| Property | Value |
|----------|-------|
| Container | WAV |
| Sample rate | 44100 Hz (matches `ANALYZE_SR` in `src/config.py`) |
| Channels | 1 (mono) |
| Subtype | PCM_16 |

Constants live in `src/canon_audio.py`:
`CANONICAL_SAMPLE_RATE`, `CANONICAL_CHANNELS`, `CANONICAL_SUBTYPE`,
`CANONICAL_FORMAT`.

---

## 2. Bypass Rule

An original input file is used **directly** (no conversion, no working WAV)
if and only if it already matches the canonical format:

- format = WAV
- sample rate = 44100
- channels = 1
- subtype = PCM_16

`is_canonical_format(path)` returns `True` only when all four conditions are
met. Any other container, sample rate, channel count, or PCM/float subtype
triggers a canonical conversion via `render_canonical_wav()`.

This rule is intentionally strict: PCM_24, PCM_32, FLOAT, FLAC, stereo, and
non-44100 files are all converted so that downstream analyses share one
unambiguous sample grid.

---

## 3. Original Never Modified

`render_canonical_wav(src, dst)` always writes to a **different** destination
path. It never overwrites the source. The byte-identical integrity of the
original is guaranteed by:

- `src.resolve() == dst.resolve()` raises `ValueError`
- the function only reads `src` and writes `dst`

Tests verify the original hash is stable before and after conversion.

---

## 4. Portable Hash / Provenance Link

Original and working files are linked by **content hashes** (SHA-1 via
`src/utils.file_hash`), never by absolute filesystem paths.

`verify_provenance(original, working)` returns
`(original_hash, working_hash, identical_content)`:

- When the original is used directly (Bypass), `identical_content` is `True`
  and both hashes are equal.
- When a canonical conversion has been produced, the hashes differ and
  `identical_content` is `False`. The Track Map records both hashes in its
  `source.original` and optional `source.working_audio` blocks.

No private absolute paths are stored in any persistent provenance record.

---

## 5. Sample Index as Authoritative Timebase

The **sample index** is the authoritative timebase. Seconds are a derived
representation only.

`AudioTimebase(sample_rate, n_samples)` owns the authoritative grid:

- `seconds_to_samples(sec, mode)` → integer sample boundary
- `samples_to_seconds(idx)` → derived seconds value
- `duration_seconds` → derived from `n_samples / sample_rate`

---

## 6. Range Semantics: Start Inclusive / End Exclusive

`AudioRange(start_sample, end_sample)` defines a half-open interval:

```
[start_sample, end_sample)
```

- `start_sample` is **inclusive** (the first sample in the range)
- `end_sample` is **exclusive** (the sample immediately after the range)
- `n_samples = end_sample - start_sample`
- `contains_sample(i)` returns True for `start_sample <= i < end_sample`

Invalid ranges (negative start, empty range, end <= start) raise
`ValueError` (fail-closed).

---

## 7. Deterministic Rounding Rule

When converting backend time values (seconds/floats) to integer sample
boundaries, two explicit rounding modes are defined:

| Mode | Behavior | Use case |
|------|----------|----------|
| `floor` | `int(np.floor(sec * sr))` | Conservative start boundary; never overshoots |
| `round` (default) | `int(np.round(sec * sr))` | Nearest sample; standard for mid-point alignment |

`np.round` uses banker's rounding (round-half-to-even), which is
deterministic and reproducible across platforms.

Edge cases:

- `seconds_to_samples(0.0)` → `0` in both modes
- When `compute_range_from_seconds` produces `end <= start`, `end` is bumped
  to `start + 1` so the range is never empty.
- `end_sec` exceeding the audio duration raises `ValueError`.

---

## 8. Why #236 and Later Analyses Can Build on This

#236 (BeatGrid) needs beats and downbeats on a single, reproducible sample
grid. With this slice, every beat/downbeat position from any backend
(`beat_this/final0`, `librosa`) can be converted to integer sample indices
via `AudioTimebase.seconds_to_samples()` and stored as sample-accurate
boundaries. #265 (StructureV1) and later asset cuts use the same
`AudioRange` half-open semantics so that sections, stems, and loop slices
land on exactly the same sample boundaries.

---

## 9. Acceptance Mapping (Issue #234)

| #234 criterion | This document / code |
|----------------|----------------------|
| Canonical working format and Bypass rule documented | §1, §2; `src/canon_audio.py` |
| Original remains unchanged | §3; `render_canonical_wav` |
| Original and working file portable, hash-linked | §4; `verify_provenance` |
| All downstream analyses can reference integer sample boundaries on same timebase | §5; `AudioTimebase` |
| Start-inclusive / end-exclusive semantics defined | §6; `AudioRange` |
| Typical WAV/FLAC and rounding cases testable | §7; `tests/test_canon_audio.py` |
| No private absolute paths in persistent data | §4; no absolute paths in code or tests |
