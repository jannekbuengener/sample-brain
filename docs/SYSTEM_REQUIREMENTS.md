# System Requirements — Sample Brain

## 1. Functional Requirements

### 1.1 Scan — Library Indexing

| ID | Requirement | Priority |
|---|---|---|
| FR-SCAN-01 | The system shall recursively traverse a user-specified directory tree to discover audio files | P0 |
| FR-SCAN-02 | The system shall compute a content hash (SHA-1) for each discovered audio file for deduplication | P0 |
| FR-SCAN-03 | The system shall store file metadata (path, relative path, size, sample rate, channels, duration, hash) in a SQLite catalog | P0 |
| FR-SCAN-04 | The system shall skip files with unsupported or unrecognised audio extensions | P0 |
| FR-SCAN-05 | The system shall support scanning multiple roots sequentially or in a single pass | P1 |
| FR-SCAN-06 | The system shall detect and report files that have been renamed or moved since the last scan | P2 |

### 1.2 Analyze — Audio Feature Extraction

| ID | Requirement | Priority |
|---|---|---|
| FR-ANLZ-01 | The system shall extract BPM via onset detection or tempo estimation algorithms | P0 |
| FR-ANLZ-02 | The system shall extract musical key via chroma-based key detection | P0 |
| FR-ANLZ-03 | The system shall extract loudness (RMS energy, peak) | P0 |
| FR-ANLZ-04 | The system shall extract spectral brightness (spectral centroid) | P0 |
| FR-ANLZ-05 | The system shall extract MFCCs (Mel-frequency cepstral coefficients) | P0 |
| FR-ANLZ-06 | The system shall extract chroma features | P0 |
| FR-ANLZ-07 | The system shall persist extracted features in the SQLite catalog linked to the source sample | P0 |
| FR-ANLZ-08 | The system shall handle short audio files (< 1 second) gracefully without crashing | P1 |
| FR-ANLZ-09 | The system shall report analysis confidence or failure per sample | P1 |
| FR-ANLZ-10 | The system shall support re-analysis of individual samples without full re-scan | P2 |

### 1.3 Autotype — Sample Classification

| ID | Requirement | Priority |
|---|---|---|
| FR-TYPE-01 | The system shall classify samples by instrument category (kick, snare, hat, clap, tom, percussion, bass, pad, lead, fx, loop, drone, impact, vocal, other) using rule-based heuristics | P0 |
| FR-TYPE-02 | The system shall optionally use kNN classification trained on existing weak labels | P1 |
| FR-TYPE-03 | The system shall persist classification results (type, confidence) in the SQLite catalog | P0 |
| FR-TYPE-04 | The system shall allow disabling kNN to run rules-only classification | P1 |
| FR-TYPE-05 | The system shall support genre-specific classification profiles (seed lists, thresholds, regex tag maps) | P1 |

### 1.4 Export — FL Studio Browser Tags (Legacy/Fallback)

