# Stem Backend Selection v1 — Default and Quality Mode

**Status:** `DONE_247_MERGED_CLOSED` — provisional selection decided; production default rejected on license grounds.
**Issue:** #247
**Parent:** #229
**Depends on:** #244, #245, #246
**Date:** 2026-08-16

---

## 1. Decision Status

```text
PRODUCTION_DEFAULT:         NO_GO
EXPERIMENTAL_CANDIDATE:     htdemucs.yaml
QUALITY_BACKEND:            NONE
WEIGHT_USAGE_STATUS:        RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED
WEIGHT_LICENSE_STATUS:      VERIFIED_NONCOMMERCIAL   (internal enum mapping; see §4)
```

> **Semantic note (technical vs production):** `htdemucs` is the evidence-backed *technical* candidate (best blind preference, fastest, fewest observed failures). It is **not** approved as a Sample Brain *production/commercial* default, because the pretrained weight license does not grant commercial use. These two statements are not contradictory.

---

## 2. Evidence Summary

| Criterion | htdemucs | htdemucs_ft |
|-----------|----------|-------------|
| Blind preference (4 private Techno tracks) | **preferred 4 / 4** | preferred 0 / 4 |
| CPU runtime (mean, ~60 s slices) | **~121 s** | ~252 s (~2.1× slower; range 1.5–3.8×) |
| Technical success | 4 / 4 runs ok | 4 / 4 runs ok |
| Notable failure | none observed | `TARGET_ABSENCE_LEAKAGE` on track_01 vocals stem |
| Exact model identity | `htdemucs.yaml`, single model sig `955717e8` | `htdemucs_ft.yaml`, bag of 4 per-source sigs (`f7e0c4bc`, `d12395a8`, `92cfc3b6`, `04573f0d`) |
| Code license | MIT (verified) | MIT (verified) |
| Weight license | **RESEARCH_ONLY / not granted for commercial** | **RESEARCH_ONLY / not granted for commercial** |
| Commercial status | **Not granted** | **Not granted** |

