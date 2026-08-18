# Model Readiness v1 — Optional ML Runtime and Commercial Policy

**Issue:** #423  
**Status:** canonical readiness contract  
**Date:** 2026-08-18

## 1. Purpose

Sample Brain keeps optional ML backends isolated from Core. This contract separates three questions that must never be collapsed into one flag:

1. **Technical availability** — can the optional runtime be imported and invoked on the supported host?
2. **Model/weight provenance** — which exact package/model revision and license metadata are being used?
3. **Commercial readiness** — does Sample Brain have sufficient primary-source license evidence to approve that exact model/weight as a commercial product default?

A technically working model is not automatically commercially approved. A package/code license is not automatically the license of separately distributed model weights.

## 2. CLAP reproducibility contract

The supported optional CLAP matrix for this revision is:

| Component | Pinned identity | Evidence |
|---|---|---|
| Python | 3.12 | Sample Brain project baseline |
| PyTorch | `2.13.0` | PyPI release; CPython 3.12 Windows x86-64 wheel published |
| Transformers | `5.14.1` | PyPI release; CLAP remains an official Transformers model family |
| Model | `laion/clap-htsat-unfused` | Hugging Face model repository |
| Model revision | `79b58ed25fc00386262a2bea4b19fd21dc4310a0` | immutable Hugging Face safetensors conversion commit |
| Serialization | `safetensors` required | model loader passes `use_safetensors=True` |
| Declared model license | `Apache-2.0` | model-card metadata in the official repository |
| Embedding dimension | `512` | existing Sample Brain CLAP contract |

Install surfaces (`requirements-clap.txt` and `[project.optional-dependencies].clap`) must stay identical for the two Python packages.

The model and processor loaders must pass the immutable model `revision`. The model loader additionally requires `use_safetensors=True`; it must not silently fall back to the repository's Pickle checkpoint. `model_info().model_version` reports the safetensors revision rather than a floating or planned value.

### Serialization security boundary

The earlier repository snapshot exposed the legacy `pytorch_model.bin` Pickle checkpoint. Because deserializing untrusted Pickle-backed PyTorch artifacts can execute code, Sample Brain does not use that snapshot as the supported runtime identity. The pinned revision above is the official repository commit that adds a safetensors representation, and runtime loading explicitly requires safetensors.

This is a supply-chain control, not a change to the CLAP model selection or quality thresholds.

### No-download rule

Core CI and Core imports never download CLAP weights. The optional matrix smoke may install Python packages, import `torch`, `transformers`, `ClapModel`, and `ClapProcessor`, and verify exact package versions, but it must not call `from_pretrained`.

Real model download remains explicit/local only and uses an external cache (`SAMPLE_BRAIN_MODEL_CACHE_DIR` or an explicitly configured Hugging Face cache).

## 3. CLAP API compatibility rule

Transformers has changed the documented return contract of `ClapModel.get_text_features()` / `get_audio_features()` across releases. Sample Brain therefore treats feature output as an adapter boundary:

- direct tensor output is accepted;
- a model-output object carrying `pooler_output` is accepted;
- a non-empty tuple/list whose first element is the tensor is accepted;
- anything else fails explicitly rather than silently fabricating an embedding.

The normalized vector must remain one-dimensional `float32`; the existing worker continues to enforce the configured 512-d dimension.

## 4. Model readiness matrix

| Model | Technical status | Code/package license | Weight/model license evidence | Commercial readiness | Product selection |
|---|---|---|---|---|---|
| `laion/clap-htsat-unfused` | optional supported runtime | Transformers/PyTorch have their own package licenses | pinned model card declares `Apache-2.0`; runtime uses pinned safetensors snapshot | `READY_BY_DECLARED_LICENSE` | optional/experimental search backend; not Core-required |
| `htdemucs` | optional experimental stem backend | Demucs / wrapper code metadata is separate from weights | `UNKNOWN_UNVERIFIED` for the exact pretrained weight grant used by Sample Brain | `NOT_APPROVED` | not a commercial default |
| `htdemucs_ft` | optional experimental stem backend | Demucs / wrapper code metadata is separate from weights | `UNKNOWN_UNVERIFIED` for the exact pretrained weight grant used by Sample Brain | `NOT_APPROVED` | not a commercial default |