> **Note:** FL Studio Browser export is the current stable integration point but is classified as **legacy/fallback** per the VST3-first product target (Issues [#90](https://github.com/jannekbuengener/sample-brain/issues/90)–[#95](https://github.com/jannekbuengener/sample-brain/issues/95)). The main product path is the VST3 browser/assistant plugin; FL Studio Browser tags remain available for producers who use the CLI pipeline directly.

| ID | Requirement | Priority |
|---|---|---|
| FR-EXPT-01 | The system shall write FL Studio Browser-compatible tag files from analysis and classification results | P0 |
| FR-EXPT-02 | The system shall limit the number of tags per sample to a configurable maximum (default 10) | P0 |
| FR-EXPT-03 | The system shall write tags to a user-specified FL Studio User Data directory | P0 |
| FR-EXPT-04 | The system shall produce tag entries for BPM, key, and instrument type where available | P0 |
| FR-EXPT-05 | The system shall skip samples whose features are incomplete or missing | P1 |

### 1.5 Embed — Embedding Generation (EPIC 2)

| ID | Requirement | Priority |
|---|---|---|
| FR-EMBD-01 | The system shall provide a pluggable embedding backend interface (abstract base class) | P1 |
| FR-EMBD-02 | The system shall register embedding models with version metadata in the SQLite catalog | P1 |
| FR-EMBD-03 | The system shall persist embedding vectors (BLOB) linked to sample and model | P1 |
| FR-EMBD-04 | The system shall detect embedding staleness via content hash comparison | P1 |
| FR-EMBD-05 | The system shall support embedding of audio files (audio-to-vector) | P1 |
| FR-EMBD-06 | The system shall support embedding of text queries (text-to-vector) for later search | P1 |
| FR-EMBD-07 | The system shall guard ML library imports so core functionality works without torch/transformers | P1 |
| FR-EMBD-08 | The system shall support batch embedding with progress reporting and failure resume | P2 |

### 1.6 Index — Vector Index Build (EPIC 2)

| ID | Requirement | Priority |
|---|---|---|
| FR-IDX-01 | The system shall build a local FAISS vector index from stored embeddings on demand | P1 |
| FR-IDX-02 | The system shall support index rebuild from the SQLite catalog (source of truth) | P1 |
| FR-IDX-03 | The system shall store index files outside version control in a designated local directory | P1 |
| FR-IDX-04 | The system shall support at least IndexFlatIP (exact) and IndexIVFFlat (approximate) index types | P2 |

### 1.7 Search — Semantic Search (EPIC 2)

| ID | Requirement | Priority |
|---|---|---|
| FR-SRCH-01 | The system shall accept a natural language text query and return ranked sample results | P1 |
| FR-SRCH-02 | The system shall accept an audio file as a query and return similar samples | P2 |
| FR-SRCH-03 | The system shall return result metadata sufficient for producer workflow (filename, path, BPM, key, type, confidence) | P1 |
| FR-SRCH-04 | The system shall support configurable result count (top-k) | P1 |

---

## 2. Non-functional Requirements

### 2.1 Local-first

| ID | Requirement | Priority |
|---|---|---|
| NFR-LOC-01 | All core pipeline operations (scan, analyze, autotype, export) shall work fully offline | P0 |
| NFR-LOC-02 | No cloud account, API key, or network registration shall be required for any core function | P0 |
| NFR-LOC-03 | Cloud services may exist only as optional opt-in extensions, never as mandatory dependencies | P1 |

### 2.2 Privacy

| ID | Requirement | Priority |
|---|---|---|
| NFR-PRV-01 | Audio data shall never be transmitted to any external service by default | P0 |
| NFR-PRV-02 | Analysis results and metadata shall be stored exclusively in a local SQLite database unless the user explicitly exports or shares them | P0 |
| NFR-PRV-03 | No telemetry, analytics, or usage tracking shall be built into any core pipeline component | P1 |

### 2.3 Offline Capability

| ID | Requirement | Priority |
|---|---|---|
| NFR-OFF-01 | Scan, analyze, autotype, and export shall function with zero network access | P0 |
| NFR-OFF-02 | Embedding (EPIC 2) shall require model weights that are downloaded on first use, but the download is a one-time explicit opt-in | P1 |
| NFR-OFF-03 | After model weights are cached, embedding shall work offline | P1 |

### 2.4 Performance

| ID | Requirement | Priority |
|---|---|---|
| NFR-PRF-01 | Scan throughput shall be limited by filesystem I/O, not by application logic | P1 |
| NFR-PRF-02 | Analyze throughput on consumer hardware (CPU-only) shall process at least 1 sample per second for typical audio lengths (3-30 seconds) | P1 |
| NFR-PRF-03 | The SQLite catalog shall support up to 100,000 samples without degradation of basic queries | P1 |
| NFR-PRF-04 | FAISS approximate search (EPIC 2) shall return results in under one second for up to 100k samples | P2 |
| NFR-PRF-05 | CLI startup time to `--help` shall be under one second regardless of optional dependencies | P0 |

### 2.5 Reproducibility

| ID | Requirement | Priority |
|---|---|---|
| NFR-REP-01 | The same sample file with the same pipeline version shall produce identical analysis features | P0 |
| NFR-REP-02 | The same sample with the same embedding model version shall produce identical embedding vectors | P1 |
| NFR-REP-03 | Classification results shall be deterministic given the same input features and configuration | P0 |
| NFR-REP-04 | Model versions shall be pinned in the embedding registry to guarantee reproducibility | P1 |

### 2.6 Reliability

| ID | Requirement | Priority |
|---|---|---|
| NFR-REL-01 | The system shall not crash on corrupt, truncated, or unsupported audio files — it shall skip them and report the failure | P0 |
| NFR-REL-02 | Interrupted operations (scan, analyze, embed) shall be resumable or restartable without data corruption | P1 |
| NFR-REL-03 | The SQLite catalog shall use transactions for all write operations to maintain integrity | P0 |

### 2.7 Maintainability

| ID | Requirement | Priority |
|---|---|---|
| NFR-MNT-01 | Each pipeline step shall be a separate, independently testable module | P0 |
| NFR-MNT-02 | Optional dependencies shall be import-guarded so core functionality never requires ML libraries | P0 |
| NFR-MNT-03 | Configuration shall be externalised (not hardcoded) for library roots, model settings, and export paths | P1 |

---

## 3. System Constraints

| ID | Constraint | Value |
|---|---|---|
| CST-OS-01 | Primary target OS | Windows 10/11 (FL Studio is first target host, not a hard product dependency — all VST3-capable DAWs are potential hosts) |
| CST-OS-02 | Secondary target OS | macOS (>= 12) and Linux (Ubuntu 22.04+) |
| CST-PYTHON-01 | Python version | 3.12.10, pinned by `.python-version` |
| CST-PYTHON-02 | Package manager | pip with `requirements.txt` and optional extras |
| CST-DB-01 | Database engine | SQLite 3, accessed through SQLAlchemy |
| CST-DB-02 | Database format | Single file (`catalog.db`) in a local `data/` directory |
| CST-DB-03 | Database location | Untracked local artifact — never committed |
| CST-CLI-01 | CLI framework | Python `argparse` (standard library) |
| CST-CLI-02 | Entry point | `pyproject.toml` script entry, invocable as `sample-brain` |
| CST-DEPS-01 | Core dependencies | Runtime dependencies are pinned in `requirements.txt` (numpy, librosa, soundfile, SQLAlchemy, tqdm, PyYAML); heavy ML deps must stay optional |
| CST-DEPS-02 | Optional dependencies (EPIC 2 target) | torch and transformers must remain optional, preferably exposed through a `[clap]` extra. Not a core dependency. |
| CST-DEPS-03 | GPU | Not required — CPU-only is the default. CUDA is opt-in. |
| CST-STOR-01 | Model cache | Hugging Face cache (`~/.cache/huggingface/`) — system-global, untracked |
| CST-STOR-02 | Index storage | `data/indexes/` — untracked local artifact |
| CST-STOR-03 | Report storage | `reports/` — untracked local artifact |
| CST-PLUGIN-01 | Plugin format target | VST3 is the first plugin format; CLAP optional later (Issues #90–#95) |
| CST-PLUGIN-02 | Product incarnation | VST3 browser/assistant plugin first; standalone producing app later from the same core |
| CST-PLUGIN-03 | Host scope | FL Studio is first target host but not a hard dependency — all VST3-capable DAWs are supported |

---

## 4. Definition of Done

### 4.1 Per EPIC

| EPIC | Done when |
|------|-----------|
| **EPIC 0 — Hygiene & Docs** | Repository is self-contained, bootstrapable, documented. No generated artifacts tracked. README matches actual state. |
| **EPIC 1 — Config & Setup** | Library roots and model paths are configurable via profiles. Fresh clone setup is verified end-to-end. |
| **EPIC 2 — Semantic Search** | Embedding pipeline (embed → index → search) works locally with CLAP. Dependencies are optional. Artifacts are rebuildable and untracked. |
| **EPIC 3 — Ranking** | Hybrid search (vector + structured metadata) is implemented and testable. |
| **EPIC 4 — API & UI** | FastAPI service boots locally and exposes pipeline operations. Desktop UI is prototyped. |
| **EPIC 5 — DAW Workflow** | FL Studio export is stable and tested. Integration research for other DAWs is documented. |
| **EPIC 6 — Re-imagine** | DSP variant generation is prototyped with bounded scope. Generated audio is cacheable and exportable. |

### 4.2 Per Issue (template)

An issue is done when:

- All acceptance criteria are satisfied
- The corresponding module compiles and passes basic smoke tests
- No generated artifacts appear in `git status` after execution
- The change does not introduce new hardcoded paths or private data
- If relevant, documentation (README, pipeline docs) is updated
- Optional: a consuming workflow (CLI command) is verified

---

## 5. Data Model Overview

### 5.1 Core Entities

| Entity | Table | Key Fields | Purpose |
|--------|-------|------------|---------|
| **Sample** | `samples` | `id`, `path`, `relpath`, `hash`, `samplerate`, `channels`, `duration`, `size_bytes` | Represents a single audio file discovered during scan |
| **Feature** | `features` | `sample_id` (FK), `bpm`, `key`, `loudness`, `brightness`, `mfcc_mean`, `chroma_mean`, `pred_type` | Acoustic analysis results for one sample |
| **Embedding Model** | `embedding_models` | `id`, `provider`, `model_name`, `model_version`, `embedding_dim`, `modality` | Registry of embedding models ever used |
| **Sample Embedding** | `sample_embeddings` | `sample_id` (FK), `model_id` (FK), `embedding` (BLOB), `source_hash` | One embedding vector per sample per model version |

### 5.2 Future Entities

| Entity | Table | Purpose | Planned |
|--------|-------|---------|---------|
| **Embedding Job** | `embedding_jobs` | Track batch embedding progress, resume on failure | EPIC 2, P2 |
| **Vector Index** | `vector_indexes` | Track FAISS index builds (checksum, count, timestamp) | EPIC 2, P2 |
| **Search Log** | `search_log` | Local search interaction logging for ranking improvement | EPIC 3, P3 |

### 5.3 Data Flow

```
Filesystem          SQLite                    Filesystem (optional)
──────────          ──────                    ─────────────────────
Audio files   ──→   samples
                       ↓
                    features                  Reports, CSVs
                       ↓
                    embedding_models
                       ↓
                     sample_embeddings   ──→   NumPy `.npz` index (default) / sqlite-vec vec0 cache (opt-in)
                                                   ↓
                                               Search results
```

---

## 6. Testing and Validation Strategy

### 6.1 Test Levels

| Level | Scope | Method | Target |
|-------|-------|--------|--------|
| **Unit tests** | Individual modules (`scan.py`, `analyze.py`, `classify.py`, `db.py`, `embed.py`) | pytest | Core logic correctness |
| **Integration tests** | Multi-step workflows (scan → analyze → autotype) | pytest with fixtures | Pipeline coherence |
| **Smoke tests** | CLI entry point, `--help`, version flag | Shell invocation | Packaging and import sanity |
| **Validation report** | End-to-end analysis of a real library | `validation_report.py` | BPM/key plausibility, autotype quality |

### 6.2 Test Fixtures (planned)

| Fixture | Content | Purpose |
|---------|---------|---------|
| **One-shot** | Synthesised sine wave or short loop (0.5-2s) | Scan + analyze + autotype basic path |
| **Loop** | Synthesised drum loop or tonal phrase (4-8 bars) | BPM detection, loop classification |
| **Tonal sample** | Synthesised melodic phrase with known key | Key detection validation |

### 6.3 What is not tested

- Audio format compatibility beyond librosa's supported codecs
- Specific DAW versions or FL Studio release variants
- GPU-accelerated embedding paths
- Cloud or network-dependent features (none exist in core)

---

## 7. Future Doku-Stränge (vorgemerkt, nicht ausgearbeitet)

Die folgenden Dokumente sind als spätere Ergänzungen identifiziert, aber noch nicht erstellt:

| Dokument | Zweck |
|----------|-------|
| `docs/BOOTLOADER_AND_CONTEXT_STRATEGY.md` | Definition des Bootloaders, kontextuelle Pflichtdokumente, Code-Verständnis-Architektur |
| `docs/SAMPLE_BRAIN_SKILLS_SPEC.md` | Sample-Brain-spezifische Skills, Skill-Pack-Evaluierung, Integration in den MCP-Workflow |

Diese Themen werden im nächsten Doku-Durchlauf priorisiert. Sie haben keine Auswirkung auf die aktuellen System Requirements.
