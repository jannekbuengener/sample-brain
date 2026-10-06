# Analyzer Perturbation / Metamorphic Fixture Contract

**Status:** ACTIVE_SUPPORTING — mechanics freeze for [#957](https://github.com/jannekbuengener/sample-brain/issues/957)  
**Class:** ACTIVE_SUPPORTING  
**Parents:** [#950](https://github.com/jannekbuengener/sample-brain/issues/950), [#942](https://github.com/jannekbuengener/sample-brain/issues/942)  
**Related (boundary only):** [#956](https://github.com/jannekbuengener/sample-brain/issues/956) owns portable benchmark artifact / ARVP mapping — not transform mechanics.

## Architecture outcome

```text
ANALYZER_PERTURBATION_FIXTURE_CONTRACT_FROZEN
```

This contract owns **transform mechanics + provenance only**. It does **not** own musical expectations, invariance claims, tolerances, or promotion thresholds for AQ1–AQ7.

## Ownership

| Concern | Owner |
|---|---|
| Transform identity / version | this contract (`src/analyzer_perturbation.py`) |
| Deterministic parameters + explicit composition order | this contract |
| Source → derived fixture provenance | this contract |
| Path-independent semantic derived identity | this contract |
| Invalid / non-finite parameter fail-closed | this contract |
| Whether a transform should preserve / transform / invalidate a domain target | AQ1–AQ7 |
| Expected transformed ground truth, tolerances, correctness gates | AQ1–AQ7 |
| Generic metric / comparison / Evidence Bundle envelope | ARVP + [#956](https://github.com/jannekbuengener/sample-brain/issues/956) |

## Non-goals

- no global robustness score
- no AQ-specific threshold values
- no analyzer optimization or new production analyzer algorithm
- no Workbench / UI surface
- no production pitch/time-stretch product feature
- no coupling to `src/fit_variants.py` product/cache path
- no private audio, DB, cache, or absolute host paths in semantic identity
- no hidden normalization, mono mixdown, or resampling outside an explicit transform step

## Contract identity

| Field | Value |
|---|---|
| `contract_id` | `sample-brain.analyzer-perturbation.v1` |
| `contract_version` | `1` |
| Runtime module | `src/analyzer_perturbation.py` |
| Artifact policy | synthetic/public fixtures only; derived WAVs are runtime-local and never committed |

## Transform vocabulary (v1)

Every step is an explicit `{id, version, params}` record. Composition order is the list order. Unsupported IDs fail closed.

| Transform ID | Version | Params | Capability |
|---|---|---|---|
| `gain` | `1` | `factor: float` (finite, > 0) | **supported** — linear multiply; not peak normalize |
| `peak_normalize` | `1` | `target_peak: float` (finite, > 0, ≤ 1) | **supported** — explicit peak scale only when requested |
| `to_mono` | `1` | `method: "mean"` | **supported** — mean across channels; no-op if already mono |
| `to_stereo` | `1` | `method: "duplicate"` | **supported** — duplicate mono to L/R; reject if >1 channel already |
| `resample` | `1` | `target_sr: int` (finite integer, > 0) | **supported** — explicit `librosa.resample`; no other hidden conversion |
| `pad_silence` | `1` | `leading_samples: int ≥ 0`, `trailing_samples: int ≥ 0` | **supported** — zero-pad in samples at current SR/channels |
| `trim` | `1` | `leading_samples: int ≥ 0`, `trailing_samples: int ≥ 0` | **supported** — explicit crop; must leave ≥ 1 sample |
| `pitch_shift` | `1` | `n_steps: float` (finite) | **supported** — `librosa.effects.pitch_shift` (fixture-only) |
| `time_stretch` | `1` | `rate: float` (finite, > 0) | **supported** — pitch-preserving `librosa.effects.time_stretch` (fixture-only) |

### Explicit unsupported (v1)

| Transform | Reason |
|---|---|
| Energy / threshold silence detection trim | Non-parameterized detection would hide thresholds and drift across backends |
| Implicit analyzer-style load (`safe_load` / canonical mono+SR) as part of materialize | Would hide mono/resample; load preserves source channels and sample rate until explicit steps run |

Unsupported requests raise a typed error; they must not be approximated.

## Spec shape

```json
{
  "contract_id": "sample-brain.analyzer-perturbation.v1",
  "contract_version": "1",
  "transforms": [
    {"id": "gain", "version": "1", "params": {"factor": 0.5}},
    {"id": "pad_silence", "version": "1", "params": {"leading_samples": 1000, "trailing_samples": 0}}
  ]
}
```

Rules:

- `transforms` may be empty (identity derivation: same audio content semantics, new derived artifact path allowed).
- Unknown keys on a step fail closed.
- Missing required params fail closed.
- Non-finite (`NaN` / `±Inf`) numeric params fail closed.
- Negative sample counts or non-positive rates/factors fail closed where the table requires positivity.

## Provenance and semantic identity

### Source reference

Portable only:

```json
{"content_hash": {"algorithm": "sha256", "value": "<hex>"}}
```

Absolute paths, usernames, hostnames, and wall-clock fields are forbidden in semantic identity.

### Derived semantic identity

```text
derived_identity = sha256(
  canonical_json({
    contract_id,
    contract_version,
    source_content_hash,
    transforms  # validated, order-preserving, params canonicalized
  })
)
```

Properties:

- same source bytes + same validated transform spec → same `derived_identity`
- changing transform order → different identity
- output filesystem path does not enter identity
- derived WAV bytes are a materialization convenience; consumers key on `derived_identity` + provenance, not on path strings

### Provenance record (portable)

Returned by materialize / describe helpers; path fields are process-local convenience and must not be treated as semantic identity:

| Field | Portable? |
|---|---|
| `contract_id`, `contract_version` | yes |
| `source.content_hash` | yes |
| `transforms` | yes |
| `derived_identity` | yes |
| `backend` (`librosa` name + version when DSP used) | yes (informational) |
| `output_path` | **no** — local only |

## Materialization rules

1. Read source with `soundfile` preserving channels and sample rate (no hidden mono/resample).
2. Apply transforms strictly in list order.
3. Write derived WAV to an explicit destination path ≠ source path (also reject hard-linked destinations that share the source inode).
4. Never mutate or overwrite the source artifact.
5. Do not peak-normalize, dither-policy-change, or resample unless the corresponding transform is present.
6. Derived write uses `PCM_16`. If post-transform peak would exceed `1.0`, materialization **fails closed** with `ValidationError` — linear gain must not silently clip.
7. Synthetic/public fixtures only in tests; never commit derived audio.

## Consumer reuse proof (required)

At least two structurally different AQ-like consumers must generate derived fixtures through this module without bespoke transform plumbing:

1. tempo / beat-style consumer (AQ1-shaped)
2. onset / classification-style consumer (AQ3/AQ4-shaped)

Those proofs demonstrate fixture reuse only. They do **not** freeze domain tolerances.

## Exit vocabulary

Exactly one:

- `ANALYZER_PERTURBATION_FIXTURE_CONTRACT_FROZEN`
- `PERTURBATION_CONTRACT_INSUFFICIENT`
- `BLOCKED_BY_MISSING_SAFE_TRANSFORM_PRIMITIVE`
