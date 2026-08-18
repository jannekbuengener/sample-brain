# Dur/Moll (Major/Minor) Mode Analysis — V1

**Issues:** #212, #418
**Status:** IMPLEMENTED & VALIDATED

## 1. Purpose

The analyzer answers two separate questions and keeps their evidence distinct:

1. **Root detection** (`estimate_key`) computes mean CQT chroma and selects the
   strongest pitch class with `argmax(chroma_mean)`. `key_conf` is the normalized
   peak prominence `max(chroma_mean) / sum(chroma_mean)`.
2. **Mode detection** (`estimate_key_mode`) compares the major-third and
   minor-third chroma energy relative to the selected root.

`key_conf` and mode contrast are relative deterministic evidence. Neither is a
calibrated probability or a generic confidence score.

## 2. Canonical representation

Single source of truth: `src/key_signature.py`.

- Stored key: `<ROOT>maj` | `<ROOT>min` | `<ROOT>` (root-only).
- Root is canonical uppercase with sharps (`#`), never flats (`b`). `Db` → `C#`.
- Accepted legacy inputs include `C`, `Am`, `Amin`, `A major`, `C minor`, `Cm`.

## 3. Analyzer outputs and durable evidence

`Features` carries:

- `key_mode: str | None` — `"maj"` | `"min"` | `None` (unresolved)
- `key_mode_evidence: dict | None`
- `quality_note: str | None`

Mode evidence is retained when computed even if the detector abstains:

```json
{
  "kind": "third_contrast",
  "major_third_energy": 0.0,
  "minor_third_energy": 0.0,
  "contrast": 0.0,
  "threshold": 0.3,
  "mode": null
}
```

`run_analyze()` persists this evidence in the `features` table:

- `quality_note TEXT NULL`
- `key_mode TEXT NULL`
- `key_mode_evidence TEXT NULL` containing deterministic JSON

The migration is additive and backward-compatible. `init_db()` adds missing
nullable columns to older databases. Existing rows are not rewritten and no
historical evidence is invented.

`features.key` remains the canonical root/mode string (`<ROOT>maj` /
`<ROOT>min` / `<ROOT>`).

## 4. Third-contrast detector

`estimate_key_mode(y, sr, *, root, chroma_mean)` uses the already-selected root as
a fixed reference. It reads the chroma energy at the **major third** (root + 4
semitones) and the **minor third** (root + 3 semitones):

```text
contrast = |major_third_energy - minor_third_energy|
         / (major_third_energy + minor_third_energy + epsilon)
```

Direction:

- major third higher → `maj`
- minor third higher → `min`
- contrast below `MODE_CONTRAST_MIN` → `None` (abstain)

Single notes, octaves, root+fifth, and equal major/minor blends are deliberately
ambiguous and must abstain rather than invent a mode.

## 5. Contract constants

- `KEY_ANALYSIS_CONTRACT_VERSION = 1`
- `MODE_CONTRAST_MIN = 0.30`

The mode threshold is frozen against deterministic synthetic fixtures. Clear
major/minor fixtures are well above the threshold while ambiguous fixtures remain
well below it.

## 6. Consumers

- **FL export** (`export_fl.key_to_tag`): root-only values are withheld; only an
  explicit major/minor key becomes a scale tag.
- **Search** (`search_filters.key_matches_scale`): root-only keys match neither
  major nor minor scale filtering.
- **Asset reanalysis** (`asset_analysis`): stores pure `key_root`, never mode.
- **Track Map** (`context_analyze`): retains mode evidence when unresolved and
  reports `MODE_UNRESOLVED` rather than inventing a mode.
- **Track-analysis cache**: fingerprint includes the key-analysis contract version.
- **SQLite features**: #418 persists `quality_note`, `key_mode`, and
  `key_mode_evidence` so normal `run_analyze()` no longer drops uncertainty data.

## 7. Synthetic validation baseline

`tests/test_key_mode_analysis.py` freezes the pre-algorithm-change quality gate:

- clear-root accuracy >= 0.90
- clear-mode accuracy >= 0.90
- combined root+mode accuracy >= 0.85
- ambiguous abstention = 1.00

The clear set contains six roots in both major and minor; the ambiguous set covers
single note, octave, root+fifth, and an equal major/minor blend.

Issue #418 adds a synthetic **bass-dominant** case with a much stronger low C2 than
its upper C-major triad. The frozen expected root remains `C`.

Canonical baseline/evidence report:
`docs/validation/ISSUE_418_KEY_BASELINE.md`.

No private tracks are used or committed.

## 8. Why the earlier Krumhansl-Schmuckler mode design was rejected

An earlier design compared `chroma_mean` against major/minor
Krumhansl-Schmuckler profiles by cosine similarity. Those profiles are highly
correlated, so the attainable margin was too small to separate clear and
ambiguous synthetic fixtures reliably. The shipped mode detector therefore uses
third contrast instead.

This historical K-S experiment must not be confused with the current root
algorithm: **the current root detector is strongest mean chroma pitch class, not a
Krumhansl profile matcher.**

## 9. Future algorithm changes

Any proposal to replace the current deterministic root/mode logic must first
compare against the frozen #418 baseline and report at least:

- `wrong_root`
- `wrong_mode`
- `abstain_or_unknown`

A change is not justified by a new method name alone; it needs measured improvement
without weakening abstention semantics or inventing probability-like confidence.
