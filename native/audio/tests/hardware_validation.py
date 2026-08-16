#!/usr/bin/env python3
"""
Hardware validation script for samplebrain_audio native core.

Run this on a Windows machine with Visual Studio build tools after building the native library.

Usage:
    python hardware_validation.py --buffer 512 --duration 600
    python hardware_validation.py --buffer 256 --duration 600 --record
    python hardware_validation.py --device-lost-test
"""

import argparse
import sys
import time
import json
from pathlib import Path

# Add parent to path for native_audio import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

try:
    from native_audio import NativeAudioEngine, EngineConfig, VoiceConfig, is_available
except ImportError as e:
    print(f"ERROR: Could not import native_audio: {e}")
    print("Ensure native library is built and in PATH")
    sys.exit(1)


def run_playback_test(buffer_frames: int, duration_sec: float, sample_rate: int = 48000) -> dict:
    """Run playback-only test with two click tracks."""
    print(f"\n=== Playback Test: buffer={buffer_frames}, duration={duration_sec}s ===")

    engine = NativeAudioEngine()
    try:
        config = EngineConfig(
            sample_rate=sample_rate,
            buffer_frames=buffer_frames,
            output_channels=2,
            input_channels=2,
        )
        engine.open(config)
        engine.start()

        # Voice A: 128 BPM -> 132 BPM target
        engine.create_voice(VoiceConfig(
            id=1,
            bpm=128.0,
            initial_rate=132.0 / 128.0,
        ))

        # Voice B: 140 BPM -> 132 BPM target
        engine.create_voice(VoiceConfig(
            id=2,
            bpm=140.0,
            initial_rate=132.0 / 140.0,
        ))

        # Schedule both at same frame
        time.sleep(0.1)
        snap = engine.snapshot()
        start_frame = snap.engine_frame + int(0.5 * sample_rate)

        print(f"Scheduling voices at frame {start_frame} (engine frame: {snap.engine_frame})")
        engine.schedule_voice_start(1, start_frame)
        engine.schedule_voice_start(2, start_frame)

        # Wait for playback
        print(f"Playing for {duration_sec} seconds...")
        time.sleep(duration_sec)

        final_snap = engine.snapshot()

        # Collect results
        result = {
            "test": "playback",
            "buffer_frames": buffer_frames,
            "duration_sec": duration_sec,
            "sample_rate": sample_rate,
            "start_frame": start_frame,
            "end_engine_frame": final_snap.engine_frame,
            "voice_1": {
                "requested_start": start_frame,
                "actual_start": final_snap.actual_start_frame[0],
                "skew_frames": final_snap.start_skew_frames[0],
                "rate": final_snap.voice_rates[0],
            },
            "voice_2": {
                "requested_start": start_frame,
                "actual_start": final_snap.actual_start_frame[1],
                "skew_frames": final_snap.start_skew_frames[1],
                "rate": final_snap.voice_rates[1],
            },
            "callback_mean_us": final_snap.callback_mean_us,
            "callback_p95_us": final_snap.callback_p95_us,
            "callback_p99_us": final_snap.callback_p99_us,
            "callback_max_us": final_snap.callback_max_us,
            "underflow_count": final_snap.underflow_count,
            "overflow_count": final_snap.overflow_count,
            "xrun_count": final_snap.xrun_count,
            "recording_dropped_frames": final_snap.recording_dropped_frames,
            "device_status": final_snap.device_status,
        }

        # Print summary
        print(f"Voice 1 skew: {result['voice_1']['skew_frames']} frames")
        print(f"Voice 2 skew: {result['voice_2']['skew_frames']} frames")
        print(f"Callback: mean={result['callback_mean_us']:.2f}us, p95={result['callback_p95_us']:.2f}us, max={result['callback_max_us']:.2f}us")
        print(f"Xruns: {result['xrun_count']} (underflows={result['underflow_count']}, overflows={result['overflow_count']})")
        print(f"Device status: {result['device_status']}")

        return result

    finally:
        engine.close()


