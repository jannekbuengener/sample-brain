# Stem Cache + Model Provenance v1 — Local Regenerable Cache

**Issue:** [#248](https://github.com/jannekbuengener/sample-brain/issues/248)
**Parent:** [#229](https://github.com/jannekbuengener/sample-brain/issues/229) — Stem Separation for Track Deconstruction
**Depends on:** [#244](https://github.com/jannekbuengener/sample-brain/issues/244) (Stem Manifest v1), [#247](https://github.com/jannekbuengener/sample-brain/issues/247) (default/quality selection)
**Next consumer:** [#249](https://github.com/jannekbuengener/sample-brain/issues/249) (Deconstruct stem integration)
**Status:** `DONE_MERGED_CLOSED`
**Cache contract version:** `1` (`STEM_CACHE_CONTRACT_VERSION`)
**Cache document type:** `sample_brain.stem_cache_entry`

This document defines the local, regenerable, file-based **stem cache** and the
exact **model provenance** used by Sample Brain. It is a *separate* cache
contract from Stem Manifest v1 (#244). It is not a database, introduces no new
dependency, and keeps the core import graph free of `audio_separator` / `torch`.

---

## 1. Purpose

Stem separation is expensive. Sample Brain must not separate the same working
audio again when:

- same original track,
- same actual separation input (working audio),
- same backend/wrapper,
- same exact model/checkpoint,
- same actual weight set,
- same output-affecting config

were already used successfully. At the same time it must **never** reuse old
stems when any of those inputs changed.

Every cached stem remains traceable to:

- original track (`track_ref`)
- actual working audio (`working_audio_hash`)
- wrapper (`backend`)
- wrapper version (`backend.version`)
- model (`model.family` / `model.name`)
- checkpoint (`model.checkpoint`)
- actual weight hash (`model.weight_hash`)
- relevant parameters (`configuration`)
- code license (`model.code_license`)
- weight usage/license status (`model.weight_license`)

---

## 2. Scope Boundary

This issue builds:

- model identity / provenance
- deterministic cache fingerprint / key
- local stem cache
- validation / invalidation
- reusable wrapper-level cache API (`separate_with_cache`)
- correction of fake spike provenance

It does **not** build: Deconstruct integration (#249), Performance Pack stem
integration (#261), stem-based asset generation (#255), producer groups (#268),
default automatic stem execution, a new separation model, a new dependency, a
database cache, or a cloud cache. No private audio and no weights are committed.

---

## 3. Core Module

`src/stem_cache.py` — pure stdlib (`hashlib`, `json`, `os`, `tempfile`,
`shutil`, `pathlib`). It MUST NOT import `audio_separator`, `torch`, or
`onnxruntime`, so importing sample-brain core stays lightweight.

It reuses the established cache principles (canonical deterministic JSON,
SHA-256 keys/fingerprints, explicit contract version, explicit > env >
platform-default path precedence, cache outside the repo, atomic writes,
malformed/corrupt entry => MISS, structural + expected-value validation, no
absolute private paths in entries, no SQLite, no global cache framework, no new
dependency).

---

## 4. Cache Location

Environment variable: `SAMPLE_BRAIN_STEM_CACHE_DIR`

Platform default:

- Windows: `%LOCALAPPDATA%/sample-brain/stems`
- Unix: `${XDG_CACHE_HOME:-~/.cache}/sample-brain/stems`

Precedence (highest first):

1. explicit argument (`cache_dir=`)
2. environment variable
3. platform default

The absolute cache root is **never** serialized into portable entries or results.

---

## 5. Cache Key

The cache key is `SHA-256` over canonical deterministic JSON (sorted keys, no
timestamp, no UUID) of:

```json
{
  "track_ref": "<portable original-track identity>",
  "working_audio_hash": "<content hash of the actual separation input>",
  "separation_fingerprint": "<see section 6>"
}
```

`track_ref` and `working_audio_hash` are deliberately **separate** concepts:
they may be equal (original audio separated directly), or differ when the
separation operates on a canonicalized / resampled / prepared working file.
Filenames are never used as identity.

---

## 6. Separation / Model Fingerprint

A deterministic parameter/model fingerprint, separate from the source audio:

```json
{
  "component": "stem_separator",
  "stem_cache_contract_version": 1,
  "sample_brain_version": "0.1.0",
  "backend": { "name": "python-audio-separator", "version": "0.44.5" },
  "model": {
    "family": "htdemucs",
    "name": "htdemucs",
    "checkpoint": "955717e8",
    "weight_hash": { "algorithm": "sha256", "value": "<actual weight identity>" },
    "code_license": "MIT",
    "weight_license": "RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED"
  },
  "configuration": { "overlap": 0.25, "segment": 10 }
}
```

**Fingerprinted** (output-affecting only): backend name+version, model
family/name/checkpoint/weight_hash/code license/weight usage status, and
configuration parameters that affect resulting stems (output format, sample
rate, overlap, segment / segment_size, model-specific params).

**NOT fingerprinted**: output directory, model cache directory path, timeout,
temp directory, absolute input path, timestamps.

---

## 7. Model Identity & Checkpoint vs Weight Hash

`StemModelIdentity` carries:

- `family`
- `name`
- `checkpoint`
- `weight_hash` (`{algorithm, value}` or `None`)
- `code_license`
- `weight_license`

### htdemucs (single released checkpoint)

- name: `htdemucs`
- checkpoint: `955717e8`
- code license: `MIT`
- weight usage: `RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED`

### htdemucs_ft (bag of four released checkpoints)

- name: `htdemucs_ft`
- checkpoint: `f7e0c4bc,d12395a8,92cfc3b6,04573f0d`
- code license: `MIT`
- weight usage: `RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED`

**Critical:** `checkpoint` is a released checkpoint/source **identifier**, NOT a
cryptographic weight hash. The short signatures `955717e8` and the four-source
bag are NOT full local weight hashes.

### Actual weight hashing (fail closed)

- single weight file: `SHA-256(file bytes)`
- multi-file / bag model: sort component identities, compute aggregate
  `SHA-256` over canonical JSON of `checkpoint` + component hashes.
  Algorithm label: `sha256-set-v1`.

If the actual weight file path(s) cannot be resolved, the wrapper/cache API
**requires explicit verified weight identity** from the caller. Incomplete
model identity (missing real `weight_hash`) can **never** produce a reusable
cache hit — it may run uncached (truthfully) or report provenance-unavailable,
but it never fabricates provenance.

---

## 8. Invalidation Matrix

| Change | Result |
|--------|--------|
| same track + same working audio + same backend/version + same checkpoint + same actual weights + same config | **HIT** |
| change original track identity | MISS |
| change working audio bytes/hash | MISS |
| change backend version | MISS |
| change model (htdemucs ↔ htdemucs_ft) | MISS |
| change checkpoint | MISS |
| change actual weight hash | MISS |
| change output-affecting config | MISS |
| change cache contract version | MISS |
| change license / usage provenance | MISS |
| incomplete model identity | NO HIT |
| corrupt entry | MISS |
| missing output file | MISS |
| output hash mismatch | MISS |

---

## 9. Cache Entry

Physical structure:

```
<cache_root>/
  <cache_key>/
    entry.json
    outputs/
      drums.wav
      bass.wav
      vocals.wav
      other.wav
    manifests/
      stem_drums_....json
      ...
```

`entry.json` preserves at least: `document_type`, `schema_version`, `cache_key`,
`track_ref`, `working_audio_hash`, `separation_fingerprint`, backend provenance,
model provenance, effective configuration, aggregate run status, and per-stem
results (relative `file_ref`, `hash`, `status`, relative `manifest_ref`).

Never stored: original absolute input path, cache root, model cache absolute
path, private source filename, local DB ID.

---

## 10. Status / Failure Behavior

Respects #244 statuses (`ok`, `partial`, `not_run`, `no_result`, `failed`):

- `ok`: reusable HIT after full validation.
- `partial`: reusable only when all declared partial outputs validate and status
  remains explicitly `partial`.
- `not_run`: stored as execution evidence only; NOT reusable as a successful hit.
- `no_result`: not silently converted to hit/success.
- `failed`: not reused as successful hit.

Per-stem partial/error information is preserved separately.

---

## 11. Output Validation On Hit

For every reusable output, before a HIT is accepted:

- file exists
- relative path stays inside the cache entry (no traversal)
- content hash matches stored output hash
- manifest exists and parses
- `track_ref` matches expected track
- source working-audio hash matches
- model provenance matches expected fingerprint

Any mismatch → MISS. No crash. No fake hit.

---

## 12. Atomic Writes

JSON is written via temp file + `flush`/`fsync` + `os.replace`. A complete
stem-cache entry is staged under a temporary staging directory inside the cache
root and published (moved) only after all required files and metadata are
written and validated. A half-written cache is never accepted as a hit. The
implementation is Windows-safe.

---

## 13. Wrapper Cache API

`separate_with_cache(...)` is the reusable wrapper-level entry point #249 will
consume:

```python
separate_with_cache(
    *,
    input_path,
    track_ref,
    working_audio_hash,
    model_identity,           # StemModelIdentity (must be complete)
    configuration,
    output_dir,
    cache_dir=None,
    cache_enabled=True,
    backend_name="unknown",
    backend_version="unknown",
    executor,                 # injected separation callable
) -> { "cache_status": "hit" | "miss" | "disabled", ... }
```

- On HIT: reuse validated cached stem outputs (copied into `output_dir`).
- On MISS: run the injected `executor`, validate the result, publish the cache
  entry if eligible.

It is **not** wired into `src/deconstruct.py` in this issue (#249 scope).

---

## 14. Privacy

- No absolute source path in entry.
- No cache path in entry.
- No model-cache path in entry.
- No private filenames or local DB IDs.

---

## 15. #247 License Provenance

For both candidates the resolved status is:

- code license: `MIT`
- weight usage: `RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED`
  (internal policy classification `VERIFIED_NONCOMMERCIAL`)

`CC-BY-NC` is **not** asserted. The Hugging Face `license: mit` metadata is
never silently turned into a commercial weight grant. The spike no longer
stamps a fabricated long weight hash.

---

## 16. #244 Remains Model-Independent

This cache contract does not change Stem Manifest v1 (#244). No default model
is prescribed by the manifest; standard stem kinds are unchanged; no production
default is added to the schema. Any new cache document is a separate cache
contract, not Stem Manifest v2.

---

## 17. Handoff To #249 (DONE)

#249 (Deconstruct stem integration) is implemented:

- `src/deconstruct.py` calls `separate_with_cache` (from this module) for the
  optional `stems` step. The executor is `tools.stem_separator_spike` run in an
  isolated subprocess; `stem_runtime.build_subprocess_executor` wires provenance.
- The actual weight identity is supplied by the caller via `--stem-weight-hash`
  (and validated against the model's expected algorithm); `backend_name` /
  `backend_version` are passed for correct fingerprinting.
- Cache order: (1) pack-local #262 resume (checked by the orchestrator before
  the step runs), then (2) global #248 cache — a `hit` copies validated outputs
  into `<pack_root>/stems/` without re-running separation. `cache_status` is
  recorded in the stems StepResult provenance (`stem_cache_status`).
- Incomplete model identity degrades to uncached, truthful execution (no
  fabricated provenance hit), preserving the guarantees above.
