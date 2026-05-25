# ADR-0001: Embedding Model Strategy

**Status:** Proposed  
**Applied:** Not yet  
**Deciders:** (project owner)

---

## Context

Sample Brain is a local-first sample library intelligence tool for music producers. EPIC 2 (Semantic Search Foundation) requires semantic embeddings to enable:

- Text-to-sample search (natural language queries over the sample catalog)
- Audio-to-audio similarity search (find similar samples from a reference audio file)

Constraints:

- **Local-first by default** — no cloud dependency for embedding generation
- **Reproducible embeddings** — same sample + same model version must yield the same vector
- **Versioned** — model metadata must be stored alongside embeddings to detect staleness
- **Backend-agnostic** — the system should not be locked into a single model provider

---

## Decision

**LAION-CLAP** (Contrastive Language-Audio Pretraining) is the primary candidate for the embedding backend.

Rationale:

- Designed for the exact use case: joint audio-text embedding space
- Pre-trained model available, open-source (MIT license for most variants)
- Produces a single 512-dim vector per audio input (variable by model variant)
- Supports both text and audio embedding from the same model
- Proven in producer/sample-search contexts

The embedding backend will be designed as a **pluggable abstraction**:

```python
class EmbeddingBackend(ABC):
    @abstractmethod
    def embed_audio(self, audio_path: str) -> np.ndarray: ...
    @abstractmethod
    def embed_text(self, text: str) -> np.ndarray: ...
    @abstractmethod
    def model_metadata(self) -> dict: ...
```

This allows future substitution (e.g. OpenL3, custom models) without changing the rest of the pipeline.

Model metadata that must be persisted:

- `provider` (e.g. "clap", "openl3")
- `model_name` (e.g. "laion/clap-htsat-fused")
- `model_version` (release tag or hash)
- `embedding_dim` (e.g. 512)
- `modality` (e.g. "audio+text")

---

## Alternatives Considered

| Alternative | Reason Not Chosen (as sole backend) |
|---|---|
| **OpenL3** | Audio-only embeddings; no native text query support. Strong candidate as secondary/fallback. |
| **Essentia / MusicNN** | Good for music tagging, but not designed for free-text similarity search. |
| **Hand-crafted audio features** (MFCC, chroma, etc.) | Already available in the pipeline; useful for hybrid ranking (EPIC 3) but insufficient for semantic search alone. |
| **Cloud APIs** (Whisper, Gemini, etc.) | Violates local-first constraint. Samples would leave the machine. |
| **Custom trained model** | Out of scope for EPIC 2; requires labeled data and training infra. |

---

## Consequences

1. **Dependency weight** — CLAP requires PyTorch and Transformers. These are large dependencies and will be introduced deliberately in a later commit (not in this ADR phase).
2. **Optional imports** — CLAP imports must be guarded (`try: import torch; except ImportError: …`). The core CLI and all existing pipeline steps must work without torch/transformers installed.
3. **CPU vs. GPU** — CLAP works on CPU (slow) and CUDA (fast). The backend must default to CPU and accept an optional `device` parameter. GPU support is opt-in.
4. **Model download** — The first run will download the model weights (~500 MB). This is acceptable for a local-first tool but should be surfaced to the user.
5. **Model cache as local artifact** — Downloaded weights are local untracked artifacts. Model cache directories and serialised weight files (`.pt`, `.pth`, `.safetensors`) must be in `.gitignore`.
6. **CI must stay fast** — CI smoke tests must not trigger model downloads. Compile-only checks suffice.
7. **Version pinning** — Model versions must be pinned in a config or registry to guarantee reproducibility. Upgrading the model invalidates existing embeddings.
8. **Not implemented yet** — This ADR documents the design decision only. No CLAP import, no model download, no embedding generation exists at the time of writing.

---

## Non-Goals

- No implementation in this commit
- No model downloads
- No sample processing
- No cloud embedding path (future optional add-on, not default)