def run_playback_recording_test(buffer_frames: int, duration_sec: float, sample_rate: int = 48000) -> dict:
    """Run playback + recording test."""
    print(f"\n=== Playback + Recording Test: buffer={buffer_frames}, duration={duration_sec}s ===")

    engine = NativeAudioEngine()
    try:
        config = EngineConfig(
            sample_rate=sample_rate,
            buffer_frames=buffer_frames,
            output_channels=2,
            input_channels=2,
        )
        engine.open(config)
        engine.start()

        # Voice A: 128 BPM -> 132 BPM
        engine.create_voice(VoiceConfig(
            id=1,
            bpm=128.0,
            initial_rate=132.0 / 128.0,
        ))

        # Voice B: 140 BPM -> 132 BPM
        engine.create_voice(VoiceConfig(
            id=2,
            bpm=140.0,
            initial_rate=132.0 / 140.0,
        ))

        # Schedule both and start recording at same frame
        time.sleep(0.1)
        snap = engine.snapshot()
        start_frame = snap.engine_frame + int(0.5 * sample_rate)

        print(f"Scheduling voices and recording at frame {start_frame}")
        engine.schedule_voice_start(1, start_frame)
        engine.schedule_voice_start(2, start_frame)

        rec_id = engine.start_recording(start_frame)
        print(f"Recording started (id={rec_id})")

        print(f"Running for {duration_sec} seconds...")
        time.sleep(duration_sec)

        # Stop recording
        audio_data, frames = engine.stop_recording(rec_id)
        print(f"Recording stopped: {frames} frames captured ({len(audio_data)} bytes)")

        final_snap = engine.snapshot()

        result = {
            "test": "playback_recording",
            "buffer_frames": buffer_frames,
            "duration_sec": duration_sec,
            "sample_rate": sample_rate,
            "start_frame": start_frame,
            "end_engine_frame": final_snap.engine_frame,
            "recorded_frames": frames,
            "voice_1": {
                "requested_start": start_frame,
                "actual_start": final_snap.actual_start_frame[0],
                "skew_frames": final_snap.start_skew_frames[0],
                "rate": final_snap.voice_rates[0],
            },
            "voice_2": {
                "requested_start": start_frame,
                "actual_start": final_snap.actual_start_frame[1],
                "skew_frames": final_snap.start_skew_frames[1],
                "rate": final_snap.voice_rates[1],
            },
            "callback_mean_us": final_snap.callback_mean_us,
            "callback_p95_us": final_snap.callback_p95_us,
            "callback_p99_us": final_snap.callback_p99_us,
            "callback_max_us": final_snap.callback_max_us,
            "underflow_count": final_snap.underflow_count,
            "overflow_count": final_snap.overflow_count,
            "xrun_count": final_snap.xrun_count,
            "recording_dropped_frames": final_snap.recording_dropped_frames,
            "device_status": final_snap.device_status,
        }

        print(f"Voice 1 skew: {result['voice_1']['skew_frames']} frames")
        print(f"Voice 2 skew: {result['voice_2']['skew_frames']} frames")
        print(f"Callback: mean={result['callback_mean_us']:.2f}us, max={result['callback_max_us']:.2f}us")
        print(f"Xruns: {result['xrun_count']}")
        print(f"Recording dropped frames: {result['recording_dropped_frames']}")

        return result

    finally:
        engine.close()


