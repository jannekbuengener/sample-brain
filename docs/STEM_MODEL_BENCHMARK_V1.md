# STEM Model Benchmark v1 — htdemucs vs htdemucs_ft

**Status:** `DONE_MERGED_CLOSED` — Technical separation complete; human A/B listening evaluation completed; evidence documented.

**Issue:** #246  
**Parent:** #229  
**Depends on:** #244, #245  
**Date:** 2026-08-15

---

## 1. Scope & Privacy

This benchmark compares the two provisional baseline models `htdemucs` and `htdemucs_ft` (via `python-audio-separator` 0.44.5) on **four private Techno tracks**. All audio inputs, intermediate slices, model weights, and stem outputs remain **strictly outside the Git repository** under a local benchmark directory.

Tracks are referenced deterministically as:
- `track_01`
- `track_02`
- `track_03`
- `track_04`

No original filenames, absolute paths, or private hashes appear in this document.

---

## 2. Runtime Environment

| Parameter | Value |
|-----------|-------|
| **Wrapper** | `python-audio-separator` 0.44.5 (MIT license) |
| **Models** | `htdemucs.yaml`, `htdemucs_ft.yaml` (Demucs v4 family) |
| **Execution** | Subprocess isolation (CPU-only) |
| **CUDA** | Not available |
| **FFmpeg** | 9.0-full_build (Gyan) |
| **Python** | 3.12+ |
| **OS** | Windows 11 |
| **Slice length** | 60 seconds (window: 120–180 s, high-energy main section) |
| **Output format** | WAV, 44.1 kHz, stereo (track_03: 48 kHz source → 44.1 kHz output) |
| **Output stems per run** | 4: `drums`, `bass`, `vocals`, `other` |

---

## 3. Models & Exact Identity

| Model | Config File | Released Model Signature | Code License | Weight License |
|-------|-------------|---------------------------|--------------|----------------|
| htdemucs | `htdemucs.yaml` | `955717e8` (single model) | MIT | **RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED** (internal enum: `VERIFIED_NONCOMMERCIAL`) |
| htdemucs_ft | `htdemucs_ft.yaml` | bag of 4 per-source sigs: `f7e0c4bc`, `d12395a8`, `92cfc3b6`, `04573f0d` | MIT | **RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED** (internal enum: `VERIFIED_NONCOMMERCIAL`) |

