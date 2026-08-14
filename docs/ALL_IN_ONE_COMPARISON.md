# All-In-One Structure Analyzer — Comparison Evaluation

**Issue:** [#235](https://github.com/jannekbuengener/sample-brain/issues/235)
**Parent:** [#227](https://github.com/jannekbuengener/sample-brain/issues/227)
**Comparison baseline:** [#236](https://github.com/jannekbuengener/sample-brain/issues/236) BeatGrid, [#265](https://github.com/jannekbuengener/sample-brain/issues/265) StructureV1, [#240](https://github.com/jannekbuengener/sample-brain/issues/240) ArrangementClassifier, [#233](https://github.com/jannekbuengener/sample-brain/issues/233) Context Analyze.

## Scope of #235 (live)

`mir-aidj/all-in-one` (`allin1`, Kim & Nam, WASPAA 2023, arXiv:2307.16425) is to be
evaluated as an **isolated, optional comparison** against the Sample-Brain core that is
built from BeatGrid (#236) and StructureV1 (#265). It must never become a core backend, a
core dependency, or a source of authoritative Techno labels. The issue outcome is to be
recorded as one of `EXPERIMENTAL_ADDON`, `COMPARISON_ONLY`, or `NO_GO`.

## Subject facts (from public `mir-aidj/all-in-one` README / PyPI, MIT license)

`allin1` predicts, in one neural pass:

1. Tempo (BPM)
2. Beats
3. Downbeats
4. Functional segment boundaries
5. Functional segment labels (`start`, `end`, `intro`, `outro`, `break`, `bridge`,
   `inst`, `solo`, `verse`, `chorus`)

Key implementation characteristics observed from the public package:

- **Internal Demucs source separation** is core: the model consumes four stems
  (bass, drums, other, vocals) and the README states audio is read through Demucs.
- **Ensemble of 8 models** (`harmonix-all`); frame resolution 100 FPS.
- **Dependency cost:** PyTorch + NATTEN + Demucs + Hugging Face model/checkpoint
  downloads. README states NATTEN must be **built from source on Windows**
  (`git clone SHI-Labs/NATTEN && make`), while macOS auto-installs and Linux downloads
  a wheel.
- **License:** MIT (permissive) — no license blocker.
- **Offline:** not offline-by-default; Demucs and the checkpoints are fetched on demand.
- **Determinism:** GPU neural ensemble; no determinism guarantee across hardware.

## Empirical side-by-side run — blocked, no fabrication

The acceptance criterion "mehrere eigene Techno-Tracks außerhalb des Repos verglichen"
requires the author's **private Techno tracks**. Those are unavailable to this agent and
must not be used (privacy policy: no private audio). Without identical source material the
quantitative BPM/beat/downbeat/boundary/label error comparison against #236/#265 cannot be
performed honestly.

Installing `allin1` to run on synthetic/public fixtures was deliberately **not** done,
because it would add the heavy optional dependency stack (PyTorch, NATTEN Windows source
build, Demucs, HF downloads) that #235 itself forbids as a core path, and the repo policy
forbids adding dependencies/model downloads unless the live contract explicitly requires
it. The decision below is therefore reached from (a) the public architecture/dependency/
license facts of `allin1` and (b) the verified functional modular baseline in this repo.

**Blocker classification:** empirical quantitative comparison is *blocked* (private tracks
unavailable + privacy policy). A decisive evaluation is still *possible* from existing
public evidence plus the verified baseline. No green result is fabricated.

## Baseline verified functional (evidence)

```text
pytest tests/test_beat_grid.py tests/test_structure_v1.py \
       tests/test_context_analyze.py tests/test_cli_context_analyze.py
29 passed
```

The comparison target is real and green:

- #236 BeatGrid (`src/beat_grid.py`) emits BPM/beats/downbeats on `AudioTimebase`,
  `beat_this/final0` primary with a lightweight `librosa` fallback, provenance per
  backend, fail-soft status (`ok`/`partial`/`no_result`/`failed`).
- #265 StructureV1 (`src/structure_v1.py`) emits **neutral, bar-synchronous** boundaries
  only — no functional labels — deterministically from bar features + self-similarity /
  recurrence / novelty.
- #240 ArrangementClassifier maps neutral signals to Techno roles heuristically,
  keeping `unknown` valid.
- #233 Context Analyze (`src/context_analyze.py`) gives a DB-free, portable, deterministic
  Track Map `1.0.0` for arbitrary local WAV/FLAC.

## Fair comparison against the live modular baseline

| Dimension | `mir-aidj/all-in-one` | Sample-Brain baseline (#236/#265/#240) |
|-----------|-----------------------|----------------------------------------|
| BPM / beats / downbeats | Yes (single neural pass) | Yes (`beat_this` + `librosa` fallback) |
| Segment boundaries | Functional boundaries | Neutral, bar-synchronous (deliberate) |
| Functional labels | Emits `verse`/`chorus`/… | Deliberately **not** authoritative Techno truth |
| Determinism | GPU ensemble, not guaranteed | Deterministic (librosa / numpy, no heavy model) |
| Offline | Needs Demucs + HF checkpoints | Offline by design; optional `beat_this` degrades to `librosa` |
| Provenance | Monolithic model | Per-backend provenance, explicit fallback reason |
| Error / fallback | Single model, no graceful degradation | Status-based `partial`/`no_result`/`failed` |
| Dependency cost | PyTorch + NATTEN (Win: source build) + Demucs | librosa only; optional `beat_this` stays optional |
| Windows fit | NATTEN must be compiled from source | Pure-Python / librosa, no native build |
| Maintainability | External opaque model, 8-model ensemble | In-repo, auditable, separable slices |
| Track Map v1 fit | Different label ontology | Directly wired to Track Map `1.0.0` |

## Boundary / label error expectation (architectural, not measured)

`allin1` labels use a generic popular-music ontology (`verse`/`chorus`/`bridge`/…) trained
on Harmonix-style data. Electronic/Techno arrangements routinely deviate from that ontology
(intro→build→drop→breakdown loops, no verse/chorus), so boundary and especially label errors
on Techno are expected to be systematic, not occasional. The repo encodes this exact
distrust in #227/#228/#265: functional labels are "höchstens Vergleichsdaten, keine
Techno-Wahrheit". Adopting `allin1` output as role truth would regress the design intent.

## Decision

**Result: `COMPARISON_ONLY`** — `mir-aidj/all-in-one` remains an external comparison
reference, explicitly outside the core path. This resolves to **`NO_GO` for any repository
integration**: no optional backend, no dependency, no label adoption.

Rationale (evidence-based, concrete):

- The only unique output `allin1` adds — functional segment labels — is the one output the
  repo deliberately treats as non-authoritative for Techno (#227/#228/#265).
- The dependency/offline/determinism/Windows costs are high (PyTorch + NATTEN Windows
  source build + Demucs + HF downloads) and are not justified by a proven benefit over the
  verified, offline, deterministic modular baseline.
- The baseline already covers BPM/beats/downbeats (#236) and neutral sections (#265) with
  per-backend provenance and graceful fallback.

`allin1` may be re-evaluated later **only** if an explicitly enabled experimental addon is
requested and the private-pilot track set is made available under the privacy policy.

## Acceptance criteria mapping

- [x] Ansätze untersucht (public `allin1` architecture/dependency/license vs live baseline)
- [x] Nutzen gegenüber #236/#265 getrennt bewertet (table + rationale)
- [x] Installations-, Dependency- und Lizenzrisiken dokumentiert (PyTorch/NATTEN/Demucs/HF; MIT ok)
- [x] All-In-One bleibt optional und außerhalb des Core-Pfads (`COMPARISON_ONLY` / `NO_GO`)
- [ ] mehrere eigene Techno-Tracks verglichen — **blocked**: private tracks unavailable + privacy policy; not fabricated
- [ ] Boundary-/Label-Fehler mit konkreten Beispielen — **blocked empirically**; architectural expectation documented above

## Non-goals

- No `allin1` backend, dependency, runtime, or CLI added to Sample-Brain.
- No functional labels adopted as `drop`/`build`/Techno truth.
- No reuse of internal Demucs intermediates.
- No private tracks, model caches, or audio committed to the repo.
