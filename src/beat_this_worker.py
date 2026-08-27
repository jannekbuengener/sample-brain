"""Isolated process entrypoint for the optional ``beat_this`` backend."""

from __future__ import annotations

import argparse
import contextlib
import json
import multiprocessing
import sys


RESULT_MARKER = "SAMPLE_BRAIN_BEAT_THIS_RESULT="


def _emit(payload: dict[str, object]) -> None:
    print(RESULT_MARKER + json.dumps(payload, sort_keys=True), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--device", required=True)
    args = parser.parse_args(argv)

    try:
        from beat_this.inference import File2Beats
    except (ImportError, ModuleNotFoundError):
        _emit({"status": "failed", "code": "BACKEND_UNAVAILABLE"})
        return 2

    try:
        # Third-party initialization may write progress/log records. Keep the
        # parent protocol on stdout unambiguous and never re-enter deconstruct.
        with contextlib.redirect_stdout(sys.stderr):
            tracker = File2Beats(
                checkpoint_path=args.checkpoint, device=args.device, dbn=False
            )
            beats_sec, downbeats_sec = tracker(args.input)
        _emit(
            {
                "status": "ok",
                "beats_sec": [float(value) for value in beats_sec],
                "downbeats_sec": [float(value) for value in downbeats_sec],
            }
        )
        return 0
    except Exception:
        _emit({"status": "failed", "code": "INFERENCE_FAILED"})
        return 1


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