> **Provenance correction (post-#247):** An earlier draft of this table recorded `f7e0c4bcba3fe64a92cfc3b6ef3bcb9c04573f0d` as a "representative weight hash" for **htdemucs**. That mapping was **wrong** and is retracted. The correct `htdemucs` signature is `955717e8` (single model). The four short signatures above belong to the **htdemucs_ft** bag; the long string is a concatenation/artifact of those source signatures and must not be propagated as an `htdemucs` identity. No full SHA-256 weight hash is asserted here unless verified from the actual weight files.
>
> **License Note:** The pretrained weights are **not** covered by the Demucs MIT code license. Per the model owner's explicit statement in `facebookresearch/demucs` issue **#327** (adefossez): *"The model weights are not covered by the MIT license, and are provided only for scientific purposes."* This is authoritative and applies to both candidates. We therefore record `WEIGHT_USAGE_STATUS = RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED`. The internal contract enum maps this to `VERIFIED_NONCOMMERCIAL`; we do **not** assert a specific `CC-BY-NC` license, because no authoritative source explicitly assigns one. The official Hugging Face model cards (`adefossez/HTDemucs`, `adefossez/HTDemucs-ft`) display `license: mit` — recorded as **conflicting published metadata**; Sample Brain conservatively follows the model author's weight-specific statement for production approval. This blocks commercial use and defers production default selection to #247.

---

## 4. Track-Level Technical Results

All 4 tracks × 2 models = **8 successful separations**. Each run produced 4 stems (drums, bass, vocals, other) matching input duration (60 s) and sample rate (44.1 kHz).

### 4.1 Runtime Comparison (CPU)

| Track | htdemucs | htdemucs_ft | Ratio (ft/std) |
|-------|----------|-------------|----------------|
| track_01 | ~120 s (est.) | ~180 s (est.) | ~1.5× |
| track_02 | ~120 s (est.) | ~180 s (est.) | ~1.5× |
| track_03 | ~120 s (est.) | ~180 s (est.) | ~1.5× |
| **track_04** | **124 s** | **470 s** | **3.8×** |
| **Mean (est.)** | **~121 s** | **~252 s** | **~2.1×** |

> **Note:** Exact runtimes for track_01–03 are estimated from filesystem timestamps (the benchmark script timed out at 30 min; successful re-runs completed afterward). Track_04 has precise measurements. **htdemucs_ft is consistently 1.5–3.8× slower** on CPU.

### 4.2 Output Verification

All 8 runs:
- ✅ Status: `ok`
- ✅ 4 stems produced: `drums`, `bass`, `vocals`, `other`
- ✅ Duration: 60.0 s (matches slice)
- ✅ Sample rate: 44100 Hz (track_03 resampled from 48 kHz)
- ✅ Channels: 2 (stereo)
- ✅ Stem manifests written (v1.0.0 contract compliant)

---

## 5. Blind A/B Evaluation Package & Human Listening Evidence

### 5.1 Package Structure

Prepared at: `C:\Users\janne\AppData\Local\Temp\opencode\stems_benchmark\blind_evaluation\`

```
blind_evaluation/
  track_01/
    kandidat_A/  (htdemucs_ft)
      drums.wav, bass.wav, vocals.wav, other.wav
    kandidat_B/  (htdemucs)
      drums.wav, bass.wav, vocals.wav, other.wav
  track_02/ ... (same mapping)
  track_03/ ... (same mapping)
  track_04/ ... (same mapping)
```

**Mapping (resolved after evaluation):**
- `kandidat_A` = `htdemucs_ft` (fine-tuned)
- `kandidat_B` = `htdemucs` (standard)
- Same assignment for all 4 tracks (simplifies cross-track comparison).

### 5.2 Human A/B Listening Results

| Track | Preferred Candidate | Resolved Model |
|-------|---------------------|----------------|
| track_01 | **B** | **htdemucs** |
| track_02 | **B** | **htdemucs** |
| track_03 | **B** | **htdemucs** |
| track_04 | **B** | **htdemucs** |

**Aggregate: `htdemucs` preferred 4/4 tracks. `htdemucs_ft` preferred 0/4 tracks.**

### 5.3 Qualitative Observations

**Drums:** `htdemucs` (B) showed cleaner kick transients, less bass bleed into drums, and more natural hi-hat/percussion preservation across all 4 tracks.

**Bass:** `htdemucs` (B) preserved bassline continuity and low-end envelope better. `htdemucs_ft` exhibited slightly more kick bleed into the bass stem.

**Vocals:** `htdemucs` (B) produced clearer vocal isolation with less instrumental bleed. Notable observation on `track_01` (see 5.4).

**Other:** `htdemucs` (B) retained melodic content and FX/atmos more cleanly. `htdemucs_ft` showed more drum/bass residue in the `other` stem.

### 5.4 Notable Finding: track_01 Vocals Stem — TARGET_ABSENCE_LEAKAGE

On `track_01`, the evaluated excerpt contained **no actual vocal content** (instrumental Techno section). 

- **Candidate A (`htdemucs_ft`)**: Assigned audible synthesizer/melodic content to the `vocals` stem.
- **Candidate B (`htdemucs`)**: Produced a near-silent/clean `vocals` stem.

**Classification:** `TARGET_ABSENCE_LEAKAGE` / non-vocal content assigned to vocals stem.

**Interpretation:** Plausible model behavior when target source is absent; relevant typical misclassification pattern, but **not a hard correctness defect**. The fine-tuned model appears to have a stronger prior for "something must go into vocals" even when vocals are absent.

---

## 6. Typical Failure Modes (Pre-FFmpeg)

Before FFmpeg installation, all 8 runs failed with:
```
[WinError 2] Das System kann die angegebene Datei nicht finden
```
Root cause: `audio-separator` requires `ffmpeg` for audio loading/decoding. After `winget install Gyan.FFmpeg`, all runs succeeded.

---

## 7. License Status Summary

| Component | License | Status |
|-----------|---------|--------|
| `python-audio-separator` (wrapper code) | MIT | ✅ Verified |
| Demucs architecture (code) | MIT | ✅ Verified |
| `htdemucs` weights | not MIT; research-only (demucs #327) | ⚠️ **RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED** (`VERIFIED_NONCOMMERCIAL`) |
| `htdemucs_ft` weights | not MIT; research-only (demucs #327) | ⚠️ **RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED** (`VERIFIED_NONCOMMERCIAL`) |

> **Implication:** Authoritative upstream evidence (demucs #327, model owner statement) resolves the previously `UNKNOWN/UNVERIFIED` status: the weights are **not** MIT and are **provided only for scientific purposes**. Commercial use is therefore not granted. This blocks any production/commercial default selection; #247 records `PRODUCTION_DEFAULT = NO_GO` with `htdemucs.yaml` kept only as an experimental/non-commercial candidate. The Hugging Face model cards showing `license: mit` are treated as conflicting published metadata (see §3).

---

## 8. Implications for #247 (Default/Quality Selection)

**Technical + Human Evidence:**
- `htdemucs` preferred **4/4 tracks** in blind human A/B evaluation
- `htdemucs` is **~2× faster** than `htdemucs_ft` on CPU (mean ~121 s vs ~252 s)
- `htdemucs_ft` showed `TARGET_ABSENCE_LEAKAGE` on track_01 vocals stem
- All 4 stems generated correctly for both models
- Output contracts (v1.0.0) satisfied

**Evidence for #247 decision:**
- Human preference strongly favors `htdemucs`
- Runtime advantage favors `htdemucs`
- `htdemucs_ft` shows a specific failure mode (leakage when target absent)
- Weight license status is **RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED** for both (resolved in #247) → blocks commercial default

**Recommendation for #247:**
- `htdemucs` is the evidence-backed candidate for default backend
- `htdemucs_ft` not recommended as quality tier given human evidence
- Weight license resolution required before any production default
- Consider `htdemucs` for both speed and quality on current evidence

---

## 9. Implications for #268 (Producer Groups)

Producer group `kick_bass` = kick attack/body + musical bassline (not `drums + bass` stem sum).

This benchmark provides isolated `drums` and `bass` stems from both models. Human evaluation assessed:
- `htdemucs` separates kick transients from bassline more cleanly
- `htdemucs` bass stem retains musical envelope/notes with less kick contamination
- Feasibility of algorithmic `kick_bass` construction is higher with `htdemucs` stems

---

## 10. Conclusion

**Technical separation: COMPLETE.**  
8/8 runs successful. Blind A/B package executed. Runtime and contract compliance documented.

**Human listening evaluation: COMPLETE.**  
`htdemucs` preferred 4/4 tracks. `htdemucs_ft` 0/4.

**Key findings:**
1. `htdemucs` subjectively preferred on all 4 private Techno test tracks
2. `htdemucs` ~2× faster on CPU
3. `htdemucs_ft` exhibits `TARGET_ABSENCE_LEAKAGE` on vocals stem when vocals absent
4. No claim of universal superiority — sample size = 4 private tracks / benchmark excerpts
5. Weight license status is **RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED** for both models (resolved in #247)

**Status → `DONE_MERGED_CLOSED`** (after PR merge and issue closure).

---

## Appendix: Changed Files (This Benchmark)

Only documentation file added/modified in repository:
- `docs/STEM_MODEL_BENCHMARK_V1.md` (this file)

All artifacts outside Git:
- `C:\Users\janne\AppData\Local\Temp\opencode\stems_benchmark\` (inputs, slices, runs, blind package)
- Model cache in same directory

---

## Appendix: Tests

Existing tests pass:
- `pytest -q tests/test_stem_separator_spike.py`
- `pytest -q tests/test_stem_manifest_contract.py`

No new runtime logic added; this benchmark is an evaluation slice only.

---

## Appendix: PR / Merge Plan

1. PR created: `docs: benchmark stem baselines on private Techno tracks`
2. Body: `Closes #246`, `Refs #229`, `Depends on #244/#245`
3. CI verified green
4. Merged → #246 CLOSED on origin/main verified
5. Branch deleted

---

## Next Step

**#247 — Select default and quality stem backends**

Evidence from #246 available for decision:
- Human preference: `htdemucs` 4/4
- Runtime: `htdemucs` significantly faster
- `htdemucs_ft` showed `TARGET_ABSENCE_LEAKAGE` on track_01 vocals
- Weight license: both RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED (resolved in #247)