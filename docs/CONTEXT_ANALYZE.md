# One-shot Context Analyze

Issue [#233](https://github.com/jannekbuengener/sample-brain/issues/233) adds a local, DB-free Track Map v1 path:

```text
sample-brain context analyze <path> --json
```

Input is one local WAV or FLAC file. The command validates the path, creates a temporary canonical mono WAV for analysis, reuses the existing base-feature extractor, and prints deterministic Track Map `1.0.0` JSON. The original file is never modified and the temporary working audio is removed after the command.

The output contains only portable source identity: file name, size, SHA-1, and audio properties. It never serializes an absolute input path. The requested components are BPM, key, loudness, and brightness. Beat, downbeat, energy, and sections are explicitly `not_run` because they are outside #233's scope.

No catalog scan, import, database initialization, or persistent database mutation is performed.

Exit codes:

- `0`: Track Map JSON was produced.
- `2`: Invalid or unreadable input; stderr contains deterministic JSON with `status: "error"` and a stable error code.

Supported input failures include `FILE_NOT_FOUND`, `NOT_A_FILE`, `UNSUPPORTED_AUDIO_FORMAT`, and `AUDIO_LOAD_FAILED`. The command is local/offline and must not be used to add private audio files to the repository.
