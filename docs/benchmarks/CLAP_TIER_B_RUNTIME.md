# CLAP Tier-B Runtime — Reproducible Install & Run

Optional CLAP Tier-B search-quality evaluation requires the `[clap]` extra, a
Hugging Face model download, and external work directories. This document makes
the path reproducible on a clean machine, distinct from one-off spikes.

Issue: #218 (child of #73). Scope boundary: this document covers the **runtime
path only** — install, env vars, model cache, skip behavior. It does **not**
measure or interpret CLAP search quality (that belongs to #216 / #217 / #219).

## Authoritative model identity

| Field | Value |
|-------|-------|
| Model name | `laion/clap-htsat-unfused` |
| Embedding dimension | `512` |
| Modality | `audio_text` |
| Provider | `laion` |

These values are centralized as module constants in `src/embed.py`
(`CLAP_MODEL_NAME`, `CLAP_EMBEDDING_DIM`, `CLAP_MODALITY`, `CLAP_PROVIDER`) and
consumed by `model_info()`, the model loader, the Tier-B benchmark, and the
runtime tests. Do not change the model or the dimension without a dedicated
decision.

## Clean machine install

The package `pyproject.toml` declares `dependencies = []`. The real runtime
dependencies live in `requirements.txt`. Therefore `pip install -e ".[clap]"`
**alone does not install the base runtime** (no numpy, sqlalchemy, librosa,
etc.). Always install the base requirements first.

### Windows (Python 3.12)

```powershell
python -m venv <EXTERNAL_VENV>
<EXTERNAL_VENV>\Scripts\python.exe -m pip install --upgrade pip
<EXTERNAL_VENV>\Scripts\python.exe -m pip install -r requirements.txt
<EXTERNAL_VENV>\Scripts\python.exe -m pip install -e ".[clap]"
<EXTERNAL_VENV>\Scripts\python.exe -m pip install pytest
```

### Unix equivalent (Python 3.12)

```bash
python3.12 -m venv /tmp/sample-brain-clap-venv
/tmp/sample-brain-clap-venv/bin/python -m pip install --upgrade pip
/tmp/sample-brain-clap-venv/bin/python -m pip install -r requirements.txt
/tmp/sample-brain-clap-venv/bin/python -m pip install -e ".[clap]"
/tmp/sample-brain-clap-venv/bin/python -m pip install pytest
```

Equivalent extra install (no editable package resolution of base deps):

```bash
pip install -r requirements.txt -r requirements-clap.txt
pip install -e .
```

### Search harness also needs the `[vec]` extra

The Tier-B search-quality harness imports the search module, which imports
`sqlite_vec` unconditionally at module top. Therefore the harness (and any test
that imports `benchmark_search_quality`) additionally requires the `[vec]` extra
even though the CLAP embedding path itself does not use sqlite-vec:

```bash
<EXTERNAL_VENV>/Scripts/python.exe -m pip install -e ".[vec]"
```

This is a pre-existing import coupling, not changed by #218.

## Environment variables (all external — never inside the repo)

| Variable | Purpose |
|----------|---------|
| `SAMPLE_BRAIN_DB_PATH` | SQLite catalog used by the Tier-B benchmark. Point outside the repo (e.g. `%TEMP%/sample-brain-clap-repro/catalog.db`). |
| `SAMPLE_BRAIN_MODEL_CACHE_DIR` | Hugging Face model cache directory passed as `cache_dir` to `ClapModel.from_pretrained(...)` and `ClapProcessor.from_pretrained(...)`. Must be outside the repo. |
| `HF_HOME` | Optional, documented alternative for the transformers/HF cache. `ClapEmbeddingBackend` does **not** mutate `HF_HOME` itself; set it yourself if you prefer it over `SAMPLE_BRAIN_MODEL_CACHE_DIR`. |
| `--work-dir` (CLI) | Temporary benchmark working dir (generated WAV fixtures, golden catalog DB). Must be outside the repo. |

Example (Windows):

```powershell
$env:SAMPLE_BRAIN_DB_PATH = "$env:TEMP\sample-brain-clap-repro\catalog.db"
$env:SAMPLE_BRAIN_MODEL_CACHE_DIR = "$env:TEMP\sample-brain-clap-model-cache"
$dir = Join-Path $env:TEMP "sample-brain-clap-repro\work"
```

## First-run behavior

- **Online, empty cache:** the first explicit CLAP run downloads
  `laion/clap-htsat-unfused` (~500 MB) into the configured model cache. This
  first run is slower. `model_info()` never downloads — only `embed_text()` /
  `embed_audio()` trigger the lazy load.
- **Subsequent runs:** reuse the existing external model cache.
- **No automatic download** in these contexts: normal `pytest` CI, tests run
  with `-m "not clap"`, importing `src.embed`, and normal Sample-Brain core
  commands.

## Skip behavior (no CI model download)

| Situation | Result |
|----------|--------|
| `[clap]` deps missing (no torch/transformers) | CLAP test **SKIP** (clean) |
| deps present, online, model cached/missing | explicit CLAP test may load/download and run |
| deps present, offline, model cached | CLAP test runs from local cache |
| deps present, offline, model missing | **clean SKIP** with a clear reason — no traceback chaos |

Only a genuine **model/processor load failure** is turned into
`EmbeddingBackendUnavailableError` and therefore into a SKIP on the optional
`@pytest.mark.clap` path. Any failure **after** a successful model load
(wrong 512-d dimension, NaN/Inf embedding, audio load error, assertion error,
benchmark/quality error) remains a real **FAIL** and is never relabeled as a
runtime skip.

## Commands

Run the non-CLAP path (must be green without CLAP installed):

```bash
python -m pytest -q tests/test_clap_runtime_repro.py -m "not clap"
python -m pytest -q tests/test_search_quality.py -m "not clap"
```

Run the optional CLAP path (skips cleanly when unavailable):

```bash
python -m pytest -q tests/test_clap_runtime_repro.py -m clap
python -m pytest -q tests/test_search_quality.py -m clap
```

Run the Tier-B search-quality harness (real CLAP embeddings):

```bash
python -m src.cli benchmark search-quality `
  --suite tests/fixtures/search_quality/golden_v2_clap.yaml `
  --work-dir <EXTERNAL_WORK_DIR>
```

The harness requires `SAMPLE_BRAIN_MODEL_CACHE_DIR` (and the `[vec]` extra, see
above) to be set. When the CLAP runtime is unavailable, the command exits 1 with
a single clear `EmbeddingBackendUnavailableError` message instead of a raw
traceback.

Note: this harness asserts pre-existing CLAP search-quality gates
(`must_recall`/`neg@5`). Those gates may fail on the current `laion/clap-htsat`
text queries; such quality failures are **out of #218 scope** (quality belongs
to #216 / #217 / #219) and are intentionally not changed here. A non-zero exit
from the quality assertion is a quality signal, not a #218 runtime regression.

## Hard rules

- No private audio files. Synthetic WAVs are generated at benchmark time via
  `src/search_quality_fixtures.py`; none are committed.
- No CI model download. Normal CI runs `-m "not clap"`; the CLAP path is
  local/optional only.
- No generated artifacts in git: DB, indexes, WAVs, model weights, and caches
  stay outside the repo (see `docs/DATA_AND_ARTIFACT_POLICY.md`).
- Do not change CLAP search-quality thresholds, `relevant_sample_ids`, or
  `negative_sample_ids` here. Quality interpretation is #216 / #217 / #219.
