# Stem Backend Selection v1 — Default and Quality Mode

**Status:** `DONE_247_MERGED_CLOSED` — technical selection evidence retained; license/readiness wording corrected by #423.  
**Issue:** #247  
**Readiness clarification:** #423 / `docs/MODEL_READINESS_V1.md`  
**Date:** 2026-08-16; readiness clarification 2026-08-18

## 1. Current decision

```text
PRODUCTION_DEFAULT:         NO_GO
EXPERIMENTAL_CANDIDATE:     htdemucs.yaml
QUALITY_BACKEND:            NONE
WEIGHT_LICENSE_EVIDENCE:    UNKNOWN_UNVERIFIED
COMMERCIAL_READINESS:       NOT_APPROVED
```

`htdemucs` remains the evidence-backed **technical** candidate from #246/#247. It is not approved as a commercial product default because Sample Brain does not currently have sufficient primary-source evidence for the exact pretrained-weight commercial grant. `NOT_APPROVED` is a product-policy state, not a claim that every commercial use is legally prohibited.

This wording supersedes the earlier `RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED` and `VERIFIED_NONCOMMERCIAL` labels. Those historical strings may still exist only as a stem-cache-v1 fingerprint compatibility token; they are no longer the current license/readiness claim.

## 2. Technical evidence retained from #246/#247

| Criterion | htdemucs | htdemucs_ft |
|---|---|---|
| Blind preference (4 private Techno tracks) | **preferred 4 / 4** | preferred 0 / 4 |
| CPU runtime (mean, ~60 s slices) | **~121 s** | ~252 s (~2.1× slower) |
| Technical success | 4 / 4 runs ok | 4 / 4 runs ok |
| Notable observed failure | none in pilot | `TARGET_ABSENCE_LEAKAGE` on one vocals stem |
| Released identity | `htdemucs.yaml`, sig `955717e8` | `htdemucs_ft.yaml`, bag `f7e0c4bc,d12395a8,92cfc3b6,04573f0d` |
| Code/package evidence | MIT code metadata | MIT code metadata |
| Exact weight-license evidence used for commercial approval | `UNKNOWN_UNVERIFIED` | `UNKNOWN_UNVERIFIED` |
| Commercial default | not approved | not approved |

The pilot is small and genre-specific. It proves only the observed technical preference/runtime/robustness results for those runs.

## 3. Default decision

No production/commercial default stem backend is approved.

Reasons:

1. technical quality and commercial readiness are separate gates;
2. `htdemucs` won the limited technical pilot, but the exact pretrained-weight commercial grant has not been verified to Sample Brain's required standard;
3. `htdemucs_ft` offered no quality benefit in the pilot and was slower, so there is no separate quality tier regardless of licensing;
4. code/package license metadata is not promoted into a weight-license grant.

`htdemucs` therefore remains optional/experimental only.

## 4. Code versus weight boundary

Sample Brain records code/package metadata and model-weight evidence separately.

- Demucs / wrapper code metadata can be MIT without proving the legal status of separately distributed pretrained weights.
- Hugging Face or package metadata is evidence only for the artifact to which it actually applies.
- Where primary sources conflict or do not establish the exact commercial weight grant, Sample Brain records `UNKNOWN_UNVERIFIED` and fails closed for product-default approval.
- A future primary-source permissive/commercial weight grant may upgrade readiness without changing the technical benchmark result.

This is a conservative product policy, not legal advice or a fabricated named license.

## 5. Exact model identity

| Model | Config / name | Released model signature | Composition |
|---|---|---|---|
| htdemucs | `htdemucs.yaml` | `955717e8` | single model |
| htdemucs_ft | `htdemucs_ft.yaml` | `f7e0c4bc`, `d12395a8`, `92cfc3b6`, `04573f0d` | bag of four fine-tuned per-source models |

These released signatures are checkpoint identifiers, not asserted full cryptographic hashes of locally loaded weight files. Real cache reuse still requires the actual weight-file/set hash recorded by the #248 provenance contract.

### Provenance correction retained from #247

The historical long string `f7e0c4bcba3fe64a92cfc3b6ef3bcb9c04573f0d` is not an htdemucs weight hash. `955717e8` is the htdemucs released signature; the four short signatures belong to the `htdemucs_ft` bag. No downstream provenance should treat the concatenated long value as authoritative.

## 6. Cache compatibility after #423

New known-Demucs provenance emits:

```text
weight_license = UNKNOWN_UNVERIFIED
```

Stem cache v1 historically included the previous license-status label in its fingerprint even though that label does not change audio output. #423 therefore preserves the old token **only inside the v1 fingerprint compatibility path** for `htdemucs` and `htdemucs_ft`. This prevents a metadata clarification from forcing unnecessary re-separation while new manifests/cache entries expose the corrected neutral evidence state.

Model/checkpoint/weight-hash/backend/configuration changes still invalidate the cache normally.

## 7. What can proceed

- Stem cache/provenance infrastructure may continue model-independently.
- Stem separation remains explicit opt-in/experimental.
- No unverified-weight model becomes a commercial default merely because it is technically available.
- No model weights belong in the repository.
- Any future commercial-readiness upgrade requires exact primary-source evidence for the actual weights/checkpoint.

## 8. Final verdict

```text
PRODUCTION_DEFAULT:          NO_GO
EXPERIMENTAL_CANDIDATE:      htdemucs.yaml
QUALITY_BACKEND:             NONE
WEIGHT_LICENSE_EVIDENCE:     UNKNOWN_UNVERIFIED
COMMERCIAL_READINESS:        NOT_APPROVED

HTDEMUCS_CHECKPOINT:         htdemucs.yaml (sig 955717e8)
HTDEMUCS_FT_CHECKPOINTS:     f7e0c4bc,d12395a8,92cfc3b6,04573f0d

QUALITY_EVIDENCE:            htdemucs preferred 4/4; htdemucs_ft 0/4
RUNTIME_EVIDENCE:            htdemucs ~121 s; htdemucs_ft ~252 s
ROBUSTNESS_EVIDENCE:         8/8 technical runs completed; one observed htdemucs_ft leakage case
PRIVATE_AUDIO_ADDED:         NO
WEIGHTS_ADDED:               NO
```
