# Search Quality Benchmark Evidence

Measured Tier-A gate results for [ADR-0005](../adr/ADR-0005-search-quality-evaluation.md). This campaign measures **ranking relevance** (P@K, R@K), not sqlite-vec latency or backend parity.

## Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-05-31 |
| Branch | `feat/search-quality-campaign` |
| Commit | `da8c3fe` (base `main` + campaign work) |
| OS | Windows 11 (10.0.26200) |
| Python | 3.12.10 (64-bit) |
| Suite | `tests/fixtures/search_quality/golden_v1.yaml` |
| Tier | A (deterministic 8-d vectors, NumPy backend) |
| Catalog size | 9 synthetic samples (3 clusters × 3) |
| Query count | 9 (vector, filter, hybrid) |
| Harness wall time | ~3 s (CLI + temp DB under `%TEMP%`) |

## Commands

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_search_quality.py -m "not clap"
.\.venv\Scripts\python.exe -m src.cli benchmark search-quality --work-dir $env:TEMP\sample-brain-quality
```

Work directory was outside the repo (`%TEMP%\sample-brain-quality`); no `.db` files were committed.

## Aggregate results (Tier A)

| Metric | Measured | Threshold | Verdict |
|--------|----------|-----------|---------|
| Mean P@1 | 1.000 | ≥ 0.60 | **PASS** |
| Mean P@5 | 0.600 | ≥ 0.50 | **PASS** |
| Mean R@10 | 1.000 | ≥ 0.80 | **PASS** |
| MRR | 1.000 | (informative) | — |
| Must-recall queries | 9/9 | all PASS | **PASS** |
| Filter compliance | 9/9 @ 1.000 | 100% | **PASS** |

Full harness stdout:

```
suite=...\golden_v1.yaml tier=A queries=9
mean_precision_at_1=1.000 mean_precision_at_5=0.600 mean_recall_at_10=1.000 mrr=1.000
gate_mean_precision_at_1=PASS
gate_mean_precision_at_5=PASS
gate_mean_recall_at_10=PASS
gate_must_recall_queries=PASS
gate_filter_compliance=PASS
query=kick_cluster p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=snare_cluster p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=pad_cluster p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=kick_pred_type_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=kick_tag_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=snare_bpm_range_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=hybrid_bpm_promote_snare p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=hybrid_key_match_pad p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
query=scale_minor_filter p@1=1.000 p@5=0.600 r@10=1.000 filter=1.000 must_recall=PASS
```

## Per-query-type coverage

| Query type | IDs in suite | Notes |
|------------|--------------|-------|
| Vector cluster | kick_cluster, snare_cluster, pad_cluster | Cosine ranking over orthogonal clusters |
| Metadata filter | kick_pred_type_filter, kick_tag_filter, snare_bpm_range_filter, scale_minor_filter | 100% filter compliance |
| Hybrid rerank | hybrid_bpm_promote_snare, hybrid_key_match_pad | BPM/key uplift vs semantic-only baseline |

## Tier B Phase 1 — CLAP semantic evidence (optional, not CI-blocking)

Measured on synthetic fixtures with real CLAP embeddings (`laion/clap-htsat-unfused`). Phase 1 covers query classes **`kick_snare_perc`** and **`pad_texture`** only (Issue #73 partial).

### Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-07-08 |
| Branch | `feat/clap-tier-b-phase1-evidence-73` |
| Base commit | `08e72c0` |
| OS | Windows 11 (10.0.26200) |
| Python | 3.12.10 (64-bit) |
| Suite | `tests/fixtures/search_quality/golden_v2_clap.yaml` |
| Tier | B (CLAP 512-d embeddings, NumPy search backend) |
| Catalog size | 12 synthetic samples (6 kick/snare/perc + 6 pad/texture) |
| Query count | 10 (6 text + 4 audio) |
| Work dir | `%TEMP%\sample-brain-clap-quality` (external; not committed) |

### Commands

```powershell
pip install -e ".[clap]"
.\.venv\Scripts\python.exe -m src.cli benchmark search-quality `
  --suite tests/fixtures/search_quality/golden_v2_clap.yaml `
  --work-dir $env:TEMP\sample-brain-clap-quality
