# Dur/Moll (Major/Minor) Mode Analysis — V1

**Issue:** #212 — Analyzer: Dur-/Moll-Erkennung separat validieren und versionieren.
**Status:** IMPLEMENTED & VALIDATED (`feat/key-mode-analysis-v1`). The synthetic
validation gate (§6) is met normally by the third-contrast detector.

## 1. Purpose

The existing analyzer detects a tonal **root** plus a `key_conf`. Issue #212 adds a
*separate, technically evidenced* major/minor (Dur/Moll) decision that rides on the
same `chroma_mean` but never invents a mode when the evidence is weak. The two
questions stay independent:

* Root detection (`estimate_key`) and `key_conf` are **unchanged** (issues #72 etc.).
* A new `estimate_key_mode` (third-contrast detector) produces a Dur/Moll mode
  **only** when the normalized third contrast clears `MODE_CONTRAST_MIN`.

## 1.1 Status

**Implemented and validated.** The synthetic validation gate (§6) is **met**
normally by the third-contrast detector — no `xfail`, no relaxed thresholds.

## 2. Canonical representation

Single source of truth: `src/key_signature.py`.

* Stored value: `<ROOT>maj` | `<ROOT>min` | `<ROOT>` (root-only).
* Root is canonical: uppercase, **sharps** (`#`), never flats (`b`). `Db` → `C#`.
* Accepted legacy inputs: `C`, `Am`, `Amin`, `A major`, `C minor`, `Cm`.

## 3. New analyzer outputs

`Features` gains two optional fields (defaults, placed after `quality_note`):

* `key_mode: str | None` — `"maj"` | `"min"` | `None` (unresolved).
* `key_mode_evidence: dict | None` — always retained when computed, even when
  unresolved:

  ```
  {
    "kind": "third_contrast",
    "major_third_energy": <chroma energy at root + 4 semitones>,
    "minor_third_energy": <chroma energy at root + 3 semitones>,
    "contrast": <normalized ratio in [0, 1]>,
    "threshold": MODE_CONTRAST_MIN,
    "mode": "maj" | "min" | None
  }
  ```

`extract_features` writes `features.key` as the canonical string
(`<ROOT>maj` / `<ROOT>min` / `<ROOT>`). No DB migration: `features.key` is an
existing `TEXT` column.

## 3.1 Third-contrast detector

`estimate_key_mode(y, sr, *, root, chroma_mean)` uses the already-detected root as
a fixed reference. It reads the chroma energy at the **major third** (root + 4
semitones) and the **minor third** (root + 3 semitones) and computes:

```
contrast = |major_third_energy - minor_third_energy|
         / (major_third_energy + minor_third_energy + epsilon)
```

Direction: major third higher → `maj`; minor third higher → `min`; contrast below
`MODE_CONTRAST_MIN` → `None` (abstain, no invented mode). This is fully
deterministic and needs no private audio. Single notes, octaves, root+fifth, and an
equal maj/min blend all have a near-zero contrast and abstain.

## 4. Contract constants

* `KEY_ANALYSIS_CONTRACT_VERSION = 1` (`src/analyze.py`), embedded in the Track Map
  analysis provenance config and in the track-analysis cache fingerprint.
* `MODE_CONTRAST_MIN = 0.30` — frozen. Derived from the deterministic synthetic
  fixtures in `tests/audio_fixtures.py`: clear major/minor fixtures reach a contrast
  `>= ~0.916`, while ambiguous fixtures (single note, octave, root+fifth, maj/min
  blend) stay `<= ~0.056`. `0.30` sits with a wide safety margin between the two
  groups, so the synthetic validation gate passes without overfitting.

## 5. Consumers

* **FL export** (`export_fl.key_to_tag`): root-only (`C`) is **withheld** (`None`);
  only an explicit `Cmaj`/`Amin` becomes a tag. Never invents "major".
* **Search** (`search_filters.key_matches_scale`): `--scale major|minor` uses the
  parser; a root-only key matches **neither** scale. `--filter-key` stays **EXACT**
  (e.g. `--filter-key C` matches exactly `C`, never expanded to `Cmaj`/`Cmin`).
* **Asset reanalysis** (`asset_analysis`): records `key_root` (pure root only) via
  `asset_key_root()`; never stores a Dur/Moll mode, even if the analyzer emits one.
* **Track Map** (`context_analyze`): `analysis.key` carries the canonical key; when
  mode is unresolved, `analysis.mode` is omitted and `status` is `partial` with
  `reason_code = "MODE_UNRESOLVED"`. The analysis block `schema_version` is `1.1.0`.
* **Track-analysis cache** (`track_analysis_cache`): `TRACK_ANALYSIS_CACHE_CONTRACT_VERSION`
  bumped `1 → 2`; fingerprints now include `key_analysis_contract_version`.

## 6. Synthetic validation gate — MET

The contract required a frozen synthetic gate, verified by
`tests/test_key_mode_analysis.py::TestSyntheticValidationGate`:

* `root_accuracy >= 0.90`
* `mode_accuracy >= 0.90`
* `combined >= 0.85`
* `ambiguous_abstention = 1.00`

The third-contrast detector meets all four on the deterministic fixtures in
`tests/audio_fixtures.py`:

* Root detection is reliable (~100% on the 12 clear fixtures).
* Every clear fixture (6 major + 6 minor at distinct roots) commits the **correct**
  mode → `mode_accuracy = 1.00`, `combined = 1.00`.
* The ambiguous fixtures (single note, octave, root+fifth, maj/min blend) all
  produce a near-zero third contrast and abstain → `ambiguous_abstention = 1.00`.

### 6.1 Why the earlier K-S approach blocked

The original K-S cosine design compared `chroma_mean` against two Krumhansl-Schmuckler
profiles by cosine similarity, deciding on `margin = |cos(maj) - cos(min)|`. The two
profiles are intrinsically highly correlated (`cos(KS_MAJOR, KS_MINOR) ≈ 0.949`), so
the maximal achievable margin is `~0.05` — a threshold that could never let clear
fixtures commit without also making ambiguous fixtures commit. That ceiling is what
made the K-S design `BLOCKED_SYNTHETIC_VALIDATION`. The third-contrast detector
avoids it by isolating the discriminating bins (root+3 vs root+4), where clear
fixtures reach a contrast `>= ~0.916` and ambiguous fixtures stay `<= ~0.056`.

## 7. Notes

The public contract is unchanged from the K-S design: root detection and `key_conf`
are untouched, `key_mode ∈ {maj, min, None}`, `mode_evidence` remains transparent
non-probabilistic evidence, the Track Map analysis block stays `schema_version`
`1.1.0`, the DB schema is unchanged, and all consumer/cache/asset boundaries are
preserved.
