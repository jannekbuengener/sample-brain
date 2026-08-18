# Quick Capture — local Voice-to-Issue

Quick Capture is the small Workbench microphone flow for turning a short spoken note into a GitHub issue in `jannekbuengener/sample-brain`.

## Runtime contract

The flow is local until the final GitHub issue write:

1. Workbench records through the existing native audio engine.
2. The take is stored under the user-local Workbench state directory (`~/.sample-brain/recordings` by default, or `SAMPLE_BRAIN_WORKBENCH_STATE_DIR/recordings`).
3. Sample Brain renders a temporary **16 kHz, mono, PCM16 WAV** for whisper.cpp.
4. `whisper-cli` transcribes locally.
5. Obvious secrets and absolute local paths are redacted from the transcript.
6. `gh issue create` sends the redacted text to the public Sample-Brain GitHub repository.
7. On success the local recording is deleted. On transcription/GitHub failure it is retained for retry.

No cloud speech API is used.

## Required local tools

Quick Capture intentionally does not download or install third-party software itself.

### whisper.cpp

Use the official `whisper-cli` binary and a local ggml model. Configure:

```text
SAMPLE_BRAIN_WHISPER_CPP=<absolute path to whisper-cli / whisper-cli.exe>
SAMPLE_BRAIN_WHISPER_MODEL=<absolute path to ggml model file>
SAMPLE_BRAIN_WHISPER_LANGUAGE=auto
```

`SAMPLE_BRAIN_WHISPER_LANGUAGE` is optional and defaults to `auto`.

The adapter follows the official whisper.cpp CLI contract with `--model`, `--language`, `--file`, `--no-timestamps`, and `--no-prints`. whisper.cpp documents the CLI input as 16-bit WAV and demonstrates 16 kHz mono PCM16 conversion; Sample Brain prepares that format locally before invocation.

Official upstream reference:

- https://github.com/ggml-org/whisper.cpp

### GitHub CLI

`gh` must be installed and authenticated for the account allowed to create Sample-Brain issues. Sample Brain invokes only the narrow command:

```text
gh issue create --repo jannekbuengener/sample-brain --title <title> --body <redacted transcript>
```

Official command reference:

- https://cli.github.com/manual/gh_issue_create

## Public-repository warning

The Sample-Brain repository is public. Quick Capture therefore redacts obvious token/secret assignments and absolute local paths before issue creation. This is a guard, not a general-purpose data-loss-prevention system: do not dictate passwords, credentials, private keys, private sample names, or other sensitive material into Quick Capture.

## Failure behavior

- Native audio unavailable: no recording starts.
- whisper.cpp/model missing or transcription fails: no issue is created; the original local WAV is retained.
- No speech recognized: no issue is created; the empty recording is removed.
- `gh` missing/not authenticated/write fails: no issue is created; the WAV is retained.
- Successful issue creation: issue URL/number is shown in the Workbench status and the local WAV is removed.

## Manual smoke

1. Configure whisper.cpp paths above and ensure `gh auth status` is healthy.
2. Start `python -m src.cli workbench`.
3. Click **Mikrofon**.
4. Speak a short non-sensitive test note.
5. Click **Mikrofon stoppen**.
6. Verify an issue number/URL appears.
7. Verify the created issue contains the spoken text and no absolute local recording path.
8. Verify no Quick Capture WAV remains after success.