.\.venv\Scripts\python.exe -m pytest -q tests/test_search_quality.py -m clap
```

Synthetic WAVs are generated at benchmark time via `src/search_quality_fixtures.py`; no audio files are committed.

### Aggregate results (Tier B Phase 1)

| Metric | Measured | Threshold | Verdict |
|--------|----------|-----------|---------|
| Mean P@1 | 0.700 | (informative) | — |
| Mean P@5 | 0.440 | ≥ 0.20 | **PASS** |
| Mean R@10 | 1.000 | ≥ 0.30 | **PASS** |
| MRR@10 | 0.792 | (informative) | — |
| Must-recall queries | 10/10 | all PASS | **PASS** |

### Per query class

| Query class | Queries | Mean P@5 | MRR |
|-------------|---------|----------|-----|
| `kick_snare_perc` | 6 | 0.433 | 0.875 |
| `pad_texture` | 4 | 0.450 | 0.667 |

### Per mode (text vs audio)

| Mode | Queries | Mean P@5 | MRR |
|------|---------|----------|-----|
| text | 6 | 0.400 | 0.653 |
| audio | 4 | 0.500 | 1.000 |

Audio-to-audio queries rank first relevant hit at rank 1 for all four audio references (MRR=1.000). Text queries show lower P@5 on cross-class discrimination (snare vs kick confusion).

### Failure buckets

| Bucket | Count | Meaning |
|--------|-------|---------|
| `success` | 7 | Relevant hits in top ranks; no hard-negative leak in top-5 |
| `negative_leak_top5` | 3 | Hard negative sample appeared in top-5 |

Queries with hard-negative leak:

| Query | Mode | P@5 | neg@5 | Notes |
|-------|------|-----|-------|-------|
| `snare_text_basic` | text | 0.200 | 3 | Kick samples ranked when querying "snare drum" |
| `pad_text_ambient` | text | 0.200 | 2 | Drum-class samples leaked for ambient texture query |
| `snare_audio_ref` | audio | 0.400 | 2 | Kick samples in top-5 when querying snare audio reference |

Hard negatives are **reported**, not enforced as a merge gate in Phase 1 — they document cross-class confusion on minimal synthetic fixtures.

### Full harness stdout

```
suite=tests\fixtures\search_quality\golden_v2_clap.yaml tier=B queries=10
mean_precision_at_1=0.700 mean_precision_at_5=0.440 mean_recall_at_10=1.000 mrr=0.792
gate_mean_precision_at_1=PASS
gate_mean_precision_at_5=PASS
gate_mean_recall_at_10=PASS
gate_must_recall_queries=PASS
gate_filter_compliance=PASS
per_query_class:
  class=kick_snare_perc p@5=0.433 mrr=0.875 queries=6
  class=pad_texture p@5=0.450 mrr=0.667 queries=4
per_mode:
  mode=audio p@5=0.500 mrr=1.000 queries=4
  mode=text p@5=0.400 mrr=0.653 queries=6
failure_buckets:
  success=7
  negative_leak_top5=3
```

### Limitations

- **Synthetic fixtures only** — kick/pulse/sine/chord/noise generators; not representative of real producer libraries.
- **Phase 1 scope** — does not cover riser/impact, vocal/no-vocal, dry/wet, or genre/mood query classes (#73 completion requires follow-up).
- **Local-only** — requires `[clap]` extra and HF model download; CI skips via `@pytest.mark.clap`.
- **No private samples** — no real library scans; work-dir artifacts stay outside the repo.

### Follow-up (#73 Phase 2+)

- ~~Expand query classes: riser/impact, vocal/no-vocal, dry/wet, genre/mood~~ → Phase 2 adds riser_impact + dry_wet (see below)
- vocal/no-vocal proxy and genre/mood curated set remain for Phase 2b/3
- Tighten hard-negative gates once baseline is stable

## Tier B Phase 2 — CLAP semantic evidence (optional, not CI-blocking)

Measured on synthetic fixtures with real CLAP embeddings (`laion/clap-htsat-unfused`). Phase 2 adds query classes **`riser_impact`** and **`dry_wet`** to the Phase 1 golden set (Issue #73 partial — 4/6 classes).

### Dry/Wet mini-spike (pre-gate)

Before adding `dry_wet` to the golden set, a local CLAP discrimination spike was run on one kick dry/wet pair:

| Check | Result |
|-------|--------|
| Work dir | `%TEMP%\sample-brain-clap-quality-p2-spike` |
| `"dry kick"` prefers dry over wet | **PASS** (margin +0.109 cosine) |
| `"reverb tail"` / `"wet kick with room"` prefer wet | **PASS** (margin +0.205 cosine) |
| Spike verdict | **PASS** — dry_wet included in golden set |

### Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-07-08 |
| Branch | `feat/clap-tier-b-phase2-evidence` |
| Base commit | `f1381fb` (Phase 1 on `main`) |
| OS | Windows 11 (10.0.26200) |
| Python | 3.12.10 (64-bit) |
| Suite | `tests/fixtures/search_quality/golden_v2_clap.yaml` |
| Tier | B (CLAP 512-d embeddings, NumPy search backend) |
| Catalog size | 24 synthetic samples (Phase 1: 12 + Phase 2: 12) |
| Query count | 23 (16 text + 7 audio) |
| Work dir | `%TEMP%\sample-brain-clap-quality-p2` (external; not committed) |

### Commands

```powershell
pip install -e ".[clap]"
.\.venv\Scripts\python.exe -m src.cli benchmark search-quality `
  --suite tests/fixtures/search_quality/golden_v2_clap.yaml `
  --work-dir $env:TEMP\sample-brain-clap-quality-p2
