# Key Confidence Threshold Evidence

Evidence for [Issue #72](https://github.com/jannekbuengener/sample-brain/issues/72): `key_conf` value distribution on synthetic fixtures and validation of the FL export threshold (`CONF_KEY_MIN = 0.55`).

Related spec: [`docs/product/01_LIBRARY_INTELLIGENCE_SPEC.md`](../product/01_LIBRARY_INTELLIGENCE_SPEC.md) §6.1.

## Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-07-07 |
| Branch | `main` |
| Commit | `6f77176` (base at evidence capture) |
| OS | Windows 11 (10.0.26200) |
| Python | 3.12 |
| numpy | 2.4.6 (pinned in `requirements.txt`) |
| librosa | 0.11.x (via project venv) |
| Fixture set | 17 synthetic WAVs (12 sine tones, 2 triads, pulse, kick, noise) |
| Harness command | `python -m src.cli benchmark key-conf-evidence --work-dir %TEMP%\sample-brain-key-conf-evidence` |
| Export threshold | `CONF_KEY_MIN = 0.55` in `src/export_fl.py` |

## Analyzer scale (current code)

`src/analyze.py` sets `key_conf` as normalised chroma peak prominence:

```
key_conf = max(chroma_mean) / sum(chroma_mean)
```

- **Theoretical range:** ~`0.083` (uniform 12-bin chroma) to `1.0` (single pitch class dominates).
- **Not a calibrated probability** — a relative prominence score only.

### Historical scale (pre-`3ca2a17`)

Initial import used Krumhansl-Schmuckler template correlation divided by `sum(chroma_mean)`. That formula could yield values **well above 1.0** (observed ~3.7–5.4 in legacy notes). Existing catalogs analyzed before the repair may still contain legacy-scale values until re-analyzed.

## Fixture description

| Variant | Generator | Signal |
|---------|-----------|--------|
| sine | `write_sine_wav` | 2 s mono sine at each semitone frequency (12 notes) |
| chord | `_write_chord_wav` | 2 s major triad (root + 5th + 4th partial stack) |
| pulse | `write_pulse_train_wav` | 4 s rhythmic clicks at 120 BPM |
| kick | `write_kick_transient_wav` | 4 s low-frequency kick transients at 128 BPM |
| noise | `_write_noise_wav` | 2 s Gaussian noise (seed 42) |

No private audio committed. Work directory outside the repo.

## Per-fixture results

| fixture | variant | key | key_conf | export | tag |
|---------|---------|-----|----------|--------|-----|
| sine_C | sine | C | 0.8770 | yes | Cmaj |
| sine_C# | sine | C# | 0.8883 | yes | C# |
| sine_D | sine | D | 0.8830 | yes | Dmaj |
| sine_D# | sine | D# | 0.8853 | yes | D# |
| sine_E | sine | E | 0.8685 | yes | Emaj |
| sine_F | sine | F | 0.8698 | yes | Fmaj |
| sine_F# | sine | F# | 0.8770 | yes | F# |
| sine_G | sine | G | 0.8808 | yes | Gmaj |
| sine_G# | sine | G# | 0.8818 | yes | G# |
| sine_A | sine | A | 0.8892 | yes | Amaj |
| sine_A# | sine | A# | 0.9179 | yes | A# |
| sine_B | sine | B | 0.9288 | yes | Bmaj |
| chord_C | chord | C | 0.3337 | no | — |
| chord_A | chord | A | 0.3357 | no | — |
| pulse_120 | pulse | C# | 0.0983 | no | — |
| kick_128 | kick | A# | 0.1380 | no | — |
| noise | noise | A# | 0.0865 | no | — |

## Aggregate metrics

| Metric | Value |
|--------|-------|
| total fixtures | 17 |
| with key_conf | 17 |
| min / median / max | 0.0865 / 0.8770 / 0.9288 |
| bucket `< 0.40` | 5 (29.4%) |
| bucket `0.40 – 0.55` | 0 (0.0%) |
| bucket `0.55 – 0.70` | 0 (0.0%) |
| bucket `≥ 0.70` | 12 (70.6%) |
| export rate @ 0.55 | 70.6% (12/17) |

### Histogram (ASCII)

```
<0.40      |#####                              5
0.40-0.55  |                                    0
0.55-0.70  |                                    0
>=0.70     |############                       12
             0    2    4    6    8   10   12
```

## Proposed threshold buckets (0–1 scale)

| Bucket | Range | Export policy (proposed) | Rationale |
|--------|-------|--------------------------|-----------|
| withhold | `< 0.40` | No FL key tag | Polyphonic, percussive, or ambiguous chroma on fixtures |
| low | `0.40 – 0.55` | No tag (current gate) | Borderline prominence — avoid over-tagging |
| medium | `0.55 – 0.70` | Tag with optional “low confidence” UI hint (plugin target) | Acceptable for export fallback |
| high | `≥ 0.70` | Tag normally | Clear tonal dominance on synthetic sines |

**Current shipped behavior:** binary gate at `0.55` only (no low-confidence tier in FL tag file).

## Export decision rules (documented)

| Condition | `key_to_tag` result | Notes |
|-----------|---------------------|-------|
| `key` missing | no tag | — |
| `key_conf` is `NULL` | no tag | Fixed in export slice — previously exported anyway |
| `key_conf < 0.55` | no tag | `CONF_KEY_MIN` hardcoded |
| `key_conf ≥ 0.55` | tag emitted | Normalised to `Cmaj` / `Amin` / `C#` style |
| Legacy DB `key_conf ~ 3.7–5.4` | always passes 0.55 gate | Re-analyze required after analyzer scale change |

## Cross-consumer threshold alignment

| Consumer | Location | Threshold | Expected scale | Aligned with current analyzer? |
|----------|----------|-----------|----------------|--------------------------------|
| FL export | `src/export_fl.py` | `0.55` | 0–1 peak/sum | **Yes** |
| Library spec | `docs/product/01_LIBRARY_INTELLIGENCE_SPEC.md` §6.1 | documents `0.55` | 0–1 | **Yes** |
| Genre profiles | `profiles/*.yaml` `require_confidence` | 1.5 – 3.0 | Legacy Krumhansl | **No** |
| Title pipeline | `tools/title_pipeline.py` | default `2.5` | Legacy | **No** |
| Validation report | `tools/validate_report.py` | low if `< 2.0` | Legacy | **No** |
| PROJECT_META risk note | `knowledge/project/PROJECT_META.md` | cites ~3.7–5.4 | Legacy observation | **Stale** (see below) |

### Legacy-scale impact

If a catalog still holds pre-`3ca2a17` `key_conf` values (~3.7–5.4), the export threshold `0.55` is **effectively disabled** — every row with a non-null key gets a key tag. After re-analyze with the current formula, the same threshold becomes **strict** — polyphonic/percussive material tends to fall below 0.55.

## Recommendation

**Keep `CONF_KEY_MIN = 0.55` on the current 0–1 analyzer scale** until real-library evidence suggests otherwise.

Synthetic fixtures show a **bimodal** split:

- Pure tones: ~0.87–0.93 → exported
- Chords / pulse / kick / noise: ~0.09–0.34 → withheld

The threshold separates these groups cleanly on the fixture set (no samples in the 0.40–0.70 band). This supports conservative FL export: do not tag keys for ambiguous chroma.

### Follow-up fix slice (separate GO)

| Priority | Item | Status |
|----------|------|--------|
| P0 | Unit tests for `key_to_tag` / evidence harness | Done (`tests/test_key_conf_evidence.py`) |
| P0 | NULL `key_conf` must not export key tag | Done (`src/export_fl.py`) |
| P1 | Expose `export.key_conf_min` via profile config | Open |
| P1 | Re-calibrate after private-library histogram (opt-in, local) | Open |
| P2 | Migrate `profiles/*.yaml` `require_confidence` to 0–1 scale | Open |
| P2 | Update `tools/validate_report.py` / `title_pipeline.py` thresholds | Open |
| P2 | Re-analyze legacy catalogs or document migration note | Open |

## Commands

```powershell
.\.venv\Scripts\python.exe -m pip install "numpy==2.4.6"
.\.venv\Scripts\python.exe -m src.cli benchmark key-conf-evidence --work-dir $env:TEMP\sample-brain-key-conf-evidence
.\.venv\Scripts\python.exe -m pytest -q tests/test_key_conf_evidence.py
```

## References

- Issue #72 — eval: calibrate key confidence thresholds for FL export
- `src/analyze.py` — `estimate_key()`
- `src/export_fl.py` — `CONF_KEY_MIN`, `key_to_tag()`
- `src/key_conf_evidence.py` — reproducible harness
- Git history: `b80856a` (Krumhansl scale) → `3ca2a17` (peak/sum scale)
