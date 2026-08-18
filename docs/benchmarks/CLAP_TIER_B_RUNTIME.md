# CLAP Tier-B Runtime — Reproducible Install & Run

Optional CLAP search-quality evaluation remains local/opt-in. #423 makes the Python runtime and model snapshot reproducible without turning model download into a Core or CI requirement.

## Pinned runtime identity

| Field | Value |
|---|---|
| Python | `3.12` |
| PyTorch | `2.13.0` |
| Transformers | `5.14.1` |
| Model | `laion/clap-htsat-unfused` |
| Model revision | `79b58ed25fc00386262a2bea4b19fd21dc4310a0` |
| Serialization | `safetensors` required (`use_safetensors=True`) |
| Declared model license | `Apache-2.0` |
| Embedding dimension | `512` |
| Modality | `audio_text` |
| Provider | `laion` |

`requirements-clap.txt` and the `clap` extra in `pyproject.toml` carry the same exact package pins. `src.embed.ClapEmbeddingBackend` passes the immutable model revision to both `ClapModel.from_pretrained()` and `ClapProcessor.from_pretrained()`. The model loader additionally requires `use_safetensors=True`, so the supported path does not fall back to the repository's legacy Pickle checkpoint.

Transformers has changed the documented shape/type of `get_text_features()` and `get_audio_features()` across releases. Sample Brain normalizes direct tensors, pooled model-output objects, and non-empty tuple/list output at the CLAP adapter boundary; the existing worker still rejects any vector that is not the configured 512 dimensions.

## Why the safetensors revision is pinned

The older model snapshot exposes `pytorch_model.bin`. Pickle-backed PyTorch model loading is a code-execution boundary when artifacts are untrusted. The pinned official model-repository commit adds a safetensors representation, and Sample Brain explicitly requires it. This is a supply-chain hardening decision; it does not change CLAP quality thresholds or model identity.

## Clean-machine install

Install the base runtime first, then the optional CLAP extra.

### Windows / Python 3.12

```powershell
python -m venv <EXTERNAL_VENV>
<EXTERNAL_VENV>\Scripts\python.exe -m pip install --upgrade pip
<EXTERNAL_VENV>\Scripts\python.exe -m pip install -r requirements.txt
<EXTERNAL_VENV>\Scripts\python.exe -m pip install -r requirements-clap.txt
<EXTERNAL_VENV>\Scripts\python.exe -m pip install -e . pytest
```

Equivalent extra install:

```powershell
<EXTERNAL_VENV>\Scripts\python.exe -m pip install -r requirements.txt
<EXTERNAL_VENV>\Scripts\python.exe -m pip install -e ".[clap]"
```

### Unix equivalent

```bash
python3.12 -m venv /tmp/sample-brain-clap-venv
/tmp/sample-brain-clap-venv/bin/python -m pip install --upgrade pip
/tmp/sample-brain-clap-venv/bin/python -m pip install -r requirements.txt -r requirements-clap.txt
/tmp/sample-brain-clap-venv/bin/python -m pip install -e . pytest
```

## No-download dependency smoke

The path-scoped Windows CI smoke for #423 may install the two pinned Python packages and import `torch`, `transformers`, `ClapModel`, and `ClapProcessor`. It must **not** call `from_pretrained()` and therefore must not download model weights.

Core CI remains independent of the optional ML stack.

## External runtime locations

| Variable / argument | Purpose |
|---|---|
| `SAMPLE_BRAIN_DB_PATH` | external SQLite catalog for benchmark/runtime work |
| `SAMPLE_BRAIN_MODEL_CACHE_DIR` | external Hugging Face cache passed to model + processor loaders |
| `HF_HOME` | optional Hugging Face cache alternative; Sample Brain does not mutate it |
| `--work-dir` | external benchmark work directory |

Example:

```powershell
$env:SAMPLE_BRAIN_DB_PATH = "$env:TEMP\sample-brain-clap-repro\catalog.db"
$env:SAMPLE_BRAIN_MODEL_CACHE_DIR = "$env:TEMP\sample-brain-clap-model-cache"
```

## First-run and fallback behavior

- `model_info()` reports the immutable safetensors revision and never downloads a model.
- The first explicit `embed_text()` / `embed_audio()` call may download the pinned safetensors snapshot when online and not cached.
- Subsequent runs reuse the external cache.
- Core imports and normal Core commands do not require `torch` or `transformers`.
- Missing/broken optional dependencies resolve through `EmbeddingBackendUnavailableError` instead of breaking Core.
- A missing safetensors artifact fails as unavailable; the supported loader does not fall back to Pickle.
- Optional `@pytest.mark.clap` tests may skip cleanly when the model runtime/cache is unavailable.
- Once a model is loaded, dimension/NaN/audio/quality failures remain real failures and are not relabeled as availability skips.

## Commands

Core/no-model path:

```bash
python -m pytest -q tests/test_model_readiness.py
python -m pytest -q tests/test_clap_runtime_repro.py -m "not clap"
python -m pytest -q tests/test_search_quality.py -m "not clap"
```

Explicit optional model path:

```bash
python -m pytest -q tests/test_clap_runtime_repro.py -m clap
python -m pytest -q tests/test_search_quality.py -m clap
```

Tier-B search-quality harness:

```powershell
python -m src.cli benchmark search-quality `
  --suite tests/fixtures/search_quality/golden_v2_clap.yaml `
  --work-dir <EXTERNAL_WORK_DIR>
```

`sqlite-vec` is a separate optional search backend. It is not a prerequisite for merely importing the CLAP runtime; install `[vec]` only when the selected search path actually requires sqlite-vec.

## Commercial/readiness boundary

The pinned Hugging Face model card declares `Apache-2.0`; Sample Brain records that declaration separately from technical runtime state. See `docs/MODEL_READINESS_V1.md` for the readiness policy and Demucs code-vs-weight distinction.

## Hard rules

- No private audio in the repository.
- No CI model download.
- No Pickle fallback in the supported CLAP model loader.
- No model weights/caches/DB/index/WAV benchmark artifacts in git.
- Do not alter CLAP search-quality thresholds as part of runtime-readiness work.
- Do not float package versions or the Hugging Face model revision in the supported #423 matrix.