.\.venv\Scripts\python.exe -m pytest -q tests/test_search_quality.py -m clap
```

New synthetic generators in `src/search_quality_fixtures.py`: `freq_sweep_riser`, `impact_hit`, `wet_reverb` (FFT convolution with deterministic IR). Text queries may carry optional `query_style` (`keyword`, `natural_language`, `exclusion`) for reporting only — no ranking or gate impact. No audio files committed.

### Aggregate results (Tier B Phase 2 — full suite)

| Metric | Measured | Threshold | Verdict |
|--------|----------|-----------|---------|
| Mean P@1 | 0.391 | (informative) | — |
| Mean P@5 | 0.287 | ≥ 0.20 | **PASS** |
| Mean R@10 | 0.833 | ≥ 0.30 | **PASS** |
| MRR@10 | 0.544 | (informative) | — |
| Must-recall queries | 20/23 | (informative) | 3 FAIL |

### Per query class (Phase 2 full suite)

| Query class | Queries | Mean P@5 | MRR | Phase |
|-------------|---------|----------|-----|-------|
| `kick_snare_perc` | 6 | 0.400 | 0.688 | 1 |
| `pad_texture` | 4 | 0.300 | 0.467 | 1 |
| `riser_impact` | 6 | 0.300 | 0.521 | 2 |
| `dry_wet` | 7 | 0.171 | 0.485 | 2 |

### Per query style (text queries, reporting only)

Optional YAML field `query_style` groups producer-style text queries for evidence — **not** used in search ranking or gates.

| Query style | Queries | Mean P@5 | MRR | Example queries |
|-------------|---------|----------|-----|-----------------|
| `keyword` | 7 | 0.257 | 0.491 | `"dry kick"`, `"reverb tail"`, `"riser build up"` |
| `natural_language` | 7 | 0.229 | 0.404 | `"rising sweep sound"`, `"warm pad synth"` |
| `exclusion` | 2 | 0.100 | 0.125 | `"kick with no reverb tail"`, `"impact hit, not a kick"` |

**Interpretation (informative):** On this synthetic catalog, short keyword-style text queries slightly outperform natural-language phrasing; exclusion-style negation queries score lowest (P@5=0.100). This suggests CLAP handles simple producer keywords better than negation constraints on minimal fixtures — not a claim about real libraries.

### Per mode (text vs audio)

| Mode | Queries | Mean P@5 | MRR |
|------|---------|----------|-----|
| text | 16 | 0.225 | 0.407 |
| audio | 7 | 0.429 | 0.857 |

Audio-to-audio queries remain stronger than text (MRR=0.857). Text queries show increased cross-class confusion with the larger 24-sample catalog.

### Phase 2 query classes — synthetic catalog

| Class | Samples | Generators | Queries |
|-------|---------|------------|---------|
| `riser_impact` | 6 (3 riser + 3 impact) | `freq_sweep_riser`, `impact_hit` | 6 (5 text + 1 audio) |
| `dry_wet` | 6 (3 dry/wet pairs) | `kick_transient`/`sine_tone`/`perc_hit` + `wet_reverb` | 7 (5 text + 2 audio) |

### Text-to-sample evidence (Phase 2 classes)

| Query class | Text queries | Mean P@5 | Notes |
|-------------|--------------|----------|-------|
| `riser_impact` | 5 | 0.240 | `"riser build up"` and `"rising sweep sound"` rank risers at P@5=0.600; impact text queries weaker |
| `dry_wet` | 5 | 0.160 | Dry/wet text discrimination weak; exclusion query `"kick with no reverb tail"` P@5=0.200 |

### Audio-to-audio evidence (Phase 2 classes)

| Query class | Audio queries | Mean P@5 | MRR |
|-------------|---------------|----------|-----|
| `riser_impact` | 1 | 0.600 | 1.000 |
| `dry_wet` | 2 | 0.200 | 1.000 |

Audio references rank first relevant hit at rank 1 (MRR=1.000) for all Phase 2 audio queries.

### Failure buckets (Phase 2 full suite)

| Bucket | Count | Meaning |
|--------|-------|---------|
| `success` | 5 | Relevant hits in top ranks; no hard-negative leak in top-5 |
| `negative_leak_top5` | 15 | Hard negative sample appeared in top-5 |
| `must_recall_fail` | 3 | Relevant set not fully recalled within k=10 |

Notable hard-negative leaks: cross-class samples from the expanded 24-item catalog appear in top-5 for most Phase 2 queries. Phase 1 queries also show catalog-dilution regression (`snare_text_basic`, `pad_text_warm`, `texture_audio_ref` must-recall FAIL with 24 samples vs 10/10 PASS on 12-sample catalog).

Hard negatives and must-recall are **reported**, not enforced as merge gates — informative evidence only.

### Full harness stdout (Phase 2)

```
suite=tests\fixtures\search_quality\golden_v2_clap.yaml tier=B queries=23
mean_precision_at_1=0.391 mean_precision_at_5=0.287 mean_recall_at_10=0.833 mrr=0.544
gate_mean_precision_at_1=PASS
gate_mean_precision_at_5=PASS
gate_mean_recall_at_10=PASS
gate_must_recall_queries=FAIL
gate_filter_compliance=PASS
per_query_class:
  class=dry_wet p@5=0.171 mrr=0.485 queries=7
  class=kick_snare_perc p@5=0.400 mrr=0.688 queries=6
  class=pad_texture p@5=0.300 mrr=0.467 queries=4
  class=riser_impact p@5=0.300 mrr=0.521 queries=6
