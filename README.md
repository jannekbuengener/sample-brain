**AI-powered sample management for FL Studio**  
Scan → Analyze → Tag → Export. Stay in your flow.  

---

## 🎨 UI Mockup

![sample-brain UI](./ui_mockup.png)

---

## 🚀 Features (MVP)

- **Scan**: build a database from your sample library  
- **Analyze**: extract audio features (BPM, key, loudness, brightness, MFCCs, chroma …)  
- **Autotype**: automatic categorization (Kick, Snare, Pad, Drone, Impact …)  
- **Export**: write smart tags into the **FL Studio Browser**  

---

## 🛠️ Setup

```bash
# Create virtual environment
python -m venv .venv

# Activate (Windows)
. .venv\Scripts\activate
# Activate (macOS/Linux)
# source .venv/bin/activate

pip install -r requirements.txt

# For CLAP embedding backend (optional):
pip install -r requirements.txt -r requirements-clap.txt
# or: pip install -e ".[clap]"

# For sqlite-vec search backend (optional):
pip install -e ".[vec]"
# or: pip install -r requirements-vec.txt
```

---

## Bootstrap / Fresh Setup Validation

Use this path to verify a clean checkout before feature work. Prefer an **isolated venv outside the repo** for agent validation.

**Python:** 3.12 required (`.python-version` pins `3.12.10`). Minor 3.12.x patch drift is acceptable if tests pass.

**Linux system notes:**
- `python3.12-venv` (or `python3-venv`) may be required for `python -m venv`; fallback: `pip install virtualenv && virtualenv .venv`
- `libsndfile1` is required for audio analysis (`soundfile` / `librosa` analyze path)

```bash
# Isolated venv (example paths — keep outside repo)
python3.12 -m venv /tmp/sample-brain-bootstrap-venv
source /tmp/sample-brain-bootstrap-venv/bin/activate   # Windows: ...\Scripts\activate

pip install --upgrade pip
pip install -r requirements.txt pytest
pip install -e .

# CLI validation
python -m src.cli --help
sample-brain --help

# Test validation (fresh venv: 138 passed as of bootstrap validation)
python -m pytest -q

# External DB smoke (no repo-local DB artifacts)
export SAMPLE_BRAIN_DB_PATH=/tmp/sample-brain-bootstrap-smoke/catalog.db   # Windows: set env var
python -m src.cli init
# init must print the external DB path; parent dir is created outside repo

# Optional synthetic WAV smoke (no CLAP model download)
mkdir -p /tmp/sample-brain-bootstrap-fixtures
# generate a tiny WAV outside repo (stdlib wave or soundfile), then:
python -m src.cli scan --root /tmp/sample-brain-bootstrap-fixtures
python -m src.cli analyze
```

**Guardrails:**
- Do not use private samples for bootstrap validation.
- Do not commit DB files, indexes, model caches, or generated runtime artifacts.
- Do not run CLAP model download during bootstrap validation (`embed --backend clap` is out of scope here).

See also [`CONTRIBUTING.md`](./CONTRIBUTING.md) for contributor verification commands.

---

## 🏃 Quickstart

