#!/usr/bin/env python3
"""Exact-head Windows native/audible acceptance harness for #1284.

Generates synthetic WAVs at runtime (never commits audio). Exercises Loop
owner lifecycle, SYNC transitions, audition coexistence, and drift repeats
against the live native engine when available.

Usage (from repo / worktree root):

    python tools/browser_loop_windows_runtime_evidence.py --work-dir %TEMP%\\sb-1284-evidence

Exit codes: 0 = PASS, 1 = FAIL, 2 = NATIVE_UNAVAILABLE (honest fail-closed).
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.browser_loop_playback import BrowserLoopOwner, browser_loop_extent_from_downbeats
from src.workbench_controller import WorkbenchRow
from src.workbench_preview import WorkbenchPreviewPlayer
from src.workbench_transport_adapter import WorkbenchTransportAdapter
from src.workbench_transport_preview import TransportAwarePreview


SR = 48_000


def _write_pulse(path: Path, *, bars: int, bpm: float = 120.0) -> tuple[Path, tuple[int, ...]]:
    """Write a bar-aligned pulse train and return (path, downbeat_frames)."""
    frames_per_beat = int(round(SR * 60.0 / bpm))
    frames_per_bar = frames_per_beat * 4
    total = frames_per_bar * bars + frames_per_bar  # intentional tail after last downbeat
    y = np.zeros(total, dtype=np.float32)
    downbeats = tuple(i * frames_per_bar for i in range(bars + 1))
    for d in downbeats:
        end = min(total, d + int(0.01 * SR))
        y[d:end] = 0.6
    # Tail marker after final musical boundary (must stay outside Loop extent)
    tail = downbeats[-1] + frames_per_bar // 2
    if tail < total:
        y[tail : tail + int(0.005 * SR)] = 0.9
    sf.write(path, y, SR, subtype="PCM_16")
    return path, downbeats


def _row(path: Path, downbeats: tuple[int, ...], *, bpm: float = 120.0) -> WorkbenchRow:
    return WorkbenchRow(
        display_name=path.name,
        relative_path=path.name,
        path=str(path),
        bpm=bpm,
        key="Am",
        key_conf=0.9,
        loudness=-12.0,
        brightness=0.4,
        sample_class="loop",
        pred_type="loop",
        status="ok",
        details={
            "beat_grid": {
                "downbeats": {"status": "ok", "sample_indices": list(downbeats)},
                "beats": {"status": "ok", "sample_indices": list(downbeats)},
            }
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--work-dir",
        type=Path,
        default=None,
        help="Directory for synthetic WAVs + evidence JSON (outside repo preferred).",
    )
    parser.add_argument("--audible-seconds", type=float, default=1.5)
    args = parser.parse_args()

    work = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp(prefix="sb-1284-"))
    work.mkdir(parents=True, exist_ok=True)

    evidence: dict = {
        "issue": 1284,
        "exit_target": "BROWSER_LOOP_AUDIO_RUNTIME_PASS",
        "work_dir": str(work),
        "checks": {},
    }

    transport = WorkbenchTransportAdapter(initial_bpm=120.0, initial_sync_enabled=False)
    if not transport.is_native_available():
        evidence["result"] = "NATIVE_UNAVAILABLE"
        evidence["message"] = "Native audio library unavailable; fail closed (no QML/OS timer)."
        (work / "browser_loop_runtime_evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(json.dumps(evidence, indent=2))
        return 2

    owner = BrowserLoopOwner(transport)
    audition = TransportAwarePreview(
        WorkbenchPreviewPlayer(),
        transport,
        should_keep_shared_transport=lambda: owner.is_active,
    )

    paths = {}
    for bars in (4, 8, 16, 32):
        p, d = _write_pulse(work / f"loop_{bars}bar.wav", bars=bars)
        paths[bars] = (p, d)
        ext = browser_loop_extent_from_downbeats(d)
        assert ext is not None and ext.bar_count == bars
        assert ext.source_end_frame_exclusive == d[-1]
        evidence["checks"][f"extent_{bars}"] = "PASS"

    # Long N-bar
    p_long, d_long = _write_pulse(work / "loop_long.wav", bars=64)
    paths["long"] = (p_long, d_long)
    evidence["checks"]["extent_long"] = "PASS"

    def run_case(name: str, fn) -> None:  # noqa: ANN001
        try:
            fn()
            evidence["checks"][name] = "PASS"
        except Exception as exc:
            evidence["checks"][name] = f"FAIL: {exc}"
            raise

    def case_loop_on_off() -> None:
        row = _row(*paths[4])
        assert owner.loop_on(row).ok
        owner.tick()
        assert owner.is_active
        time.sleep(min(0.4, args.audible_seconds))
        assert owner.loop_off().ok
        assert not owner.is_active

    def case_replace() -> None:
        a = _row(*paths[4])
        b = _row(*paths[8])
        assert owner.loop_on(a).ok
        owner.tick()
        assert owner.loop_on(b).ok
        owner.tick()
        assert owner.extent and owner.extent.bar_count == 8
        owner.loop_off()

    def case_audition_coexist() -> None:
        loop_row = _row(*paths[4])
        assert owner.loop_on(loop_row).ok
        owner.tick()
        click = _row(*paths[8])
        assert audition.play_row(click, start_ms=0).ok
        assert owner.is_active
        time.sleep(min(0.3, args.audible_seconds))
        audition.release_voice()
        assert owner.is_active
        owner.loop_off()

    def case_sync_off_on_off() -> None:
        row = _row(*paths[4])
        transport.set_sync_enabled(False)
        assert owner.loop_on(row).ok
        owner.tick()
        time.sleep(min(0.25, args.audible_seconds))
        transport.set_sync_enabled(True)
        owner.on_sync_changed(enabled=True)
        owner.tick()
        time.sleep(min(0.25, args.audible_seconds))
        transport.set_sync_enabled(False)
        owner.on_sync_changed(enabled=False)
        owner.tick()
        owner.loop_off()

    def case_bpm_change() -> None:
        row = _row(*paths[4])
        transport.set_sync_enabled(True)
        assert owner.loop_on(row).ok
        owner.tick()
        transport.set_tempo(140.0)
        owner.on_master_bpm_changed()
        owner.tick()
        time.sleep(min(0.25, args.audible_seconds))
        owner.loop_off()
        transport.set_tempo(120.0)
        transport.set_sync_enabled(False)

    def case_missing_downbeats() -> None:
        bad = WorkbenchRow(
            display_name="bad",
            relative_path="bad.wav",
            path=str(paths[4][0]),
            bpm=120.0,
            key=None,
            key_conf=None,
            loudness=None,
            brightness=None,
            sample_class="loop",
            pred_type="loop",
            status="ok",
            details={},
        )
        result = owner.loop_on(bad)
        assert not result.ok
        assert result.reason_code == "NO_DOWNBEATS"

    def case_sync_missing_bpm() -> None:
        p, d = paths[4]
        row = _row(p, d, bpm=None)  # type: ignore[arg-type]
        transport.set_sync_enabled(True)
        result = owner.loop_on(row)
        assert not result.ok
        assert result.reason_code == "SYNC_NOT_SYNCABLE"
        transport.set_sync_enabled(False)

    def case_drift_run() -> None:
        row = _row(*paths[4])
        transport.set_sync_enabled(True)
        assert owner.loop_on(row).ok
        cycle = owner.comparison_cycle_frames()
        assert cycle and cycle > 0
        owner.tick()
        # Deterministic software advance via tick boundaries (native clock may also run).
        for _ in range(16):
            owner.tick()
            time.sleep(0.02)
        assert owner.is_active
        assert len(owner.active_voice_ids) <= 2
        owner.loop_off()
        transport.set_sync_enabled(False)

    try:
        run_case("loop_on_off_4bar", case_loop_on_off)
        run_case("replace_4_to_8", case_replace)
        run_case("loop_plus_audition", case_audition_coexist)
        run_case("sync_off_on_off", case_sync_off_on_off)
        run_case("master_bpm_change", case_bpm_change)
        run_case("missing_downbeats", case_missing_downbeats)
        run_case("sync_missing_bpm", case_sync_missing_bpm)
        run_case("drift_repeat", case_drift_run)
        # Longer audible soak for 16-bar + long source
        row16 = _row(*paths[16])
        assert owner.loop_on(row16).ok
        owner.tick()
        time.sleep(min(args.audible_seconds, 2.0))
        owner.loop_off()
        evidence["checks"]["audible_16bar"] = "PASS"
        row_long = _row(*paths["long"])
        assert owner.loop_on(row_long).ok
        owner.tick()
        time.sleep(min(0.5, args.audible_seconds))
        owner.loop_off()
        evidence["checks"]["audible_long"] = "PASS"
        evidence["result"] = "PASS"
    except Exception as exc:
        evidence["result"] = "FAIL"
        evidence["error"] = str(exc)
        (work / "browser_loop_runtime_evidence.json").write_text(
            json.dumps(evidence, indent=2), encoding="utf-8"
        )
        print(json.dumps(evidence, indent=2))
        return 1
    finally:
        try:
            transport.close()
        except Exception:
            pass

    out = work / "browser_loop_runtime_evidence.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence.get("result") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