per_mode:
  mode=audio p@5=0.429 mrr=0.857 queries=7
  mode=text p@5=0.225 mrr=0.407 queries=16
per_query_style:
  style=exclusion p@5=0.100 mrr=0.125 queries=2
  style=keyword p@5=0.257 mrr=0.491 queries=7
  style=natural_language p@5=0.229 mrr=0.404 queries=7
failure_buckets:
  success=5
  negative_leak_top5=15
  must_recall_fail=3
```

### Limitations (Phase 2)

- **Synthetic fixtures only** — chirp/impact/reverb generators; not representative of real producer libraries.
- **Catalog dilution** — Phase 1 queries regress on must-recall when catalog grows from 12→24 samples.
- **query_style reporting** — optional YAML tag for text-query phrasing analysis; exclusion queries weakest on synthetic fixtures
- **Phase 2 scope** — 4/6 #73 query classes; `vocal_no_vocal` and `genre_mood` deferred (Phase 2b/3).
- **Local-only** — requires `[clap]` extra and HF model download; CI skips via `@pytest.mark.clap`.
- **No private samples** — no real library scans; work-dir artifacts stay outside the repo.
- **Issue #73 remains OPEN** — vocal/no-vocal and genre/mood still required for full acceptance.

### Follow-up (#73 Phase 2b/3)

- ~~Phase 2b: vocal/no-vocal with explicit proxy-only limitation~~ → spike run; **HOLD_VOCAL_PROXY_FAILED** (see below)
- Phase 3: genre/mood with curated public-domain mini-set (outside repo)
- Consider split suites or catalog partitioning to reduce dilution regression

## Tier B Phase 2b — vocal/no-vocal proxy spike (HOLD)

Isolated CLAP spike on synthetic formant/vowel fixtures vs instrumental controls. **Not merged into `golden_v2_clap.yaml`.** This is **not** evidence of real vocal discrimination.

### Run metadata

| Field | Value |
|-------|-------|
| Date | 2026-07-08 |
| Branch | `feat/clap-tier-b-vocal-proxy-spike` |
| Base commit | `9cd86cb` (Phase 2 on `main`) |
| Suite | `tests/fixtures/search_quality/golden_v2_clap_vocal_proxy_spike.yaml` |
| Catalog size | 6 (3 formant/vowel proxy + 3 instrumental) |
| Query count | 6 (4 text + 2 audio) |
| Work dir | external temp dir (not committed) |

### Commands

```powershell
pip install -e ".[clap]"
.\.venv\Scripts\python.exe -m src.cli benchmark search-quality `
  --suite tests/fixtures/search_quality/golden_v2_clap_vocal_proxy_spike.yaml `
  --work-dir $env:TEMP\sample-brain-clap-vocal-spike