Source of quality/runtime/robustness evidence: `docs/STEM_MODEL_BENCHMARK_V1.md` (#246).
Source of weight-license evidence: `facebookresearch/demucs` issue **#327** (model author adefossez, explicit weight-specific statement).

---

## 3. Default Decision — REJECTED

**Selected: NO.** No production/commercial default backend is approved.

**Reason:**
1. The decisive production gate is the **weight license**, not quality or speed.
2. Both candidate weight sets are released *"only for scientific purposes"* and are *not covered by the Demucs MIT license* (upstream owner statement, demucs #327). Commercial use is therefore **not granted**.
3. `htdemucs` remains the recommended **experimental/non-commercial** candidate because it wins on all three non-license dimensions: 4/4 blind preference, ~2.1× faster on CPU, and no observed leakage failure (`htdemucs_ft` showed `TARGET_ABSENCE_LEAKAGE`).

---

## 4. Quality Decision — REJECTED

**Selected: NO.** No quality tier is approved.

**Reason:**
- A quality tier is only justified if it offers a meaningful quality benefit worth extra runtime.
- #246 shows the opposite for `htdemucs_ft`: it was **preferred 0/4**, is **~2.1× slower**, and exhibited a specific leakage failure.
- Therefore `htdemucs_ft` must **not** become a quality mode merely because its name contains `ft`. Quality backend = `NONE`.

> The internal contract enum (`docs/STEM_MANIFEST_V1.md` §6) only allows `VERIFIED_PERMISSIVE`, `VERIFIED_NONCOMMERCIAL`, `UNKNOWN_UNVERIFIED`. We map the finding to **`VERIFIED_NONCOMMERCIAL`** internally. This is a conservative production-policy label only — it does **not** assert a specific `CC-BY-NC` license. Per upstream, no authoritative source explicitly assigns a named license (e.g. CC-BY-NC) to these weights; the only explicit statement is that they are *not MIT* and are *provided only for scientific purposes*. We record `WEIGHT_USAGE_STATUS = RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED` as the accurate primary wording.

---

## 5. License Boundary

- **MIT covers the code**, not the weights. `python-audio-separator` (wrapper) and `demucs` (architecture) are MIT. A code license does **not** grant a license to the pretrained model weights.
- **Weights are released only for scientific purposes** (demucs #327, model owner adefossez):
  > *"The model weights are not covered by the MIT license, and are provided only for scientific purposes."*
- This statement is authoritative: it comes from the model owner, not a third party. It applies to all Demucs v4 pretrained weights, i.e. both `htdemucs` and `htdemucs_ft`.

### Conflicting published metadata (Hugging Face)

The official Hugging Face model cards `adefossez/HTDemucs` and `adefossez/HTDemucs-ft` currently display `license: mit`. Sample Brain records this as **conflicting published metadata**. We do **not** speculate on why the card shows `mit` (e.g. we do not assert it is an automatic Hugging Face default). We simply note the conflict and explain the conservative policy:

> Sample Brain follows the **model author's explicit weight-specific statement** (demucs #327) for production approval, because code-license metadata (`MIT`) is not a grant over the weights. Until the model owner publishes an explicit permissive/commercial weight license, the weights remain RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED.

---

## 6. Exact Model Identity (Corrected)

Both candidates are Demucs v4 family, invoked via `python-audio-separator` 0.44.5. Exact released identities from the authoritative Demucs model zoo:

| Model | Config / name | Released model signature | Composition |
|-------|---------------|--------------------------|-------------|
| htdemucs | `htdemucs.yaml` | `955717e8` | single model |
| htdemucs_ft | `htdemucs_ft.yaml` | `f7e0c4bc`, `d12395a8`, `92cfc3b6`, `04573f0d` | bag of four fine-tuned per-source models (outputs averaged) |

- `htdemucs` weights: representative signature `955717e8` (single checkpoint).
- `htdemucs_ft` weights: **bag of four** per-source fine-tuned checkpoints; the four short signatures above are the authoritative identifiers. No full SHA-256 hash is asserted here unless verified from the actual weight files.

### Provenance correction (retracts a #246 mislabel)

`docs/STEM_MODEL_BENCHMARK_V1.md` (#246) recorded the long string
`f7e0c4bcba3fe64a92cfc3b6ef3bcb9c04573f0d` as a *"representative weight hash"* for **htdemucs**. That mapping is **wrong** and is corrected in this slice:

- `f7e0c4bc…` is **not** the htdemucs weight hash. The correct htdemucs signature is `955717e8`.
- The four short signatures `f7e0c4bc`, `d12395a8`, `92cfc3b6`, `04573f0d` belong to the **htdemucs_ft** bag. The #246 long string is a concatenation/artifact of those source signatures and must not be propagated as an htdemucs identity.
- `tools/stem_separator_spike.py` still hardcodes the same debunked long string as a placeholder `weight_hash` (line ~99). That spike placeholder is **not** authoritative provenance and must be reconciled to the per-model signatures in a follow-up (out of scope for #247; the spike is an isolated study, not wired into production).

---

## 7. Provisional Status

- Pilot scope: **4 private Techno tracks / 60 s excerpts**. No universal superiority claim.
- All findings are provisional with respect to:
  - the small, genre-specific, private sample,
  - the unresolved weight license (research-only),
  - the absent `htdemucs_ft` exact weight hash in #246 (provenance gap, not fabricated here).

---

## 8. What Can Proceed Next

**#248 (stem cache / model provenance):** May build a model-agnostic cache and provenance layer. It **must** preserve the weight-license status explicitly on every cached artifact (no silent upgrade to "approved"). The `NO_GO` production default does not block #248 infrastructure work.

**#249 (optional stem pipeline integration):** Must remain **experimental / opt-in**. It must **not** silently make an unapproved model the production default. If wired, it should reference `htdemucs.yaml` only as an experimental, non-commercial candidate and surface the license boundary to the user.

**#268 (producer groups):** Uses the technical stems produced here; the quality finding (no quality tier) is independent of producer-group definition.

---

## 9. Acceptance Criteria (#247)

- [x] Default backend + exact checkpoint selected OR explicitly rejected → **rejected (NO_GO)**, `htdemucs.yaml` named as experimental candidate
- [x] Quality backend + exact checkpoint selected OR explicitly rejected → **rejected (NONE)**
- [x] Quality reasoning documented (§4)
- [x] Runtime reasoning documented (§2, §3)
- [x] Robustness reasoning documented (§2, §3 — `htdemucs_ft` leakage)
- [x] Code license documented separately from weight license (§5)
- [x] Weight license documented separately (§4, §5)
- [x] Decision marked provisional where evidence is limited (§7)
- [x] #244 adapter remains model-independent (no schema change; selection names a candidate only)
- [x] No new hearing required (#246 evidence reused)
- [x] No private artifacts committed (docs only)

---

## 10. Final Verdict

```text
PRODUCTION_DEFAULT:        NO_GO
EXPERIMENTAL_CANDIDATE:    htdemucs.yaml
QUALITY_BACKEND:           NONE
WEIGHT_USAGE_STATUS:       RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED
WEIGHT_LICENSE_STATUS:     VERIFIED_NONCOMMERCIAL (internal enum; no CC-BY-NC asserted)

HTDEMUCS_CHECKPOINT:       htdemucs.yaml  (sig 955717e8, single model)
HTDEMUCS_WEIGHT_LICENSE:   RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED

HTDEMUCS_FT_CHECKPOINT:    htdemucs_ft.yaml  (bag: f7e0c4bc, d12395a8, 92cfc3b6, 04573f0d)
HTDEMUCS_FT_WEIGHT_LICENSE: RESEARCH_ONLY / COMMERCIAL_USE_NOT_GRANTED

QUALITY_EVIDENCE:   htdemucs preferred 4/4; htdemucs_ft 0/4; htdemucs_ft TARGET_ABSENCE_LEAKAGE
RUNTIME_EVIDENCE:    htdemucs ~121 s mean; htdemucs_ft ~252 s mean (~2.1x slower)
ROBUSTNESS_EVIDENCE: 8/8 technical runs ok; both produce drums/bass/vocals/other

PRIVATE_AUDIO_ADDED: NO
WEIGHTS_ADDED:       NO
ADAPTER_244_CHANGED: NO
BLOCKERS:           NONE
```
