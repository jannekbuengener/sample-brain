# One-shot Context Analyze

Issue [#233](https://github.com/jannekbuengener/sample-brain/issues/233) adds a local, DB-free Track Map v1 path:

```text
sample-brain context analyze <path> --json
```

Input is one local WAV or FLAC file. The command validates the path, creates a temporary canonical mono WAV for analysis, reuses the existing base-feature extractor, and prints deterministic Track Map `1.0.0` JSON. The original file is never modified and the temporary working audio is removed after the command.

The output contains only portable source identity: file name, size, SHA-1, and audio properties. It never serializes an absolute input path. The requested components are BPM, key, loudness, and brightness. Beat, downbeat, energy, and sections are explicitly `not_run` because they are outside #233's scope.

No catalog scan, import, database initialization, or persistent database mutation is performed.

### Cache & Provenance (#237)

`context analyze` can reuse expensive Track-Analyse-Ergebnisse via a local,
regenerable, file-based cache (see `docs/TRACK_ANALYSIS_CACHE_V1.md`). The cache
is opt-in by default but active; it lives user-local outside the repo.

Cache control flags:

- `--track-cache-dir <path>` — override the cache target directory.
- `--no-track-cache` — disable the cache entirely (always recompute).

The cache key is a SHA-256 over canonical deterministic JSON that includes the
source audio content hash, the `analyze` component id, the cache contract version,
the sample-brain analysis version, the librosa backend name/version, and the
relevant analyzer configuration (`bpm_normalization`, canonical sample rate,
canonical channels, `ANALYZE_SR`, `ANALYZE_HOP_LENGTH`). On a cache hit the
expensive feature extraction is skipped and the analysis values are reused; the
current source file is re-probed so the returned Track Map still shows the current
file name and audio properties.

The Track Map provenance `analyze` component carries a `parameter_fingerprint`
(SHA-256 of the effective analyzer parameters and analysis identity), so identical
analyses are reproducible and cache invalidation is auditable.

For programmatic use, `analyze_context_file` stays backwards compatible; the new
`analyze_context_file_cached` returns the Track Map plus `cache_status`
(`hit` | `miss` | `disabled`) and `cache_key`. The cache status is execution
evidence only and is never written into the portable Track Map.

Exit codes:

- `0`: Track Map JSON was produced.
- `2`: Invalid or unreadable input; stderr contains deterministic JSON with `status: "error"` and a stable error code.

Supported input failures include `FILE_NOT_FOUND`, `NOT_A_FILE`, `UNSUPPORTED_AUDIO_FORMAT`, and `AUDIO_LOAD_FAILED`. The command is local/offline and must not be used to add private audio files to the repository.