def run_device_lost_test(buffer_frames: int = 512) -> dict:
    """
    Test device loss and recovery.
    NOTE: This requires manual intervention - disable/enable audio device in Windows Sound settings.
    """
    print(f"\n=== Device Lost/Recovery Test: buffer={buffer_frames} ===")
    print("INSTRUCTIONS:")
    print("1. Test will start engine")
    print("2. When prompted, DISABLE the output device in Windows Sound settings")
    print("3. Wait for 'Device lost detected' message")
    print("4. RE-ENABLE the device")
    print("5. Wait for recovery")
    print("6. Press Enter to continue")

    engine = NativeAudioEngine()
    try:
        config = EngineConfig(
            sample_rate=48000,
            buffer_frames=buffer_frames,
            output_channels=2,
            input_channels=2,
        )
        engine.open(config)
        engine.start()

        # Create a voice to keep engine active
        engine.create_voice(VoiceConfig(id=1, bpm=128.0))
        time.sleep(0.1)
        snap = engine.snapshot()
        engine.schedule_voice_start(1, snap.engine_frame + 24000)

        input("\nPress Enter after disabling audio device...")

        # Monitor device status
        lost_detected = False
        recovered = False
        for i in range(60):  # 30 seconds max
            snap = engine.snapshot()
            if snap.device_status == 1 and not lost_detected:  # SB_DEVICE_LOST
                print("Device LOST detected")
                lost_detected = True
            elif snap.device_status == 2 and lost_detected and not recovered:  # SB_DEVICE_RECOVERING
                print("Device RECOVERING...")
            elif snap.device_status == 0 and lost_detected and not recovered:  # SB_DEVICE_OK
                print("Device RECOVERED")
                recovered = True
                break
            time.sleep(0.5)

        if not lost_detected:
            print("WARNING: Device loss not detected (may not support hot-plug)")
        if not recovered:
            print("WARNING: Device did not recover within timeout")

        final_snap = engine.snapshot()

        result = {
            "test": "device_lost_recovery",
            "buffer_frames": buffer_frames,
            "lost_detected": lost_detected,
            "recovered": recovered,
            "final_device_status": final_snap.device_status,
            "xrun_count": final_snap.xrun_count,
            "callback_max_us": final_snap.callback_max_us,
        }

        return result

    finally:
        engine.close()


def main():
    parser = argparse.ArgumentParser(description="Hardware validation for samplebrain_audio")
    parser.add_argument("--buffer", type=int, default=512, choices=[512, 256, 128, 64],
                        help="Buffer size in frames")
    parser.add_argument("--duration", type=float, default=600,
                        help="Test duration in seconds (default: 600 = 10 min)")
    parser.add_argument("--sample-rate", type=int, default=48000,
                        help="Sample rate (default: 48000)")
    parser.add_argument("--record", action="store_true",
                        help="Run playback + recording test")
    parser.add_argument("--device-lost-test", action="store_true",
                        help="Run device lost/recovery test (manual)")
    parser.add_argument("--output", type=str,
                        help="Output JSON file for results")

    args = parser.parse_args()

    if not is_available():
        print("ERROR: Native audio library not available")
        print("Build native/audio first (see BUILD.md)")
        sys.exit(1)

    print(f"samplebrain_audio hardware validation")
    print(f"Buffer: {args.buffer} frames, Duration: {args.duration}s, Sample rate: {args.sample_rate}Hz")

    results = []

    try:
        if args.device_lost_test:
            result = run_device_lost_test(args.buffer)
            results.append(result)
        else:
            # Playback test
            result = run_playback_test(args.buffer, args.duration, args.sample_rate)
            results.append(result)

            # Playback + recording if requested
            if args.record:
                result = run_playback_recording_test(args.buffer, args.duration, args.sample_rate)
                results.append(result)

    except KeyboardInterrupt:
        print("\nTest interrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Print PASS/FAIL summary
    print("\n=== SUMMARY ===")
    all_pass = True
    for r in results:
        if r["test"] in ("playback", "playback_recording"):
            skew1 = abs(r["voice_1"]["skew_frames"])
            skew2 = abs(r["voice_2"]["skew_frames"])
            pass_skew = skew1 == 0 and skew2 == 0
            pass_xruns = r["xrun_count"] < 10  # Allow some xruns
            pass_device = r["device_status"] == 0
            test_pass = pass_skew and pass_xruns and pass_device
            all_pass = all_pass and test_pass

            status = "PASS" if test_pass else "FAIL"
            print(f"{r['test']} (buffer={r['buffer_frames']}): {status}")
            print(f"  Skew: v1={skew1}, v2={skew2} {'OK' if pass_skew else 'FAIL'}")
            print(f"  Xruns: {r['xrun_count']} {'OK' if pass_xruns else 'FAIL'}")
            print(f"  Device: {'OK' if pass_device else 'FAIL'}")

        elif r["test"] == "device_lost_recovery":
            # Device lost test is informational
            print(f"Device lost test: lost_detected={r['lost_detected']}, recovered={r['recovered']}")

    if args.output:
        with open(args.output, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to {args.output}")

    if all_pass:
        print("\nOVERALL: PASS")
        sys.exit(0)
    else:
        print("\nOVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()