```bash
# Initialize DB
python -m src.cli init

# Scan sample folder (uses library_roots from profile)
python -m src.cli scan

# Scan with explicit root override (repeatable)
python -m src.cli scan --root "<SAMPLE_LIBRARY_ROOT>"
python -m src.cli scan --root "<ROOT_A>" --root "<ROOT_B>"

# Analyze audio features
python -m src.cli analyze

# Autotype samples (uses use_knn / knn_min_conf from profile)
python -m src.cli autotype                                          # uses profile config
python -m src.cli autotype --no-knn                                 # disable kNN for this run

# Export tags to FL Studio (uses fl_user_data_path from profile)
python -m src.cli export_fl                                         # uses profile config
python -m src.cli export_fl --fl-user-data "<FL_USER_DATA_PATH>"    # override for this run
python -m src.cli export_fl --max-tags 3                            # limit tags per sample

# Embedding pipeline (experimental — requires CLAP backend)
python -m src.cli embed --backend noop --limit 5                    # noop placeholder, no real embedding
python -m src.cli embed --backend clap --limit 5                    # requires pip install torch transformers

# Index & search (NumPy default; sqlite-vec opt-in — see below)
python -m src.cli index_build --model-id 1                          # build NumPy vector index (in-memory)
python -m src.cli index_build --model-id 1 --save                   # build + persist to data/indexes/ as .npz
python -m src.cli index_build --model-id 1 --save --index-path "custom/path.npz"  # custom save path
python -m src.cli search "kick" --model-id 1                        # search (noop: shows "not configured" message)
python -m src.cli search "kick" --model-id 1 --backend clap         # search (clap stub: shows "not available" message)
python -m src.cli search "kick" --model-id 1 --backend clap --index-path "data/indexes/model-1-numpy-cosine.npz"  # load persisted index

# sqlite-vec path (optional — requires pip install -e ".[vec]")
python -m src.cli vec status                                        # report sqlite-vec availability
python -m src.cli vec smoke                                         # exit 0 when extension loads
python -m src.cli index_build --model-id 1 --search-backend sqlite-vec   # rebuild vec0 cache in SQLite DB
python -m src.cli search "kick" --model-id 1 --search-backend sqlite-vec  # search via vec0 cache (no --index-path)
python -m src.cli db doctor                                         # SQLite integrity + catalog checks
python -m src.cli benchmark vec --samples 1000 10000 100000 --work-dir "%TEMP%\\sample-brain-bench"  # gate harness (Windows)
```

**Search backend default:** `numpy` (profile key `search.backend`). Opt in to `sqlite-vec` via `--search-backend`, `SAMPLE_BRAIN_SEARCH_BACKEND`, or profile. Precedence: profile &lt; env &lt; CLI. Gate evidence: [`docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md`](./docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md) — overlap PASS; 100k latency FAIL on measured host; default stays `numpy` until all gates PASS.

**Artifact safety:** Keep runtime DBs, vec0 cache data, `.npz` indexes, and benchmark work directories outside the repo (`SAMPLE_BRAIN_DB_PATH`, `--work-dir` under `%TEMP%`). Do not commit generated artifacts.

---

## ⚙️ Configuration

### Profile-based Config

Sample Brain uses YAML configuration profiles. See `config/profiles.example.yaml` for the full reference.

For your local machine, copy the example and replace the placeholders:

```bash
cp config/profiles.example.yaml config/profiles.local.yaml
```

`config/profiles.local.yaml` is gitignored — no local paths are ever committed.

### CLI Overrides

| Flag | Scope | Example |
|------|-------|---------|
| `--profile <name>` | All commands | `--profile minimal-demo embed --limit 1` |
| `--config <path>` | All commands | `--config config/profiles.example.yaml embed --limit 1` |
| `scan --root <path>` | Scan only | `scan --root "<ROOT_A>" --root "<ROOT_B>"` |
| `embed --backend <name>` | Embed only | `embed --backend clap --limit 1` |
| `embed --limit <n>` | Embed only | `embed --backend noop --limit 5` |
| `index_build --model-id <id>` | Index only | `index_build --model-id 1 --limit 100` |
| `index_build --limit <n>` | Index only | `index_build --model-id 1 --limit 100` |
| `index_build --save` | Index only | `index_build --model-id 1 --save` |
| `index_build --index-path <path>` | Index only | `index_build --model-id 1 --save --index-path "custom.npz"` |
| `index_build --search-backend <name>` | Index only | `index_build --model-id 1 --search-backend sqlite-vec` |
| `search [query] --model-id <id>` | Search only | `search "kick" --model-id 1 --topk 20` |
| `search --topk <n>` | Search only | `search "kick" --model-id 1 --topk 20` |
| `search --backend <name>` | Search only | `search "kick" --model-id 1 --backend clap` |
| `search --search-backend <name>` | Search only | `search "kick" --model-id 1 --search-backend sqlite-vec` |
| `search --index-path <path>` | Search only | `search "kick" --model-id 1 --backend clap --index-path "data/indexes/model-1-numpy-cosine.npz"` |
| `export_fl --fl-user-data <path>` | Export only | `export_fl --fl-user-data "<FL_USER_DATA_PATH>"` |
| `export_fl --max-tags <n>` | Export only | `export_fl --max-tags 3` |
| `autotype --no-knn` | Autotype only | `autotype --no-knn` |