`READY_BY_DECLARED_LICENSE` is a Sample Brain policy classification based on the upstream-declared license, not a legal warranty. `NOT_APPROVED` means the evidence is insufficient for a commercial default; it does **not** assert that every commercial use is legally forbidden.

## 5. Demucs correction / supersession

Earlier Sample Brain documentation used the wording `RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED` and the internal label `VERIFIED_NONCOMMERCIAL` for Demucs v4 weights. #423 supersedes that legal/readiness wording.

The canonical state is now:

```text
WEIGHT_LICENSE_EVIDENCE: UNKNOWN_UNVERIFIED
COMMERCIAL_READINESS:    NOT_APPROVED
TECHNICAL_AVAILABILITY:  OPTIONAL_EXPERIMENTAL
```

The historical quality/runtime evidence for `htdemucs` versus `htdemucs_ft`, checkpoint signatures, and code-vs-weight separation remain useful. Only the over-strong commercial-license conclusion is superseded unless a primary weight-license grant is produced.

## 6. Cache/provenance compatibility

Stem provenance emitted by new writes uses the neutral `UNKNOWN_UNVERIFIED` weight-license evidence value for the known Demucs identities.

Stem cache contract v1 historically included the old license-status string inside the separation fingerprint. Correcting legal/readiness metadata must not silently invalidate otherwise identical cached separation outputs. Therefore the v1 fingerprint path keeps a narrow compatibility normalization for the two known Demucs identities only:

```text
new provenance value:       UNKNOWN_UNVERIFIED
v1 fingerprint compatibility token: RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED
```

This compatibility token is internal to the existing v1 cache identity. It is not emitted as the current commercial-readiness claim. Any real model/checkpoint/weight-hash/configuration/backend-version change still invalidates the cache as before.

## 7. Fallback policy

- Missing/broken `torch` or `transformers` must not break Core import or Core commands.
- CLAP remains opt-in; unavailable CLAP maps to the existing deterministic `EmbeddingBackendUnavailableError` path.
- CLAP runtime loading requires the pinned safetensors snapshot; no Pickle fallback is accepted by the supported loader.
- Stem separation remains opt-in and subprocess-isolated.
- A model with `commercial_ready == false` is never selected as a commercial product default solely because it is technically available.
- No model weights are committed to the repository.

## 8. Primary-source evidence used for this decision

- PyTorch `2.13.0` release on PyPI, including CPython 3.12 Windows x86-64 wheel metadata.
- Transformers `5.14.1` release on PyPI and the official Transformers CLAP model documentation.
- Hugging Face repository `laion/clap-htsat-unfused`: model metadata declares `Apache-2.0`; immutable commit `79b58ed25fc00386262a2bea4b19fd21dc4310a0` adds the official safetensors representation used by Sample Brain.
- Hugging Face and PyTorch security guidance distinguish safetensors from untrusted Pickle-backed model loading; Sample Brain therefore fails closed to safetensors for this model path.
- `audio-separator` / Demucs code-license metadata is treated only as code/package evidence and is not promoted into a weight-license grant.

## 9. Validation contract

Required evidence for this slice:

1. dependency surfaces contain the same exact CLAP package pins;
2. optional Windows/Python 3.12 smoke imports pinned `torch`, `transformers`, `ClapModel`, and `ClapProcessor` without model download;
3. Core/non-CLAP tests pass without requiring optional ML packages;
4. CLAP loader forwards the pinned safetensors revision and requires `use_safetensors=True`;
5. CLAP feature-output normalization covers tensor and pooled-output forms;
6. new Demucs provenance is `UNKNOWN_UNVERIFIED` while the v1 cache fingerprint remains backward compatible;
7. full Core pytest and normal repository security/CI gates remain green.