.\.venv\Scripts\python.exe -m pytest -q tests/test_vocal_proxy_spike.py -m clap
```

New generators in `src/search_quality_fixtures.py`: `formant_tone`, `vowel_pad`. No audio committed.

### Spike verdict: **HOLD_VOCAL_PROXY_FAILED**

Stufe-1 margin gates **FAIL** — CLAP text embeddings do not prefer vocal-proxy over instrumental on mean-audio cosine margins:

| Check | Threshold | Measured | Verdict |
|-------|-----------|----------|---------|
| Text `"singing voice"` margin (vocal − instrumental) | ≥ +0.08 | **−0.063** | **FAIL** |
| Text `"vocal sound"` margin | ≥ +0.08 | **−0.010** | **FAIL** |
| Formant-proxy vs chord_pad margin | ≥ +0.05 | **−0.153** | **FAIL** |
| Audio-ref vocal-proxy top-1 in vocal class | rank 1 | rank 1 | PASS |
| Audio-ref instrumental top-1 in instrumental class | rank 1 | rank 1 | PASS |
| Isolated mean P@5 | ≥ 0.25 | 0.500 | PASS |

### Isolated benchmark (informative only)

| Metric | Measured |
|--------|----------|
| Mean P@5 | 0.500 |
| MRR@10 | 0.917 |
| Audio mode P@5 | 0.600 |
| Text mode P@5 | 0.450 |

Audio-to-audio discrimination works on the 6-sample catalog; **text-to-embedding margin gates fail**. Negative leaks in top-5 on all queries (6/6).

### Limitations and decision

- **Synthetic vocal-proxy only** — formant harmonics, not speech, lyrics, or producer vocal chops.
- **No real vocal discrimination claim** — spike does not justify adding `vocal_no_vocal` to Tier-B golden set.
- **No producer-library claim** — isolated 6-sample catalog only.
- **Issue #73 remains OPEN** — vocal/no-vocal requires separate data strategy (curated public-domain vocals); genre/mood still pending.
- **Next step:** defer `vocal_no_vocal` Tier-B evidence; plan genre_mood / public-domain vocal mini-set (Phase 3).

## Tier B stub (superseded by Phase 1 above)

- ~~Suite stub only~~ → Phase 1 golden set populated
- Run locally with `pip install -e ".[clap]"` and `@pytest.mark.clap` tests

## Regression gate (pytest)

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Campaign adds `tests/test_search_quality.py` (Tier A metrics + frozen P@5 baseline) and `tests/conftest.py` (`clap` marker). Full suite: **236 passed** (`pytest -q -m "not clap"`) + **2 optional** `[clap]` Tier-B tests when installed.

## Decision

**Tier A regression gates PASS.** The harness proves filter compliance, hybrid reranking, and P@K/R@K aggregation on deterministic fixtures. **Tier B Phase 1** delivers first measured CLAP semantic evidence on synthetic fixtures (P@5=0.440, MRR=0.792). **Tier B Phase 2** extends to 4/6 query classes (P@5=0.287, MRR=0.544 on 24-sample catalog); default merge gate remains Tier A only.

**Explicitly not measured here:** sqlite-vec latency, CLAP semantic accuracy on private samples, hybrid weight tuning, full #73 query-class coverage (vocal/no-vocal, genre/mood pending).