**Note:** `analyze` does not accept `--root` (it reads sample paths from the pre-scanned catalog, not from filesystem roots). To analyze different samples, re-run `scan --root <path>` first, then `analyze`.

### Environment Variables

| Variable | Overrides |
|----------|-----------|
| `SAMPLE_BRAIN_PROFILE` | Active profile name |
| `SAMPLE_BRAIN_EMBEDDING_BACKEND` | Embedding backend |
| `SAMPLE_BRAIN_LIBRARY_ROOTS` | Library root paths |
| `SAMPLE_BRAIN_FL_USER_DATA` | FL Studio user data path |
| `SAMPLE_BRAIN_MODEL_CACHE_DIR` | Model cache directory |
| `SAMPLE_BRAIN_DB_PATH` | SQLite database path |
| `SAMPLE_BRAIN_SEARCH_BACKEND` | Vector search backend (`numpy` or `sqlite-vec`) |
| `SAMPLE_BRAIN_MAX_TAGS` | Export max tags |

### Precedence

```
built-in default < example profile < local profile < environment variables < CLI flags
```

**Security:** Never commit real sample paths, DB files, reports, indexes, model caches, or FL Studio user data paths.
Local paths belong in `config/profiles.local.yaml` (which is gitignored).
See [`docs/DATA_AND_ARTIFACT_POLICY.md`](./docs/DATA_AND_ARTIFACT_POLICY.md) for the full policy.

---

## 📚 Documentation

### Architecture & Requirements

- [Product Requirements](./docs/PRODUCT_REQUIREMENTS.md) — vision, audience, problem, MVP scope
- [System Requirements](./docs/SYSTEM_REQUIREMENTS.md) — functional and non-functional requirements, constraints
- [Target Architecture](./docs/TARGET_ARCHITECTURE.md) — current and target pipeline, component boundaries, data flow
- [Data and Artifact Policy](./docs/DATA_AND_ARTIFACT_POLICY.md) — what is committed vs untracked

### EPIC Specs

- [EPIC 1: Config and Profiles](./docs/EPIC_1_CONFIG_PROFILES.md) — configuration layers, profile design, env vars, migration plan
- [EPIC 2: Semantic Search Foundation](./docs/EPIC_2_SEMANTIC_SEARCH_SPEC.md) — embedding, indexing, search contracts and milestones
- [SQLite + sqlite-vec Roadmap](./docs/SQLITE_VEC_ROADMAP.md) — phased rollout (Phases 1–8 complete; default switch gated)
- [sqlite-vec gate evidence](./docs/benchmarks/SQLITE_VEC_GATE_EVIDENCE.md) — measured benchmark gates (default stays `numpy`)
- [DAW Integration](./docs/DAW_INTEGRATION_SPEC.md) — FL Studio export, Ableton/Reaper research

### Project

- [Issue Backlog](./docs/ISSUE_BACKLOG.md) — planned work across all epics
- [Project Structure](./STRUCTURE.md)  
- [Docs folder](./docs/README.md) (setup, roadmap, details)

---

## ⚖️ License

MIT License – free to use, hack and share.  
Dependencies: see [THIRD_PARTY_LICENSES.md](./THIRD_PARTY_LICENSES.md).  

---

🎧 **Your sound. Your flow.**
